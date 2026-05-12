"""Phase 6H: Tests for /workflow-runs CRUD endpoints."""
from __future__ import annotations

import sys
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

import main

# ── Helpers ───────────────────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_db(workflow_runs=None):
    """Build a minimal mock db with a workflow_runs collection."""
    from bson import ObjectId
    db = MagicMock()

    _runs: list[dict] = []
    for r in (workflow_runs or []):
        entry = dict(r)
        if "_id" not in entry:
            entry["_id"] = ObjectId()
        _runs.append(entry)

    def wf_insert_one(doc):
        doc["_id"] = ObjectId()
        _runs.append(doc)
        r = MagicMock()
        r.inserted_id = doc["_id"]
        return r

    def wf_find_one(q):
        from bson import ObjectId as OID
        for run in _runs:
            match = True
            for k, v in q.items():
                rv = run.get(k)
                # Allow ObjectId / string comparison
                if str(rv) != str(v) and rv != v:
                    match = False
                    break
            if match:
                return dict(run)
        return None

    def wf_find(q=None, *args, **kwargs):
        q = q or {}
        results = []
        for run in _runs:
            if all(run.get(k) == v for k, v in q.items()):
                results.append(dict(run))
        m = MagicMock()
        m.sort.return_value = m
        m.limit.return_value = iter(results)
        return m

    def wf_update_one(q, update):
        for run in _runs:
            if all(run.get(k) == v for k, v in q.items()):
                run.update(update.get("$set", {}))
        return MagicMock()

    db.workflow_runs.insert_one = wf_insert_one
    db.workflow_runs.find_one = wf_find_one
    db.workflow_runs.find = wf_find
    db.workflow_runs.update_one = wf_update_one

    # Stub other collections to avoid AttributeError
    for col in ["agent_tasks", "agent_runs", "discovery_run_summaries", "discovery_insights",
                "approval_requests", "workflow_assets", "client_sources"]:
        m = MagicMock()
        m.find.return_value = MagicMock()
        m.find.return_value.sort.return_value = m.find.return_value
        m.find.return_value.limit.return_value = iter([])
        setattr(db, col, m)

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


# ── POST /workflow-runs ───────────────────────────────────────────────────────

def test_create_workflow_run_success():
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.post("/workflow-runs", json={
            "workspace_slug": "ws-test",
            "run_type": "discovery",
            "workflow_stage": 2,
            "status": "completed",
            "title": "Content Discovery Run",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["item"]["workspace_slug"] == "ws-test"
    assert data["item"]["run_type"] == "discovery"
    assert data["item"]["status"] == "completed"
    assert "_id" in data["item"]


def test_create_workflow_run_with_outputs():
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.post("/workflow-runs", json={
            "workspace_slug": "ws-test",
            "run_type": "content_build",
            "workflow_stage": 2,
            "status": "needs_review",
            "title": "Content Build Run",
            "outputs": {
                "assets_generated": 3,
                "approval_requests_created": 3,
                "recommended_next_step": "review",
            },
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["item"]["outputs"]["assets_generated"] == 3
    assert data["item"]["outputs"]["approval_requests_created"] == 3


def test_create_workflow_run_invalid_run_type():
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.post("/workflow-runs", json={
            "workspace_slug": "ws-test",
            "run_type": "invalid_type",
            "workflow_stage": 2,
            "status": "completed",
        })
    assert resp.status_code == 422


def test_create_workflow_run_invalid_status():
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.post("/workflow-runs", json={
            "workspace_slug": "ws-test",
            "run_type": "discovery",
            "workflow_stage": 2,
            "status": "not_a_status",
        })
    assert resp.status_code == 422


# ── GET /workflow-runs ────────────────────────────────────────────────────────

def test_list_workflow_runs_empty():
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.get("/workflow-runs")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["count"] == 0


def test_list_workflow_runs_returns_items():
    from bson import ObjectId
    run_id = ObjectId()
    db = _make_db(workflow_runs=[{
        "_id": run_id,
        "workspace_slug": "ws-a",
        "run_type": "discovery",
        "workflow_stage": 2,
        "status": "completed",
        "title": "Test Discovery",
        "created_at": _utc_now(),
    }])
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.get("/workflow-runs?workspace_slug=ws-a")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["items"][0]["run_type"] == "discovery"
    assert data["items"][0]["workspace_slug"] == "ws-a"


def test_list_workflow_runs_filter_by_run_type():
    from bson import ObjectId
    db = _make_db(workflow_runs=[
        {"_id": ObjectId(), "workspace_slug": "ws-b", "run_type": "discovery",
         "workflow_stage": 2, "status": "completed", "created_at": _utc_now()},
        {"_id": ObjectId(), "workspace_slug": "ws-b", "run_type": "content_build",
         "workflow_stage": 2, "status": "needs_review", "created_at": _utc_now()},
    ])
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.get("/workflow-runs?workspace_slug=ws-b&run_type=content_build")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(i["run_type"] == "content_build" for i in items)


def test_list_workflow_runs_filter_by_status():
    from bson import ObjectId
    db = _make_db(workflow_runs=[
        {"_id": ObjectId(), "workspace_slug": "ws-c", "run_type": "discovery",
         "workflow_stage": 2, "status": "completed", "created_at": _utc_now()},
        {"_id": ObjectId(), "workspace_slug": "ws-c", "run_type": "content_build",
         "workflow_stage": 2, "status": "running", "created_at": _utc_now()},
    ])
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.get("/workflow-runs?workspace_slug=ws-c&status=running")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(i["status"] == "running" for i in items)


# ── GET /workflow-runs/{run_id} ───────────────────────────────────────────────

def test_get_workflow_run_by_id():
    from bson import ObjectId
    run_id = ObjectId()
    db = _make_db(workflow_runs=[{
        "_id": run_id,
        "workspace_slug": "ws-get",
        "run_type": "discovery",
        "workflow_stage": 2,
        "status": "completed",
        "title": "Get Test",
        "created_at": _utc_now(),
    }])
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.get(f"/workflow-runs/{run_id}")
    assert resp.status_code == 200
    assert resp.json()["item"]["title"] == "Get Test"
    assert resp.json()["item"]["_id"] == str(run_id)


def test_get_workflow_run_not_found():
    from bson import ObjectId
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.get(f"/workflow-runs/{ObjectId()}")
    assert resp.status_code == 404


def test_get_workflow_run_invalid_id():
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.get("/workflow-runs/not-a-valid-id")
    # Invalid ObjectId: endpoint may return 400, 404, or 422
    assert resp.status_code in (400, 404, 422)


# ── PATCH /workflow-runs/{run_id} ─────────────────────────────────────────────

def test_patch_workflow_run_status():
    from bson import ObjectId
    run_id = ObjectId()
    db = _make_db(workflow_runs=[{
        "_id": run_id,
        "workspace_slug": "ws-patch",
        "run_type": "content_build",
        "workflow_stage": 2,
        "status": "running",
        "created_at": _utc_now(),
    }])
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.patch(f"/workflow-runs/{run_id}", json={"status": "needs_review"})
    assert resp.status_code == 200
    assert resp.json()["item"]["status"] == "needs_review"


def test_patch_workflow_run_outputs():
    from bson import ObjectId
    run_id = ObjectId()
    db = _make_db(workflow_runs=[{
        "_id": run_id,
        "workspace_slug": "ws-patch2",
        "run_type": "discovery",
        "workflow_stage": 2,
        "status": "running",
        "created_at": _utc_now(),
    }])
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.patch(f"/workflow-runs/{run_id}", json={
            "status": "completed",
            "outputs": {"insights_generated": 5, "high_confidence_count": 3},
            "summary": "Found 5 insights",
        })
    assert resp.status_code == 200
    item = resp.json()["item"]
    assert item["status"] == "completed"
    assert item["outputs"]["insights_generated"] == 5
    assert item["summary"] == "Found 5 insights"


def test_patch_workflow_run_not_found():
    from bson import ObjectId
    db = _make_db()
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.patch(f"/workflow-runs/{ObjectId()}", json={"status": "completed"})
    assert resp.status_code == 404
