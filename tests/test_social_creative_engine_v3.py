"""
Tests for Social Creative Engine v3 — audio extraction, transcript runs,
transcript segments, snippet generation from transcript, and source content
metadata updates.
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
        # v3 collections
        self.audio_extraction_runs = FakeCollection()
        self.transcript_runs = FakeCollection()
        self.transcript_segments = FakeCollection()


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
# Part 1 — Audio Extraction Runs
# ---------------------------------------------------------------------------


def test_create_audio_extraction_run_returns_skipped():
    """With FFMPEG_ENABLED=false (default stub), status should be 'skipped'."""
    fake_db = FakeDatabase()
    fake_db.source_content.documents.append(
        make_doc(workspace_slug="acme", source_url="https://example.invalid/video")
    )
    source_id = str(fake_db.source_content.documents[0]["_id"])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database), \
         patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
        client = TestClient(app)
        response = client.post("/audio-extraction-runs", json={
            "workspace_slug": "acme",
            "source_content_id": source_id,
            "source_url": "https://example.invalid/video",
        })
    assert response.status_code == 200
    data = response.json()
    assert data["item"]["status"] == "skipped"
    assert data["item"]["skip_reason"] == "ffmpeg_disabled"


def test_create_audio_extraction_run_has_safety_fields():
    """Audio extraction run must always have simulation_only=True and outbound_actions_taken=0."""
    fake_db = FakeDatabase()
    fake_db.source_content.documents.append(
        make_doc(workspace_slug="acme", source_url="https://example.invalid/video")
    )
    source_id = str(fake_db.source_content.documents[0]["_id"])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post("/audio-extraction-runs", json={
            "workspace_slug": "acme",
            "source_content_id": source_id,
            "source_url": "https://example.invalid/video",
        })
    assert response.status_code == 200
    item = response.json()["item"]
    assert item["simulation_only"] is True
    assert item["outbound_actions_taken"] == 0


def test_create_audio_extraction_run_workspace_isolation():
    """Audio extraction run is stored with the correct workspace_slug."""
    fake_db = FakeDatabase()
    fake_db.source_content.documents.append(
        make_doc(workspace_slug="acme", source_url="https://example.invalid/video")
    )
    source_id = str(fake_db.source_content.documents[0]["_id"])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post("/audio-extraction-runs", json={
            "workspace_slug": "acme",
            "source_content_id": source_id,
            "source_url": "https://example.invalid/video",
        })
    assert response.status_code == 200
    stored = fake_db.audio_extraction_runs.documents
    assert len(stored) == 1
    assert stored[0]["workspace_slug"] == "acme"


def test_list_audio_extraction_runs_workspace_filter():
    """GET /audio-extraction-runs?workspace_slug= returns only matching runs."""
    fake_db = FakeDatabase()
    fake_db.audio_extraction_runs.documents = [
        make_doc(workspace_slug="acme", source_content_id="sc1", status="skipped"),
        make_doc(workspace_slug="other", source_content_id="sc2", status="skipped"),
    ]
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/audio-extraction-runs?workspace_slug=acme")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["workspace_slug"] == "acme"


# ---------------------------------------------------------------------------
# Part 2 — Transcript Runs
# ---------------------------------------------------------------------------


def test_create_transcript_run_stub_creates_segments():
    """POST /transcript-runs with stub provider should create segments (segment_count > 0)."""
    fake_db = FakeDatabase()
    fake_db.source_content.documents.append(
        make_doc(workspace_slug="acme", source_url="https://example.invalid/video")
    )
    source_id = str(fake_db.source_content.documents[0]["_id"])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database), \
         patch.dict(os.environ, {"TRANSCRIPT_PROVIDER": "stub"}):
        client = TestClient(app)
        response = client.post("/transcript-runs", json={
            "workspace_slug": "acme",
            "source_content_id": source_id,
        })
    assert response.status_code == 200
    data = response.json()
    assert data["item"]["segment_count"] > 0
    assert data["item"]["status"] == "complete"


def test_create_transcript_run_segments_stored_in_db():
    """POST /transcript-runs should persist segments to transcript_segments collection."""
    fake_db = FakeDatabase()
    fake_db.source_content.documents.append(
        make_doc(workspace_slug="acme", source_url="https://example.invalid/video")
    )
    source_id = str(fake_db.source_content.documents[0]["_id"])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post("/transcript-runs", json={
            "workspace_slug": "acme",
            "source_content_id": source_id,
        })
    assert response.status_code == 200
    assert len(fake_db.transcript_segments.documents) > 0
    seg = fake_db.transcript_segments.documents[0]
    assert seg["source_content_id"] == source_id
    assert "text" in seg


def test_create_transcript_run_has_safety_fields():
    """Transcript run must have simulation_only=True and outbound_actions_taken=0."""
    fake_db = FakeDatabase()
    fake_db.source_content.documents.append(
        make_doc(workspace_slug="acme", source_url="https://example.invalid/video")
    )
    source_id = str(fake_db.source_content.documents[0]["_id"])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post("/transcript-runs", json={
            "workspace_slug": "acme",
            "source_content_id": source_id,
        })
    item = response.json()["item"]
    assert item["simulation_only"] is True
    assert item["outbound_actions_taken"] == 0


def test_list_transcript_runs_workspace_filter():
    """GET /transcript-runs returns only runs for the requested workspace."""
    fake_db = FakeDatabase()
    fake_db.transcript_runs.documents = [
        make_doc(workspace_slug="acme", source_content_id="sc1", status="complete"),
        make_doc(workspace_slug="other", source_content_id="sc2", status="complete"),
    ]
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get("/transcript-runs?workspace_slug=acme")
    assert response.status_code == 200
    items = response.json()["items"]
    assert all(i["workspace_slug"] == "acme" for i in items)
    assert len(items) == 1


# ---------------------------------------------------------------------------
# Part 3 — Transcript Segments
# ---------------------------------------------------------------------------


def test_list_transcript_segments_by_run_id():
    """GET /transcript-segments?transcript_run_id= returns only segments for that run."""
    run_id = str(ObjectId())
    other_run_id = str(ObjectId())
    fake_db = FakeDatabase()
    fake_db.transcript_segments.documents = [
        make_doc(workspace_slug="acme", transcript_run_id=run_id, index=0, text="Hello world."),
        make_doc(workspace_slug="acme", transcript_run_id=run_id, index=1, text="Second line."),
        make_doc(workspace_slug="acme", transcript_run_id=other_run_id, index=0, text="Different run."),
    ]
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.get(f"/transcript-segments?transcript_run_id={run_id}")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert all(i["transcript_run_id"] == run_id for i in items)


# ---------------------------------------------------------------------------
# Part 4 — Snippet Generation
# ---------------------------------------------------------------------------


def test_generate_snippets_from_transcript():
    """POST /source-content/{id}/generate-snippets should create snippet candidates."""
    fake_db = FakeDatabase()
    fake_db.source_content.documents.append(
        make_doc(workspace_slug="acme", source_url="https://example.invalid/video")
    )
    source_id = str(fake_db.source_content.documents[0]["_id"])
    run_id = str(ObjectId())
    fake_db.transcript_segments.documents = [
        make_doc(
            workspace_slug="acme",
            source_content_id=source_id,
            transcript_run_id=run_id,
            index=0,
            start_ms=0,
            end_ms=4000,
            text="We closed ten roofing jobs in one week using a simple system.",
        ),
        make_doc(
            workspace_slug="acme",
            source_content_id=source_id,
            transcript_run_id=run_id,
            index=1,
            start_ms=4100,
            end_ms=8000,
            text="Every estimate got a next-day follow-up call from a real person.",
        ),
    ]
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post(
            f"/source-content/{source_id}/generate-snippets",
            json={"workspace_slug": "acme", "transcript_run_id": run_id},
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) > 0


def test_generate_snippets_creates_simulation_only_records():
    """Generated snippets must have simulation_only=True and outbound_actions_taken=0."""
    fake_db = FakeDatabase()
    fake_db.source_content.documents.append(
        make_doc(workspace_slug="acme", source_url="https://example.invalid/video")
    )
    source_id = str(fake_db.source_content.documents[0]["_id"])
    run_id = str(ObjectId())
    fake_db.transcript_segments.documents = [
        make_doc(
            workspace_slug="acme",
            source_content_id=source_id,
            transcript_run_id=run_id,
            index=0,
            start_ms=0,
            end_ms=4000,
            text="This is a great roofing tip for homeowners looking for real value.",
        ),
    ]
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post(
            f"/source-content/{source_id}/generate-snippets",
            json={"workspace_slug": "acme", "transcript_run_id": run_id},
        )
    assert response.status_code == 200
    items = response.json()["items"]
    for item in items:
        assert item["simulation_only"] is True
        assert item["outbound_actions_taken"] == 0
        assert item["status"] == "needs_review"
        assert item["generation_source"] == "auto"


def test_generate_snippets_respects_max_snippets():
    """max_snippets parameter should cap how many snippet candidates are returned."""
    fake_db = FakeDatabase()
    fake_db.source_content.documents.append(
        make_doc(workspace_slug="acme", source_url="https://example.invalid/video")
    )
    source_id = str(fake_db.source_content.documents[0]["_id"])
    run_id = str(ObjectId())
    # Create 10 segments
    for i in range(10):
        fake_db.transcript_segments.documents.append(
            make_doc(
                workspace_slug="acme",
                source_content_id=source_id,
                transcript_run_id=run_id,
                index=i,
                start_ms=i * 4000,
                end_ms=(i + 1) * 4000,
                text=f"This is segment {i}. We help roofing contractors grow revenue fast.",
            )
        )
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post(
            f"/source-content/{source_id}/generate-snippets",
            json={"workspace_slug": "acme", "transcript_run_id": run_id, "max_snippets": 3},
        )
    assert response.status_code == 200
    assert len(response.json()["items"]) <= 3


def test_generate_snippets_empty_when_no_segments():
    """generate-snippets with no matching segments should return empty items, not error."""
    fake_db = FakeDatabase()
    fake_db.source_content.documents.append(
        make_doc(workspace_slug="acme", source_url="https://example.invalid/video")
    )
    source_id = str(fake_db.source_content.documents[0]["_id"])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.post(
            f"/source-content/{source_id}/generate-snippets",
            json={"workspace_slug": "acme", "transcript_run_id": str(ObjectId())},
        )
    assert response.status_code == 200
    assert response.json()["items"] == []


# ---------------------------------------------------------------------------
# Part 5 — Source Content Metadata Update
# ---------------------------------------------------------------------------


def test_update_source_content_metadata():
    """PATCH /source-content/{id}/metadata should update allowed fields."""
    fake_db = FakeDatabase()
    fake_db.source_content.documents.append(
        make_doc(workspace_slug="acme", source_url="https://example.invalid/video", tags=[], language="en")
    )
    source_id = str(fake_db.source_content.documents[0]["_id"])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.patch(
            f"/source-content/{source_id}/metadata",
            json={"tags": ["roofing", "b2b"], "language": "en", "description": "Great video."},
        )
    assert response.status_code == 200
    item = response.json()["item"]
    assert item["tags"] == ["roofing", "b2b"]
    assert item["language"] == "en"
    assert item["description"] == "Great video."


def test_update_source_content_metadata_404():
    """PATCH /source-content/{id}/metadata should return 404 for unknown id."""
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)
    missing_id = str(ObjectId())

    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_database):
        client = TestClient(app)
        response = client.patch(
            f"/source-content/{missing_id}/metadata",
            json={"tags": ["test"]},
        )
    assert response.status_code == 404
