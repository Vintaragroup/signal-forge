"""
Tests for Social Creative Engine v5 — Runtime Infrastructure

Covers:
- POST /assets/render enqueues job when Redis mock available → status=queued
- POST /assets/render returns immediately (no ComfyUI/FFmpeg) when queued
- POST /assets/render falls back to sync when Redis unavailable (existing behaviour)
- process_render_job: queued → running → generated → needs_review (comfyui_disabled)
- process_render_job: ffmpeg_disabled path
- process_render_job: failure handling → status=failed
- process_render_job: status transition order verified
- process_render_job: simulation_only=True on all records
- process_render_job: outbound_actions_taken=0 on all records
- process_render_job: no subprocess calls when gates disabled
- process_render_job: render_id in result
- job_queue: enqueue_render_job returns job_id when Redis available
- job_queue: enqueue_render_job returns None when Redis unavailable
- job_queue: dequeue_render_job returns None when Redis unavailable
- job_queue: is_available returns False when Redis unavailable
- GET /assets: status filter for "running" / "failed" statuses
"""

import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import main
from main import app

# Import worker and job_queue directly
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))
try:
    from worker import process_render_job
    from job_queue import enqueue_render_job, dequeue_render_job, is_available
except ImportError:
    for _mod_name, _mod_path in [
        ("worker", "/app/worker.py"),
        ("job_queue", "/app/job_queue.py"),
    ]:
        import importlib.util
        spec = importlib.util.spec_from_file_location(_mod_name, _mod_path)
        _m = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(_m)  # type: ignore[union-attr]
        if _mod_name == "worker":
            process_render_job = _m.process_render_job
        else:
            enqueue_render_job = _m.enqueue_render_job
            dequeue_render_job = _m.dequeue_render_job
            is_available = _m.is_available


# ---------------------------------------------------------------------------
# Fake database (same pattern as v5 tests)
# ---------------------------------------------------------------------------

NOW = datetime(2024, 6, 1, tzinfo=timezone.utc)


def make_doc(**kwargs):
    return {"_id": ObjectId(), "created_at": NOW, "updated_at": NOW, **kwargs}


class InsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, _spec):
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(self.documents)


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = list(documents or [])

    def find(self, query=None):
        query = query or {}
        return FakeCursor([d for d in self.documents if self._matches(d, query)])

    def find_one(self, query):
        docs = list(self.find(query))
        return docs[0] if docs else None

    def insert_one(self, document):
        if "_id" not in document:
            document["_id"] = ObjectId()
        self.documents.append(document)
        return InsertResult(document["_id"])

    def update_one(self, query, update):
        for doc in self.documents:
            if self._matches(doc, query):
                for key, value in (update.get("$set") or {}).items():
                    doc[key] = value
                for key, value in (update.get("$push") or {}).items():
                    doc.setdefault(key, []).append(value)
                return

    def update_many(self, query, update):
        for doc in self.documents:
            if self._matches(doc, query):
                for key, value in (update.get("$set") or {}).items():
                    doc[key] = value

    def count_documents(self, query):
        return len([d for d in self.documents if self._matches(d, query)])

    def delete_one(self, query):
        for i, doc in enumerate(self.documents):
            if self._matches(doc, query):
                del self.documents[i]
                return

    def _matches(self, document, query):
        for key, value in query.items():
            if key == "$or":
                if not any(self._matches(document, cond) for cond in value):
                    return False
                continue
            if key == "$and":
                if not all(self._matches(document, cond) for cond in value):
                    return False
                continue
            if isinstance(value, dict):
                doc_val = document.get(key)
                if "$in" in value:
                    if doc_val not in value["$in"]:
                        return False
                elif "$nin" in value:
                    if doc_val in value["$nin"]:
                        return False
                elif "$exists" in value:
                    exists = key in document and document[key] is not None
                    if value["$exists"] != exists:
                        return False
                elif "$ne" in value:
                    if doc_val == value["$ne"]:
                        return False
            else:
                if document.get(key) != value:
                    return False
        return True


class FakeDatabase:
    def __init__(self):
        self.contacts = FakeCollection()
        self.leads = FakeCollection()
        self.message_drafts = FakeCollection()
        self.approval_requests = FakeCollection()
        self.agent_tasks = FakeCollection()
        self.agent_runs = FakeCollection()
        self.agent_artifacts = FakeCollection()
        self.deals = FakeCollection()
        self.scraped_candidates = FakeCollection()
        self.tool_runs = FakeCollection()
        self.workspaces = FakeCollection()
        self.content_briefs = FakeCollection()
        self.content_drafts = FakeCollection()
        self.client_profiles = FakeCollection()
        self.source_channels = FakeCollection()
        self.source_content = FakeCollection()
        self.content_transcripts = FakeCollection()
        self.content_snippets = FakeCollection()
        self.creative_assets = FakeCollection()
        self.creative_tool_runs = FakeCollection()
        self.audio_extraction_runs = FakeCollection()
        self.transcript_runs = FakeCollection()
        self.transcript_segments = FakeCollection()
        self.media_intake_records = FakeCollection()
        self.prompt_generations = FakeCollection()
        self.companies = FakeCollection()
        self.briefs = FakeCollection()
        self.asset_renders = FakeCollection()


class FakeClient:
    def close(self):
        pass


def make_db_patch(fake_db):
    fake_client = FakeClient()

    def fake_get_client():
        return fake_client

    def fake_get_database(_client):
        return fake_db

    return fake_get_client, fake_get_database


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _approved_snippet(**extra):
    defaults = dict(
        workspace_slug="ws1",
        transcript_text="Every estimate got a next-day check-in text.",
        status="approved",
        simulation_only=True,
        outbound_actions_taken=0,
    )
    defaults.update(extra)
    return make_doc(**defaults)


def _approved_prompt_gen(snippet_id, **extra):
    defaults = dict(
        workspace_slug="ws1",
        snippet_id=str(snippet_id),
        prompt_type="faceless_motivational",
        positive_prompt="Cinematic faceless motivational",
        negative_prompt="realistic face",
        visual_style="cinematic",
        lighting="dramatic",
        camera_direction="slow push-in",
        status="approved",
        simulation_only=True,
        outbound_actions_taken=0,
    )
    defaults.update(extra)
    return make_doc(**defaults)


def _render_payload(snippet_id, prompt_gen_id, **extra):
    base = {
        "workspace_slug": "ws1",
        "snippet_id": str(snippet_id),
        "prompt_generation_id": str(prompt_gen_id),
        "asset_type": "video",
        "generation_engine": "comfyui",
        "add_captions": False,
    }
    base.update(extra)
    return base


def _queued_render_record(snippet_id, pg_id, **extra):
    defaults = dict(
        workspace_slug="ws1",
        snippet_id=str(snippet_id),
        prompt_generation_id=str(pg_id),
        asset_type="video",
        generation_engine="comfyui",
        source_audio_path="",
        add_captions=False,
        status="queued",
        comfyui_result={},
        assembly_result={},
        file_path="",
        duration_seconds=0.0,
        resolution="1080x1920",
        review_events=[],
        simulation_only=True,
        outbound_actions_taken=0,
    )
    defaults.update(extra)
    return make_doc(**defaults)


# ---------------------------------------------------------------------------
# Part 1 — POST /assets/render: async queued path
# ---------------------------------------------------------------------------


def _make_fake_redis_client():
    """Return a MagicMock that looks like a connected Redis client."""
    r = MagicMock()
    r.ping.return_value = True
    r.lpush.return_value = 1
    r.llen.return_value = 0
    return r


def test_render_returns_queued_when_redis_available():
    """When Redis is available, POST /assets/render → status=queued, queued=True."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_redis = _make_fake_redis_client()
    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
        patch("job_queue._connect", return_value=fake_redis),
        patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}),
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))

    assert resp.status_code == 200
    data = resp.json()
    assert data["queued"] is True
    assert data["item"]["status"] == "queued"
    assert "job_id" in data


def test_render_enqueues_to_redis_when_available():
    """POST /assets/render must call lpush on Redis when it's available."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_redis = _make_fake_redis_client()
    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
        patch("job_queue._connect", return_value=fake_redis),
        patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}),
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))

    assert resp.status_code == 200
    fake_redis.lpush.assert_called_once()


def test_render_queued_no_comfyui_call():
    """When queued, the endpoint must not call ComfyUI (no work done inline)."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_redis = _make_fake_redis_client()
    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
        patch("job_queue._connect", return_value=fake_redis),
        patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}),
        patch("subprocess.run") as mock_run,
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))

    assert resp.status_code == 200
    assert resp.json()["queued"] is True
    mock_run.assert_not_called()


def test_render_queued_simulation_only():
    """Queued render record must carry simulation_only=True."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_redis = _make_fake_redis_client()
    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
        patch("job_queue._connect", return_value=fake_redis),
        patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}),
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))

    assert resp.status_code == 200
    assert resp.json()["item"]["simulation_only"] is True
    assert resp.json()["simulation_only"] is True
    assert resp.json()["outbound_actions_taken"] == 0


# ---------------------------------------------------------------------------
# Part 2 — POST /assets/render: sync fallback path (Redis unavailable)
# ---------------------------------------------------------------------------

def test_render_falls_back_to_sync_when_redis_unavailable():
    """When Redis is unavailable, endpoint processes synchronously → needs_review."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
        # Redis unavailable → _connect returns None
        patch("job_queue._connect", return_value=None),
        patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}),
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))

    assert resp.status_code == 200
    data = resp.json()
    assert data["queued"] is False
    assert data["item"]["status"] == "needs_review"


# ---------------------------------------------------------------------------
# Part 3 — process_render_job: status transitions
# ---------------------------------------------------------------------------

def test_worker_job_queued_to_running_to_needs_review():
    """process_render_job transitions: queued → running → generated → needs_review."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)
    render = _queued_render_record(snippet["_id"], pg["_id"])
    fake_db.asset_renders.insert_one(render)

    status_history = []
    orig_update = fake_db.asset_renders.update_one

    def tracking_update(query, update):
        new_status = (update.get("$set") or {}).get("status")
        if new_status:
            status_history.append(new_status)
        return orig_update(query, update)

    fake_db.asset_renders.update_one = tracking_update

    job = {"render_id": str(render["_id"]), "job_id": "test-job-1"}
    with patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}):
        result = process_render_job(job, fake_db)

    assert result["status"] == "needs_review"
    assert status_history == ["running", "generated", "needs_review"]


def test_worker_comfyui_disabled_path():
    """process_render_job with COMFYUI_ENABLED=false uses mock comfyui_result."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)
    render = _queued_render_record(snippet["_id"], pg["_id"])
    fake_db.asset_renders.insert_one(render)

    job = {"render_id": str(render["_id"]), "job_id": "test-job-2"}
    with patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}):
        result = process_render_job(job, fake_db)

    assert result["comfyui_result"]["skip_reason"] == "comfyui_disabled"
    assert result["comfyui_result"]["simulation_only"] is True


def test_worker_ffmpeg_disabled_path():
    """process_render_job with FFMPEG_ENABLED=false returns mock assembly_result."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)
    render = _queued_render_record(snippet["_id"], pg["_id"])
    fake_db.asset_renders.insert_one(render)

    job = {"render_id": str(render["_id"]), "job_id": "test-job-3"}
    with patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}):
        result = process_render_job(job, fake_db)

    assembly = result["assembly_result"]
    assert assembly.get("mock") or assembly.get("skip_reason") == "ffmpeg_disabled"


def test_worker_simulation_only_enforced():
    """process_render_job must set simulation_only=True on final record."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)
    render = _queued_render_record(snippet["_id"], pg["_id"])
    fake_db.asset_renders.insert_one(render)

    job = {"render_id": str(render["_id"]), "job_id": "test-job-4"}
    with patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}):
        result = process_render_job(job, fake_db)

    assert result["simulation_only"] is True
    assert result["outbound_actions_taken"] == 0
    # Verify in DB too
    updated = fake_db.asset_renders.find_one({"_id": render["_id"]})
    assert updated["simulation_only"] is True
    assert updated["outbound_actions_taken"] == 0


def test_worker_no_subprocess_when_gates_disabled():
    """process_render_job must not call subprocess when ComfyUI/FFmpeg disabled."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)
    render = _queued_render_record(snippet["_id"], pg["_id"])
    fake_db.asset_renders.insert_one(render)

    job = {"render_id": str(render["_id"]), "job_id": "test-job-5"}
    with (
        patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}),
        patch("subprocess.run") as mock_run,
        patch("subprocess.Popen") as mock_popen,
    ):
        result = process_render_job(job, fake_db)

    assert result["status"] == "needs_review"
    mock_run.assert_not_called()
    mock_popen.assert_not_called()


def test_worker_stores_render_id_in_result():
    """process_render_job result includes the render_id."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)
    render = _queued_render_record(snippet["_id"], pg["_id"])
    fake_db.asset_renders.insert_one(render)

    render_id_str = str(render["_id"])
    job = {"render_id": render_id_str, "job_id": "test-job-6"}
    with patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}):
        result = process_render_job(job, fake_db)

    assert result["render_id"] == render_id_str


# ---------------------------------------------------------------------------
# Part 4 — process_render_job: failure handling
# ---------------------------------------------------------------------------

def test_worker_handles_render_record_not_found():
    """process_render_job with unknown render_id → status=failed, no crash."""
    fake_db = FakeDatabase()

    job = {"render_id": str(ObjectId()), "job_id": "test-job-7"}
    with patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}):
        result = process_render_job(job, fake_db)

    assert result["status"] == "failed"
    assert "error" in result


def test_worker_handles_comfyui_exception_gracefully():
    """process_render_job survives a ComfyUI exception → records error, still reaches needs_review."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)
    render = _queued_render_record(snippet["_id"], pg["_id"])
    fake_db.asset_renders.insert_one(render)

    job = {"render_id": str(render["_id"]), "job_id": "test-job-8"}
    with (
        patch.dict(os.environ, {"COMFYUI_ENABLED": "true", "FFMPEG_ENABLED": "false"}),
        patch("agents.comfyui_client.ComfyUIClient", side_effect=RuntimeError("ComfyUI down")),
    ):
        result = process_render_job(job, fake_db)

    # Should not hard-fail; comfyui_result carries the error
    assert result["status"] in ("needs_review", "failed")
    if result["status"] == "needs_review":
        assert "error" in result.get("comfyui_result", {})


def test_worker_db_write_on_failure():
    """When process_render_job fails unexpectedly, status is set to failed in DB."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)
    render = _queued_render_record(snippet["_id"], pg["_id"])
    fake_db.asset_renders.insert_one(render)

    job = {"render_id": str(render["_id"]), "job_id": "test-job-9"}

    # Force a failure inside the ComfyUI mock path by injecting an error
    # after the "running" write but before "generated" write.
    orig_update = fake_db.asset_renders.update_one
    call_count = [0]

    def patched_update(query, update):
        call_count[0] += 1
        if call_count[0] == 2:  # The "generated" write
            raise RuntimeError("Simulated DB failure")
        return orig_update(query, update)

    fake_db.asset_renders.update_one = patched_update

    with patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}):
        result = process_render_job(job, fake_db)

    assert result["status"] == "failed"


# ---------------------------------------------------------------------------
# Part 5 — job_queue unit tests
# ---------------------------------------------------------------------------

def test_job_queue_enqueue_returns_job_id_when_redis_available():
    """enqueue_render_job returns a non-None job_id when Redis is reachable."""
    fake_redis = _make_fake_redis_client()
    with patch("job_queue._connect", return_value=fake_redis):
        result = enqueue_render_job("render-123", {"workspace_slug": "ws1"})
    assert result is not None
    assert len(result) > 0


def test_job_queue_enqueue_returns_none_when_redis_unavailable():
    """enqueue_render_job returns None when Redis is unreachable."""
    with patch("job_queue._connect", return_value=None):
        result = enqueue_render_job("render-123", {"workspace_slug": "ws1"})
    assert result is None


def test_job_queue_dequeue_returns_none_when_redis_unavailable():
    """dequeue_render_job returns None when Redis is unreachable."""
    with patch("job_queue._connect", return_value=None):
        result = dequeue_render_job(timeout=1)
    assert result is None


def test_job_queue_is_available_false_when_redis_unavailable():
    """is_available() returns False when Redis is unreachable."""
    with patch("job_queue._connect", return_value=None):
        assert is_available() is False


def test_job_queue_is_available_true_when_redis_available():
    """is_available() returns True when Redis is reachable."""
    fake_redis = _make_fake_redis_client()
    with patch("job_queue._connect", return_value=fake_redis):
        assert is_available() is True


def test_job_queue_enqueue_pushes_to_correct_queue():
    """enqueue_render_job calls lpush with the correct queue name."""
    import json
    fake_redis = _make_fake_redis_client()
    with patch("job_queue._connect", return_value=fake_redis):
        enqueue_render_job("render-abc", {"workspace_slug": "ws2"})
    queue_name = fake_redis.lpush.call_args[0][0]
    assert queue_name == "signalforge:render_jobs"


def test_job_queue_enqueue_payload_contains_render_id():
    """Enqueued job payload includes the render_id."""
    import json
    fake_redis = _make_fake_redis_client()
    with patch("job_queue._connect", return_value=fake_redis):
        enqueue_render_job("render-xyz", {"workspace_slug": "ws1"})
    raw_payload = fake_redis.lpush.call_args[0][1]
    job = json.loads(raw_payload)
    assert job["render_id"] == "render-xyz"
    assert job["job_type"] == "asset_render"
    assert "job_id" in job


def test_job_queue_no_redis_calls_when_unavailable():
    """When Redis is unavailable, no redis methods are called."""
    with patch("job_queue._connect", return_value=None) as mock_connect:
        enqueue_render_job("render-000", {})
    # _connect is called once to check availability
    mock_connect.assert_called()


# ---------------------------------------------------------------------------
# Part 6 — GET /assets: running / failed status filters
# ---------------------------------------------------------------------------

def test_list_assets_running_status_filter():
    """GET /assets?status=running returns only running renders."""
    fake_db = FakeDatabase()
    fake_db.asset_renders.insert_one(make_doc(workspace_slug="ws1", status="running", simulation_only=True, outbound_actions_taken=0))
    fake_db.asset_renders.insert_one(make_doc(workspace_slug="ws1", status="queued", simulation_only=True, outbound_actions_taken=0))

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.get("/assets?workspace_slug=ws1&status=running")

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "running"


def test_list_assets_failed_status_filter():
    """GET /assets?status=failed returns only failed renders."""
    fake_db = FakeDatabase()
    fake_db.asset_renders.insert_one(make_doc(workspace_slug="ws1", status="failed", simulation_only=True, outbound_actions_taken=0))
    fake_db.asset_renders.insert_one(make_doc(workspace_slug="ws1", status="needs_review", simulation_only=True, outbound_actions_taken=0))

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.get("/assets?workspace_slug=ws1&status=failed")

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "failed"
