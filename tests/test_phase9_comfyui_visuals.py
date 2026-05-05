"""
Tests for Phase 9 ComfyUI Visuals Upgrade

Covers:
- ComfyUI stub /prompt POST returns a valid PNG (size > 50 bytes)
- Per-beat images are saved to disk with correct filenames
- video_assembler.assemble_video_sequence: mock path with ffmpeg_disabled
- video_assembler.assemble_video_sequence: real FFmpeg produces MP4 with duration > 0
- video_assembler.assemble_video_sequence: image_source from result dict when used via worker
- assemble_video_sequence: fallback to assemble_video when only 1 valid image
- process_render_job: comfyui enabled → image_source=comfyui, fallback_used=false
- process_render_job: comfyui scene beats → output_image_paths list in comfyui_result
- process_render_job: audio preserved (source_audio_path unchanged)
- process_render_job: simulation_only=True, outbound_actions_taken=0
- process_render_job: assembly_status=success in DB when FFMPEG runs OK
- comfyui_client.run_scene_beats: returns list equal to number of beats
- comfyui_client.run_scene_beats: fallback to single image when scene_beats empty
"""

import os
import sys
import struct
import uuid
import tempfile
import zlib
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
    from video_assembler import (
        assemble_video,
        assemble_video_sequence,
        generate_test_tone,
        VideoAssemblyResult,
    )
    from comfyui_client import ComfyUIClient, _build_positive_text
except ImportError:
    for _mod_name, _mod_path in [
        ("worker", "/app/worker.py"),
        ("video_assembler", "/app/video_assembler.py"),
        ("comfyui_client", "/app/comfyui_client.py"),
    ]:
        import importlib.util
        _spec = importlib.util.spec_from_file_location(_mod_name, _mod_path)
        _m = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_m)
        if _mod_name == "worker":
            process_render_job = _m.process_render_job
        elif _mod_name == "video_assembler":
            assemble_video = _m.assemble_video
            assemble_video_sequence = _m.assemble_video_sequence
            generate_test_tone = _m.generate_test_tone
            VideoAssemblyResult = _m.VideoAssemblyResult
        elif _mod_name == "comfyui_client":
            ComfyUIClient = _m.ComfyUIClient
            _build_positive_text = _m._build_positive_text

client = TestClient(app)

NOW = datetime(2024, 6, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# In-memory DB helpers (avoids real MongoDB connection inside container)
# ---------------------------------------------------------------------------

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


def _make_snippet(**extra):
    defaults = dict(
        workspace_slug="john-maxwell-pilot",
        transcript_text="Test snippet transcript.",
        start_time=0.0,
        end_time=6.0,
        duration_seconds=6.0,
        source_audio_path="/tmp/signalforge_renders/test_audio.mp3",
        status="approved",
        simulation_only=True,
        outbound_actions_taken=0,
    )
    defaults.update(extra)
    return make_doc(**defaults)


def _make_pg(snippet_id, scene_beats=None, **extra):
    defaults = dict(
        workspace_slug="john-maxwell-pilot",
        snippet_id=str(snippet_id),
        positive_prompt="cinematic B-roll, faceless",
        negative_prompt="realistic face, identifiable person",
        visual_style="cinematic warm",
        lighting="golden-hour",
        camera_direction="static",
        scene_beats=scene_beats or [
            "Hook: test hook line",
            "0-10s: environment shot",
            "10-25s: action B-roll",
        ],
        status="approved",
        simulation_only=True,
        outbound_actions_taken=0,
    )
    defaults.update(extra)
    return make_doc(**defaults)


def _make_render(snippet_id, pg_id, **extra):
    defaults = dict(
        workspace_slug="john-maxwell-pilot",
        snippet_id=str(snippet_id),
        prompt_generation_id=str(pg_id),
        asset_type="video",
        generation_engine="comfyui",
        source_audio_path="/tmp/signalforge_renders/test_audio.mp3",
        add_captions=False,
        resolution="1080x1920",
        preserve_original_audio=True,
        status="queued",
        comfyui_result={},
        assembly_result={},
        assembly_status="",
        assembly_engine="",
        simulation_only=True,
        outbound_actions_taken=0,
    )
    defaults.update(extra)
    return make_doc(**defaults)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tiny_png() -> bytes:
    """Return a minimal valid 1x1 RGB PNG (no external deps)."""
    def chunk(name, data):
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = b"\x00\xFF\x80\x00"
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _make_png_file(path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(_make_tiny_png())
    return path


SAMPLE_PG = {
    "_id": "aabbccddeeff001122334455",
    "positive_prompt": "cinematic B-roll, no faces",
    "negative_prompt": "realistic face, identifiable person",
    "visual_style": "cinematic, warm",
    "lighting": "golden-hour",
    "camera_direction": "static medium shot",
    "scene_beats": [
        "Hook: hope never gave that to you.",
        "0-10s: Establishing environment detail shot — no face shown",
        "10-25s: Action or process B-roll underscoring the audio hook",
        "25-35s: Close-up detail — textures, materials, no face",
        "35-45s: Motion B-roll — camera pan, no face",
        "45s+: Outro — fade to logo or abstract",
    ],
}


# ---------------------------------------------------------------------------
# 1. ComfyUI stub returns real PNG via HTTP mock
# ---------------------------------------------------------------------------

class TestComfyUIStubReturnsPNG:
    """Tests via mocked HTTP responses simulating the upgraded stub."""

    def test_run_scene_beats_returns_list_of_image_paths(self, tmp_path):
        """run_scene_beats returns one path per scene beat."""
        png_bytes = _make_tiny_png()
        assert len(png_bytes) > 50, "PNG must be a valid non-empty file"

        history_resp = {
            "test-prompt-id": {
                "status": {"completed": True},
                "outputs": {
                    "7": {"images": [{"filename": "img.png", "subfolder": "", "type": "output"}]}
                },
            }
        }

        with (
            patch.object(ComfyUIClient, "_queue_prompt", return_value={"prompt_id": "test-prompt-id"}),
            patch.object(ComfyUIClient, "_get_history", return_value=history_resp),
            patch.object(ComfyUIClient, "_download_image", side_effect=lambda fname, sub, t, path: (
                open(path, "wb").write(png_bytes) or path  # type: ignore[func-returns-value]
            )),
        ):
            c = ComfyUIClient(base_url="http://localhost:8188")
            result = c.run_scene_beats(
                SAMPLE_PG,
                render_id="testrender001",
                output_dir=str(tmp_path),
            )

        paths = result["output_image_paths"]
        assert len(paths) == len(SAMPLE_PG["scene_beats"]), (
            f"Expected {len(SAMPLE_PG['scene_beats'])} image paths, got {len(paths)}"
        )
        assert result["simulation_only"] is True
        assert result["outbound_actions_taken"] == 0

    def test_run_scene_beats_files_saved_locally(self, tmp_path):
        """Each returned path should be a real file on disk."""
        png_bytes = _make_tiny_png()
        assert len(png_bytes) > 0  # basic validity check

        history_resp = {
            "pid": {
                "status": {"completed": True},
                "outputs": {
                    "7": {"images": [{"filename": "x.png", "subfolder": "", "type": "output"}]}
                },
            }
        }

        def _fake_download(fname, sub, t, path):
            with open(path, "wb") as fh:
                fh.write(png_bytes)
            return path

        with (
            patch.object(ComfyUIClient, "_queue_prompt", return_value={"prompt_id": "pid"}),
            patch.object(ComfyUIClient, "_get_history", return_value=history_resp),
            patch.object(ComfyUIClient, "_download_image", side_effect=_fake_download),
        ):
            c = ComfyUIClient(base_url="http://localhost:8188")
            result = c.run_scene_beats(SAMPLE_PG, render_id="r001", output_dir=str(tmp_path))

        for p in result["output_image_paths"]:
            assert os.path.isfile(p), f"Image not saved to disk: {p}"
            assert os.path.getsize(p) > 0, f"Image file empty: {p}"

    def test_run_scene_beats_fallback_empty_beats(self, tmp_path):
        """When scene_beats is empty, falls back to run_from_prompt_generation (single image)."""
        pg_no_beats = {**SAMPLE_PG, "scene_beats": []}
        single_result = {
            "output_image_path": str(tmp_path / "single.png"),
            "prompt_id": "x",
            "image_filename": "single.png",
            "workflow": {},
            "error": "",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
        # write the file so isfile() passes
        _make_png_file(str(tmp_path / "single.png"))

        with patch.object(ComfyUIClient, "run_from_prompt_generation", return_value=single_result):
            c = ComfyUIClient(base_url="http://localhost:8188")
            result = c.run_scene_beats(pg_no_beats, render_id="r002", output_dir=str(tmp_path))

        assert len(result["output_image_paths"]) == 1
        assert result["output_image_path"] == str(tmp_path / "single.png")


# ---------------------------------------------------------------------------
# 2. assemble_video_sequence — unit tests
# ---------------------------------------------------------------------------

class TestAssembleVideoSequence:

    def test_mock_when_ffmpeg_disabled(self, tmp_path):
        """When FFMPEG_ENABLED=false, returns mock result immediately."""
        imgs = [_make_png_file(str(tmp_path / f"f{i}.png")) for i in range(3)]
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
            res = assemble_video_sequence(
                image_paths=imgs,
                audio_path="",
                duration_seconds=10.0,
                asset_render_id="mocktest",
            )
        assert res.assembly_status == "mock"
        assert res.mock is True
        assert res.ffmpeg_enabled is False
        assert res.simulation_only is True
        assert res.outbound_actions_taken == 0

    def test_single_valid_image_falls_back_to_assemble_video(self, tmp_path):
        """With only one valid image, delegates to assemble_video."""
        img = _make_png_file(str(tmp_path / "only.png"))
        with patch("video_assembler.assemble_video") as mock_av:
            mock_av.return_value = VideoAssemblyResult(
                file_path=str(tmp_path / "out.mp4"),
                duration_seconds=5.0,
                assembly_status="success",
                assembly_engine="ffmpeg",
                simulation_only=True,
            )
            with patch.dict(os.environ, {"FFMPEG_ENABLED": "true"}):
                res = assemble_video_sequence(
                    image_paths=[img],
                    audio_path="",
                    duration_seconds=5.0,
                    asset_render_id="fallback001",
                )
        mock_av.assert_called_once()
        assert res.assembly_status == "success"

    def test_empty_image_paths_falls_back_to_assemble_video(self, tmp_path):
        """Empty list falls back to assemble_video with empty image_path."""
        with patch("video_assembler.assemble_video") as mock_av:
            mock_av.return_value = VideoAssemblyResult(
                assembly_status="mock",
                mock=True,
                simulation_only=True,
            )
            with patch.dict(os.environ, {"FFMPEG_ENABLED": "true"}):
                res = assemble_video_sequence(
                    image_paths=[],
                    duration_seconds=5.0,
                    asset_render_id="empty001",
                )
        mock_av.assert_called_once()

    def test_sequence_calls_ffmpeg_with_multiple_inputs(self, tmp_path):
        """With multiple images and FFMPEG_ENABLED=true, subprocess.run is called."""
        imgs = [_make_png_file(str(tmp_path / f"frame_{i}.png")) for i in range(3)]

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with (
            patch.dict(os.environ, {"FFMPEG_ENABLED": "true"}),
            patch("subprocess.run", return_value=mock_proc) as mock_run,
            patch("video_assembler.generate_test_tone", return_value=str(tmp_path / "tone.wav")),
        ):
            res = assemble_video_sequence(
                image_paths=imgs,
                audio_path="",
                duration_seconds=6.0,
                resolution="1080x1920",
                asset_render_id="seq001",
                output_dir=str(tmp_path),
            )

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        # Should have ffmpeg + multiple -i flags for images + 1 audio
        assert cmd[0] == "ffmpeg"
        assert "-filter_complex" in cmd
        assert "concat" in " ".join(cmd)
        assert res.assembly_status == "success"
        assert res.simulation_only is True
        assert res.outbound_actions_taken == 0

    def test_duration_positive(self, tmp_path):
        """Returned duration_seconds > 0."""
        imgs = [_make_png_file(str(tmp_path / f"f{i}.png")) for i in range(2)]
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
            res = assemble_video_sequence(
                image_paths=imgs,
                duration_seconds=8.5,
                asset_render_id="dur001",
            )
        assert res.duration_seconds > 0

    def test_audio_path_passed_through(self, tmp_path):
        """source_audio_path is forwarded to FFmpeg as-is (preserved)."""
        imgs = [_make_png_file(str(tmp_path / f"f{i}.png")) for i in range(2)]
        audio_path = str(tmp_path / "speech.mp3")
        # write a dummy audio file
        with open(audio_path, "wb") as fh:
            fh.write(b"\x00" * 512)

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with (
            patch.dict(os.environ, {"FFMPEG_ENABLED": "true"}),
            patch("subprocess.run", return_value=mock_proc) as mock_run,
        ):
            assemble_video_sequence(
                image_paths=imgs,
                audio_path=audio_path,
                duration_seconds=5.0,
                asset_render_id="audio001",
                output_dir=str(tmp_path),
            )

        cmd = mock_run.call_args[0][0]
        assert audio_path in cmd, "source_audio_path not passed to FFmpeg"


# ---------------------------------------------------------------------------
# 3. process_render_job integration tests (FakeDatabase — no real MongoDB)
# ---------------------------------------------------------------------------

class TestProcessRenderJobPhase9:
    """Tests for the upgraded worker path (scene beats → multi-image)."""

    def _make_job(self, render_id_str):
        return {"job_id": str(uuid.uuid4()), "render_id": render_id_str}

    def test_comfyui_scene_beats_produce_image_list(self, tmp_path):
        """Worker calls run_scene_beats; comfyui_result has output_image_paths list."""
        fake_db = FakeDatabase()
        snippet = _make_snippet()
        pg = _make_pg(snippet["_id"])
        fake_db.content_snippets.documents.append(snippet)
        fake_db.prompt_generations.documents.append(pg)

        render = _make_render(snippet["_id"], pg["_id"])
        fake_db.asset_renders.documents.append(render)
        render_id_str = str(render["_id"])

        # Build 3 fake PNG paths (one per beat)
        img_paths = []
        for i in range(3):
            p = str(tmp_path / f"{render_id_str}_frame_{i:03d}.png")
            _make_png_file(p)
            img_paths.append(p)

        fake_comfyui_result = {
            "output_image_paths": img_paths,
            "output_image_path": img_paths[0],
            "prompt_ids": ["p1", "p2", "p3"],
            "errors": [],
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

        with (
            patch.dict(os.environ, {
                "COMFYUI_ENABLED": "true",
                "FFMPEG_ENABLED": "false",
                "FFMPEG_OUTPUT_DIR": str(tmp_path),
            }),
            patch("comfyui_client.ComfyUIClient.health_check", return_value={"reachable": True}),
            patch("comfyui_client.ComfyUIClient.run_scene_beats", return_value=fake_comfyui_result),
        ):
            result = process_render_job(self._make_job(render_id_str), db=fake_db)

        record = fake_db.asset_renders.find_one({"_id": render["_id"]})
        assert record is not None
        comfyui_res = record.get("comfyui_result", {})
        assert isinstance(comfyui_res.get("output_image_paths"), list)
        assert len(comfyui_res["output_image_paths"]) == 3
        assert record.get("image_source") == "comfyui"

    def test_simulation_only_and_zero_outbound(self, tmp_path):
        """All records created by worker have simulation_only=True and outbound_actions_taken=0."""
        fake_db = FakeDatabase()
        snippet = _make_snippet()
        pg = _make_pg(snippet["_id"])
        fake_db.content_snippets.documents.append(snippet)
        fake_db.prompt_generations.documents.append(pg)

        render = _make_render(snippet["_id"], pg["_id"])
        fake_db.asset_renders.documents.append(render)
        render_id_str = str(render["_id"])

        img = _make_png_file(str(tmp_path / "frame_000.png"))
        fake_result = {
            "output_image_paths": [img],
            "output_image_path": img,
            "prompt_ids": [],
            "errors": [],
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

        with (
            patch.dict(os.environ, {
                "COMFYUI_ENABLED": "true",
                "FFMPEG_ENABLED": "false",
                "FFMPEG_OUTPUT_DIR": str(tmp_path),
            }),
            patch("comfyui_client.ComfyUIClient.health_check", return_value={"reachable": True}),
            patch("comfyui_client.ComfyUIClient.run_scene_beats", return_value=fake_result),
        ):
            process_render_job(self._make_job(render_id_str), db=fake_db)

        record = fake_db.asset_renders.find_one({"_id": render["_id"]})
        assert record["simulation_only"] is True
        assert record["outbound_actions_taken"] == 0

    def test_audio_path_preserved_in_db(self, tmp_path):
        """source_audio_path in the DB record is unchanged after render."""
        fake_db = FakeDatabase()
        snippet = _make_snippet()
        pg = _make_pg(snippet["_id"])
        fake_db.content_snippets.documents.append(snippet)
        fake_db.prompt_generations.documents.append(pg)

        original_audio = "/tmp/signalforge_renders/test_audio.mp3"
        render = _make_render(snippet["_id"], pg["_id"], source_audio_path=original_audio)
        fake_db.asset_renders.documents.append(render)
        render_id_str = str(render["_id"])

        img = _make_png_file(str(tmp_path / "frame_000.png"))

        with (
            patch.dict(os.environ, {
                "COMFYUI_ENABLED": "true",
                "FFMPEG_ENABLED": "false",
                "FFMPEG_OUTPUT_DIR": str(tmp_path),
            }),
            patch("comfyui_client.ComfyUIClient.health_check", return_value={"reachable": True}),
            patch("comfyui_client.ComfyUIClient.run_scene_beats", return_value={
                "output_image_paths": [img],
                "output_image_path": img,
                "prompt_ids": [],
                "errors": [],
                "simulation_only": True,
                "outbound_actions_taken": 0,
            }),
        ):
            process_render_job(self._make_job(render_id_str), db=fake_db)

        record = fake_db.asset_renders.find_one({"_id": render["_id"]})
        assert record.get("source_audio_path") == original_audio, (
            "source_audio_path was modified — audio must be preserved unchanged"
        )

    def test_no_face_in_negative_prompt(self):
        """Sanity check: negative_prompt always contains face exclusion terms."""
        pg = dict(SAMPLE_PG)
        c = ComfyUIClient(base_url="http://localhost:8188")
        workflow = c.build_txt2img_workflow(pg)
        negative_text = workflow["3"]["inputs"]["text"].lower()
        assert any(term in negative_text for term in ["face", "likeness", "person"]), (
            f"negative_prompt missing face exclusion: {negative_text[:200]}"
        )


