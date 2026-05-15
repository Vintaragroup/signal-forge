"""
tests/test_phase6x_linkedin_pilot.py
Phase 6X — First Live External Workflow Execution (LinkedIn Pilot)
56 tests: linkedin_client unit, helpers, endpoints, telemetry, audit trail.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from fastapi.testclient import TestClient

import sys, os, types, hashlib

# ── Stub heavy optional dependencies ─────────────────────────────────────────
for _mod in [
    "whisper", "yt_dlp", "core.constants", "prompt_generator", "snippet_scorer",
    "agents.base_agent", "agents.content_agent", "agents.fan_engagement_agent",
    "agents.followup_agent", "agents.outreach_agent",
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


def _mock_db_6x(
    has_integration=False,
    access_token="tok_test",
    duplicate=False,
    attempt_doc=None,
):
    db = MagicMock()
    db.command.return_value = {"ok": 1}

    # external_integrations
    integration_rec = None
    if has_integration:
        integration_rec = {
            "workspace_slug": "test-ws",
            "provider":       "linkedin",
            "status":         "connected",
            "access_token":   access_token,
            "refresh_token":  "rt_test",
            "expires_at":     "2026-12-31T00:00:00+00:00",
            "author_urn":     "urn:li:person:test123",
            "connected_by":   "operator",
            "created_at":     "2026-05-13T00:00:00+00:00",
        }
    db.external_integrations.find_one.return_value = integration_rec
    db.external_integrations.update_one.return_value = MagicMock()

    # distribution_attempts
    dup_count = 1 if duplicate else 0
    db.distribution_attempts.count_documents.return_value = dup_count
    db.distribution_attempts.insert_one.return_value = MagicMock()
    db.distribution_attempts.update_one.return_value = MagicMock()
    if attempt_doc:
        db.distribution_attempts.find_one.return_value = attempt_doc
    else:
        db.distribution_attempts.find_one.return_value = None
    db.distribution_attempts.find.return_value = iter([])

    # recommendation_signals / memory_proposals
    db.recommendation_signals.insert_one.return_value = MagicMock()
    db.memory_proposals.insert_one.return_value = MagicMock()

    db.__getitem__ = MagicMock(side_effect=lambda n: getattr(db, n, MagicMock()))
    return db


def _patch_6x(db):
    mc = MagicMock()
    mc.close = MagicMock()
    return patch.multiple("main", get_client=lambda: mc, get_database=lambda c: db)


def _make_attempt(status="pending", retry_count=0, verified=False, asset_id="asset-1"):
    return {
        "distribution_attempt_id": "da_test001",
        "workspace_slug":          "test-ws",
        "workflow_asset_id":       asset_id,
        "provider":                "linkedin",
        "status":                  status,
        "distribution_verification_status": status,
        "content_text":            "Test LinkedIn post content.",
        "external_post_id":        "urn:li:share:123" if verified else None,
        "published_url":           "https://www.linkedin.com/feed/update/urn:li:share:123" if verified else None,
        "request_trace_id":        "trace-001" if verified else None,
        "retry_count":             retry_count,
        "verified":                verified,
        "escalated":               False,
        "created_at":              "2026-05-13T00:00:00+00:00",
        "updated_at":              "2026-05-13T00:00:00+00:00",
        "metadata":                {},
    }


# =============================================================================
# 1. linkedin_client unit tests
# =============================================================================
class TestLinkedInClientUnit6X:
    def test_01_build_authorization_url_contains_client_id(self):
        import linkedin_client
        orig = linkedin_client.LINKEDIN_CLIENT_ID
        linkedin_client.LINKEDIN_CLIENT_ID = "test_client_id"
        url = linkedin_client.build_authorization_url("state123")
        assert "test_client_id" in url
        assert "state123" in url
        assert "linkedin.com" in url
        linkedin_client.LINKEDIN_CLIENT_ID = orig

    def test_02_redact_hides_token(self):
        import linkedin_client
        redacted = linkedin_client._redact("abcdefghij1234")
        assert "1234" in redacted
        assert "abcdefghij" not in redacted

    def test_03_redact_none_returns_placeholder(self):
        import linkedin_client
        assert linkedin_client._redact(None) == "<none>"

    def test_04_hash_idempotency_key_deterministic(self):
        import linkedin_client
        k1 = linkedin_client._hash_idempotency_key("workspace:asset-1")
        k2 = linkedin_client._hash_idempotency_key("workspace:asset-1")
        assert k1 == k2

    def test_05_hash_idempotency_key_different_keys(self):
        import linkedin_client
        k1 = linkedin_client._hash_idempotency_key("workspace:asset-1")
        k2 = linkedin_client._hash_idempotency_key("workspace:asset-2")
        assert k1 != k2

    def test_06_backoff_increases_with_attempts(self):
        import linkedin_client
        b0 = linkedin_client._backoff(0)
        b2 = linkedin_client._backoff(2)
        b4 = linkedin_client._backoff(4)
        assert b0 < b2 <= b4

    def test_07_backoff_capped_at_max(self):
        import linkedin_client
        b = linkedin_client._backoff(100)
        assert b == linkedin_client._MAX_BACKOFF_S

    def test_08_exception_hierarchy(self):
        import linkedin_client
        assert issubclass(linkedin_client.LinkedInAuthError,      linkedin_client.LinkedInError)
        assert issubclass(linkedin_client.LinkedInTokenExpiredError, linkedin_client.LinkedInAuthError)
        assert issubclass(linkedin_client.LinkedInPublishError,    linkedin_client.LinkedInError)
        assert issubclass(linkedin_client.LinkedInDuplicateError,  linkedin_client.LinkedInPublishError)
        assert issubclass(linkedin_client.LinkedInNotFoundError,   linkedin_client.LinkedInPublishError)

    def test_09_validate_token_response_raises_on_missing_token(self):
        import linkedin_client
        with pytest.raises(linkedin_client.LinkedInAuthError):
            linkedin_client._validate_token_response({"error": "oops"})

    def test_10_validate_token_response_passes_with_token(self):
        import linkedin_client
        linkedin_client._validate_token_response({"access_token": "tok123"})  # no exception


# =============================================================================
# 2. Simulate publish helper tests
# =============================================================================
class TestSimulatePublish6X:
    def test_11_simulate_returns_post_id(self):
        result = main._simulate_linkedin_publish_6x("Hello world", "urn:li:person:x", "key1")
        assert result["external_post_id"]
        assert "urn:li:share:" in result["external_post_id"]

    def test_12_simulate_returns_url(self):
        result = main._simulate_linkedin_publish_6x("Hello", "urn:li:person:x", "key1")
        assert "linkedin.com" in result["published_url"]

    def test_13_simulate_marks_simulated_flag(self):
        result = main._simulate_linkedin_publish_6x("Hello", "urn:li:person:x", "key1")
        assert result["_simulated"] is True

    def test_14_simulate_deterministic_for_same_key(self):
        r1 = main._simulate_linkedin_publish_6x("Hello", "urn:li:person:x", "same_key")
        r2 = main._simulate_linkedin_publish_6x("Hello", "urn:li:person:x", "same_key")
        assert r1["external_post_id"] == r2["external_post_id"]


# =============================================================================
# 3. Duplicate publish prevention tests
# =============================================================================
class TestDuplicatePublish6X:
    def test_15_duplicate_check_true_when_verified_exists(self):
        db = _mock_db_6x(duplicate=True)
        assert main._check_duplicate_publish_6x(db, "asset-dup") is True

    def test_16_duplicate_check_false_when_none(self):
        db = _mock_db_6x(duplicate=False)
        assert main._check_duplicate_publish_6x(db, "asset-new") is False

    def test_17_duplicate_check_db_failure_returns_false(self):
        db = MagicMock()
        db.distribution_attempts.count_documents.side_effect = Exception("DB down")
        result = main._check_duplicate_publish_6x(db, "asset-x")
        assert result is False


# =============================================================================
# 4. Distribution attempt lifecycle tests
# =============================================================================
class TestDistributionAttempt6X:
    def setup_method(self):
        _reset_state()

    def test_18_create_attempt_returns_dict(self):
        db = _mock_db_6x()
        result = main._create_distribution_attempt_6x(db, "ws1", "asset-1", "Post text")
        assert isinstance(result, dict)
        assert result["status"] == "pending"
        assert result["provider"] == "linkedin"

    def test_19_create_attempt_has_attempt_id(self):
        db = _mock_db_6x()
        result = main._create_distribution_attempt_6x(db, "ws1", "asset-1", "Post text")
        assert result["distribution_attempt_id"].startswith("da_")

    def test_20_create_attempt_writes_audit(self):
        _reset_state()
        db = _mock_db_6x()
        main._create_distribution_attempt_6x(db, "ws1", "asset-audit", "Post")
        assert any(e["action"] == "distribution_attempt_created"
                   for e in main._runtime_state_6u["audit_log"])

    def test_21_execute_publish_simulation_returns_verified(self):
        db = _mock_db_6x(has_integration=False)
        attempt = _make_attempt()
        result = main._execute_linkedin_publish_6x(db, "test-ws", attempt)
        assert result["status"] == "verified"
        assert result["verified"] is True

    def test_22_execute_publish_sets_post_id(self):
        db = _mock_db_6x(has_integration=False)
        attempt = _make_attempt()
        result = main._execute_linkedin_publish_6x(db, "test-ws", attempt)
        assert result["external_post_id"]

    def test_23_execute_publish_sets_published_url(self):
        db = _mock_db_6x(has_integration=False)
        attempt = _make_attempt()
        result = main._execute_linkedin_publish_6x(db, "test-ws", attempt)
        assert "linkedin.com" in result["published_url"]

    def test_24_execute_publish_writes_audit_entry(self):
        _reset_state()
        db = _mock_db_6x(has_integration=False)
        attempt = _make_attempt()
        main._execute_linkedin_publish_6x(db, "test-ws", attempt)
        assert any(e["action"] == "distribution_published"
                   for e in main._runtime_state_6u["audit_log"])

    def test_25_execute_publish_inserts_recommendation_signal(self):
        db = _mock_db_6x(has_integration=False)
        attempt = _make_attempt()
        main._execute_linkedin_publish_6x(db, "test-ws", attempt)
        db.recommendation_signals.insert_one.assert_called()

    def test_26_execute_publish_inserts_memory_proposal(self):
        db = _mock_db_6x(has_integration=False)
        attempt = _make_attempt()
        main._execute_linkedin_publish_6x(db, "test-ws", attempt)
        db.memory_proposals.insert_one.assert_called()


# =============================================================================
# 5. Telemetry helper tests
# =============================================================================
class TestDistributionTelemetry6X:
    def test_27_telemetry_returns_all_keys(self):
        db = _mock_db_6x()
        db.distribution_attempts.count_documents.return_value = 0
        result = main._build_distribution_telemetry_6x(db, "test-ws")
        for key in ["publish_success_rate", "retry_frequency",
                    "verification_failures", "totals", "channels"]:
            assert key in result

    def test_28_telemetry_success_rate_zero_when_no_attempts(self):
        db = _mock_db_6x()
        db.distribution_attempts.count_documents.return_value = 0
        result = main._build_distribution_telemetry_6x(db, "test-ws")
        assert result["publish_success_rate"] == 0.0

    def test_29_telemetry_db_failure_returns_safe_defaults(self):
        db = MagicMock()
        db.distribution_attempts.count_documents.side_effect = Exception("DB down")
        result = main._build_distribution_telemetry_6x(db, "test-ws")
        assert result["publish_success_rate"] == 0.0

    def test_30_telemetry_has_evaluated_at(self):
        db = _mock_db_6x()
        db.distribution_attempts.count_documents.return_value = 0
        result = main._build_distribution_telemetry_6x(db, None)
        assert "evaluated_at" in result


# =============================================================================
# 6. LinkedIn connection status endpoint
# =============================================================================
class TestLinkedInStatusEndpoint6X:
    def test_31_status_not_connected_when_no_integration(self):
        db = _mock_db_6x(has_integration=False)
        with _patch_6x(db):
            r = client.get("/connect/linkedin/status?workspace_slug=test-ws")
        assert r.status_code == 200
        assert r.json()["connected"] is False

    def test_32_status_connected_when_integration_exists(self):
        db = _mock_db_6x(has_integration=True)
        with _patch_6x(db):
            r = client.get("/connect/linkedin/status?workspace_slug=test-ws")
        assert r.status_code == 200
        assert r.json()["connected"] is True

    def test_33_status_never_exposes_access_token(self):
        db = _mock_db_6x(has_integration=True)
        with _patch_6x(db):
            r = client.get("/connect/linkedin/status?workspace_slug=test-ws")
        body = r.json()
        assert "access_token" not in body
        assert "refresh_token" not in body


# =============================================================================
# 7. OAuth start endpoint
# =============================================================================
class TestLinkedInOAuthStart6X:
    def setup_method(self):
        _reset_state()

    def test_34_oauth_start_returns_200(self):
        db = _mock_db_6x()
        with _patch_6x(db):
            r = client.post("/connect/linkedin/start?workspace_slug=test-ws")
        assert r.status_code == 200

    def test_35_oauth_start_returns_state(self):
        db = _mock_db_6x()
        with _patch_6x(db):
            r = client.post("/connect/linkedin/start?workspace_slug=test-ws")
        assert "state" in r.json()
        assert len(r.json()["state"]) == 32  # 16-byte hex = 32 chars

    def test_36_oauth_start_returns_auth_url(self):
        db = _mock_db_6x()
        with _patch_6x(db):
            r = client.post("/connect/linkedin/start?workspace_slug=test-ws")
        assert "authorization_url" in r.json()

    def test_37_oauth_start_writes_audit(self):
        _reset_state()
        db = _mock_db_6x()
        with _patch_6x(db):
            client.post("/connect/linkedin/start?workspace_slug=test-ws")
        assert any(e["action"] == "linkedin_oauth_started"
                   for e in main._runtime_state_6u["audit_log"])


# =============================================================================
# 8. OAuth callback endpoint
# =============================================================================
class TestLinkedInOAuthCallback6X:
    def setup_method(self):
        _reset_state()

    def test_38_callback_state_match_connects(self):
        db = _mock_db_6x(has_integration=True)
        # Stored state matches
        db.external_integrations.find_one.return_value = {
            "oauth_state": "match_state", "status": "pending_oauth"
        }
        with _patch_6x(db):
            r = client.get("/connect/linkedin/callback?code=code123&state=match_state&workspace_slug=test-ws")
        assert r.status_code == 200
        assert r.json()["status"] == "connected"

    def test_39_callback_state_mismatch_returns_400(self):
        db = _mock_db_6x(has_integration=True)
        db.external_integrations.find_one.return_value = {
            "oauth_state": "stored_state_xyz", "status": "pending_oauth"
        }
        with _patch_6x(db):
            r = client.get("/connect/linkedin/callback?code=code123&state=wrong_state&workspace_slug=test-ws")
        assert r.status_code == 400

    def test_40_callback_simulated_when_no_client_id(self):
        db = _mock_db_6x(has_integration=False)
        db.external_integrations.find_one.return_value = None
        with _patch_6x(db):
            r = client.get("/connect/linkedin/callback?code=code123&state=s1&workspace_slug=test-ws")
        assert r.status_code == 200
        assert r.json()["simulated"] is True


# =============================================================================
# 9. LinkedIn publish endpoint
# =============================================================================
class TestLinkedInPublishEndpoint6X:
    def setup_method(self):
        _reset_state()

    def test_41_publish_returns_200(self):
        db = _mock_db_6x(has_integration=False, duplicate=False)
        with _patch_6x(db):
            r = client.post("/distribution/linkedin/publish", json={
                "workspace_slug": "test-ws",
                "workflow_asset_id": "asset-new-1",
                "content_text": "Hello from SignalForge!",
            })
        assert r.status_code == 200

    def test_42_publish_returns_verified_status(self):
        db = _mock_db_6x(has_integration=False, duplicate=False)
        with _patch_6x(db):
            r = client.post("/distribution/linkedin/publish", json={
                "workspace_slug": "test-ws",
                "workflow_asset_id": "asset-new-2",
                "content_text": "Hello LinkedIn!",
            })
        data = r.json()
        assert data["status"] == "verified"

    def test_43_publish_duplicate_returns_409(self):
        db = _mock_db_6x(has_integration=False, duplicate=True)
        with _patch_6x(db):
            r = client.post("/distribution/linkedin/publish", json={
                "workspace_slug": "test-ws",
                "workflow_asset_id": "asset-dup",
                "content_text": "Duplicate post",
            })
        assert r.status_code == 409

    def test_44_publish_response_has_post_id(self):
        db = _mock_db_6x(has_integration=False, duplicate=False)
        with _patch_6x(db):
            r = client.post("/distribution/linkedin/publish", json={
                "workspace_slug": "test-ws",
                "workflow_asset_id": "asset-new-3",
                "content_text": "Post content here",
            })
        assert r.json().get("external_post_id")


# =============================================================================
# 10. LinkedIn retry endpoint
# =============================================================================
class TestLinkedInRetryEndpoint6X:
    def setup_method(self):
        _reset_state()

    def test_45_retry_failed_attempt_returns_200(self):
        attempt = _make_attempt(status="failed", retry_count=0)
        db = _mock_db_6x(attempt_doc=attempt)
        with _patch_6x(db):
            r = client.post("/distribution/linkedin/retry?attempt_id=da_test001",
                            json={"workspace_slug": "test-ws"})
        assert r.status_code == 200

    def test_46_retry_nonexistent_attempt_returns_404(self):
        db = _mock_db_6x()
        db.distribution_attempts.find_one.return_value = None
        with _patch_6x(db):
            r = client.post("/distribution/linkedin/retry?attempt_id=nonexistent",
                            json={"workspace_slug": "test-ws"})
        assert r.status_code == 404

    def test_47_retry_verified_attempt_returns_400(self):
        attempt = _make_attempt(status="verified", verified=True)
        db = _mock_db_6x(attempt_doc=attempt)
        with _patch_6x(db):
            r = client.post("/distribution/linkedin/retry?attempt_id=da_test001",
                            json={"workspace_slug": "test-ws"})
        assert r.status_code == 400

    def test_48_retry_over_limit_escalates(self):
        attempt = _make_attempt(status="failed",
                                retry_count=main._PUBLISH_RETRY_LIMITS_6X["network_failure"])
        db = _mock_db_6x(attempt_doc=attempt)
        with _patch_6x(db):
            r = client.post("/distribution/linkedin/retry?attempt_id=da_test001",
                            json={"workspace_slug": "test-ws"})
        assert r.status_code == 200
        assert r.json()["status"] == "escalated"


# =============================================================================
# 11. Distribution attempt status endpoint
# =============================================================================
class TestDistributionStatusEndpoint6X:
    def test_49_status_returns_attempt(self):
        attempt = _make_attempt(status="verified", verified=True)
        db = _mock_db_6x(attempt_doc=attempt)
        with _patch_6x(db):
            r = client.get("/distribution/linkedin/da_test001/status")
        assert r.status_code == 200
        assert r.json()["status"] == "verified"

    def test_50_status_missing_returns_404(self):
        db = _mock_db_6x()
        db.distribution_attempts.find_one.return_value = None
        with _patch_6x(db):
            r = client.get("/distribution/linkedin/da_missing/status")
        assert r.status_code == 404


# =============================================================================
# 12. External executions list endpoint
# =============================================================================
class TestExternalExecutionsEndpoint6X:
    def test_51_executions_list_returns_200(self):
        db = _mock_db_6x()
        with _patch_6x(db):
            r = client.get("/external-executions")
        assert r.status_code == 200

    def test_52_executions_list_has_executions_key(self):
        db = _mock_db_6x()
        with _patch_6x(db):
            r = client.get("/external-executions")
        assert "executions" in r.json()

    def test_53_execution_detail_missing_returns_404(self):
        db = _mock_db_6x()
        db.distribution_attempts.find_one.return_value = None
        with _patch_6x(db):
            r = client.get("/external-executions/da_missing")
        assert r.status_code == 404


# =============================================================================
# 13. Distribution telemetry endpoint
# =============================================================================
class TestDistributionTelemetryEndpoint6X:
    def test_54_telemetry_returns_200(self):
        db = _mock_db_6x()
        db.distribution_attempts.count_documents.return_value = 0
        with _patch_6x(db):
            r = client.get("/distribution/telemetry")
        assert r.status_code == 200

    def test_55_telemetry_has_success_rate(self):
        db = _mock_db_6x()
        db.distribution_attempts.count_documents.return_value = 0
        with _patch_6x(db):
            r = client.get("/distribution/telemetry")
        assert "publish_success_rate" in r.json()


# =============================================================================
# 14. Deployment smoke — all new 6X endpoints respond
# =============================================================================
class TestDeploymentSmoke6X:
    def setup_method(self):
        _reset_state()

    def test_56_all_6x_endpoints_respond(self):
        db = _mock_db_6x(has_integration=True)
        attempt = _make_attempt(status="failed", retry_count=0)
        db.distribution_attempts.find_one.return_value = attempt
        db.distribution_attempts.count_documents.return_value = 0
        with _patch_6x(db):
            checks = [
                ("GET",  "/connect/linkedin/status?workspace_slug=ws",     None),
                ("POST", "/connect/linkedin/start?workspace_slug=ws",       {}),
                ("GET",  "/connect/linkedin/callback?code=c&state=s&workspace_slug=ws", None),
                ("POST", "/distribution/linkedin/publish",
                 {"workspace_slug": "ws", "workflow_asset_id": "ax1", "content_text": "Hi"}),
                ("GET",  "/distribution/linkedin/da_test001/status",        None),
                ("GET",  "/external-executions",                            None),
                ("GET",  "/distribution/telemetry",                         None),
            ]
            for method, path, body in checks:
                r = client.get(path) if method == "GET" else client.post(path, json=body or {})
                assert r.status_code in (200, 201, 409), (
                    f"{method} {path} → {r.status_code}: {r.text[:200]}"
                )

    def test_57_6x_endpoints_in_openapi(self):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        paths = r.json()["paths"]
        assert "/connect/linkedin/status" in paths
        assert "/distribution/linkedin/publish" in paths
        assert "/external-executions" in paths
        assert "/distribution/telemetry" in paths
