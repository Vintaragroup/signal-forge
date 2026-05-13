"""Phase 6N: Memory-Aware Agent Execution — backend tests.

Tests cover:
- build_memory_context() with existing memory → correct fields populated
- build_memory_context() with no memory → has_memory=False
- _enforce_memory_constraints() — blocked claim detected
- _enforce_memory_constraints() — clean content passes
- _enforce_memory_constraints() — losing pattern triggers warning
- _enforce_memory_constraints() — no memory context → always clean
- Discovery run workflow_run has memory fields populated
- Content build run workflow_run has memory fields populated
- Content build assets include memory_context_used + tone hints
- GET /workflow-runs/{run_id}/memory-context returns snapshot
- Auto-proposal includes memory_version_used and reasoning_trace
- WorkflowRunCreateRequest accepts memory fields
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch
from bson import ObjectId

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Import the app under test
# ---------------------------------------------------------------------------
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

from main import app, build_memory_context, _enforce_memory_constraints

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

WORKSPACE = "phase-6n-test-workspace"
MODULE = "media_growth"


def _make_mock_memory(
    version: int = 2,
    winning: list[str] | None = None,
    losing: list[str] | None = None,
    blocked: list[str] | None = None,
    tone: str = "professional",
    style: str = "direct",
) -> dict:
    oid = ObjectId()
    return {
        "_id": oid,
        "workspace_slug": WORKSPACE,
        "version": version,
        "voice_tone": {"tone": tone, "style": style, "examples": [], "forbidden_phrases": []},
        "winning_patterns": winning or ["LinkedIn short-form posts drove highest engagement"],
        "losing_patterns": losing or ["overly salesy language"],
        "blocked_claims": blocked or ["guaranteed results", "risk-free"],
        "approved_claims": ["We serve 500+ brands"],
        "distribution_preferences": {"channels": ["LinkedIn", "Email"], "manual_only": True},
        "source_preferences": [{"name": "LinkedIn", "priority": "high"}],
        "workflow_preferences": {"max_assets_per_run": 5, "review_all_assets": True},
        "approval_tendencies": {"approval_rate": 0.75},
        "performance_notes": [],
    }


def _make_mock_db(memory: dict | None = None) -> MagicMock:
    db = MagicMock()
    db.client_memories.find_one.return_value = memory
    return db


# ---------------------------------------------------------------------------
# Tests: build_memory_context
# ---------------------------------------------------------------------------

class TestBuildMemoryContext:
    def test_returns_full_context_when_memory_exists(self):
        mem = _make_mock_memory()
        db = _make_mock_db(mem)
        ctx = build_memory_context(db, WORKSPACE)
        assert ctx["has_memory"] is True
        assert ctx["memory_id"] == str(mem["_id"])
        assert ctx["memory_version"] == 2
        assert isinstance(ctx["memory_context_hash"], str)
        assert len(ctx["memory_context_hash"]) == 32  # md5 hex
        assert ctx["voice_tone"]["tone"] == "professional"
        assert "LinkedIn short-form posts" in ctx["winning_patterns"][0]
        assert "overly salesy language" in ctx["losing_patterns"][0]
        assert "guaranteed results" in ctx["blocked_claims"][0]
        assert isinstance(ctx["snapshot"], dict)
        assert "snapshot_taken_at" in ctx

    def test_returns_has_memory_false_when_no_memory(self):
        db = _make_mock_db(None)
        ctx = build_memory_context(db, WORKSPACE)
        assert ctx["has_memory"] is False
        assert "memory_id" not in ctx

    def test_hash_is_deterministic(self):
        mem = _make_mock_memory()
        db = _make_mock_db(mem)
        ctx1 = build_memory_context(db, WORKSPACE)
        ctx2 = build_memory_context(db, WORKSPACE)
        assert ctx1["memory_context_hash"] == ctx2["memory_context_hash"]

    def test_hash_changes_when_patterns_change(self):
        mem_a = _make_mock_memory(winning=["Pattern A"])
        mem_b = _make_mock_memory(winning=["Pattern B"])
        db_a = _make_mock_db(mem_a)
        db_b = _make_mock_db(mem_b)
        ctx_a = build_memory_context(db_a, WORKSPACE)
        ctx_b = build_memory_context(db_b, WORKSPACE)
        assert ctx_a["memory_context_hash"] != ctx_b["memory_context_hash"]

    def test_handles_db_exception_gracefully(self):
        db = MagicMock()
        db.client_memories.find_one.side_effect = Exception("DB error")
        ctx = build_memory_context(db, WORKSPACE)
        assert ctx["has_memory"] is False

    def test_snapshot_contains_expected_keys(self):
        mem = _make_mock_memory()
        db = _make_mock_db(mem)
        ctx = build_memory_context(db, WORKSPACE)
        snap = ctx["snapshot"]
        for key in ("voice_tone", "winning_patterns", "losing_patterns", "blocked_claims", "distribution_preferences", "source_preferences"):
            assert key in snap, f"Snapshot missing key: {key}"


# ---------------------------------------------------------------------------
# Tests: _enforce_memory_constraints
# ---------------------------------------------------------------------------

class TestEnforceMemoryConstraints:
    def _ctx(self):
        return {
            "has_memory": True,
            "blocked_claims": ["guaranteed results", "risk-free"],
            "losing_patterns": ["overly salesy"],
        }

    def test_blocked_claim_detected(self):
        text = "We provide guaranteed results for every client."
        result = _enforce_memory_constraints(text, self._ctx())
        assert not result["clean"]
        assert len(result["violations"]) == 1
        assert "guaranteed results" in result["violations"][0]

    def test_clean_text_passes(self):
        text = "We help media operators build strategic partnerships."
        result = _enforce_memory_constraints(text, self._ctx())
        assert result["clean"]
        assert result["violations"] == []
        assert result["warnings"] == []

    def test_losing_pattern_triggers_warning(self):
        text = "Don't use overly salesy language in this draft."
        result = _enforce_memory_constraints(text, self._ctx())
        assert result["clean"]  # warning not a violation
        assert len(result["warnings"]) == 1
        assert "overly salesy" in result["warnings"][0]

    def test_no_memory_context_always_clean(self):
        result = _enforce_memory_constraints("any content here", {"has_memory": False})
        assert result["clean"]
        assert result["violations"] == []
        assert result["warnings"] == []

    def test_multiple_violations_detected(self):
        text = "Guaranteed results risk-free every time."
        result = _enforce_memory_constraints(text, self._ctx())
        assert not result["clean"]
        assert len(result["violations"]) == 2

    def test_empty_text_clean(self):
        result = _enforce_memory_constraints("", self._ctx())
        assert result["clean"]


# ---------------------------------------------------------------------------
# Tests: workflow run memory fields via API
# ---------------------------------------------------------------------------

def _setup_discovery_db() -> MagicMock:
    """Return a mock db suitable for a discovery run with memory context."""
    mem = _make_mock_memory()
    task_id = ObjectId()
    task_doc = {
        "_id": task_id,
        "workspace_slug": WORKSPACE,
        "module": MODULE,
        "card_id": "content_discovery",
        "task_type": "discovery",
        "status": "queued",
        "priority": "normal",
        "input_config": {"limit": 2},
        "outbound_actions_taken": 0,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    db = MagicMock()
    db.client_memories.find_one.return_value = mem
    db.agent_tasks.find_one.return_value = task_doc
    db.agent_tasks.update_one.return_value = MagicMock(modified_count=1)
    db.agent_runs.insert_one.return_value = MagicMock(inserted_id=ObjectId())
    db.agent_runs.update_one.return_value = MagicMock(modified_count=1)
    db.agent_runs.find_one.return_value = {"run_id": "mock_run", "_id": ObjectId()}
    db.discovery_run_summaries.insert_one.return_value = MagicMock(inserted_id=ObjectId())
    db.workflow_runs.insert_one.return_value = MagicMock(inserted_id=ObjectId())
    return db, task_id, mem


class TestDiscoveryRunMemoryInjection:
    def test_discovery_run_records_memory_context(self):
        """When a discovery task runs, the resulting workflow_run should include memory fields."""
        db, task_id, mem = _setup_discovery_db()

        from main import _run_content_discovery_task

        with patch("main.generate_discovery_insights", return_value=[], create=True), \
             patch("main.get_configured_sources", return_value=[], create=True):
            # Run the task handler directly
            task_doc = db.agent_tasks.find_one.return_value
            _run_content_discovery_task.__globals__["get_configured_sources"] = lambda *a, **k: []
            # We only verify the insert_one call receives memory fields
            _run_content_discovery_task(db, task_doc, datetime.now(timezone.utc))

        # Verify workflow_runs.insert_one was called with memory context fields
        call_args = db.workflow_runs.insert_one.call_args
        assert call_args is not None
        doc_inserted = call_args[0][0]
        assert doc_inserted.get("client_memory_id") == str(mem["_id"])
        assert doc_inserted.get("client_memory_version") == 2
        assert isinstance(doc_inserted.get("memory_context_hash"), str)
        assert "memory_snapshot" in doc_inserted
        assert doc_inserted["outputs"]["memory_informed"] is True

    def test_discovery_run_without_memory_has_empty_memory_fields(self):
        """Without client memory, memory fields should be empty/falsy."""
        db, task_id, _ = _setup_discovery_db()
        db.client_memories.find_one.return_value = None  # no memory

        from main import _run_content_discovery_task

        task_doc = db.agent_tasks.find_one.return_value
        _run_content_discovery_task(db, task_doc, datetime.now(timezone.utc))

        call_args = db.workflow_runs.insert_one.call_args
        doc_inserted = call_args[0][0]
        assert doc_inserted.get("client_memory_id") == ""
        assert doc_inserted.get("client_memory_version") == 0
        assert doc_inserted["outputs"]["memory_informed"] is False


class TestContentBuildRunMemoryInjection:
    def _setup_db(self):
        mem = _make_mock_memory()
        insight_id = ObjectId()
        insight_doc = {
            "_id": insight_id,
            "workspace_slug": WORKSPACE,
            "module": MODULE,
            "title": "Test Insight About LinkedIn Posts",
            "summary": "Brands that post short LinkedIn updates see 3x engagement",
            "confidence_score": 0.85,
            "status": "approved",
            "evidence": [{"platform": "LinkedIn", "source": "test"}],
        }
        task_id = ObjectId()
        task_doc = {
            "_id": task_id,
            "workspace_slug": WORKSPACE,
            "module": MODULE,
            "card_id": "content_build",
            "task_type": "content_build",
            "status": "queued",
            "priority": "normal",
            "input_config": {"limit": 1},
            "outbound_actions_taken": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        db = MagicMock()
        db.client_memories.find_one.return_value = mem
        db.agent_tasks.find_one.return_value = task_doc
        db.agent_tasks.update_one.return_value = MagicMock(modified_count=1)
        db.agent_runs.insert_one.return_value = MagicMock(inserted_id=ObjectId())
        db.agent_runs.update_one.return_value = MagicMock(modified_count=1)
        db.agent_runs.find_one.return_value = {"run_id": "mock_run", "_id": ObjectId()}
        wf_run_id = ObjectId()
        db.workflow_runs.insert_one.return_value = MagicMock(inserted_id=wf_run_id)
        db.workflow_runs.update_one.return_value = MagicMock(modified_count=1)
        db.workflow_assets.insert_one.return_value = MagicMock(inserted_id=ObjectId())
        db.workflow_assets.find.return_value = []
        db.approval_requests.insert_one.return_value = MagicMock(inserted_id=ObjectId())
        # Return insight from discovery_insights query
        db.discovery_insights.find.return_value.__iter__ = MagicMock(return_value=iter([insight_doc]))
        db.discovery_insights.find.return_value.sort.return_value.limit.return_value = [insight_doc]
        return db, task_doc, mem

    def test_content_build_workflow_run_has_memory_fields(self):
        from main import _run_content_build_task

        db, task_doc, mem = self._setup_db()
        _run_content_build_task(db, task_doc, datetime.now(timezone.utc))

        # First insert_one is the workflow_run
        first_insert = db.workflow_runs.insert_one.call_args_list[0]
        doc = first_insert[0][0]
        assert doc.get("client_memory_id") == str(mem["_id"])
        assert doc.get("client_memory_version") == 2
        assert isinstance(doc.get("memory_context_hash"), str)
        assert "memory_snapshot" in doc

    def test_content_build_asset_body_includes_memory_tone(self):
        from main import _run_content_build_task

        db, task_doc, mem = self._setup_db()
        _run_content_build_task(db, task_doc, datetime.now(timezone.utc))

        # The asset body should be in the first workflow_assets insert
        asset_insert = db.workflow_assets.insert_one.call_args_list[0]
        asset_doc = asset_insert[0][0]
        body = asset_doc.get("body", "")
        # Should include tone from memory
        assert "professional" in body or "direct" in body or "Memory" in body

    def test_content_build_asset_has_memory_context_used_true(self):
        from main import _run_content_build_task

        db, task_doc, mem = self._setup_db()
        _run_content_build_task(db, task_doc, datetime.now(timezone.utc))

        asset_insert = db.workflow_assets.insert_one.call_args_list[0]
        asset_doc = asset_insert[0][0]
        assert asset_doc.get("memory_context_used") is True
        assert "memory_violations" in asset_doc
        assert "memory_warnings" in asset_doc

    def test_content_build_without_memory_asset_has_memory_context_used_false(self):
        from main import _run_content_build_task

        db, task_doc, _ = self._setup_db()
        db.client_memories.find_one.return_value = None  # no memory

        _run_content_build_task(db, task_doc, datetime.now(timezone.utc))

        asset_insert = db.workflow_assets.insert_one.call_args_list[0]
        asset_doc = asset_insert[0][0]
        assert asset_doc.get("memory_context_used") is False


# ---------------------------------------------------------------------------
# Tests: GET /workflow-runs/{run_id}/memory-context endpoint
# ---------------------------------------------------------------------------

class TestWorkflowRunMemoryContextEndpoint:
    def _make_run_doc(self, with_memory: bool = True):
        run_id = ObjectId()
        mem_id = str(ObjectId()) if with_memory else ""
        return {
            "_id": run_id,
            "run_type": "content_build",
            "client_memory_id": mem_id,
            "client_memory_version": 2 if with_memory else 0,
            "memory_context_hash": "abc123" if with_memory else "",
            "memory_snapshot": {
                "voice_tone": {"tone": "professional", "style": "direct"},
                "winning_patterns": ["Short LinkedIn posts"],
                "blocked_claims": ["guaranteed results"],
            } if with_memory else {},
        }, run_id

    def test_returns_memory_snapshot_for_existing_run(self):
        run_doc, run_id = self._make_run_doc(with_memory=True)
        with patch("main.get_client") as mock_get_client, \
             patch("main.get_database") as mock_get_db:
            mock_db = MagicMock()
            mock_db.workflow_runs.find_one.return_value = run_doc
            mock_get_db.return_value = mock_db
            mock_client = MagicMock()
            mock_get_client.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_get_client.return_value.__exit__ = MagicMock(return_value=False)
            mock_get_client.return_value = mock_client
            mock_get_db.return_value = mock_db

            resp = client.get(f"/workflow-runs/{str(run_id)}/memory-context")
            assert resp.status_code == 200
            data = resp.json()
            assert data["has_memory"] is True
            assert data["client_memory_version"] == 2
            assert "memory_snapshot" in data
            assert data["memory_snapshot"]["voice_tone"]["tone"] == "professional"

    def test_returns_404_for_nonexistent_run(self):
        fake_id = str(ObjectId())
        with patch("main.get_client") as mock_get_client, \
             patch("main.get_database") as mock_get_db:
            mock_db = MagicMock()
            mock_db.workflow_runs.find_one.return_value = None
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_get_db.return_value = mock_db

            resp = client.get(f"/workflow-runs/{fake_id}/memory-context")
            assert resp.status_code == 404

    def test_returns_404_for_nonexistent_slug_run_id(self):
        """A non-ObjectId run_id is treated as a source_task_id slug lookup; 404 if not found."""
        with patch("main.get_client") as mock_get_client, \
             patch("main.get_database") as mock_get_db:
            mock_db = MagicMock()
            mock_db.workflow_runs.find_one.return_value = None
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_get_db.return_value = mock_db

            resp = client.get("/workflow-runs/not-a-valid-id/memory-context")
            assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: _try_propose_memory_update includes memory_version_used
# ---------------------------------------------------------------------------

class TestProposalMemoryVersionTracing:
    def test_proposal_includes_memory_version_used(self):
        mem = _make_mock_memory(version=3)
        db = MagicMock()
        db.client_memories.find_one.return_value = mem
        db.memory_update_proposals.insert_one.return_value = MagicMock(inserted_id=ObjectId())

        from main import _try_propose_memory_update

        _try_propose_memory_update(
            db,
            workspace_slug=WORKSPACE,
            workflow_run_id=str(ObjectId()),
            source="asset_approval",
            proposed_change={"field": "winning_patterns", "change_type": "add", "new_value": "New pattern"},
            evidence="Operator approved asset",
            confidence=0.85,
        )

        call_args = db.memory_update_proposals.insert_one.call_args
        assert call_args is not None
        proposal_doc = call_args[0][0]
        assert proposal_doc.get("memory_version_used") == 3
        assert "reasoning_trace" in proposal_doc
        assert "asset_approval" in proposal_doc["reasoning_trace"]

    def test_proposal_silently_skips_when_no_memory(self):
        db = MagicMock()
        db.client_memories.find_one.return_value = None

        from main import _try_propose_memory_update

        # Should not raise
        _try_propose_memory_update(
            db,
            workspace_slug=WORKSPACE,
            workflow_run_id=str(ObjectId()),
            source="asset_approval",
            proposed_change={"field": "winning_patterns", "change_type": "add", "new_value": "x"},
            evidence="test",
        )
        db.memory_update_proposals.insert_one.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: WorkflowRunCreateRequest accepts memory fields
# ---------------------------------------------------------------------------

class TestWorkflowRunCreateRequestMemoryFields:
    def test_create_request_accepts_memory_fields(self):
        """WorkflowRunCreateRequest should validate with memory fields present."""
        from main import WorkflowRunCreateRequest

        req = WorkflowRunCreateRequest(
            workspace_slug=WORKSPACE,
            workflow_stage=2,
            run_type="discovery",
            client_memory_id=str(ObjectId()),
            client_memory_version=2,
            memory_context_hash="abc123def456",
        )
        assert req.client_memory_id != ""
        assert req.client_memory_version == 2
        assert req.memory_context_hash == "abc123def456"

    def test_create_request_memory_fields_default_empty(self):
        """Memory fields should default to empty/zero when not supplied."""
        from main import WorkflowRunCreateRequest

        req = WorkflowRunCreateRequest(
            workspace_slug=WORKSPACE,
            workflow_stage=2,
            run_type="content_build",
        )
        assert req.client_memory_id == ""
        assert req.client_memory_version == 0
        assert req.memory_context_hash == ""
