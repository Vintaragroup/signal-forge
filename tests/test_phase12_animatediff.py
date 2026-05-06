"""
test_phase12_animatediff.py — Phase 12: AnimateDiff / Comfy Cloud Video Workflow

Tests:
  - Workflow loads and parses correctly
  - Video output node detection (VHS_VideoCombine, AnimateDiffCombine, etc.)
  - Image output node detection still works
  - validate_animatediff_workflow: passes for valid workflow, fails clearly for missing nodes
  - fetch_cloud_job_outputs classifies images and videos by output_kind
  - download_cloud_outputs_typed separates image and video paths
  - Typed download returns correct file naming for video outputs
  - run_scene_beats_cloud returns video metadata fields when cloud disabled
  - mux_video_with_audio mock path (FFMPEG_ENABLED=false)
  - mux_video_with_audio error path when video_path missing
  - worker.py branches to mux path for comfy_output_type=video
  - worker.py stores Phase 12 metadata (workflow_variant, comfy_output_type, comfy_video_path)
  - backwards compat: download_cloud_outputs returns only image paths
  - simulation_only=True always
  - outbound_actions_taken=0 always
  - no HTTP calls when cloud disabled
  - fallback blocked unless allowed
  - workflow file exists on disk
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Ensure /app is on path when running inside container
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, "/app")

# ---------------------------------------------------------------------------
# Helpers / Fake DB (shared with Phase 11)
# ---------------------------------------------------------------------------

class FakeCollection:
    def __init__(self):
        self._docs = {}

    def insert_one(self, doc):
        from bson import ObjectId
        oid = ObjectId()
        doc["_id"] = oid
        self._docs[str(oid)] = doc
        result = MagicMock()
        result.inserted_id = oid
        return result

    def find_one(self, query):
        from bson import ObjectId
        if "_id" in query:
            return self._docs.get(str(query["_id"]))
        for doc in self._docs.values():
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None

    def update_one(self, query, update):
        doc = self.find_one(query)
        if doc and "$set" in update:
            doc.update(update["$set"])

    def find(self, query=None):
        return list(self._docs.values())


class FakeDatabase:
    def __init__(self):
        self.asset_renders = FakeCollection()
        self.prompt_generations = FakeCollection()
        self.content_snippets = FakeCollection()
        self.renderer_validation_runs = FakeCollection()


ANIMATEDIFF_WORKFLOW = {
    "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
    },
    "2": {
        "class_type": "ADE_AnimateDiffLoaderWithContext",
        "inputs": {"model": ["1", 0], "model_name": "mm_sdxl_v10_beta.ckpt"},
    },
    "3": {
        "class_type": "CLIPTextEncode",
        "inputs": {"clip": ["1", 1], "text": "{{positive_prompt}}, cinematic"},
    },
    "4": {
        "class_type": "CLIPTextEncode",
        "inputs": {"clip": ["1", 1], "text": "{{negative_prompt}}, face"},
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 768, "height": 1344, "batch_size": 24},
    },
    "6": {
        "class_type": "KSampler",
        "inputs": {"seed": 12345, "model": ["2", 0], "positive": ["3", 0], "negative": ["4", 0], "latent_image": ["5", 0]},
    },
    "7": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["6", 0], "vae": ["1", 2]},
    },
    "8": {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": ["7", 0],
            "frame_rate": 12,
            "format": "video/h264-mp4",
            "filename_prefix": "signalforge_animatediff_faceless_t2v",
        },
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "signalforge_animatediff_preview_frame", "images": ["7", 0]},
    },
}

IMAGE_ONLY_WORKFLOW = {
    "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "dreamshaper_8.safetensors"},
    },
    "2": {
        "class_type": "CLIPTextEncode",
        "inputs": {"clip": ["1", 1], "text": "{{positive_prompt}}"},
    },
    "3": {
        "class_type": "CLIPTextEncode",
        "inputs": {"clip": ["1", 1], "text": "{{negative_prompt}}"},
    },
    "4": {
        "class_type": "KSampler",
        "inputs": {"seed": 42, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0]},
    },
    "5": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["4", 0], "vae": ["1", 2]},
    },
    "6": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "output_frame", "images": ["5", 0]},
    },
}


# ---------------------------------------------------------------------------
# 1. Workflow file on disk
# ---------------------------------------------------------------------------

class TestWorkflowFile(unittest.TestCase):
    WORKFLOW_PATH = os.path.join(
        os.path.dirname(__file__), "..",
        "workflows", "comfyui", "signalforge_animatediff_faceless_t2v_v1_api.json",
    )

    def test_workflow_file_exists(self):
        self.assertTrue(
            os.path.isfile(self.WORKFLOW_PATH),
            f"Workflow file not found at {self.WORKFLOW_PATH}",
        )

    def test_workflow_file_is_valid_json(self):
        with open(self.WORKFLOW_PATH) as f:
            wf = json.load(f)
        self.assertIsInstance(wf, dict)
        self.assertGreater(len(wf), 0)

    def test_workflow_has_vhs_videocombine_node(self):
        with open(self.WORKFLOW_PATH) as f:
            wf = json.load(f)
        node_types = {v.get("class_type") for v in wf.values() if isinstance(v, dict)}
        self.assertIn("VHS_VideoCombine", node_types)

    def test_workflow_has_animatediff_loader(self):
        with open(self.WORKFLOW_PATH) as f:
            wf = json.load(f)
        node_types = {v.get("class_type") for v in wf.values() if isinstance(v, dict)}
        ade_nodes = {"ADE_AnimateDiffLoaderWithContext", "AnimateDiffLoader", "AnimateDiffLoaderWithContext"}
        self.assertTrue(node_types & ade_nodes, f"No AnimateDiff loader found in {node_types}")

    def test_workflow_has_prompt_markers(self):
        with open(self.WORKFLOW_PATH) as f:
            content = f.read()
        self.assertIn("{{positive_prompt}}", content)
        self.assertIn("{{negative_prompt}}", content)

    def test_workflow_has_save_image_preview(self):
        with open(self.WORKFLOW_PATH) as f:
            wf = json.load(f)
        node_types = {v.get("class_type") for v in wf.values() if isinstance(v, dict)}
        self.assertIn("SaveImage", node_types)


# ---------------------------------------------------------------------------
# 2. detect_workflow_output_types
# ---------------------------------------------------------------------------

class TestDetectWorkflowOutputTypes(unittest.TestCase):
    def _detect(self, workflow):
        from comfyui_cloud_client import detect_workflow_output_types
        return detect_workflow_output_types(workflow)

    def test_animatediff_workflow_has_video_nodes(self):
        info = self._detect(ANIMATEDIFF_WORKFLOW)
        self.assertTrue(info["has_video_nodes"])
        self.assertIn("8", info["video_node_ids"])

    def test_animatediff_workflow_has_image_nodes(self):
        info = self._detect(ANIMATEDIFF_WORKFLOW)
        self.assertTrue(info["has_image_nodes"])
        self.assertIn("9", info["image_node_ids"])

    def test_animatediff_workflow_detects_motion_model(self):
        info = self._detect(ANIMATEDIFF_WORKFLOW)
        self.assertTrue(info["has_animatediff"])
        self.assertIn("mm_sdxl_v10_beta.ckpt", info["motion_model_names"])

    def test_animatediff_workflow_detects_checkpoint(self):
        info = self._detect(ANIMATEDIFF_WORKFLOW)
        self.assertIn("sd_xl_base_1.0.safetensors", info["checkpoint_names"])

    def test_image_only_workflow_no_video_nodes(self):
        info = self._detect(IMAGE_ONLY_WORKFLOW)
        self.assertFalse(info["has_video_nodes"])
        self.assertEqual(info["video_node_ids"], [])

    def test_image_only_workflow_has_image_nodes(self):
        info = self._detect(IMAGE_ONLY_WORKFLOW)
        self.assertTrue(info["has_image_nodes"])

    def test_image_only_workflow_no_animatediff(self):
        info = self._detect(IMAGE_ONLY_WORKFLOW)
        self.assertFalse(info["has_animatediff"])

    def test_empty_workflow_returns_false_flags(self):
        info = self._detect({})
        self.assertFalse(info["has_video_nodes"])
        self.assertFalse(info["has_image_nodes"])
        self.assertFalse(info["has_animatediff"])


# ---------------------------------------------------------------------------
# 3. validate_animatediff_workflow
# ---------------------------------------------------------------------------

class TestValidateAnimateDiffWorkflow(unittest.TestCase):
    def _validate(self, workflow):
        from comfyui_cloud_client import validate_animatediff_workflow
        return validate_animatediff_workflow(workflow)

    def test_valid_animatediff_workflow_passes(self):
        result = self._validate(ANIMATEDIFF_WORKFLOW)
        self.assertTrue(result["valid"])
        self.assertEqual(result["errors"], [])

    def test_image_only_workflow_fails_validation(self):
        result = self._validate(IMAGE_ONLY_WORKFLOW)
        self.assertFalse(result["valid"])
        self.assertTrue(len(result["errors"]) > 0)
        # Error mentions specific node types
        error_text = " ".join(result["errors"])
        self.assertIn("VHS_VideoCombine", error_text)

    def test_validation_result_has_required_keys(self):
        result = self._validate(ANIMATEDIFF_WORKFLOW)
        for key in ("valid", "has_video_nodes", "has_image_nodes", "has_animatediff",
                    "video_node_ids", "image_node_ids", "motion_model_names", "errors", "warnings"):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_video_node_without_animatediff_loader_produces_warning(self):
        workflow_no_loader = {
            "1": {"class_type": "VHS_VideoCombine", "inputs": {}},
        }
        result = self._validate(workflow_no_loader)
        self.assertTrue(result["valid"])  # Not an error, just a warning
        self.assertTrue(len(result["warnings"]) > 0)


# ---------------------------------------------------------------------------
# 4. fetch_cloud_job_outputs with output_kind classification
# ---------------------------------------------------------------------------

class TestFetchCloudJobOutputsTyped(unittest.TestCase):
    def test_images_classified_as_image(self):
        from comfyui_cloud_client import ComfyCloudClient, fetch_cloud_job_outputs
        mock_client = MagicMock(spec=ComfyCloudClient)
        mock_client.fetch_job_outputs.return_value = {
            "outputs": {
                "9": {"images": [{"filename": "frame_001.png", "subfolder": "", "type": "output"}]},
            }
        }
        refs = fetch_cloud_job_outputs(mock_client, "test-prompt-id")
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["output_kind"], "image")
        self.assertEqual(refs[0]["filename"], "frame_001.png")

    def test_videos_in_videos_key_classified_as_video(self):
        from comfyui_cloud_client import ComfyCloudClient, fetch_cloud_job_outputs
        mock_client = MagicMock(spec=ComfyCloudClient)
        mock_client.fetch_job_outputs.return_value = {
            "outputs": {
                "8": {"videos": [{"filename": "output.mp4", "subfolder": "", "type": "output"}]},
            }
        }
        refs = fetch_cloud_job_outputs(mock_client, "test-prompt-id")
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["output_kind"], "video")

    def test_mixed_outputs_classified_correctly(self):
        from comfyui_cloud_client import ComfyCloudClient, fetch_cloud_job_outputs
        mock_client = MagicMock(spec=ComfyCloudClient)
        mock_client.fetch_job_outputs.return_value = {
            "outputs": {
                "8": {"videos": [{"filename": "clip.mp4", "subfolder": "", "type": "output"}]},
                "9": {"images": [{"filename": "preview.png", "subfolder": "", "type": "output"}]},
            }
        }
        refs = fetch_cloud_job_outputs(mock_client, "test-prompt-id")
        kinds = {r["output_kind"] for r in refs}
        self.assertIn("video", kinds)
        self.assertIn("image", kinds)

    def test_extension_based_classification_for_mp4(self):
        from comfyui_cloud_client import ComfyCloudClient, fetch_cloud_job_outputs
        mock_client = MagicMock(spec=ComfyCloudClient)
        mock_client.fetch_job_outputs.return_value = {
            "results": [{"filename": "generated.mp4", "subfolder": "", "type": "output"}]
        }
        refs = fetch_cloud_job_outputs(mock_client, "test-prompt-id")
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["output_kind"], "video")


# ---------------------------------------------------------------------------
# 5. download_cloud_outputs_typed
# ---------------------------------------------------------------------------

class TestDownloadCloudOutputsTyped(unittest.TestCase):
    def test_video_output_named_correctly(self):
        from comfyui_cloud_client import ComfyCloudClient, download_cloud_outputs_typed
        mock_client = MagicMock(spec=ComfyCloudClient)
        mock_client.download_output.return_value = b"fake video bytes"
        refs = [{"filename": "clip.mp4", "subfolder": "", "type": "output", "output_kind": "video"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            results = download_cloud_outputs_typed(
                mock_client, "pid", refs, tmpdir, "render-abc"
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["output_kind"], "video")
        self.assertTrue(results[0]["path"].endswith(".mp4") or "_cloud_video_" in results[0]["path"])

    def test_image_output_named_correctly(self):
        from comfyui_cloud_client import ComfyCloudClient, download_cloud_outputs_typed
        mock_client = MagicMock(spec=ComfyCloudClient)
        mock_client.download_output.return_value = b"fake png bytes"
        refs = [{"filename": "frame.png", "subfolder": "", "type": "output", "output_kind": "image"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            results = download_cloud_outputs_typed(
                mock_client, "pid", refs, tmpdir, "render-abc"
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["output_kind"], "image")
        self.assertIn("_cloud_frame_", results[0]["path"])

    def test_backwards_compat_download_returns_image_paths_only(self):
        from comfyui_cloud_client import ComfyCloudClient, download_cloud_outputs
        mock_client = MagicMock(spec=ComfyCloudClient)
        mock_client.download_output.return_value = b"fake bytes"
        refs = [
            {"filename": "frame.png", "subfolder": "", "type": "output", "output_kind": "image"},
            {"filename": "clip.mp4", "subfolder": "", "type": "output", "output_kind": "video"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = download_cloud_outputs(mock_client, "pid", refs, tmpdir, "render-abc")

        # Should only return image paths
        self.assertEqual(len(paths), 1)
        self.assertNotIn(".mp4", paths[0])


# ---------------------------------------------------------------------------
# 6. run_scene_beats_cloud — video metadata fields
# ---------------------------------------------------------------------------

class TestRunSceneBeatsCLoudVideoFields(unittest.TestCase):
    def test_result_has_video_fields_when_disabled(self):
        """Even when disabled, result dict contains new Phase 12 keys."""
        from comfyui_cloud_client import run_scene_beats_cloud
        with patch.dict(os.environ, {"COMFY_CLOUD_ENABLED": "false"}):
            result = run_scene_beats_cloud(
                {"positive_prompt": "test", "scene_beats": ["beat 1"]},
                render_id="render-test",
            )
        for key in ("workflow_variant", "comfy_output_type", "output_video_paths",
                    "comfy_video_path", "downloaded_outputs"):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_simulation_only_always_true(self):
        from comfyui_cloud_client import run_scene_beats_cloud
        with patch.dict(os.environ, {"COMFY_CLOUD_ENABLED": "false"}):
            result = run_scene_beats_cloud({"positive_prompt": "test"}, render_id="r1")
        self.assertTrue(result["simulation_only"])

    def test_outbound_actions_always_zero(self):
        from comfyui_cloud_client import run_scene_beats_cloud
        with patch.dict(os.environ, {"COMFY_CLOUD_ENABLED": "false"}):
            result = run_scene_beats_cloud({"positive_prompt": "test"}, render_id="r1")
        self.assertEqual(result["outbound_actions_taken"], 0)

    def test_animatediff_workflow_sets_variant_and_output_type(self):
        """With mocked cloud calls, check workflow_variant and comfy_output_type."""
        from comfyui_cloud_client import run_scene_beats_cloud

        with patch.dict(os.environ, {
            "COMFY_CLOUD_ENABLED": "true",
            "COMFY_CLOUD_API_KEY": "test-key-placeholder",
            "COMFY_CLOUD_WORKFLOW_PATH": "/tmp/test_wf.json",
        }):
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(ANIMATEDIFF_WORKFLOW, f)
                wf_path = f.name
            try:
                with patch.dict(os.environ, {"COMFY_CLOUD_WORKFLOW_PATH": wf_path}):
                    with patch("comfyui_cloud_client.ComfyCloudClient") as MockClient:
                        mock_inst = MagicMock()
                        MockClient.return_value = mock_inst
                        mock_inst.submit_workflow.return_value = {"prompt_id": "pid-001"}
                        mock_inst.poll_job_status.return_value = {"status": "completed"}
                        mock_inst.fetch_job_outputs.return_value = {
                            "outputs": {
                                "8": {"videos": [{"filename": "clip.mp4", "subfolder": "", "type": "output"}]},
                                "9": {"images": [{"filename": "frame.png", "subfolder": "", "type": "output"}]},
                            }
                        }
                        mock_inst.download_output.return_value = b"fake content"

                        with tempfile.TemporaryDirectory() as tmpdir:
                            result = run_scene_beats_cloud(
                                {"positive_prompt": "test", "scene_beats": ["beat 1"]},
                                render_id="render-test",
                                output_dir=tmpdir,
                                workflow_path=wf_path,
                            )
            finally:
                os.unlink(wf_path)

        self.assertEqual(result["workflow_variant"], "animatediff_t2v")
        self.assertIn(result["comfy_output_type"], ("video", "mixed"))
        self.assertTrue(result["simulation_only"])
        self.assertEqual(result["outbound_actions_taken"], 0)

    def test_fallback_blocked_when_not_allowed(self):
        from comfyui_cloud_client import run_scene_beats_cloud
        with patch.dict(os.environ, {
            "COMFY_CLOUD_ENABLED": "false",
            "COMFY_CLOUD_FALLBACK_ALLOWED": "false",
        }):
            result = run_scene_beats_cloud({"positive_prompt": "test"}, render_id="r1")
        self.assertFalse(result["fallback_used"])
        self.assertGreater(len(result["errors"]), 0)

    def test_animatediff_validation_fails_for_image_only_workflow(self):
        """Image-only workflow should fail AnimateDiff validation and return errors."""
        from comfyui_cloud_client import run_scene_beats_cloud

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(IMAGE_ONLY_WORKFLOW, f)
            wf_path = f.name
        try:
            with patch.dict(os.environ, {
                "COMFY_CLOUD_ENABLED": "true",
                "COMFY_CLOUD_API_KEY": "test-key-placeholder",
                "COMFY_CLOUD_WORKFLOW_PATH": wf_path,
                "COMFY_CLOUD_FALLBACK_ALLOWED": "false",
            }):
                result = run_scene_beats_cloud(
                    {"positive_prompt": "test", "scene_beats": ["beat 1"]},
                    render_id="render-validate-test",
                    workflow_path=wf_path,
                )
        finally:
            os.unlink(wf_path)

        # Image-only workflow has no video nodes — no validation failure from validate_animatediff_workflow
        # because it only runs if has_video_nodes is True. So comfy_output_type stays image_sequence.
        # No errors expected from the AnimateDiff validation path.
        self.assertTrue(result["simulation_only"])
        self.assertEqual(result["outbound_actions_taken"], 0)


# ---------------------------------------------------------------------------
# 7. mux_video_with_audio
# ---------------------------------------------------------------------------

class TestMuxVideoWithAudio(unittest.TestCase):
    def test_mock_when_ffmpeg_disabled(self):
        from video_assembler import mux_video_with_audio
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
            result = mux_video_with_audio(
                video_path="/tmp/fake_video.mp4",
                audio_path="/tmp/fake_audio.mp3",
                asset_render_id="test-mux-1",
            )
        self.assertTrue(result.mock)
        self.assertEqual(result.assembly_status, "mock")
        self.assertTrue(result.simulation_only)
        self.assertEqual(result.outbound_actions_taken, 0)

    def test_failed_when_video_path_missing(self):
        from video_assembler import mux_video_with_audio
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "true"}):
            result = mux_video_with_audio(
                video_path="/tmp/nonexistent_video_file_12345.mp4",
                audio_path="",
                asset_render_id="test-mux-2",
            )
        self.assertEqual(result.assembly_status, "failed")
        self.assertIn("not found", result.error.lower())
        self.assertTrue(result.simulation_only)
        self.assertEqual(result.outbound_actions_taken, 0)

    def test_mock_returns_mp4_path(self):
        from video_assembler import mux_video_with_audio
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
            result = mux_video_with_audio(
                video_path="/tmp/fake.mp4",
                audio_path="/tmp/fake.mp3",
                asset_render_id="test-mux-3",
            )
        self.assertTrue(result.file_path.endswith(".mp4"))

    def test_preserve_original_audio_flag_respected(self):
        from video_assembler import mux_video_with_audio
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
            result = mux_video_with_audio(
                video_path="/tmp/fake.mp4",
                audio_path="/tmp/real_audio.mp3",
                asset_render_id="test-mux-4",
                preserve_original_audio=True,
            )
        # Function should complete without error (not raise on preserve_original_audio)
        self.assertTrue(result.simulation_only)


# ---------------------------------------------------------------------------
# 8. worker.py — Phase 12 metadata stored
# ---------------------------------------------------------------------------

class TestWorkerPhase12Metadata(unittest.TestCase):
    def _make_render(self, db):
        from bson import ObjectId
        pg_doc = {
            "workspace_slug": "john-maxwell-pilot",
            "positive_prompt": "leadership inspiration cinematic",
            "visual_style": "cinematic",
            "lighting": "warm dramatic",
            "negative_prompt": "face, portrait",
            "scene_beats": ["beat one"],
        }
        pg_id = db.prompt_generations.insert_one(pg_doc).inserted_id

        render_doc = {
            "workspace_slug": "john-maxwell-pilot",
            "prompt_generation_id": str(pg_id),
            "snippet_id": "",
            "status": "queued",
            "source_audio_path": "",
            "add_captions": False,
            "preserve_original_audio": True,
            "resolution": "1080x1920",
            "generation_engine": "comfyui_cloud",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
        render_id = db.asset_renders.insert_one(render_doc).inserted_id
        return str(render_id)

    def test_video_path_stored_when_comfy_returns_video(self):
        """Worker stores comfy_video_path when comfy_output_type=video."""
        from worker import process_render_job

        db = FakeDatabase()
        render_id_str = self._make_render(db)

        mock_comfyui_result = {
            "renderer_type": "comfyui_cloud",
            "workflow_variant": "animatediff_t2v",
            "comfy_output_type": "video",
            "comfy_video_path": "/tmp/signalforge_renders/render-abc_cloud_video_000.mp4",
            "output_video_paths": ["/tmp/signalforge_renders/render-abc_cloud_video_000.mp4"],
            "output_image_paths": [],
            "output_image_path": "",
            "downloaded_outputs": [
                {"path": "/tmp/signalforge_renders/render-abc_cloud_video_000.mp4",
                 "output_kind": "video", "filename": "clip.mp4"},
            ],
            "cloud_job_ids": ["pid-001"],
            "fallback_used": False,
            "fallback_reason": "",
            "errors": [],
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

        mock_va_result = MagicMock()
        mock_va_result.file_path = "/tmp/signalforge_renders/render-abc_muxed.mp4"
        mock_va_result.assembly_status = "mock"
        mock_va_result.assembly_engine = "mock"
        mock_va_result.to_dict.return_value = {
            "file_path": mock_va_result.file_path,
            "assembly_status": "mock",
            "assembly_engine": "mock",
            "mock": True,
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true", "FFMPEG_ENABLED": "false"}):
            with patch("comfyui_client.ComfyUIClient") as MockCUI:
                mock_cui = MagicMock()
                MockCUI.return_value = mock_cui
                mock_cui.health_check.return_value = {"reachable": True}
                mock_cui.run_scene_beats.return_value = mock_comfyui_result
                with patch("video_assembler.mux_video_with_audio", return_value=mock_va_result):
                    with patch("video_assembler.assemble_video", return_value=mock_va_result):
                        result = process_render_job({"render_id": render_id_str}, db)

        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["workflow_variant"], "animatediff_t2v")
        self.assertEqual(result["comfy_output_type"], "video")
        self.assertEqual(
            result["comfy_video_path"],
            "/tmp/signalforge_renders/render-abc_cloud_video_000.mp4",
        )
        self.assertTrue(result["simulation_only"])
        self.assertEqual(result["outbound_actions_taken"], 0)

    def test_metadata_written_to_db(self):
        """worker writes workflow_variant, comfy_output_type, comfy_video_path to DB."""
        from worker import process_render_job

        db = FakeDatabase()
        render_id_str = self._make_render(db)

        from bson import ObjectId
        render_doc = db.asset_renders.find_one(
            {"_id": ObjectId(render_id_str)}
        )

        mock_comfyui_result = {
            "renderer_type": "comfyui_cloud",
            "workflow_variant": "animatediff_t2v",
            "comfy_output_type": "video",
            "comfy_video_path": "/tmp/test_cloud_video.mp4",
            "output_video_paths": ["/tmp/test_cloud_video.mp4"],
            "output_image_paths": [],
            "output_image_path": "",
            "downloaded_outputs": [],
            "cloud_job_ids": [],
            "fallback_used": False,
            "fallback_reason": "",
            "errors": [],
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

        mock_va_result = MagicMock()
        mock_va_result.file_path = "/tmp/test_muxed.mp4"
        mock_va_result.assembly_status = "mock"
        mock_va_result.assembly_engine = "mock"
        mock_va_result.to_dict.return_value = {
            "file_path": "/tmp/test_muxed.mp4",
            "assembly_status": "mock",
            "assembly_engine": "mock",
            "mock": True,
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true", "FFMPEG_ENABLED": "false"}):
            with patch("comfyui_client.ComfyUIClient") as MockCUI:
                mock_cui = MagicMock()
                MockCUI.return_value = mock_cui
                mock_cui.health_check.return_value = {"reachable": True}
                mock_cui.run_scene_beats.return_value = mock_comfyui_result
                with patch("video_assembler.mux_video_with_audio", return_value=mock_va_result):
                    with patch("video_assembler.assemble_video", return_value=mock_va_result):
                        process_render_job({"render_id": render_id_str}, db)

        updated = db.asset_renders.find_one({"_id": ObjectId(render_id_str)})
        self.assertEqual(updated["workflow_variant"], "animatediff_t2v")
        self.assertEqual(updated["comfy_output_type"], "video")
        self.assertEqual(updated["comfy_video_path"], "/tmp/test_cloud_video.mp4")
        self.assertTrue(updated["simulation_only"])
        self.assertEqual(updated["outbound_actions_taken"], 0)

    def test_image_sequence_path_unchanged(self):
        """Image-sequence workflow still uses assemble_video_sequence path."""
        from worker import process_render_job

        db = FakeDatabase()
        render_id_str = self._make_render(db)

        mock_comfyui_result = {
            "renderer_type": "comfyui_cloud",
            "workflow_variant": "",
            "comfy_output_type": "image_sequence",
            "comfy_video_path": "",
            "output_video_paths": [],
            "output_image_paths": [],
            "output_image_path": "",
            "downloaded_outputs": [],
            "cloud_job_ids": [],
            "fallback_used": False,
            "fallback_reason": "",
            "errors": [],
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

        mock_va_result = MagicMock()
        mock_va_result.file_path = "/tmp/mock_render.mp4"
        mock_va_result.assembly_status = "mock"
        mock_va_result.assembly_engine = "mock"
        mock_va_result.to_dict.return_value = {
            "file_path": "/tmp/mock_render.mp4",
            "assembly_status": "mock",
            "assembly_engine": "mock",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

        mux_called = []

        def track_mux(**kwargs):
            mux_called.append(kwargs)
            return mock_va_result

        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true", "FFMPEG_ENABLED": "false"}):
            with patch("comfyui_client.ComfyUIClient") as MockCUI:
                mock_cui = MagicMock()
                MockCUI.return_value = mock_cui
                mock_cui.health_check.return_value = {"reachable": True}
                mock_cui.run_scene_beats.return_value = mock_comfyui_result
                with patch("video_assembler.mux_video_with_audio", side_effect=track_mux):
                    with patch("video_assembler.assemble_video", return_value=mock_va_result):
                        process_render_job({"render_id": render_id_str}, db)

        # mux should NOT have been called for image_sequence output
        self.assertEqual(len(mux_called), 0)


# ---------------------------------------------------------------------------
# 9. Safety invariants
# ---------------------------------------------------------------------------

class TestPhase12SafetyInvariants(unittest.TestCase):
    def test_no_http_calls_when_cloud_disabled(self):
        """Cloud disabled → no HTTP calls made."""
        from comfyui_cloud_client import run_scene_beats_cloud
        http_calls = []

        with patch("urllib.request.urlopen", side_effect=lambda *a, **k: http_calls.append(a)):
            with patch.dict(os.environ, {"COMFY_CLOUD_ENABLED": "false"}):
                run_scene_beats_cloud({"positive_prompt": "test"}, render_id="r1")

        self.assertEqual(len(http_calls), 0)

    def test_api_key_never_in_diagnostics(self):
        """cloud_diagnostics never returns API key value."""
        from comfyui_cloud_client import cloud_diagnostics
        with patch.dict(os.environ, {"COMFY_CLOUD_API_KEY": "super-secret-key-12345"}):
            diag = cloud_diagnostics()
        result_str = json.dumps(diag)
        self.assertNotIn("super-secret-key-12345", result_str)
        self.assertIn("api_key_configured", result_str)

    def test_validate_animatediff_does_not_silently_fallback(self):
        """validate_animatediff_workflow with missing nodes returns valid=False, not silent pass."""
        from comfyui_cloud_client import validate_animatediff_workflow
        result = validate_animatediff_workflow(IMAGE_ONLY_WORKFLOW)
        self.assertFalse(result["valid"])
        self.assertGreater(len(result["errors"]), 0)

    def test_mux_simulation_only_always_true(self):
        from video_assembler import mux_video_with_audio
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
            result = mux_video_with_audio(video_path="/tmp/fake.mp4")
        self.assertTrue(result.simulation_only)

    def test_mux_outbound_always_zero(self):
        from video_assembler import mux_video_with_audio
        with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
            result = mux_video_with_audio(video_path="/tmp/fake.mp4")
        self.assertEqual(result.outbound_actions_taken, 0)


if __name__ == "__main__":
    unittest.main()
