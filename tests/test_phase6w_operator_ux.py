"""
tests/test_phase6w_operator_ux.py
Phase 6W — Pilot UX, Operator Experience & Guided Operations
50 tests: activity feed, workspace readiness, explainability, health summary,
demo seeder, role capabilities, deployment smoke, telemetry.
"""

import pytest
from unittest.mock import MagicMock, patch
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


def _mock_db_6w(ping_ok=True, mem_count=2, orch_stuck=0, wf_count=3,
                auto_count=2, rec_pending=2, approval_count=1):
    """Return a fully wired mock DB for Phase 6W tests."""
    db = MagicMock()
    if ping_ok:
        db.command.return_value = {"ok": 1}
    else:
        db.command.side_effect = Exception("connection refused")

    # Real collections the readiness/health-summary checks now read from
    # (client_memories, plural — matches the actual POST /client-memory
    # feature; autonomy_policies — matches PATCH /autonomy/policies/{ws}).
    # "client_memory"/"autonomy_actions" (singular/legacy names) are still
    # stubbed below since the demo seeder writes to those, unrelated to
    # this fix.
    db.client_memories.count_documents.return_value = mem_count
    db.orchestrations.count_documents.return_value = orch_stuck
    db.autonomy_policies.find_one.return_value = {"workspace_slug": "test-ws"} if auto_count > 0 else None
    db.workflow_runs.count_documents.return_value = wf_count
    db.recommendation_statuses.count_documents.return_value = rec_pending
    db.approval_requests.count_documents.return_value = approval_count

    # find() iterators
    db.orchestrations.find.return_value = iter([])
    db.client_memories.find.return_value = iter([])

    # Collection bracket access
    _default = MagicMock()
    _default.find_one.return_value = None
    _default.insert_many.return_value = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda n: getattr(db, n, _default))

    # insert_many on each known collection
    for col in ["workflow_runs", "orchestrations", "recommendation_statuses",
                "autonomy_actions", "client_memory"]:
        getattr(db, col).insert_many.return_value = MagicMock()

    return db


def _patch_6w(db):
    mc = MagicMock()
    mc.close = MagicMock()
    return patch.multiple("main", get_client=lambda: mc, get_database=lambda c: db)


# =============================================================================
# 1. Activity feed helper tests
# =============================================================================
class TestActivityFeedHelper6W:
    def setup_method(self):
        _reset_state()

    def test_01_empty_feed_when_no_events(self):
        db = _mock_db_6w()
        result = main._build_activity_feed_6w(db, None, 50, None)
        assert isinstance(result, list)

    def test_02_audit_log_entries_appear_in_feed(self):
        main._runtime_state_6u["audit_log"].append({
            "ts": "2026-05-13T10:00:00+00:00",
            "action": "backup_created",
            "resource": "system/backup",
            "actor": "operator",
            "trace_id": "t1",
        })
        db = _mock_db_6w()
        result = main._build_activity_feed_6w(db, None, 50, None)
        assert any(e["type"] == "backup_created" for e in result)

    def test_03_severity_filter_applied(self):
        main._runtime_state_6u["audit_log"].extend([
            {"ts": "2026-05-13T10:00:00+00:00", "action": "backup_created", "resource": "r", "actor": "sys", "trace_id": ""},
            {"ts": "2026-05-13T10:01:00+00:00", "action": "rollback_executed", "resource": "r", "actor": "sys", "trace_id": ""},
        ])
        db = _mock_db_6w()
        # Only "info" severity
        result = main._build_activity_feed_6w(db, None, 50, "info")
        assert all(e["severity"] == "info" for e in result)

    def test_04_limit_respected(self):
        for i in range(20):
            main._runtime_state_6u["audit_log"].append({
                "ts": f"2026-05-13T10:{i:02d}:00+00:00",
                "action": "workflow_completed", "resource": "r",
                "actor": "sys", "trace_id": "",
            })
        db = _mock_db_6w()
        result = main._build_activity_feed_6w(db, None, 5, None)
        assert len(result) <= 5

    def test_05_events_sorted_newest_first(self):
        for ts in ["2026-05-13T08:00:00+00:00", "2026-05-13T10:00:00+00:00",
                   "2026-05-13T09:00:00+00:00"]:
            main._runtime_state_6u["audit_log"].append({
                "ts": ts, "action": "workflow_completed",
                "resource": "r", "actor": "sys", "trace_id": "",
            })
        db = _mock_db_6w()
        result = main._build_activity_feed_6w(db, None, 10, None)
        if len(result) >= 2:
            assert result[0]["ts"] >= result[-1]["ts"]


# =============================================================================
# 2. Workspace readiness helper tests
# =============================================================================
class TestWorkspaceReadinessHelper6W:
    def setup_method(self):
        _reset_state()

    def test_06_readiness_returns_score(self):
        db = _mock_db_6w()
        result = main._workspace_readiness_6w(db, "test-ws")
        assert "score" in result
        assert isinstance(result["score"], int)

    def test_07_readiness_has_checks_dict(self):
        db = _mock_db_6w()
        result = main._workspace_readiness_6w(db, "test-ws")
        assert isinstance(result["checks"], dict)
        assert "client_memory_initialized" in result["checks"]

    def test_08_all_checks_pass_gives_high_score(self):
        db = _mock_db_6w(mem_count=5, orch_stuck=0, wf_count=10,
                         auto_count=3, rec_pending=2, approval_count=2)
        result = main._workspace_readiness_6w(db, "test-ws")
        assert result["score"] >= 80

    def test_09_no_memory_reduces_score(self):
        db = _mock_db_6w(mem_count=0)
        result = main._workspace_readiness_6w(db, "test-ws")
        assert result["checks"]["client_memory_initialized"] is False
        assert result["score"] <= 80

    def test_10_missing_checks_appear_in_remediation(self):
        db = _mock_db_6w(mem_count=0, wf_count=0, auto_count=0)
        result = main._workspace_readiness_6w(db, "test-ws")
        assert "client_memory_initialized" in result["remediation"]
        assert "workflows_active" in result["remediation"]

    def test_11_ready_flag_reflects_score_threshold(self):
        db = _mock_db_6w()
        result = main._workspace_readiness_6w(db, "test-ws")
        assert result["ready"] == (result["score"] >= 70)

    def test_12_has_evaluated_at(self):
        db = _mock_db_6w()
        result = main._workspace_readiness_6w(db, "test-ws")
        assert "evaluated_at" in result


# =============================================================================
# 3. Explainability helper tests
# =============================================================================
class TestExplainabilityHelper6W:
    def setup_method(self):
        _reset_state()

    def test_13_unknown_entity_type_returns_explanation(self):
        db = _mock_db_6w()
        result = main._explain_entity_6w(db, "unknown_type", "some-id")
        assert "Unknown entity type" in result["explanation"]
        assert result["found"] is False

    def test_14_not_found_entity_returns_found_false(self):
        db = _mock_db_6w()
        # find_one returns None by default
        db.__getitem__ = MagicMock(side_effect=lambda n: MagicMock(find_one=lambda q: None))
        result = main._explain_entity_6w(db, "recommendation", "nonexistent-id")
        assert result["found"] is False

    def test_15_found_entity_populates_fields(self):
        db = _mock_db_6w()
        mock_col = MagicMock()
        mock_col.find_one.return_value = {
            "recommendation_id": "rec-1",
            "status": "accepted",
            "confidence": 0.9,
            "explanation": "High signal score detected.",
            "workspace_slug": "ws-1",
            "metadata": {"evidence": ["signal > 0.8"], "policy_checks": ["budget_ok"]},
        }
        db.__getitem__ = MagicMock(return_value=mock_col)
        result = main._explain_entity_6w(db, "recommendation", "rec-1")
        assert result["found"] is True
        assert result["confidence"] == 0.9
        assert "signal > 0.8" in result["evidence"]

    def test_16_has_all_required_fields(self):
        db = _mock_db_6w()
        result = main._explain_entity_6w(db, "orchestration", "orch-123")
        for field in ["entity_type", "entity_id", "found", "evidence",
                      "policy_checks", "confidence", "evaluated_at"]:
            assert field in result


# =============================================================================
# 4. Health summary helper tests
# =============================================================================
class TestHealthSummaryHelper6W:
    def setup_method(self):
        _reset_state()

    def test_17_health_summary_returns_dict(self):
        db = _mock_db_6w()
        result = main._health_summary_6w(db)
        assert isinstance(result, dict)

    def test_18_has_all_health_dimensions(self):
        db = _mock_db_6w()
        result = main._health_summary_6w(db)
        for key in ["system_health", "autonomy_confidence", "memory_health",
                    "orchestration_health", "worker_health",
                    "recommendation_quality", "pilot_readiness"]:
            assert key in result

    def test_19_has_indicators_dict(self):
        db = _mock_db_6w()
        result = main._health_summary_6w(db)
        assert "indicators" in result
        assert "mongodb" in result["indicators"]

    def test_20_mongo_failure_sets_error_indicator(self):
        db = _mock_db_6w(ping_ok=False)
        result = main._health_summary_6w(db)
        assert result["indicators"]["mongodb"] == "error"
        assert result["system_health"] < 100

    def test_22_memory_scope_defaults_to_system(self):
        db = _mock_db_6w()
        result = main._health_summary_6w(db)
        assert result["memory_scope"] == "system"
        db.client_memories.count_documents.assert_called_with({})

    def test_23_memory_scope_reflects_workspace_slug(self):
        db = _mock_db_6w()
        result = main._health_summary_6w(db, workspace_slug="ws-scoped")
        assert result["memory_scope"] == "ws-scoped"
        db.client_memories.count_documents.assert_called_with({"workspace_slug": "ws-scoped"})

    def test_21_healthy_system_has_ok_indicators(self):
        db = _mock_db_6w(ping_ok=True)
        result = main._health_summary_6w(db)
        assert result["indicators"]["mongodb"] == "ok"


# =============================================================================
# 5. Demo seed helper tests
# =============================================================================
class TestDemoSeedHelper6W:
    def setup_method(self):
        _reset_state()

    def test_22_seed_returns_created_dict(self):
        db = _mock_db_6w()
        result = main._seed_demo_workspace_6w(db, "test-pilot")
        assert "created" in result
        assert isinstance(result["created"], dict)

    def test_23_seed_creates_workflows(self):
        db = _mock_db_6w()
        result = main._seed_demo_workspace_6w(db, "test-pilot")
        assert result["created"]["workflows"] == main._DEMO_SEED_6W["workflows"]

    def test_24_seed_creates_recommendations(self):
        db = _mock_db_6w()
        result = main._seed_demo_workspace_6w(db, "test-pilot")
        assert result["created"]["recommendations"] == main._DEMO_SEED_6W["recommendations"]

    def test_25_seed_total_entities_correct(self):
        db = _mock_db_6w()
        result = main._seed_demo_workspace_6w(db, "test-pilot")
        assert result["total_entities"] == sum(result["created"].values())

    def test_26_seed_writes_audit_entry(self):
        _reset_state()
        db = _mock_db_6w()
        main._seed_demo_workspace_6w(db, "test-pilot")
        assert any(e["action"] == "demo_workspace_seeded"
                   for e in main._runtime_state_6u["audit_log"])


# =============================================================================
# 6. Role capabilities tests
# =============================================================================
class TestRoleCapabilities6W:
    def test_27_admin_has_most_capabilities(self):
        assert len(main._ROLE_CAPABILITIES_6W["admin"]) > len(
            main._ROLE_CAPABILITIES_6W["observer"])

    def test_28_observer_limited_to_analytics(self):
        caps = main._ROLE_CAPABILITIES_6W["observer"]
        assert caps == ["analytics"]

    def test_29_all_roles_defined(self):
        for role in ["admin", "operator", "reviewer", "observer"]:
            assert role in main._ROLE_CAPABILITIES_6W


# =============================================================================
# 7. Activity feed endpoint tests
# =============================================================================
class TestActivityFeedEndpoint6W:
    def setup_method(self):
        _reset_state()

    def test_30_activity_feed_returns_200(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.get("/activity-feed")
        assert r.status_code == 200

    def test_31_activity_feed_has_events_list(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.get("/activity-feed")
        assert "events" in r.json()

    def test_32_activity_feed_respects_limit_param(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.get("/activity-feed?limit=5")
        assert r.json()["count"] <= 5

    def test_33_activity_feed_workspace_filter(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.get("/activity-feed?workspace_slug=my-ws")
        assert r.status_code == 200


# =============================================================================
# 8. Workspace readiness endpoint tests
# =============================================================================
class TestWorkspaceReadinessEndpoint6W:
    def setup_method(self):
        _reset_state()

    def test_34_readiness_returns_200(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.get("/workspace-readiness?workspace_slug=test-ws")
        assert r.status_code == 200

    def test_35_readiness_has_score(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.get("/workspace-readiness?workspace_slug=test-ws")
        assert "score" in r.json()

    def test_36_readiness_has_ready_flag(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.get("/workspace-readiness?workspace_slug=test-ws")
        assert "ready" in r.json()

    def test_37_readiness_missing_param_422(self):
        r = client.get("/workspace-readiness")
        assert r.status_code == 422


# =============================================================================
# 9. Explainability endpoint tests
# =============================================================================
class TestExplainabilityEndpoint6W:
    def setup_method(self):
        _reset_state()

    def test_38_explainability_returns_200(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.get("/explainability/recommendation/rec-1")
        assert r.status_code == 200

    def test_39_explainability_has_entity_type(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.get("/explainability/orchestration/orch-1")
        assert r.json()["entity_type"] == "orchestration"

    def test_40_explainability_has_found_field(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.get("/explainability/autonomy_action/act-1")
        assert "found" in r.json()

    def test_41_explainability_unknown_type_still_200(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.get("/explainability/unknown_type/some-id")
        assert r.status_code == 200
        assert r.json()["found"] is False


# =============================================================================
# 10. Health summary endpoint tests
# =============================================================================
class TestHealthSummaryEndpoint6W:
    def setup_method(self):
        _reset_state()

    def test_42_health_summary_returns_200(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.get("/health-summary")
        assert r.status_code == 200

    def test_43_health_summary_has_system_health(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.get("/health-summary")
        assert "system_health" in r.json()

    def test_44_health_summary_has_pilot_readiness(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.get("/health-summary")
        assert "pilot_readiness" in r.json()

    def test_44b_health_summary_workspace_slug_scopes_memory(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.get("/health-summary?workspace_slug=ws-endpoint-test")
        assert r.status_code == 200
        assert r.json()["memory_scope"] == "ws-endpoint-test"
        db.client_memories.count_documents.assert_called_with({"workspace_slug": "ws-endpoint-test"})


# =============================================================================
# 11. Demo workspace seed endpoint tests
# =============================================================================
class TestDemoWorkspaceSeedEndpoint6W:
    def setup_method(self):
        _reset_state()

    def test_45_demo_seed_returns_200(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.post("/demo-workspace/seed", json={"workspace_slug": "pilot-demo"})
        assert r.status_code == 200

    def test_46_demo_seed_returns_created(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.post("/demo-workspace/seed", json={"workspace_slug": "pilot-demo"})
        assert "created" in r.json()

    def test_47_demo_seed_default_slug(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            r = client.post("/demo-workspace/seed", json={})
        data = r.json()
        assert data["workspace_slug"] == "demo-workspace"

    def test_48_demo_seed_records_audit(self):
        _reset_state()
        db = _mock_db_6w()
        with _patch_6w(db):
            client.post("/demo-workspace/seed", json={"workspace_slug": "qa-demo"})
        assert any(e["action"] == "demo_workspace_seeded"
                   for e in main._runtime_state_6u["audit_log"])


# =============================================================================
# 12. Role capabilities endpoint tests
# =============================================================================
class TestRoleCapabilitiesEndpoint6W:
    def test_49_role_capabilities_valid_role(self):
        r = client.get("/role-capabilities?role=admin")
        assert r.status_code == 200
        assert "capabilities" in r.json()

    def test_50_role_capabilities_observer(self):
        r = client.get("/role-capabilities?role=observer")
        assert r.status_code == 200
        assert r.json()["capabilities"] == ["analytics"]

    def test_51_role_capabilities_unknown_role_400(self):
        r = client.get("/role-capabilities?role=superuser")
        assert r.status_code == 400

    def test_52_role_capabilities_all_roles_listed(self):
        r = client.get("/role-capabilities?role=operator")
        data = r.json()
        assert set(data["all_roles"]) == {"admin", "operator", "reviewer", "observer"}


# =============================================================================
# 13. Deployment smoke tests
# =============================================================================
class TestDeploymentSmoke6W:
    def setup_method(self):
        _reset_state()

    def test_53_all_six_new_endpoints_respond(self):
        db = _mock_db_6w()
        with _patch_6w(db):
            checks = [
                ("GET",  "/activity-feed",                       None),
                ("GET",  "/workspace-readiness?workspace_slug=x", None),
                ("GET",  "/explainability/recommendation/r-1",   None),
                ("GET",  "/health-summary",                       None),
                ("POST", "/demo-workspace/seed",                  {"workspace_slug": "smoke"}),
                ("GET",  "/role-capabilities?role=operator",      None),
            ]
            for method, path, body in checks:
                r = client.get(path) if method == "GET" else client.post(path, json=body)
                assert r.status_code == 200, (
                    f"{method} {path} → {r.status_code}: {r.text[:200]}"
                )

    def test_54_6w_endpoints_listed_in_openapi(self):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        paths = r.json()["paths"]
        assert "/activity-feed" in paths
        assert "/workspace-readiness" in paths
        assert "/health-summary" in paths
        assert "/role-capabilities" in paths
