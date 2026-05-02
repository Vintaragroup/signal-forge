"""
Tests for Social Creative Engine v2 — client profiles, source channels,
source content, transcripts, snippets, creative assets, and creative tool runs.
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
        # v2 collections
        self.client_profiles = FakeCollection()
        self.source_channels = FakeCollection()
        self.source_content = FakeCollection()
        self.content_transcripts = FakeCollection()
        self.content_snippets = FakeCollection()
        self.creative_assets = FakeCollection()
        self.creative_tool_runs = FakeCollection()


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
# Part 1 — Client Profiles
# ---------------------------------------------------------------------------


def test_create_client_profile_returns_item():
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post("/client-profiles", json={
            "workspace_slug": "acme",
            "client_name": "Acme Corp",
            "brand_name": "ACME",
            "status": "active",
        })
    assert response.status_code == 200
    data = response.json()
    assert "item" in data
    assert data["item"]["client_name"] == "Acme Corp"
    assert data["item"]["likeness_permissions"] is False
    assert data["item"]["voice_permissions"] is False
    assert data["item"]["avatar_permissions"] is False
    assert "No post published" in data["message"]


def test_create_client_profile_requires_client_name():
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post("/client-profiles", json={"client_name": "   "})
    assert response.status_code == 400


def test_list_client_profiles_returns_items():
    fake_db = FakeDatabase()
    fake_db.client_profiles = FakeCollection([
        make_doc(workspace_slug="acme", client_name="Acme", is_demo=False),
        make_doc(workspace_slug="other", client_name="Other", is_demo=False),
    ])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/client-profiles")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


def test_list_client_profiles_workspace_isolation():
    fake_db = FakeDatabase()
    fake_db.client_profiles = FakeCollection([
        make_doc(workspace_slug="acme", client_name="Acme", is_demo=False),
        make_doc(workspace_slug="other", client_name="Other", is_demo=False),
    ])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/client-profiles?workspace_slug=acme")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["client_name"] == "Acme"


def test_list_client_profiles_demo_isolation():
    fake_db = FakeDatabase()
    fake_db.client_profiles = FakeCollection([
        make_doc(workspace_slug="acme", client_name="Real", is_demo=False),
        make_doc(workspace_slug="demo", client_name="DemoClient", is_demo=True),
    ])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/client-profiles?workspace_slug=acme")
    assert response.status_code == 200
    items = response.json()["items"]
    assert all(item["client_name"] != "DemoClient" for item in items)


# ---------------------------------------------------------------------------
# Part 2 — Source Channels
# ---------------------------------------------------------------------------


def test_create_source_channel_returns_item():
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post("/source-channels", json={
            "workspace_slug": "acme",
            "client_id": "client-1",
            "platform": "youtube",
            "channel_name": "Acme YouTube",
            "channel_url": "https://youtube.com/@acme",
            "approved_for_ingestion": True,
            "approved_for_reuse": False,
        })
    assert response.status_code == 200
    data = response.json()
    assert data["item"]["channel_name"] == "Acme YouTube"
    assert data["item"]["approved_for_ingestion"] is True


def test_list_source_channels_returns_items():
    fake_db = FakeDatabase()
    fake_db.source_channels = FakeCollection([
        make_doc(workspace_slug="acme", channel_name="Ch1", approved_for_ingestion=True),
        make_doc(workspace_slug="acme", channel_name="Ch2", approved_for_ingestion=False),
    ])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/source-channels?workspace_slug=acme")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


def test_list_source_channels_workspace_isolation():
    fake_db = FakeDatabase()
    fake_db.source_channels = FakeCollection([
        make_doc(workspace_slug="acme", channel_name="AcmeCh"),
        make_doc(workspace_slug="other", channel_name="OtherCh"),
    ])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/source-channels?workspace_slug=acme")
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["channel_name"] == "AcmeCh"


def test_list_source_channels_approval_gate_filter():
    fake_db = FakeDatabase()
    fake_db.source_channels = FakeCollection([
        make_doc(workspace_slug="acme", channel_name="Approved", approved_for_ingestion=True),
        make_doc(workspace_slug="acme", channel_name="Unapproved", approved_for_ingestion=False),
    ])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/source-channels?workspace_slug=acme&approved_for_ingestion=true")
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["channel_name"] == "Approved"


# ---------------------------------------------------------------------------
# Part 3 — Source Content
# ---------------------------------------------------------------------------


def test_create_source_content_defaults_to_needs_review():
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post("/source-content", json={
            "workspace_slug": "acme",
            "client_id": "client-1",
            "platform": "youtube",
            "source_url": "https://youtube.com/watch?v=abc123",
            "title": "How We Built Our Roofing Brand",
        })
    assert response.status_code == 200
    data = response.json()
    assert data["item"]["status"] == "needs_review"
    assert data["item"]["simulation_only"] is True
    assert data["item"]["outbound_actions_taken"] == 0


def test_list_source_content_returns_items():
    fake_db = FakeDatabase()
    fake_db.source_content = FakeCollection([
        make_doc(workspace_slug="acme", title="Video 1", status="needs_review"),
        make_doc(workspace_slug="acme", title="Video 2", status="approved"),
    ])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/source-content?workspace_slug=acme")
    assert len(response.json()["items"]) == 2


def test_list_source_content_workspace_filter():
    fake_db = FakeDatabase()
    fake_db.source_content = FakeCollection([
        make_doc(workspace_slug="acme", title="AcmeVid"),
        make_doc(workspace_slug="other", title="OtherVid"),
    ])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/source-content?workspace_slug=acme")
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "AcmeVid"


# ---------------------------------------------------------------------------
# Part 4 — Transcripts + Snippets
# ---------------------------------------------------------------------------


def test_create_content_transcript():
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post("/content-transcripts", json={
            "workspace_slug": "acme",
            "source_content_id": "src-1",
            "transcript_text": "Welcome to the show...",
            "status": "complete",
        })
    assert response.status_code == 200
    data = response.json()
    assert data["item"]["transcript_text"] == "Welcome to the show..."
    assert data["item"]["status"] == "complete"


def test_create_content_snippet_defaults_to_needs_review():
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post("/content-snippets", json={
            "workspace_slug": "acme",
            "source_content_id": "src-1",
            "transcript_id": "transcript-1",
            "transcript_text": "The best quote here.",
            "score": 0.92,
            "theme": "authority",
        })
    assert response.status_code == 200
    data = response.json()
    assert data["item"]["status"] == "needs_review"
    assert data["item"]["simulation_only"] is True
    assert data["item"]["outbound_actions_taken"] == 0
    assert "No post published" in data["message"]


def test_review_snippet_approve():
    fake_db = FakeDatabase()
    snippet_id = ObjectId()
    fake_db.content_snippets = FakeCollection([
        make_doc(_id=snippet_id, workspace_slug="acme", status="needs_review", review_events=[]),
    ])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post(f"/content-snippets/{snippet_id}/review", json={
            "decision": "approve",
            "note": "Great hook",
        })
    assert response.status_code == 200
    data = response.json()
    assert data["item"]["status"] == "approved"
    assert data["simulation_only"] is True
    assert "No post published" in data["message"]


def test_review_snippet_reject():
    fake_db = FakeDatabase()
    snippet_id = ObjectId()
    fake_db.content_snippets = FakeCollection([
        make_doc(_id=snippet_id, workspace_slug="acme", status="needs_review", review_events=[]),
    ])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post(f"/content-snippets/{snippet_id}/review", json={
            "decision": "reject",
            "note": "Off brand",
        })
    assert response.status_code == 200
    assert response.json()["item"]["status"] == "rejected"


def test_review_snippet_revise():
    fake_db = FakeDatabase()
    snippet_id = ObjectId()
    fake_db.content_snippets = FakeCollection([
        make_doc(_id=snippet_id, workspace_slug="acme", status="needs_review", review_events=[]),
    ])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post(f"/content-snippets/{snippet_id}/review", json={
            "decision": "revise",
            "note": "Trim 3 seconds",
        })
    assert response.status_code == 200
    assert response.json()["item"]["status"] == "needs_review"


def test_review_snippet_not_found():
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post(f"/content-snippets/{ObjectId()}/review", json={
            "decision": "approve",
        })
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Part 5 — Creative Assets + ComfyUI Tool Runs
# ---------------------------------------------------------------------------


def test_create_creative_asset_defaults_to_needs_review():
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post("/creative-assets", json={
            "workspace_slug": "acme",
            "client_id": "client-1",
            "asset_type": "image",
            "title": "Hero Banner",
        })
    assert response.status_code == 200
    data = response.json()
    assert data["item"]["status"] == "needs_review"
    assert data["item"]["simulation_only"] is True
    assert data["item"]["outbound_actions_taken"] == 0
    assert "No post published" in data["message"]


def test_list_creative_assets_returns_items():
    fake_db = FakeDatabase()
    fake_db.creative_assets = FakeCollection([
        make_doc(workspace_slug="acme", title="Asset1", status="needs_review"),
        make_doc(workspace_slug="acme", title="Asset2", status="approved"),
    ])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/creative-assets?workspace_slug=acme")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


def test_creative_tool_run_comfyui_disabled_skips_call():
    """When COMFYUI_ENABLED=false, no ComfyUI call is made and status is skipped."""
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database), \
         patch.dict(os.environ, {"COMFYUI_ENABLED": "false"}):
        client = TestClient(app)
        response = client.post("/creative-tool-runs", json={
            "workspace_slug": "acme",
            "tool_name": "comfyui",
            "prompt_inputs": {"6": {"text": "professional roofing photo"}},
        })

    assert response.status_code == 200
    data = response.json()
    assert data["item"]["status"] == "skipped"
    assert data["item"]["skip_reason"] == "comfyui_disabled"
    assert data["simulation_only"] is True
    assert "No post published" in data["message"]


def test_creative_tool_run_comfyui_enabled_but_unavailable_writes_failed_run():
    """When ComfyUI is enabled but unreachable, a failed tool run record is written."""
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    mock_comfyui = MagicMock()
    mock_comfyui.run_workflow.side_effect = Exception("Connection refused")

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database), \
         patch.dict(os.environ, {"COMFYUI_ENABLED": "true"}), \
         patch("agents.comfyui_client.ComfyUIClient", return_value=mock_comfyui):
        client = TestClient(app)
        response = client.post("/creative-tool-runs", json={
            "workspace_slug": "acme",
            "tool_name": "comfyui",
            "prompt_inputs": {},
        })

    assert response.status_code == 200
    data = response.json()
    assert data["item"]["status"] == "failed"
    assert "Connection refused" in data["error"]
    assert data["simulation_only"] is True
    assert "No post published" in data["message"]


def test_creative_tool_run_manual_completes():
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post("/creative-tool-runs", json={
            "workspace_slug": "acme",
            "tool_name": "manual",
            "notes": "Manually created asset",
        })
    assert response.status_code == 200
    data = response.json()
    assert data["item"]["status"] == "completed"
    assert data["item"]["tool_name"] == "manual"
    assert data["simulation_only"] is True
