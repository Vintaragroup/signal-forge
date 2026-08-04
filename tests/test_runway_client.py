"""
tests/test_runway_client.py
Content ingestion pipeline — Runway image generation.
Pure-unit tests for services/api/runway_client.py. No `main` import, no
module stubbing — mirrors tests/test_trend_discovery_agent.py's pattern,
since runway_client.py (like tavily_client.py/instagram_client.py) is only
imported inline within worker.py functions, never at any module's top level.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

import runway_client  # noqa: E402
from runway_client import RunwayClient  # noqa: E402
from comfyui_client import _FACELESS_SUFFIX  # noqa: E402


def _mock_response(status_code=200, json_body=None, text="ok"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    resp.text = text
    resp.json.return_value = json_body or {}
    return resp


# ══════════════════════════════════════════════════════════════════════════════
# Utilities
# ══════════════════════════════════════════════════════════════════════════════

class TestUtilities:
    def test_redact_hides_key(self):
        assert runway_client._redact("abcdefgh1234") == "...1234"

    def test_redact_none_returns_placeholder(self):
        assert runway_client._redact(None) == "<none>"

    def test_backoff_increases_with_attempts(self):
        b0 = runway_client._backoff(0)
        b2 = runway_client._backoff(2)
        b4 = runway_client._backoff(4)
        assert b0 < b2 <= b4

    def test_backoff_capped_at_max(self):
        assert runway_client._backoff(100) == runway_client._MAX_BACKOFF_S

    def test_headers_include_auth_and_version(self):
        headers = runway_client._headers("test-key")
        assert headers["Authorization"] == "Bearer test-key"
        assert headers["X-Runway-Version"] == runway_client.RUNWAY_API_VERSION

    def test_exception_hierarchy(self):
        assert issubclass(runway_client.RunwayAuthError, runway_client.RunwayError)
        assert issubclass(runway_client.RunwayGenerationError, runway_client.RunwayError)
        assert issubclass(runway_client.RunwayTimeoutError, runway_client.RunwayGenerationError)
        assert issubclass(runway_client.RunwayRateLimitError, runway_client.RunwayGenerationError)


# ══════════════════════════════════════════════════════════════════════════════
# submit_text_to_image
# ══════════════════════════════════════════════════════════════════════════════

class TestSubmitTextToImage:
    def test_raises_auth_error_without_key(self):
        with pytest.raises(runway_client.RunwayAuthError):
            runway_client.submit_text_to_image("a prompt", api_key="")

    def test_success_returns_task_id(self):
        resp = _mock_response(200, {"id": "task_abc123"})
        with patch("runway_client.requests.post", return_value=resp) as mock_post:
            task_id = runway_client.submit_text_to_image("a prompt", api_key="test-key")
        assert task_id == "task_abc123"
        sent_headers = mock_post.call_args.kwargs["headers"]
        assert sent_headers["Authorization"] == "Bearer test-key"
        assert sent_headers["X-Runway-Version"] == runway_client.RUNWAY_API_VERSION

    def test_sends_model_and_ratio(self):
        resp = _mock_response(200, {"id": "task_1"})
        with patch("runway_client.requests.post", return_value=resp) as mock_post:
            runway_client.submit_text_to_image(
                "a prompt", api_key="test-key", model="custom-model", ratio="1:1"
            )
        body = mock_post.call_args.kwargs["json"]
        assert body["model"] == "custom-model"
        assert body["ratio"] == "1:1"
        assert body["promptText"] == "a prompt"

    def test_missing_id_raises_generation_error(self):
        resp = _mock_response(200, {})
        with patch("runway_client.requests.post", return_value=resp):
            with pytest.raises(runway_client.RunwayGenerationError):
                runway_client.submit_text_to_image("a prompt", api_key="test-key")

    def test_401_raises_auth_error(self):
        resp = _mock_response(401, text="unauthorized")
        with patch("runway_client.requests.post", return_value=resp):
            with pytest.raises(runway_client.RunwayAuthError):
                runway_client.submit_text_to_image("a prompt", api_key="bad-key")

    def test_key_never_appears_in_error(self):
        resp = _mock_response(500, text="server error")
        with patch("runway_client.requests.post", return_value=resp):
            with pytest.raises(runway_client.RunwayGenerationError) as exc_info:
                runway_client.submit_text_to_image("a prompt", api_key="super-secret-key")
        assert "super-secret-key" not in str(exc_info.value)


# ══════════════════════════════════════════════════════════════════════════════
# poll_task
# ══════════════════════════════════════════════════════════════════════════════

class TestPollTask:
    def test_raises_auth_error_without_key(self):
        with pytest.raises(runway_client.RunwayAuthError):
            runway_client.poll_task("task_1", api_key="")

    def test_returns_immediately_on_terminal_status(self):
        resp = _mock_response(200, {"id": "task_1", "status": "SUCCEEDED", "output": ["https://x/img.png"]})
        with patch("runway_client.requests.get", return_value=resp):
            task = runway_client.poll_task("task_1", api_key="test-key")
        assert task["status"] == "SUCCEEDED"

    def test_polls_until_terminal(self):
        pending = _mock_response(200, {"id": "task_1", "status": "RUNNING"})
        done = _mock_response(200, {"id": "task_1", "status": "SUCCEEDED", "output": ["https://x/img.png"]})
        with patch("runway_client.requests.get", side_effect=[pending, pending, done]):
            with patch("runway_client.time.sleep"):
                task = runway_client.poll_task("task_1", api_key="test-key", poll_interval_s=0)
        assert task["status"] == "SUCCEEDED"

    def test_timeout_raises(self):
        pending = _mock_response(200, {"id": "task_1", "status": "RUNNING"})
        with patch("runway_client.requests.get", return_value=pending):
            with patch("runway_client.time.sleep"):
                with pytest.raises(runway_client.RunwayTimeoutError):
                    runway_client.poll_task("task_1", api_key="test-key", timeout_s=0, poll_interval_s=0)

    def test_401_raises_auth_error(self):
        resp = _mock_response(401)
        with patch("runway_client.requests.get", return_value=resp):
            with pytest.raises(runway_client.RunwayAuthError):
                runway_client.poll_task("task_1", api_key="bad-key")


# ══════════════════════════════════════════════════════════════════════════════
# download_image
# ══════════════════════════════════════════════════════════════════════════════

class TestDownloadImage:
    def test_success_writes_file(self, tmp_path):
        resp = MagicMock()
        resp.ok = True
        resp.iter_content.return_value = [b"fake-image-bytes"]
        dest = str(tmp_path / "sub" / "out.png")
        with patch("runway_client.requests.get", return_value=resp):
            result = runway_client.download_image("https://x/img.png", dest)
        assert result == dest
        assert os.path.isfile(dest)
        with open(dest, "rb") as fh:
            assert fh.read() == b"fake-image-bytes"

    def test_failure_raises(self, tmp_path):
        resp = MagicMock()
        resp.ok = False
        resp.status_code = 404
        dest = str(tmp_path / "out.png")
        with patch("runway_client.requests.get", return_value=resp):
            with pytest.raises(runway_client.RunwayGenerationError):
                runway_client.download_image("https://x/missing.png", dest)


# ══════════════════════════════════════════════════════════════════════════════
# health_check
# ══════════════════════════════════════════════════════════════════════════════

class TestHealthCheck:
    def test_no_key_unreachable(self):
        result = runway_client.health_check(api_key="")
        assert result["reachable"] is False

    def test_401_unreachable(self):
        resp = _mock_response(401)
        with patch("runway_client.requests.get", return_value=resp):
            result = runway_client.health_check(api_key="bad-key")
        assert result["reachable"] is False

    def test_404_is_reachable(self):
        # A well-formed 404 (task not found) confirms key + host are valid.
        resp = _mock_response(404)
        with patch("runway_client.requests.get", return_value=resp):
            result = runway_client.health_check(api_key="test-key")
        assert result["reachable"] is True


# ══════════════════════════════════════════════════════════════════════════════
# RunwayClient.run_scene_beats — contract parity with ComfyUIClient
# ══════════════════════════════════════════════════════════════════════════════

class TestRunSceneBeats:
    _EXPECTED_KEYS = {
        "output_image_paths", "output_image_path", "prompt_ids", "errors",
        "renderer_type", "workflow_path", "model_name", "fallback_used",
        "fallback_reason", "simulation_only", "outbound_actions_taken",
    }

    def test_no_api_key_returns_fallback_shape_no_network_call(self, tmp_path):
        client = RunwayClient(api_key="")
        with patch("runway_client.requests.post") as mock_post, \
             patch("runway_client.requests.get") as mock_get:
            result = client.run_scene_beats({"scene_beats": ["a beat"]}, "render-1", str(tmp_path))
        mock_post.assert_not_called()
        mock_get.assert_not_called()
        assert result["fallback_used"] is True
        assert set(result.keys()) == self._EXPECTED_KEYS

    def test_return_shape_matches_comfyui_contract(self, tmp_path):
        submit_resp = _mock_response(200, {"id": "task_1"})
        poll_resp = _mock_response(200, {"id": "task_1", "status": "SUCCEEDED", "output": ["https://x/img.png"]})
        dl_resp = MagicMock(ok=True)
        dl_resp.iter_content.return_value = [b"bytes"]
        client = RunwayClient(api_key="test-key")
        with patch("runway_client.requests.post", return_value=submit_resp), \
             patch("runway_client.requests.get", side_effect=[poll_resp, dl_resp]):
            result = client.run_scene_beats({"scene_beats": ["a beat"]}, "render-1", str(tmp_path))
        assert set(result.keys()) == self._EXPECTED_KEYS
        assert result["simulation_only"] is True
        assert result["outbound_actions_taken"] == 0

    def test_scene_beats_produce_one_image_each(self, tmp_path):
        submit_resp = _mock_response(200, {"id": "task_1"})
        poll_resp = _mock_response(200, {"id": "task_1", "status": "SUCCEEDED", "output": ["https://x/img.png"]})
        dl_resp = MagicMock(ok=True)
        dl_resp.iter_content.return_value = [b"bytes"]
        client = RunwayClient(api_key="test-key")
        pg = {"scene_beats": ["beat one", "beat two"], "visual_style": "cinematic"}
        with patch("runway_client.requests.post", return_value=submit_resp), \
             patch("runway_client.requests.get", side_effect=[poll_resp, dl_resp, poll_resp, dl_resp]):
            result = client.run_scene_beats(pg, "render-2", str(tmp_path))
        assert len(result["output_image_paths"]) == 2
        assert result["fallback_used"] is False
        assert result["renderer_type"] == "runway_real"

    def test_scene_beat_prompt_includes_faceless_safety_suffix(self, tmp_path):
        submit_resp = _mock_response(200, {"id": "task_1"})
        poll_resp = _mock_response(200, {"id": "task_1", "status": "SUCCEEDED", "output": ["https://x/img.png"]})
        dl_resp = MagicMock(ok=True)
        dl_resp.iter_content.return_value = [b"bytes"]
        client = RunwayClient(api_key="test-key")
        with patch("runway_client.requests.post", return_value=submit_resp) as mock_post, \
             patch("runway_client.requests.get", side_effect=[poll_resp, dl_resp]):
            client.run_scene_beats({"scene_beats": ["a beat"]}, "render-3", str(tmp_path))
        sent_body = mock_post.call_args.kwargs["json"]
        assert _FACELESS_SUFFIX in sent_body["promptText"]

    def test_empty_scene_beats_falls_back_to_single_prompt(self, tmp_path):
        submit_resp = _mock_response(200, {"id": "task_1"})
        poll_resp = _mock_response(200, {"id": "task_1", "status": "SUCCEEDED", "output": ["https://x/img.png"]})
        dl_resp = MagicMock(ok=True)
        dl_resp.iter_content.return_value = [b"bytes"]
        client = RunwayClient(api_key="test-key")
        with patch("runway_client.requests.post", return_value=submit_resp), \
             patch("runway_client.requests.get", side_effect=[poll_resp, dl_resp]):
            result = client.run_scene_beats({"scene_beats": []}, "render-4", str(tmp_path))
        assert len(result["output_image_paths"]) == 1

    def test_beat_failure_recorded_not_crashed(self, tmp_path):
        client = RunwayClient(api_key="test-key")
        with patch("runway_client.requests.post", side_effect=runway_client.RunwayGenerationError("boom")):
            result = client.run_scene_beats({"scene_beats": ["a beat"]}, "render-5", str(tmp_path))
        assert result["output_image_paths"] == []
        assert result["fallback_used"] is True
        assert len(result["errors"]) == 1

    def test_task_failed_status_recorded_as_error(self, tmp_path):
        submit_resp = _mock_response(200, {"id": "task_1"})
        failed_resp = _mock_response(200, {"id": "task_1", "status": "FAILED"})
        client = RunwayClient(api_key="test-key")
        with patch("runway_client.requests.post", return_value=submit_resp), \
             patch("runway_client.requests.get", return_value=failed_resp):
            result = client.run_scene_beats({"scene_beats": ["a beat"]}, "render-6", str(tmp_path))
        assert result["output_image_paths"] == []
        assert any("FAILED" in e for e in result["errors"])
