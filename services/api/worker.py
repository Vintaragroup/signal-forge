"""
worker.py — SignalForge Render Job Worker

Polls Redis for ``asset_render`` jobs and processes them through the
ComfyUI → FFmpeg pipeline.

Status flow
-----------
  queued → running → generated → needs_review
  queued → running → failed

Safety guarantees
-----------------
- simulation_only: True on every updated record
- outbound_actions_taken: 0 always
- No external publishing, scheduling, or platform API calls
- COMFYUI_ENABLED=false  → mock ComfyUI result, no HTTP calls
- FFMPEG_ENABLED=false   → mock assembly result, no subprocess spawned

Usage
-----
  python worker.py            # production — runs until SIGTERM/SIGINT
  python worker.py --once     # process one job then exit (CI / smoke test)
  python worker.py --dry-run  # print next job without processing it
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo import MongoClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_db():
    """Return (MongoClient, database) using MONGO_URI env var."""
    uri = os.getenv("MONGO_URI", "mongodb://mongo:27017/signalforge")
    db_name = uri.rsplit("/", 1)[-1].split("?")[0] or "signalforge"
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return client, client[db_name]


def _serialize_doc(doc: Any) -> Any:
    """Recursively convert ObjectId / datetime to JSON-safe types."""
    if isinstance(doc, dict):
        return {k: _serialize_doc(v) for k, v in doc.items()}
    if isinstance(doc, list):
        return [_serialize_doc(v) for v in doc]
    if isinstance(doc, ObjectId):
        return str(doc)
    if isinstance(doc, datetime):
        return doc.isoformat()
    return doc


def _env_enabled(name: str, default: str = "false") -> bool:
    return str(os.getenv(name, default)).strip().lower() in ("1", "true", "yes", "on")


def _find_by_id(collection: Any, id_str: str) -> Optional[dict]:
    """Find a record by string id, trying ObjectId first."""
    try:
        doc = collection.find_one({"_id": ObjectId(id_str)})
        if doc:
            return doc
    except Exception:
        pass
    return collection.find_one({"_id": id_str})


# ---------------------------------------------------------------------------
# Core processing function — testable independently of the worker loop
# ---------------------------------------------------------------------------

def process_render_job(job: dict, db: Any) -> dict:
    """
    Execute one asset render job.

    Accepts a job dict (from the queue) and a live MongoDB database object.
    Returns a result dict with keys:
        render_id, status, comfyui_result, assembly_result[, error]

    All database writes carry simulation_only=True and outbound_actions_taken=0.
    This function may be called directly in tests without Redis.
    """
    render_id_str = str(job.get("render_id", ""))
    comfyui_enabled = _env_enabled("COMFYUI_ENABLED")
    ffmpeg_enabled = _env_enabled("FFMPEG_ENABLED")

    # ------------------------------------------------------------------
    # Locate render record
    # ------------------------------------------------------------------
    record = _find_by_id(db.asset_renders, render_id_str)
    if not record:
        logger.error("Render record not found: %s", render_id_str)
        return {
            "render_id": render_id_str,
            "status": "failed",
            "error": "Render record not found",
        }

    # ------------------------------------------------------------------
    # Mark running
    # ------------------------------------------------------------------
    db.asset_renders.update_one(
        {"_id": record["_id"]},
        {"$set": {"status": "running", "updated_at": _utc_now()}},
    )
    logger.info("render_id=%s status=running", render_id_str)

    try:
        # --------------------------------------------------------------
        # ComfyUI step
        # --------------------------------------------------------------
        comfyui_result: dict[str, Any] = {}
        generated_image_path = ""

        if comfyui_enabled:
            try:
                sys.path.insert(0, "/app")
                from agents.comfyui_client import ComfyUIClient  # type: ignore

                comfyui = ComfyUIClient()
                pg = _find_by_id(db.prompt_generations, record.get("prompt_generation_id", ""))
                if pg:
                    comfyui_result = comfyui.run_from_prompt_generation(
                        _serialize_doc(pg),
                        workflow_path=os.getenv("COMFYUI_WORKFLOW_PATH", ""),
                    )
                    generated_image_path = comfyui_result.get("output_image_path", "")
                else:
                    comfyui_result = {
                        "error": "prompt_generation not found for ComfyUI step",
                        "simulation_only": True,
                        "outbound_actions_taken": 0,
                    }
            except Exception as exc:
                comfyui_result = {
                    "error": f"{type(exc).__name__}: {exc}",
                    "simulation_only": True,
                    "outbound_actions_taken": 0,
                }
        else:
            comfyui_result = {
                "skipped": True,
                "skip_reason": "comfyui_disabled",
                "mock_image_path": f"/tmp/signalforge_renders/mock_comfyui_{render_id_str}.png",
                "simulation_only": True,
                "outbound_actions_taken": 0,
            }
            generated_image_path = comfyui_result["mock_image_path"]

        db.asset_renders.update_one(
            {"_id": record["_id"]},
            {"$set": {"status": "generated", "comfyui_result": comfyui_result, "updated_at": _utc_now()}},
        )
        logger.info("render_id=%s status=generated", render_id_str)

        # --------------------------------------------------------------
        # Snippet lookup for duration / captions
        # --------------------------------------------------------------
        snippet = _find_by_id(db.content_snippets, record.get("snippet_id", ""))
        duration_seconds = float((snippet or {}).get("duration_seconds") or 30.0)

        # --------------------------------------------------------------
        # FFmpeg / video assembly step
        # --------------------------------------------------------------
        assembly_result: dict[str, Any] = {}
        final_file_path = ""

        add_captions = record.get("add_captions", False)
        source_audio_path = record.get("source_audio_path", "")
        generation_engine = record.get("generation_engine", "comfyui")
        resolution = record.get("resolution", "1080x1920")

        try:
            from video_assembler import assemble_video  # type: ignore

            caption_text = ""
            if add_captions:
                pg = _find_by_id(db.prompt_generations, record.get("prompt_generation_id", ""))
                if pg:
                    caption_text = (
                        pg.get("caption_overlay_suggestion")
                        or ((snippet or {}).get("transcript_text", "")[:120])
                        or ""
                    )

            va_result = assemble_video(
                image_path=generated_image_path,
                audio_path=source_audio_path,
                duration_seconds=duration_seconds,
                add_captions=add_captions,
                caption_text=caption_text,
                resolution=resolution,
                generation_engine=generation_engine,
                asset_render_id=render_id_str,
            )
            assembly_result = va_result.to_dict()
            final_file_path = va_result.file_path

        except ImportError:
            assembly_result = {
                "skipped": True,
                "skip_reason": "video_assembler_unavailable",
                "mock": True,
                "mock_file_path": f"/tmp/signalforge_renders/mock_{render_id_str}.mp4",
                "simulation_only": True,
                "outbound_actions_taken": 0,
            }
            final_file_path = assembly_result["mock_file_path"]

        # --------------------------------------------------------------
        # Transition to needs_review
        # --------------------------------------------------------------
        db.asset_renders.update_one(
            {"_id": record["_id"]},
            {
                "$set": {
                    "status": "needs_review",
                    "assembly_result": assembly_result,
                    "file_path": final_file_path,
                    "duration_seconds": duration_seconds,
                    "simulation_only": True,
                    "outbound_actions_taken": 0,
                    "updated_at": _utc_now(),
                }
            },
        )
        logger.info("render_id=%s status=needs_review", render_id_str)

        return {
            "render_id": render_id_str,
            "status": "needs_review",
            "comfyui_result": comfyui_result,
            "assembly_result": assembly_result,
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

    except Exception as exc:
        logger.exception("Render job failed for render_id=%s", render_id_str)
        db.asset_renders.update_one(
            {"_id": record["_id"]},
            {
                "$set": {
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                    "simulation_only": True,
                    "outbound_actions_taken": 0,
                    "updated_at": _utc_now(),
                }
            },
        )
        return {
            "render_id": render_id_str,
            "status": "failed",
            "error": str(exc),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

_shutdown = False


def _handle_signal(signum: int, _frame: Any) -> None:
    global _shutdown
    logger.info("Signal %s received — shutting down after current job", signum)
    _shutdown = True


def run_worker_loop() -> None:
    """Main event loop.  Polls Redis until SIGTERM / SIGINT."""
    from job_queue import dequeue_render_job, move_to_failed  # type: ignore

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info(
        "SignalForge worker listening for render jobs. "
        "COMFYUI_ENABLED=%s FFMPEG_ENABLED=%s REDIS_URL=%s",
        os.getenv("COMFYUI_ENABLED", "false"),
        os.getenv("FFMPEG_ENABLED", "false"),
        os.getenv("REDIS_URL", "redis://redis:6379"),
    )

    mongo_client, db = _make_db()
    try:
        while not _shutdown:
            try:
                job = dequeue_render_job(timeout=5)
            except Exception as exc:
                # Transient Redis error — log and continue polling
                logger.warning("dequeue error (%s: %s) — retrying in 2s", type(exc).__name__, exc)
                import time
                time.sleep(2)
                continue

            if job is None:
                continue

            render_id = job.get("render_id", "unknown")
            job_id = job.get("job_id", "unknown")
            logger.info("Processing job_id=%s render_id=%s", job_id, render_id)

            try:
                result = process_render_job(job, db)
                logger.info("job_id=%s finished status=%s", job_id, result.get("status"))
            except Exception as exc:
                logger.exception("Unhandled exception in process_render_job render_id=%s", render_id)
                try:
                    move_to_failed(job)
                except Exception:
                    pass
    finally:
        mongo_client.close()
        logger.info("Worker stopped.")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--dry-run" in args:
        from job_queue import dequeue_render_job  # type: ignore
        job = dequeue_render_job(timeout=2)
        if job:
            logger.info("Next job (dry-run, not processed): %s", job)
        else:
            logger.info("Queue is empty.")
        sys.exit(0)

    if "--once" in args:
        from job_queue import dequeue_render_job  # type: ignore
        _client, _db = _make_db()
        try:
            job = dequeue_render_job(timeout=2)
            if job:
                result = process_render_job(job, _db)
                logger.info("Processed one job: %s", result)
            else:
                logger.info("No job available — exiting.")
        finally:
            _client.close()
        sys.exit(0)

    run_worker_loop()
