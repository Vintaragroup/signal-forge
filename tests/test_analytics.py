"""Phase 6P: Tests for Operational Analytics & Learning Dashboard."""
from __future__ import annotations

import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from bson import ObjectId

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

import main


# ── Fixtures / Helpers ─────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    return TestClient(main.app)


def _patch(db):
    """Context manager: patch get_client and get_database in main."""
    mongo_client = MagicMock()
    mongo_client.close = MagicMock()
    return patch.multiple(
        "main",
        get_client=lambda: mongo_client,
        get_database=lambda c: db,
    )


def _utc_now():
    return datetime.now(timezone.utc)


_NOW = _utc_now()
_RECENT = _NOW - timedelta(hours=1)
_STALE_APPROVAL = _NOW - timedelta(hours=30)   # older than _BOTTLENECK_APPROVAL_STALE_HOURS (24)
_STALE_WORKFLOW = _NOW - timedelta(hours=60)   # older than _BOTTLENECK_WORKFLOW_STALE_HOURS (48)
_OLD_PROPOSAL = _NOW - timedelta(hours=15)     # older than 12h auto_approve stale threshold


def _matches_analytics(doc: dict, query: dict) -> bool:
    """Minimal MongoDB query matcher supporting exact match + $lt/$gte/$in/$exists operators."""
    for k, v in query.items():
        if k.startswith("$"):
            continue
        dv = doc.get(k)
        if isinstance(v, dict):
            for op, ov in v.items():
                if op == "$lt":
                    if dv is None or dv >= ov:
                        return False
                elif op == "$gte":
                    if dv is None or dv < ov:
                        return False
                elif op == "$in":
                    if dv not in ov:
                        return False
                elif op == "$exists":
                    if ov and dv is None:
                        return False
                    if not ov and dv is not None:
                        return False
        else:
            if dv != v and str(dv) != str(v):
                return False
    return True


def _make_find(items: list[dict]):
    """Return a callable that mimics MongoDB collection.find() with chainable .sort()/.limit()."""
    def find(q=None, *args, **kwargs):
        filtered = [dict(d) for d in items if _matches_analytics(d, q or {})]
        result = MagicMock()
        result.__iter__ = lambda self: iter(filtered)
        result.sort = lambda *a, **kw: result
        result.limit = lambda n: iter(filtered[:n] if isinstance(n, int) else filtered)
        return result
    return find


def _make_analytics_db(
    workflow_runs=None,
    workflow_assets=None,
    approval_requests=None,
    memory_update_proposals=None,
    client_memories=None,
    workspaces=None,
):
    """Build a MagicMock db with all analytics collections wired up."""
    db = MagicMock()

    def _prep(docs):
        result = []
        for d in (docs or []):
            d = dict(d)
            if "_id" not in d:
                d["_id"] = ObjectId()
            result.append(d)
        return result

    _runs = _prep(workflow_runs)
    _assets = _prep(workflow_assets)
    _approvals = _prep(approval_requests)
    _proposals = _prep(memory_update_proposals)
    _memories = _prep(client_memories)
    _workspaces = _prep(workspaces)

    db.workflow_runs.find = _make_find(_runs)
    db.workflow_assets.find = _make_find(_assets)
    db.approval_requests.find = _make_find(_approvals)
    db.memory_update_proposals.find = _make_find(_proposals)
    db.client_memories.find = _make_find(_memories)
    db.workspaces.find = _make_find(_workspaces)

    db.client_memories.find_one = lambda q, *a, **kw: next(
        (dict(m) for m in _memories if _matches_analytics(m, q or {})), None
    )
    db.approval_requests.count_documents = lambda q=None, *a, **kw: sum(
        1 for r in _approvals if _matches_analytics(r, q or {})
    )

    return db


# ── TestWorkflowMetrics ────────────────────────────────────────────────────────

class TestWorkflowMetrics:

    def test_empty_returns_zero_totals(self):
        db = _make_analytics_db()
        result = main.compute_workflow_metrics(db, days=30)
        assert result["total_runs"] == 0
        assert result["completion_rate"] == 0.0
        assert result["failure_rate"] == 0.0

    def test_completion_rate_calculation(self):
        runs = [
            {"workspace_slug": "ws1", "status": "completed", "run_type": "content_build", "created_at": _RECENT},
            {"workspace_slug": "ws1", "status": "completed", "run_type": "content_build", "created_at": _RECENT},
            {"workspace_slug": "ws1", "status": "failed",    "run_type": "discovery",     "created_at": _RECENT},
            {"workspace_slug": "ws1", "status": "needs_review", "run_type": "content_build", "created_at": _RECENT},
        ]
        db = _make_analytics_db(workflow_runs=runs)
        result = main.compute_workflow_metrics(db, days=30)
        assert result["total_runs"] == 4
        assert result["completed_runs"] == 2
        assert result["failed_runs"] == 1
        assert result["needs_review_runs"] == 1
        assert result["completion_rate"] == 0.5
        assert result["failure_rate"] == 0.25

    def test_memory_informed_rate(self):
        runs = [
            {"status": "completed", "client_memory_id": "mem1", "run_type": "content_build", "created_at": _RECENT},
            {"status": "completed", "client_memory_id": "",     "run_type": "content_build", "created_at": _RECENT},
            {"status": "completed",                             "run_type": "content_build", "created_at": _RECENT},
        ]
        db = _make_analytics_db(workflow_runs=runs)
        result = main.compute_workflow_metrics(db, days=30)
        assert result["memory_informed_runs"] == 1
        assert round(result["memory_informed_rate"], 4) == round(1 / 3, 4)

    def test_by_run_type_breakdown(self):
        runs = [
            {"status": "completed", "run_type": "content_build", "created_at": _RECENT},
            {"status": "completed", "run_type": "content_build", "created_at": _RECENT},
            {"status": "completed", "run_type": "discovery",     "created_at": _RECENT},
        ]
        db = _make_analytics_db(workflow_runs=runs)
        result = main.compute_workflow_metrics(db, days=30)
        assert result["by_run_type"]["content_build"] == 2
        assert result["by_run_type"]["discovery"] == 1

    def test_avg_duration_seconds(self):
        s = _NOW - timedelta(seconds=120)
        runs = [
            {"status": "completed", "run_type": "content_build",
             "started_at": s, "completed_at": _NOW, "created_at": _RECENT},
        ]
        db = _make_analytics_db(workflow_runs=runs)
        result = main.compute_workflow_metrics(db, days=30)
        assert result["avg_duration_seconds"] == 120.0

    def test_period_days_returned(self):
        db = _make_analytics_db()
        result = main.compute_workflow_metrics(db, days=7)
        assert result["period_days"] == 7


# ── TestMemoryMetrics ──────────────────────────────────────────────────────────

class TestMemoryMetrics:

    def test_empty_returns_zero_totals(self):
        db = _make_analytics_db()
        result = main.compute_memory_metrics(db, days=30)
        assert result["total_proposals"] == 0
        assert result["approval_rate"] == 0.0

    def test_approval_rate_excludes_pending(self):
        proposals = [
            {"status": "approved", "confidence": 0.9, "created_at": _RECENT},
            {"status": "rejected", "confidence": 0.3, "created_at": _RECENT},
            {"status": "pending",  "confidence": 0.5, "created_at": _RECENT},
        ]
        db = _make_analytics_db(memory_update_proposals=proposals)
        result = main.compute_memory_metrics(db, days=30)
        assert result["approved_proposals"] == 1
        assert result["rejected_proposals"] == 1
        assert result["pending_proposals"] == 1
        assert result["approval_rate"] == 0.5

    def test_governance_suggestion_counts(self):
        proposals = [
            {"status": "pending", "governance_suggestion": "auto_approve", "created_at": _RECENT},
            {"status": "pending", "governance_suggestion": "auto_approve", "created_at": _RECENT},
            {"status": "pending", "governance_suggestion": "auto_reject",  "created_at": _RECENT},
            {"status": "pending", "governance_suggestion": "review",       "created_at": _RECENT},
        ]
        db = _make_analytics_db(memory_update_proposals=proposals)
        result = main.compute_memory_metrics(db, days=30)
        assert result["governance_auto_approve_count"] == 2
        assert result["governance_auto_reject_count"] == 1
        assert result["governance_review_count"] == 1

    def test_avg_confidence(self):
        proposals = [
            {"status": "approved", "confidence": 0.8, "created_at": _RECENT},
            {"status": "rejected", "confidence": 0.4, "created_at": _RECENT},
        ]
        db = _make_analytics_db(memory_update_proposals=proposals)
        result = main.compute_memory_metrics(db, days=30)
        assert result["avg_confidence"] == 0.6

    def test_winning_losing_pattern_aggregation(self):
        memories = [
            {"workspace_slug": "ws1", "winning_patterns": ["pat1", "pat2"], "losing_patterns": ["bad1"]},
            {"workspace_slug": "ws1", "winning_patterns": ["pat3"],         "losing_patterns": []},
        ]
        db = _make_analytics_db(client_memories=memories)
        result = main.compute_memory_metrics(db, days=30)
        assert result["total_winning_patterns"] == 3
        assert result["total_losing_patterns"] == 1

    def test_duplicate_and_conflict_counts(self):
        proposals = [
            {"status": "pending", "is_duplicate": True,                "conflicts": [],      "created_at": _RECENT},
            {"status": "pending", "is_duplicate": False,               "conflicts": [{"f": 1}], "created_at": _RECENT},
            {"status": "pending", "is_duplicate": False,               "conflicts": [],      "created_at": _RECENT},
        ]
        db = _make_analytics_db(memory_update_proposals=proposals)
        result = main.compute_memory_metrics(db, days=30)
        assert result["duplicate_proposals"] == 1
        assert result["conflicted_proposals"] == 1


# ── TestDistributionMetrics ────────────────────────────────────────────────────

class TestDistributionMetrics:

    def test_empty_returns_zero_totals(self):
        db = _make_analytics_db()
        result = main.compute_distribution_metrics(db, days=30)
        assert result["total_assets"] == 0
        assert result["publish_rate"] == 0.0

    def test_publish_rate_calculation(self):
        assets = [
            {"distribution_state": "published",  "created_at": _RECENT},
            {"distribution_state": "published",  "created_at": _RECENT},
            {"distribution_state": "queued",     "created_at": _RECENT},
            {"distribution_state": "not_queued", "created_at": _RECENT},
        ]
        db = _make_analytics_db(workflow_assets=assets)
        result = main.compute_distribution_metrics(db, days=30)
        assert result["published_count"] == 2
        assert result["queued_count"] == 1
        assert result["not_queued_count"] == 1
        assert result["publish_rate"] == 0.5

    def test_by_channel_breakdown(self):
        assets = [
            {"distribution_state": "published", "distribution_channel": "LinkedIn", "created_at": _RECENT},
            {"distribution_state": "published", "distribution_channel": "LinkedIn", "created_at": _RECENT},
            {"distribution_state": "published", "distribution_channel": "Email",    "created_at": _RECENT},
        ]
        db = _make_analytics_db(workflow_assets=assets)
        result = main.compute_distribution_metrics(db, days=30)
        assert result["by_channel"]["LinkedIn"] == 2
        assert result["by_channel"]["Email"] == 1

    def test_archived_counted_separately(self):
        assets = [
            {"distribution_state": "archived", "created_at": _RECENT},
        ]
        db = _make_analytics_db(workflow_assets=assets)
        result = main.compute_distribution_metrics(db, days=30)
        assert result["archived_count"] == 1


# ── TestApprovalMetrics ────────────────────────────────────────────────────────

class TestApprovalMetrics:

    def test_empty_returns_zero_totals(self):
        db = _make_analytics_db()
        result = main.compute_approval_metrics(db, days=30)
        assert result["total_requests"] == 0
        assert result["approval_rate"] == 0.0
        assert result["avg_approval_latency_hours"] is None

    def test_approval_rate_calculation(self):
        requests = [
            {"status": "approved", "module": "contractor_growth", "created_at": _RECENT},
            {"status": "approved", "module": "contractor_growth", "created_at": _RECENT},
            {"status": "rejected", "module": "contractor_growth", "created_at": _RECENT},
        ]
        db = _make_analytics_db(approval_requests=requests)
        result = main.compute_approval_metrics(db, days=30)
        assert result["approved_count"] == 2
        assert result["rejected_count"] == 1
        assert round(result["approval_rate"], 4) == round(2 / 3, 4)

    def test_avg_latency_hours(self):
        created = _NOW - timedelta(hours=4)
        requests = [
            {"status": "approved", "created_at": created, "approved_at": _NOW},
        ]
        db = _make_analytics_db(approval_requests=requests)
        result = main.compute_approval_metrics(db, days=30)
        assert result["avg_approval_latency_hours"] == 4.0

    def test_open_count(self):
        requests = [
            {"status": "open",     "created_at": _RECENT},
            {"status": "open",     "created_at": _RECENT},
            {"status": "approved", "created_at": _RECENT},
        ]
        db = _make_analytics_db(approval_requests=requests)
        result = main.compute_approval_metrics(db, days=30)
        assert result["open_count"] == 2

    def test_by_request_type_breakdown(self):
        requests = [
            {"status": "open", "request_type": "content_asset_review", "created_at": _RECENT},
            {"status": "open", "request_type": "content_asset_review", "created_at": _RECENT},
            {"status": "open", "request_type": "outreach_review",      "created_at": _RECENT},
        ]
        db = _make_analytics_db(approval_requests=requests)
        result = main.compute_approval_metrics(db, days=30)
        assert result["by_request_type"]["content_asset_review"] == 2
        assert result["by_request_type"]["outreach_review"] == 1


# ── TestTemplateMetrics ────────────────────────────────────────────────────────

class TestTemplateMetrics:

    def test_empty_returns_empty_leaderboard(self):
        db = _make_analytics_db()
        result = main.compute_template_metrics(db, days=30)
        assert result["templates"] == []
        assert result["total_modules"] == 0

    def test_module_approval_rate_ranking(self):
        runs = [
            {"workspace_slug": "ws", "inputs": {"module": "artist_growth"},    "status": "completed", "created_at": _RECENT},
            {"workspace_slug": "ws", "inputs": {"module": "insurance_growth"}, "status": "failed",    "created_at": _RECENT},
        ]
        approvals = [
            {"module": "artist_growth",    "status": "approved", "created_at": _RECENT},
            {"module": "artist_growth",    "status": "approved", "created_at": _RECENT},
            {"module": "insurance_growth", "status": "rejected", "created_at": _RECENT},
        ]
        db = _make_analytics_db(workflow_runs=runs, approval_requests=approvals)
        result = main.compute_template_metrics(db, days=30)
        modules = [t["module"] for t in result["templates"]]
        assert "artist_growth" in modules
        assert "insurance_growth" in modules
        # artist_growth (100% approval) should rank higher than insurance_growth (0%)
        assert modules.index("artist_growth") < modules.index("insurance_growth")

    def test_distribution_rate_per_module(self):
        assets = [
            {"module": "media_growth", "distribution_state": "published",  "created_at": _RECENT},
            {"module": "media_growth", "distribution_state": "not_queued", "created_at": _RECENT},
        ]
        db = _make_analytics_db(workflow_assets=assets)
        result = main.compute_template_metrics(db, days=30)
        tpl = next((t for t in result["templates"] if t["module"] == "media_growth"), None)
        assert tpl is not None
        assert tpl["distribution_completion_rate"] == 0.5

    def test_period_days_returned(self):
        db = _make_analytics_db()
        result = main.compute_template_metrics(db, days=90)
        assert result["period_days"] == 90


# ── TestClientHealthMetrics ────────────────────────────────────────────────────

class TestClientHealthMetrics:

    def test_returns_one_workspace_when_slug_specified(self):
        db = _make_analytics_db()
        result = main.compute_client_health_metrics(db, workspace_slug="ws-test", days=30)
        assert result["total_workspaces"] == 1
        assert result["workspaces"][0]["workspace_slug"] == "ws-test"

    def test_zero_score_for_empty_workspace(self):
        db = _make_analytics_db()
        result = main.compute_client_health_metrics(db, workspace_slug="ws-empty", days=30)
        ws = result["workspaces"][0]
        assert ws["overall_health_score"] == 0.0
        assert ws["status"] == "at_risk"

    def test_score_in_valid_range(self):
        runs = [
            {"workspace_slug": "ws-good", "status": "completed", "run_type": "content_build", "created_at": _RECENT},
        ]
        approvals = [
            {"workspace_slug": "ws-good", "status": "approved", "created_at": _RECENT},
        ]
        assets = [
            {"workspace_slug": "ws-good", "distribution_state": "published", "created_at": _RECENT},
        ]
        db = _make_analytics_db(workflow_runs=runs, approval_requests=approvals, workflow_assets=assets)
        result = main.compute_client_health_metrics(db, workspace_slug="ws-good", days=30)
        ws = result["workspaces"][0]
        assert 0.0 <= ws["overall_health_score"] <= 1.0

    def test_period_days_returned(self):
        db = _make_analytics_db()
        result = main.compute_client_health_metrics(db, workspace_slug="ws1", days=7)
        assert result["period_days"] == 7


# ── TestLearningSignals ────────────────────────────────────────────────────────

class TestLearningSignals:

    def test_empty_returns_empty_lists(self):
        db = _make_analytics_db()
        result = main.compute_learning_signals(db, days=30)
        assert result["top_winning_patterns"] == []
        assert result["top_rejected_patterns"] == []
        assert result["top_distribution_channels"] == []

    def test_top_winning_patterns_by_frequency(self):
        memories = [
            {"winning_patterns": ["email outreach", "short copy"]},
            {"winning_patterns": ["email outreach", "social proof"]},
        ]
        db = _make_analytics_db(client_memories=memories)
        result = main.compute_learning_signals(db, days=30)
        top = {item["pattern"]: item["frequency"] for item in result["top_winning_patterns"]}
        assert top["email outreach"] == 2
        assert top["short copy"] == 1
        # highest frequency first
        assert result["top_winning_patterns"][0]["pattern"] == "email outreach"

    def test_top_tone_profiles(self):
        memories = [
            {"voice_tone": {"tone": "professional"}},
            {"voice_tone": {"tone": "professional"}},
            {"voice_tone": {"tone": "casual"}},
        ]
        db = _make_analytics_db(client_memories=memories)
        result = main.compute_learning_signals(db, days=30)
        tones = {item["tone"]: item["workspace_count"] for item in result["top_tone_profiles"]}
        assert tones["professional"] == 2
        assert tones["casual"] == 1

    def test_top_approved_change_fields(self):
        proposals = [
            {"status": "approved", "proposed_change": {"field": "winning_patterns"}, "created_at": _RECENT},
            {"status": "approved", "proposed_change": {"field": "winning_patterns"}, "created_at": _RECENT},
            {"status": "approved", "proposed_change": {"field": "voice_tone"},       "created_at": _RECENT},
        ]
        db = _make_analytics_db(memory_update_proposals=proposals)
        result = main.compute_learning_signals(db, days=30)
        fields = {item["field"]: item["approval_count"] for item in result["top_approved_change_fields"]}
        assert fields["winning_patterns"] == 2
        assert fields["voice_tone"] == 1


# ── TestBottleneckDetection ────────────────────────────────────────────────────

class TestBottleneckDetection:

    def test_no_bottlenecks_when_clean(self):
        approvals = [{"status": "open", "workspace_slug": "ws1", "created_at": _RECENT}]
        db = _make_analytics_db(approval_requests=approvals)
        result = main.compute_bottlenecks(db, workspace_slug="ws1")
        assert result == []

    def test_stuck_approvals_detected(self):
        approvals = [
            {"workspace_slug": "ws1", "status": "open", "created_at": _STALE_APPROVAL},
            {"workspace_slug": "ws1", "status": "open", "created_at": _STALE_APPROVAL},
        ]
        db = _make_analytics_db(approval_requests=approvals)
        result = main.compute_bottlenecks(db, workspace_slug="ws1")
        types = [b["type"] for b in result]
        assert "stuck_approvals" in types

    def test_stale_workflow_runs_detected(self):
        runs = [
            {"workspace_slug": "ws1", "status": "needs_review", "created_at": _STALE_WORKFLOW},
        ]
        db = _make_analytics_db(workflow_runs=runs)
        result = main.compute_bottlenecks(db, workspace_slug="ws1")
        types = [b["type"] for b in result]
        assert "stale_workflow_runs" in types

    def test_unactioned_auto_approve_proposals_detected(self):
        proposals = [
            {
                "workspace_slug": "ws1",
                "status": "pending",
                "governance_suggestion": "auto_approve",
                "created_at": _OLD_PROPOSAL,
            }
        ]
        db = _make_analytics_db(memory_update_proposals=proposals)
        result = main.compute_bottlenecks(db, workspace_slug="ws1")
        types = [b["type"] for b in result]
        assert "unactioned_auto_approve_proposals" in types

    def test_bottlenecks_sorted_high_before_low(self):
        # 6 stuck approvals → severity=high; 1 stale proposal → severity=low
        approvals = [
            {"workspace_slug": "ws1", "status": "open", "created_at": _STALE_APPROVAL}
            for _ in range(6)
        ]
        proposals = [
            {
                "workspace_slug": "ws1",
                "status": "pending",
                "governance_suggestion": "auto_approve",
                "created_at": _OLD_PROPOSAL,
            }
        ]
        db = _make_analytics_db(approval_requests=approvals, memory_update_proposals=proposals)
        result = main.compute_bottlenecks(db, workspace_slug="ws1")
        assert len(result) >= 2
        severity_rank = {"high": 0, "medium": 1, "low": 2}
        ranks = [severity_rank[b["severity"]] for b in result]
        assert ranks == sorted(ranks)

    def test_bottleneck_has_required_fields(self):
        approvals = [
            {"workspace_slug": "ws1", "status": "open", "created_at": _STALE_APPROVAL},
        ]
        db = _make_analytics_db(approval_requests=approvals)
        result = main.compute_bottlenecks(db, workspace_slug="ws1")
        assert len(result) >= 1
        b = result[0]
        for key in ("type", "severity", "count", "description", "workspace_slug", "item_ids", "status"):
            assert key in b


# ── TestAnalyticsEndpoints ────────────────────────────────────────────────────

class TestAnalyticsEndpoints:

    def test_workflows_endpoint_200(self, client):
        db = _make_analytics_db()
        with _patch(db):
            resp = client.get("/analytics/workflows")
        assert resp.status_code == 200
        data = resp.json()
        for key in ("total_runs", "completion_rate", "failure_rate", "memory_informed_rate", "period_days"):
            assert key in data

    def test_memory_endpoint_200(self, client):
        db = _make_analytics_db()
        with _patch(db):
            resp = client.get("/analytics/memory")
        assert resp.status_code == 200
        data = resp.json()
        for key in ("total_proposals", "approval_rate", "avg_confidence", "period_days"):
            assert key in data

    def test_distribution_endpoint_200(self, client):
        db = _make_analytics_db()
        with _patch(db):
            resp = client.get("/analytics/distribution")
        assert resp.status_code == 200
        data = resp.json()
        for key in ("total_assets", "publish_rate", "published_count", "period_days"):
            assert key in data

    def test_approvals_endpoint_200(self, client):
        db = _make_analytics_db()
        with _patch(db):
            resp = client.get("/analytics/approvals")
        assert resp.status_code == 200
        data = resp.json()
        for key in ("total_requests", "approval_rate", "open_count", "period_days"):
            assert key in data

    def test_templates_endpoint_200(self, client):
        db = _make_analytics_db()
        with _patch(db):
            resp = client.get("/analytics/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "templates" in data
        assert "total_modules" in data

    def test_client_health_endpoint_200(self, client):
        db = _make_analytics_db()
        with _patch(db):
            resp = client.get("/analytics/client-health?workspace_slug=test-ws")
        assert resp.status_code == 200
        data = resp.json()
        assert "workspaces" in data
        assert "total_workspaces" in data

    def test_learning_signals_endpoint_200(self, client):
        db = _make_analytics_db()
        with _patch(db):
            resp = client.get("/analytics/learning-signals")
        assert resp.status_code == 200
        data = resp.json()
        for key in ("top_winning_patterns", "top_rejected_patterns", "top_tone_profiles",
                    "top_distribution_channels", "period_days"):
            assert key in data

    def test_bottlenecks_endpoint_200(self, client):
        db = _make_analytics_db()
        with _patch(db):
            resp = client.get("/analytics/bottlenecks")
        assert resp.status_code == 200
        data = resp.json()
        assert "bottlenecks" in data
        assert "total" in data
        assert isinstance(data["bottlenecks"], list)

    def test_workspace_slug_filter(self, client):
        runs = [
            {"workspace_slug": "ws-a", "status": "completed", "run_type": "content_build", "created_at": _RECENT},
            {"workspace_slug": "ws-b", "status": "failed",    "run_type": "content_build", "created_at": _RECENT},
        ]
        db = _make_analytics_db(workflow_runs=runs)
        with _patch(db):
            resp = client.get("/analytics/workflows?workspace_slug=ws-a")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_runs"] == 1
        assert data["completion_rate"] == 1.0

    def test_days_query_param_propagated(self, client):
        db = _make_analytics_db()
        with _patch(db):
            resp = client.get("/analytics/workflows?days=7")
        assert resp.status_code == 200
        assert resp.json()["period_days"] == 7

    def test_days_zero_means_all_time(self, client):
        db = _make_analytics_db()
        with _patch(db):
            resp = client.get("/analytics/workflows?days=0")
        assert resp.status_code == 200
        assert resp.json()["period_days"] == 0

    def test_bottlenecks_with_stuck_approvals(self, client):
        approvals = [
            {"workspace_slug": "ws-x", "status": "open", "created_at": _STALE_APPROVAL},
            {"workspace_slug": "ws-x", "status": "open", "created_at": _STALE_APPROVAL},
        ]
        db = _make_analytics_db(approval_requests=approvals)
        with _patch(db):
            resp = client.get("/analytics/bottlenecks?workspace_slug=ws-x")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any(b["type"] == "stuck_approvals" for b in data["bottlenecks"])

    def test_templates_endpoint_with_data(self, client):
        runs = [
            {"workspace_slug": "ws", "inputs": {"module": "artist_growth"}, "status": "completed", "created_at": _RECENT},
        ]
        approvals = [
            {"workspace_slug": "ws", "module": "artist_growth", "status": "approved", "created_at": _RECENT},
        ]
        db = _make_analytics_db(workflow_runs=runs, approval_requests=approvals)
        with _patch(db):
            resp = client.get("/analytics/templates?workspace_slug=ws")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_modules"] >= 1
        tpl = next((t for t in data["templates"] if t["module"] == "artist_growth"), None)
        assert tpl is not None
        assert tpl["approval_rate"] == 1.0
