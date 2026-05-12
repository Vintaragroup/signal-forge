"""
Phase 6G — Backend tests for _validate_workflow_definition_stages enhanced rules.

Tests:
  1. Invalid stage number (stage_number=8) → 422
  2. Duplicate stage numbers → 422
  3. Blank labels → 422
  4. No required stages → 422
  5. Valid creation (all stages valid, at least one required, labels present) → 201/200
"""
from datetime import datetime, timezone

from bson import ObjectId
from fastapi.testclient import TestClient

import main
from main import app

# ── Shared fakes (same pattern as test_client_profiles_api) ──────────────────


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
        return FakeCursor([doc for doc in self.documents if self._matches(doc, query)])

    def find_one(self, query):
        docs = list(self.find(query))
        return docs[0] if docs else None

    def insert_one(self, document):
        if "_id" not in document:
            document["_id"] = ObjectId()
        self.documents.append(document)
        return InsertResult(document["_id"])

    def update_one(self, query, update, upsert=False):
        doc = self.find_one(query)
        if not doc:
            return None
        for key, value in (update.get("$set") or {}).items():
            doc[key] = value
        return None

    def _matches(self, document, query):
        for key, value in query.items():
            if key == "$or":
                if not any(self._matches(document, cond) for cond in value):
                    return False
                continue
            if document.get(key) != value:
                return False
        return True


class FakeDatabase:
    def __init__(self):
        self.workflow_definitions = FakeCollection([])
        self.admin_client_profiles = FakeCollection([])
        self.workspaces = FakeCollection([])


class FakeClient:
    def close(self):
        return None


def make_test_client():
    db = FakeDatabase()
    fake_client = FakeClient()
    client = TestClient(app)
    main.get_client = lambda: fake_client
    main.get_database = lambda c: db
    return client, db


# ── Helpers ───────────────────────────────────────────────────────────────────

def _valid_stages():
    """Return a complete set of 7 valid stages with at least one required."""
    return [
        {
            "stage_number": i,
            "label": f"Stage {i}",
            "agent_key": "",
            "run_card_type": "",
            "chips": [],
            "required": True,
            "notes": "",
        }
        for i in range(1, 8)
    ]


def _post_workflow_def(client, stages, *, slug="test-def", display_name="Test Def"):
    return client.post(
        "/admin/workflow-definitions",
        json={
            "slug": slug,
            "display_name": display_name,
            "system_profile_id": "",
            "module": "",
            "notes": "",
            "status": "active",
            "stages": stages,
        },
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_invalid_stage_number_returns_422():
    client, _ = make_test_client()
    stages = _valid_stages()
    stages[0]["stage_number"] = 8  # invalid
    resp = _post_workflow_def(client, stages)
    assert resp.status_code == 422
    assert "8" in resp.json()["detail"]


def test_duplicate_stage_numbers_returns_422():
    client, _ = make_test_client()
    stages = _valid_stages()
    stages[1]["stage_number"] = 1  # duplicate of first stage
    resp = _post_workflow_def(client, stages)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "duplicate" in detail.lower() or "1" in detail


def test_blank_label_returns_422():
    client, _ = make_test_client()
    stages = _valid_stages()
    stages[2]["label"] = "   "  # blank/whitespace
    resp = _post_workflow_def(client, stages)
    assert resp.status_code == 422
    assert "blank" in resp.json()["detail"].lower() or "label" in resp.json()["detail"].lower()


def test_no_required_stages_returns_422():
    client, _ = make_test_client()
    stages = _valid_stages()
    for s in stages:
        s["required"] = False
    resp = _post_workflow_def(client, stages)
    assert resp.status_code == 422
    detail = resp.json()["detail"].lower()
    assert "required" in detail


def test_valid_workflow_definition_creation_succeeds():
    client, _ = make_test_client()
    stages = _valid_stages()
    resp = _post_workflow_def(client, stages)
    # 200 or 201 both acceptable depending on API version
    assert resp.status_code in (200, 201)
    body = resp.json()
    assert body.get("item") or body.get("slug") or body.get("ok")
