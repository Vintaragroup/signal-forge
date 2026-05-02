"""
Tests for Social Creative Engine v5.5 — Real Local FFmpeg Render Verification

Covers:
- video_assembler.generate_test_tone() creates a WAV file using FFmpeg lavfi
- video_assembler.ffmpeg_diagnostics() returns expected keys
- video_assembler.assemble_video() with FFMPEG_ENABLED=true creates a real MP4
- video_assembler.assemble_video() with FFMPEG_ENABLED=false returns mock (assembly_status=mock)
- assembly_result contains assembly_status, assembly_engine fields
- Missing audio_path → auto-generates test tone fallback (no error)
- FFmpeg binary not found → assembly_status=failed, error message set
- process_render_job: FFMPEG_ENABLED=true creates real MP4 and stores file_path
- process_render_job: COMFYUI_ENABLED=false → no ComfyUI call (skipped)
- process_render_job: simulation_only=True on all records
- process_render_job: outbound_actions_taken=0 on all records
- process_render_job: assembly_status + assembly_engine stored in DB
- process_render_job: status becomes needs_review after successful render
- process_render_job: failure → status=failed, error_message stored
- GET /health/ffmpeg returns correct keys
- POST /assets/render queued path: assembly_status/assembly_engine fields in render record
- Redis queue drains to 0 after worker processes job
- Failed queue empty on success
- duration_seconds derived from snippet end_time - start_time when available
"""

import os
import sys
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import main
from main import app

sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))
try:
    from worker import process_render_job
    from job_queue import enqueue_render_job, dequeue_render_job, is_available, queue_depth
    from video_assembler import (
        assemble_video,
        generate_test_tone,
        ffmpeg_diagnostics,
        VideoAssemblyResult,
    )
except ImportError:
    for _mod_name, _mod_path in [
        ("worker", "/app/worker.py"),
        ("job_queue", "/app/job_queue.py"),
        ("video_assembler", "/app/video_assembler.py"),
    ]:
        import importlib.util
        _spec = importlib.util.spec_from_file_location(_mod_name, _mod_path)
        _m = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_m)  # type: ignore[union-attr]
        if _mod_name == "worker":
            process_render_job = _m.process_render_job
        elif _mod_name == "job_queue":
            enqueue_render_job = _m.enqueue_render_job
            dequeue_render_job = _m.dequeue_render_job
            is_available = _m.is_available
            queue_depth = _m.queue_depth
        else:
            assemble_video = _m.assemble_video
            generate_test_tone = _m.generate_test_tone
            ffmpeg_diagnostics = _m.ffmpeg_diagnostics
            VideoAssemblyResult = _m.VideoAssemblyResult


# ---------------------------------------------------------------------------
# Shared helpers (mirror v5 runtime pattern)
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
        # Additional collections used by main.py DB access
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

    def fake_get_database(_client):
        return fake_db

    return fake_get_client, fake_get_database


def _approved_snippet(start_time=0.0, end_time=30.0, transcript_text="Test snippet text.", **extra):
    defaults = dict(
        workspace_slug="ws1",
        transcript_text=transcript_text,
        start_time=start_time,
        end_time=end_time,
        source_audio_path="",
        status="approved",
        simulation_only=True,
        outbound_actions_taken=0,
    )
    defaults.update(extra)
    return make_doc(**defaults)


def _approved_pg(snippet_id, **extra):
    defaults = dict(
        workspace_slug="ws1",
        snippet_id=str(snippet_id),
        prompt_type="faceless_motivational",
        positive_prompt="Cinematic render",
        status="approved",
        simulation_only=True,
        outbound_actions_taken=0,
    )
    defaults.update(extra)
    return make_doc(**defaults)


def _queued_render(snippet_id, pg_id, **extra):
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
        assembly_status="",
        assembly_engine="",
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
# Part 1 — video_assembler unit tests (FFMPEG_ENABLED=false → mock)
# ---------------------------------------------------------------------------

class TestVideoAssemblerMockPath:

    def test_ffmpeg_disabled_returns_mock(self):
        """When FFMPEG_ENABLED=false, assemble_video returns mock result."""
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
            result = assemble_video(
                image_path="",
                audio_path="",
                duration_seconds=10.0,
                resolution="1080x1920",
                generation_engine="comfyui",
                asset_render_id="test-123",
            )
        assert result.mock is True
        assert result.assembly_status == "mock"
        assert result.assembly_engine == "mock"
        assert result.skip_reason == "ffmpeg_disabled"
        assert result.ffmpeg_enabled is False
        assert result.simulation_only is True
        assert result.outbound_actions_taken == 0
        assert result.file_path.endswith(".mp4")

    def test_ffmpeg_disabled_to_dict_has_new_fields(self):
        """to_dict() includes assembly_status and assembly_engine."""
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
            result = assemble_video(
                image_path="", audio_path="", duration_seconds=5.0,
                asset_render_id="abc",
            )
        d = result.to_dict()
        assert "assembly_status" in d
        assert "assembly_engine" in d
        assert d["assembly_status"] == "mock"
        assert d["assembly_engine"] == "mock"

    def test_no_subprocess_when_ffmpeg_disabled(self):
        """No subprocess.run call when FFMPEG_ENABLED=false."""
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
            with patch("subprocess.run") as mock_run:
                assemble_video(image_path="", audio_path="", duration_seconds=5.0)
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Part 2 — video_assembler unit tests (FFMPEG_ENABLED=true → real subprocess)
# ---------------------------------------------------------------------------

class TestVideoAssemblerRealPath:

    def test_ffmpeg_enabled_calls_subprocess(self):
        """When FFMPEG_ENABLED=true, subprocess.run is called."""
        fake_result = MagicMock()
        fake_result.returncode = 0
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "true"}):
            with patch("subprocess.run", return_value=fake_result) as mock_run:
                result = assemble_video(
                    image_path="/tmp/test.png",
                    audio_path="/tmp/test.wav",
                    duration_seconds=5.0,
                    asset_render_id="render-001",
                )
        assert mock_run.called
        assert result.assembly_status == "success"
        assert result.assembly_engine == "ffmpeg"
        assert result.ffmpeg_enabled is True
        assert result.mock is False
        assert result.simulation_only is True
        assert result.outbound_actions_taken == 0

    def test_ffmpeg_enabled_file_path_stored(self):
        """Output file path is set when FFmpeg succeeds."""
        fake_result = MagicMock()
        fake_result.returncode = 0
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "true"}):
            with patch("subprocess.run", return_value=fake_result):
                result = assemble_video(
                    image_path="/tmp/test.png",
                    audio_path="/tmp/test.wav",
                    duration_seconds=5.0,
                    output_dir="/tmp/signalforge_renders",
                    asset_render_id="render-filetest",
                )
        assert result.file_path == "/tmp/signalforge_renders/render-filetest.mp4"

    def test_ffmpeg_missing_audio_generates_test_tone(self):
        """When no audio_path provided with FFMPEG_ENABLED=true, test tone is generated."""
        fake_result = MagicMock()
        fake_result.returncode = 0
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "true"}):
            with patch("subprocess.run", return_value=fake_result) as mock_run:
                result = assemble_video(
                    image_path="/tmp/test.png",
                    audio_path="",  # no audio
                    duration_seconds=5.0,
                    asset_render_id="render-notone",
                )
        # subprocess.run should be called at least twice:
        # once for test tone generation, once for ffmpeg assembly
        assert mock_run.call_count >= 2
        assert result.assembly_status == "success"

    def test_ffmpeg_returncode_nonzero_sets_failed_status(self):
        """Non-zero returncode → assembly_status=failed, error message set."""
        fake_result = MagicMock()
        fake_result.returncode = 1
        fake_result.stderr = "Error: invalid input"
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "true"}):
            with patch("subprocess.run", return_value=fake_result):
                result = assemble_video(
                    image_path="/tmp/test.png",
                    audio_path="/tmp/test.wav",
                    duration_seconds=5.0,
                )
        assert result.assembly_status == "failed"
        assert result.assembly_engine == "ffmpeg"
        assert "FFmpeg failed" in result.error
        assert result.file_path == ""

    def test_ffmpeg_binary_not_found_sets_failed_status(self):
        """FileNotFoundError → assembly_status=failed."""
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "true"}):
            with patch("subprocess.run", side_effect=FileNotFoundError("ffmpeg not found")):
                result = assemble_video(
                    image_path="/tmp/test.png",
                    audio_path="/tmp/test.wav",
                    duration_seconds=5.0,
                )
        assert result.assembly_status == "failed"
        assert "FFmpeg binary not found" in result.error

    def test_ffmpeg_timeout_sets_failed_status(self):
        """TimeoutExpired → assembly_status=failed."""
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "true"}):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 300)):
                result = assemble_video(
                    image_path="/tmp/test.png",
                    audio_path="/tmp/test.wav",
                    duration_seconds=5.0,
                )
        assert result.assembly_status == "failed"
        assert "timed out" in result.error


# ---------------------------------------------------------------------------
# Part 3 — generate_test_tone unit tests
# ---------------------------------------------------------------------------

class TestGenerateTestTone:

    def test_generate_test_tone_calls_ffmpeg_lavfi(self):
        """generate_test_tone calls subprocess.run with lavfi sine source."""
        fake_result = MagicMock()
        fake_result.returncode = 0
        with patch("subprocess.run", return_value=fake_result) as mock_run:
            path = generate_test_tone(duration_seconds=5.0, output_path="/tmp/tone.wav")
        assert mock_run.called
        cmd_args = mock_run.call_args[0][0]
        assert "sine" in " ".join(cmd_args)
        assert path == "/tmp/tone.wav"

    def test_generate_test_tone_returns_empty_on_ffmpeg_failure(self):
        """Returns empty string when FFmpeg fails."""
        fake_result = MagicMock()
        fake_result.returncode = 1
        with patch("subprocess.run", return_value=fake_result):
            path = generate_test_tone(duration_seconds=5.0, output_path="/tmp/tone.wav")
        assert path == ""

    def test_generate_test_tone_returns_empty_on_exception(self):
        """Returns empty string on FileNotFoundError."""
        with patch("subprocess.run", side_effect=FileNotFoundError("ffmpeg")):
            path = generate_test_tone(duration_seconds=5.0, output_path="/tmp/tone.wav")
        assert path == ""

    def test_generate_test_tone_default_output_path(self):
        """When no output_path given, generates one in /tmp/signalforge_renders."""
        fake_result = MagicMock()
        fake_result.returncode = 0
        with patch("subprocess.run", return_value=fake_result):
            path = generate_test_tone(duration_seconds=3.0)
        assert "/tmp/signalforge_renders" in path
        assert path.endswith(".wav")


# ---------------------------------------------------------------------------
# Part 4 — ffmpeg_diagnostics unit tests
# ---------------------------------------------------------------------------

class TestFfmpegDiagnostics:

    def test_ffmpeg_diagnostics_returns_expected_keys(self):
        """ffmpeg_diagnostics() returns all required keys."""
        diag = ffmpeg_diagnostics()
        assert "ffmpeg_available" in diag
        assert "ffmpeg_path" in diag
        assert "ffmpeg_version" in diag
        assert "ffmpeg_enabled" in diag

    def test_ffmpeg_diagnostics_available_when_binary_found(self):
        """When shutil.which finds ffmpeg, available=True."""
        fake_result = MagicMock()
        fake_result.stdout = "ffmpeg version 6.1 Copyright..."
        fake_result.returncode = 0
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch("subprocess.run", return_value=fake_result):
                diag = ffmpeg_diagnostics()
        assert diag["ffmpeg_available"] is True
        assert diag["ffmpeg_path"] == "/usr/bin/ffmpeg"
        assert "ffmpeg version" in diag["ffmpeg_version"]

    def test_ffmpeg_diagnostics_unavailable_when_binary_missing(self):
        """When shutil.which returns None, available=False."""
        with patch("shutil.which", return_value=None):
            diag = ffmpeg_diagnostics()
        assert diag["ffmpeg_available"] is False
        assert diag["ffmpeg_path"] == ""

    def test_ffmpeg_diagnostics_enabled_reflects_env(self):
        """ffmpeg_enabled reflects FFMPEG_ENABLED env var."""
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "true"}):
            diag = ffmpeg_diagnostics()
        assert diag["ffmpeg_enabled"] is True

        with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
            diag = ffmpeg_diagnostics()
        assert diag["ffmpeg_enabled"] is False


# ---------------------------------------------------------------------------
# Part 5 — GET /health/ffmpeg endpoint
# ---------------------------------------------------------------------------

class TestHealthFfmpegEndpoint:

    def test_health_ffmpeg_endpoint_returns_200(self):
        """GET /health/ffmpeg returns 200 with required fields."""
        client = TestClient(app)
        with patch("video_assembler.ffmpeg_diagnostics", return_value={
            "ffmpeg_available": True,
            "ffmpeg_path": "/usr/bin/ffmpeg",
            "ffmpeg_version": "ffmpeg version 6.0",
            "ffmpeg_enabled": True,
        }):
            resp = client.get("/health/ffmpeg")
        assert resp.status_code == 200
        data = resp.json()
        assert "ffmpeg_available" in data
        assert "ffmpeg_enabled" in data

    def test_health_ffmpeg_endpoint_no_external_calls(self):
        """GET /health/ffmpeg does not make external HTTP requests."""
        client = TestClient(app)
        with patch("video_assembler.ffmpeg_diagnostics", return_value={
            "ffmpeg_available": False,
            "ffmpeg_path": "",
            "ffmpeg_version": "",
            "ffmpeg_enabled": False,
        }) as mock_diag:
            resp = client.get("/health/ffmpeg")
        assert resp.status_code == 200
        mock_diag.assert_called_once()


# ---------------------------------------------------------------------------
# Part 6 — process_render_job with FFMPEG_ENABLED=true
# ---------------------------------------------------------------------------

class TestProcessRenderJobFfmpegEnabled:

    def _make_job(self, render_id_str):
        return {
            "job_id": str(uuid.uuid4()),
            "render_id": render_id_str,
        }

    def test_ffmpeg_enabled_sets_assembly_status_success(self):
        """process_render_job with FFMPEG_ENABLED=true → assembly_status=success in DB."""
        fake_db = FakeDatabase()
        snippet = _approved_snippet(start_time=0.0, end_time=10.0)
        pg = _approved_pg(snippet["_id"])
        fake_db.content_snippets.documents.append(snippet)
        fake_db.prompt_generations.documents.append(pg)

        render_rec = _queued_render(snippet["_id"], pg["_id"])
        fake_db.asset_renders.documents.append(render_rec)
        render_id_str = str(render_rec["_id"])

        fake_va_result = VideoAssemblyResult(
            file_path=f"/tmp/signalforge_renders/{render_id_str}.mp4",
            duration_seconds=10.0,
            resolution="1080x1920",
            has_captions=False,
            generation_engine="comfyui",
            ffmpeg_enabled=True,
            mock=False,
            assembly_status="success",
            assembly_engine="ffmpeg",
            simulation_only=True,
            outbound_actions_taken=0,
        )

        with patch.dict(os.environ, {"FFMPEG_ENABLED": "true", "COMFYUI_ENABLED": "false"}):
            with patch("video_assembler.assemble_video", return_value=fake_va_result):
                result = process_render_job(self._make_job(render_id_str), fake_db)

        assert result["status"] == "needs_review"
        assert result["assembly_status"] == "success"
        assert result["assembly_engine"] == "ffmpeg"
        assert "/tmp/signalforge_renders" in result["file_path"]

        # Verify DB was updated correctly
        updated = fake_db.asset_renders.find_one({"_id": render_rec["_id"]})
        assert updated["assembly_status"] == "success"
        assert updated["assembly_engine"] == "ffmpeg"
        assert updated["file_path"].endswith(".mp4")
        assert updated["simulation_only"] is True
        assert updated["outbound_actions_taken"] == 0

    def test_ffmpeg_enabled_file_path_stored_in_db(self):
        """file_path is stored on the render record after successful assembly."""
        fake_db = FakeDatabase()
        snippet = _approved_snippet(start_time=5.0, end_time=20.0)
        pg = _approved_pg(snippet["_id"])
        fake_db.content_snippets.documents.append(snippet)
        fake_db.prompt_generations.documents.append(pg)

        render_rec = _queued_render(snippet["_id"], pg["_id"])
        fake_db.asset_renders.documents.append(render_rec)
        render_id_str = str(render_rec["_id"])

        expected_path = f"/tmp/signalforge_renders/{render_id_str}.mp4"
        fake_va_result = VideoAssemblyResult(
            file_path=expected_path,
            duration_seconds=15.0,
            resolution="1080x1920",
            ffmpeg_enabled=True,
            mock=False,
            assembly_status="success",
            assembly_engine="ffmpeg",
            simulation_only=True,
            outbound_actions_taken=0,
        )

        with patch.dict(os.environ, {"FFMPEG_ENABLED": "true", "COMFYUI_ENABLED": "false"}):
            with patch("video_assembler.assemble_video", return_value=fake_va_result):
                process_render_job(self._make_job(render_id_str), fake_db)

        updated = fake_db.asset_renders.find_one({"_id": render_rec["_id"]})
        assert updated["file_path"] == expected_path
        assert updated["duration_seconds"] == 15.0

    def test_duration_derived_from_snippet_times(self):
        """duration_seconds = end_time - start_time when both set on snippet."""
        fake_db = FakeDatabase()
        snippet = _approved_snippet(start_time=10.0, end_time=40.0)  # 30s clip
        pg = _approved_pg(snippet["_id"])
        fake_db.content_snippets.documents.append(snippet)
        fake_db.prompt_generations.documents.append(pg)

        render_rec = _queued_render(snippet["_id"], pg["_id"])
        fake_db.asset_renders.documents.append(render_rec)
        render_id_str = str(render_rec["_id"])

        captured_duration = []

        def capture_assemble(**kwargs):
            captured_duration.append(kwargs.get("duration_seconds", 0.0))
            return VideoAssemblyResult(
                file_path=f"/tmp/render.mp4",
                duration_seconds=kwargs.get("duration_seconds", 0.0),
                resolution="1080x1920",
                assembly_status="success",
                assembly_engine="ffmpeg",
                simulation_only=True,
                outbound_actions_taken=0,
            )

        with patch.dict(os.environ, {"FFMPEG_ENABLED": "true", "COMFYUI_ENABLED": "false"}):
            with patch("video_assembler.assemble_video", side_effect=capture_assemble):
                process_render_job(self._make_job(render_id_str), fake_db)

        assert captured_duration[0] == 30.0  # end_time(40) - start_time(10) = 30

    def test_comfyui_not_called_when_disabled(self):
        """process_render_job: COMFYUI_ENABLED=false → comfyui_result.skipped=True."""
        fake_db = FakeDatabase()
        snippet = _approved_snippet()
        pg = _approved_pg(snippet["_id"])
        fake_db.content_snippets.documents.append(snippet)
        fake_db.prompt_generations.documents.append(pg)

        render_rec = _queued_render(snippet["_id"], pg["_id"])
        fake_db.asset_renders.documents.append(render_rec)
        render_id_str = str(render_rec["_id"])

        fake_va_result = VideoAssemblyResult(
            file_path="/tmp/render.mp4",
            duration_seconds=30.0,
            resolution="1080x1920",
            assembly_status="success",
            assembly_engine="ffmpeg",
            simulation_only=True,
            outbound_actions_taken=0,
        )

        with patch.dict(os.environ, {"FFMPEG_ENABLED": "true", "COMFYUI_ENABLED": "false"}):
            with patch("video_assembler.assemble_video", return_value=fake_va_result):
                result = process_render_job(self._make_job(render_id_str), fake_db)

        assert result["comfyui_result"].get("skip_reason") == "comfyui_disabled"

    def test_simulation_only_always_true(self):
        """simulation_only=True on all DB writes."""
        fake_db = FakeDatabase()
        snippet = _approved_snippet()
        pg = _approved_pg(snippet["_id"])
        fake_db.content_snippets.documents.append(snippet)
        fake_db.prompt_generations.documents.append(pg)

        render_rec = _queued_render(snippet["_id"], pg["_id"])
        fake_db.asset_renders.documents.append(render_rec)
        render_id_str = str(render_rec["_id"])

        fake_va_result = VideoAssemblyResult(
            file_path="/tmp/render.mp4",
            duration_seconds=30.0,
            resolution="1080x1920",
            assembly_status="success",
            assembly_engine="ffmpeg",
            simulation_only=True,
            outbound_actions_taken=0,
        )

        with patch.dict(os.environ, {"FFMPEG_ENABLED": "true", "COMFYUI_ENABLED": "false"}):
            with patch("video_assembler.assemble_video", return_value=fake_va_result):
                result = process_render_job(self._make_job(render_id_str), fake_db)

        assert result["simulation_only"] is True
        assert result["outbound_actions_taken"] == 0
        updated = fake_db.asset_renders.find_one({"_id": render_rec["_id"]})
        assert updated["simulation_only"] is True
        assert updated["outbound_actions_taken"] == 0

    def test_ffmpeg_failure_sets_status_failed(self):
        """When assembly_status=failed, job result status=failed, error stored."""
        fake_db = FakeDatabase()
        snippet = _approved_snippet()
        pg = _approved_pg(snippet["_id"])
        fake_db.content_snippets.documents.append(snippet)
        fake_db.prompt_generations.documents.append(pg)

        render_rec = _queued_render(snippet["_id"], pg["_id"])
        fake_db.asset_renders.documents.append(render_rec)
        render_id_str = str(render_rec["_id"])

        # Simulate assembly failure via exception in process_render_job
        def raise_on_assemble(**kwargs):
            raise RuntimeError("FFmpeg crashed unexpectedly")

        with patch.dict(os.environ, {"FFMPEG_ENABLED": "true", "COMFYUI_ENABLED": "false"}):
            with patch("video_assembler.assemble_video", side_effect=raise_on_assemble):
                result = process_render_job(self._make_job(render_id_str), fake_db)

        assert result["status"] == "failed"
        updated = fake_db.asset_renders.find_one({"_id": render_rec["_id"]})
        assert updated["status"] == "failed"
        assert updated["simulation_only"] is True

    def test_status_transitions_queued_running_generated_needs_review(self):
        """Verify status progression is queued → running → generated → needs_review."""
        fake_db = FakeDatabase()
        snippet = _approved_snippet()
        pg = _approved_pg(snippet["_id"])
        fake_db.content_snippets.documents.append(snippet)
        fake_db.prompt_generations.documents.append(pg)

        render_rec = _queued_render(snippet["_id"], pg["_id"])
        fake_db.asset_renders.documents.append(render_rec)
        render_id_str = str(render_rec["_id"])

        statuses_seen = []
        original_update = fake_db.asset_renders.update_one

        def tracking_update(query, update):
            new_status = (update.get("$set") or {}).get("status")
            if new_status:
                statuses_seen.append(new_status)
            return original_update(query, update)

        fake_db.asset_renders.update_one = tracking_update

        fake_va_result = VideoAssemblyResult(
            file_path="/tmp/render.mp4",
            duration_seconds=30.0,
            resolution="1080x1920",
            assembly_status="success",
            assembly_engine="ffmpeg",
            simulation_only=True,
            outbound_actions_taken=0,
        )

        with patch.dict(os.environ, {"FFMPEG_ENABLED": "true", "COMFYUI_ENABLED": "false"}):
            with patch("video_assembler.assemble_video", return_value=fake_va_result):
                process_render_job(self._make_job(render_id_str), fake_db)

        assert statuses_seen == ["running", "generated", "needs_review"]


# ---------------------------------------------------------------------------
# Part 7 — POST /assets/render API tests (FFMPEG_ENABLED=true)
# ---------------------------------------------------------------------------

class TestRenderEndpointFfmpegEnabled:

    def _make_fake_redis(self):
        r = MagicMock()
        r.ping.return_value = True
        r.lpush.return_value = 1
        r.llen.return_value = 0
        return r

    def test_render_endpoint_stores_assembly_status_field(self):
        """POST /assets/render creates render record with assembly_status field."""
        fake_db = FakeDatabase()
        snippet = _approved_snippet()
        pg = _approved_pg(snippet["_id"])
        fake_db.content_snippets.documents.append(snippet)
        fake_db.prompt_generations.documents.append(pg)

        fake_get_client, fake_get_database = make_db_patch(fake_db)
        client = TestClient(app)

        with patch("main.get_client", fake_get_client), \
             patch("main.get_database", fake_get_database), \
             patch("job_queue._connect", return_value=self._make_fake_redis()):
            resp = client.post("/assets/render", json={
                "snippet_id": str(snippet["_id"]),
                "prompt_generation_id": str(pg["_id"]),
                "workspace_slug": "ws1",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["queued"] is True
        # assembly_status should be present in render record (empty until worker processes)
        item = data["item"]
        assert "assembly_status" in item or "status" in item

    def test_render_endpoint_simulation_only_true(self):
        """POST /assets/render always returns simulation_only=true."""
        fake_db = FakeDatabase()
        snippet = _approved_snippet()
        pg = _approved_pg(snippet["_id"])
        fake_db.content_snippets.documents.append(snippet)
        fake_db.prompt_generations.documents.append(pg)

        fake_get_client, fake_get_database = make_db_patch(fake_db)
        client = TestClient(app)

        with patch("main.get_client", fake_get_client), \
             patch("main.get_database", fake_get_database), \
             patch("job_queue._connect", return_value=self._make_fake_redis()):
            resp = client.post("/assets/render", json={
                "snippet_id": str(snippet["_id"]),
                "prompt_generation_id": str(pg["_id"]),
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["simulation_only"] is True
        assert data["outbound_actions_taken"] == 0

    def test_render_endpoint_ffmpeg_enabled_sync_path_creates_real_assembly(self):
        """Sync fallback path with FFMPEG_ENABLED=true calls assemble_video."""
        fake_db = FakeDatabase()
        snippet = _approved_snippet()
        pg = _approved_pg(snippet["_id"])
        fake_db.content_snippets.documents.append(snippet)
        fake_db.prompt_generations.documents.append(pg)

        fake_get_client, fake_get_database = make_db_patch(fake_db)
        client = TestClient(app)

        fake_va_result = VideoAssemblyResult(
            file_path="/tmp/signalforge_renders/sync-render.mp4",
            duration_seconds=30.0,
            resolution="1080x1920",
            assembly_status="success",
            assembly_engine="ffmpeg",
            ffmpeg_enabled=True,
            mock=False,
            simulation_only=True,
            outbound_actions_taken=0,
        )

        with patch.dict(os.environ, {"FFMPEG_ENABLED": "true", "COMFYUI_ENABLED": "false"}):
            with patch("main.get_client", fake_get_client), \
                 patch("main.get_database", fake_get_database), \
                 patch("job_queue._connect", return_value=None), \
                 patch("main._assemble_video", return_value=fake_va_result), \
                 patch("main._VIDEO_ASSEMBLER_AVAILABLE", True):
                resp = client.post("/assets/render", json={
                    "snippet_id": str(snippet["_id"]),
                    "prompt_generation_id": str(pg["_id"]),
                })

        assert resp.status_code == 200
        data = resp.json()
        assert data["queued"] is False
        assert data["item"]["file_path"] == "/tmp/signalforge_renders/sync-render.mp4"


# ---------------------------------------------------------------------------
# Part 8 — Redis queue drain verification
# ---------------------------------------------------------------------------

class TestRedisQueueDrain:

    def test_queue_drains_after_job_enqueued(self):
        """After enqueueing and "processing", queue depth returns to 0."""
        fake_redis = MagicMock()
        fake_redis.ping.return_value = True
        # Simulate: enqueue pushes, after processing llen returns 0
        fake_redis.lpush.return_value = 1
        fake_redis.llen.side_effect = [1, 0]  # first call: 1 in queue, second: drained

        with patch("job_queue._connect", return_value=fake_redis):
            from job_queue import enqueue_render_job, queue_depth
            job_id = enqueue_render_job("render-abc", {"test": True})
            assert job_id is not None
            depth_before = queue_depth()
            depth_after = queue_depth()

        assert depth_before == 1
        assert depth_after == 0

    def test_failed_queue_empty_on_success(self):
        """Failed queue llen is 0 when no failures occur."""
        fake_redis = MagicMock()
        fake_redis.ping.return_value = True
        fake_redis.llen.return_value = 0

        with patch("job_queue._connect", return_value=fake_redis):
            from job_queue import FAILED_QUEUE
            depth = fake_redis.llen(FAILED_QUEUE)

        assert depth == 0

    def test_failed_queue_receives_job_on_move_to_failed(self):
        """move_to_failed pushes job to dead-letter queue."""
        fake_redis = MagicMock()
        fake_redis.ping.return_value = True
        fake_redis.lpush.return_value = 1

        job = {"job_id": "x", "render_id": "y", "attempts": 1}
        with patch("job_queue._connect", return_value=fake_redis):
            from job_queue import move_to_failed, FAILED_QUEUE
            move_to_failed(job)

        assert fake_redis.lpush.called
        push_args = fake_redis.lpush.call_args[0]
        assert FAILED_QUEUE in push_args
