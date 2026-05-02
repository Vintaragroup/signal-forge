"""
Tests for Creative Studio v1 — content briefs, content drafts,
review workflow, workspace filtering, demo isolation, and
agent draft generation.
"""

import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import main
from main import app


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

NOW = datetime(2024, 6, 1, tzinfo=timezone.utc)


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

    def update_one(self, query, update):
        for doc in self.documents:
            if self._matches(doc, query):
                for key, value in (update.get("$set") or {}).items():
                    doc[key] = value
                for key, value in (update.get("$push") or {}).items():
                    doc.setdefault(key, []).append(value)
                return

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
                elif "$ne" in value:
                    if doc_val == value["$ne"]:
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
        self.agent_artifacts = FakeCollection()
        self.deals = FakeCollection()
        self.scraped_candidates = FakeCollection()
        self.tool_runs = FakeCollection()
        self.workspaces = FakeCollection()
        self.content_briefs = FakeCollection()
        self.content_drafts = FakeCollection()


class FakeClient:
    def close(self):
        pass


def make_db_patch(fake_db):
    fake_client = FakeClient()

    def fake_get_client():
        return fake_client

    def fake_get_database(_client):
        return fake_db

    return fake_get_client, fake_get_database


# ---------------------------------------------------------------------------
# Content Briefs: create
# ---------------------------------------------------------------------------


def test_create_brief_returns_item():
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post("/content-briefs", json={
            "workspace_slug": "acme",
            "module": "contractor_growth",
            "campaign_name": "Summer Outreach",
            "audience": "Local roofers",
            "platform": "Instagram",
            "goal": "5 booked calls",
            "offer": "Free audit",
            "tone": "friendly",
            "notes": "Focus on summer.",
            "status": "draft",
        })

    assert response.status_code == 200
    data = response.json()
    assert "item" in data
    assert data["item"]["campaign_name"] == "Summer Outreach"
    assert data["item"]["workspace_slug"] == "acme"
    assert data["item"]["status"] == "draft"
    assert data["message"] == "Content brief created."


def test_create_brief_stored_in_collection():
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        client.post("/content-briefs", json={
            "workspace_slug": "store-test",
            "campaign_name": "Stored Brief",
            "status": "draft",
        })

    assert len(fake_db.content_briefs.documents) == 1
    assert fake_db.content_briefs.documents[0]["campaign_name"] == "Stored Brief"


# ---------------------------------------------------------------------------
# Content Briefs: list + workspace filter
# ---------------------------------------------------------------------------


def test_list_briefs_returns_all():
    fake_db = FakeDatabase()
    fake_db.content_briefs.documents = [
        make_doc(workspace_slug="ws1", campaign_name="Brief A", status="draft"),
        make_doc(workspace_slug="ws2", campaign_name="Brief B", status="approved"),
    ]
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/content-briefs?include_test=true")

    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


def test_list_briefs_workspace_filter():
    fake_db = FakeDatabase()
    fake_db.content_briefs.documents = [
        make_doc(workspace_slug="ws1", campaign_name="Brief A", status="draft"),
        make_doc(workspace_slug="ws2", campaign_name="Brief B", status="draft"),
    ]
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/content-briefs?workspace_slug=ws1&include_test=true")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["campaign_name"] == "Brief A"


def test_list_briefs_status_filter():
    fake_db = FakeDatabase()
    fake_db.content_briefs.documents = [
        make_doc(workspace_slug="ws1", campaign_name="Brief A", status="approved"),
        make_doc(workspace_slug="ws1", campaign_name="Brief B", status="draft"),
    ]
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/content-briefs?status=approved&include_test=true")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["campaign_name"] == "Brief A"


# ---------------------------------------------------------------------------
# Content Drafts: create
# ---------------------------------------------------------------------------


def test_create_draft_returns_item():
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post("/content-drafts", json={
            "workspace_slug": "acme",
            "module": "contractor_growth",
            "brief_id": "brief-123",
            "platform": "Instagram",
            "content_type": "post",
            "title": "Summer Post",
            "body": "Check out our summer deals!",
            "hashtags": ["summer", "contractor"],
            "call_to_action": "DM us today",
            "status": "needs_review",
        })

    assert response.status_code == 200
    data = response.json()
    assert data["item"]["title"] == "Summer Post"
    assert data["item"]["status"] == "needs_review"
    assert data["item"]["outbound_actions_taken"] == 0
    assert data["item"]["simulation_only"] is True
    assert data["item"]["review_events"] == []
    assert "No post published" in data["message"]


def test_create_draft_sets_safety_flags():
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        client.post("/content-drafts", json={
            "workspace_slug": "safety-test",
            "title": "Safety Check Draft",
            "status": "needs_review",
        })

    doc = fake_db.content_drafts.documents[0]
    assert doc["outbound_actions_taken"] == 0
    assert doc["simulation_only"] is True


# ---------------------------------------------------------------------------
# Content Drafts: list + workspace filter
# ---------------------------------------------------------------------------


def test_list_drafts_workspace_filter():
    fake_db = FakeDatabase()
    fake_db.content_drafts.documents = [
        make_doc(workspace_slug="ws1", title="Draft A", status="needs_review"),
        make_doc(workspace_slug="ws2", title="Draft B", status="needs_review"),
    ]
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/content-drafts?workspace_slug=ws1&include_test=true")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Draft A"


# ---------------------------------------------------------------------------
# Draft review: approve
# ---------------------------------------------------------------------------


def test_review_draft_approve():
    fake_db = FakeDatabase()
    draft_id = ObjectId()
    fake_db.content_drafts.documents = [
        make_doc(_id=draft_id, workspace_slug="ws1", title="Draft X", status="needs_review", review_events=[]),
    ]
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post(f"/content-drafts/{draft_id}/review", json={
            "decision": "approve",
            "note": "Looks great",
        })

    assert response.status_code == 200
    data = response.json()
    assert data["item"]["status"] == "approved"
    assert data["item"]["review_decision"] == "approve"
    assert data["simulation_only"] is True
    assert "No post published" in data["message"]


def test_review_draft_reject():
    fake_db = FakeDatabase()
    draft_id = ObjectId()
    fake_db.content_drafts.documents = [
        make_doc(_id=draft_id, workspace_slug="ws1", title="Draft Y", status="needs_review", review_events=[]),
    ]
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post(f"/content-drafts/{draft_id}/review", json={
            "decision": "reject",
            "note": "Off-brand",
        })

    assert response.status_code == 200
    assert response.json()["item"]["status"] == "rejected"


def test_review_draft_revise():
    fake_db = FakeDatabase()
    draft_id = ObjectId()
    fake_db.content_drafts.documents = [
        make_doc(_id=draft_id, workspace_slug="ws1", title="Draft Z", status="needs_review", review_events=[]),
    ]
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post(f"/content-drafts/{draft_id}/review", json={
            "decision": "revise",
            "note": "Please shorten",
        })

    assert response.status_code == 200
    assert response.json()["item"]["status"] == "needs_review"


def test_review_draft_not_found():
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post(f"/content-drafts/{ObjectId()}/review", json={
            "decision": "approve",
        })

    assert response.status_code == 404


def test_review_stores_review_event():
    fake_db = FakeDatabase()
    draft_id = ObjectId()
    fake_db.content_drafts.documents = [
        make_doc(_id=draft_id, title="Event Draft", status="needs_review", review_events=[]),
    ]
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        client.post(f"/content-drafts/{draft_id}/review", json={"decision": "approve", "note": "LGTM"})

    doc = fake_db.content_drafts.documents[0]
    assert len(doc["review_events"]) == 1
    assert doc["review_events"][0]["decision"] == "approve"


# ---------------------------------------------------------------------------
# Demo isolation: is_demo records filtered by default
# ---------------------------------------------------------------------------


def test_demo_briefs_excluded_by_default():
    fake_db = FakeDatabase()
    fake_db.content_briefs.documents = [
        make_doc(workspace_slug="ws1", campaign_name="Real Brief", status="draft", is_demo=False),
        make_doc(workspace_slug="ws1", campaign_name="Demo Brief", status="draft", is_demo=True),
    ]
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        # include_test=False (default) — demo records excluded
        response = client.get("/content-briefs?workspace_slug=ws1")

    assert response.status_code == 200
    items = response.json()["items"]
    names = [i["campaign_name"] for i in items]
    assert "Demo Brief" not in names


def test_demo_briefs_included_with_include_test():
    fake_db = FakeDatabase()
    fake_db.content_briefs.documents = [
        make_doc(workspace_slug="ws1", campaign_name="Real Brief", status="draft"),
        make_doc(workspace_slug="ws1", campaign_name="Demo Brief", status="draft", is_demo=True),
    ]
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/content-briefs?workspace_slug=ws1&include_test=true")

    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


def test_demo_drafts_excluded_by_default():
    fake_db = FakeDatabase()
    fake_db.content_drafts.documents = [
        make_doc(workspace_slug="ws1", title="Real Draft", status="needs_review"),
        make_doc(workspace_slug="ws1", title="Demo Draft", status="needs_review", is_demo=True),
    ]
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/content-drafts?workspace_slug=ws1")

    assert response.status_code == 200
    items = response.json()["items"]
    titles = [i["title"] for i in items]
    assert "Demo Draft" not in titles


# ---------------------------------------------------------------------------
# Agent draft creation: generate_content_drafts
# ---------------------------------------------------------------------------


def test_agent_generate_content_drafts_creates_draft():
    """generate_content_drafts() should insert a content_draft for each approved brief."""
    from agents.content_agent import ContentAgent

    db = FakeDatabase()
    brief_id = ObjectId()
    db.content_briefs.documents = [
        {
            "_id": brief_id,
            "workspace_slug": "ws1",
            "module": "contractor_growth",
            "campaign_name": "Agent Test Brief",
            "audience": "Local roofers",
            "platform": "Instagram",
            "goal": "Get calls",
            "offer": "Free audit",
            "tone": "friendly",
            "notes": "",
            "status": "approved",
            "is_demo": False,
        }
    ]

    mock_plan_result = {
        "response": "Plan: focus on summer demand for roofing.",
        "confidence": 0.85,
        "model_used": "gpt-4o",
        "task": "plan_content_from_brief",
    }
    mock_draft_result = {
        "response": "Draft body: Summer is here — get your roof inspected!",
        "confidence": 0.80,
        "model_used": "gpt-4o-mini",
        "task": "write_content_draft",
    }

    agent = ContentAgent.__new__(ContentAgent)
    agent.db = db
    agent.module = "contractor_growth"
    agent.workspace_slug = "ws1"
    agent.limit = 100
    agent.run_id = "test-run-001"
    agent.agent_name = "content_agent"

    with patch("agents.gpt_client.generate_agent_response", return_value=mock_plan_result), \
         patch("agents.gpt_client.generate_draft_response", return_value=mock_draft_result):
        results = agent.generate_content_drafts()

    assert len(db.content_drafts.documents) == 1
    draft = db.content_drafts.documents[0]
    assert draft["brief_id"] == str(brief_id)
    assert draft["status"] == "needs_review"
    assert draft["generated_by_agent"] == "content_agent"
    assert draft["simulation_only"] is True
    assert draft["outbound_actions_taken"] == 0

    # Brief should be updated to needs_review
    updated_brief = db.content_briefs.documents[0]
    assert updated_brief["status"] == "needs_review"


def test_agent_generate_content_drafts_no_approved_briefs():
    """generate_content_drafts() returns empty list if no approved briefs exist."""
    from agents.content_agent import ContentAgent

    db = FakeDatabase()
    db.content_briefs.documents = [
        {
            "_id": ObjectId(),
            "workspace_slug": "ws1",
            "module": "contractor_growth",
            "campaign_name": "Draft Brief",
            "status": "draft",
        }
    ]

    agent = ContentAgent.__new__(ContentAgent)
    agent.db = db
    agent.module = "contractor_growth"
    agent.workspace_slug = "ws1"
    agent.limit = 100
    agent.run_id = "test-run-002"
    agent.agent_name = "content_agent"

    results = agent.generate_content_drafts()

    assert results == []
    assert len(db.content_drafts.documents) == 0
