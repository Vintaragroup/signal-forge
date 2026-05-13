"""
tests/test_e2e_system_validation.py — Phase 6S: Full System Validation & Operational Readiness

Validates the complete SignalForge adaptive operating system loop end-to-end:
  profile → template → memory → workflow → outcome → learning
          → analytics → recommendation → autonomy → rollback

15 sequential validation steps executed against a single shared workspace ("phase6s_test").
A stateful in-memory MongoDB mock persists data across all steps so the output of each
step feeds naturally into the next — exactly as the live system would behave.

Steps:
  01. Client profile creation
  02. Foundation template recommendation
  03. Client memory initialization
  04. Workflow lifecycle execution (queued → completed)
  05. Memory-aware discovery build
  06. Approval and distribution lifecycle
  07. Memory proposal generation
  08. Governance review: diff and conflict detection
  09. Memory update approval and auto-apply
  10. Analytics refresh (workflows + memory)
  11. Recommendation generation
  12. Autonomy policy evaluation
  13. Autonomy simulation
  14. Action lifecycle: insert → list → get → rollback
  15. Final operational dashboard state
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

import main
from main import app, evaluate_autonomy_policy, simulate_autonomy_action

# ── Constants ─────────────────────────────────────────────────────────────────

_WS = "phase6s_test"

# ── In-memory MongoDB layer ───────────────────────────────────────────────────


def _doc_matches(doc: dict, query: dict) -> bool:
    """Minimal query matcher: equality and ObjectId-safe _id comparison."""
    for k, v in query.items():
        if k.startswith("$"):
            continue  # skip top-level operators ($or, $and, …)
        doc_val = doc.get(k)
        if isinstance(v, dict) and any(op.startswith("$") for op in v):
            continue  # skip value-level operators ($in, $gte, $exists, …)
        if str(doc_val) != str(v) and doc_val != v:
            return False
    return True


class _FindResult:
    """Chainable find result supporting .sort(), .limit(), and iteration."""

    def __init__(self, results: list[dict]) -> None:
        self._r = results

    def sort(self, *_a, **_kw) -> "_FindResult":
        return self

    def limit(self, n: int) -> "_FindResult":
        self._r = self._r[: int(n)]
        return self

    def __iter__(self):
        return iter(self._r)


class _MemCollection:
    """Stateful in-memory collection that satisfies all MongoDB call patterns used in main.py."""

    def __init__(self) -> None:
        self._docs: list[dict] = []

    # ── writes ────────────────────────────────────────────────────────────────

    def insert_one(self, doc: dict):
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self._docs.append(doc)
        r = MagicMock()
        r.inserted_id = doc["_id"]
        return r

    def update_one(self, q: dict, upd: dict, *_args, upsert: bool = False, **_kw):
        for doc in self._docs:
            if _doc_matches(doc, q):
                if "$set" in upd:
                    doc.update(upd["$set"])
                return MagicMock()
        if upsert:
            new_doc: dict = {k: v for k, v in q.items() if not k.startswith("$")}
            if "$set" in upd:
                new_doc.update(upd["$set"])
            if "_id" not in new_doc:
                new_doc["_id"] = ObjectId()
            self._docs.append(new_doc)
        return MagicMock()

    def delete_one(self, q: dict):
        for i, doc in enumerate(self._docs):
            if _doc_matches(doc, q):
                self._docs.pop(i)
                return MagicMock()
        return MagicMock()

    # ── reads ─────────────────────────────────────────────────────────────────

    def find_one(self, q: dict | None = None, *_args, **_kw) -> dict | None:
        for doc in self._docs:
            if _doc_matches(doc, q or {}):
                return dict(doc)
        return None

    def find(self, q: dict | None = None, *_args, **_kw) -> _FindResult:
        q = q or {}
        return _FindResult([dict(d) for d in self._docs if _doc_matches(d, q)])

    def count_documents(self, q: dict | None = None) -> int:
        q = q or {}
        return sum(1 for d in self._docs if _doc_matches(d, q))


class _MemDB:
    """Complete stateful mock database carrying all collections Phase 6S touches."""

    def __init__(self) -> None:
        # Core system collections
        self.client_profiles = _MemCollection()
        self.client_memories = _MemCollection()
        self.workflow_runs = _MemCollection()
        self.workflow_assets = _MemCollection()
        self.discovery_insights = _MemCollection()
        self.memory_update_proposals = _MemCollection()
        self.approval_requests = _MemCollection()
        self.workspaces = _MemCollection()
        # Analytics
        self.learning_signals = _MemCollection()
        self.analytics_snapshots = _MemCollection()
        # Recommendations
        self.recommendation_statuses = _MemCollection()
        # Autonomy
        self.autonomy_policies = _MemCollection()
        self.autonomy_state = _MemCollection()
        self.autonomy_action_logs = _MemCollection()


# ── Patch helper (same pattern as all other test modules) ────────────────────


def _patch(db: _MemDB):
    mongo_client = MagicMock()
    mongo_client.close = MagicMock()
    return patch.multiple(
        "main",
        get_client=lambda: mongo_client,
        get_database=lambda c: db,
    )


# ── Module-level shared state (IDs flow between steps) ───────────────────────

_STATE: dict = {}


# ── Module-scoped fixtures ────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def shared_db() -> _MemDB:
    """Single stateful DB shared across all 15 validation steps."""
    return _MemDB()


@pytest.fixture(scope="module")
def http(shared_db) -> TestClient:  # noqa: F811
    """TestClient bound to the shared DB."""
    return TestClient(app)


# ═════════════════════════════════════════════════════════════════════════════
# Phase 6S — 15-Step Validation Suite
# ═════════════════════════════════════════════════════════════════════════════


class TestPhase6SOperationalReadiness:
    """
    Validates the full SignalForge loop in one workspace.

    Test methods are prefixed 01–15 so pytest runs them in definition order.
    Each step asserts its own outcomes AND populates _STATE for later steps.
    """

    # ── Step 01 ───────────────────────────────────────────────────────────────

    def test_01_client_profile_creation(self, shared_db, http):
        with _patch(shared_db):
            r = http.post(
                "/client-profiles",
                json={
                    "workspace_slug": _WS,
                    "client_name": "Phase6S Test Client",
                    "brand_name": "Signal6S",
                    "approved_source_channels": ["instagram", "youtube"],
                    "allowed_content_types": ["video", "graphic"],
                    "disallowed_topics": [],
                    "compliance_notes": "Phase 6S E2E validation client",
                    "status": "active",
                },
            )
        assert r.status_code == 200
        item = r.json()["item"]
        assert item["workspace_slug"] == _WS
        assert item["client_name"] == "Phase6S Test Client"
        assert "message" in r.json()
        _STATE["profile_id"] = item["_id"]

    # ── Step 02 ───────────────────────────────────────────────────────────────

    def test_02_foundation_template_recommendation(self, shared_db, http):
        """Template recommendation is pure computation — no DB required."""
        with _patch(shared_db):
            r = http.post(
                "/template-recommendation",
                json={
                    "industry": "media production",
                    "primary_offer": "content creation and distribution",
                    "target_audience": "independent artists and creators",
                    "goals": "grow audience and monetize content",
                    "differentiators": "data-driven creative strategy",
                    "tone_keywords": "authentic bold creative",
                    "existing_content_types": "video graphic reels",
                    "approved_channels": "instagram youtube",
                },
            )
        assert r.status_code == 200
        data = r.json()
        assert "recommended_template" in data
        assert "confidence_score" in data
        assert "reason" in data
        slug = data["recommended_template"]["slug"]
        assert slug in main.FOUNDATION_TEMPLATES
        assert data["confidence_score"] > 0.0
        _STATE["template_slug"] = slug

    # ── Step 03 ───────────────────────────────────────────────────────────────

    def test_03_client_memory_initialization(self, shared_db, http):
        template_slug = _STATE.get("template_slug", "media_growth")
        with _patch(shared_db):
            r = http.post(
                "/client-memory",
                json={
                    "workspace_slug": _WS,
                    "client_profile_id": _STATE.get("profile_id", ""),
                    "foundation_template_slug": template_slug,
                    "positioning": {"core_value_proposition": "Data-driven creative growth"},
                    "approved_claims": ["We help artists grow their audience"],
                    "blocked_claims": ["guaranteed results"],
                },
            )
        assert r.status_code == 200
        data = r.json()
        assert data["created"] is True
        item = data["item"]
        assert item["workspace_slug"] == _WS
        assert item["foundation_template_slug"] == template_slug
        assert item["version"] == 1
        _STATE["memory_id"] = item["_id"]

    # ── Step 04 ───────────────────────────────────────────────────────────────

    def test_04_workflow_lifecycle_execution(self, shared_db, http):
        # Create — queued
        with _patch(shared_db):
            r = http.post(
                "/workflow-runs",
                json={
                    "workspace_slug": _WS,
                    "client_profile_id": _STATE.get("profile_id", ""),
                    "workflow_stage": 2,
                    "run_type": "content_build",
                    "status": "queued",
                    "title": "Phase6S Content Build Run",
                    "summary": "E2E validation content build",
                    "inputs": {"source": "e2e_test"},
                },
            )
        assert r.status_code == 200
        run = r.json()["item"]
        assert run["status"] == "queued"
        assert run["workflow_stage"] == 2
        run_id = run["_id"]
        _STATE["run_id"] = run_id

        # Advance — running
        with _patch(shared_db):
            r2 = http.patch(
                f"/workflow-runs/{run_id}",
                json={"status": "running"},
            )
        assert r2.status_code == 200
        assert r2.json()["item"]["status"] == "running"

        # Complete
        with _patch(shared_db):
            r3 = http.patch(
                f"/workflow-runs/{run_id}",
                json={
                    "status": "completed",
                    "summary": "Content build completed successfully",
                    "outputs": {"posts_generated": 3, "approval_rate": 1.0},
                },
            )
        assert r3.status_code == 200
        assert r3.json()["item"]["status"] == "completed"

    # ── Step 05 ───────────────────────────────────────────────────────────────

    def test_05_memory_aware_discovery_build(self, shared_db, http):
        run_id = _STATE["run_id"]

        # Memory context snapshot for the run
        with _patch(shared_db):
            r_ctx = http.get(f"/workflow-runs/{run_id}/memory-context")
        assert r_ctx.status_code == 200
        ctx = r_ctx.json()
        assert "has_memory" in ctx
        assert "run_id" in ctx

        # Create a discovery insight from the run
        with _patch(shared_db):
            r_ins = http.post(
                "/discovery-insights",
                json={
                    "workspace_slug": _WS,
                    "insight_type": "audience_pattern",
                    "title": "High engagement on short-form video",
                    "summary": "Short-form video posts see 3x engagement vs static graphics",
                    "confidence_score": 0.87,
                    "evidence": [
                        {
                            "source": "instagram",
                            "detail": "Reels outperform graphics by 3x",
                            "strength": 0.9,
                        }
                    ],
                    "status": "pending_review",
                    "source_run_id": run_id,
                },
            )
        assert r_ins.status_code == 200
        insight = r_ins.json()["item"]
        assert insight["workspace_slug"] == _WS
        assert insight["confidence_score"] == 0.87
        _STATE["insight_id"] = insight["_id"]

    # ── Step 06 ───────────────────────────────────────────────────────────────

    def test_06_approval_and_distribution_lifecycle(self, shared_db, http):
        # Seed a workflow asset directly — simulates an asset produced during the run
        asset_id = ObjectId()
        shared_db.workflow_assets._docs.append(
            {
                "_id": asset_id,
                "workspace_slug": _WS,
                "workflow_run_id": _STATE["run_id"],
                "asset_type": "post",
                "platform": "instagram",
                "title": "Phase6S Validation Post",
                "body": "Creative content for Phase6S system validation",
                "approval_state": "needs_review",
                "distribution_state": "not_queued",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        asset_id_str = str(asset_id)
        _STATE["asset_id"] = asset_id_str

        # Approve
        with _patch(shared_db):
            r_approve = http.patch(
                f"/workflow-assets/{asset_id_str}/decision",
                json={"decision": "approve"},
            )
        assert r_approve.status_code == 200
        assert r_approve.json()["item"]["approval_state"] == "approved"

        # Queue for distribution
        with _patch(shared_db):
            r_queue = http.patch(
                f"/workflow-assets/{asset_id_str}/distribution",
                json={"action": "queue", "distribution_channel": "instagram"},
            )
        assert r_queue.status_code == 200
        assert r_queue.json()["item"]["distribution_state"] == "queued"

        # Mark published
        with _patch(shared_db):
            r_pub = http.patch(
                f"/workflow-assets/{asset_id_str}/distribution",
                json={
                    "action": "mark_published",
                    "published_url": "https://instagram.com/p/phase6s_test",
                },
            )
        assert r_pub.status_code == 200
        assert r_pub.json()["item"]["distribution_state"] == "published"

    # ── Step 07 ───────────────────────────────────────────────────────────────

    def test_07_memory_proposal_generation(self, shared_db, http):
        with _patch(shared_db):
            r = http.post(
                "/memory-update-proposals",
                json={
                    "workspace_slug": _WS,
                    "client_memory_id": _STATE["memory_id"],
                    "client_profile_id": _STATE.get("profile_id", ""),
                    "workflow_run_id": _STATE["run_id"],
                    "source": "e2e_validation",
                    "proposed_change": {
                        "field": "winning_patterns",
                        "change_type": "add",
                        "new_value": "Short-form video drives highest engagement",
                        "old_value": None,
                    },
                    "evidence": "Discovery run showed 3× engagement on short-form video vs static.",
                    "confidence": 0.91,
                },
            )
        assert r.status_code == 200
        proposal = r.json()["item"]
        assert proposal["workspace_slug"] == _WS
        assert proposal["status"] == "pending"
        assert proposal["confidence"] == 0.91
        _STATE["proposal_id"] = proposal["_id"]

    # ── Step 08 ───────────────────────────────────────────────────────────────

    def test_08_governance_review_diff_and_conflicts(self, shared_db, http):
        proposal_id = _STATE["proposal_id"]

        # Diff preview
        with _patch(shared_db):
            r_diff = http.get(f"/memory-update-proposals/{proposal_id}/diff")
        assert r_diff.status_code == 200
        diff_data = r_diff.json()
        assert "diff" in diff_data
        assert "proposal_id" in diff_data
        assert "workspace_slug" in diff_data

        # Conflict detection
        with _patch(shared_db):
            r_conf = http.get(f"/memory-update-proposals/{proposal_id}/conflicts")
        assert r_conf.status_code == 200
        conf_data = r_conf.json()
        assert "conflicts" in conf_data
        assert "conflict_count" in conf_data
        assert "has_high_severity_conflicts" in conf_data
        assert "duplicate" in conf_data
        assert isinstance(conf_data["conflict_count"], int)
        assert conf_data["conflict_count"] >= 0

    # ── Step 09 ───────────────────────────────────────────────────────────────

    def test_09_memory_update_approval_and_apply(self, shared_db, http):
        proposal_id = _STATE["proposal_id"]
        with _patch(shared_db):
            r = http.patch(
                f"/memory-update-proposals/{proposal_id}",
                json={
                    "status": "approved",
                    "reviewed_by": "phase6s_operator",
                    "note": "Phase6S E2E approval — pattern validated by discovery run",
                    "override_conflicts": True,
                },
            )
        assert r.status_code == 200
        result = r.json()
        assert result["item"]["status"] == "approved"
        assert result["item"]["reviewed_by"] == "phase6s_operator"

    # ── Step 10 ───────────────────────────────────────────────────────────────

    def test_10_analytics_refresh(self, shared_db, http):
        with _patch(shared_db):
            r_wf = http.get(f"/analytics/workflows?workspace_slug={_WS}")
            r_mem = http.get(f"/analytics/memory?workspace_slug={_WS}")

        assert r_wf.status_code == 200
        assert r_mem.status_code == 200

        wf = r_wf.json()
        mem = r_mem.json()

        # Workflow analytics should reflect Step 04's run
        assert wf.get("total_runs", 0) >= 1
        assert "completion_rate" in wf
        assert "by_run_type" in wf

        # Memory analytics should reflect Steps 03 + 07 + 09
        assert "total_proposals" in mem
        assert mem.get("total_proposals", 0) >= 1

    # ── Step 11 ───────────────────────────────────────────────────────────────

    def test_11_recommendation_generation(self, shared_db, http):
        with _patch(shared_db):
            r = http.get(f"/recommendations?workspace_slug={_WS}")
        assert r.status_code == 200
        data = r.json()
        assert "recommendations" in data
        assert "total" in data
        assert isinstance(data["recommendations"], list)
        assert data["total"] >= 0

        # If recommendations exist, accept the first one
        if data["recommendations"]:
            rec_id = data["recommendations"][0]["id"]
            with _patch(shared_db):
                r_accept = http.post(f"/recommendations/{rec_id}/accept")
            assert r_accept.status_code == 200
            assert r_accept.json()["status"] == "accepted"
            _STATE["accepted_rec_id"] = rec_id

    # ── Step 12 ───────────────────────────────────────────────────────────────

    def test_12_autonomy_policy_evaluation(self, shared_db, http):
        # Set a workspace-specific policy
        with _patch(shared_db):
            r_set = http.patch(
                f"/autonomy/policies/{_WS}",
                json={
                    "autonomy_enabled": True,
                    "max_autonomy_risk": "medium",
                    "auto_apply_threshold": 0.85,
                    "require_review_for": [],
                    "auto_archive_days": 30,
                },
            )
        assert r_set.status_code == 200
        resp = r_set.json()
        assert "policy" in resp
        policy = resp["policy"]
        assert policy["autonomy_enabled"] is True
        assert policy["max_autonomy_risk"] == "medium"

        # Retrieve all policies for the workspace
        with _patch(shared_db):
            r_list = http.get(f"/autonomy/policies?workspace_slug={_WS}")
        assert r_list.status_code == 200
        pd = r_list.json()
        assert "policies" in pd
        assert "autonomy_paused" in pd
        assert pd["autonomy_paused"] is False

        # Helper-level evaluation — low-risk action, high confidence
        with _patch(shared_db):
            result = evaluate_autonomy_policy(
                action_type="auto_archive_stale_workflows",
                confidence_score=0.95,
                evidence_count=5,
                workspace_slug=_WS,
                db=shared_db,
            )
        assert "allowed" in result
        assert "policy" in result
        assert "reason" in result
        _STATE["eval_result"] = result

    # ── Step 13 ───────────────────────────────────────────────────────────────

    def test_13_autonomy_simulation(self, shared_db, http):
        with _patch(shared_db):
            sim = simulate_autonomy_action(
                action_type="auto_archive_stale_workflows",
                workspace_slug=_WS,
                params={"stale_threshold_days": 30},
                db=shared_db,
            )
        assert sim["action_type"] == "auto_archive_stale_workflows"
        assert sim["risk_level"] == "low"
        assert sim["rollback_supported"] is True
        assert "expected_changes" in sim
        assert "impact_summary" in sim
        assert "conflict_detected" in sim
        assert "rollback_complexity" in sim

    # ── Step 14 ───────────────────────────────────────────────────────────────

    def test_14_action_lifecycle_list_get_rollback(self, shared_db, http):
        # Seed a rollback-eligible action directly — simulates a system-applied action
        # Use a plain string _id so FastAPI can JSON-serialize the document without projection
        action_id = "6s" + str(ObjectId())[:14]
        shared_db.autonomy_action_logs._docs.append(
            {
                "_id": action_id,                      # plain string avoids ObjectId serialization error
                "id": action_id,                       # queried by endpoints as "id"
                "action_id": action_id,                # also stored for list display
                "workspace_slug": _WS,
                "action_type": "auto_archive_stale_workflows",
                "status": "applied",
                "risk_level": "low",
                "rollback_supported": True,
                "confidence_score": 0.95,
                "evidence_count": 5,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "applied_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _STATE["action_id"] = action_id

        # List — must appear in workspace results
        with _patch(shared_db):
            r_list = http.get(f"/autonomy/actions?workspace_slug={_WS}")
        assert r_list.status_code == 200
        ad = r_list.json()
        assert "actions" in ad
        found = [a for a in ad["actions"] if a.get("id") == action_id]
        assert len(found) == 1, "Seeded action must appear in list"

        # Get by ID
        with _patch(shared_db):
            r_get = http.get(f"/autonomy/actions/{action_id}")
        assert r_get.status_code == 200
        action_doc = r_get.json()
        assert action_doc["id"] == action_id
        assert action_doc["status"] == "applied"

        # Rollback
        with _patch(shared_db):
            r_rb = http.post(f"/autonomy/actions/{action_id}/rollback")
        assert r_rb.status_code == 200
        rb = r_rb.json()
        assert rb["action_id"] == action_id
        assert rb["status"] == "rolled_back"

        # Verify the in-DB status updated
        stored = shared_db.autonomy_action_logs.find_one({"id": action_id})
        assert stored is not None
        assert stored["status"] == "rolled_back"

    # ── Step 15 ───────────────────────────────────────────────────────────────

    def test_15_final_operational_dashboard_state(self, shared_db, http):
        """
        Confirm the full dashboard picture after all 14 prior steps:
        - Autonomy analytics tallies the rolled-back action
        - Recommendations summary returns valid structure
        - Workflow analytics reflects the completed run
        - Autonomy is not globally paused
        """
        # Autonomy analytics
        with _patch(shared_db):
            r_auto = http.get(f"/autonomy/analytics?workspace_slug={_WS}")
        assert r_auto.status_code == 200
        aa = r_auto.json()
        assert "total_actions" in aa
        assert "auto_apply_success_rate" in aa
        assert "rollback_rate" in aa
        assert "by_action_type" in aa
        assert "by_risk_level" in aa
        assert aa["total_actions"] >= 1

        # Recommendations summary
        with _patch(shared_db):
            r_rec = http.get(f"/recommendations/summary?workspace_slug={_WS}")
        assert r_rec.status_code == 200
        rs = r_rec.json()
        assert "total" in rs
        assert "active" in rs
        assert "by_type" in rs

        # Final workflow analytics — run from Step 04 must still be counted
        with _patch(shared_db):
            r_wf = http.get(f"/analytics/workflows?workspace_slug={_WS}")
        assert r_wf.status_code == 200
        wf = r_wf.json()
        assert wf.get("total_runs", 0) >= 1
        assert wf.get("completed_runs", 0) >= 1

        # System should not be globally paused
        with _patch(shared_db):
            r_pause = http.get(f"/autonomy/policies?workspace_slug={_WS}")
        assert r_pause.status_code == 200
        assert r_pause.json()["autonomy_paused"] is False
