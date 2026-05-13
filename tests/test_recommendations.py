"""
tests/test_recommendations.py — Phase 6Q: Autonomous Optimization & Recommendation Engine

Coverage:
  - generate_workflow_recommendations
  - generate_memory_recommendations
  - generate_template_recommendations
  - generate_distribution_recommendations
  - generate_operational_recommendations
  - generate_cross_client_signals
  - _collect_all_recommendations (lifecycle merge)
  - recommendation endpoints: list, summary, cross-client-signals, get, accept, dismiss, apply
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
    _collect_all_recommendations,
    _rec_id,
    generate_cross_client_signals,
    generate_distribution_recommendations,
    generate_memory_recommendations,
    generate_operational_recommendations,
    generate_template_recommendations,
    generate_workflow_recommendations,
    app,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_NOW = datetime.now(timezone.utc)


def _patch(db):
    mongo_client = MagicMock()
    mongo_client.close = MagicMock()
    return patch.multiple("main", get_client=lambda: mongo_client, get_database=lambda c: db)


def _mock_db():
    """Minimal db mock with empty collections and recommendation_statuses support."""
    db = MagicMock()
    db.recommendation_statuses.find.return_value = iter([])
    db.recommendation_statuses.find_one.return_value = None
    db.recommendation_statuses.update_one.return_value = MagicMock()
    return db


@pytest.fixture
def client():
    return TestClient(app)


# ── Helpers: mock return values for compute functions ─────────────────────────

def _wf_metrics(**kwargs):
    base = {
        "total_runs": 10,
        "completed_runs": 8,
        "failed_runs": 2,
        "needs_review_runs": 0,
        "completion_rate": 0.8,
        "failure_rate": 0.2,
        "avg_duration_seconds": 60.0,
        "memory_informed_runs": 8,
        "memory_informed_rate": 0.8,
        "by_run_type": {},
        "period_days": 30,
    }
    base.update(kwargs)
    return base


def _mem_metrics(**kwargs):
    base = {
        "total_proposals": 10,
        "approved_proposals": 6,
        "rejected_proposals": 2,
        "pending_proposals": 2,
        "approval_rate": 0.75,
        "rejection_rate": 0.25,
        "avg_confidence": 0.8,
        "governance_auto_approve_count": 4,
        "governance_auto_reject_count": 1,
        "governance_review_count": 5,
        "duplicate_proposals": 0,
        "conflicted_proposals": 0,
        "total_winning_patterns": 5,
        "total_losing_patterns": 2,
        "total_blocked_claims": 0,
        "memory_count": 3,
        "period_days": 30,
    }
    base.update(kwargs)
    return base


def _dist_metrics(**kwargs):
    base = {
        "total_assets": 20,
        "published_count": 16,
        "queued_count": 2,
        "archived_count": 1,
        "not_queued_count": 1,
        "publish_rate": 0.8,
        "queue_rate": 0.1,
        "by_asset_type": {},
        "by_channel": {"linkedin": 10, "email": 6},
        "period_days": 30,
    }
    base.update(kwargs)
    return base


def _tmpl_metrics(**kwargs):
    base = {
        "templates": [
            {
                "module": "artist_growth",
                "workflow_runs": 5,
                "workflow_completion_rate": 0.8,
                "total_assets": 5,
                "total_approvals": 5,
                "approval_rate": 0.9,
                "rejection_rate": 0.1,
                "distribution_completion_rate": 0.8,
                "avg_memory_proposal_confidence": 0.85,
            },
            {
                "module": "media_growth",
                "workflow_runs": 4,
                "workflow_completion_rate": 0.75,
                "total_assets": 4,
                "total_approvals": 4,
                "approval_rate": 0.5,
                "rejection_rate": 0.5,
                "distribution_completion_rate": 0.5,
                "avg_memory_proposal_confidence": 0.6,
            },
        ],
        "total_modules": 2,
        "period_days": 30,
    }
    base.update(kwargs)
    return base


def _health_metrics(**kwargs):
    base = {
        "workspaces": [],
        "total_workspaces": 0,
        "period_days": 30,
    }
    base.update(kwargs)
    return base


# ── TestGenerateWorkflowRecommendations ───────────────────────────────────────

class TestGenerateWorkflowRecommendations:

    def test_no_runs_returns_empty(self):
        db = _mock_db()
        with patch("main.compute_workflow_metrics", return_value=_wf_metrics(total_runs=0)):
            recs = generate_workflow_recommendations(db, "ws", 30)
        assert recs == []

    def test_low_completion_rate_triggers_recommendation(self):
        db = _mock_db()
        metrics = _wf_metrics(total_runs=10, failed_runs=4, completion_rate=0.6)
        with patch("main.compute_workflow_metrics", return_value=metrics):
            recs = generate_workflow_recommendations(db, "ws", 30)
        types = [r["recommendation_type"] for r in recs]
        assert "workflow_optimization" in types
        rec = next(r for r in recs if r["recommendation_type"] == "workflow_optimization" and "Completion" in r["title"])
        assert rec["impact_estimate"] == "high"
        assert rec["confidence_score"] >= 0.85

    def test_high_avg_duration_triggers_recommendation(self):
        db = _mock_db()
        metrics = _wf_metrics(avg_duration_seconds=400.0)
        with patch("main.compute_workflow_metrics", return_value=metrics):
            recs = generate_workflow_recommendations(db, "ws", 30)
        assert any("Duration" in r["title"] for r in recs)

    def test_low_memory_rate_triggers_recommendation(self):
        db = _mock_db()
        metrics = _wf_metrics(total_runs=5, memory_informed_rate=0.2)
        with patch("main.compute_workflow_metrics", return_value=metrics):
            recs = generate_workflow_recommendations(db, "ws", 30)
        assert any("Memory" in r["title"] for r in recs)

    def test_needs_review_backlog_triggers_bottleneck_rec(self):
        db = _mock_db()
        metrics = _wf_metrics(needs_review_runs=8)
        with patch("main.compute_workflow_metrics", return_value=metrics):
            recs = generate_workflow_recommendations(db, "ws", 30)
        assert any(r["recommendation_type"] == "bottleneck_remediation" for r in recs)

    def test_good_metrics_returns_no_recs(self):
        db = _mock_db()
        with patch("main.compute_workflow_metrics", return_value=_wf_metrics()):
            recs = generate_workflow_recommendations(db, "ws", 30)
        assert recs == []

    def test_recommendation_has_required_fields(self):
        db = _mock_db()
        metrics = _wf_metrics(completion_rate=0.5, total_runs=10)
        with patch("main.compute_workflow_metrics", return_value=metrics):
            recs = generate_workflow_recommendations(db, "ws", 30)
        assert len(recs) >= 1
        rec = recs[0]
        for field in ["id", "recommendation_type", "title", "description", "confidence_score",
                      "impact_estimate", "evidence", "affected_workspaces", "generated_at", "status"]:
            assert field in rec, f"Missing field: {field}"

    def test_evidence_is_non_empty(self):
        db = _mock_db()
        metrics = _wf_metrics(completion_rate=0.5, total_runs=10)
        with patch("main.compute_workflow_metrics", return_value=metrics):
            recs = generate_workflow_recommendations(db, "ws", 30)
        for rec in recs:
            assert len(rec["evidence"]) >= 1


# ── TestGenerateMemoryRecommendations ─────────────────────────────────────────

class TestGenerateMemoryRecommendations:

    def test_empty_data_returns_memory_init_rec(self):
        db = _mock_db()
        metrics = _mem_metrics(total_proposals=0, memory_count=0, pending_proposals=0)
        with patch("main.compute_memory_metrics", return_value=metrics):
            recs = generate_memory_recommendations(db, "ws", 30)
        assert any("Initialize" in r["title"] for r in recs)

    def test_high_pending_triggers_recommendation(self):
        db = _mock_db()
        metrics = _mem_metrics(pending_proposals=12)
        with patch("main.compute_memory_metrics", return_value=metrics):
            recs = generate_memory_recommendations(db, "ws", 30)
        assert any("Pending" in r["title"] for r in recs)

    def test_low_approval_rate_triggers_governance_rec(self):
        db = _mock_db()
        metrics = _mem_metrics(total_proposals=10, approval_rate=0.3)
        with patch("main.compute_memory_metrics", return_value=metrics):
            recs = generate_memory_recommendations(db, "ws", 30)
        assert any("Governance" in r["title"] for r in recs)

    def test_high_rejection_rate_triggers_rec(self):
        db = _mock_db()
        metrics = _mem_metrics(total_proposals=10, rejection_rate=0.6)
        with patch("main.compute_memory_metrics", return_value=metrics):
            recs = generate_memory_recommendations(db, "ws", 30)
        assert any("Rejection" in r["title"] for r in recs)

    def test_healthy_memory_returns_no_recs(self):
        db = _mock_db()
        with patch("main.compute_memory_metrics", return_value=_mem_metrics()):
            recs = generate_memory_recommendations(db, "ws", 30)
        assert recs == []

    def test_exception_in_compute_returns_empty(self):
        db = _mock_db()
        with patch("main.compute_memory_metrics", side_effect=Exception("db error")):
            recs = generate_memory_recommendations(db, "ws", 30)
        assert recs == []


# ── TestGenerateTemplateRecommendations ───────────────────────────────────────

class TestGenerateTemplateRecommendations:

    def test_single_template_returns_empty(self):
        db = _mock_db()
        single = _tmpl_metrics(templates=[_tmpl_metrics()["templates"][0]], total_modules=1)
        with patch("main.compute_template_metrics", return_value=single):
            recs = generate_template_recommendations(db, "ws", 30)
        assert recs == []

    def test_performance_gap_triggers_promotion_rec(self):
        db = _mock_db()
        with patch("main.compute_template_metrics", return_value=_tmpl_metrics()):
            recs = generate_template_recommendations(db, "ws", 30)
        assert any(r["recommendation_type"] == "template_adaptation" for r in recs)
        rec = next(r for r in recs if "Promote" in r["title"])
        assert "artist_growth" in rec["title"]

    def test_evidence_contains_both_modules(self):
        db = _mock_db()
        with patch("main.compute_template_metrics", return_value=_tmpl_metrics()):
            recs = generate_template_recommendations(db, "ws", 30)
        promo = next((r for r in recs if "Promote" in r["title"]), None)
        assert promo is not None
        evidence_text = " ".join(promo["evidence"])
        assert "artist_growth" in evidence_text
        assert "media_growth" in evidence_text

    def test_underutilized_template_flagged(self):
        db = _mock_db()
        metrics = _tmpl_metrics()
        metrics["templates"].append({
            "module": "insurance_growth",
            "workflow_runs": 0,
            "workflow_completion_rate": 0.0,
            "total_assets": 0,
            "total_approvals": 0,
            "approval_rate": 0.0,
            "rejection_rate": 0.0,
            "distribution_completion_rate": 0.0,
            "avg_memory_proposal_confidence": 0.0,
        })
        with patch("main.compute_template_metrics", return_value=metrics):
            recs = generate_template_recommendations(db, "ws", 30)
        assert any("Underutilized" in r["title"] and "insurance_growth" in r["title"] for r in recs)

    def test_small_gap_does_not_trigger(self):
        db = _mock_db()
        metrics = _tmpl_metrics()
        # Close rates: 0.81 vs 0.80 — below threshold
        metrics["templates"][0]["approval_rate"] = 0.81
        metrics["templates"][1]["approval_rate"] = 0.80
        metrics["templates"][1]["workflow_runs"] = 3
        with patch("main.compute_template_metrics", return_value=metrics):
            recs = generate_template_recommendations(db, "ws", 30)
        assert not any("Promote" in r["title"] for r in recs)


# ── TestGenerateDistributionRecommendations ───────────────────────────────────

class TestGenerateDistributionRecommendations:

    def test_no_assets_returns_empty(self):
        db = _mock_db()
        with patch("main.compute_distribution_metrics", return_value=_dist_metrics(total_assets=0)):
            recs = generate_distribution_recommendations(db, "ws", 30)
        assert recs == []

    def test_low_publish_rate_triggers_rec(self):
        db = _mock_db()
        with patch("main.compute_distribution_metrics", return_value=_dist_metrics(publish_rate=0.3)):
            recs = generate_distribution_recommendations(db, "ws", 30)
        assert any("Publish Rate" in r["title"] for r in recs)

    def test_channel_imbalance_triggers_rec(self):
        db = _mock_db()
        metrics = _dist_metrics(by_channel={"linkedin": 20, "email": 4})
        with patch("main.compute_distribution_metrics", return_value=metrics):
            recs = generate_distribution_recommendations(db, "ws", 30)
        assert any("Prioritize" in r["title"] and "Linkedin" in r["title"] for r in recs)

    def test_balanced_channels_no_channel_rec(self):
        db = _mock_db()
        metrics = _dist_metrics(by_channel={"linkedin": 10, "email": 9})
        with patch("main.compute_distribution_metrics", return_value=metrics):
            recs = generate_distribution_recommendations(db, "ws", 30)
        assert not any("Prioritize" in r["title"] for r in recs)

    def test_healthy_distribution_no_recs(self):
        db = _mock_db()
        with patch("main.compute_distribution_metrics", return_value=_dist_metrics()):
            recs = generate_distribution_recommendations(db, "ws", 30)
        assert recs == []


# ── TestGenerateOperationalRecommendations ────────────────────────────────────

class TestGenerateOperationalRecommendations:

    def test_no_bottlenecks_no_health_issues_returns_empty(self):
        db = _mock_db()
        with patch("main.compute_bottlenecks", return_value=[]), \
             patch("main.compute_client_health_metrics", return_value=_health_metrics()):
            recs = generate_operational_recommendations(db, "ws", 30)
        assert recs == []

    def test_bottleneck_generates_remediation_rec(self):
        db = _mock_db()
        bn = {
            "type": "stuck_approvals",
            "severity": "high",
            "count": 6,
            "description": "6 approval request(s) open for more than 24h.",
            "workspace_slug": "ws",
        }
        with patch("main.compute_bottlenecks", return_value=[bn]), \
             patch("main.compute_client_health_metrics", return_value=_health_metrics()):
            recs = generate_operational_recommendations(db, "ws", 30)
        assert len(recs) == 1
        assert recs[0]["recommendation_type"] == "bottleneck_remediation"
        assert recs[0]["impact_estimate"] == "high"

    def test_low_health_score_triggers_warning(self):
        db = _mock_db()
        health = _health_metrics(workspaces=[{
            "workspace_slug": "ws",
            "overall_health_score": 0.30,
            "status": "at_risk",
            "workflow_completion_rate": 0.3,
            "approval_efficiency": 0.2,
        }])
        with patch("main.compute_bottlenecks", return_value=[]), \
             patch("main.compute_client_health_metrics", return_value=health):
            recs = generate_operational_recommendations(db, "ws", 30)
        assert any(r["recommendation_type"] == "client_health_warning" for r in recs)
        warn = next(r for r in recs if r["recommendation_type"] == "client_health_warning")
        assert warn["impact_estimate"] == "high"

    def test_healthy_workspace_no_health_warning(self):
        db = _mock_db()
        health = _health_metrics(workspaces=[{
            "workspace_slug": "ws",
            "overall_health_score": 0.85,
            "status": "healthy",
            "workflow_completion_rate": 0.9,
            "approval_efficiency": 0.8,
        }])
        with patch("main.compute_bottlenecks", return_value=[]), \
             patch("main.compute_client_health_metrics", return_value=health):
            recs = generate_operational_recommendations(db, "ws", 30)
        assert not any(r["recommendation_type"] == "client_health_warning" for r in recs)

    def test_multiple_bottlenecks_generate_multiple_recs(self):
        db = _mock_db()
        bns = [
            {"type": "stuck_approvals", "severity": "high", "count": 6, "description": "stuck", "workspace_slug": "ws"},
            {"type": "stale_workflow_runs", "severity": "medium", "count": 3, "description": "stale", "workspace_slug": "ws"},
        ]
        with patch("main.compute_bottlenecks", return_value=bns), \
             patch("main.compute_client_health_metrics", return_value=_health_metrics()):
            recs = generate_operational_recommendations(db, "ws", 30)
        assert len(recs) == 2


# ── TestGenerateCrossClientSignals ────────────────────────────────────────────

class TestGenerateCrossClientSignals:

    def test_empty_db_returns_zero_workspaces(self):
        db = _mock_db()
        db.memory_update_proposals.find.return_value = iter([])
        db.workflow_runs.find.return_value = iter([])
        with patch("main.compute_template_metrics", return_value={"templates": [], "total_modules": 0, "period_days": 30}), \
             patch("main.compute_distribution_metrics", return_value=_dist_metrics(total_assets=0, by_channel={})), \
             patch("main.compute_bottlenecks", return_value=[]):
            result = generate_cross_client_signals(db, 30)
        assert result["active_workspaces"] == 0
        assert result["top_winning_patterns"] == []

    def test_returns_required_fields(self):
        db = _mock_db()
        db.memory_update_proposals.find.return_value = iter([])
        db.workflow_runs.find.return_value = iter([])
        with patch("main.compute_template_metrics", return_value={"templates": [], "total_modules": 0, "period_days": 30}), \
             patch("main.compute_distribution_metrics", return_value=_dist_metrics(by_channel={})), \
             patch("main.compute_bottlenecks", return_value=[]):
            result = generate_cross_client_signals(db, 30)
        for field in ["period_days", "active_workspaces", "top_winning_patterns",
                      "best_performing_templates", "top_channels", "common_bottlenecks", "generated_at"]:
            assert field in result, f"Missing field: {field}"

    def test_active_workspaces_counted(self):
        db = _mock_db()
        db.memory_update_proposals.find.return_value = iter([])
        db.workflow_runs.find.return_value = iter([
            {"workspace_slug": "ws1"}, {"workspace_slug": "ws2"}, {"workspace_slug": "ws1"},
        ])
        with patch("main.compute_template_metrics", return_value={"templates": [], "total_modules": 0, "period_days": 30}), \
             patch("main.compute_distribution_metrics", return_value=_dist_metrics(by_channel={})), \
             patch("main.compute_bottlenecks", return_value=[]):
            result = generate_cross_client_signals(db, 30)
        assert result["active_workspaces"] == 2

    def test_best_performing_templates_ordered(self):
        db = _mock_db()
        db.memory_update_proposals.find.return_value = iter([])
        db.workflow_runs.find.return_value = iter([])
        with patch("main.compute_template_metrics", return_value=_tmpl_metrics()), \
             patch("main.compute_distribution_metrics", return_value=_dist_metrics(by_channel={})), \
             patch("main.compute_bottlenecks", return_value=[]):
            result = generate_cross_client_signals(db, 30)
        tpls = result["best_performing_templates"]
        assert len(tpls) >= 1
        if len(tpls) >= 2:
            assert tpls[0]["approval_rate"] >= tpls[1]["approval_rate"]


# ── TestRecommendationLifecycle ───────────────────────────────────────────────

class TestRecommendationLifecycle:

    def test_accept_returns_accepted_status(self, client):
        db = _mock_db()
        with _patch(db):
            resp = client.post("/recommendations/abc123/accept")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["rec_id"] == "abc123"

    def test_dismiss_returns_dismissed_status(self, client):
        db = _mock_db()
        with _patch(db):
            resp = client.post("/recommendations/abc123/dismiss")
        assert resp.status_code == 200
        assert resp.json()["status"] == "dismissed"

    def test_apply_returns_applied_status(self, client):
        db = _mock_db()
        with _patch(db):
            resp = client.post("/recommendations/abc123/apply")
        assert resp.status_code == 200
        assert resp.json()["status"] == "applied"

    def test_accept_persists_via_update_one(self, client):
        db = _mock_db()
        with _patch(db):
            client.post("/recommendations/test_id/accept")
        db.recommendation_statuses.update_one.assert_called_once()
        call_args = db.recommendation_statuses.update_one.call_args
        assert call_args[0][0] == {"rec_id": "test_id"}
        assert call_args[0][1]["$set"]["status"] == "accepted"

    def test_lifecycle_response_has_updated_at(self, client):
        db = _mock_db()
        with _patch(db):
            resp = client.post("/recommendations/abc123/apply")
        assert "updated_at" in resp.json()

    def test_collect_merges_persisted_status(self):
        db = _mock_db()
        override = {"rec_id": "fake_id", "status": "dismissed", "updated_at": _NOW}
        db.recommendation_statuses.find.return_value = iter([override])
        with patch("main.generate_workflow_recommendations", return_value=[{
            "id": "fake_id",
            "recommendation_type": "workflow_optimization",
            "title": "Test",
            "description": "Test",
            "confidence_score": 0.9,
            "impact_estimate": "high",
            "evidence": [],
            "affected_workspaces": [],
            "generated_at": _NOW.isoformat(),
            "status": "active",
        }]), \
        patch("main.generate_memory_recommendations", return_value=[]), \
        patch("main.generate_template_recommendations", return_value=[]), \
        patch("main.generate_distribution_recommendations", return_value=[]), \
        patch("main.generate_operational_recommendations", return_value=[]):
            recs = _collect_all_recommendations(db, "ws", 30)
        assert len(recs) == 1
        assert recs[0]["status"] == "dismissed"


# ── TestRecIdDeterminism ──────────────────────────────────────────────────────

class TestRecIdDeterminism:

    def test_same_inputs_produce_same_id(self):
        id1 = _rec_id("workflow_optimization", "Improve Rate", "ws")
        id2 = _rec_id("workflow_optimization", "Improve Rate", "ws")
        assert id1 == id2

    def test_different_workspace_produces_different_id(self):
        id1 = _rec_id("workflow_optimization", "Improve Rate", "ws1")
        id2 = _rec_id("workflow_optimization", "Improve Rate", "ws2")
        assert id1 != id2

    def test_different_type_produces_different_id(self):
        id1 = _rec_id("workflow_optimization", "Title", "ws")
        id2 = _rec_id("memory_refinement", "Title", "ws")
        assert id1 != id2


# ── TestRecommendationEndpoints ───────────────────────────────────────────────

class TestRecommendationEndpoints:

    def _make_sample_recs(self, n=2):
        return [
            {
                "id": f"rec_{i}",
                "recommendation_type": "workflow_optimization",
                "title": f"Recommendation {i}",
                "description": f"Desc {i}",
                "confidence_score": 0.8,
                "impact_estimate": "high" if i == 0 else "medium",
                "evidence": [f"evidence {i}"],
                "affected_workspaces": ["ws"],
                "generated_at": _NOW.isoformat(),
                "status": "active",
            }
            for i in range(n)
        ]

    def test_list_recommendations_200(self, client):
        db = _mock_db()
        with _patch(db), \
             patch("main._collect_all_recommendations", return_value=self._make_sample_recs()):
            resp = client.get("/recommendations")
        assert resp.status_code == 200
        data = resp.json()
        assert "recommendations" in data
        assert "total" in data
        assert data["total"] == 2

    def test_list_filters_by_status(self, client):
        db = _mock_db()
        recs = self._make_sample_recs(2)
        recs[0]["status"] = "dismissed"
        with _patch(db), \
             patch("main._collect_all_recommendations", return_value=recs):
            resp = client.get("/recommendations?status=active")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_list_filters_by_rec_type(self, client):
        db = _mock_db()
        recs = self._make_sample_recs(2)
        recs[1]["recommendation_type"] = "memory_refinement"
        with _patch(db), \
             patch("main._collect_all_recommendations", return_value=recs):
            resp = client.get("/recommendations?rec_type=workflow_optimization")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_list_sorted_high_impact_first(self, client):
        db = _mock_db()
        recs = self._make_sample_recs(2)
        # rec_0 is high, rec_1 is medium
        with _patch(db), \
             patch("main._collect_all_recommendations", return_value=recs):
            resp = client.get("/recommendations")
        items = resp.json()["recommendations"]
        assert items[0]["impact_estimate"] == "high"

    def test_summary_endpoint_200(self, client):
        db = _mock_db()
        with _patch(db), \
             patch("main._collect_all_recommendations", return_value=self._make_sample_recs(3)):
            resp = client.get("/recommendations/summary")
        assert resp.status_code == 200
        data = resp.json()
        for field in ["total", "active", "high_impact", "by_type", "period_days"]:
            assert field in data

    def test_summary_counts_correct(self, client):
        db = _mock_db()
        recs = self._make_sample_recs(3)
        recs[2]["status"] = "dismissed"
        with _patch(db), \
             patch("main._collect_all_recommendations", return_value=recs):
            resp = client.get("/recommendations/summary")
        data = resp.json()
        assert data["total"] == 3
        assert data["active"] == 2

    def test_cross_client_signals_endpoint_200(self, client):
        db = _mock_db()
        db.memory_update_proposals.find.return_value = iter([])
        db.workflow_runs.find.return_value = iter([])
        with _patch(db), \
             patch("main.compute_template_metrics", return_value={"templates": [], "total_modules": 0, "period_days": 30}), \
             patch("main.compute_distribution_metrics", return_value=_dist_metrics(by_channel={})), \
             patch("main.compute_bottlenecks", return_value=[]):
            resp = client.get("/recommendations/cross-client-signals")
        assert resp.status_code == 200
        assert "active_workspaces" in resp.json()

    def test_get_recommendation_by_id(self, client):
        db = _mock_db()
        recs = self._make_sample_recs(2)
        target_id = recs[0]["id"]
        with _patch(db), \
             patch("main._collect_all_recommendations", return_value=recs):
            resp = client.get(f"/recommendations/{target_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == target_id

    def test_get_recommendation_not_found_returns_404(self, client):
        db = _mock_db()
        with _patch(db), \
             patch("main._collect_all_recommendations", return_value=[]):
            resp = client.get("/recommendations/nonexistent_id")
        assert resp.status_code == 404

    def test_accept_endpoint_200(self, client):
        db = _mock_db()
        with _patch(db):
            resp = client.post("/recommendations/some_rec/accept")
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    def test_dismiss_endpoint_200(self, client):
        db = _mock_db()
        with _patch(db):
            resp = client.post("/recommendations/some_rec/dismiss")
        assert resp.status_code == 200
        assert resp.json()["status"] == "dismissed"

    def test_apply_endpoint_200(self, client):
        db = _mock_db()
        with _patch(db):
            resp = client.post("/recommendations/some_rec/apply")
        assert resp.status_code == 200
        assert resp.json()["status"] == "applied"

    def test_days_param_accepted(self, client):
        db = _mock_db()
        with _patch(db), \
             patch("main._collect_all_recommendations", return_value=self._make_sample_recs()):
            resp = client.get("/recommendations?days=7")
        assert resp.status_code == 200
        assert resp.json()["period_days"] == 7

    def test_workspace_slug_param_accepted(self, client):
        db = _mock_db()
        with _patch(db), \
             patch("main._collect_all_recommendations", return_value=[]) as mock_collect:
            resp = client.get("/recommendations?workspace_slug=acme")
        assert resp.status_code == 200
        mock_collect.assert_called_once()
        call_args = mock_collect.call_args[0]
        assert call_args[1] == "acme"
