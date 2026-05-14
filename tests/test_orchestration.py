"""
tests/test_orchestration.py — Phase 6T: Multi-Agent Coordination & Autonomous Workflow Orchestration

Coverage:
  - evaluate_agent_dependencies: dependency resolution logic
  - schedule_next_agent_tasks: DB-backed promotion to ready
  - create_orchestration_plan: graph creation, node ordering, edges
  - execute_orchestration_graph: ready→running transitions, guard conditions
  - handle_agent_failure: retry vs. escalate decision tree
  - escalate_orchestration_issue: node and orch status updates
  - _compute_queue_priority: scoring across urgency/deadline/health factors
  - _compute_orchestration_telemetry: aggregation correctness
  - Endpoints: POST/GET /orchestrations, GET /orchestrations/telemetry,
               GET /{id}, GET /{id}/graph, GET /{id}/telemetry,
               POST /{id}/pause, POST /{id}/resume, POST /{id}/retry-node,
               POST /{id}/escalate, GET /agents/profiles, GET /agents/utilization
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
from main import (
    _DEFAULT_AGENT_PROFILES_6T,
    _PRIORITY_LEVELS_6T,
    _compute_orchestration_telemetry,
    _compute_queue_priority,
    app,
    create_orchestration_plan,
    escalate_orchestration_issue,
    evaluate_agent_dependencies,
    execute_orchestration_graph,
    handle_agent_failure,
    schedule_next_agent_tasks,
)

# ── Fixtures & helpers ────────────────────────────────────────────────────────

_NOW = datetime.now(timezone.utc).isoformat()

client = TestClient(app)


def _patch(db):
    mongo_client = MagicMock()
    mongo_client.close = MagicMock()
    return patch.multiple("main", get_client=lambda: mongo_client, get_database=lambda c: db)


def _make_orch(
    orch_id: str = "testorch001",
    status: str = "running",
    priority: str = "normal",
    workspace_slug: str = "test_ws",
    nodes: list | None = None,
    retry_total: int = 0,
    delegation_count: int = 0,
) -> dict:
    """Build a minimal orchestration document for testing."""
    if nodes is None:
        nodes = [
            {
                "node_id": "node_a",
                "agent_name": "discovery",
                "label": "Discovery (step 1)",
                "status": "ready",
                "depends_on": [],
                "retry_count": 0,
                "max_retries": 3,
                "failure_reason": None,
                "recovery_strategy": None,
                "execution_metadata": {},
                "started_at": None,
                "completed_at": None,
            },
            {
                "node_id": "node_b",
                "agent_name": "content_build",
                "label": "Content Build (step 2)",
                "status": "pending",
                "depends_on": ["node_a"],
                "retry_count": 0,
                "max_retries": 3,
                "failure_reason": None,
                "recovery_strategy": None,
                "execution_metadata": {},
                "started_at": None,
                "completed_at": None,
            },
        ]
    return {
        "_id": ObjectId(),
        "orchestration_id": orch_id,
        "workspace_slug": workspace_slug,
        "workflow_run_id": "",
        "status": status,
        "priority": priority,
        "nodes": nodes,
        "edges": [{"from": "node_a", "to": "node_b"}],
        "created_at": _NOW,
        "updated_at": _NOW,
        "completed_at": None,
        "failure_reason": None,
        "escalation_status": None,
        "delegation_count": delegation_count,
        "retry_total": retry_total,
    }


def _orch_db(orch: dict | None = None):
    """Mock db with a single orchestration and chainable find/find_one/update_one."""
    db = MagicMock()
    orches: list[dict] = [dict(orch)] if orch else []

    def _find_one(q, *a, **kw):
        for o in orches:
            if all(str(o.get(k)) == str(v) or o.get(k) == v for k, v in q.items()):
                return dict(o)
        return None

    def _update_one(q, upd, *a, **kw):
        for o in orches:
            if all(str(o.get(k)) == str(v) or o.get(k) == v for k, v in q.items()):
                if "$set" in upd:
                    o.update(upd["$set"])
                return MagicMock()
        return MagicMock()

    def _insert_one(doc):
        doc.setdefault("_id", ObjectId())
        orches.append(doc)
        r = MagicMock()
        r.inserted_id = doc["_id"]
        return r

    _fm = MagicMock()
    _fm.__iter__ = lambda self: iter([dict(o) for o in orches])
    _fm.sort.return_value = _fm
    _fm.limit.side_effect = lambda n: iter([dict(o) for o in orches[:n]])

    db.orchestrations.find_one.side_effect = _find_one
    db.orchestrations.update_one.side_effect = _update_one
    db.orchestrations.insert_one.side_effect = _insert_one
    db.orchestrations.find.return_value = _fm

    db.agent_profiles.find.return_value = iter([])
    return db, orches


# ═══════════════════════════════════════════════════════════════════════════════
# 1. evaluate_agent_dependencies — pure function
# ═══════════════════════════════════════════════════════════════════════════════


class TestEvaluateAgentDependencies:

    def test_empty_nodes_returns_empty(self):
        assert evaluate_agent_dependencies([]) == []

    def test_pending_no_deps_is_ready(self):
        nodes = [{"node_id": "n1", "status": "pending", "depends_on": []}]
        assert evaluate_agent_dependencies(nodes) == ["n1"]

    def test_pending_with_incomplete_dep_not_ready(self):
        nodes = [
            {"node_id": "n1", "status": "running", "depends_on": []},
            {"node_id": "n2", "status": "pending", "depends_on": ["n1"]},
        ]
        assert evaluate_agent_dependencies(nodes) == []

    def test_pending_with_completed_dep_is_ready(self):
        nodes = [
            {"node_id": "n1", "status": "completed", "depends_on": []},
            {"node_id": "n2", "status": "pending", "depends_on": ["n1"]},
        ]
        assert evaluate_agent_dependencies(nodes) == ["n2"]

    def test_multi_level_chain_only_directly_unblocked(self):
        nodes = [
            {"node_id": "n1", "status": "completed"},
            {"node_id": "n2", "status": "pending", "depends_on": ["n1"]},
            {"node_id": "n3", "status": "pending", "depends_on": ["n2"]},
        ]
        ready = evaluate_agent_dependencies(nodes)
        assert ready == ["n2"]
        assert "n3" not in ready


# ═══════════════════════════════════════════════════════════════════════════════
# 2. schedule_next_agent_tasks
# ═══════════════════════════════════════════════════════════════════════════════


class TestScheduleNextAgentTasks:

    def test_promotes_pending_with_completed_dep(self):
        orch = _make_orch(nodes=[
            {"node_id": "n1", "status": "completed", "depends_on": [], "retry_count": 0, "max_retries": 3, "failure_reason": None, "recovery_strategy": None, "execution_metadata": {}, "started_at": None, "completed_at": None, "agent_name": "discovery", "label": ""},
            {"node_id": "n2", "status": "pending", "depends_on": ["n1"], "retry_count": 0, "max_retries": 3, "failure_reason": None, "recovery_strategy": None, "execution_metadata": {}, "started_at": None, "completed_at": None, "agent_name": "content_build", "label": ""},
        ])
        db, orches = _orch_db(orch)
        ready = schedule_next_agent_tasks("testorch001", db)
        assert "n2" in ready
        assert orches[0]["nodes"][1]["status"] == "ready"

    def test_returns_empty_when_no_ready_candidates(self):
        orch = _make_orch()
        db, _ = _orch_db(orch)
        ready = schedule_next_agent_tasks("testorch001", db)
        assert ready == []

    def test_returns_empty_for_unknown_orch(self):
        db, _ = _orch_db()
        ready = schedule_next_agent_tasks("no_such_id", db)
        assert ready == []


# ═══════════════════════════════════════════════════════════════════════════════
# 3. create_orchestration_plan
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateOrchestrationPlan:

    def test_correct_node_count(self):
        db, _ = _orch_db()
        doc = create_orchestration_plan("ws1", "", ["discovery", "content_build", "approval"], db)
        assert len(doc["nodes"]) == 3

    def test_first_node_is_ready(self):
        db, _ = _orch_db()
        doc = create_orchestration_plan("ws1", "", ["discovery", "content_build"], db)
        assert doc["nodes"][0]["status"] == "ready"
        assert doc["nodes"][1]["status"] == "pending"

    def test_sequential_edges_built(self):
        db, _ = _orch_db()
        doc = create_orchestration_plan("ws1", "", ["discovery", "content_build", "approval"], db)
        edges = doc["edges"]
        assert len(edges) == 2
        assert edges[0]["to"] == doc["nodes"][1]["node_id"]
        assert edges[1]["to"] == doc["nodes"][2]["node_id"]

    def test_workspace_slug_preserved(self):
        db, _ = _orch_db()
        doc = create_orchestration_plan("my_workspace", "", ["discovery"], db)
        assert doc["workspace_slug"] == "my_workspace"

    def test_priority_stored(self):
        db, _ = _orch_db()
        doc = create_orchestration_plan("ws", "", ["discovery"], db, priority="high")
        assert doc["priority"] == "high"

    def test_orchestration_id_generated(self):
        db, _ = _orch_db()
        doc = create_orchestration_plan("ws", "", ["discovery"], db)
        assert len(doc["orchestration_id"]) == 16


# ═══════════════════════════════════════════════════════════════════════════════
# 4. execute_orchestration_graph
# ═══════════════════════════════════════════════════════════════════════════════


class TestExecuteOrchestrationGraph:

    def test_starts_ready_nodes(self):
        db, orches = _orch_db(_make_orch())
        result = execute_orchestration_graph("testorch001", db)
        assert "node_a" in result["nodes_started"]
        assert result["total_started"] == 1

    def test_does_not_start_pending_nodes(self):
        db, orches = _orch_db(_make_orch())
        execute_orchestration_graph("testorch001", db)
        node_b = next(n for n in orches[0]["nodes"] if n["node_id"] == "node_b")
        assert node_b["status"] == "pending"

    def test_paused_orch_returns_error(self):
        db, _ = _orch_db(_make_orch(status="paused"))
        result = execute_orchestration_graph("testorch001", db)
        assert "error" in result
        assert "paused" in result["error"]

    def test_unknown_orch_returns_not_found(self):
        db, _ = _orch_db()
        result = execute_orchestration_graph("ghost", db)
        assert result["error"] == "not_found"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. handle_agent_failure
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleAgentFailure:

    def test_retry_when_under_max(self):
        orch = _make_orch()
        db, _ = _orch_db(orch)
        result = handle_agent_failure("testorch001", "node_a", "timeout", db)
        assert result["new_status"] == "retrying"
        assert result["retry_count"] == 1

    def test_escalate_when_at_max_retries(self):
        orch = _make_orch(nodes=[{
            "node_id": "node_a", "agent_name": "discovery", "label": "",
            "status": "failed", "depends_on": [], "retry_count": 3, "max_retries": 3,
            "failure_reason": None, "recovery_strategy": None,
            "execution_metadata": {}, "started_at": None, "completed_at": None,
        }])
        db, _ = _orch_db(orch)
        result = handle_agent_failure("testorch001", "node_a", "persistent_error", db)
        assert result["new_status"] == "escalated"

    def test_failure_reason_stored(self):
        db, orches = _orch_db(_make_orch())
        handle_agent_failure("testorch001", "node_a", "api_timeout", db)
        node = next(n for n in orches[0]["nodes"] if n["node_id"] == "node_a")
        assert node["failure_reason"] == "api_timeout"

    def test_retry_count_increments(self):
        db, orches = _orch_db(_make_orch())
        handle_agent_failure("testorch001", "node_a", "err", db)
        node = next(n for n in orches[0]["nodes"] if n["node_id"] == "node_a")
        assert node["retry_count"] == 1

    def test_unknown_orch_returns_error(self):
        db, _ = _orch_db()
        result = handle_agent_failure("no_orch", "n1", "err", db)
        assert result["error"] == "not_found"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. escalate_orchestration_issue
# ═══════════════════════════════════════════════════════════════════════════════


class TestEscalateOrchestrationIssue:

    def test_sets_node_status_escalated(self):
        db, orches = _orch_db(_make_orch())
        escalate_orchestration_issue("testorch001", "node_a", "quality_threshold_failed", db)
        node = next(n for n in orches[0]["nodes"] if n["node_id"] == "node_a")
        assert node["status"] == "escalated"

    def test_sets_orch_status_escalated(self):
        db, orches = _orch_db(_make_orch())
        escalate_orchestration_issue("testorch001", "node_a", "reason", db)
        assert orches[0]["status"] == "escalated"

    def test_escalation_status_field_set(self):
        db, orches = _orch_db(_make_orch())
        escalate_orchestration_issue("testorch001", "", "reason", db)
        assert orches[0]["escalation_status"] == "pending_operator_review"

    def test_unknown_orch_returns_error(self):
        db, _ = _orch_db()
        result = escalate_orchestration_issue("no_orch", "", "reason", db)
        assert result["error"] == "not_found"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. _compute_queue_priority
# ═══════════════════════════════════════════════════════════════════════════════


class TestComputeQueuePriority:

    def test_critical_urgency_gives_high_score(self):
        p = _compute_queue_priority("critical", True, 1.0, 0.9, 0.95)
        assert p == "critical"

    def test_background_conditions_gives_background(self):
        p = _compute_queue_priority("background", False, 72.0, 0.3, 0.5)
        assert p == "background"

    def test_short_deadline_boosts_priority(self):
        # normal urgency but <4hr deadline
        p = _compute_queue_priority("normal", False, 2.0, 0.5, 0.5)
        assert p in ("high", "critical")

    def test_deps_ready_adds_score(self):
        p_ready = _compute_queue_priority("normal", True, 25.0, 0.5, 0.5)
        p_not = _compute_queue_priority("normal", False, 25.0, 0.5, 0.5)
        assert _PRIORITY_LEVELS_6T.get(p_ready, 0) >= _PRIORITY_LEVELS_6T.get(p_not, 0)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. _compute_orchestration_telemetry
# ═══════════════════════════════════════════════════════════════════════════════


class TestComputeOrchestrationTelemetry:

    def test_empty_returns_zero_metrics(self):
        db, _ = _orch_db()
        result = _compute_orchestration_telemetry(db)
        assert result["total_orchestrations"] == 0
        assert result["completion_rate"] == 0.0

    def test_completed_orch_counted(self):
        db, _ = _orch_db(_make_orch(status="completed"))
        result = _compute_orchestration_telemetry(db)
        assert result["total_orchestrations"] == 1
        assert result["completed"] == 1

    def test_retry_total_aggregated(self):
        db, _ = _orch_db(_make_orch(retry_total=5))
        result = _compute_orchestration_telemetry(db)
        assert result["total_retries"] == 5

    def test_by_agent_breakdown(self):
        orch = _make_orch(nodes=[
            {"node_id": "n1", "agent_name": "discovery", "status": "completed", "retry_count": 0, "depends_on": [], "max_retries": 3, "failure_reason": None, "recovery_strategy": None, "execution_metadata": {}, "started_at": None, "completed_at": None, "label": ""},
            {"node_id": "n2", "agent_name": "content_build", "status": "running", "retry_count": 1, "depends_on": ["n1"], "max_retries": 3, "failure_reason": None, "recovery_strategy": None, "execution_metadata": {}, "started_at": None, "completed_at": None, "label": ""},
        ])
        db, _ = _orch_db(orch)
        result = _compute_orchestration_telemetry(db)
        assert "discovery" in result["by_agent"]
        assert result["by_agent"]["discovery"]["completed"] == 1
        assert result["by_agent"]["content_build"]["retries"] == 1

    def test_delegation_count_aggregated(self):
        db, _ = _orch_db(_make_orch(delegation_count=3))
        result = _compute_orchestration_telemetry(db)
        assert result["total_delegations"] == 3


# ═══════════════════════════════════════════════════════════════════════════════
# 9. POST /orchestrations — create endpoint
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestrationCreateEndpoint:

    def test_200_on_valid_chain(self):
        db, _ = _orch_db()
        with _patch(db):
            r = client.post("/orchestrations", json={
                "workspace_slug": "ws_test",
                "agent_chain": ["discovery", "content_build"],
            })
        assert r.status_code == 200

    def test_returns_orchestration_id(self):
        db, _ = _orch_db()
        with _patch(db):
            r = client.post("/orchestrations", json={
                "workspace_slug": "ws_test",
                "agent_chain": ["discovery"],
            })
        data = r.json()
        assert "item" in data
        assert "orchestration_id" in data["item"]

    def test_correct_node_count_in_response(self):
        db, _ = _orch_db()
        with _patch(db):
            r = client.post("/orchestrations", json={
                "workspace_slug": "ws_test",
                "agent_chain": ["discovery", "content_build", "approval"],
            })
        assert len(r.json()["item"]["nodes"]) == 3

    def test_400_on_empty_agent_chain(self):
        db, _ = _orch_db()
        with _patch(db):
            r = client.post("/orchestrations", json={
                "workspace_slug": "ws",
                "agent_chain": [],
            })
        assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# 10. GET /orchestrations — list endpoint
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestrationListGetEndpoints:

    def test_list_returns_200(self):
        db, _ = _orch_db(_make_orch())
        with _patch(db):
            r = client.get("/orchestrations")
        assert r.status_code == 200
        assert "items" in r.json()

    def test_list_total_matches(self):
        db, _ = _orch_db(_make_orch())
        with _patch(db):
            r = client.get("/orchestrations")
        assert r.json()["total"] == 1

    def test_get_single_200(self):
        db, _ = _orch_db(_make_orch())
        with _patch(db):
            r = client.get("/orchestrations/testorch001")
        assert r.status_code == 200
        assert r.json()["item"]["orchestration_id"] == "testorch001"

    def test_get_single_404_unknown(self):
        db, _ = _orch_db()
        with _patch(db):
            r = client.get("/orchestrations/no_such_orch")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 11. GET /orchestrations/{id}/graph + telemetry
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestrationGraphTelemetryEndpoints:

    def test_graph_200_with_nodes_edges(self):
        db, _ = _orch_db(_make_orch())
        with _patch(db):
            r = client.get("/orchestrations/testorch001/graph")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data
        assert "completion_rate" in data

    def test_graph_404_unknown(self):
        db, _ = _orch_db()
        with _patch(db):
            r = client.get("/orchestrations/ghost/graph")
        assert r.status_code == 404

    def test_single_telemetry_200(self):
        db, _ = _orch_db(_make_orch())
        with _patch(db):
            r = client.get("/orchestrations/testorch001/telemetry")
        assert r.status_code == 200
        data = r.json()
        assert "total_nodes" in data
        assert "completion_rate" in data
        assert "by_agent" in data

    def test_global_telemetry_200(self):
        db, _ = _orch_db(_make_orch())
        with _patch(db):
            r = client.get("/orchestrations/telemetry")
        assert r.status_code == 200
        data = r.json()
        assert "total_orchestrations" in data
        assert "completion_rate" in data
        assert "by_agent" in data


# ═══════════════════════════════════════════════════════════════════════════════
# 12. POST pause / resume
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestrationPauseResumeEndpoints:

    def test_pause_returns_paused(self):
        db, _ = _orch_db(_make_orch())
        with _patch(db):
            r = client.post("/orchestrations/testorch001/pause")
        assert r.status_code == 200
        assert r.json()["status"] == "paused"

    def test_pause_writes_to_db(self):
        db, orches = _orch_db(_make_orch())
        with _patch(db):
            client.post("/orchestrations/testorch001/pause")
        assert orches[0]["status"] == "paused"

    def test_resume_returns_running(self):
        db, _ = _orch_db(_make_orch(status="paused"))
        with _patch(db):
            r = client.post("/orchestrations/testorch001/resume")
        assert r.status_code == 200
        assert r.json()["status"] == "running"

    def test_pause_404_unknown(self):
        db, _ = _orch_db()
        with _patch(db):
            r = client.post("/orchestrations/unknown/pause")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 13. POST retry-node
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestrationRetryNodeEndpoint:

    def _orch_with_failed_node(self):
        return _make_orch(nodes=[
            {
                "node_id": "node_a", "agent_name": "discovery", "label": "",
                "status": "failed", "depends_on": [], "retry_count": 1, "max_retries": 3,
                "failure_reason": "timeout", "recovery_strategy": None,
                "execution_metadata": {}, "started_at": None, "completed_at": None,
            },
        ])

    def test_200_on_valid_retry(self):
        db, _ = _orch_db(self._orch_with_failed_node())
        with _patch(db):
            r = client.post("/orchestrations/testorch001/retry-node",
                            json={"node_id": "node_a"})
        assert r.status_code == 200
        assert r.json()["status"] == "retrying"

    def test_retry_increments_retry_count(self):
        db, orches = _orch_db(self._orch_with_failed_node())
        with _patch(db):
            client.post("/orchestrations/testorch001/retry-node",
                        json={"node_id": "node_a"})
        node = orches[0]["nodes"][0]
        assert node["retry_count"] == 2

    def test_404_unknown_orch(self):
        db, _ = _orch_db()
        with _patch(db):
            r = client.post("/orchestrations/ghost/retry-node",
                            json={"node_id": "node_a"})
        assert r.status_code == 404

    def test_400_node_not_in_failed_state(self):
        db, _ = _orch_db(_make_orch())  # node_a is 'ready'
        with _patch(db):
            r = client.post("/orchestrations/testorch001/retry-node",
                            json={"node_id": "node_a"})
        assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# 14. POST escalate
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestrationEscalateEndpoint:

    def test_200_on_valid_escalate(self):
        db, _ = _orch_db(_make_orch())
        with _patch(db):
            r = client.post("/orchestrations/testorch001/escalate",
                            json={"node_id": "node_a", "reason": "quality_below_threshold"})
        assert r.status_code == 200
        data = r.json()
        assert data["escalation_status"] == "pending_operator_review"

    def test_escalate_writes_to_db(self):
        db, orches = _orch_db(_make_orch())
        with _patch(db):
            client.post("/orchestrations/testorch001/escalate",
                        json={"node_id": "node_a", "reason": "test"})
        assert orches[0]["status"] == "escalated"

    def test_404_unknown_orch(self):
        db, _ = _orch_db()
        with _patch(db):
            r = client.post("/orchestrations/no_orch/escalate",
                            json={"reason": "test"})
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 15. GET /agents/profiles
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentProfilesEndpoint:

    def test_returns_all_default_profiles(self):
        db, _ = _orch_db()
        with _patch(db):
            r = client.get("/agents/profiles")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == len(_DEFAULT_AGENT_PROFILES_6T)
        assert len(data["profiles"]) == len(_DEFAULT_AGENT_PROFILES_6T)

    def test_each_profile_has_agent_name(self):
        db, _ = _orch_db()
        with _patch(db):
            r = client.get("/agents/profiles")
        names = {p["agent_name"] for p in r.json()["profiles"]}
        assert "discovery" in names
        assert "content_build" in names

    def test_each_profile_has_success_rate(self):
        db, _ = _orch_db()
        with _patch(db):
            r = client.get("/agents/profiles")
        for p in r.json()["profiles"]:
            assert "success_rate" in p
            assert 0.0 <= p["success_rate"] <= 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# 16. GET /agents/utilization
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentUtilizationEndpoint:

    def test_returns_200_with_agents_list(self):
        db, _ = _orch_db()
        with _patch(db):
            r = client.get("/agents/utilization")
        assert r.status_code == 200
        data = r.json()
        assert "agents" in data
        assert "total_running" in data

    def test_utilization_rate_computed(self):
        db, _ = _orch_db()
        with _patch(db):
            r = client.get("/agents/utilization")
        for agent in r.json()["agents"]:
            assert "utilization_rate" in agent
            assert 0.0 <= agent["utilization_rate"] <= 1.0

    def test_workspace_slug_param_accepted(self):
        db, _ = _orch_db()
        with _patch(db):
            r = client.get("/agents/utilization?workspace_slug=test_ws")
        assert r.status_code == 200
