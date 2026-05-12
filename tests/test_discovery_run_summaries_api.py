"""Phase 6F: Tests for /discovery-run-summaries CRUD endpoints
and auto-generation via /discovery-insights/generate.
"""
from __future__ import annotations

import sys
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

import main

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_db(run_summaries=None, insights=None, client_sources=None):
    """Build a minimal mock db with discovery_run_summaries, discovery_insights, client_sources."""
    db = MagicMock()

    # discovery_run_summaries
    _summaries: list[dict] = list(run_summaries or [])

    def rs_find_one(q):
        for s in _summaries:
            if all(s.get(k) == v for k, v in q.items()):
                return dict(s)
        return None

    def rs_insert_one(doc):
        from bson import ObjectId
        doc["_id"] = ObjectId()
        _summaries.append(doc)
        r = MagicMock()
        r.inserted_id = doc["_id"]
        return r

    def rs_update_one(q, update):
        for s in _summaries:
            if all(s.get(k) == v for k, v in q.items()):
                s.update(update.get("$set", {}))
        return MagicMock()

    def rs_find(q):
        results = [s for s in _summaries if all(s.get(k) == v for k, v in q.items())]
        m = MagicMock()
        m.sort.return_value = m
        m.limit.return_value = iter(results)
        return m

    db.discovery_run_summaries.find_one = rs_find_one
    db.discovery_run_summaries.insert_one = rs_insert_one
    db.discovery_run_summaries.update_one = rs_update_one
    db.discovery_run_summaries.find = rs_find

    # discovery_insights (for generate route)
    _ins: list[dict] = list(insights or [])

    def ins_insert_one(doc):
        from bson import ObjectId
        doc["_id"] = ObjectId()
        _ins.append(doc)
        r = MagicMock()
        r.inserted_id = doc["_id"]
        return r

    def ins_find(q):
        m = MagicMock()
        m.sort.return_value = m
        m.limit.return_value = iter([])
        return m

    db.discovery_insights.insert_one = ins_insert_one
    db.discovery_insights.find = ins_find

    # client_sources
    _sources: list[dict] = list(client_sources or [])

    def src_find(q):
        results = [s for s in _sources if all(s.get(k) == v for k, v in q.items())]
        m = MagicMock()
        m.sort.return_value = m
        m.limit.return_value = iter(results)
        return m

    db.client_sources.find = src_find
    return db


def _patch_db(db):
    mock_client = MagicMock()
    mock_client.__enter__ = lambda s: s
    mock_client.__exit__ = MagicMock(return_value=False)

    def fake_get_client():
        return mock_client

    def fake_get_db(client):
        return db

    return (
        patch.object(main, "get_client", side_effect=fake_get_client),
        patch.object(main, "get_database", side_effect=fake_get_db),
    )


# ── Create ────────────────────────────────────────────────────────────────────

def test_create_run_summary_success():
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        now = _utc_now().isoformat()
        r = client.post("/discovery-run-summaries", json={
            "workspace_slug": "ws-1",
            "run_id": "run-abc-001",
            "agent_name": "content_discovery",
            "started_at": now,
            "completed_at": now,
            "sources_checked": 3,
            "insights_generated": 4,
            "high_confidence_insights": 2,
            "configured_sources_used": ["My LinkedIn", "My Website"],
            "platforms_checked": ["LinkedIn", "YouTube"],
            "completion_state": "completed",
            "summary": "Generated 4 insights.",
            "next_recommended_action": "Review insights.",
        })
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["workspace_slug"] == "ws-1"
    assert item["run_id"] == "run-abc-001"
    assert item["sources_checked"] == 3
    assert item["insights_generated"] == 4
    assert item["high_confidence_insights"] == 2
    assert item["completion_state"] == "completed"
    assert item["summary"] == "Generated 4 insights."


def test_create_run_summary_missing_workspace():
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.post("/discovery-run-summaries", json={
            "workspace_slug": "",
            "run_id": "run-x",
            "started_at": _utc_now().isoformat(),
        })
    assert r.status_code == 400


def test_create_run_summary_missing_run_id():
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.post("/discovery-run-summaries", json={
            "workspace_slug": "ws-1",
            "run_id": "",
            "started_at": _utc_now().isoformat(),
        })
    assert r.status_code == 400


def test_create_run_summary_duplicate_run_id():
    now = _utc_now()
    existing = {
        "_id": "existing-id",
        "workspace_slug": "ws-1",
        "run_id": "run-dup",
        "completion_state": "completed",
        "started_at": now,
    }
    db = _make_db(run_summaries=[existing])
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.post("/discovery-run-summaries", json={
            "workspace_slug": "ws-1",
            "run_id": "run-dup",
            "started_at": now.isoformat(),
        })
    assert r.status_code == 409


def test_create_run_summary_defaults():
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.post("/discovery-run-summaries", json={
            "workspace_slug": "ws-2",
            "run_id": "run-defaults",
            "started_at": _utc_now().isoformat(),
        })
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["completion_state"] == "running"
    assert item["sources_checked"] == 0
    assert item["insights_generated"] == 0
    assert item["configured_sources_used"] == []
    assert item["platforms_checked"] == []


# ── List ──────────────────────────────────────────────────────────────────────

def _seed_summaries():
    now = _utc_now()
    return [
        {
            "_id": "id-1", "workspace_slug": "ws-a", "run_id": "run-1",
            "completion_state": "completed", "started_at": now, "completed_at": now,
            "insights_generated": 3, "sources_checked": 2,
        },
        {
            "_id": "id-2", "workspace_slug": "ws-a", "run_id": "run-2",
            "completion_state": "partial", "started_at": now, "completed_at": None,
            "insights_generated": 0, "sources_checked": 1,
        },
        {
            "_id": "id-3", "workspace_slug": "ws-b", "run_id": "run-3",
            "completion_state": "failed", "started_at": now, "completed_at": None,
            "insights_generated": 0, "sources_checked": 0,
        },
    ]


def test_list_all_summaries():
    db = _make_db(run_summaries=_seed_summaries())
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.get("/discovery-run-summaries")
    assert r.status_code == 200
    assert r.json()["count"] == 3


def test_list_filter_by_workspace():
    db = _make_db(run_summaries=_seed_summaries())
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.get("/discovery-run-summaries?workspace_slug=ws-a")
    assert r.status_code == 200
    assert r.json()["count"] == 2


def test_list_filter_by_completion_state():
    db = _make_db(run_summaries=_seed_summaries())
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.get("/discovery-run-summaries?completion_state=failed")
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_list_filter_by_run_id():
    db = _make_db(run_summaries=_seed_summaries())
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.get("/discovery-run-summaries?run_id=run-2")
    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert r.json()["items"][0]["run_id"] == "run-2"


# ── Get ───────────────────────────────────────────────────────────────────────

def test_get_run_summary_by_run_id():
    db = _make_db(run_summaries=_seed_summaries())
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.get("/discovery-run-summaries/run-1")
    assert r.status_code == 200
    assert r.json()["item"]["run_id"] == "run-1"
    assert r.json()["item"]["completion_state"] == "completed"


def test_get_run_summary_404():
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.get("/discovery-run-summaries/nonexistent-run")
    assert r.status_code == 404


# ── Patch ─────────────────────────────────────────────────────────────────────

def test_patch_run_summary_completion_state():
    db = _make_db(run_summaries=_seed_summaries())
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.patch("/discovery-run-summaries/run-2", json={
            "completion_state": "completed",
            "insights_generated": 2,
            "summary": "Updated summary.",
        })
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["completion_state"] == "completed"
    assert item["insights_generated"] == 2
    assert item["summary"] == "Updated summary."


def test_patch_run_summary_404():
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.patch("/discovery-run-summaries/no-such-run", json={"completion_state": "completed"})
    assert r.status_code == 404


def test_patch_platforms_checked():
    db = _make_db(run_summaries=_seed_summaries())
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.patch("/discovery-run-summaries/run-1", json={
            "platforms_checked": ["LinkedIn", "YouTube", "Podcasts"],
        })
    assert r.status_code == 200
    assert r.json()["item"]["platforms_checked"] == ["LinkedIn", "YouTube", "Podcasts"]


# ── Completion States ─────────────────────────────────────────────────────────

def test_completion_state_running():
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.post("/discovery-run-summaries", json={
            "workspace_slug": "ws-1",
            "run_id": "run-running",
            "started_at": _utc_now().isoformat(),
            "completion_state": "running",
        })
    assert r.status_code == 200
    assert r.json()["item"]["completion_state"] == "running"


def test_completion_state_partial():
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.post("/discovery-run-summaries", json={
            "workspace_slug": "ws-1",
            "run_id": "run-partial",
            "started_at": _utc_now().isoformat(),
            "completion_state": "partial",
            "next_recommended_action": "Add more client sources or rerun discovery later.",
        })
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["completion_state"] == "partial"
    assert "more client sources" in item["next_recommended_action"]


def test_completion_state_failed():
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.post("/discovery-run-summaries", json={
            "workspace_slug": "ws-1",
            "run_id": "run-failed",
            "started_at": _utc_now().isoformat(),
            "completion_state": "failed",
        })
    assert r.status_code == 200
    assert r.json()["item"]["completion_state"] == "failed"


# ── Auto-generation via /discovery-insights/generate ──────────────────────────

def test_generate_insights_creates_run_summary():
    """Triggering discovery insight generation auto-creates a run summary."""
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.post("/discovery-insights/generate", json={
            "workspace_slug": "ws-gen",
            "module": "contractor_growth",
        })
    assert r.status_code == 200
    data = r.json()
    assert "run_summary" in data
    assert data["run_summary"]["completion_state"] in ("completed", "partial")
    assert data["run_summary"]["run_id"]
    assert data["run_summary"]["summary"]


def test_generate_insights_run_summary_completion_state_partial_when_no_insights():
    """When discovery engine produces 0 insights, completion_state should be partial."""
    db = _make_db()
    p1, p2 = _patch_db(db)

    # Patch generate_discovery_insights to return empty list
    with p1, p2:
        with patch("main.trigger_discovery_insight_generation.__wrapped__", create=True):
            pass
        # We need to patch the import inside the function
        import discovery_engine as de
        original_fn = de.generate_discovery_insights

        def _empty_gen(**kwargs):
            return []

        de.generate_discovery_insights = _empty_gen
        try:
            client = TestClient(main.app)
            r = client.post("/discovery-insights/generate", json={
                "workspace_slug": "ws-empty",
                "module": "contractor_growth",
            })
        finally:
            de.generate_discovery_insights = original_fn

    assert r.status_code == 200
    assert r.json()["run_summary"]["completion_state"] == "partial"


def test_generate_insights_response_includes_count():
    """Response from generate always includes count and items."""
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        r = client.post("/discovery-insights/generate", json={
            "workspace_slug": "ws-count",
            "module": "contractor_growth",
            "max_insights": 2,
        })
    assert r.status_code == 200
    data = r.json()
    assert "count" in data
    assert "items" in data
    assert isinstance(data["items"], list)
