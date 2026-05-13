"""Phase 6O: Tests for Memory Governance, Version History, Health, Rollback, Conflicts, and Diffs."""
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
    """Context manager: patch get_client and get_database."""
    mongo_client = MagicMock()
    mongo_client.close = MagicMock()
    return patch.multiple(
        "main",
        get_client=lambda: mongo_client,
        get_database=lambda c: db,
    )


def _utc_now():
    return datetime.now(timezone.utc)


def _make_db(memories=None, proposals=None, history=None):
    db = MagicMock()

    _memories: list[dict] = [dict(m) for m in (memories or [])]
    for m in _memories:
        if "_id" not in m:
            m["_id"] = ObjectId()

    _proposals: list[dict] = [dict(p) for p in (proposals or [])]
    for p in _proposals:
        if "_id" not in p:
            p["_id"] = ObjectId()

    _history: list[dict] = [dict(h) for h in (history or [])]
    for h in _history:
        if "_id" not in h:
            h["_id"] = ObjectId()

    # ── client_memories ──────────────────────────────────────────────────────

    def mem_find_one(q, *args, **kwargs):
        for m in _memories:
            if _matches(m, q or {}):
                return dict(m)
        return None

    def mem_update_one(q, upd, *args, **kwargs):
        for m in _memories:
            if _matches(m, q or {}):
                if "$set" in upd:
                    m.update(upd["$set"])
                break

    def mem_insert_one(doc):
        doc["_id"] = doc.get("_id") or ObjectId()
        _memories.append(doc)
        r = MagicMock()
        r.inserted_id = doc["_id"]
        return r

    db.client_memories.find_one = mem_find_one
    db.client_memories.update_one = mem_update_one
    db.client_memories.insert_one = mem_insert_one

    # ── memory_update_proposals ──────────────────────────────────────────────

    def prop_find_one(q, *args, **kwargs):
        for p in _proposals:
            if _matches(p, q or {}):
                return dict(p)
        return None

    def prop_find(q=None, *args, **kwargs):
        results = [dict(p) for p in _proposals if _matches(p, q or {})]
        mock = MagicMock()
        mock.sort.return_value = mock
        mock.limit.return_value = iter(results)
        return mock

    def prop_insert_one(doc):
        doc["_id"] = doc.get("_id") or ObjectId()
        _proposals.append(doc)
        r = MagicMock()
        r.inserted_id = doc["_id"]
        return r

    def prop_update_one(q, upd, *args, **kwargs):
        for p in _proposals:
            if _matches(p, q or {}):
                if "$set" in upd:
                    p.update(upd["$set"])
                break

    def prop_count_documents(q=None, *args, **kwargs):
        return sum(1 for p in _proposals if _matches(p, q or {}))

    db.memory_update_proposals.find_one = prop_find_one
    db.memory_update_proposals.find = prop_find
    db.memory_update_proposals.insert_one = prop_insert_one
    db.memory_update_proposals.update_one = prop_update_one
    db.memory_update_proposals.count_documents = prop_count_documents

    # ── memory_version_history ───────────────────────────────────────────────

    def hist_find_one(q, *args, **kwargs):
        for h in _history:
            if _matches(h, q or {}):
                return dict(h)
        return None

    def hist_find(q=None, *args, **kwargs):
        results = [dict(h) for h in _history if _matches(h, q or {})]
        mock = MagicMock()
        mock.sort.return_value = mock
        mock.limit.return_value = iter(results)
        return mock

    # Track calls so tests can assert on insert_one
    _hist_inserted: list[dict] = []

    def hist_insert_one(doc):
        doc["_id"] = doc.get("_id") or ObjectId()
        _history.append(doc)
        _hist_inserted.append(doc)
        r = MagicMock()
        r.inserted_id = doc["_id"]
        return r

    db.memory_version_history.find_one = hist_find_one
    db.memory_version_history.find = hist_find
    db.memory_version_history.insert_one = hist_insert_one
    db._hist_inserted = _hist_inserted  # expose for assertions

    return db


def _matches(doc: dict, query: dict) -> bool:
    """Simple MongoDB query matcher supporting dotted paths and ObjectId string coercion."""
    for k, v in query.items():
        if "." in k:
            parts = k.split(".")
            cur = doc
            for part in parts:
                cur = (cur or {}).get(part)
            if cur != v:
                return False
        else:
            dv = doc.get(k)
            if isinstance(v, ObjectId):
                if dv != v and str(dv) != str(v):
                    return False
            else:
                if dv != v and str(dv) != str(v):
                    return False
    return True


def _base_memory(version: int = 2) -> dict:
    return {
        "_id": ObjectId(),
        "workspace_slug": "test-ws",
        "foundation_template_slug": "media_growth",
        "foundation_template_name": "Media Growth",
        "version": version,
        "winning_patterns": ["LinkedIn short-form posts drove highest engagement"],
        "losing_patterns": ["Long-form cold emails had low reply rates"],
        "approved_claims": ["Award-winning content agency"],
        "blocked_claims": ["guaranteed ROI"],
        "voice_tone": {"tone": "engaging", "style": "authentic"},
        "positioning": {"what_they_do": "Content marketing"},
        "icp": {},
        "performance_notes": [],
        "updated_at": _utc_now(),
        "created_at": _utc_now(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# TestConflictDetection  (unit tests — no HTTP)
# ─────────────────────────────────────────────────────────────────────────────

class TestConflictDetection:
    """Tests for _detect_proposal_conflicts helper."""

    def test_winning_losing_overlap_detected(self):
        memory = _base_memory()
        # Use enough overlapping words to exceed threshold 0.40
        change = {
            "field": "winning_patterns",
            "change_type": "add",
            "new_value": "Long-form cold emails low reply rates great",  # shares many tokens with losing pattern
        }
        conflicts = main._detect_proposal_conflicts(memory, change)
        assert len(conflicts) >= 1
        assert any(c["conflict_type"] == "winning_losing_overlap" for c in conflicts)

    def test_losing_winning_overlap_detected(self):
        memory = _base_memory()
        change = {
            "field": "losing_patterns",
            "change_type": "add",
            "new_value": "LinkedIn short-form posts highest engagement drove results",
        }
        conflicts = main._detect_proposal_conflicts(memory, change)
        assert any(c["conflict_type"] == "losing_winning_overlap" for c in conflicts)

    def test_no_conflict_disjoint_patterns(self):
        memory = _base_memory()
        change = {
            "field": "winning_patterns",
            "change_type": "add",
            "new_value": "Video tutorials generate newsletter signups",
        }
        conflicts = main._detect_proposal_conflicts(memory, change)
        assert conflicts == []

    def test_blocked_approved_overlap_detected(self):
        memory = _base_memory()
        change = {
            "field": "blocked_claims",
            "change_type": "add",
            "new_value": "Award-winning content agency results",  # high overlap with approved_claims
        }
        conflicts = main._detect_proposal_conflicts(memory, change)
        assert any(c["conflict_type"] == "blocked_approved_overlap" for c in conflicts)

    def test_tone_contradiction_detected(self):
        memory = _base_memory()
        memory["voice_tone"] = {"tone": "formal", "style": "corporate"}
        change = {
            "field": "voice_tone",
            "change_type": "update",
            "new_value": {"tone": "casual", "style": "conversational"},
        }
        conflicts = main._detect_proposal_conflicts(memory, change)
        assert any(c["conflict_type"] == "tone_contradiction" for c in conflicts)

    def test_tone_same_no_conflict(self):
        memory = _base_memory()
        memory["voice_tone"] = {"tone": "engaging", "style": "authentic"}
        change = {
            "field": "voice_tone",
            "change_type": "update",
            "new_value": {"tone": "engaging", "style": "bold"},
        }
        conflicts = main._detect_proposal_conflicts(memory, change)
        tone_conflicts = [c for c in conflicts if c["conflict_type"] == "tone_contradiction"]
        assert len(tone_conflicts) == 0

    def test_empty_memory_no_conflict(self):
        conflicts = main._detect_proposal_conflicts({}, {"field": "winning_patterns", "change_type": "add", "new_value": "anything"})
        assert conflicts == []


# ─────────────────────────────────────────────────────────────────────────────
# TestDuplicatePrevention  (unit tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestDuplicatePrevention:
    def test_exact_duplicate_pending_proposal(self):
        existing = {
            "_id": ObjectId(),
            "workspace_slug": "test-ws",
            "status": "pending",
            "proposed_change": {
                "field": "winning_patterns",
                "change_type": "add",
                "new_value": "LinkedIn drives engagement",
            },
        }
        db = _make_db(proposals=[existing])
        result = main._detect_proposal_duplicate(
            db, "test-ws",
            {"field": "winning_patterns", "change_type": "add", "new_value": "LinkedIn drives engagement"},
        )
        assert result["is_duplicate"] is True
        assert result["similarity"] == 1.0

    def test_no_duplicate_when_different_value(self):
        existing = {
            "_id": ObjectId(),
            "workspace_slug": "test-ws",
            "status": "pending",
            "proposed_change": {"field": "winning_patterns", "new_value": "podcast outreach works great"},
        }
        db = _make_db(proposals=[existing])
        result = main._detect_proposal_duplicate(
            db, "test-ws",
            {"field": "winning_patterns", "new_value": "video tutorials generate leads"},
        )
        assert result["is_duplicate"] is False

    def test_near_duplicate_detected(self):
        existing = {
            "_id": ObjectId(),
            "workspace_slug": "test-ws",
            "status": "pending",
            "proposed_change": {
                "field": "winning_patterns",
                "new_value": "LinkedIn short posts drive engagement well",
            },
        }
        db = _make_db(proposals=[existing])
        result = main._detect_proposal_duplicate(
            db, "test-ws",
            {"field": "winning_patterns", "new_value": "LinkedIn short posts drive engagement"},
        )
        assert result["is_duplicate"] is True

    def test_empty_db_no_duplicate(self):
        db = _make_db()
        result = main._detect_proposal_duplicate(
            db, "test-ws", {"field": "winning_patterns", "new_value": "brand new insight"},
        )
        assert result["is_duplicate"] is False


# ─────────────────────────────────────────────────────────────────────────────
# TestMemoryDiff  (unit tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryDiff:
    def test_list_add_diff(self):
        memory = _base_memory()
        change = {"field": "winning_patterns", "change_type": "add", "new_value": "Webinar series doubles pipeline"}
        diff = main._generate_memory_diff(memory, change)
        assert "Webinar series doubles pipeline" in diff["additions"]
        assert diff["has_changes"] is True

    def test_list_remove_diff(self):
        memory = _base_memory()
        change = {
            "field": "winning_patterns",
            "change_type": "remove",
            "new_value": "LinkedIn short-form posts drove highest engagement",
        }
        diff = main._generate_memory_diff(memory, change)
        assert "LinkedIn short-form posts drove highest engagement" in diff["removals"]
        assert diff["has_changes"] is True

    def test_list_update_diff_replace(self):
        memory = _base_memory()
        change = {"field": "winning_patterns", "change_type": "update", "new_value": ["New pattern only"]}
        diff = main._generate_memory_diff(memory, change)
        assert "New pattern only" in diff["additions"]

    def test_no_change_when_already_present(self):
        memory = _base_memory()
        existing = "LinkedIn short-form posts drove highest engagement"
        change = {"field": "winning_patterns", "change_type": "add", "new_value": existing}
        diff = main._generate_memory_diff(memory, change)
        assert diff["has_changes"] is False

    def test_scalar_field_diff(self):
        memory = _base_memory()
        change = {"field": "voice_tone", "change_type": "update", "new_value": {"tone": "bold", "style": "direct"}}
        diff = main._generate_memory_diff(memory, change)
        assert diff["has_changes"] is True


# ─────────────────────────────────────────────────────────────────────────────
# TestHealthScore  (unit tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthScore:
    def test_healthy_memory(self):
        memory = _base_memory()
        db = _make_db()
        health = main._compute_memory_health(db, memory)
        assert health["status"] in ("healthy", "needs_review", "conflicted")
        assert 0.0 <= health["memory_health_score"] <= 1.0

    def test_conflicted_memory(self):
        memory = _base_memory()
        # Both lists share substantial words → conflict detected
        memory["winning_patterns"] = ["Long-form cold emails drive pipeline growth"]
        memory["losing_patterns"] = ["Long-form cold emails drive pipeline low reply"]
        db = _make_db()
        health = main._compute_memory_health(db, memory)
        assert health["conflict_count"] >= 1
        assert health["memory_health_score"] < 1.0

    def test_stale_memory(self):
        memory = _base_memory()
        memory["updated_at"] = _utc_now() - timedelta(days=40)
        db = _make_db()
        health = main._compute_memory_health(db, memory)
        assert health["stale"] is True

    def test_empty_memory_no_crash(self):
        db = _make_db()
        health = main._compute_memory_health(db, {})
        assert health is not None


# ─────────────────────────────────────────────────────────────────────────────
# TestVersionHistory  (HTTP endpoints)
# ─────────────────────────────────────────────────────────────────────────────

class TestVersionHistory:
    def test_snapshot_writes_to_history(self):
        memory = _base_memory()
        db = _make_db()
        main._snapshot_memory_for_history(
            db, memory,
            change_summary=["add winning_patterns"], source_proposal_ids=["p1"], created_by="operator",
        )
        assert len(db._hist_inserted) == 1

    def test_snapshot_preserves_field_data(self):
        memory = _base_memory()
        db = _make_db()
        main._snapshot_memory_for_history(db, memory, change_summary=["test"], source_proposal_ids=[])
        snap = db._hist_inserted[0].get("snapshot", {})
        assert snap.get("winning_patterns") == memory["winning_patterns"]
        assert snap.get("version") == memory["version"]

    def test_get_history_endpoint_returns_list(self, client):
        memory = _base_memory()
        mem_id = str(memory["_id"])
        history_entry = {
            "_id": ObjectId(),
            "client_memory_id": mem_id,
            "workspace_slug": "test-ws",
            "version": 1,
            "snapshot": {},
            "change_summary": ["initial"],
            "source_proposal_ids": [],
            "created_by": "operator",
            "created_at": _utc_now(),
        }
        db = _make_db(memories=[memory], history=[history_entry])
        with _patch(db):
            resp = client.get(f"/client-memory/{mem_id}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1

    def test_get_history_invalid_id_returns_400(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.get("/client-memory/not-an-id/history")
        assert resp.status_code == 400

    def test_get_history_not_found_returns_404(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.get(f"/client-memory/{ObjectId()}/history")
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# TestRollback  (HTTP endpoints)
# ─────────────────────────────────────────────────────────────────────────────

class TestRollback:
    def _setup(self, version: int = 2):
        memory = _base_memory(version=version)
        mem_id = str(memory["_id"])
        old_patterns = ["Old winning pattern from v1"]
        history_entry = {
            "_id": ObjectId(),
            "client_memory_id": mem_id,
            "workspace_slug": "test-ws",
            "version": 1,
            "snapshot": {
                **{k: v for k, v in memory.items() if k != "_id"},
                "version": 1,
                "winning_patterns": old_patterns,
            },
            "change_summary": ["initial"],
            "source_proposal_ids": [],
            "created_by": "operator",
            "created_at": _utc_now(),
        }
        db = _make_db(memories=[memory], history=[history_entry])
        return db, mem_id, memory, old_patterns

    def test_rollback_restores_snapshot(self, client):
        db, mem_id, memory, _, = self._setup()
        with _patch(db):
            resp = client.post(f"/client-memory/{mem_id}/rollback", json={"target_version": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["rolled_back_to_version"] == 1

    def test_rollback_increments_version(self, client):
        db, mem_id, memory, _ = self._setup(version=3)
        with _patch(db):
            resp = client.post(f"/client-memory/{mem_id}/rollback", json={"target_version": 1})
        assert resp.status_code == 200
        assert resp.json()["new_version"] == 4

    def test_rollback_version_not_found_returns_404(self, client):
        db, mem_id, *_ = self._setup()
        with _patch(db):
            resp = client.post(f"/client-memory/{mem_id}/rollback", json={"target_version": 99})
        assert resp.status_code == 404

    def test_rollback_invalid_memory_id(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.post("/client-memory/bad-id/rollback", json={"target_version": 1})
        assert resp.status_code == 400

    def test_rollback_writes_history_snapshot(self, client):
        db, mem_id, *_ = self._setup()
        with _patch(db):
            client.post(f"/client-memory/{mem_id}/rollback", json={"target_version": 1})
        assert len(db._hist_inserted) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# TestHealthEndpoint  (HTTP endpoints)
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_endpoint_returns_score(self, client):
        memory = _base_memory()
        mem_id = str(memory["_id"])
        db = _make_db(memories=[memory])
        with _patch(db):
            resp = client.get(f"/client-memory/{mem_id}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "memory_health_score" in data
        assert data["status"] in ("healthy", "needs_review", "conflicted", "stale", "overgrown", "unknown")

    def test_health_endpoint_invalid_id(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.get("/client-memory/bad-id/health")
        assert resp.status_code == 400

    def test_health_endpoint_not_found(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.get(f"/client-memory/{ObjectId()}/health")
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# TestProposalDiffEndpoint  (HTTP endpoints)
# ─────────────────────────────────────────────────────────────────────────────

class TestProposalDiffEndpoint:
    def _make_setup(self):
        memory = _base_memory()
        proposal = {
            "_id": ObjectId(),
            "workspace_slug": "test-ws",
            "client_memory_id": str(memory["_id"]),
            "status": "pending",
            "proposed_change": {
                "field": "winning_patterns",
                "change_type": "add",
                "new_value": "Webinar series drives signups",
            },
            "confidence": 0.8,
            "conflicts": [],
        }
        return memory, proposal

    def test_diff_endpoint_returns_diff(self, client):
        memory, proposal = self._make_setup()
        prop_id = str(proposal["_id"])
        db = _make_db(memories=[memory], proposals=[proposal])
        with _patch(db):
            resp = client.get(f"/memory-update-proposals/{prop_id}/diff")
        assert resp.status_code == 200
        data = resp.json()
        assert "diff" in data
        assert data["diff"]["field"] == "winning_patterns"

    def test_diff_endpoint_invalid_id(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.get("/memory-update-proposals/bad-id/diff")
        assert resp.status_code == 400

    def test_diff_endpoint_not_found(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.get(f"/memory-update-proposals/{ObjectId()}/diff")
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# TestProposalConflictsEndpoint  (HTTP endpoints)
# ─────────────────────────────────────────────────────────────────────────────

class TestProposalConflictsEndpoint:
    def test_conflicts_endpoint_no_conflicts(self, client):
        memory = _base_memory()
        proposal = {
            "_id": ObjectId(),
            "workspace_slug": "test-ws",
            "client_memory_id": str(memory["_id"]),
            "status": "pending",
            "proposed_change": {
                "field": "winning_patterns",
                "change_type": "add",
                "new_value": "Podcast episode drives traffic",
            },
            "confidence": 0.75,
            "conflicts": [],
        }
        prop_id = str(proposal["_id"])
        db = _make_db(memories=[memory], proposals=[proposal])
        with _patch(db):
            resp = client.get(f"/memory-update-proposals/{prop_id}/conflicts")
        assert resp.status_code == 200
        data = resp.json()
        assert "conflicts" in data
        assert "conflict_count" in data
        assert "duplicate" in data

    def test_conflicts_endpoint_detects_overlap(self, client):
        memory = _base_memory()
        proposal = {
            "_id": ObjectId(),
            "workspace_slug": "test-ws",
            "client_memory_id": str(memory["_id"]),
            "status": "pending",
            "proposed_change": {
                "field": "winning_patterns",
                "change_type": "add",
                "new_value": "Long-form cold emails had low reply rates pipeline",  # high overlap with losing_patterns → high severity
            },
            "confidence": 0.7,
            "conflicts": [],
        }
        prop_id = str(proposal["_id"])
        db = _make_db(memories=[memory], proposals=[proposal])
        with _patch(db):
            resp = client.get(f"/memory-update-proposals/{prop_id}/conflicts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["conflict_count"] >= 1
        assert data["has_high_severity_conflicts"] is True

    def test_conflicts_endpoint_invalid_id(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.get("/memory-update-proposals/bad-id/conflicts")
        assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# TestProposalApprovalWithGovernance  (HTTP endpoints)
# ─────────────────────────────────────────────────────────────────────────────

class TestProposalApprovalWithGovernance:
    def _make_proposal(self, memory, conflicts=None, status="pending"):
        return {
            "_id": ObjectId(),
            "workspace_slug": "test-ws",
            "client_memory_id": str(memory["_id"]),
            "status": status,
            "proposed_change": {
                "field": "winning_patterns",
                "change_type": "add",
                "new_value": "New winning tactic for outreach",
            },
            "confidence": 0.75,
            "conflicts": conflicts or [],
        }

    def test_approve_without_conflicts_succeeds(self, client):
        memory = _base_memory()
        proposal = self._make_proposal(memory)
        prop_id = str(proposal["_id"])
        db = _make_db(memories=[memory], proposals=[proposal])
        with _patch(db):
            resp = client.patch(f"/memory-update-proposals/{prop_id}", json={"status": "approved"})
        assert resp.status_code == 200
        assert resp.json()["applied_to_memory"] is True

    def test_approve_with_high_conflict_blocked(self, client):
        memory = _base_memory()
        proposal = self._make_proposal(memory, conflicts=[{
            "conflict_type": "winning_losing_overlap",
            "severity": "high",
            "description": "overlaps with losing pattern",
        }])
        prop_id = str(proposal["_id"])
        db = _make_db(memories=[memory], proposals=[proposal])
        with _patch(db):
            resp = client.patch(f"/memory-update-proposals/{prop_id}", json={"status": "approved"})
        assert resp.status_code == 409

    def test_approve_with_high_conflict_override_succeeds(self, client):
        memory = _base_memory()
        proposal = self._make_proposal(memory, conflicts=[{
            "conflict_type": "winning_losing_overlap",
            "severity": "high",
            "description": "overlaps with losing pattern",
        }])
        prop_id = str(proposal["_id"])
        db = _make_db(memories=[memory], proposals=[proposal])
        with _patch(db):
            resp = client.patch(f"/memory-update-proposals/{prop_id}", json={"status": "approved", "override_conflicts": True})
        assert resp.status_code == 200

    def test_approve_medium_conflict_not_blocked(self, client):
        memory = _base_memory()
        proposal = self._make_proposal(memory, conflicts=[{
            "conflict_type": "winning_losing_overlap",
            "severity": "medium",
            "description": "mild overlap",
        }])
        prop_id = str(proposal["_id"])
        db = _make_db(memories=[memory], proposals=[proposal])
        with _patch(db):
            resp = client.patch(f"/memory-update-proposals/{prop_id}", json={"status": "approved"})
        assert resp.status_code == 200

    def test_approve_writes_version_history(self, client):
        memory = _base_memory()
        proposal = self._make_proposal(memory)
        prop_id = str(proposal["_id"])
        db = _make_db(memories=[memory], proposals=[proposal])
        with _patch(db):
            client.patch(f"/memory-update-proposals/{prop_id}", json={"status": "approved"})
        assert len(db._hist_inserted) >= 1

    def test_reject_does_not_write_history(self, client):
        memory = _base_memory()
        proposal = self._make_proposal(memory)
        prop_id = str(proposal["_id"])
        db = _make_db(memories=[memory], proposals=[proposal])
        with _patch(db):
            client.patch(f"/memory-update-proposals/{prop_id}", json={"status": "rejected"})
        assert len(db._hist_inserted) == 0


# ─────────────────────────────────────────────────────────────────────────────
# TestCreateProposalGovernance  (HTTP endpoints)
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateProposalGovernance:
    def test_create_proposal_includes_conflicts_field(self, client):
        memory = _base_memory()
        db = _make_db(memories=[memory])
        with _patch(db):
            resp = client.post("/memory-update-proposals", json={
                "workspace_slug": "test-ws",
                "proposed_change": {
                    "field": "winning_patterns",
                    "change_type": "add",
                    "new_value": "Podcast driving signups organically",
                },
                "confidence": 0.7,
            })
        assert resp.status_code == 200
        item = resp.json()["item"]
        assert "conflicts" in item
        assert "governance_suggestion" in item

    def test_create_proposal_governance_suggestion_review(self, client):
        memory = _base_memory()
        db = _make_db(memories=[memory])
        with _patch(db):
            resp = client.post("/memory-update-proposals", json={
                "workspace_slug": "test-ws",
                "proposed_change": {"field": "winning_patterns", "change_type": "add", "new_value": "new tactic works"},
                "confidence": 0.7,
            })
        item = resp.json()["item"]
        assert item["governance_suggestion"] == "review"

    def test_create_proposal_low_confidence_suggests_reject(self, client):
        memory = _base_memory()
        db = _make_db(memories=[memory])
        with _patch(db):
            resp = client.post("/memory-update-proposals", json={
                "workspace_slug": "test-ws",
                "proposed_change": {"field": "winning_patterns", "change_type": "add", "new_value": "uncertain claim"},
                "confidence": 0.20,
            })
        item = resp.json()["item"]
        assert item["governance_suggestion"] == "auto_reject"

    def test_create_proposal_high_confidence_no_conflicts_suggests_approve(self, client):
        memory = _base_memory()
        db = _make_db(memories=[memory])
        with _patch(db):
            resp = client.post("/memory-update-proposals", json={
                "workspace_slug": "test-ws",
                "proposed_change": {
                    "field": "performance_notes",
                    "change_type": "add",
                    "new_value": "Q4 outreach outperformed benchmark significantly",
                },
                "confidence": 0.95,
            })
        item = resp.json()["item"]
        assert item["governance_suggestion"] == "auto_approve"
