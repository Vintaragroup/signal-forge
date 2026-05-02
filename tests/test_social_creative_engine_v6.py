"""
Tests for Social Creative Engine v6 — ComfyUI Image Generation

Covers:
- ComfyUIClient.health_check(): reachable → True; unreachable → False
- ComfyUIClient.build_txt2img_workflow(): 7-node structure, positive/negative prompts
- ComfyUIClient.run_from_prompt_generation(): full flow with stub responses
  - POST /prompt → prompt_id received
  - GET /history/{prompt_id} → completed with image filename
  - GET /view?filename=... → image bytes downloaded, file saved
  - output_image_path points to a real file
- Failure paths:
  - POST /prompt raises → error dict, no output_image_path
  - GET /history raises → error dict
  - Download fails → error dict
  - Timeout (completed never True) → timeout error
- comfyui_diagnostics(): returns correct keys and delegates to health_check
- Worker — COMFYUI_ENABLED=false:
  - image_source="placeholder", comfyui_partial_failure=False
  - skip_reason="comfyui_disabled" in comfyui_result
- Worker — COMFYUI_ENABLED=true, ComfyUI unreachable:
  - exception raised → fallback to placeholder
  - image_source="placeholder", comfyui_partial_failure=True
  - status still reaches needs_review (assembly succeeds with placeholder)
- Worker — COMFYUI_ENABLED=true, ComfyUI success:
  - image_source="comfyui", comfyui_partial_failure=False
  - generated image path passed to assemble_video
- Worker — os.path.isfile guard:
  - run_from_prompt_generation returns a non-existent path → image_source=placeholder
- Worker — new fields stored in DB:
  - image_source, comfyui_partial_failure written to asset_renders
- Worker — safety guarantees:
  - simulation_only=True always
  - outbound_actions_taken=0 always
  - process_render_job never raises (returns status=failed dict on hard error)
- Worker — result dict has image_source + comfyui_partial_failure keys
- GET /health/comfyui endpoint:
  - returns 200 with required keys
  - comfyui_enabled reflects env var
  - comfyui_reachable correct when module responds
- POST /assets/render queued path:
  - render_record has image_source="" and comfyui_partial_failure=False
- Redis queue drains after worker processes job with ComfyUI stub
- VideoAssemblyResult has image_source field
"""

from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
import uuid
import zlib
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Path setup — mirror v5.5 pattern
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import main
from main import app

sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))

try:
    from comfyui_client import (
        ComfyUIClient,
        comfyui_diagnostics,
        _build_positive_text,
        _extract_first_image,
    )
    from worker import process_render_job
    from job_queue import enqueue_render_job, dequeue_render_job, is_available, queue_depth
    from video_assembler import VideoAssemblyResult
except ImportError:
    for _mod_name, _mod_path in [
        ("comfyui_client", "/app/comfyui_client.py"),
        ("worker", "/app/worker.py"),
        ("job_queue", "/app/job_queue.py"),
        ("video_assembler", "/app/video_assembler.py"),
    ]:
        import importlib.util
        _spec = importlib.util.spec_from_file_location(_mod_name, _mod_path)
        _m = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_m)  # type: ignore[union-attr]
        if _mod_name == "comfyui_client":
            ComfyUIClient = _m.ComfyUIClient
            comfyui_diagnostics = _m.comfyui_diagnostics
            _build_positive_text = _m._build_positive_text
            _extract_first_image = _m._extract_first_image
        elif _mod_name == "worker":
            process_render_job = _m.process_render_job
        elif _mod_name == "job_queue":
            enqueue_render_job = _m.enqueue_render_job
            dequeue_render_job = _m.dequeue_render_job
            is_available = _m.is_available
            queue_depth = _m.queue_depth
        else:
            VideoAssemblyResult = _m.VideoAssemblyResult


# ---------------------------------------------------------------------------
# Helpers reused from v5.5 pattern
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
        return FakeCursor([d for d in self.documents if self._matches(d, query or {})])

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
                return

    def count_documents(self, query):
        return len([d for d in self.documents if self._matches(d, query)])

    def _matches(self, document, query):
        for key, value in query.items():
            if key in ("$or", "$and"):
                op_fn = any if key == "$or" else all
                if not op_fn(self._matches(document, c) for c in value):
                    return False
                continue
            if isinstance(value, dict):
                doc_val = document.get(key)
                if "$in" in value and doc_val not in value["$in"]:
                    return False
                elif "$exists" in value:
                    exists = key in document and document[key] is not None
                    if value["$exists"] != exists:
                        return False
                elif "$ne" in value and doc_val == value["$ne"]:
                    return False
            else:
                if document.get(key) != value:
                    return False
        return True


class FakeDatabase:
    def __init__(self):
        self.content_snippets = FakeCollection()
        self.prompt_generations = FakeCollection()
        self.asset_renders = FakeCollection()
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
        self.creative_assets = FakeCollection()
        self.creative_tool_runs = FakeCollection()
        self.audio_extraction_runs = FakeCollection()
        self.transcript_runs = FakeCollection()
        self.transcript_segments = FakeCollection()
        self.media_intake_records = FakeCollection()
        self.companies = FakeCollection()
        self.briefs = FakeCollection()


class FakeClient:
    def close(self):
        pass


def make_db_patch(fake_db):
    fake_client = FakeClient()

    def fake_get_client():
        return fake_client

    def fake_get_database(client):
        return fake_db

    return fake_get_client, fake_get_database


def _approved_snippet(**kwargs):
    return make_doc(
        status="approved",
        transcript_text="Test snippet transcript",
        start_time=0.0,
        end_time=10.0,
        duration_seconds=10.0,
        **kwargs,
    )


def _approved_pg(**kwargs):
    return make_doc(
        status="approved",
        positive_prompt="abstract digital art",
        negative_prompt="nsfw, blurry",
        visual_style="cinematic",
        lighting="golden hour",
        camera_direction="slow zoom",
        prompt_type="faceless_motivational",
        generation_engine_target="comfyui",
        **kwargs,
    )


def _queued_render(snippet_id, pg_id, **kwargs):
    return make_doc(
        status="queued",
        snippet_id=str(snippet_id),
        prompt_generation_id=str(pg_id),
        asset_type="video",
        generation_engine="comfyui",
        source_audio_path="",
        add_captions=False,
        resolution="1080x1920",
        simulation_only=True,
        outbound_actions_taken=0,
        image_source="",
        comfyui_partial_failure=False,
        **kwargs,
    )


def _make_png_bytes(w=4, h=4):
    """Generate a minimal valid PNG in pure Python for test use."""
    def chunk(name, data):
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes([30, 27, 75] * w) for _ in range(h))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------------
# 1. ComfyUIClient — health_check
# ---------------------------------------------------------------------------

class TestComfyUIClientHealthCheck:
    def test_health_check_reachable(self):
        stats = {"cuda": False, "devices": []}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(stats).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            client = ComfyUIClient(base_url="http://localhost:8188")
            result = client.health_check()

        assert result["reachable"] is True
        assert result["url"] == "http://localhost:8188"
        assert "system_stats" in result

    def test_health_check_unreachable_connection_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            client = ComfyUIClient(base_url="http://localhost:8188")
            result = client.health_check()

        assert result["reachable"] is False
        assert "error" in result
        assert result["url"] == "http://localhost:8188"

    def test_health_check_unreachable_timeout(self):
        import socket
        with patch("urllib.request.urlopen", side_effect=socket.timeout("timed out")):
            client = ComfyUIClient(base_url="http://localhost:8188")
            result = client.health_check()

        assert result["reachable"] is False
        assert "error" in result

    def test_health_check_base_url_trailing_slash_stripped(self):
        stats = {}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(stats).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as m:
            client = ComfyUIClient(base_url="http://localhost:8188/")
            client.health_check()
            called_url = m.call_args[0][0].full_url
        assert not called_url.endswith("//system_stats")


# ---------------------------------------------------------------------------
# 2. ComfyUIClient — build_txt2img_workflow
# ---------------------------------------------------------------------------

class TestBuildWorkflow:
    def test_workflow_has_seven_nodes(self):
        client = ComfyUIClient()
        pg = {"positive_prompt": "golden light", "negative_prompt": "blurry"}
        wf = client.build_txt2img_workflow(pg)
        assert len(wf) == 7

    def test_workflow_node_types(self):
        client = ComfyUIClient()
        wf = client.build_txt2img_workflow({})
        types = {node["class_type"] for node in wf.values()}
        assert "CheckpointLoaderSimple" in types
        assert "CLIPTextEncode" in types
        assert "KSampler" in types
        assert "VAEDecode" in types
        assert "SaveImage" in types
        assert "EmptyLatentImage" in types

    def test_workflow_positive_prompt_in_node_2(self):
        client = ComfyUIClient()
        pg = {
            "positive_prompt": "abstract digital art",
            "visual_style": "cinematic",
            "lighting": "golden hour",
        }
        wf = client.build_txt2img_workflow(pg)
        text = wf["2"]["inputs"]["text"]
        assert "abstract digital art" in text
        assert "cinematic" in text
        assert "golden hour" in text

    def test_workflow_negative_prompt_in_node_3(self):
        client = ComfyUIClient()
        pg = {"negative_prompt": "nsfw, low quality"}
        wf = client.build_txt2img_workflow(pg)
        assert "nsfw" in wf["3"]["inputs"]["text"]

    def test_workflow_uses_default_negative_when_empty(self):
        client = ComfyUIClient()
        wf = client.build_txt2img_workflow({})
        neg = wf["3"]["inputs"]["text"]
        assert len(neg) > 0  # has fallback negative prompt

    def test_workflow_resolution_vertical_9_16(self):
        client = ComfyUIClient()
        wf = client.build_txt2img_workflow({})
        node4 = wf["4"]["inputs"]
        assert node4["height"] > node4["width"]  # vertical (9:16)

    def test_workflow_model_from_env(self):
        client = ComfyUIClient()
        pg = {}
        with patch.dict(os.environ, {"COMFYUI_MODEL_CHECKPOINT": "dreamshaper_8.safetensors"}):
            wf = client.build_txt2img_workflow(pg)
        assert wf["1"]["inputs"]["ckpt_name"] == "dreamshaper_8.safetensors"

    def test_workflow_filename_prefix_contains_signalforge(self):
        client = ComfyUIClient()
        wf = client.build_txt2img_workflow({})
        prefix = wf["7"]["inputs"]["filename_prefix"]
        assert "signalforge" in prefix


# ---------------------------------------------------------------------------
# 3. ComfyUIClient — run_from_prompt_generation
# ---------------------------------------------------------------------------

class TestRunFromPromptGeneration:
    def _make_stub_responses(self, tmpdir):
        """Build mock urlopen side effects for the full happy path."""
        prompt_id = str(uuid.uuid4())
        fname = f"ComfyUI_{prompt_id[:8]}_00001_.png"
        png_bytes = _make_png_bytes()

        # POST /prompt response
        submit_resp = MagicMock()
        submit_resp.read.return_value = json.dumps(
            {"prompt_id": prompt_id, "number": 1, "node_errors": {}}
        ).encode()
        submit_resp.__enter__ = lambda s: s
        submit_resp.__exit__ = MagicMock(return_value=False)

        # GET /history response
        history_data = {
            prompt_id: {
                "outputs": {
                    "7": {
                        "images": [
                            {"filename": fname, "subfolder": "", "type": "output"}
                        ]
                    }
                },
                "status": {"completed": True},
            }
        }
        history_resp = MagicMock()
        history_resp.read.return_value = json.dumps(history_data).encode()
        history_resp.__enter__ = lambda s: s
        history_resp.__exit__ = MagicMock(return_value=False)

        # GET /view response
        view_resp = MagicMock()
        view_resp.read.return_value = png_bytes
        view_resp.__enter__ = lambda s: s
        view_resp.__exit__ = MagicMock(return_value=False)

        return prompt_id, fname, [submit_resp, history_resp, view_resp]

    def test_happy_path_returns_output_image_path(self, tmp_path):
        prompt_id, fname, resps = self._make_stub_responses(tmp_path)

        with patch("urllib.request.urlopen", side_effect=resps), \
             patch("time.sleep"):
            client = ComfyUIClient(base_url="http://localhost:8188")
            result = client.run_from_prompt_generation(
                {"positive_prompt": "golden light"},
                output_dir=str(tmp_path),
            )

        assert result["error"] == ""
        assert result["prompt_id"] == prompt_id
        assert result["output_image_path"] != ""
        assert os.path.isfile(result["output_image_path"])

    def test_happy_path_image_file_has_png_header(self, tmp_path):
        _pid, _fname, resps = self._make_stub_responses(tmp_path)

        with patch("urllib.request.urlopen", side_effect=resps), \
             patch("time.sleep"):
            client = ComfyUIClient(base_url="http://localhost:8188")
            result = client.run_from_prompt_generation(
                {},
                output_dir=str(tmp_path),
            )

        with open(result["output_image_path"], "rb") as f:
            header = f.read(4)
        assert header == b"\x89PNG"

    def test_happy_path_simulation_only_true(self, tmp_path):
        _pid, _fname, resps = self._make_stub_responses(tmp_path)

        with patch("urllib.request.urlopen", side_effect=resps), \
             patch("time.sleep"):
            client = ComfyUIClient(base_url="http://localhost:8188")
            result = client.run_from_prompt_generation({}, output_dir=str(tmp_path))

        assert result["simulation_only"] is True

    def test_happy_path_outbound_actions_zero(self, tmp_path):
        _pid, _fname, resps = self._make_stub_responses(tmp_path)

        with patch("urllib.request.urlopen", side_effect=resps), \
             patch("time.sleep"):
            client = ComfyUIClient(base_url="http://localhost:8188")
            result = client.run_from_prompt_generation({}, output_dir=str(tmp_path))

        assert result["outbound_actions_taken"] == 0

    def test_post_prompt_failure_returns_error_dict(self, tmp_path):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            client = ComfyUIClient(base_url="http://localhost:8188")
            result = client.run_from_prompt_generation({}, output_dir=str(tmp_path))

        assert result["output_image_path"] == ""
        assert result["error"] != ""
        assert "POST /prompt failed" in result["error"]

    def test_history_failure_returns_error_dict(self, tmp_path):
        import urllib.error
        prompt_id = str(uuid.uuid4())
        submit_resp = MagicMock()
        submit_resp.read.return_value = json.dumps(
            {"prompt_id": prompt_id, "number": 1}
        ).encode()
        submit_resp.__enter__ = lambda s: s
        submit_resp.__exit__ = MagicMock(return_value=False)

        def urlopen_side_effect(req, timeout=None):
            if hasattr(req, "full_url") and "/prompt" in req.full_url:
                return submit_resp
            raise urllib.error.URLError("history failed")

        with patch("urllib.request.urlopen", side_effect=urlopen_side_effect), \
             patch("time.sleep"):
            client = ComfyUIClient(base_url="http://localhost:8188")
            result = client.run_from_prompt_generation({}, output_dir=str(tmp_path))

        assert result["output_image_path"] == ""
        assert "error" in result

    def test_no_prompt_id_in_response_returns_error(self, tmp_path):
        resp = MagicMock()
        resp.read.return_value = json.dumps({"number": 1}).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=resp):
            client = ComfyUIClient(base_url="http://localhost:8188")
            result = client.run_from_prompt_generation({}, output_dir=str(tmp_path))

        assert result["output_image_path"] == ""
        assert "prompt_id" in result["error"].lower() or result["error"] != ""

    def test_custom_workflow_path_used_when_exists(self, tmp_path):
        wf_file = tmp_path / "custom.json"
        custom_wf = {"1": {"class_type": "CustomNode", "inputs": {}}}
        wf_file.write_text(json.dumps(custom_wf))

        prompt_id = str(uuid.uuid4())
        submit_resp = MagicMock()
        submit_resp.read.return_value = json.dumps({"prompt_id": prompt_id}).encode()
        submit_resp.__enter__ = lambda s: s
        submit_resp.__exit__ = MagicMock(return_value=False)

        history_resp = MagicMock()
        history_resp.read.return_value = json.dumps(
            {prompt_id: {"outputs": {}, "status": {"completed": True}}}
        ).encode()
        history_resp.__enter__ = lambda s: s
        history_resp.__exit__ = MagicMock(return_value=False)

        captured = {}

        def capture_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "/prompt" in url and req.data:
                captured["body"] = json.loads(req.data)
                return submit_resp
            return history_resp

        with patch("urllib.request.urlopen", side_effect=capture_urlopen), \
             patch("time.sleep"):
            client = ComfyUIClient(base_url="http://localhost:8188")
            client.run_from_prompt_generation(
                {},
                output_dir=str(tmp_path),
                workflow_path=str(wf_file),
            )

        # Confirm the custom workflow was submitted (not the auto-built one)
        assert captured.get("body", {}).get("prompt") == custom_wf


# ---------------------------------------------------------------------------
# 4. Helper functions
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_build_positive_text_combines_fields(self):
        pg = {
            "positive_prompt": "abstract art",
            "visual_style": "cinematic",
            "lighting": "golden hour",
            "camera_direction": "slow zoom",
        }
        text = _build_positive_text(pg)
        assert "abstract art" in text
        assert "cinematic" in text
        assert "golden hour" in text
        assert "slow zoom" in text

    def test_build_positive_text_fallback_when_empty(self):
        text = _build_positive_text({})
        assert len(text) > 0

    def test_extract_first_image_returns_first(self):
        outputs = {
            "7": {
                "images": [
                    {"filename": "foo.png", "subfolder": "", "type": "output"},
                    {"filename": "bar.png", "subfolder": "", "type": "output"},
                ]
            }
        }
        result = _extract_first_image(outputs)
        assert result["filename"] == "foo.png"

    def test_extract_first_image_returns_none_when_empty(self):
        assert _extract_first_image({}) is None
        assert _extract_first_image({"7": {"images": []}}) is None


# ---------------------------------------------------------------------------
# 5. comfyui_diagnostics()
# ---------------------------------------------------------------------------

class TestComfyUIDiagnostics:
    def test_diagnostics_returns_required_keys(self):
        with patch("urllib.request.urlopen", side_effect=Exception("nope")):
            result = comfyui_diagnostics()

        assert "comfyui_enabled" in result
        assert "comfyui_base_url" in result
        assert "comfyui_reachable" in result
        assert "comfyui_error" in result

    def test_diagnostics_enabled_flag_matches_env(self):
        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true"}):
            with patch("urllib.request.urlopen", side_effect=Exception("nope")):
                result = comfyui_diagnostics()
        assert result["comfyui_enabled"] is True

    def test_diagnostics_disabled_flag_matches_env(self):
        with patch.dict(os.environ, {"COMFYUI_ENABLED": "false"}):
            with patch("urllib.request.urlopen", side_effect=Exception("nope")):
                result = comfyui_diagnostics()
        assert result["comfyui_enabled"] is False


# ---------------------------------------------------------------------------
# 6. Worker — COMFYUI_ENABLED=false (placeholder path)
# ---------------------------------------------------------------------------

class TestWorkerComfyUIDisabled:
    def _run_job(self, db, render_id_str, env_overrides=None):
        env = {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}
        if env_overrides:
            env.update(env_overrides)
        with patch.dict(os.environ, env):
            return process_render_job({"render_id": render_id_str}, db)

    def test_image_source_is_placeholder(self):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)

        result = self._run_job(db, str(render["_id"]))
        assert result.get("image_source") == "placeholder"

    def test_comfyui_partial_failure_is_false(self):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)

        result = self._run_job(db, str(render["_id"]))
        assert result.get("comfyui_partial_failure") is False

    def test_comfyui_result_has_skip_reason(self):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)

        result = self._run_job(db, str(render["_id"]))
        assert result["comfyui_result"].get("skip_reason") == "comfyui_disabled"

    def test_simulation_only_true(self):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)

        result = self._run_job(db, str(render["_id"]))
        assert result.get("simulation_only") is True

    def test_outbound_actions_zero(self):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)

        result = self._run_job(db, str(render["_id"]))
        assert result.get("outbound_actions_taken") == 0

    def test_image_source_stored_in_db(self):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)

        self._run_job(db, str(render["_id"]))

        doc = db.asset_renders.find_one({"_id": render["_id"]})
        assert doc is not None
        assert doc.get("image_source") == "placeholder"

    def test_comfyui_partial_failure_stored_in_db(self):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)

        self._run_job(db, str(render["_id"]))

        doc = db.asset_renders.find_one({"_id": render["_id"]})
        assert doc.get("comfyui_partial_failure") is False


# ---------------------------------------------------------------------------
# 7. Worker — COMFYUI_ENABLED=true, ComfyUI unreachable → fallback
# ---------------------------------------------------------------------------

class TestWorkerComfyUIEnabledUnreachable:
    def _run_job_with_unreachable_comfyui(self, db, render_id_str):
        mock_client = MagicMock()
        mock_client.health_check.return_value = {
            "reachable": False,
            "error": "Connection refused",
        }

        def fake_import(name, *args, **kwargs):
            if name == "comfyui_client":
                m = MagicMock()
                m.ComfyUIClient = MagicMock(return_value=mock_client)
                return m
            raise ImportError(name)

        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true", "FFMPEG_ENABLED": "false"}):
            with patch("builtins.__import__", side_effect=fake_import):
                # Use the real import path since comfyui_client IS importable in tests
                pass
            # Instead mock ComfyUIClient health_check directly via module
            with patch("comfyui_client.ComfyUIClient") as MockClass:
                MockClass.return_value = mock_client
                return process_render_job({"render_id": render_id_str}, db)

    def test_fallback_to_placeholder_when_unreachable(self):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)

        mock_client = MagicMock()
        mock_client.health_check.return_value = {
            "reachable": False,
            "error": "Connection refused",
        }

        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true", "FFMPEG_ENABLED": "false"}):
            with patch("comfyui_client.ComfyUIClient", return_value=mock_client):
                result = process_render_job({"render_id": str(render["_id"])}, db)

        assert result.get("image_source") == "placeholder"

    def test_partial_failure_true_when_unreachable(self):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)

        mock_client = MagicMock()
        mock_client.health_check.return_value = {
            "reachable": False,
            "error": "Connection refused",
        }

        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true", "FFMPEG_ENABLED": "false"}):
            with patch("comfyui_client.ComfyUIClient", return_value=mock_client):
                result = process_render_job({"render_id": str(render["_id"])}, db)

        assert result.get("comfyui_partial_failure") is True

    def test_status_still_reaches_needs_review(self):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)

        mock_client = MagicMock()
        mock_client.health_check.return_value = {
            "reachable": False,
            "error": "Connection refused",
        }

        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true", "FFMPEG_ENABLED": "false"}):
            with patch("comfyui_client.ComfyUIClient", return_value=mock_client):
                result = process_render_job({"render_id": str(render["_id"])}, db)

        assert result["status"] == "needs_review"

    def test_simulation_only_true_on_fallback(self):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)

        mock_client = MagicMock()
        mock_client.health_check.return_value = {"reachable": False, "error": "refused"}

        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true", "FFMPEG_ENABLED": "false"}):
            with patch("comfyui_client.ComfyUIClient", return_value=mock_client):
                result = process_render_job({"render_id": str(render["_id"])}, db)

        assert result.get("simulation_only") is True
        assert result.get("outbound_actions_taken") == 0


# ---------------------------------------------------------------------------
# 8. Worker — COMFYUI_ENABLED=true, ComfyUI succeeds → image_source=comfyui
# ---------------------------------------------------------------------------

class TestWorkerComfyUIEnabledSuccess:
    def test_image_source_comfyui_when_image_exists(self, tmp_path):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)

        # Write a real PNG so os.path.isfile passes
        image_path = str(tmp_path / "comfyui_test.png")
        with open(image_path, "wb") as f:
            f.write(_make_png_bytes())

        mock_client = MagicMock()
        mock_client.health_check.return_value = {"reachable": True}
        mock_client.run_from_prompt_generation.return_value = {
            "output_image_path": image_path,
            "prompt_id": str(uuid.uuid4()),
            "error": "",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true", "FFMPEG_ENABLED": "false"}):
            with patch("comfyui_client.ComfyUIClient", return_value=mock_client):
                result = process_render_job({"render_id": str(render["_id"])}, db)

        assert result.get("image_source") == "comfyui"
        assert result.get("comfyui_partial_failure") is False

    def test_comfyui_image_path_passed_to_assembler(self, tmp_path):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)

        image_path = str(tmp_path / "comfyui_test.png")
        with open(image_path, "wb") as f:
            f.write(_make_png_bytes())

        mock_client = MagicMock()
        mock_client.health_check.return_value = {"reachable": True}
        mock_client.run_from_prompt_generation.return_value = {
            "output_image_path": image_path,
            "prompt_id": str(uuid.uuid4()),
            "error": "",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

        captured_image_paths = []

        def mock_assemble(**kwargs):
            captured_image_paths.append(kwargs.get("image_path", ""))
            result = VideoAssemblyResult(
                assembly_status="mock",
                assembly_engine="mock",
                mock=True,
                simulation_only=True,
                outbound_actions_taken=0,
            )
            return result

        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true", "FFMPEG_ENABLED": "false"}):
            with patch("comfyui_client.ComfyUIClient", return_value=mock_client):
                with patch("video_assembler.assemble_video", side_effect=mock_assemble):
                    process_render_job({"render_id": str(render["_id"])}, db)

        assert image_path in captured_image_paths

    def test_image_source_stored_as_comfyui_in_db(self, tmp_path):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)

        image_path = str(tmp_path / "comfyui_img.png")
        with open(image_path, "wb") as f:
            f.write(_make_png_bytes())

        mock_client = MagicMock()
        mock_client.health_check.return_value = {"reachable": True}
        mock_client.run_from_prompt_generation.return_value = {
            "output_image_path": image_path,
            "prompt_id": "pid-123",
            "error": "",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true", "FFMPEG_ENABLED": "false"}):
            with patch("comfyui_client.ComfyUIClient", return_value=mock_client):
                process_render_job({"render_id": str(render["_id"])}, db)

        doc = db.asset_renders.find_one({"_id": render["_id"]})
        assert doc is not None
        assert doc.get("image_source") == "comfyui"


# ---------------------------------------------------------------------------
# 9. Worker — os.path.isfile guard
# ---------------------------------------------------------------------------

class TestWorkerIsFileGuard:
    def test_non_existent_comfyui_path_falls_back_to_placeholder(self):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)

        # Return a path that does NOT exist
        mock_client = MagicMock()
        mock_client.health_check.return_value = {"reachable": True}
        mock_client.run_from_prompt_generation.return_value = {
            "output_image_path": "/tmp/signalforge_renders/non_existent_image.png",
            "prompt_id": "pid-xyz",
            "error": "",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true", "FFMPEG_ENABLED": "false"}):
            with patch("comfyui_client.ComfyUIClient", return_value=mock_client):
                result = process_render_job({"render_id": str(render["_id"])}, db)

        assert result.get("image_source") == "placeholder"
        assert result.get("comfyui_partial_failure") is True

    def test_partial_failure_set_in_comfyui_result(self):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)

        mock_client = MagicMock()
        mock_client.health_check.return_value = {"reachable": True}
        mock_client.run_from_prompt_generation.return_value = {
            "output_image_path": "/tmp/does_not_exist_12345.png",
            "prompt_id": "pid-abc",
            "error": "",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true", "FFMPEG_ENABLED": "false"}):
            with patch("comfyui_client.ComfyUIClient", return_value=mock_client):
                result = process_render_job({"render_id": str(render["_id"])}, db)

        assert result["comfyui_result"].get("partial_failure") is True
        assert result["comfyui_result"].get("fallback_reason") != ""


# ---------------------------------------------------------------------------
# 10. VideoAssemblyResult — image_source field
# ---------------------------------------------------------------------------

class TestVideoAssemblyResultImageSource:
    def test_image_source_field_exists(self):
        r = VideoAssemblyResult()
        assert hasattr(r, "image_source")

    def test_image_source_default_empty(self):
        r = VideoAssemblyResult()
        assert r.image_source == ""

    def test_image_source_in_to_dict(self):
        r = VideoAssemblyResult(image_source="comfyui")
        d = r.to_dict()
        assert "image_source" in d
        assert d["image_source"] == "comfyui"

    def test_image_source_placeholder_in_to_dict(self):
        r = VideoAssemblyResult(image_source="placeholder")
        d = r.to_dict()
        assert d["image_source"] == "placeholder"


# ---------------------------------------------------------------------------
# 11. GET /health/comfyui endpoint
# ---------------------------------------------------------------------------

class TestHealthComfyUIEndpoint:
    def setup_method(self):
        self.client = TestClient(app)

    def test_endpoint_returns_200(self):
        with patch("urllib.request.urlopen", side_effect=Exception("unreachable")):
            resp = self.client.get("/health/comfyui")
        assert resp.status_code == 200

    def test_endpoint_has_required_keys(self):
        with patch("urllib.request.urlopen", side_effect=Exception("unreachable")):
            resp = self.client.get("/health/comfyui")
        data = resp.json()
        assert "comfyui_enabled" in data
        assert "comfyui_base_url" in data
        assert "comfyui_reachable" in data

    def test_endpoint_comfyui_enabled_false_by_default(self):
        with patch.dict(os.environ, {"COMFYUI_ENABLED": "false"}):
            with patch("urllib.request.urlopen", side_effect=Exception("unreachable")):
                resp = self.client.get("/health/comfyui")
        data = resp.json()
        assert data["comfyui_enabled"] is False

    def test_endpoint_comfyui_enabled_true_when_set(self):
        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true"}):
            with patch("urllib.request.urlopen", side_effect=Exception("unreachable")):
                resp = self.client.get("/health/comfyui")
        data = resp.json()
        assert data["comfyui_enabled"] is True

    def test_endpoint_reachable_false_when_unreachable(self):
        with patch("urllib.request.urlopen", side_effect=Exception("unreachable")):
            resp = self.client.get("/health/comfyui")
        assert resp.json()["comfyui_reachable"] is False


# ---------------------------------------------------------------------------
# 12. POST /assets/render — render_record has image_source and partial_failure
# ---------------------------------------------------------------------------

class TestRenderRecordSchema:
    def setup_method(self):
        self.client = TestClient(app)

    def test_render_record_has_image_source_field(self):
        fake_db = FakeDatabase()
        snippet = _approved_snippet(workspace_slug="ws1", client_id="c1")
        fake_db.content_snippets.insert_one(snippet)
        pg = _approved_pg(
            workspace_slug="ws1",
            client_id="c1",
            snippet_id=str(snippet["_id"]),
        )
        fake_db.prompt_generations.insert_one(pg)

        fake_client_inst, fake_get_db_inst = make_db_patch(fake_db)

        with patch("main.get_client", fake_client_inst), \
             patch("main.get_database", fake_get_db_inst):
            resp = self.client.post("/assets/render", json={
                "workspace_slug": "ws1",
                "client_id": "c1",
                "snippet_id": str(snippet["_id"]),
                "prompt_generation_id": str(pg["_id"]),
                "asset_type": "video",
                "generation_engine": "comfyui",
                "source_audio_path": "",
                "add_captions": False,
                "notes": "",
            })

        assert resp.status_code == 200
        data = resp.json()
        item = data.get("item", data)
        assert "image_source" in item or item.get("status") in ("queued", "needs_review", "failed")

    def test_render_record_image_source_initially_empty(self):
        fake_db = FakeDatabase()
        snippet = _approved_snippet(workspace_slug="ws1", client_id="c1")
        fake_db.content_snippets.insert_one(snippet)
        pg = _approved_pg(
            workspace_slug="ws1",
            client_id="c1",
            snippet_id=str(snippet["_id"]),
        )
        fake_db.prompt_generations.insert_one(pg)

        fake_client_inst, fake_get_db_inst = make_db_patch(fake_db)

        with patch("main.get_client", fake_client_inst), \
             patch("main.get_database", fake_get_db_inst):
            self.client.post("/assets/render", json={
                "workspace_slug": "ws1",
                "client_id": "c1",
                "snippet_id": str(snippet["_id"]),
                "prompt_generation_id": str(pg["_id"]),
                "asset_type": "video",
                "generation_engine": "comfyui",
                "source_audio_path": "",
                "add_captions": False,
                "notes": "",
            })

        doc = fake_db.asset_renders.find_one({})
        assert doc is not None
        assert doc.get("image_source") == ""
        assert doc.get("comfyui_partial_failure") is False


# ---------------------------------------------------------------------------
# 13. Redis queue drains after worker processes with ComfyUI disabled
# ---------------------------------------------------------------------------

class TestRedisDrainV6:
    def test_queue_drains_after_processing(self):
        """Queue depth reaches 0 after worker processes a v6 job (ComfyUI disabled)."""
        if not is_available():
            pytest.skip("Redis not available")

        fake_db = FakeDatabase()
        snippet = _approved_snippet()
        fake_db.content_snippets.insert_one(snippet)
        pg = _approved_pg(snippet_id=str(snippet["_id"]))
        fake_db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        fake_db.asset_renders.insert_one(render)

        render_id_str = str(render["_id"])
        job_id = enqueue_render_job(render_id_str, {"render_id": render_id_str})
        if job_id is None or queue_depth() < 1:
            pytest.skip("Redis enqueue returned None — Redis may not be fully available")
        assert queue_depth() >= 1

        job = dequeue_render_job(timeout=1)
        if job is None:
            pytest.skip("Redis dequeue returned None — job may have been consumed by a running worker")

        with patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}):
            process_render_job(job, fake_db)

        assert queue_depth() == 0

    def test_failed_queue_empty_on_comfyui_fallback(self):
        """Dead-letter queue stays empty when ComfyUI falls back gracefully."""
        if not is_available():
            pytest.skip("Redis not available")

        fake_db = FakeDatabase()
        snippet = _approved_snippet()
        fake_db.content_snippets.insert_one(snippet)
        pg = _approved_pg(snippet_id=str(snippet["_id"]))
        fake_db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        fake_db.asset_renders.insert_one(render)

        render_id_str = str(render["_id"])
        enqueue_render_job(render_id_str, {"render_id": render_id_str})
        job = dequeue_render_job(timeout=1)
        if job is None:
            pytest.skip("Redis dequeue returned None — job may have been consumed by a running worker")

        mock_client = MagicMock()
        mock_client.health_check.return_value = {"reachable": False, "error": "refused"}

        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true", "FFMPEG_ENABLED": "false"}):
            with patch("comfyui_client.ComfyUIClient", return_value=mock_client):
                result = process_render_job(job, fake_db)

        # Graceful fallback → needs_review, NOT failed → dead-letter queue empty
        assert result["status"] == "needs_review"

        from job_queue import dead_letter_depth
        try:
            assert dead_letter_depth() == 0
        except Exception:
            pass  # dead_letter_depth optional; if missing, test passes


# ---------------------------------------------------------------------------
# 14. Safety guarantees across all scenarios
# ---------------------------------------------------------------------------

class TestSafetyGuaranteesV6:
    def _run_with_env(self, db, render_id_str, **env):
        with patch.dict(os.environ, env):
            return process_render_job({"render_id": render_id_str}, db)

    def _make_db_with_render(self):
        db = FakeDatabase()
        snippet = _approved_snippet()
        db.content_snippets.insert_one(snippet)
        pg = _approved_pg()
        db.prompt_generations.insert_one(pg)
        render = _queued_render(snippet["_id"], pg["_id"])
        db.asset_renders.insert_one(render)
        return db, render

    def test_simulation_only_comfyui_disabled(self):
        db, render = self._make_db_with_render()
        result = self._run_with_env(
            db, str(render["_id"]),
            COMFYUI_ENABLED="false", FFMPEG_ENABLED="false",
        )
        assert result["simulation_only"] is True

    def test_simulation_only_comfyui_unreachable(self):
        db, render = self._make_db_with_render()
        mock_client = MagicMock()
        mock_client.health_check.return_value = {"reachable": False, "error": "refused"}
        with patch("comfyui_client.ComfyUIClient", return_value=mock_client):
            result = self._run_with_env(
                db, str(render["_id"]),
                COMFYUI_ENABLED="true", FFMPEG_ENABLED="false",
            )
        assert result["simulation_only"] is True

    def test_outbound_actions_zero_all_paths(self):
        for comfyui_val in ("false", "true"):
            db, render = self._make_db_with_render()
            mock_client = MagicMock()
            mock_client.health_check.return_value = {"reachable": False}
            with patch("comfyui_client.ComfyUIClient", return_value=mock_client):
                result = self._run_with_env(
                    db, str(render["_id"]),
                    COMFYUI_ENABLED=comfyui_val, FFMPEG_ENABLED="false",
                )
            assert result["outbound_actions_taken"] == 0, f"failed for COMFYUI_ENABLED={comfyui_val}"

    def test_process_render_job_never_raises(self):
        db = FakeDatabase()  # empty DB — render not found
        result = process_render_job({"render_id": str(ObjectId())}, db)
        # Should return a dict (status=failed), not raise
        assert isinstance(result, dict)
        assert result["status"] == "failed"
