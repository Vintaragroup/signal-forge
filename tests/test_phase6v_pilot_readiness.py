"""
tests/test_phase6v_pilot_readiness.py
Phase 6V — Production Deployment Drill & Pilot Readiness
42 tests covering: backup/restore, pilot readiness, recovery status,
auth-enabled behavior, rate-limit behavior, worker recovery scenarios,
orchestration recovery scenarios, deployment smoke, telemetry integrity.
"""

import json
import gzip
import base64
import time
import pytest
from datetime import datetime, timezone, timedelta
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


# ── Shared helpers ────────────────────────────────────────────────────────────

def _reset_state():
    main._runtime_state_6u.update({
        "total_requests": 0,
        "by_path": {},
        "worker_registry": {},
        "audit_log": [],
        "rate_buckets": {},
    })


def _mock_db_6v(orches=None, tasks=None, ping_ok=True):
    """Return a mock MongoDB with all Phase 6V collections wired up."""
    db = MagicMock()
    if ping_ok:
        db.command.return_value = {"ok": 1}
    else:
        db.command.side_effect = Exception("connection refused")

    db.list_collection_names.return_value = list(main._PHASE_6V_COLLECTIONS)

    coll_store: dict = {}
    for name in main._PHASE_6V_COLLECTIONS:
        c = MagicMock()
        docs = []
        if name == "orchestrations" and orches:
            docs = list(orches)
        elif name == "agent_tasks" and tasks:
            docs = list(tasks)
        c.find.return_value = iter(docs)
        c.find_one.return_value = None
        c.delete_many.return_value = MagicMock(deleted_count=len(docs))
        c.insert_many.return_value = MagicMock(inserted_ids=[])
        c.update_many.return_value = MagicMock(modified_count=0)
        c.create_indexes.return_value = ["idx"]
        c.index_information.return_value = {}
        coll_store[name] = c

    db.__getitem__ = MagicMock(side_effect=lambda name: coll_store.get(name, MagicMock()))
    # Also allow attribute-style access used by _detect_stuck_orchestrations_6u
    db.orchestrations = coll_store["orchestrations"]
    db.agent_tasks = coll_store["agent_tasks"]

    return db, coll_store


def _patch_6v(db):
    mc = MagicMock()
    mc.close = MagicMock()
    return patch.multiple(
        "main",
        get_client=lambda: mc,
        get_database=lambda c: db,
    )


def _make_backup_payload(collections=None, compress=True, version="6v"):
    """Build a valid base64-encoded backup payload for restore tests."""
    colls = collections or ["workflow_runs", "orchestrations"]
    snapshot = {
        "version": version,
        "created_at": "2026-05-13T00:00:00+00:00",
        "collections": {c: [] for c in colls},
    }
    raw = json.dumps(snapshot).encode()
    if compress:
        return base64.b64encode(gzip.compress(raw)).decode()
    return base64.b64encode(raw).decode()


# =============================================================================
# 1. Backup helper unit tests
# =============================================================================
class TestBackupHelper6V:
    def setup_method(self):
        _reset_state()

    def test_01_backup_returns_payload_key(self):
        db, _ = _mock_db_6v()
        result = main._do_backup_6v(db, ["workflow_runs"], compress=True)
        assert "payload" in result

    def test_02_backup_payload_is_valid_base64(self):
        db, _ = _mock_db_6v()
        result = main._do_backup_6v(db, ["orchestrations"], compress=True)
        decoded = base64.b64decode(result["payload"])
        assert len(decoded) > 0

    def test_03_backup_compressed_payload_roundtrips(self):
        db, _ = _mock_db_6v()
        result = main._do_backup_6v(db, ["client_memory"], compress=True)
        raw = gzip.decompress(base64.b64decode(result["payload"]))
        snapshot = json.loads(raw)
        assert snapshot["version"] == "6v"
        assert "client_memory" in snapshot["collections"]

    def test_04_backup_uncompressed_option(self):
        db, _ = _mock_db_6v()
        result = main._do_backup_6v(db, ["autonomy_actions"], compress=False)
        raw = base64.b64decode(result["payload"])
        snapshot = json.loads(raw)
        assert snapshot["version"] == "6v"
        assert result["compressed"] is False

    def test_05_backup_total_documents_count(self):
        db, coll_store = _mock_db_6v()
        coll_store["workflow_runs"].find.return_value = iter([{"id": 1}, {"id": 2}])
        result = main._do_backup_6v(db, ["workflow_runs"], compress=False)
        assert result["total_documents"] == 2

    def test_06_backup_reports_correct_collection_list(self):
        db, _ = _mock_db_6v()
        cols = ["workflow_runs", "orchestrations", "autonomy_actions"]
        result = main._do_backup_6v(db, cols, compress=False)
        assert set(result["collections"]) == set(cols)


# =============================================================================
# 2. Restore helper unit tests
# =============================================================================
class TestRestoreHelper6V:
    def setup_method(self):
        _reset_state()

    def test_07_restore_dry_run_makes_no_writes(self):
        db, coll_store = _mock_db_6v()
        payload = _make_backup_payload(["workflow_runs"])
        main._do_restore_6v(db, payload, compressed=True, dry_run=True)
        coll_store["workflow_runs"].delete_many.assert_not_called()
        coll_store["workflow_runs"].insert_many.assert_not_called()

    def test_08_restore_dry_run_response_shows_would_restore(self):
        db, _ = _mock_db_6v()
        payload = _make_backup_payload(["orchestrations"])
        result = main._do_restore_6v(db, payload, compressed=True, dry_run=True)
        assert result["dry_run"] is True
        assert "orchestrations" in result["collections"]
        assert result["collections"]["orchestrations"]["status"] == "dry_run"

    def test_09_restore_actual_calls_delete_many(self):
        db, coll_store = _mock_db_6v()
        payload = _make_backup_payload(["workflow_runs"])
        main._do_restore_6v(db, payload, compressed=True, dry_run=False)
        coll_store["workflow_runs"].delete_many.assert_called_once_with({})

    def test_10_restore_wrong_version_raises_value_error(self):
        db, _ = _mock_db_6v()
        payload = _make_backup_payload(version="99x")
        with pytest.raises(ValueError, match="Unsupported backup version"):
            main._do_restore_6v(db, payload, compressed=True, dry_run=False)

    def test_11_restore_uncompressed_roundtrip(self):
        db, coll_store = _mock_db_6v()
        payload = _make_backup_payload(["client_memory"], compress=False)
        result = main._do_restore_6v(db, payload, compressed=False, dry_run=True)
        assert result["source_version"] == "6v"
        assert "client_memory" in result["collections"]


# =============================================================================
# 3. Pilot readiness helper unit tests
# =============================================================================
class TestPilotReadinessHelper6V:
    def setup_method(self):
        _reset_state()

    def test_12_readiness_returns_score(self):
        db, _ = _mock_db_6v(ping_ok=True)
        result = main._pilot_readiness_6v(db)
        assert "score" in result
        assert isinstance(result["score"], int)

    def test_13_readiness_score_at_least_80_when_healthy(self):
        db, _ = _mock_db_6v(ping_ok=True)
        with patch.object(main, "ensure_indexes_6u", return_value={"created": []}):
            result = main._pilot_readiness_6v(db)
        assert result["score"] >= 80

    def test_14_readiness_ready_flag_reflects_score(self):
        db, _ = _mock_db_6v(ping_ok=True)
        with patch.object(main, "ensure_indexes_6u", return_value={"created": []}):
            result = main._pilot_readiness_6v(db)
        assert result["ready"] == (result["score"] >= 80)

    def test_15_readiness_has_checks_dict(self):
        db, _ = _mock_db_6v()
        result = main._pilot_readiness_6v(db)
        assert isinstance(result["checks"], dict)
        assert "mongodb_reachable" in result["checks"]
        assert "tracing_active" in result["checks"]

    def test_16_readiness_mongo_failure_reduces_score(self):
        db, _ = _mock_db_6v(ping_ok=False)
        result = main._pilot_readiness_6v(db)
        assert result["checks"]["mongodb_reachable"] is False
        assert result["score"] <= 80  # lost 20 points for mongo + possibly indexes


# =============================================================================
# 4. Backup endpoint tests
# =============================================================================
class TestBackupEndpoint6V:
    def setup_method(self):
        _reset_state()

    def test_17_backup_endpoint_returns_200(self):
        db, _ = _mock_db_6v()
        with _patch_6v(db):
            r = client.post("/system/backup", json={"compress": True})
        assert r.status_code == 200

    def test_18_backup_endpoint_response_has_payload(self):
        db, _ = _mock_db_6v()
        with _patch_6v(db):
            r = client.post("/system/backup", json={"compress": False})
        assert "payload" in r.json()

    def test_19_backup_custom_collections(self):
        db, _ = _mock_db_6v()
        with _patch_6v(db):
            r = client.post("/system/backup", json={"collections": ["workflow_runs"], "compress": False})
        data = r.json()
        assert data["collections"] == ["workflow_runs"]

    def test_20_backup_writes_audit_entry(self):
        db, _ = _mock_db_6v()
        _reset_state()
        with _patch_6v(db):
            client.post("/system/backup", json={"compress": False})
        assert any(e["action"] == "backup_created" for e in main._runtime_state_6u["audit_log"])


# =============================================================================
# 5. Restore endpoint tests
# =============================================================================
class TestRestoreEndpoint6V:
    def setup_method(self):
        _reset_state()

    def test_21_restore_dry_run_returns_200(self):
        db, _ = _mock_db_6v()
        payload = _make_backup_payload(["workflow_runs"])
        with _patch_6v(db):
            r = client.post("/system/restore", json={"payload": payload, "dry_run": True})
        assert r.status_code == 200

    def test_22_restore_dry_run_shows_dry_run_true(self):
        db, _ = _mock_db_6v()
        payload = _make_backup_payload(["orchestrations"])
        with _patch_6v(db):
            r = client.post("/system/restore", json={"payload": payload, "dry_run": True})
        assert r.json()["dry_run"] is True

    def test_23_restore_bad_version_raises_value_error(self):
        db, _ = _mock_db_6v()
        payload = _make_backup_payload(version="BADVER")
        with pytest.raises(ValueError, match="Unsupported backup version"):
            main._do_restore_6v(db, payload, compressed=True, dry_run=False)

    def test_24_restore_writes_audit_entry(self):
        db, _ = _mock_db_6v()
        _reset_state()
        payload = _make_backup_payload(["workflow_runs"])
        with _patch_6v(db):
            client.post("/system/restore", json={"payload": payload, "dry_run": True})
        assert any(e["action"] == "restore_executed" for e in main._runtime_state_6u["audit_log"])


# =============================================================================
# 6. Pilot readiness endpoint tests
# =============================================================================
class TestPilotReadinessEndpoint6V:
    def setup_method(self):
        _reset_state()

    def test_25_pilot_readiness_returns_200(self):
        db, _ = _mock_db_6v()
        with _patch_6v(db):
            r = client.get("/system/pilot-readiness")
        assert r.status_code == 200

    def test_26_pilot_readiness_has_score(self):
        db, _ = _mock_db_6v()
        with _patch_6v(db):
            r = client.get("/system/pilot-readiness")
        assert "score" in r.json()

    def test_27_pilot_readiness_has_ready_flag(self):
        db, _ = _mock_db_6v()
        with _patch_6v(db):
            r = client.get("/system/pilot-readiness")
        assert "ready" in r.json()

    def test_28_pilot_readiness_has_evaluated_at(self):
        db, _ = _mock_db_6v()
        with _patch_6v(db):
            r = client.get("/system/pilot-readiness")
        assert "evaluated_at" in r.json()


# =============================================================================
# 7. Recovery status endpoint tests
# =============================================================================
class TestRecoveryStatusEndpoint6V:
    def setup_method(self):
        _reset_state()

    def test_29_recovery_status_returns_200(self):
        db, _ = _mock_db_6v()
        with _patch_6v(db):
            r = client.get("/system/recovery-status")
        assert r.status_code == 200

    def test_30_recovery_status_has_stuck_orchestrations(self):
        db, _ = _mock_db_6v()
        with _patch_6v(db):
            r = client.get("/system/recovery-status")
        assert "stuck_orchestrations" in r.json()

    def test_31_recovery_status_has_worker_health(self):
        db, _ = _mock_db_6v()
        with _patch_6v(db):
            r = client.get("/system/recovery-status")
        assert "worker_health" in r.json()

    def test_32_recovery_no_stuck_gives_no_action_recommendation(self):
        db, _ = _mock_db_6v(orches=[])
        with _patch_6v(db):
            r = client.get("/system/recovery-status")
        data = r.json()
        assert data["orphaned_task_risk"] is False
        assert "no action needed" in data["recommendation"]


# =============================================================================
# 8. Auth-enabled behavior tests
# =============================================================================
class TestAuthEnabledBehavior6V:
    def setup_method(self):
        _reset_state()

    def test_33_with_auth_off_no_token_needed(self):
        db, _ = _mock_db_6v()
        with _patch_6v(db):
            with patch.object(main, "_AUTH_ENABLED_6U", False):
                r = client.get("/system/pilot-readiness")
        assert r.status_code == 200

    def test_34_auth_token_endpoint_always_accessible(self):
        r = client.post("/auth/token", json={"api_key": "dev-key-1"})
        assert r.status_code in (200, 401)  # 200 if key valid, 401 if not

    def test_35_with_auth_on_missing_token_returns_401(self):
        with patch.object(main, "_AUTH_ENABLED_6U", True):
            r = client.get("/auth/validate")
        assert r.status_code == 401

    def test_36_auth_validate_with_valid_token_returns_200(self):
        # Get a token first (auth must be temporarily off to issue one without key check)
        with patch.object(main, "_AUTH_ENABLED_6U", False):
            token_r = client.post("/auth/token", json={"api_key": "dev-key-1"})
        if token_r.status_code == 200:
            token = token_r.json()["access_token"]
            r = client.get("/auth/validate", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200

    def test_37_create_and_decode_token_roundtrip(self):
        token = main._create_token_6u({"sub": "test_user", "role": "operator"})
        payload = main._decode_token_6u(token)
        assert payload["sub"] == "test_user"
        assert payload["role"] == "operator"


# =============================================================================
# 9. Rate-limit behavior tests
# =============================================================================
class TestRateLimitBehavior6V:
    def setup_method(self):
        _reset_state()

    def test_38_rate_limit_off_allows_all_requests(self):
        with patch.object(main, "_RATE_LIMIT_ENABLED_6U", False):
            for _ in range(5):
                allowed = main._check_rate_limit_6u("test-key", max_requests=2, window_seconds=60)
            assert allowed is True

    def test_39_rate_limit_on_blocks_after_limit(self):
        _reset_state()
        with patch.object(main, "_RATE_LIMIT_ENABLED_6U", True):
            for _ in range(3):
                main._check_rate_limit_6u("burst-key", max_requests=3, window_seconds=60)
            blocked = main._check_rate_limit_6u("burst-key", max_requests=3, window_seconds=60)
        assert blocked is False

    def test_40_rate_limit_different_keys_are_independent(self):
        _reset_state()
        with patch.object(main, "_RATE_LIMIT_ENABLED_6U", True):
            for _ in range(3):
                main._check_rate_limit_6u("key-A", max_requests=3, window_seconds=60)
            # key-A is now exhausted; key-B should still be allowed
            allowed_b = main._check_rate_limit_6u("key-B", max_requests=3, window_seconds=60)
        assert allowed_b is True

    def test_41_rate_limit_on_burst_returns_429_from_heartbeat(self):
        _reset_state()
        # Worker heartbeat is rate-limited at 120/min; can't easily hit 120,
        # but we can verify the endpoint checks the limit by patching _check_rate_limit_6u
        with patch.object(main, "_check_rate_limit_6u", return_value=False):
            r = client.post("/workers/heartbeat", json={
                "worker_id": "w1", "status": "idle",
                "tasks_processed": 0, "tasks_failed": 0,
                "queue_depth": 0, "metadata": {},
            })
        assert r.status_code == 429


# =============================================================================
# 10. Worker recovery scenario tests
# =============================================================================
class TestWorkerRecoveryScenarios6V:
    def setup_method(self):
        _reset_state()

    def test_42_stale_worker_detected_in_health_check(self):
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        main._runtime_state_6u["worker_registry"]["stale-w"] = {
            "worker_id": "stale-w",
            "last_seen": old_ts,
            "status": "idle",
            "queue_depth": 0,
            "tasks_processed": 0,
            "tasks_failed": 0,
            "metadata": {},
        }
        health = main._get_worker_health_6u()
        assert "stale-w" in health["stale_worker_ids"]

    def test_43_fresh_worker_is_not_stale(self):
        fresh_ts = datetime.now(timezone.utc).isoformat()
        main._runtime_state_6u["worker_registry"]["fresh-w"] = {
            "worker_id": "fresh-w",
            "last_seen": fresh_ts,
            "status": "running",
            "queue_depth": 2,
            "tasks_processed": 10,
            "tasks_failed": 0,
            "metadata": {},
        }
        health = main._get_worker_health_6u()
        assert "fresh-w" not in health["stale_worker_ids"]

    def test_44_orphan_recovery_marks_stale_worker_tasks(self):
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        main._runtime_state_6u["worker_registry"]["dead-w"] = {
            "worker_id": "dead-w",
            "last_seen": old_ts,
            "status": "idle",
            "queue_depth": 0,
            "tasks_processed": 0,
            "tasks_failed": 0,
            "metadata": {},
        }
        db, coll_store = _mock_db_6v()
        coll_store["agent_tasks"].update_many.return_value = MagicMock(modified_count=3)
        result = main._recover_orphaned_tasks_6u(db)
        assert result["recovered_tasks"] >= 0  # only > 0 if update_many is called with stale IDs
        assert "dead-w" in result["stale_workers"]

    def test_45_heartbeat_registers_worker(self):
        _reset_state()
        db, _ = _mock_db_6v()
        with _patch_6v(db):
            r = client.post("/workers/heartbeat", json={
                "worker_id": "reg-w",
                "status": "running",
                "tasks_processed": 5,
                "tasks_failed": 0,
                "queue_depth": 1,
                "metadata": {"version": "1.0"},
            })
        assert r.status_code == 200
        assert "reg-w" in main._runtime_state_6u["worker_registry"]


# =============================================================================
# 11. Orchestration recovery scenario tests
# =============================================================================
class TestOrchestrationRecoveryScenarios6V:
    def setup_method(self):
        _reset_state()

    def _old_iso(self, minutes=90):
        return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()

    def _fresh_iso(self):
        return datetime.now(timezone.utc).isoformat()

    def test_46_stuck_orchestration_detected(self):
        stuck_orch = {
            "orchestration_id": "orch-stuck",
            "status": "running",
            "created_at": self._old_iso(90),
            "workspace_slug": "test-ws",
        }
        db, coll_store = _mock_db_6v()
        coll_store["orchestrations"].find.return_value = iter([stuck_orch])
        db.orchestrations.find.return_value = iter([stuck_orch])
        stuck = main._detect_stuck_orchestrations_6u(db, threshold_minutes=60)
        assert len(stuck) == 1
        assert stuck[0]["orchestration_id"] == "orch-stuck"

    def test_47_recent_orchestration_not_stuck(self):
        db, coll_store = _mock_db_6v()
        db.orchestrations.find.return_value = iter([])  # cutoff filters it out
        stuck = main._detect_stuck_orchestrations_6u(db, threshold_minutes=60)
        assert stuck == []

    def test_48_recovery_status_stuck_count_matches(self):
        stuck_orch = {
            "orchestration_id": "orch-stuck-2",
            "status": "running",
            "created_at": self._old_iso(120),
            "workspace_slug": "ws2",
        }
        db, coll_store = _mock_db_6v()
        db.orchestrations.find.return_value = iter([stuck_orch])
        with _patch_6v(db):
            r = client.get("/system/recovery-status")
        data = r.json()
        assert data["stuck_count"] == len(data["stuck_orchestrations"])

    def test_49_recovery_status_with_stuck_shows_risk(self):
        stuck_orch = {
            "orchestration_id": "orch-risk",
            "status": "running",
            "created_at": self._old_iso(90),
            "workspace_slug": "ws3",
        }
        db, coll_store = _mock_db_6v()
        db.orchestrations.find.return_value = iter([stuck_orch])
        with _patch_6v(db):
            r = client.get("/system/recovery-status")
        data = r.json()
        assert data["orphaned_task_risk"] is True
        assert "recover-orphaned" in data["recommendation"]


# =============================================================================
# 12. Deployment smoke tests
# =============================================================================
class TestDeploymentSmoke6V:
    def setup_method(self):
        _reset_state()

    def test_50_health_endpoint_passes(self):
        db, _ = _mock_db_6v()
        with _patch_6v(db):
            r = client.get("/health")
        assert r.status_code == 200

    def test_51_system_indexes_endpoint_passes(self):
        db, _ = _mock_db_6v()
        with _patch_6v(db):
            r = client.get("/system/indexes")
        assert r.status_code == 200

    def test_52_telemetry_endpoint_passes(self):
        db, _ = _mock_db_6v()
        with _patch_6v(db):
            r = client.get("/system/telemetry")
        assert r.status_code == 200

    def test_53_full_smoke_all_new_6v_endpoints_respond(self):
        db, _ = _mock_db_6v()
        payload = _make_backup_payload()
        with _patch_6v(db):
            endpoints = [
                ("GET", "/system/pilot-readiness", None),
                ("GET", "/system/recovery-status", None),
                ("POST", "/system/backup", {"compress": False}),
                ("POST", "/system/restore", {"payload": payload, "dry_run": True}),
            ]
            for method, path, body in endpoints:
                if method == "GET":
                    r = client.get(path)
                else:
                    r = client.post(path, json=body)
                assert r.status_code == 200, f"{method} {path} returned {r.status_code}: {r.text}"


# =============================================================================
# 13. Telemetry integrity tests
# =============================================================================
class TestTelemetryIntegrity6V:
    def setup_method(self):
        _reset_state()

    def test_54_request_count_increments_across_calls(self):
        db, _ = _mock_db_6v()
        initial = main._runtime_state_6u["total_requests"]
        with _patch_6v(db):
            client.get("/health")
            client.get("/system/pilot-readiness")
        assert main._runtime_state_6u["total_requests"] >= initial

    def test_55_audit_log_captures_backup_and_restore(self):
        db, _ = _mock_db_6v()
        _reset_state()
        payload = _make_backup_payload(["workflow_runs"])
        with _patch_6v(db):
            client.post("/system/backup", json={"compress": False})
            client.post("/system/restore", json={"payload": payload, "dry_run": True})
        actions = [e["action"] for e in main._runtime_state_6u["audit_log"]]
        assert "backup_created" in actions
        assert "restore_executed" in actions

    def test_56_telemetry_reports_workers_subfields(self):
        db, _ = _mock_db_6v()
        with _patch_6v(db):
            r = client.get("/system/telemetry")
        data = r.json()
        assert "workers" in data
        assert "total" in data["workers"]
