"""
tests/test_instagram_publish.py
Pillar 2 — Instagram Publishing.
Mirrors tests/test_phase6x_linkedin_pilot.py's structure: instagram_client
unit tests, helpers, endpoints, telemetry, deployment smoke.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

import sys, os, types

# ── Stub heavy optional dependencies ─────────────────────────────────────────
for _mod in [
    "whisper", "yt_dlp", "core.constants", "prompt_generator", "snippet_scorer",
    "agents.base_agent", "agents.content_agent", "agents.fan_engagement_agent",
    "agents.followup_agent", "agents.outreach_agent", "agents.trend_discovery_agent",
    "media_folder_scanner", "approved_url_downloader",
]:
    _parts = _mod.split(".")
    if len(_parts) > 1:
        _parent = types.ModuleType(_parts[0])
        sys.modules.setdefault(_parts[0], _parent)
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

sys.modules["core.constants"].MESSAGE_REVIEW_DECISIONS = []
sys.modules["core.constants"].OPEN_DEAL_OUTCOMES = []
sys.modules["core.constants"].VALID_MODULES = []

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

import main
from main import app

client = TestClient(app, raise_server_exceptions=False)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _reset_state():
    main._runtime_state_6u.update({
        "total_requests": 0,
        "by_path": {},
        "worker_registry": {},
        "audit_log": [],
        "rate_buckets": {},
    })


def _approved_render(render_id="render-1"):
    return {"_id": render_id, "status": "approved", "file_path": "/tmp/signalforge_renders/render-1.mp4"}


_UNSET = object()  # sentinel distinguishing "not provided" from an explicit None


def _mock_db_ig(
    has_integration=False,
    access_token="tok_test",
    ig_user_id="ig_user_test",
    duplicate=False,
    attempt_doc=None,
    render_doc=_UNSET,
):
    db = MagicMock()
    db.command.return_value = {"ok": 1}

    # external_integrations
    integration_rec = None
    if has_integration:
        integration_rec = {
            "workspace_slug": "test-ws",
            "provider":       "instagram",
            "status":         "connected",
            "access_token":   access_token,
            "ig_user_id":     ig_user_id,
            "expires_at":     "2026-12-31T00:00:00+00:00",
            "connected_by":   "operator",
            "created_at":     "2026-08-04T00:00:00+00:00",
        }
    db.external_integrations.find_one.return_value = integration_rec
    db.external_integrations.update_one.return_value = MagicMock()

    # asset_renders
    db.asset_renders.find_one.return_value = _approved_render() if render_doc is _UNSET else render_doc

    # distribution_attempts
    dup_count = 1 if duplicate else 0
    db.distribution_attempts.count_documents.return_value = dup_count
    db.distribution_attempts.insert_one.return_value = MagicMock()
    db.distribution_attempts.update_one.return_value = MagicMock()
    db.distribution_attempts.find_one.return_value = attempt_doc
    db.distribution_attempts.find.return_value = iter([])

    # recommendation_signals / memory_proposals
    db.recommendation_signals.insert_one.return_value = MagicMock()
    db.memory_proposals.insert_one.return_value = MagicMock()

    db.__getitem__ = MagicMock(side_effect=lambda n: getattr(db, n, MagicMock()))
    return db


def _patch_ig(db):
    mc = MagicMock()
    mc.close = MagicMock()
    return patch.multiple("main", get_client=lambda: mc, get_database=lambda c: db)


def _make_attempt(status="pending", retry_count=0, verified=False, render_id="render-1"):
    return {
        "distribution_attempt_id": "da_test001",
        "workspace_slug":          "test-ws",
        "source_asset_render_id":  render_id,
        "provider":                "instagram",
        "status":                  status,
        "distribution_verification_status": status,
        "caption":                 "Test Instagram caption.",
        "media_url":               "https://example.com/render-1.jpg",
        "media_type":              "IMAGE",
        "external_post_id":        "ig_123" if verified else None,
        "published_url":           "https://www.instagram.com/p/ig_123/" if verified else None,
        "retry_count":             retry_count,
        "verified":                verified,
        "escalated":               False,
        "created_at":              "2026-08-04T00:00:00+00:00",
        "updated_at":              "2026-08-04T00:00:00+00:00",
        "metadata":                {},
    }


# ══════════════════════════════════════════════════════════════════════════════
# 1. instagram_client unit tests
# ══════════════════════════════════════════════════════════════════════════════

class TestInstagramClientUnit:
    def test_build_authorization_url_contains_client_id(self):
        import instagram_client
        orig = instagram_client.INSTAGRAM_CLIENT_ID
        instagram_client.INSTAGRAM_CLIENT_ID = "test_client_id"
        url = instagram_client.build_authorization_url("state123")
        assert "test_client_id" in url
        assert "state123" in url
        assert "facebook.com" in url
        instagram_client.INSTAGRAM_CLIENT_ID = orig

    def test_redact_hides_token(self):
        import instagram_client
        redacted = instagram_client._redact("abcdefghij1234")
        assert "1234" in redacted
        assert "abcdefghij" not in redacted

    def test_redact_none_returns_placeholder(self):
        import instagram_client
        assert instagram_client._redact(None) == "<none>"

    def test_backoff_increases_with_attempts(self):
        import instagram_client
        b0 = instagram_client._backoff(0)
        b2 = instagram_client._backoff(2)
        b4 = instagram_client._backoff(4)
        assert b0 < b2 <= b4

    def test_backoff_capped_at_max(self):
        import instagram_client
        b = instagram_client._backoff(100)
        assert b == instagram_client._MAX_BACKOFF_S

    def test_exception_hierarchy(self):
        import instagram_client
        assert issubclass(instagram_client.InstagramAuthError, instagram_client.InstagramError)
        assert issubclass(instagram_client.InstagramTokenExpiredError, instagram_client.InstagramAuthError)
        assert issubclass(instagram_client.InstagramPublishError, instagram_client.InstagramError)
        assert issubclass(instagram_client.InstagramRateLimitError, instagram_client.InstagramPublishError)

    def test_validate_token_response_raises_on_missing_token(self):
        import instagram_client
        with pytest.raises(instagram_client.InstagramAuthError):
            instagram_client._validate_token_response({"error": "oops"})

    def test_validate_token_response_passes_with_token(self):
        import instagram_client
        instagram_client._validate_token_response({"access_token": "tok123"})  # no exception

    def test_create_media_container_image_uses_image_url(self):
        import instagram_client
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "ok"
        resp.json.return_value = {"id": "container123"}
        with patch("instagram_client.requests.post", return_value=resp) as mock_post:
            result = instagram_client.create_media_container(
                "tok", "ig_user", "https://example.com/a.jpg", "caption", "IMAGE"
            )
        assert result["creation_id"] == "container123"
        sent_params = mock_post.call_args.kwargs["params"]
        assert sent_params["image_url"] == "https://example.com/a.jpg"
        assert "video_url" not in sent_params

    def test_create_media_container_reels_uses_video_url(self):
        import instagram_client
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "ok"
        resp.json.return_value = {"id": "container456"}
        with patch("instagram_client.requests.post", return_value=resp) as mock_post:
            instagram_client.create_media_container(
                "tok", "ig_user", "https://example.com/a.mp4", "caption", "REELS"
            )
        sent_params = mock_post.call_args.kwargs["params"]
        assert sent_params["video_url"] == "https://example.com/a.mp4"
        assert sent_params["media_type"] == "REELS"


# ══════════════════════════════════════════════════════════════════════════════
# 2. Simulate publish helper tests
# ══════════════════════════════════════════════════════════════════════════════

class TestSimulatePublish:
    def test_simulate_returns_post_id(self):
        result = main._simulate_instagram_publish_ig("render-1")
        assert result["external_post_id"]
        assert result["external_post_id"].startswith("ig_")

    def test_simulate_returns_url(self):
        result = main._simulate_instagram_publish_ig("render-1")
        assert "instagram.com" in result["published_url"]

    def test_simulate_marks_simulated_flag(self):
        result = main._simulate_instagram_publish_ig("render-1")
        assert result["_simulated"] is True

    def test_simulate_deterministic_for_same_key(self):
        r1 = main._simulate_instagram_publish_ig("same-render")
        r2 = main._simulate_instagram_publish_ig("same-render")
        assert r1["external_post_id"] == r2["external_post_id"]


# ══════════════════════════════════════════════════════════════════════════════
# 3. Duplicate publish prevention tests
# ══════════════════════════════════════════════════════════════════════════════

class TestDuplicatePublish:
    def test_duplicate_check_true_when_verified_exists(self):
        db = _mock_db_ig(duplicate=True)
        assert main._check_duplicate_publish_ig(db, "render-dup") is True

    def test_duplicate_check_false_when_none(self):
        db = _mock_db_ig(duplicate=False)
        assert main._check_duplicate_publish_ig(db, "render-new") is False

    def test_duplicate_check_db_failure_returns_false(self):
        db = MagicMock()
        db.distribution_attempts.count_documents.side_effect = Exception("DB down")
        assert main._check_duplicate_publish_ig(db, "render-x") is False


# ══════════════════════════════════════════════════════════════════════════════
# 4. Distribution attempt lifecycle tests
# ══════════════════════════════════════════════════════════════════════════════

class TestDistributionAttempt:
    def setup_method(self):
        _reset_state()

    def test_create_attempt_returns_dict(self):
        db = _mock_db_ig()
        result = main._create_distribution_attempt_ig(
            db, "ws1", "render-1", "caption", "https://example.com/a.jpg", "IMAGE"
        )
        assert isinstance(result, dict)
        assert result["status"] == "pending"
        assert result["provider"] == "instagram"

    def test_create_attempt_has_attempt_id(self):
        db = _mock_db_ig()
        result = main._create_distribution_attempt_ig(
            db, "ws1", "render-1", "caption", "https://example.com/a.jpg", "IMAGE"
        )
        assert result["distribution_attempt_id"].startswith("da_")

    def test_create_attempt_writes_audit(self):
        _reset_state()
        db = _mock_db_ig()
        main._create_distribution_attempt_ig(
            db, "ws1", "render-audit", "caption", "https://example.com/a.jpg", "IMAGE"
        )
        assert any(e["action"] == "distribution_attempt_created"
                   for e in main._runtime_state_6u["audit_log"])

    def test_execute_publish_simulation_returns_verified(self):
        db = _mock_db_ig(has_integration=False)
        attempt = _make_attempt()
        result = main._execute_instagram_publish_ig(db, "test-ws", attempt)
        assert result["status"] == "verified"
        assert result["verified"] is True

    def test_execute_publish_sets_post_id(self):
        db = _mock_db_ig(has_integration=False)
        attempt = _make_attempt()
        result = main._execute_instagram_publish_ig(db, "test-ws", attempt)
        assert result["external_post_id"]

    def test_execute_publish_sets_published_url(self):
        db = _mock_db_ig(has_integration=False)
        attempt = _make_attempt()
        result = main._execute_instagram_publish_ig(db, "test-ws", attempt)
        assert "instagram.com" in result["published_url"]

    def test_execute_publish_writes_audit_entry(self):
        _reset_state()
        db = _mock_db_ig(has_integration=False)
        attempt = _make_attempt()
        main._execute_instagram_publish_ig(db, "test-ws", attempt)
        assert any(e["action"] == "distribution_published"
                   for e in main._runtime_state_6u["audit_log"])

    def test_execute_publish_inserts_recommendation_signal(self):
        db = _mock_db_ig(has_integration=False)
        attempt = _make_attempt()
        main._execute_instagram_publish_ig(db, "test-ws", attempt)
        db.recommendation_signals.insert_one.assert_called()

    def test_execute_publish_inserts_memory_proposal(self):
        db = _mock_db_ig(has_integration=False)
        attempt = _make_attempt()
        main._execute_instagram_publish_ig(db, "test-ws", attempt)
        db.memory_proposals.insert_one.assert_called()

    def test_execute_publish_without_ig_user_id_falls_back_to_simulation(self):
        # access_token present but ig_user_id missing/empty -> still simulated
        db = _mock_db_ig(has_integration=True, ig_user_id="")
        attempt = _make_attempt()
        result = main._execute_instagram_publish_ig(db, "test-ws", attempt)
        assert result["verified"] is True
        assert result["metadata"]["raw_response"]["_simulated"] is True


# ══════════════════════════════════════════════════════════════════════════════
# 5. Telemetry helper tests
# ══════════════════════════════════════════════════════════════════════════════

class TestDistributionTelemetry:
    def test_telemetry_returns_totals(self):
        db = _mock_db_ig()
        db.distribution_attempts.count_documents.return_value = 0
        result = main._build_instagram_distribution_telemetry_ig(db, "test-ws")
        for key in ["total", "verified", "failed", "retrying"]:
            assert key in result

    def test_telemetry_db_failure_returns_safe_defaults(self):
        db = MagicMock()
        db.distribution_attempts.count_documents.side_effect = Exception("DB down")
        result = main._build_instagram_distribution_telemetry_ig(db, "test-ws")
        assert result["total"] == 0

    def test_linkedin_telemetry_now_includes_instagram_channel(self):
        # main._build_distribution_telemetry_6x should now report both channels
        db = _mock_db_ig()
        db.distribution_attempts.count_documents.return_value = 0
        result = main._build_distribution_telemetry_6x(db, "test-ws")
        assert "instagram" in result["channels"]
        assert "linkedin" in result["channels"]


# ══════════════════════════════════════════════════════════════════════════════
# 6. Connection status endpoint
# ══════════════════════════════════════════════════════════════════════════════

class TestInstagramStatusEndpoint:
    def test_status_not_connected_when_no_integration(self):
        db = _mock_db_ig(has_integration=False)
        with _patch_ig(db):
            r = client.get("/connect/instagram/status?workspace_slug=test-ws")
        assert r.status_code == 200
        assert r.json()["connected"] is False

    def test_status_connected_when_integration_exists(self):
        db = _mock_db_ig(has_integration=True)
        with _patch_ig(db):
            r = client.get("/connect/instagram/status?workspace_slug=test-ws")
        assert r.status_code == 200
        assert r.json()["connected"] is True

    def test_status_never_exposes_access_token(self):
        db = _mock_db_ig(has_integration=True, access_token="super-secret-token")
        with _patch_ig(db):
            r = client.get("/connect/instagram/status?workspace_slug=test-ws")
        assert "super-secret-token" not in r.text


# ══════════════════════════════════════════════════════════════════════════════
# 7. OAuth start endpoint
# ══════════════════════════════════════════════════════════════════════════════

class TestInstagramOAuthStart:
    def setup_method(self):
        _reset_state()

    def test_oauth_start_returns_200(self):
        db = _mock_db_ig()
        with _patch_ig(db):
            r = client.post("/connect/instagram/start?workspace_slug=test-ws")
        assert r.status_code == 200

    def test_oauth_start_returns_state(self):
        db = _mock_db_ig()
        with _patch_ig(db):
            r = client.post("/connect/instagram/start?workspace_slug=test-ws")
        assert "state" in r.json()
        assert len(r.json()["state"]) == 32

    def test_oauth_start_returns_auth_url(self):
        db = _mock_db_ig()
        with _patch_ig(db):
            r = client.post("/connect/instagram/start?workspace_slug=test-ws")
        assert "authorization_url" in r.json()

    def test_oauth_start_writes_audit(self):
        _reset_state()
        db = _mock_db_ig()
        with _patch_ig(db):
            client.post("/connect/instagram/start?workspace_slug=test-ws")
        assert any(e["action"] == "instagram_oauth_started"
                   for e in main._runtime_state_6u["audit_log"])


# ══════════════════════════════════════════════════════════════════════════════
# 8. OAuth callback endpoint
# ══════════════════════════════════════════════════════════════════════════════

class TestInstagramOAuthCallback:
    def setup_method(self):
        _reset_state()

    def test_callback_state_match_connects(self):
        db = _mock_db_ig(has_integration=True)
        db.external_integrations.find_one.return_value = {
            "oauth_state": "match_state", "status": "pending_oauth"
        }
        with _patch_ig(db):
            r = client.get("/connect/instagram/callback?code=code123&state=match_state&workspace_slug=test-ws")
        assert r.status_code == 200
        assert r.json()["status"] == "connected"

    def test_callback_state_mismatch_returns_400(self):
        db = _mock_db_ig(has_integration=True)
        db.external_integrations.find_one.return_value = {
            "oauth_state": "stored_state_xyz", "status": "pending_oauth"
        }
        with _patch_ig(db):
            r = client.get("/connect/instagram/callback?code=code123&state=wrong_state&workspace_slug=test-ws")
        assert r.status_code == 400

    def test_callback_simulated_when_no_client_id(self):
        db = _mock_db_ig(has_integration=False)
        db.external_integrations.find_one.return_value = None
        with _patch_ig(db):
            r = client.get("/connect/instagram/callback?code=code123&state=s1&workspace_slug=test-ws")
        assert r.status_code == 200
        assert r.json()["simulated"] is True


# ══════════════════════════════════════════════════════════════════════════════
# 9. Publish endpoint
# ══════════════════════════════════════════════════════════════════════════════

class TestInstagramPublishEndpoint:
    def setup_method(self):
        _reset_state()

    def _publish_body(self, **overrides):
        body = {
            "workspace_slug": "test-ws",
            "source_asset_render_id": "render-new-1",
            "caption": "Hello from SignalForge!",
            "media_url": "https://example.com/render.jpg",
            "media_type": "IMAGE",
        }
        body.update(overrides)
        return body

    def test_publish_returns_200(self):
        db = _mock_db_ig(has_integration=False, duplicate=False)
        with _patch_ig(db):
            r = client.post("/distribution/instagram/publish", json=self._publish_body())
        assert r.status_code == 200

    def test_publish_returns_verified_status(self):
        db = _mock_db_ig(has_integration=False, duplicate=False)
        with _patch_ig(db):
            r = client.post("/distribution/instagram/publish", json=self._publish_body())
        assert r.json()["status"] == "verified"

    def test_publish_duplicate_returns_409(self):
        db = _mock_db_ig(has_integration=False, duplicate=True)
        with _patch_ig(db):
            r = client.post("/distribution/instagram/publish", json=self._publish_body())
        assert r.status_code == 409

    def test_publish_response_has_post_id(self):
        db = _mock_db_ig(has_integration=False, duplicate=False)
        with _patch_ig(db):
            r = client.post("/distribution/instagram/publish", json=self._publish_body())
        assert r.json().get("external_post_id")

    def test_publish_missing_render_returns_404(self):
        db = _mock_db_ig(has_integration=False, duplicate=False, render_doc=None)
        with _patch_ig(db):
            r = client.post("/distribution/instagram/publish", json=self._publish_body())
        assert r.status_code == 404

    def test_publish_unapproved_render_returns_422(self):
        db = _mock_db_ig(has_integration=False, duplicate=False,
                          render_doc={"_id": "render-new-1", "status": "needs_review"})
        with _patch_ig(db):
            r = client.post("/distribution/instagram/publish", json=self._publish_body())
        assert r.status_code == 422

    def test_publish_requires_media_url_field(self):
        db = _mock_db_ig(has_integration=False, duplicate=False)
        body = self._publish_body()
        del body["media_url"]
        with _patch_ig(db):
            r = client.post("/distribution/instagram/publish", json=body)
        assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# 10. Retry endpoint
# ══════════════════════════════════════════════════════════════════════════════

class TestInstagramRetryEndpoint:
    def setup_method(self):
        _reset_state()

    def test_retry_failed_attempt_returns_200(self):
        attempt = _make_attempt(status="failed", retry_count=0)
        db = _mock_db_ig(attempt_doc=attempt)
        with _patch_ig(db):
            r = client.post("/distribution/instagram/retry?attempt_id=da_test001",
                            json={"workspace_slug": "test-ws"})
        assert r.status_code == 200

    def test_retry_nonexistent_attempt_returns_404(self):
        db = _mock_db_ig()
        db.distribution_attempts.find_one.return_value = None
        with _patch_ig(db):
            r = client.post("/distribution/instagram/retry?attempt_id=nonexistent",
                            json={"workspace_slug": "test-ws"})
        assert r.status_code == 404

    def test_retry_verified_attempt_returns_400(self):
        attempt = _make_attempt(status="verified", verified=True)
        db = _mock_db_ig(attempt_doc=attempt)
        with _patch_ig(db):
            r = client.post("/distribution/instagram/retry?attempt_id=da_test001",
                            json={"workspace_slug": "test-ws"})
        assert r.status_code == 400

    def test_retry_over_limit_escalates(self):
        attempt = _make_attempt(status="failed",
                                retry_count=main._PUBLISH_RETRY_LIMITS_6X["network_failure"])
        db = _mock_db_ig(attempt_doc=attempt)
        with _patch_ig(db):
            r = client.post("/distribution/instagram/retry?attempt_id=da_test001",
                            json={"workspace_slug": "test-ws"})
        assert r.status_code == 200
        assert r.json()["status"] == "escalated"


# ══════════════════════════════════════════════════════════════════════════════
# 11. Attempt status endpoint
# ══════════════════════════════════════════════════════════════════════════════

class TestInstagramAttemptStatusEndpoint:
    def test_status_returns_attempt(self):
        attempt = _make_attempt(status="verified", verified=True)
        db = _mock_db_ig(attempt_doc=attempt)
        with _patch_ig(db):
            r = client.get("/distribution/instagram/da_test001/status")
        assert r.status_code == 200
        assert r.json()["status"] == "verified"

    def test_status_missing_returns_404(self):
        db = _mock_db_ig()
        db.distribution_attempts.find_one.return_value = None
        with _patch_ig(db):
            r = client.get("/distribution/instagram/da_missing/status")
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 12. Publishing-limit endpoint
# ══════════════════════════════════════════════════════════════════════════════

class TestInstagramPublishingLimitEndpoint:
    def test_limit_simulated_when_not_configured(self):
        db = _mock_db_ig(has_integration=False)
        with _patch_ig(db):
            r = client.get("/distribution/instagram/limit?workspace_slug=test-ws")
        assert r.status_code == 200
        assert r.json()["simulated"] is True

    def test_limit_returns_quota_usage_key(self):
        db = _mock_db_ig(has_integration=False)
        with _patch_ig(db):
            r = client.get("/distribution/instagram/limit?workspace_slug=test-ws")
        assert "quota_usage" in r.json()


# ══════════════════════════════════════════════════════════════════════════════
# 13. Telemetry endpoint
# ══════════════════════════════════════════════════════════════════════════════

class TestInstagramTelemetryEndpoint:
    def test_telemetry_returns_200(self):
        db = _mock_db_ig()
        db.distribution_attempts.count_documents.return_value = 0
        with _patch_ig(db):
            r = client.get("/distribution/instagram/telemetry")
        assert r.status_code == 200

    def test_telemetry_has_total(self):
        db = _mock_db_ig()
        db.distribution_attempts.count_documents.return_value = 0
        with _patch_ig(db):
            r = client.get("/distribution/instagram/telemetry")
        assert "total" in r.json()


# ══════════════════════════════════════════════════════════════════════════════
# 14. Deployment smoke — all new endpoints respond
# ══════════════════════════════════════════════════════════════════════════════

class TestDeploymentSmoke:
    def setup_method(self):
        _reset_state()

    def test_all_instagram_endpoints_respond(self):
        db = _mock_db_ig(has_integration=True)
        attempt = _make_attempt(status="failed", retry_count=0)
        db.distribution_attempts.find_one.return_value = attempt
        db.distribution_attempts.count_documents.return_value = 0
        with _patch_ig(db):
            checks = [
                ("GET",  "/connect/instagram/status?workspace_slug=ws",     None),
                ("POST", "/connect/instagram/start?workspace_slug=ws",       {}),
                ("GET",  "/connect/instagram/callback?code=c&state=s&workspace_slug=ws", None),
                ("POST", "/distribution/instagram/publish",
                 {"workspace_slug": "ws", "source_asset_render_id": "render-1",
                  "caption": "Hi", "media_url": "https://example.com/a.jpg", "media_type": "IMAGE"}),
                ("GET",  "/distribution/instagram/da_test001/status",       None),
                ("GET",  "/distribution/instagram/limit?workspace_slug=ws", None),
                ("GET",  "/distribution/instagram/telemetry",               None),
                ("GET",  "/external-executions",                            None),
            ]
            for method, path, body in checks:
                r = client.get(path) if method == "GET" else client.post(path, json=body or {})
                assert r.status_code in (200, 201, 409), (
                    f"{method} {path} → {r.status_code}: {r.text[:200]}"
                )

    def test_instagram_endpoints_in_openapi(self):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        paths = r.json()["paths"]
        assert "/connect/instagram/status" in paths
        assert "/distribution/instagram/publish" in paths
        assert "/distribution/instagram/limit" in paths
        assert "/distribution/instagram/telemetry" in paths
