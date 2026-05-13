"""
tests/test_autonomy.py — Phase 6R: Autonomous Execution Policies & Safe Auto-Optimization

Coverage:
  - evaluate_autonomy_policy: confidence thresholds, risk levels, safety guardrails, pause/disable
  - simulate_autonomy_action: expected changes, risk info, rollback info
  - _get_effective_policy: global defaults, workspace overrides
  - _compute_autonomy_analytics: rate calculations, breakdowns
  - Endpoints: GET/PATCH /autonomy/policies, GET /autonomy/actions,
               GET /autonomy/actions/{id}, POST /autonomy/actions/{id}/rollback,
               POST /autonomy/pause, POST /autonomy/resume, GET /autonomy/analytics
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

import main
from main import (
    _AUTO_MIN_CONFIDENCE,
    _AUTO_MIN_EVIDENCE,
    _DEFAULT_GLOBAL_POLICY,
    _SAFETY_BLOCKED_ACTIONS,
    _compute_autonomy_analytics,
    _get_effective_policy,
    _is_autonomy_paused,
    evaluate_autonomy_policy,
    simulate_autonomy_action,
    app,
)

# ── Fixtures & Helpers ────────────────────────────────────────────────────────

_NOW = datetime.now(timezone.utc)


def _patch(db):
    mongo_client = MagicMock()
    mongo_client.close = MagicMock()
    return patch.multiple("main", get_client=lambda: mongo_client, get_database=lambda c: db)


def _mock_db(
    state_doc=None,
    global_policy_doc=None,
    ws_policy_doc=None,
    ws_slug=None,
    actions=None,
    action_by_id=None,
):
    """Create a mock db with autonomy collections pre-configured."""
    db = MagicMock()

    # autonomy_state
    db.autonomy_state.find_one.return_value = state_doc
    db.autonomy_state.update_one.return_value = MagicMock()

    # autonomy_policies — find_one returns based on workspace_slug filter
    def _policy_find_one(query, *args, **kwargs):
        ws = query.get("workspace_slug", "")
        if ws == "__global__":
            return global_policy_doc
        if ws == ws_slug:
            return ws_policy_doc
        return None

    db.autonomy_policies.find_one.side_effect = _policy_find_one
    db.autonomy_policies.update_one.return_value = MagicMock()

    # For listing workspace-specific policies
    non_global_policies = []
    if ws_policy_doc:
        non_global_policies.append(ws_policy_doc)
    _pf = MagicMock()
    _pf.__iter__ = MagicMock(side_effect=lambda: iter(non_global_policies))
    db.autonomy_policies.find.return_value = _pf

    # autonomy_action_logs
    action_list = list(actions or [])
    _af = MagicMock()
    _af.sort.return_value = _af
    _af.limit.side_effect = lambda n: iter(action_list[:n])
    _af.__iter__ = MagicMock(side_effect=lambda: iter(action_list))
    db.autonomy_action_logs.find.return_value = _af
    db.autonomy_action_logs.find_one.return_value = action_by_id
    db.autonomy_action_logs.update_one.return_value = MagicMock()

    return db


def _default_policy(**overrides):
    p = dict(_DEFAULT_GLOBAL_POLICY)
    p["require_review_for"] = []  # empty for most tests
    p.update(overrides)
    return p


@pytest.fixture
def client():
    return TestClient(app)


def _make_action(status="applied", action_type="auto_archive_stale_workflows",
                 risk_level="low", rollback_supported=True, workspace_slug="ws"):
    return {
        "id": "abc123def456ghi7",
        "action_type": action_type,
        "workspace_slug": workspace_slug,
        "risk_level": risk_level,
        "confidence_score": 0.95,
        "evidence_count": 5,
        "status": status,
        "rollback_supported": rollback_supported,
        "created_at": _NOW.isoformat(),
        "applied_at": None,
        "rolled_back_at": None,
    }


# ── TestIsAutonomyPaused ───────────────────────────────────────────────────────

class TestIsAutonomyPaused:

    def test_returns_false_when_no_state_doc(self):
        db = _mock_db(state_doc=None)
        assert _is_autonomy_paused(db) is False

    def test_returns_true_when_paused(self):
        db = _mock_db(state_doc={"_id": "global", "paused": True})
        assert _is_autonomy_paused(db) is True

    def test_returns_false_when_explicitly_not_paused(self):
        db = _mock_db(state_doc={"_id": "global", "paused": False})
        assert _is_autonomy_paused(db) is False


# ── TestGetEffectivePolicy ─────────────────────────────────────────────────────

class TestGetEffectivePolicy:

    def test_returns_defaults_when_no_stored_policy(self):
        db = _mock_db()
        policy = _get_effective_policy("", db)
        assert policy["autonomy_enabled"] is True
        assert policy["max_autonomy_risk"] == "low"
        assert policy["auto_apply_threshold"] == 0.90

    def test_global_stored_policy_overrides_defaults(self):
        db = _mock_db(global_policy_doc={"workspace_slug": "__global__", "max_autonomy_risk": "medium"})
        policy = _get_effective_policy("", db)
        assert policy["max_autonomy_risk"] == "medium"
        # Other defaults preserved
        assert policy["auto_apply_threshold"] == 0.90

    def test_workspace_policy_overrides_global(self):
        db = _mock_db(
            global_policy_doc={"workspace_slug": "__global__", "auto_apply_threshold": 0.85},
            ws_policy_doc={"workspace_slug": "ws-a", "auto_apply_threshold": 0.95},
            ws_slug="ws-a",
        )
        policy = _get_effective_policy("ws-a", db)
        assert policy["auto_apply_threshold"] == 0.95

    def test_workspace_slug_global_not_re_merged(self):
        db = _mock_db(
            ws_policy_doc={"workspace_slug": "__global__", "autonomy_enabled": False},
            ws_slug="__global__",
        )
        # Passing "__global__" as workspace_slug should not double-merge
        policy = _get_effective_policy("__global__", db)
        assert isinstance(policy, dict)


# ── TestEvaluateAutonomyPolicy ─────────────────────────────────────────────────

class TestEvaluateAutonomyPolicy:

    def test_auto_apply_low_risk_high_confidence(self):
        db = _mock_db()
        with patch("main._is_autonomy_paused", return_value=False), \
             patch("main._get_effective_policy", return_value=_default_policy()):
            result = evaluate_autonomy_policy(
                "auto_archive_stale_workflows", 0.95, 5, "ws", db
            )
        assert result["allowed"] is True
        assert result["requires_review"] is False
        assert result["reason"] == "auto_apply"

    def test_blocked_when_globally_paused(self):
        db = _mock_db()
        with patch("main._is_autonomy_paused", return_value=True):
            result = evaluate_autonomy_policy(
                "auto_archive_stale_workflows", 0.95, 5, "ws", db
            )
        assert result["allowed"] is False
        assert result["reason"] == "autonomy_paused"

    def test_blocked_when_autonomy_disabled(self):
        db = _mock_db()
        with patch("main._is_autonomy_paused", return_value=False), \
             patch("main._get_effective_policy", return_value=_default_policy(autonomy_enabled=False)):
            result = evaluate_autonomy_policy(
                "auto_archive_stale_workflows", 0.95, 5, "ws", db
            )
        assert result["allowed"] is False
        assert result["reason"] == "autonomy_disabled"

    def test_hard_blocked_by_safety_guardrail(self):
        db = _mock_db()
        with patch("main._is_autonomy_paused", return_value=False), \
             patch("main._get_effective_policy", return_value=_default_policy()):
            result = evaluate_autonomy_policy(
                "blocked_claim_changes", 0.99, 10, "ws", db
            )
        assert result["allowed"] is False
        assert result["reason"] == "safety_guardrail"

    def test_requires_review_when_risk_exceeds_max(self):
        db = _mock_db()
        with patch("main._is_autonomy_paused", return_value=False), \
             patch("main._get_effective_policy", return_value=_default_policy(max_autonomy_risk="low")):
            # medium-risk action vs low max policy
            result = evaluate_autonomy_policy(
                "auto_promote_high_confidence_patterns", 0.95, 5, "ws", db
            )
        assert result["allowed"] is True
        assert result["requires_review"] is True
        assert result["reason"] == "risk_exceeds_policy"

    def test_medium_risk_allowed_when_max_is_medium(self):
        db = _mock_db()
        with patch("main._is_autonomy_paused", return_value=False), \
             patch("main._get_effective_policy", return_value=_default_policy(max_autonomy_risk="medium")):
            result = evaluate_autonomy_policy(
                "auto_promote_high_confidence_patterns", 0.95, 5, "ws", db
            )
        assert result["allowed"] is True
        assert result["requires_review"] is False

    def test_requires_review_when_in_require_review_list(self):
        db = _mock_db()
        policy = _default_policy(require_review_for=["auto_archive_stale_workflows"])
        with patch("main._is_autonomy_paused", return_value=False), \
             patch("main._get_effective_policy", return_value=policy):
            result = evaluate_autonomy_policy(
                "auto_archive_stale_workflows", 0.95, 5, "ws", db
            )
        assert result["allowed"] is True
        assert result["requires_review"] is True
        assert result["reason"] == "policy_requires_review"

    def test_requires_review_when_confidence_below_threshold(self):
        db = _mock_db()
        with patch("main._is_autonomy_paused", return_value=False), \
             patch("main._get_effective_policy", return_value=_default_policy(auto_apply_threshold=0.90)):
            result = evaluate_autonomy_policy(
                "auto_archive_stale_workflows", 0.75, 5, "ws", db
            )
        assert result["allowed"] is True
        assert result["requires_review"] is True
        assert result["reason"] == "confidence_below_threshold"

    def test_requires_review_when_insufficient_evidence(self):
        db = _mock_db()
        with patch("main._is_autonomy_paused", return_value=False), \
             patch("main._get_effective_policy", return_value=_default_policy()):
            result = evaluate_autonomy_policy(
                "auto_archive_stale_workflows", 0.95, 2, "ws", db
            )
        assert result["allowed"] is True
        assert result["requires_review"] is True
        assert result["reason"] == "insufficient_evidence"

    def test_result_includes_policy(self):
        db = _mock_db()
        pol = _default_policy()
        with patch("main._is_autonomy_paused", return_value=False), \
             patch("main._get_effective_policy", return_value=pol):
            result = evaluate_autonomy_policy(
                "auto_archive_stale_workflows", 0.95, 5, "ws", db
            )
        assert "policy" in result
        assert result["policy"] == pol


# ── TestSafetyGuardrails ───────────────────────────────────────────────────────

class TestSafetyGuardrails:

    @pytest.mark.parametrize("blocked_type", sorted(_SAFETY_BLOCKED_ACTIONS))
    def test_each_blocked_action_type_is_hard_blocked(self, blocked_type):
        db = _mock_db()
        with patch("main._is_autonomy_paused", return_value=False), \
             patch("main._get_effective_policy", return_value=_default_policy()):
            result = evaluate_autonomy_policy(blocked_type, 0.99, 99, "ws", db)
        assert result["allowed"] is False
        assert result["reason"] == "safety_guardrail"

    def test_safety_block_not_overridable_by_policy(self):
        """Even with max_autonomy_risk=high, safety-blocked actions must be rejected."""
        db = _mock_db()
        permissive_policy = _default_policy(
            max_autonomy_risk="high",
            auto_apply_threshold=0.0,
        )
        with patch("main._is_autonomy_paused", return_value=False), \
             patch("main._get_effective_policy", return_value=permissive_policy):
            result = evaluate_autonomy_policy("delete_workflow_history", 1.0, 100, "ws", db)
        assert result["allowed"] is False


# ── TestSimulateAutonomyAction ─────────────────────────────────────────────────

class TestSimulateAutonomyAction:

    def test_returns_expected_changes_list(self):
        db = _mock_db()
        result = simulate_autonomy_action(
            "auto_archive_stale_workflows", "ws", {"days": 14}, db
        )
        assert isinstance(result["expected_changes"], list)
        assert len(result["expected_changes"]) >= 1

    def test_returns_correct_risk_level(self):
        db = _mock_db()
        result = simulate_autonomy_action(
            "auto_promote_high_confidence_patterns", "ws", {}, db
        )
        assert result["risk_level"] == "medium"
        assert result["rollback_supported"] is True

    def test_rollback_complexity_none_for_non_rollbackable(self):
        db = _mock_db()
        result = simulate_autonomy_action("auto_escalate_bottlenecks", "ws", {}, db)
        assert result["rollback_complexity"] == "none"
        assert result["rollback_supported"] is False

    def test_rollback_complexity_simple_for_low_risk(self):
        db = _mock_db()
        result = simulate_autonomy_action(
            "auto_archive_stale_workflows", "ws", {}, db
        )
        assert result["rollback_complexity"] == "simple"

    def test_rollback_complexity_moderate_for_medium_risk(self):
        db = _mock_db()
        result = simulate_autonomy_action(
            "auto_recommend_template_switch", "ws",
            {"current_template": "A", "target_template": "B"}, db
        )
        assert result["rollback_complexity"] == "moderate"

    def test_impact_summary_is_non_empty(self):
        db = _mock_db()
        result = simulate_autonomy_action(
            "auto_merge_duplicate_memory_entries", "ws", {"duplicate_count": 3}, db
        )
        assert result["impact_summary"].startswith("This change would:")

    def test_unknown_action_type_returns_generic_change(self):
        db = _mock_db()
        result = simulate_autonomy_action("unknown_future_action", "ws", {}, db)
        assert result["expected_changes"] == ["Apply change"]
        assert result["risk_level"] == "unknown"

    def test_params_preserved_in_result(self):
        db = _mock_db()
        params = {"channel": "linkedin", "estimated_confidence_gain": 0.12}
        result = simulate_autonomy_action(
            "auto_prioritize_distribution_channel", "ws", params, db
        )
        assert result["params"] == params
        assert result["estimated_confidence_gain"] == 0.12


# ── TestComputeAutonomyAnalytics ───────────────────────────────────────────────

class TestComputeAutonomyAnalytics:

    def test_empty_returns_zeros(self):
        db = _mock_db(actions=[], state_doc=None)
        result = _compute_autonomy_analytics(db, "", 30)
        assert result["total_actions"] == 0
        assert result["applied_actions"] == 0
        assert result["auto_apply_success_rate"] == 0.0
        assert result["rollback_rate"] == 0.0

    def test_correct_applied_count(self):
        actions = [
            _make_action(status="applied"),
            _make_action(status="auto_applied"),
            _make_action(status="pending"),
        ]
        db = _mock_db(actions=actions)
        result = _compute_autonomy_analytics(db, "", 0)
        assert result["applied_actions"] == 2
        assert result["pending_actions"] == 1

    def test_rollback_rate_calculation(self):
        actions = [
            _make_action(status="applied"),
            _make_action(status="applied"),
            _make_action(status="rolled_back"),
        ]
        db = _mock_db(actions=actions)
        result = _compute_autonomy_analytics(db, "", 0)
        assert result["rolled_back_actions"] == 1
        # rollback_rate = 1 / 2 (applied only, not rolled_back in denominator)
        assert result["rollback_rate"] == 0.5

    def test_by_action_type_breakdown(self):
        actions = [
            _make_action(action_type="auto_archive_stale_workflows"),
            _make_action(action_type="auto_archive_stale_workflows"),
            _make_action(action_type="auto_escalate_bottlenecks"),
        ]
        db = _mock_db(actions=actions)
        result = _compute_autonomy_analytics(db, "", 0)
        assert result["by_action_type"]["auto_archive_stale_workflows"] == 2
        assert result["by_action_type"]["auto_escalate_bottlenecks"] == 1

    def test_by_risk_level_breakdown(self):
        actions = [
            _make_action(risk_level="low"),
            _make_action(risk_level="low"),
            _make_action(risk_level="medium"),
        ]
        db = _mock_db(actions=actions)
        result = _compute_autonomy_analytics(db, "", 0)
        assert result["by_risk_level"]["low"] == 2
        assert result["by_risk_level"]["medium"] == 1

    def test_autonomy_paused_reflected(self):
        db = _mock_db(state_doc={"_id": "global", "paused": True})
        result = _compute_autonomy_analytics(db, "", 0)
        assert result["autonomy_paused"] is True

    def test_blocked_count(self):
        actions = [
            _make_action(status="blocked"),
            _make_action(status="auto_blocked"),
            _make_action(status="applied"),
        ]
        db = _mock_db(actions=actions)
        result = _compute_autonomy_analytics(db, "", 0)
        assert result["blocked_actions"] == 2


# ── TestAutonomyPoliciesEndpoints ──────────────────────────────────────────────

class TestAutonomyPoliciesEndpoints:

    def test_get_policies_returns_global_default(self, client):
        db = _mock_db()
        with _patch(db):
            resp = client.get("/autonomy/policies")
        assert resp.status_code == 200
        data = resp.json()
        assert "policies" in data
        assert len(data["policies"]) >= 1
        global_pol = data["policies"][0]
        assert global_pol["workspace_slug"] == "__global__"

    def test_get_policies_includes_paused_flag(self, client):
        db = _mock_db()
        with _patch(db):
            resp = client.get("/autonomy/policies")
        assert "autonomy_paused" in resp.json()

    def test_patch_global_policy_returns_updated(self, client):
        db = _mock_db()
        with _patch(db):
            resp = client.patch(
                "/autonomy/policies/__global__",
                json={"max_autonomy_risk": "medium", "auto_apply_threshold": 0.85},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "policy" in data
        assert data["workspace"] == "__global__"

    def test_patch_workspace_policy_returns_updated(self, client):
        db = _mock_db()
        with _patch(db):
            resp = client.patch(
                "/autonomy/policies/my-workspace",
                json={"autonomy_enabled": False},
            )
        assert resp.status_code == 200
        assert resp.json()["workspace"] == "my-workspace"


# ── TestAutonomyActionsEndpoints ───────────────────────────────────────────────

class TestAutonomyActionsEndpoints:

    def test_list_actions_returns_empty(self, client):
        db = _mock_db(actions=[])
        with _patch(db):
            resp = client.get("/autonomy/actions")
        assert resp.status_code == 200
        assert resp.json()["actions"] == []
        assert resp.json()["total"] == 0

    def test_list_actions_returns_items(self, client):
        actions = [_make_action(), _make_action(status="pending")]
        db = _mock_db(actions=actions)
        with _patch(db):
            resp = client.get("/autonomy/actions")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_list_filters_accepted_by_api(self, client):
        db = _mock_db(actions=[])
        with _patch(db):
            resp = client.get("/autonomy/actions?status=pending&action_type=auto_escalate_bottlenecks")
        assert resp.status_code == 200

    def test_get_action_by_id_returns_doc(self, client):
        action = _make_action()
        db = _mock_db(action_by_id=action)
        with _patch(db):
            resp = client.get(f"/autonomy/actions/{action['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == action["id"]

    def test_get_action_not_found_returns_404(self, client):
        db = _mock_db(action_by_id=None)
        with _patch(db):
            resp = client.get("/autonomy/actions/nonexistent123")
        assert resp.status_code == 404


# ── TestRollbackEndpoint ───────────────────────────────────────────────────────

class TestRollbackEndpoint:

    def test_rollback_applied_action_returns_rolled_back(self, client):
        action = _make_action(status="applied", rollback_supported=True)
        db = _mock_db(action_by_id=action)
        with _patch(db):
            resp = client.post(f"/autonomy/actions/{action['id']}/rollback")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rolled_back"

    def test_rollback_auto_applied_action_succeeds(self, client):
        action = _make_action(status="auto_applied", rollback_supported=True)
        db = _mock_db(action_by_id=action)
        with _patch(db):
            resp = client.post(f"/autonomy/actions/{action['id']}/rollback")
        assert resp.status_code == 200

    def test_rollback_not_found_returns_404(self, client):
        db = _mock_db(action_by_id=None)
        with _patch(db):
            resp = client.post("/autonomy/actions/doesnotexist/rollback")
        assert resp.status_code == 404

    def test_rollback_pending_action_returns_400(self, client):
        action = _make_action(status="pending")
        db = _mock_db(action_by_id=action)
        with _patch(db):
            resp = client.post(f"/autonomy/actions/{action['id']}/rollback")
        assert resp.status_code == 400

    def test_rollback_unsupported_type_returns_400(self, client):
        action = _make_action(
            status="applied",
            action_type="auto_escalate_bottlenecks",
            rollback_supported=False,
        )
        db = _mock_db(action_by_id=action)
        with _patch(db):
            resp = client.post(f"/autonomy/actions/{action['id']}/rollback")
        assert resp.status_code == 400

    def test_rollback_updates_action_in_db(self, client):
        action = _make_action(status="applied")
        db = _mock_db(action_by_id=action)
        with _patch(db):
            client.post(f"/autonomy/actions/{action['id']}/rollback")
        db.autonomy_action_logs.update_one.assert_called_once()
        call_args = db.autonomy_action_logs.update_one.call_args
        assert call_args[0][1]["$set"]["status"] == "rolled_back"


# ── TestPauseResumeEndpoints ───────────────────────────────────────────────────

class TestPauseResumeEndpoints:

    def test_pause_returns_paused_true(self, client):
        db = _mock_db()
        with _patch(db):
            resp = client.post("/autonomy/pause")
        assert resp.status_code == 200
        assert resp.json()["autonomy_paused"] is True

    def test_resume_returns_paused_false(self, client):
        db = _mock_db()
        with _patch(db):
            resp = client.post("/autonomy/resume")
        assert resp.status_code == 200
        assert resp.json()["autonomy_paused"] is False

    def test_pause_writes_to_db(self, client):
        db = _mock_db()
        with _patch(db):
            client.post("/autonomy/pause")
        db.autonomy_state.update_one.assert_called_once()
        call_args = db.autonomy_state.update_one.call_args
        assert call_args[0][1]["$set"]["paused"] is True

    def test_resume_writes_to_db(self, client):
        db = _mock_db()
        with _patch(db):
            client.post("/autonomy/resume")
        db.autonomy_state.update_one.assert_called_once()
        call_args = db.autonomy_state.update_one.call_args
        assert call_args[0][1]["$set"]["paused"] is False


# ── TestAutonomyAnalyticsEndpoint ──────────────────────────────────────────────

class TestAutonomyAnalyticsEndpoint:

    def test_analytics_endpoint_returns_200(self, client):
        db = _mock_db(actions=[])
        with _patch(db):
            resp = client.get("/autonomy/analytics")
        assert resp.status_code == 200

    def test_analytics_has_required_fields(self, client):
        db = _mock_db(actions=[])
        with _patch(db):
            data = client.get("/autonomy/analytics").json()
        for field in [
            "total_actions", "applied_actions", "rolled_back_actions",
            "blocked_actions", "pending_actions", "auto_apply_success_rate",
            "rollback_rate", "by_action_type", "by_risk_level",
            "autonomy_paused", "days",
        ]:
            assert field in data, f"Missing field: {field}"

    def test_analytics_with_data(self, client):
        actions = [
            _make_action(status="auto_applied"),
            _make_action(status="pending"),
            _make_action(status="blocked"),
        ]
        db = _mock_db(actions=actions)
        with _patch(db):
            data = client.get("/autonomy/analytics?days=30").json()
        assert data["total_actions"] == 3
        assert data["pending_actions"] == 1
        assert data["blocked_actions"] == 1

    def test_analytics_workspace_slug_param_accepted(self, client):
        db = _mock_db(actions=[])
        with _patch(db):
            resp = client.get("/autonomy/analytics?workspace_slug=test-ws&days=7")
        assert resp.status_code == 200
        assert resp.json()["days"] == 7
