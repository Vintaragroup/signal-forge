"""
test_phase10_renderer_backend.py — Phase 10: Renderer backend abstraction tests

Tests:
  - resolve_renderer_type() returns correct renderer based on env
  - validate_renderer() rejects real renderer without workflow path
  - Fallback logic when COMFYUI_FALLBACK_ALLOWED=true
  - load_real_workflow() injects prompts via markers
  - load_real_workflow() patches portrait dimensions
  - load_real_workflow() fallback to first two CLIP nodes when no markers
  - run_scene_beats() includes renderer metadata in result
  - run_scene_beats() fails cleanly without workflow path for real renderer
  - Safety negative prompt always included
  - simulation_only=True and outbound_actions_taken=0 always
  - No external publishing / no HTTP calls outside ComfyUI base URL
  - Original audio preserved (not modified by renderer)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Ensure the api package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import comfyui_client as cc


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_workflow_with_markers() -> dict:
    """Return a minimal ComfyUI API-format workflow with {{positive_prompt}} markers."""
    return {
        "1": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "{{positive_prompt}}", "clip": ["3", 1]},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "{{negative_prompt}}", "clip": ["3", 1]},
        },
        "3": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 512, "height": 512, "batch_size": 1},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 42,
                "steps": 20,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "model": ["3", 0],
                "positive": ["1", 0],
                "negative": ["2", 0],
                "latent_image": ["4", 0],
                "denoise": 1.0,
            },
        },
    }


def _make_workflow_no_markers() -> dict:
    """Return a minimal workflow WITHOUT injection markers."""
    return {
        "1": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "a generic positive prompt", "clip": ["3", 1]},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "bad quality", "clip": ["3", 1]},
        },
        "3": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 512, "height": 512, "batch_size": 1},
        },
    }


# ---------------------------------------------------------------------------
# TestResolveRendererType
# ---------------------------------------------------------------------------

class TestResolveRendererType(unittest.TestCase):
    """resolve_renderer_type() must never label stub output as real."""

    def test_default_is_stub(self):
        """No env set → comfyui_stub."""
        with patch.dict(os.environ, {}, clear=False):
            for key in ("COMFYUI_RENDERER_TYPE", "COMFYUI_WORKFLOW_PATH", "COMFYUI_ENABLED"):
                os.environ.pop(key, None)
            result = cc.resolve_renderer_type()
        self.assertEqual(result, "comfyui_stub")

    def test_explicit_override_stub(self):
        with patch.dict(os.environ, {"COMFYUI_RENDERER_TYPE": "comfyui_stub"}, clear=False):
            result = cc.resolve_renderer_type()
        self.assertEqual(result, "comfyui_stub")

    def test_explicit_override_real(self):
        with patch.dict(os.environ, {"COMFYUI_RENDERER_TYPE": "comfyui_real"}, clear=False):
            result = cc.resolve_renderer_type()
        self.assertEqual(result, "comfyui_real")

    def test_explicit_override_external_manual(self):
        with patch.dict(os.environ, {"COMFYUI_RENDERER_TYPE": "external_manual"}, clear=False):
            result = cc.resolve_renderer_type()
        self.assertEqual(result, "external_manual")

    def test_enabled_with_workflow_path_resolves_real(self):
        with patch.dict(os.environ, {
            "COMFYUI_ENABLED": "true",
            "COMFYUI_WORKFLOW_PATH": "/some/path.json",
        }, clear=False):
            os.environ.pop("COMFYUI_RENDERER_TYPE", None)
            result = cc.resolve_renderer_type()
        self.assertEqual(result, "comfyui_real")

    def test_enabled_without_workflow_resolves_stub(self):
        with patch.dict(os.environ, {"COMFYUI_ENABLED": "true"}, clear=False):
            os.environ.pop("COMFYUI_RENDERER_TYPE", None)
            os.environ.pop("COMFYUI_WORKFLOW_PATH", None)
            result = cc.resolve_renderer_type()
        self.assertEqual(result, "comfyui_stub")

    def test_stub_renderer_cannot_be_labeled_real(self):
        """Core Phase 10 invariant: stub result must never report renderer_type=comfyui_real."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COMFYUI_RENDERER_TYPE", None)
            os.environ.pop("COMFYUI_WORKFLOW_PATH", None)
            result = cc.resolve_renderer_type()
        self.assertNotEqual(result, "comfyui_real",
            "Stub renderer must never be labeled as comfyui_real")


# ---------------------------------------------------------------------------
# TestValidateRenderer
# ---------------------------------------------------------------------------

class TestValidateRenderer(unittest.TestCase):

    def test_stub_is_always_valid(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COMFYUI_RENDERER_TYPE", None)
            os.environ.pop("COMFYUI_WORKFLOW_PATH", None)
            result = cc.validate_renderer("comfyui_stub")
        self.assertTrue(result["valid"])
        self.assertEqual(result["renderer_type"], "comfyui_stub")

    def test_real_renderer_requires_workflow_path(self):
        """COMFYUI_ENABLED=true + renderer_type=comfyui_real + no workflow → invalid."""
        with patch.dict(os.environ, {
            "COMFYUI_ENABLED": "true",
            "COMFYUI_FALLBACK_ALLOWED": "false",
        }, clear=False):
            os.environ.pop("COMFYUI_WORKFLOW_PATH", None)
            result = cc.validate_renderer("comfyui_real")
        self.assertFalse(result["valid"])
        self.assertTrue(len(result["errors"]) > 0,
            "Must have at least one error when real renderer + no workflow")

    def test_real_renderer_invalid_file_path(self):
        """Workflow path exists in env but file does not exist → invalid (no fallback)."""
        with patch.dict(os.environ, {
            "COMFYUI_WORKFLOW_PATH": "/nonexistent/workflow.json",
            "COMFYUI_FALLBACK_ALLOWED": "false",
        }, clear=False):
            result = cc.validate_renderer("comfyui_real")
        self.assertFalse(result["valid"])
        self.assertTrue(len(result["errors"]) > 0)

    def test_fallback_allowed_downgrades_to_stub(self):
        """When COMFYUI_FALLBACK_ALLOWED=true, bad real workflow falls back to stub."""
        with patch.dict(os.environ, {
            "COMFYUI_FALLBACK_ALLOWED": "true",
            "COMFYUI_ENABLED": "true",
        }, clear=False):
            os.environ.pop("COMFYUI_WORKFLOW_PATH", None)
            result = cc.validate_renderer("comfyui_real")
        self.assertTrue(result["valid"])
        self.assertEqual(result["renderer_type"], "comfyui_stub")
        self.assertTrue(len(result["warnings"]) > 0,
            "Fallback should be documented in warnings")

    def test_stub_warning_always_present(self):
        """Stub validation always includes a warning that output is not production-ready."""
        result = cc.validate_renderer("comfyui_stub")
        stub_warnings = [w for w in result["warnings"] if "not production-ready" in w.lower()
                         or "test stub" in w.lower()]
        self.assertTrue(len(stub_warnings) > 0,
            "Stub renderer must warn that output is not production-ready")

    def test_model_name_present_in_result(self):
        result = cc.validate_renderer("comfyui_stub")
        self.assertIn("model_name", result)
        self.assertIsInstance(result["model_name"], str)

    def test_workflow_path_present_in_result(self):
        result = cc.validate_renderer("comfyui_stub")
        self.assertIn("workflow_path", result)


# ---------------------------------------------------------------------------
# TestLoadRealWorkflow
# ---------------------------------------------------------------------------

class TestLoadRealWorkflow(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _write_workflow(self, workflow: dict) -> str:
        path = os.path.join(self.tmp.name, "workflow.json")
        with open(path, "w") as fh:
            json.dump(workflow, fh)
        return path

    def test_inject_positive_via_markers(self):
        path = self._write_workflow(_make_workflow_with_markers())
        pg = {"positive_prompt": "mountain sunrise, no people"}
        result = cc.load_real_workflow(pg, path, positive_override="cinematic B-roll")
        positive_node = result["1"]["inputs"]["text"]
        self.assertEqual(positive_node, "cinematic B-roll")

    def test_inject_negative_via_markers(self):
        path = self._write_workflow(_make_workflow_with_markers())
        pg = {"negative_prompt": "ugly, blurry"}
        result = cc.load_real_workflow(pg, path)
        negative_node = result["2"]["inputs"]["text"]
        # Safety terms should be appended
        self.assertIn("ugly, blurry", negative_node)

    def test_safety_negative_always_injected(self):
        """_SAFETY_NEGATIVE terms must appear in negative prompt regardless of input."""
        path = self._write_workflow(_make_workflow_with_markers())
        pg = {}
        result = cc.load_real_workflow(pg, path)
        negative_node = result["2"]["inputs"]["text"]
        for term in ("face", "likeness"):
            self.assertIn(term, negative_node,
                f"Safety term '{term}' must be in negative prompt")

    def test_force_portrait_patches_latent_image(self):
        path = self._write_workflow(_make_workflow_with_markers())
        pg = {}
        result = cc.load_real_workflow(pg, path, force_portrait=True)
        latent_node = result["4"]["inputs"]
        self.assertEqual(latent_node["width"], 1080)
        self.assertEqual(latent_node["height"], 1920)

    def test_force_portrait_false_leaves_dimensions_unchanged(self):
        path = self._write_workflow(_make_workflow_with_markers())
        pg = {}
        result = cc.load_real_workflow(pg, path, force_portrait=False)
        latent_node = result["4"]["inputs"]
        self.assertEqual(latent_node["width"], 512)
        self.assertEqual(latent_node["height"], 512)

    def test_fallback_no_markers_uses_first_two_clip_nodes(self):
        path = self._write_workflow(_make_workflow_no_markers())
        pg = {"positive_prompt": "golden hour"}
        result = cc.load_real_workflow(pg, path, positive_override="golden hour cinematic")
        # First CLIP node should receive positive text
        first_clip_text = result["1"]["inputs"]["text"]
        self.assertEqual(first_clip_text, "golden hour cinematic")

    def test_invalid_path_raises_value_error(self):
        with self.assertRaises(ValueError):
            cc.load_real_workflow({}, "/nonexistent/path/workflow.json")


# ---------------------------------------------------------------------------
# TestRunSceneBeatsMetadata
# ---------------------------------------------------------------------------

# Minimal fake ComfyUI response
_FAKE_SUBMIT_RESP = {"prompt_id": "test-prompt-001"}
_FAKE_HISTORY = {
    "test-prompt-001": {
        "status": {"completed": True},
        "outputs": {
            "9": {
                "images": [{"filename": "test_output.png", "subfolder": "", "type": "output"}]
            }
        },
    }
}


class TestRunSceneBeatsMetadata(unittest.TestCase):

    def _make_pg(self, beat_count: int = 2) -> dict:
        return {
            "_id": "render_test_01",
            "positive_prompt": "sunrise mountain, cinematic B-roll",
            "negative_prompt": "blurry",
            "visual_style": "golden hour",
            "lighting": "warm ambient",
            "scene_beats": [f"scene beat {i}" for i in range(beat_count)],
        }

    def _fake_download(self, fname, subfolder, img_type, path):
        """Write a tiny PNG so os.path.isfile(path) passes."""
        with open(path, "wb") as fh:
            # Minimal 1x1 PNG header
            fh.write(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
                b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01"
                b"\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
            )
        return path

    @patch.dict(os.environ, {
        "COMFYUI_ENABLED": "true",
        "COMFYUI_RENDERER_TYPE": "comfyui_stub",
    }, clear=False)
    def test_stub_metadata_returned(self):
        """run_scene_beats() must return renderer_type=comfyui_stub in result."""
        client = cc.ComfyUIClient()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(client, "_queue_prompt", return_value=_FAKE_SUBMIT_RESP), \
                 patch.object(client, "_get_history", return_value=_FAKE_HISTORY), \
                 patch.object(client, "_download_image", side_effect=self._fake_download):
                result = client.run_scene_beats(self._make_pg(), "render_test_01", tmpdir)

        self.assertEqual(result["renderer_type"], "comfyui_stub",
            "Stub render must report renderer_type=comfyui_stub")
        self.assertIn("renderer_type", result)
        self.assertIn("workflow_path", result)
        self.assertIn("model_name", result)
        self.assertIn("fallback_used", result)
        self.assertIn("fallback_reason", result)

    @patch.dict(os.environ, {
        "COMFYUI_ENABLED": "true",
        "COMFYUI_FALLBACK_ALLOWED": "false",
    }, clear=False)
    def test_real_renderer_fails_without_workflow(self):
        """run_scene_beats() must return errors when renderer_type=comfyui_real + no workflow."""
        env_patch = {
            "COMFYUI_ENABLED": "true",
            "COMFYUI_FALLBACK_ALLOWED": "false",
            "COMFYUI_RENDERER_TYPE": "comfyui_real",
        }
        with patch.dict(os.environ, env_patch, clear=False):
            os.environ.pop("COMFYUI_WORKFLOW_PATH", None)
            client = cc.ComfyUIClient()
            result = client.run_scene_beats(self._make_pg(), "render_test_fail")

        self.assertEqual(result["output_image_paths"], [])
        self.assertTrue(len(result["errors"]) > 0,
            "Must report errors when real renderer requested but no workflow path")

    def test_simulation_only_and_zero_outbound(self):
        """simulation_only=True, outbound_actions_taken=0 always."""
        with patch.dict(os.environ, {
            "COMFYUI_RENDERER_TYPE": "comfyui_stub",
        }, clear=False):
            client = cc.ComfyUIClient()
            with tempfile.TemporaryDirectory() as tmpdir:
                with patch.object(client, "_queue_prompt", return_value=_FAKE_SUBMIT_RESP), \
                     patch.object(client, "_get_history", return_value=_FAKE_HISTORY), \
                     patch.object(client, "_download_image", side_effect=self._fake_download):
                    result = client.run_scene_beats(self._make_pg(), "render_sim", tmpdir)

        self.assertTrue(result["simulation_only"])
        self.assertEqual(result["outbound_actions_taken"], 0)


# ---------------------------------------------------------------------------
# TestSafetyGuarantees
# ---------------------------------------------------------------------------

class TestSafetyGuarantees(unittest.TestCase):

    def test_negative_prompt_always_includes_safety_terms(self):
        """_SAFETY_NEGATIVE is always present in build_txt2img_workflow negative prompt."""
        client = cc.ComfyUIClient()
        pg = {
            "positive_prompt": "sunset over ocean",
            "negative_prompt": "blurry",
        }
        workflow = client.build_txt2img_workflow(pg)
        # Find CLIPTextEncode nodes
        clip_texts = [
            node["inputs"]["text"]
            for node in workflow.values()
            if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode"
        ]
        negative_text = " ".join(clip_texts)
        for safety_term in ("face", "likeness", "avatar"):
            self.assertIn(safety_term, negative_text,
                f"Safety term '{safety_term}' must be in workflow negative prompt")

    def test_faceless_suffix_applied_in_positive(self):
        """_FACELESS_SUFFIX must appear in the generated positive prompt."""
        result = cc._build_positive_text({
            "positive_prompt": "mountain sunrise",
            "visual_style": "cinematic",
        })
        self.assertIn("no faces", result,
            "_FACELESS_SUFFIX must be appended to positive prompt from _build_positive_text")

    def test_no_likeness_in_safety_negative(self):
        """_SAFETY_NEGATIVE must explicitly exclude recognizable likeness."""
        self.assertIn("recognizable likeness", cc._SAFETY_NEGATIVE)
        self.assertIn("identifiable person", cc._SAFETY_NEGATIVE)

    def test_no_avatar_in_safety_negative(self):
        self.assertIn("avatar", cc._SAFETY_NEGATIVE)

    def test_no_voice_cloning_in_safety_negative(self):
        self.assertIn("voice cloning", cc._SAFETY_NEGATIVE)


# ---------------------------------------------------------------------------
# TestWorkflowRealIntegration (with a temp file)
# ---------------------------------------------------------------------------

class TestWorkflowRealIntegration(unittest.TestCase):
    """Tests run_scene_beats with renderer_type=comfyui_real against a real temp workflow file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workflow_path = os.path.join(self.tmp.name, "test_workflow.json")
        with open(self.workflow_path, "w") as fh:
            json.dump(_make_workflow_with_markers(), fh)

    def tearDown(self):
        self.tmp.cleanup()

    def _fake_download(self, fname, subfolder, img_type, path):
        with open(path, "wb") as fh:
            fh.write(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
                b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01"
                b"\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
            )
        return path

    def test_real_workflow_mock_stores_output_files(self):
        """Successful mock real workflow results in output files stored on disk."""
        env_patch = {
            "COMFYUI_ENABLED": "true",
            "COMFYUI_RENDERER_TYPE": "comfyui_real",
            "COMFYUI_WORKFLOW_PATH": self.workflow_path,
            "COMFYUI_FALLBACK_ALLOWED": "false",
        }
        pg = {
            "_id": "render_real_01",
            "positive_prompt": "open sky, symbolic freedom",
            "negative_prompt": "ugly",
            "scene_beats": ["dawn over mountains", "light through trees"],
        }
        client = cc.ComfyUIClient()
        with patch.dict(os.environ, env_patch, clear=False), \
             tempfile.TemporaryDirectory() as out_dir:
            with patch.object(client, "_queue_prompt", return_value=_FAKE_SUBMIT_RESP), \
                 patch.object(client, "_get_history", return_value=_FAKE_HISTORY), \
                 patch.object(client, "_download_image", side_effect=self._fake_download):
                result = client.run_scene_beats(pg, "render_real_01", out_dir)

        self.assertEqual(result["renderer_type"], "comfyui_real")
        self.assertFalse(result["fallback_used"])
        self.assertEqual(len(result["output_image_paths"]), 2)

    def test_fallback_metadata_visible(self):
        """When fallback occurs, fallback_used=True and fallback_reason is populated."""
        env_patch = {
            "COMFYUI_ENABLED": "true",
            "COMFYUI_RENDERER_TYPE": "comfyui_real",
            "COMFYUI_WORKFLOW_PATH": "/nonexistent/path.json",  # bad path
            "COMFYUI_FALLBACK_ALLOWED": "true",
        }
        pg = {
            "_id": "render_fallback_01",
            "positive_prompt": "cinematic",
            "scene_beats": ["beat one"],
        }
        client = cc.ComfyUIClient()
        with patch.dict(os.environ, env_patch, clear=False), \
             tempfile.TemporaryDirectory() as out_dir:
            with patch.object(client, "_queue_prompt", return_value=_FAKE_SUBMIT_RESP), \
                 patch.object(client, "_get_history", return_value=_FAKE_HISTORY), \
                 patch.object(client, "_download_image", side_effect=self._fake_download):
                result = client.run_scene_beats(pg, "render_fallback_01", out_dir)

        self.assertTrue(result["fallback_used"],
            "fallback_used must be True when real workflow fails and fallback is allowed")
        self.assertNotEqual(result["fallback_reason"], "",
            "fallback_reason must be populated when fallback occurs")

    def test_original_audio_preserved(self):
        """Renderer must not modify source_audio_path on the prompt_generation."""
        pg = {
            "_id": "render_audio_01",
            "positive_prompt": "cinematic",
            "scene_beats": ["beat one"],
            "source_audio_path": "/data/audio/original.m4a",
            "preserve_original_audio": True,
        }
        client = cc.ComfyUIClient()
        env_patch = {"COMFYUI_RENDERER_TYPE": "comfyui_stub"}
        with patch.dict(os.environ, env_patch, clear=False), \
             tempfile.TemporaryDirectory() as out_dir:
            with patch.object(client, "_queue_prompt", return_value=_FAKE_SUBMIT_RESP), \
                 patch.object(client, "_get_history", return_value=_FAKE_HISTORY), \
                 patch.object(client, "_download_image", side_effect=self._fake_download):
                client.run_scene_beats(pg, "render_audio_01", out_dir)

        # pg must be unchanged
        self.assertEqual(pg["source_audio_path"], "/data/audio/original.m4a")
        self.assertTrue(pg["preserve_original_audio"])

    def test_no_external_publishing(self):
        """Renderer must not make HTTP calls to endpoints outside COMFYUI_BASE_URL."""
        from unittest.mock import call
        external_urls: list[str] = []

        def _spy_queue(workflow):
            # Record call — should only be to ComfyUI base
            return _FAKE_SUBMIT_RESP

        pg = {
            "_id": "render_no_pub",
            "positive_prompt": "abstract",
            "scene_beats": ["beat one"],
        }
        client = cc.ComfyUIClient()
        env_patch = {"COMFYUI_RENDERER_TYPE": "comfyui_stub"}
        with patch.dict(os.environ, env_patch, clear=False), \
             tempfile.TemporaryDirectory() as out_dir:
            with patch.object(client, "_queue_prompt", side_effect=_spy_queue), \
                 patch.object(client, "_get_history", return_value=_FAKE_HISTORY), \
                 patch.object(client, "_download_image", side_effect=self._fake_download), \
                 patch("urllib.request.urlopen") as mock_urlopen:
                client.run_scene_beats(pg, "render_no_pub", out_dir)
                # urllib.request.urlopen should NOT have been called with any external URL
                for call_args in mock_urlopen.call_args_list:
                    url = str(call_args[0][0])
                    self.assertTrue(
                        url.startswith(client.base_url),
                        f"External HTTP call detected to {url!r} — rendering must not publish externally",
                    )


if __name__ == "__main__":
    unittest.main()
