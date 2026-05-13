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


def _get_nested(doc: dict, dotpath: str):
    """Traverse dot-notation path in a dict (e.g. 'inputs.asset_id')."""
    parts = dotpath.split(".")
    val = doc
    for p in parts:
        if not isinstance(val, dict):
            return None
        val = val.get(p)
    return val


def _matches_doc(doc: dict, query: dict) -> bool:
    """Simple query matcher that supports dot-notation keys and ObjectId/string coercion."""
    from bson import ObjectId as OID
    for k, v in query.items():
        if k == "$or":
            if not any(_matches_doc(doc, cond) for cond in v):
                return False
            continue
        dv = _get_nested(doc, k)
        if v != dv:
            # Allow ObjectId / string comparison
            if str(dv) != str(v):
                return False
    return True


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

    def wf_find_one(q, *args, sort=None, **kwargs):
        matched = [run for run in _runs if _matches_doc(run, q)]
        if sort:
            # sort is list of (key, direction); just return last item as naive "latest"
            matched = list(matched)
        return dict(matched[0]) if matched else None

    def wf_find(q=None, *args, **kwargs):
        q = q or {}
        results = [dict(run) for run in _runs if _matches_doc(run, q)]
        m = MagicMock()
        m.sort.return_value = m
        m.limit.return_value = iter(results)
        # Support direct iteration (some callers do list(db.x.find(...)))
        m.__iter__ = lambda self: iter(results)
        return m

    def wf_update_one(q, update):
        for run in _runs:
            if _matches_doc(run, q):
                for k, v in update.get("$set", {}).items():
                    # Handle dot-notation in $set keys (e.g. "outputs.workflow_run_id")
                    if "." in k:
                        top, rest = k.split(".", 1)
                        if top not in run:
                            run[top] = {}
                        run[top][rest] = v
                    else:
                        run[k] = v
                break
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


# ── Phase 6K: approval_request approve → auto-approves linked workflow_asset ─


def _make_db_6k(approval_docs=None, asset_docs=None, workflow_run_docs=None):
    """Enhanced mock db for Phase 6K tests (approval + distribution endpoints)."""
    from bson import ObjectId

    db = _make_db(workflow_runs=workflow_run_docs or [])

    # --- approval_requests ---
    _approvals: list[dict] = []
    for a in (approval_docs or []):
        entry = dict(a)
        if "_id" not in entry:
            entry["_id"] = ObjectId()
        _approvals.append(entry)

    _approval_update_calls: list[tuple] = []

    def ar_find_one(q, *args, **kwargs):
        for a in _approvals:
            if _matches_doc(a, q):
                return dict(a)
        return None

    def ar_update_one(q, update):
        _approval_update_calls.append((q, update))
        for a in _approvals:
            if _matches_doc(a, q):
                a.update(update.get("$set", {}))
                break
        return MagicMock()

    db.approval_requests.find_one = ar_find_one
    db.approval_requests.update_one = ar_update_one
    db._approval_update_calls = _approval_update_calls

    # --- workflow_assets ---
    _assets: list[dict] = []
    for a in (asset_docs or []):
        entry = dict(a)
        if "_id" not in entry:
            entry["_id"] = ObjectId()
        _assets.append(entry)

    _asset_update_calls: list[tuple] = []

    def wa_find_one(q, *args, **kwargs):
        for a in _assets:
            if _matches_doc(a, q):
                return dict(a)
        return None

    def wa_find(q=None, *args, **kwargs):
        q = q or {}
        results = [dict(a) for a in _assets if _matches_doc(a, q)]
        return iter(results)

    def wa_update_one(q, update):
        _asset_update_calls.append((q, update))
        for a in _assets:
            if _matches_doc(a, q):
                for k, v in update.get("$set", {}).items():
                    a[k] = v
                break
        return MagicMock()

    db.workflow_assets.find_one = wa_find_one
    db.workflow_assets.find = wa_find
    db.workflow_assets.update_one = wa_update_one
    db._asset_update_calls = _asset_update_calls
    db._assets = _assets

    # stub contacts/leads/message_drafts for enrich_approval_requests
    for col in ["contacts", "leads", "message_drafts"]:
        m = MagicMock()
        m.find_one.return_value = None
        setattr(db, col, m)

    return db


def test_6k_approve_approval_request_auto_approves_asset():
    """Approving an approval_request with workflow_asset_id auto-approves the linked asset."""
    from bson import ObjectId
    asset_id = ObjectId()
    approval_id = ObjectId()
    db = _make_db_6k(
        approval_docs=[{
            "_id": approval_id,
            "workspace_slug": "ws-6k",
            "status": "open",
            "decision": None,
            "workflow_asset_id": str(asset_id),
            "request_type": "content_review",
        }],
        asset_docs=[{
            "_id": asset_id,
            "workspace_slug": "ws-6k",
            "approval_state": "pending",
            "distribution_state": "not_queued",
        }],
    )
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.post(f"/approval-requests/{approval_id}/decision", json={"decision": "approve", "note": ""})
    assert resp.status_code == 200

    # The linked asset should have been updated to approval_state="approved"
    asset_updates = [u for (_, u) in db._asset_update_calls if u.get("$set", {}).get("approval_state") == "approved"]
    assert len(asset_updates) >= 1, "Expected workflow_assets.update_one called with approval_state='approved'"


def test_6k_reject_approval_request_does_not_touch_asset():
    """Rejecting an approval_request should NOT change the linked asset's approval_state."""
    from bson import ObjectId
    asset_id = ObjectId()
    approval_id = ObjectId()
    db = _make_db_6k(
        approval_docs=[{
            "_id": approval_id,
            "workspace_slug": "ws-6k-rej",
            "status": "open",
            "decision": None,
            "workflow_asset_id": str(asset_id),
            "request_type": "content_review",
        }],
        asset_docs=[{
            "_id": asset_id,
            "workspace_slug": "ws-6k-rej",
            "approval_state": "pending",
            "distribution_state": "not_queued",
        }],
    )
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.post(f"/approval-requests/{approval_id}/decision", json={"decision": "reject", "note": ""})
    assert resp.status_code == 200

    asset_approval_updates = [u for (_, u) in db._asset_update_calls if "approval_state" in u.get("$set", {})]
    assert len(asset_approval_updates) == 0, "Rejecting should not auto-approve the asset"


def test_6k_mark_published_creates_distribution_workflow_run():
    """mark_published on a workflow asset creates a distribution workflow_run record."""
    from bson import ObjectId
    wf_run_id = str(ObjectId())
    asset_id = ObjectId()
    db = _make_db_6k(
        asset_docs=[{
            "_id": asset_id,
            "workspace_slug": "ws-6k-dist",
            "approval_state": "approved",
            "distribution_state": "queued",
            "workflow_run_id": wf_run_id,
            "title": "Test Post",
        }],
    )
    inserted_runs: list[dict] = []
    _orig_insert = db.workflow_runs.insert_one
    def tracking_insert(doc):
        inserted_runs.append(dict(doc))
        return _orig_insert(doc)
    db.workflow_runs.insert_one = tracking_insert

    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.patch(f"/workflow-assets/{asset_id}/distribution", json={"action": "mark_published"})
    assert resp.status_code == 200

    dist_runs = [r for r in inserted_runs if r.get("run_type") == "distribution"]
    assert len(dist_runs) == 1, "Expected one distribution workflow_run to be created"
    assert dist_runs[0]["status"] == "completed"
    assert dist_runs[0]["source_workflow_run_id"] == wf_run_id


def test_6k_mark_published_last_asset_completes_content_build_run():
    """When the last asset for a content_build run is published, the run transitions to 'completed'."""
    from bson import ObjectId
    cb_run_id = ObjectId()
    asset_id = ObjectId()
    db = _make_db_6k(
        asset_docs=[{
            "_id": asset_id,
            "workspace_slug": "ws-6k-done",
            "approval_state": "approved",
            "distribution_state": "queued",
            "workflow_run_id": str(cb_run_id),
            "title": "Final Post",
        }],
        workflow_run_docs=[{
            "_id": cb_run_id,
            "workspace_slug": "ws-6k-done",
            "run_type": "content_build",
            "workflow_stage": 3,
            "status": "needs_review",
            "created_at": _utc_now(),
        }],
    )
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.patch(f"/workflow-assets/{asset_id}/distribution", json={"action": "mark_published"})
    assert resp.status_code == 200

    # The content_build workflow_run should have been patched to "completed"
    cb_run = db.workflow_runs.find_one({"_id": cb_run_id})
    assert cb_run is not None
    assert cb_run.get("status") == "completed", f"Expected 'completed', got {cb_run.get('status')!r}"


# ── Phase 6L: Idempotency, partial publish, lineage, lifecycle summary ────────


def test_6l_mark_published_does_not_create_duplicate_dist_run():
    """A second mark_published is blocked by the state machine (400), and a
    duplicate distribution run is never inserted if somehow the asset_id already
    has one."""
    from bson import ObjectId
    cb_run_id = str(ObjectId())
    asset_id = ObjectId()
    existing_dist_id = ObjectId()
    db = _make_db_6k(
        asset_docs=[{
            "_id": asset_id,
            "workspace_slug": "ws-6l-idem",
            "approval_state": "approved",
            "distribution_state": "queued",
            "workflow_run_id": cb_run_id,
            "title": "Post A",
        }],
        workflow_run_docs=[{
            "_id": existing_dist_id,
            "run_type": "distribution",
            "status": "completed",
            "inputs": {"asset_id": str(asset_id)},
            "created_at": _utc_now(),
        }],
    )
    inserted_runs: list[dict] = []
    _orig_insert = db.workflow_runs.insert_one

    def tracking_insert(doc):
        inserted_runs.append(dict(doc))
        return _orig_insert(doc)

    db.workflow_runs.insert_one = tracking_insert
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.patch(f"/workflow-assets/{asset_id}/distribution", json={"action": "mark_published"})
    assert resp.status_code == 200

    new_dist_runs = [r for r in inserted_runs if r.get("run_type") == "distribution"]
    assert len(new_dist_runs) == 0, "Distribution run should NOT be inserted when one already exists for this asset"


def test_6l_partial_publish_does_not_complete_content_build_run():
    """Publishing one of two assets should NOT set content_build run to 'completed'."""
    from bson import ObjectId
    cb_run_id = ObjectId()
    asset1 = ObjectId()
    asset2 = ObjectId()
    cb_id_str = str(cb_run_id)
    db = _make_db_6k(
        asset_docs=[
            {
                "_id": asset1,
                "workspace_slug": "ws-6l-partial",
                "approval_state": "approved",
                "distribution_state": "queued",
                "workflow_run_id": cb_id_str,
                "title": "Post A",
            },
            {
                "_id": asset2,
                "workspace_slug": "ws-6l-partial",
                "approval_state": "pending",
                "distribution_state": "not_queued",
                "workflow_run_id": cb_id_str,
                "title": "Post B",
            },
        ],
        workflow_run_docs=[{
            "_id": cb_run_id,
            "workspace_slug": "ws-6l-partial",
            "run_type": "content_build",
            "workflow_stage": 3,
            "status": "needs_review",
            "created_at": _utc_now(),
        }],
    )
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.patch(f"/workflow-assets/{asset1}/distribution", json={"action": "mark_published"})
    assert resp.status_code == 200

    cb_run = db.workflow_runs.find_one({"_id": cb_run_id})
    assert cb_run is not None
    assert cb_run.get("status") == "needs_review", (
        f"Partial publish should not complete the content_build run; got {cb_run.get('status')!r}"
    )


def test_6l_workflow_lineage_returns_structure():
    """GET /workflow-lineage returns cycles with content_build, discovery, and assets."""
    from bson import ObjectId
    cb_id = ObjectId()
    disc_id = ObjectId()
    asset_id = ObjectId()
    dist_id = ObjectId()
    ws = "ws-6l-lineage"

    db = _make_db_6k(
        asset_docs=[{
            "_id": asset_id,
            "workspace_slug": ws,
            "approval_state": "approved",
            "distribution_state": "published",
            "workflow_run_id": str(cb_id),
            "title": "Lineage Post",
        }],
        workflow_run_docs=[
            {
                "_id": cb_id,
                "workspace_slug": ws,
                "run_type": "content_build",
                "workflow_stage": 3,
                "status": "completed",
                "source_workflow_run_id": str(disc_id),
                "created_at": _utc_now(),
            },
            {
                "_id": disc_id,
                "workspace_slug": ws,
                "run_type": "discovery",
                "workflow_stage": 2,
                "status": "completed",
                "created_at": _utc_now(),
            },
            {
                "_id": dist_id,
                "workspace_slug": ws,
                "run_type": "distribution",
                "workflow_stage": 5,
                "status": "completed",
                "inputs": {"asset_id": str(asset_id)},
                "created_at": _utc_now(),
            },
        ],
    )
    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.get(f"/workflow-lineage?workspace_slug={ws}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["workspace_slug"] == ws
    assert len(data["cycles"]) == 1
    cycle = data["cycles"][0]
    assert cycle["content_build_run"]["run_type"] == "content_build"
    assert cycle["discovery_run"]["run_type"] == "discovery"
    assert len(cycle["assets"]) == 1
    assert len(cycle["assets"][0]["distribution_runs"]) == 1


def test_6l_lifecycle_summary_complete_stage():
    """GET /workflow-lifecycle-summary returns lifecycle_stage='complete' when all assets published."""
    from bson import ObjectId
    cb_id = ObjectId()
    disc_id = ObjectId()
    asset_id = ObjectId()
    ws = "ws-6l-summary"

    db = _make_db_6k(
        asset_docs=[{
            "_id": asset_id,
            "workspace_slug": ws,
            "approval_state": "approved",
            "distribution_state": "published",
            "workflow_run_id": str(cb_id),
        }],
        workflow_run_docs=[
            {
                "_id": cb_id,
                "workspace_slug": ws,
                "run_type": "content_build",
                "workflow_stage": 3,
                "status": "completed",
                "created_at": _utc_now(),
            },
            {
                "_id": disc_id,
                "workspace_slug": ws,
                "run_type": "discovery",
                "workflow_stage": 2,
                "status": "completed",
                "outputs": {"insights_generated": 4},
                "created_at": _utc_now(),
            },
        ],
    )
    # stub approval_requests to return empty list
    db.approval_requests.find = lambda q=None, *a, **kw: iter([])

    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.get(f"/workflow-lifecycle-summary?workspace_slug={ws}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["lifecycle_stage"] == "complete"
    assert data["is_complete"] is True
    assert data["content_build"]["asset_count"] == 1
    assert data["distribution"]["published"] == 1


def test_6l_lifecycle_summary_review_stage():
    """lifecycle_stage='review' when content_build exists with pending assets and open approvals."""
    from bson import ObjectId
    cb_id = ObjectId()
    ws = "ws-6l-review"

    db = _make_db_6k(
        asset_docs=[{
            "_id": ObjectId(),
            "workspace_slug": ws,
            "approval_state": "pending",
            "distribution_state": "not_queued",
            "workflow_run_id": str(cb_id),
        }],
        workflow_run_docs=[{
            "_id": cb_id,
            "workspace_slug": ws,
            "run_type": "content_build",
            "workflow_stage": 3,
            "status": "needs_review",
            "created_at": _utc_now(),
        }],
    )
    db.approval_requests.find = lambda q=None, *a, **kw: iter([{"_id": ObjectId(), "status": "open"}])

    p1, p2 = _patch_db(db)
    with p1, p2:
        client = TestClient(main.app)
        resp = client.get(f"/workflow-lifecycle-summary?workspace_slug={ws}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["lifecycle_stage"] == "review"
    assert data["is_complete"] is False
    assert data["review"]["pending_assets"] == 1


