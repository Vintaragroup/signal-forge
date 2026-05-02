"""
Tests for workspace data cleanup logic and API include_legacy/include_test filtering.
"""

import sys
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

# Make scripts importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import main
from main import app, _is_mock_record, _is_legacy_record, apply_real_mode_filters


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


def make_doc(**kwargs):
    return {"_id": ObjectId(), "created_at": NOW, "updated_at": NOW, **kwargs}


class InsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, _spec):
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(self.documents)


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = list(documents or [])

    def find(self, query=None):
        query = query or {}
        return FakeCursor([d for d in self.documents if self._matches(d, query)])

    def find_one(self, query):
        docs = list(self.find(query))
        return docs[0] if docs else None

    def insert_one(self, document):
        if "_id" not in document:
            document["_id"] = ObjectId()
        self.documents.append(document)
        return InsertResult(document["_id"])

    def update_many(self, query, update):
        for doc in self.documents:
            if self._matches(doc, query):
                for key, value in (update.get("$set") or {}).items():
                    doc[key] = value

    def count_documents(self, query):
        return len([d for d in self.documents if self._matches(d, query)])

    def delete_one(self, query):
        for i, doc in enumerate(self.documents):
            if self._matches(doc, query):
                del self.documents[i]
                return

    def _matches(self, document, query):
        for key, value in query.items():
            if key == "$or":
                if not any(self._matches(document, cond) for cond in value):
                    return False
                continue
            if key == "$and":
                if not all(self._matches(document, cond) for cond in value):
                    return False
                continue
            if isinstance(value, dict):
                doc_val = document.get(key)
                if "$in" in value:
                    if doc_val not in value["$in"]:
                        return False
                elif "$nin" in value:
                    if doc_val in value["$nin"]:
                        return False
                elif "$exists" in value:
                    exists = key in document and document[key] is not None
                    if value["$exists"] != exists:
                        return False
            else:
                if document.get(key) != value:
                    return False
        return True


class FakeDatabase:
    def __init__(self):
        self.contacts = FakeCollection()
        self.leads = FakeCollection()
        self.message_drafts = FakeCollection()
        self.approval_requests = FakeCollection()
        self.agent_tasks = FakeCollection()
        self.agent_runs = FakeCollection()
        self.deals = FakeCollection()
        self.scraped_candidates = FakeCollection()
        self.tool_runs = FakeCollection()
        self.workspaces = FakeCollection()


class FakeClient:
    def close(self):
        pass


# ---------------------------------------------------------------------------
# Unit tests: _is_mock_record
# ---------------------------------------------------------------------------

def test_is_mock_record_source_mock():
    assert _is_mock_record({"source": "mock"})


def test_is_mock_record_source_contractor_test_campaign():
    assert _is_mock_record({"source": "contractor_test_campaign_v1"})


def test_is_mock_record_run_id_module_v():
    assert _is_mock_record({"run_id": "module-v2-test-20260428"})


def test_is_mock_record_run_id_module_n_test():
    assert _is_mock_record({"run_id": "module1-test-20260428"})


def test_is_mock_record_gpt_runtime_test():
    assert _is_mock_record({"source": "gpt_runtime_test_campaign_v1"})


def test_is_mock_record_tool_layer_review():
    assert _is_mock_record({"source": "tool_layer_review"})


def test_is_mock_record_is_demo_flag():
    assert _is_mock_record({"is_demo": True})


def test_is_mock_record_is_test_flag():
    assert _is_mock_record({"is_test": True})


def test_is_mock_record_real_record():
    assert not _is_mock_record({"source": "manual_upload", "company": "Hill Country HVAC"})


def test_is_mock_record_google_search_real():
    assert not _is_mock_record({"source": "google_search_v1", "company": "Austin Roofing Co"})


# ---------------------------------------------------------------------------
# Unit tests: _is_legacy_record
# ---------------------------------------------------------------------------

def test_is_legacy_record_missing():
    assert _is_legacy_record({})


def test_is_legacy_record_empty_string():
    assert _is_legacy_record({"workspace_slug": ""})


def test_is_legacy_record_none():
    assert _is_legacy_record({"workspace_slug": None})


def test_is_legacy_record_has_slug():
    assert not _is_legacy_record({"workspace_slug": "austin-contractor-test"})


# ---------------------------------------------------------------------------
# Unit tests: apply_real_mode_filters
# ---------------------------------------------------------------------------

REAL_DOC = make_doc(workspace_slug="acme", source="manual_upload", company="Hill Country HVAC")
LEGACY_DOC = make_doc(source="manual_upload", company="Real Company")  # no workspace_slug
MOCK_DOC = make_doc(workspace_slug="acme", source="mock", company="Mock Roofing Co")
DEMO_WS_DOC = make_doc(workspace_slug="demo", source="manual_upload", company="Demo Corp")


def test_apply_real_mode_filters_no_workspace_returns_all():
    records = [REAL_DOC, LEGACY_DOC, MOCK_DOC]
    result = apply_real_mode_filters(records, workspace_slug="")
    assert result == records  # unchanged when no workspace filter


def test_apply_real_mode_filters_excludes_legacy_by_default():
    records = [REAL_DOC, LEGACY_DOC]
    result = apply_real_mode_filters(records, workspace_slug="acme")
    assert LEGACY_DOC not in result
    assert REAL_DOC in result


def test_apply_real_mode_filters_excludes_mock_by_default():
    records = [REAL_DOC, MOCK_DOC]
    result = apply_real_mode_filters(records, workspace_slug="acme")
    assert MOCK_DOC not in result
    assert REAL_DOC in result


def test_apply_real_mode_filters_excludes_demo_workspace():
    records = [REAL_DOC, DEMO_WS_DOC]
    result = apply_real_mode_filters(records, workspace_slug="acme")
    assert DEMO_WS_DOC not in result


def test_apply_real_mode_filters_include_legacy_restores():
    records = [REAL_DOC, LEGACY_DOC]
    result = apply_real_mode_filters(records, workspace_slug="acme", include_legacy=True)
    assert LEGACY_DOC in result


def test_apply_real_mode_filters_include_test_restores_mock():
    records = [REAL_DOC, MOCK_DOC]
    result = apply_real_mode_filters(records, workspace_slug="acme", include_test=True)
    assert MOCK_DOC in result


def test_apply_real_mode_filters_include_both():
    records = [REAL_DOC, LEGACY_DOC, MOCK_DOC]
    result = apply_real_mode_filters(records, workspace_slug="acme", include_legacy=True, include_test=True)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# API tests: contacts endpoint with include_legacy / include_test
# ---------------------------------------------------------------------------

def test_contacts_excludes_legacy_when_workspace_set(monkeypatch):
    db = FakeDatabase()
    db.contacts.documents = [
        make_doc(name="Real Contact", company="Hill Country HVAC", workspace_slug="acme"),
        make_doc(name="Legacy Contact", company="Old Corp"),  # no workspace_slug
    ]
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/contacts?workspace_slug=acme")
    assert response.status_code == 200
    items = response.json()["items"]
    names = [i["name"] for i in items]
    assert "Real Contact" in names
    assert "Legacy Contact" not in names


def test_contacts_excludes_mock_when_workspace_set(monkeypatch):
    db = FakeDatabase()
    db.contacts.documents = [
        make_doc(name="Real Contact", company="Hill Country HVAC", workspace_slug="acme", source="manual_upload"),
        make_doc(name="Mock Contact", company="Mock Corp", workspace_slug="acme", source="mock"),
    ]
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/contacts?workspace_slug=acme")
    assert response.status_code == 200
    items = response.json()["items"]
    names = [i["name"] for i in items]
    assert "Real Contact" in names
    assert "Mock Contact" not in names


def test_contacts_include_legacy_restores_records(monkeypatch):
    db = FakeDatabase()
    db.contacts.documents = [
        make_doc(name="Real Contact", company="Hill Country HVAC", workspace_slug="acme"),
        make_doc(name="Legacy Contact", company="Old Corp"),
    ]
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    # No workspace_slug filter — all records visible (legacy included by default in all-workspaces mode)
    response = client.get("/contacts")
    assert response.status_code == 200
    items = response.json()["items"]
    names = [i["name"] for i in items]
    assert "Legacy Contact" in names


def test_contacts_include_test_restores_mock_records(monkeypatch):
    db = FakeDatabase()
    db.contacts.documents = [
        make_doc(name="Real Contact", company="Hill Country HVAC", workspace_slug="acme", source="manual_upload"),
        make_doc(name="Mock Contact", company="Mock Corp", workspace_slug="acme", source="mock"),
    ]
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/contacts?workspace_slug=acme&include_test=true")
    assert response.status_code == 200
    items = response.json()["items"]
    names = [i["name"] for i in items]
    assert "Mock Contact" in names


def test_contacts_all_workspaces_returns_everything(monkeypatch):
    """When workspace_slug is omitted (all workspaces), legacy and mock records are visible."""
    db = FakeDatabase()
    db.contacts.documents = [
        make_doc(name="Real Contact", company="Hill Country HVAC", workspace_slug="acme"),
        make_doc(name="Legacy Contact", company="Old Corp"),
        make_doc(name="Mock Contact", company="Mock Corp", source="mock"),
    ]
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/contacts")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 3


# ---------------------------------------------------------------------------
# Script unit tests (dry-run logic, archive, backfill)
# ---------------------------------------------------------------------------

# Import cleanup helpers directly from script
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from workspace_data_cleanup import (
    count_stats,
    is_mock_record as cleanup_is_mock,
    is_missing_workspace as cleanup_is_missing,
    archive_and_remove,
    run_backfill_default,
    run_archive_legacy,
    run_archive_mock,
)


class SimpleCollection:
    """Minimal in-memory collection for script tests."""

    def __init__(self, docs=None):
        self.documents = list(docs or [])
        self._archive = []

    def find(self, query=None):
        return list(self.documents)

    def insert_one(self, doc):
        self._archive.append(doc)

    def delete_one(self, query):
        oid = query.get("_id")
        self.documents = [d for d in self.documents if d.get("_id") != oid]


class SimpleDB:
    def __init__(self, collections):
        self._collections = collections
        for name, coll in collections.items():
            setattr(self, name, coll)

    def __getitem__(self, name):
        if name not in self._collections:
            self._collections[name] = SimpleCollection()
        return self._collections[name]


def test_cleanup_is_mock_record():
    assert cleanup_is_mock({"source": "mock"})
    assert cleanup_is_mock({"source": "contractor_test_campaign"})
    assert not cleanup_is_mock({"source": "manual_upload"})


def test_cleanup_is_missing_workspace():
    assert cleanup_is_missing({})
    assert cleanup_is_missing({"workspace_slug": ""})
    assert not cleanup_is_missing({"workspace_slug": "acme"})


def test_cleanup_dry_run_counts():
    docs = [
        {"_id": ObjectId(), "workspace_slug": "acme", "source": "manual_upload"},
        {"_id": ObjectId(), "source": "mock"},  # mock, also missing ws
        {"_id": ObjectId()},  # legacy only
    ]
    coll = SimpleCollection(docs)
    colls = {
        "contacts": coll,
        "leads": SimpleCollection(),
        "companies": SimpleCollection(),
        "scraped_candidates": SimpleCollection(),
        "tool_runs": SimpleCollection(),
        "message_drafts": SimpleCollection(),
        "approval_requests": SimpleCollection(),
        "agent_tasks": SimpleCollection(),
        "agent_runs": SimpleCollection(),
        "deals": SimpleCollection(),
    }
    db = SimpleDB(colls)

    stats = count_stats(db)
    assert stats["contacts"]["total"] == 3
    assert stats["contacts"]["missing_workspace_slug"] == 2
    assert stats["contacts"]["likely_mock_or_test"] == 1  # only "mock" doc is identified as mock
    assert stats["contacts"]["real_looking"] == 1  # only acme/manual_upload


def test_cleanup_archive_and_remove_dry_run():
    docs = [{"_id": ObjectId(), "source": "mock"}]
    coll = SimpleCollection(docs)
    archive_coll = SimpleCollection()

    class DB:
        def __getitem__(self, name):
            if name == "contacts_archive":
                return archive_coll
            return coll

        contacts = coll

    count = archive_and_remove(DB(), "contacts", docs, "test", dry_run=True)
    assert count == 1
    assert len(archive_coll._archive) == 0  # dry_run — nothing written
    assert len(coll.documents) == 1  # nothing removed


def test_cleanup_archive_and_remove_applies():
    oid = ObjectId()
    docs = [{"_id": oid, "source": "mock"}]
    coll = SimpleCollection(docs)
    archive_coll = SimpleCollection()

    class DB:
        contacts = coll

        def __getitem__(self, name):
            if name == "contacts_archive":
                return archive_coll
            return coll

    count = archive_and_remove(DB(), "contacts", docs, "test_archive", dry_run=False)
    assert count == 1
    assert len(archive_coll._archive) == 1
    assert archive_coll._archive[0]["_archive_reason"] == "test_archive"
    assert len(coll.documents) == 0  # removed from active


def test_cleanup_backfill_default_dry_run():
    docs = [{"_id": ObjectId()}, {"_id": ObjectId(), "workspace_slug": "acme"}]
    coll = SimpleCollection(docs)
    coll.update_many_calls = []

    def track_update_many(query, update):
        coll.update_many_calls.append((query, update))

    coll.update_many = track_update_many

    colls = {
        "contacts": coll,
        "leads": SimpleCollection(),
        "companies": SimpleCollection(),
        "scraped_candidates": SimpleCollection(),
        "tool_runs": SimpleCollection(),
        "message_drafts": SimpleCollection(),
        "approval_requests": SimpleCollection(),
        "agent_tasks": SimpleCollection(),
        "agent_runs": SimpleCollection(),
        "deals": SimpleCollection(),
    }
    db = SimpleDB(colls)

    run_backfill_default(db, dry_run=True)
    # dry_run — no update_many should be called
    assert len(coll.update_many_calls) == 0


def test_cleanup_backfill_default_applies():
    oid1 = ObjectId()
    oid2 = ObjectId()
    docs = [
        {"_id": oid1},  # missing ws
        {"_id": oid2, "workspace_slug": "acme"},  # has ws — should not be touched
    ]
    coll = SimpleCollection(docs)
    coll.update_many_calls = []

    def track_update_many(query, update):
        coll.update_many_calls.append((query, update))
        # Actually apply the update for verification
        for doc in coll.documents:
            ids = (query.get("_id") or {}).get("$in", [])
            if doc["_id"] in ids:
                for k, v in (update.get("$set") or {}).items():
                    doc[k] = v

    coll.update_many = track_update_many

    colls = {
        "contacts": coll,
        "leads": SimpleCollection(),
        "companies": SimpleCollection(),
        "scraped_candidates": SimpleCollection(),
        "tool_runs": SimpleCollection(),
        "message_drafts": SimpleCollection(),
        "approval_requests": SimpleCollection(),
        "agent_tasks": SimpleCollection(),
        "agent_runs": SimpleCollection(),
        "deals": SimpleCollection(),
    }
    db = SimpleDB(colls)

    run_backfill_default(db, dry_run=False)
    assert len(coll.update_many_calls) == 1
    # Only oid1 (the one missing workspace_slug) should be in the $in list
    ids_to_update = coll.update_many_calls[0][0]["_id"]["$in"]
    assert oid1 in ids_to_update
    assert oid2 not in ids_to_update
