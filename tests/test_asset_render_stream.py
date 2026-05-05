"""
Tests for Phase 8 — GET /asset-renders/{asset_id}/stream

Covers:
- 200 + video/mp4 for valid record with a real local file
- 404 when the record does not exist
- 404 when the record exists but the file is absent on disk
- 403 when the resolved file path escapes the allowed render directory
- 403 when a path-traversal string is present in the stored file_path
- workspace filter — GET /assets only returns records matching workspace_slug
- stream endpoint does not expose raw filesystem paths to the client
"""

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Path wiring (mirrors test_social_creative_engine_v5.py)
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import main
from main import app

# ---------------------------------------------------------------------------
# Minimal fake DB helpers (same pattern as v5 tests)
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

    def count_documents(self, query):
        return len([d for d in self.documents if self._matches(d, query)])

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
        # Declare all collections used anywhere in main.py so attribute lookups
        # succeed even when only some collections are under test here.
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
        self.client_profiles = FakeCollection()
        self.source_channels = FakeCollection()
        self.source_content = FakeCollection()
        self.content_transcripts = FakeCollection()
        self.content_snippets = FakeCollection()
        self.creative_assets = FakeCollection()
        self.creative_tool_runs = FakeCollection()
        self.audio_extraction_runs = FakeCollection()
        self.transcript_runs = FakeCollection()
        self.transcript_segments = FakeCollection()
        self.media_intake_records = FakeCollection()
        self.prompt_generations = FakeCollection()
        self.companies = FakeCollection()
        self.briefs = FakeCollection()
        self.asset_renders = FakeCollection()
        # v7.5 collections
        self.manual_publish_logs = FakeCollection()
        self.asset_performance_records = FakeCollection()
        self.creative_performance_summaries = FakeCollection()


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
# The allowed render directory used by the stream endpoint
# ---------------------------------------------------------------------------
ALLOWED_DIR = "/tmp/signalforge_renders"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _render_doc(render_id: ObjectId, file_path: str, workspace_slug="test-ws") -> dict:
    return make_doc(
        _id=render_id,
        workspace_slug=workspace_slug,
        file_path=file_path,
        status="needs_review",
        asset_type="short_form_video",
        generation_engine="comfyui",
        assembly_status="success",
        assembly_engine="ffmpeg",
        simulation_only=True,
        outbound_actions_taken=0,
    )


# ===========================================================================
# 1. Stream returns 200 + video/mp4 for a valid local file
# ===========================================================================

def test_stream_returns_mp4_for_valid_file():
    """
    Given a render record whose file_path points to a real .mp4 file inside
    ALLOWED_DIR, the endpoint should return 200 with Content-Type video/mp4.
    """
    fake_db = FakeDatabase()
    render_id = ObjectId()

    # Write a minimal file so FileResponse can stat it
    with tempfile.NamedTemporaryFile(
        suffix=".mp4",
        dir=ALLOWED_DIR,
        delete=False,
    ) as tmp:
        tmp.write(b"fake-mp4-bytes")
        tmp_path = tmp.name

    try:
        fake_db.asset_renders.documents.append(
            _render_doc(render_id, tmp_path)
        )
        fake_get_client, fake_get_database = make_db_patch(fake_db)

        with patch("main.get_client", fake_get_client), \
             patch("main.get_database", fake_get_database):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/asset-renders/{render_id}/stream",
                follow_redirects=True,
            )

        assert resp.status_code == 200, resp.text
        assert "video/mp4" in resp.headers.get("content-type", "")
    finally:
        os.unlink(tmp_path)


# ===========================================================================
# 2. Stream returns 404 when the render record is not in the database
# ===========================================================================

def test_stream_404_render_not_found():
    fake_db = FakeDatabase()
    # no documents inserted
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch("main.get_client", fake_get_client), \
         patch("main.get_database", fake_get_database):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/asset-renders/{ObjectId()}/stream")

    assert resp.status_code == 404
    assert "not found" in resp.json().get("detail", "").lower()


# ===========================================================================
# 3. Stream returns 404 when the record exists but the file is missing on disk
# ===========================================================================

def test_stream_404_file_missing_on_disk():
    fake_db = FakeDatabase()
    render_id = ObjectId()
    absent_path = os.path.join(ALLOWED_DIR, f"{render_id}_nonexistent.mp4")

    fake_db.asset_renders.documents.append(
        _render_doc(render_id, absent_path)
    )
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch("main.get_client", fake_get_client), \
         patch("main.get_database", fake_get_database):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/asset-renders/{render_id}/stream")

    assert resp.status_code == 404
    detail = resp.json().get("detail", "").lower()
    assert "not found" in detail or "missing" in detail or "cleaned" in detail


# ===========================================================================
# 4. Stream returns 403 when the file path escapes the allowed directory
# ===========================================================================

def test_stream_403_file_outside_allowed_dir():
    fake_db = FakeDatabase()
    render_id = ObjectId()

    # Path that resolves outside the allowed render dir
    outside_path = "/tmp/evil_video.mp4"

    fake_db.asset_renders.documents.append(
        _render_doc(render_id, outside_path)
    )
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    # Make os.path.isfile return True so path-check is reached before 404
    with patch("main.get_client", fake_get_client), \
         patch("main.get_database", fake_get_database), \
         patch("os.path.isfile", return_value=True):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/asset-renders/{render_id}/stream")

    assert resp.status_code == 403
    assert "outside" in resp.json().get("detail", "").lower()


# ===========================================================================
# 5. Stream returns 403 for a path-traversal attempt (symlink / .. sequence)
# ===========================================================================

def test_stream_403_path_traversal():
    fake_db = FakeDatabase()
    render_id = ObjectId()

    # Simulate a stored path that looks like it's inside the dir but resolves
    # outside via ".." traversal.  os.path.realpath will collapse it.
    traversal_path = os.path.join(ALLOWED_DIR, "..", "etc", "passwd.mp4")

    fake_db.asset_renders.documents.append(
        _render_doc(render_id, traversal_path)
    )
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch("main.get_client", fake_get_client), \
         patch("main.get_database", fake_get_database), \
         patch("os.path.isfile", return_value=True):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/asset-renders/{render_id}/stream")

    assert resp.status_code == 403


# ===========================================================================
# 6. Stream returns 404 when file_path is empty or non-mp4
# ===========================================================================

def test_stream_404_no_file_path():
    fake_db = FakeDatabase()
    render_id = ObjectId()

    # Record exists but has no file_path
    doc = _render_doc(render_id, "")
    doc["file_path"] = ""
    fake_db.asset_renders.documents.append(doc)
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch("main.get_client", fake_get_client), \
         patch("main.get_database", fake_get_database):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/asset-renders/{render_id}/stream")

    assert resp.status_code == 404


def test_stream_404_non_mp4_extension():
    fake_db = FakeDatabase()
    render_id = ObjectId()

    doc = _render_doc(render_id, os.path.join(ALLOWED_DIR, f"{render_id}.avi"))
    fake_db.asset_renders.documents.append(doc)
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch("main.get_client", fake_get_client), \
         patch("main.get_database", fake_get_database):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/asset-renders/{render_id}/stream")

    assert resp.status_code == 404


# ===========================================================================
# 7. Workspace filter — GET /assets only returns records for the given slug
# ===========================================================================

def test_get_assets_workspace_filter():
    fake_db = FakeDatabase()

    id_jm = ObjectId()
    id_other = ObjectId()

    fake_db.asset_renders.documents.extend([
        _render_doc(id_jm, os.path.join(ALLOWED_DIR, f"{id_jm}.mp4"), workspace_slug="john-maxwell-pilot"),
        _render_doc(id_other, os.path.join(ALLOWED_DIR, f"{id_other}.mp4"), workspace_slug="other-client"),
    ])
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch("main.get_client", fake_get_client), \
         patch("main.get_database", fake_get_database):
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/assets?workspace_slug=john-maxwell-pilot")

    assert resp.status_code == 200
    data = resp.json()
    items = data.get("items", [])
    assert len(items) == 1
    assert items[0]["workspace_slug"] == "john-maxwell-pilot"


# ===========================================================================
# 8. Stream endpoint does NOT reveal raw file paths in any response body
# ===========================================================================

def test_stream_404_body_does_not_leak_path():
    """The 404 response body must not contain the server-side file path."""
    fake_db = FakeDatabase()
    render_id = ObjectId()
    secret_path = "/tmp/signalforge_renders/super_secret.mp4"

    fake_db.asset_renders.documents.append(
        _render_doc(render_id, secret_path)
    )
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with patch("main.get_client", fake_get_client), \
         patch("main.get_database", fake_get_database):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/asset-renders/{render_id}/stream")

    # File doesn't exist so we get 404 — body must not contain the raw path
    assert secret_path not in resp.text
