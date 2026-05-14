"""
tests/test_production_hardening.py
Phase 6U — Production Hardening & Deployment Readiness
63 tests covering: indexes, logging, rate limiting, auth, error responses,
tracing middleware, worker heartbeat, system/worker endpoints, and smoke flows.
"""

import time
import pytest
from unittest.mock import MagicMock, patch, call
from fastapi.testclient import TestClient

import sys, os, types

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
    _m = types.ModuleType(_mod)
    sys.modules.setdefault(_mod, _m)

sys.modules["core.constants"].MESSAGE_REVIEW_DECISIONS = []
sys.modules["core.constants"].OPEN_DEAL_OUTCOMES = []
sys.modules["core.constants"].VALID_MODULES = []

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

import main
from main import app

client = TestClient(app, raise_server_exceptions=False)


# ── DB mock helpers ───────────────────────────────────────────────────────────
def _mock_db_6u(orches: list | None = None, tasks: list | None = None):
    db = MagicMock()
    db.command.return_value = {"ok": 1}

    # Each collection returns a mock with create_indexes and find/update_many
    def _coll_mock(docs=None):
        c = MagicMock()
        c.create_indexes.return_value = ["idx"]
        _docs = list(docs or [])
        c.find.return_value = iter(_docs)
        result = MagicMock()
        result.modified_count = 0
        c.update_many.return_value = result
        return c

    for name in ["workflow_runs", "workflow_assets", "approval_requests", "client_memory",
                 "memory_update_proposals", "recommendation_statuses", "orchestrations",
                 "autonomy_actions", "agent_tasks"]:
        setattr(db, name, _coll_mock(tasks if name == "agent_tasks" else orches if name == "orchestrations" else None))

    return db


def _patch_6u(db=None):
    _db = db or _mock_db_6u()
    mc = MagicMock()
    mc.close = MagicMock()
    return patch.multiple("main", get_client=lambda: mc, get_database=lambda c: _db)


# ── Reset runtime state between test classes ──────────────────────────────────
def _reset_state():
    main._runtime_state_6u["total_requests"] = 0
    main._runtime_state_6u["by_path"] = {}
    main._runtime_state_6u["worker_registry"] = {}
    main._runtime_state_6u["audit_log"] = []
    main._runtime_state_6u["rate_buckets"] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. ensure_indexes_6u
# ═══════════════════════════════════════════════════════════════════════════════
class TestEnsureIndexes:
    def test_01_returns_dict_with_all_collections(self):
        db = _mock_db_6u()
        result = main.ensure_indexes_6u(db)
        assert isinstance(result, dict)
        expected = {
            "workflow_runs", "workflow_assets", "approval_requests", "client_memory",
            "memory_update_proposals", "recommendation_statuses", "orchestrations",
            "autonomy_actions", "agent_tasks",
        }
        assert set(result.keys()) == expected

    def test_02_all_collections_ok(self):
        db = _mock_db_6u()
        result = main.ensure_indexes_6u(db)
        for col, info in result.items():
            assert info["status"] == "ok", f"{col} not ok"

    def test_03_each_collection_index_count_positive(self):
        db = _mock_db_6u()
        result = main.ensure_indexes_6u(db)
        for col, info in result.items():
            assert info["indexes"] > 0, f"{col} has no indexes"

    def test_04_handles_collection_error_gracefully(self):
        db = MagicMock()
        bad_coll = MagicMock()
        bad_coll.create_indexes.side_effect = Exception("index error")
        db.workflow_runs = bad_coll
        for name in ["workflow_assets", "approval_requests", "client_memory",
                     "memory_update_proposals", "recommendation_statuses", "orchestrations",
                     "autonomy_actions", "agent_tasks"]:
            c = MagicMock(); c.create_indexes.return_value = ["idx"]; setattr(db, name, c)
        result = main.ensure_indexes_6u(db)
        assert result["workflow_runs"]["status"] == "error"
        assert "error" in result["workflow_runs"]

    def test_05_idempotent_second_call(self):
        db = _mock_db_6u()
        r1 = main.ensure_indexes_6u(db)
        r2 = main.ensure_indexes_6u(db)
        assert r1.keys() == r2.keys()
        for col in r1:
            assert r1[col]["status"] == r2[col]["status"]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Structured logging helpers
# ═══════════════════════════════════════════════════════════════════════════════
class TestStructuredLogging:
    def setup_method(self):
        _reset_state()

    def test_06_log_event_does_not_raise(self):
        main._log_event_6u("info", "test_event", key="value")  # should not raise

    def test_07_append_audit_adds_entry(self):
        main._append_audit_6u("user1", "action1", "resource1", extra="data")
        log = main._runtime_state_6u["audit_log"]
        assert len(log) >= 1
        last = log[-1]
        assert last["actor"] == "user1"
        assert last["action"] == "action1"
        assert last["resource"] == "resource1"
        assert last["extra"] == "data"

    def test_08_audit_log_capped_at_500(self):
        _reset_state()
        for i in range(510):
            main._append_audit_6u("sys", f"act{i}", "res")
        assert len(main._runtime_state_6u["audit_log"]) == 500


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Rate limiting
# ═══════════════════════════════════════════════════════════════════════════════
class TestRateLimiting:
    def setup_method(self):
        _reset_state()
        # Ensure rate limiting is enabled for these tests
        self._orig = main._RATE_LIMIT_ENABLED_6U
        main._RATE_LIMIT_ENABLED_6U = True

    def teardown_method(self):
        main._RATE_LIMIT_ENABLED_6U = self._orig
        _reset_state()

    def test_09_allows_under_limit(self):
        assert main._check_rate_limit_6u("testkey", max_requests=5, window_seconds=60) is True
        assert main._check_rate_limit_6u("testkey", max_requests=5, window_seconds=60) is True

    def test_10_blocks_over_limit(self):
        for _ in range(3):
            main._check_rate_limit_6u("testkey2", max_requests=3, window_seconds=60)
        assert main._check_rate_limit_6u("testkey2", max_requests=3, window_seconds=60) is False

    def test_11_bypassed_when_disabled(self):
        main._RATE_LIMIT_ENABLED_6U = False
        # Even "exceeded" key should pass
        for _ in range(200):
            main._check_rate_limit_6u("testkey3", max_requests=1, window_seconds=60)
        assert main._check_rate_limit_6u("testkey3", max_requests=1, window_seconds=60) is True

    def test_12_separate_keys_independent(self):
        for _ in range(3):
            main._check_rate_limit_6u("key_a", max_requests=3, window_seconds=60)
        # key_a is exhausted; key_b should still pass
        assert main._check_rate_limit_6u("key_b", max_requests=3, window_seconds=60) is True
        assert main._check_rate_limit_6u("key_a", max_requests=3, window_seconds=60) is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Auth helpers
# ═══════════════════════════════════════════════════════════════════════════════
class TestAuthHelpers:
    def setup_method(self):
        self._orig_auth = main._AUTH_ENABLED_6U

    def teardown_method(self):
        main._AUTH_ENABLED_6U = self._orig_auth

    def test_13_create_token_returns_string(self):
        token = main._create_token_6u({"sub": "test_user", "role": "admin"})
        assert isinstance(token, str)
        assert len(token) > 10

    def test_14_decode_token_round_trip(self):
        if not main._PYJWT_AVAILABLE:
            pytest.skip("PyJWT not available")
        token = main._create_token_6u({"sub": "test_user", "role": "admin"})
        decoded = main._decode_token_6u(token)
        assert decoded["sub"] == "test_user"
        assert decoded["role"] == "admin"

    def test_15_require_auth_bypassed_when_disabled(self):
        main._AUTH_ENABLED_6U = False
        req = MagicMock()
        req.headers = {}
        identity = main._require_auth_6u(req)
        assert identity["role"] == "admin"
        assert identity["sub"] == "dev-bypass"

    def test_16_require_auth_accepts_valid_api_key(self):
        main._AUTH_ENABLED_6U = True
        req = MagicMock()
        api_key = list(main._DEFAULT_API_KEYS_6U.keys())[0]
        req.headers = {"Authorization": f"Bearer {api_key}"}
        identity = main._require_auth_6u(req)
        assert identity["role"] == "admin"

    def test_17_require_auth_raises_401_no_header(self):
        main._AUTH_ENABLED_6U = True
        req = MagicMock()
        req.headers = {}
        from fastapi import HTTPException as _HTTPException
        with pytest.raises(_HTTPException) as exc_info:
            main._require_auth_6u(req)
        assert exc_info.value.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Error response helper
# ═══════════════════════════════════════════════════════════════════════════════
class TestErrorResponse:
    def test_18_returns_http_exception(self):
        from fastapi import HTTPException as _HTTPException
        exc = main._error_response_6u("test_code", "test message", status_code=400)
        assert isinstance(exc, _HTTPException)
        assert exc.status_code == 400

    def test_19_detail_has_required_fields(self):
        exc = main._error_response_6u("bad_input", "Something went wrong", status_code=422)
        detail = exc.detail
        assert detail["error"] is True
        assert detail["code"] == "bad_input"
        assert detail["message"] == "Something went wrong"
        assert "trace_id" in detail
        assert "details" in detail

    def test_20_uses_provided_trace_id(self):
        exc = main._error_response_6u("err", "msg", trace_id="abc123")
        assert exc.detail["trace_id"] == "abc123"

    def test_21_autogenerates_trace_id_when_missing(self):
        exc = main._error_response_6u("err", "msg")
        assert isinstance(exc.detail["trace_id"], str)
        assert len(exc.detail["trace_id"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Request metrics
# ═══════════════════════════════════════════════════════════════════════════════
class TestRequestMetrics:
    def setup_method(self):
        _reset_state()

    def test_22_record_increments_total(self):
        before = main._runtime_state_6u["total_requests"]
        main._record_request_6u("/test", "GET", 10.0, 200)
        assert main._runtime_state_6u["total_requests"] == before + 1

    def test_23_tracks_per_path(self):
        main._record_request_6u("/my/path", "GET", 25.0, 200)
        bucket = main._runtime_state_6u["by_path"]["GET:/my/path"]
        assert bucket["count"] == 1
        assert bucket["avg_latency_ms"] == 25.0

    def test_24_counts_errors(self):
        main._record_request_6u("/fail", "POST", 5.0, 500)
        bucket = main._runtime_state_6u["by_path"]["POST:/fail"]
        assert bucket["errors"] == 1

    def test_25_running_avg_latency(self):
        main._record_request_6u("/avg", "GET", 100.0, 200)
        main._record_request_6u("/avg", "GET", 200.0, 200)
        bucket = main._runtime_state_6u["by_path"]["GET:/avg"]
        assert bucket["avg_latency_ms"] == 150.0


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Worker heartbeat helpers
# ═══════════════════════════════════════════════════════════════════════════════
class TestWorkerHeartbeatHelpers:
    def setup_method(self):
        _reset_state()

    def test_26_record_heartbeat_stores_record(self):
        rec = main._record_worker_heartbeat_6u("w1", "running", tasks_processed=5)
        assert rec["worker_id"] == "w1"
        assert rec["status"] == "running"
        assert rec["tasks_processed"] == 5
        assert "last_seen" in rec
        assert main._runtime_state_6u["worker_registry"]["w1"] == rec

    def test_27_get_worker_health_empty(self):
        h = main._get_worker_health_6u()
        assert h["total_workers"] == 0
        assert h["healthy"] == 0
        assert h["stale"] == 0

    def test_28_get_worker_health_fresh_worker(self):
        main._record_worker_heartbeat_6u("w2", "running")
        h = main._get_worker_health_6u()
        assert h["healthy"] == 1
        assert h["stale"] == 0

    def test_29_stale_detection(self):
        # Inject a stale timestamp directly
        from datetime import datetime, timezone, timedelta
        stale_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        main._runtime_state_6u["worker_registry"]["w3"] = {
            "worker_id": "w3", "status": "running", "last_seen": stale_time,
            "tasks_processed": 0, "tasks_failed": 0, "queue_depth": 0, "metadata": {},
        }
        h = main._get_worker_health_6u()
        assert "w3" in h["stale_worker_ids"]

    def test_30_detect_stuck_orchestrations_empty(self):
        db = _mock_db_6u()
        stuck = main._detect_stuck_orchestrations_6u(db, threshold_minutes=60)
        assert isinstance(stuck, list)

    def test_31_recover_orphaned_no_stale(self):
        db = _mock_db_6u()
        result = main._recover_orphaned_tasks_6u(db)
        assert result["recovered_tasks"] == 0
        assert result["stale_workers"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Auth endpoints
# ═══════════════════════════════════════════════════════════════════════════════
class TestAuthEndpoints:
    def setup_method(self):
        _reset_state()

    def test_32_post_auth_token_valid_key(self):
        api_key = list(main._DEFAULT_API_KEYS_6U.keys())[0]
        r = client.post("/auth/token", json={"api_key": api_key, "workspace_slug": "ws1"})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["role"] == "admin"

    def test_33_post_auth_token_invalid_key(self):
        r = client.post("/auth/token", json={"api_key": "bad-key"})
        assert r.status_code == 401

    def test_34_get_auth_validate_auth_disabled(self):
        r = client.get("/auth/validate")
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True
        assert "identity" in data

    def test_35_post_auth_token_adds_audit_log(self):
        _reset_state()
        api_key = list(main._DEFAULT_API_KEYS_6U.keys())[0]
        client.post("/auth/token", json={"api_key": api_key})
        log = main._runtime_state_6u["audit_log"]
        assert any(e["action"] == "token_issued" for e in log)

    def test_36_auth_validate_returns_identity_fields(self):
        r = client.get("/auth/validate")
        identity = r.json()["identity"]
        assert "role" in identity


# ═══════════════════════════════════════════════════════════════════════════════
# 9. System health detailed
# ═══════════════════════════════════════════════════════════════════════════════
class TestSystemHealthDetailed:
    def test_37_returns_healthy_status(self):
        db = _mock_db_6u()
        with _patch_6u(db):
            r = client.get("/system/health/detailed")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert "components" in data
        assert "version" in data

    def test_38_components_include_all_keys(self):
        db = _mock_db_6u()
        with _patch_6u(db):
            r = client.get("/system/health/detailed")
        comp = r.json()["components"]
        assert "database" in comp
        assert "vault" in comp
        assert "workers" in comp
        assert "auth" in comp
        assert "rate_limiting" in comp

    def test_39_db_error_returns_degraded(self):
        db = MagicMock()
        db.command.side_effect = Exception("conn refused")
        mc = MagicMock(); mc.close = MagicMock()
        with patch.multiple("main", get_client=lambda: mc, get_database=lambda c: db):
            r = client.get("/system/health/detailed")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "degraded"
        assert data["components"]["database"]["status"] == "error"

    def test_40_has_timestamp_and_environment(self):
        db = _mock_db_6u()
        with _patch_6u(db):
            r = client.get("/system/health/detailed")
        data = r.json()
        assert "timestamp" in data
        assert "environment" in data


# ═══════════════════════════════════════════════════════════════════════════════
# 10. System metrics
# ═══════════════════════════════════════════════════════════════════════════════
class TestSystemMetrics:
    def setup_method(self):
        _reset_state()

    def test_41_returns_200(self):
        r = client.get("/system/metrics")
        assert r.status_code == 200

    def test_42_includes_required_fields(self):
        r = client.get("/system/metrics")
        data = r.json()
        assert "total_requests" in data
        assert "unique_endpoints" in data
        assert "top_endpoints" in data
        assert "error_endpoints" in data
        assert "timestamp" in data

    def test_43_unique_endpoints_reflects_hits(self):
        _reset_state()
        main._record_request_6u("/some/path", "GET", 5.0, 200)
        main._record_request_6u("/other/path", "GET", 5.0, 200)
        r = client.get("/system/metrics")
        data = r.json()
        assert data["unique_endpoints"] >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# 11. System indexes endpoint
# ═══════════════════════════════════════════════════════════════════════════════
class TestSystemIndexes:
    def test_44_returns_200(self):
        db = _mock_db_6u()
        with _patch_6u(db):
            r = client.get("/system/indexes")
        assert r.status_code == 200

    def test_45_response_structure(self):
        db = _mock_db_6u()
        with _patch_6u(db):
            r = client.get("/system/indexes")
        data = r.json()
        assert "status" in data
        assert "collections" in data
        assert "timestamp" in data

    def test_46_all_nine_collections_present(self):
        db = _mock_db_6u()
        with _patch_6u(db):
            r = client.get("/system/indexes")
        cols = r.json()["collections"]
        expected = {
            "workflow_runs", "workflow_assets", "approval_requests", "client_memory",
            "memory_update_proposals", "recommendation_statuses", "orchestrations",
            "autonomy_actions", "agent_tasks",
        }
        assert expected.issubset(set(cols.keys()))


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Worker endpoints
# ═══════════════════════════════════════════════════════════════════════════════
class TestWorkerEndpoints:
    def setup_method(self):
        _reset_state()

    def test_47_post_heartbeat_returns_accepted(self):
        r = client.post("/workers/heartbeat", json={
            "worker_id": "worker-abc", "status": "running",
            "tasks_processed": 10, "queue_depth": 3,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["accepted"] is True
        assert data["worker"]["worker_id"] == "worker-abc"

    def test_48_get_workers_health_returns_registry(self):
        r = client.get("/workers/health")
        assert r.status_code == 200
        data = r.json()
        assert "total_workers" in data
        assert "healthy" in data
        assert "stale" in data
        assert "registry" in data

    def test_49_get_queue_depth_no_workers(self):
        r = client.get("/workers/queue-depth")
        assert r.status_code == 200
        data = r.json()
        assert data["total_queue_depth"] == 0
        assert data["worker_count"] == 0

    def test_50_get_queue_depth_with_worker(self):
        client.post("/workers/heartbeat", json={
            "worker_id": "w-q1", "status": "running", "queue_depth": 7,
        })
        r = client.get("/workers/queue-depth")
        data = r.json()
        assert data["total_queue_depth"] >= 7

    def test_51_post_recover_orphaned(self):
        db = _mock_db_6u()
        with _patch_6u(db):
            r = client.post("/workers/recover-orphaned")
        assert r.status_code == 200
        data = r.json()
        assert "recovery" in data
        assert "stuck_orchestrations" in data
        assert "stuck_count" in data
        assert "timestamp" in data

    def test_52_heartbeat_registry_updates(self):
        client.post("/workers/heartbeat", json={"worker_id": "w-upd", "status": "idle"})
        client.post("/workers/heartbeat", json={"worker_id": "w-upd", "status": "running"})
        r = client.get("/workers/health")
        registry = {w["worker_id"]: w for w in r.json()["registry"]}
        assert registry["w-upd"]["status"] == "running"


# ═══════════════════════════════════════════════════════════════════════════════
# 13. System telemetry
# ═══════════════════════════════════════════════════════════════════════════════
class TestSystemTelemetry:
    def setup_method(self):
        _reset_state()

    def test_53_returns_200(self):
        db = _mock_db_6u()
        with _patch_6u(db):
            r = client.get("/system/telemetry")
        assert r.status_code == 200

    def test_54_has_all_top_level_fields(self):
        db = _mock_db_6u()
        with _patch_6u(db):
            r = client.get("/system/telemetry")
        data = r.json()
        assert "database" in data
        assert "api" in data
        assert "workers" in data
        assert "timestamp" in data

    def test_55_api_subfields(self):
        db = _mock_db_6u()
        with _patch_6u(db):
            r = client.get("/system/telemetry")
        api_data = r.json()["api"]
        assert "total_requests" in api_data
        assert "total_errors" in api_data
        assert "error_rate" in api_data
        assert "avg_latency_ms" in api_data

    def test_56_workers_subfields(self):
        db = _mock_db_6u()
        with _patch_6u(db):
            r = client.get("/system/telemetry")
        wk = r.json()["workers"]
        assert "total" in wk
        assert "healthy" in wk
        assert "stale" in wk
        assert "total_queue_depth" in wk


# ═══════════════════════════════════════════════════════════════════════════════
# 14. System reset metrics + audit log
# ═══════════════════════════════════════════════════════════════════════════════
class TestSystemResetAndAuditLog:
    def setup_method(self):
        _reset_state()

    def test_57_reset_metrics_clears_state(self):
        # Record many requests before reset to establish a clear before/after
        for _ in range(10):
            main._record_request_6u("/foo", "GET", 10.0, 200)
        before = main._runtime_state_6u["total_requests"]
        assert before >= 10
        r = client.post("/system/reset-metrics")
        assert r.status_code == 200
        assert r.json()["reset"] is True
        # After reset, total_requests resets to 0 then middleware records the POST call (~1)
        # Either way it should be far less than 10
        after = main._runtime_state_6u["total_requests"]
        assert after < before

    def test_58_reset_adds_audit_entry(self):
        _reset_state()
        client.post("/system/reset-metrics")
        log = main._runtime_state_6u["audit_log"]
        assert any(e["action"] == "reset_metrics" for e in log)

    def test_59_get_audit_log_returns_entries(self):
        main._append_audit_6u("sys", "test_action", "resource")
        r = client.get("/system/audit-log")
        assert r.status_code == 200
        data = r.json()
        assert "entries" in data
        assert "total_recorded" in data
        assert "returned" in data
        assert data["returned"] <= data["total_recorded"]

    def test_60_audit_log_limit_param(self):
        for i in range(10):
            main._append_audit_6u("sys", f"act{i}", "res")
        r = client.get("/system/audit-log?limit=3")
        data = r.json()
        assert data["returned"] <= 3


# ═══════════════════════════════════════════════════════════════════════════════
# 15. Tracing middleware headers
# ═══════════════════════════════════════════════════════════════════════════════
class TestTracingMiddleware:
    def test_61_x_trace_id_in_response(self):
        r = client.get("/health")
        assert "x-trace-id" in r.headers

    def test_62_x_response_time_in_response(self):
        r = client.get("/health")
        assert "x-response-time-ms" in r.headers

    def test_63_custom_trace_id_propagated(self):
        r = client.get("/health", headers={"X-Trace-ID": "my-trace-123"})
        assert r.headers.get("x-trace-id") == "my-trace-123"
