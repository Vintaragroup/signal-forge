"""
Tests for Social Creative Engine v4 — media intake, approval gates,
FFmpeg integration, and safety guarantees.

All v4 endpoints require source content to be approved before audio
extraction can run.  Transcript runs check for completed audio extraction
(except when using stub provider with text_hint). Snippet generation
requires a completed transcript run.

Safety invariants checked:
- simulation_only = True on every record
- outbound_actions_taken = 0 on every record
- No audio downloaded, no posts published, no schedules created
"""

import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import main
from main import app


# ---------------------------------------------------------------------------
# Shared helpers (same FakeDatabase pattern as v2/v3 tests)
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
        # v4 collections
        self.media_intake_records = FakeCollection()


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
# Part 1 — Source content status update (approval)
# ---------------------------------------------------------------------------


def test_approve_source_content_for_extraction():
    """PATCH /source-content/{id}/status with approved updates the status field."""
    fake_db = FakeDatabase()
    content_id = ObjectId()
    content_doc = make_doc(
        _id=content_id,
        workspace_slug="ws1",
        source_url="https://example.com/vid.mp4",
        title="Test video",
        status="needs_review",
    )
    fake_db.source_content.documents.append(content_doc)

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.patch(
            f"/source-content/{content_id}/status",
            json={"status": "approved"},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["item"]["status"] == "approved"
    assert "No post published" in data["message"]


def test_reject_source_content_status():
    """PATCH /source-content/{id}/status with rejected updates correctly."""
    fake_db = FakeDatabase()
    content_id = ObjectId()
    content_doc = make_doc(
        _id=content_id,
        workspace_slug="ws1",
        source_url="https://example.com/vid.mp4",
        title="Test",
        status="needs_review",
    )
    fake_db.source_content.documents.append(content_doc)

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.patch(
            f"/source-content/{content_id}/status",
            json={"status": "rejected"},
        )

    assert resp.status_code == 200
    assert resp.json()["item"]["status"] == "rejected"


def test_update_source_content_status_404():
    """PATCH /source-content/{id}/status with unknown id returns 404."""
    fake_db = FakeDatabase()
    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.patch(
            f"/source-content/{ObjectId()}/status",
            json={"status": "approved"},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Part 2 — Media intake registration
# ---------------------------------------------------------------------------


def test_register_url_metadata_only():
    """POST /media-intake-records with source_url stores metadata only, no download."""
    fake_db = FakeDatabase()
    content_id = ObjectId()
    content_doc = make_doc(
        _id=content_id,
        workspace_slug="ws1",
        source_url="https://youtube.com/watch?v=abc",
        status="approved",
    )
    fake_db.source_content.documents.append(content_doc)

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.post(
            "/media-intake-records",
            json={
                "workspace_slug": "ws1",
                "source_content_id": str(content_id),
                "source_url": "https://youtube.com/watch?v=abc",
            },
        )

    assert resp.status_code == 200, resp.text
    item = resp.json()["item"]
    assert item["intake_method"] == "url_metadata_only"
    assert item["status"] == "registered"
    assert item["simulation_only"] is True
    assert item["outbound_actions_taken"] == 0
    # URL was not fetched — just stored
    assert item["source_url"] == "https://youtube.com/watch?v=abc"
    assert item["media_path"] == ""


def test_media_intake_has_safety_fields():
    """Media intake records always carry simulation_only and outbound_actions_taken."""
    fake_db = FakeDatabase()
    content_id = ObjectId()
    content_doc = make_doc(_id=content_id, workspace_slug="ws1", status="approved")
    fake_db.source_content.documents.append(content_doc)

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.post(
            "/media-intake-records",
            json={
                "workspace_slug": "ws1",
                "source_content_id": str(content_id),
                "source_url": "https://example.com/vid",
            },
        )

    item = resp.json()["item"]
    assert item["simulation_only"] is True
    assert item["outbound_actions_taken"] == 0


def test_register_media_requires_approved_content():
    """POST /media-intake-records blocks when source content is not approved."""
    fake_db = FakeDatabase()
    content_id = ObjectId()
    content_doc = make_doc(
        _id=content_id,
        workspace_slug="ws1",
        status="needs_review",
    )
    fake_db.source_content.documents.append(content_doc)

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.post(
            "/media-intake-records",
            json={
                "workspace_slug": "ws1",
                "source_content_id": str(content_id),
                "source_url": "https://example.com/vid",
            },
        )

    assert resp.status_code == 422


def test_list_media_intake_records():
    """GET /media-intake-records returns records for workspace."""
    fake_db = FakeDatabase()
    fake_db.media_intake_records.documents.append(
        make_doc(workspace_slug="ws1", intake_method="url_metadata_only", status="registered")
    )
    fake_db.media_intake_records.documents.append(
        make_doc(workspace_slug="ws2", intake_method="url_metadata_only", status="registered")
    )

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.get("/media-intake-records?workspace_slug=ws1")

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["workspace_slug"] == "ws1"


def test_workspace_isolation_media_intake():
    """Media intake records are filtered by workspace_slug."""
    fake_db = FakeDatabase()
    for ws in ("alpha", "beta", "alpha"):
        fake_db.media_intake_records.documents.append(
            make_doc(workspace_slug=ws, intake_method="url_metadata_only")
        )

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.get("/media-intake-records?workspace_slug=alpha")

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    assert all(i["workspace_slug"] == "alpha" for i in items)


# ---------------------------------------------------------------------------
# Part 3 — Audio extraction v4 (approval gate)
# ---------------------------------------------------------------------------


def test_audio_extraction_v4_requires_approved_content():
    """POST /audio-extraction-runs/v4 returns 422 when content is not approved."""
    fake_db = FakeDatabase()
    content_id = ObjectId()
    content_doc = make_doc(
        _id=content_id,
        workspace_slug="ws1",
        source_url="https://example.com/vid",
        status="needs_review",
    )
    fake_db.source_content.documents.append(content_doc)

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.post(
            "/audio-extraction-runs/v4",
            json={
                "workspace_slug": "ws1",
                "source_content_id": str(content_id),
                "source_url": "https://example.com/vid",
            },
        )

    assert resp.status_code == 422
    assert "approved" in resp.json()["detail"].lower()


def test_audio_extraction_v4_ffmpeg_disabled_skips_safely():
    """With FFMPEG_ENABLED=false (default), extraction skips safely for approved content."""
    fake_db = FakeDatabase()
    content_id = ObjectId()
    content_doc = make_doc(
        _id=content_id,
        workspace_slug="ws1",
        source_url="https://example.com/vid",
        status="approved",
    )
    fake_db.source_content.documents.append(content_doc)

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}), \
         patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.post(
            "/audio-extraction-runs/v4",
            json={
                "workspace_slug": "ws1",
                "source_content_id": str(content_id),
                "source_url": "https://example.com/vid",
            },
        )

    assert resp.status_code == 200, resp.text
    item = resp.json()["item"]
    assert item["status"] == "skipped"
    assert item["simulation_only"] is True
    assert item["outbound_actions_taken"] == 0


def test_audio_extraction_v4_safety_fields():
    """Audio extraction run records always carry simulation_only=True."""
    fake_db = FakeDatabase()
    content_id = ObjectId()
    content_doc = make_doc(
        _id=content_id, workspace_slug="ws1", source_url="https://x.com/v", status="approved"
    )
    fake_db.source_content.documents.append(content_doc)

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}), \
         patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.post(
            "/audio-extraction-runs/v4",
            json={"workspace_slug": "ws1", "source_content_id": str(content_id)},
        )

    item = resp.json()["item"]
    assert item["simulation_only"] is True
    assert item["outbound_actions_taken"] == 0


# ---------------------------------------------------------------------------
# Part 4 — Transcript runs v4 (audio run gate)
# ---------------------------------------------------------------------------


def test_transcript_v4_stub_allowed_without_extraction():
    """Stub provider transcript allowed even without a prior audio extraction run."""
    fake_db = FakeDatabase()
    content_id = ObjectId()
    content_doc = make_doc(
        _id=content_id, workspace_slug="ws1", source_url="https://x.com/v", status="approved"
    )
    fake_db.source_content.documents.append(content_doc)

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.dict(os.environ, {"TRANSCRIPT_PROVIDER": "stub"}), \
         patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.post(
            "/transcript-runs/v4",
            json={
                "workspace_slug": "ws1",
                "source_content_id": str(content_id),
                "text_hint": "Hello world this is a test transcript.",
            },
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["item"]["status"] == "complete"
    assert data["item"]["simulation_only"] is True
    assert data["item"]["outbound_actions_taken"] == 0


def test_transcript_v4_rejects_missing_audio_run():
    """Transcript run with a nonexistent audio_extraction_run_id returns 422."""
    fake_db = FakeDatabase()
    content_id = ObjectId()
    content_doc = make_doc(
        _id=content_id, workspace_slug="ws1", source_url="https://x.com/v", status="approved"
    )
    fake_db.source_content.documents.append(content_doc)

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.post(
            "/transcript-runs/v4",
            json={
                "workspace_slug": "ws1",
                "source_content_id": str(content_id),
                "audio_extraction_run_id": str(ObjectId()),
            },
        )

    assert resp.status_code == 422
    assert "not found" in resp.json()["detail"].lower()


def test_transcript_v4_stores_segments():
    """Transcript run with text_hint stores segments in transcript_segments collection."""
    fake_db = FakeDatabase()
    content_id = ObjectId()
    content_doc = make_doc(
        _id=content_id, workspace_slug="ws1", source_url="https://x.com/v", status="approved"
    )
    fake_db.source_content.documents.append(content_doc)

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.dict(os.environ, {"TRANSCRIPT_PROVIDER": "stub"}), \
         patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.post(
            "/transcript-runs/v4",
            json={
                "workspace_slug": "ws1",
                "source_content_id": str(content_id),
                "text_hint": "We closed ten deals this week using a simple follow-up system.",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["segment_count"] > 0
    assert len(fake_db.transcript_segments.documents) > 0
    seg = fake_db.transcript_segments.documents[0]
    assert seg["simulation_only"] is True


def test_transcript_v4_workspace_isolation():
    """Transcript runs list is filtered by workspace."""
    fake_db = FakeDatabase()
    fake_db.transcript_runs.documents.append(
        make_doc(workspace_slug="ws1", status="complete", source_content_id="c1")
    )
    fake_db.transcript_runs.documents.append(
        make_doc(workspace_slug="ws2", status="complete", source_content_id="c2")
    )

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.get("/transcript-runs?workspace_slug=ws1")

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["workspace_slug"] == "ws1"


# ---------------------------------------------------------------------------
# Part 5 — Snippet generation v4 (transcript gate)
# ---------------------------------------------------------------------------


def test_snippet_generation_v4_requires_transcript():
    """POST generate-snippets/v4 returns 422 when no completed transcript run exists."""
    fake_db = FakeDatabase()
    content_id = ObjectId()
    content_doc = make_doc(
        _id=content_id, workspace_slug="ws1", source_url="https://x.com/v", status="approved"
    )
    fake_db.source_content.documents.append(content_doc)

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.post(
            f"/source-content/{content_id}/generate-snippets/v4",
            json={"workspace_slug": "ws1"},
        )

    assert resp.status_code == 422


def test_snippet_generation_v4_with_transcript():
    """POST generate-snippets/v4 creates snippet candidates from transcript segments."""
    fake_db = FakeDatabase()
    content_id_str = str(ObjectId())

    run_id = ObjectId()
    run_doc = make_doc(
        _id=run_id,
        workspace_slug="ws1",
        source_content_id=content_id_str,
        status="complete",
        provider="stub",
    )
    fake_db.transcript_runs.documents.append(run_doc)

    # Two segments with different signal density
    fake_db.transcript_segments.documents.append(
        make_doc(
            workspace_slug="ws1",
            source_content_id=content_id_str,
            transcript_run_id=str(run_id),
            index=0,
            start_ms=0,
            end_ms=4640,
            text="We closed ten deals this week using a simple consistent system.",
            speaker="speaker_1",
            confidence=0.9,
            provider="stub",
        )
    )
    fake_db.transcript_segments.documents.append(
        make_doc(
            workspace_slug="ws1",
            source_content_id=content_id_str,
            transcript_run_id=str(run_id),
            index=1,
            start_ms=5000,
            end_ms=9000,
            text="Just a filler sentence here.",
            speaker="speaker_1",
            confidence=0.9,
            provider="stub",
        )
    )

    content_oid = ObjectId(content_id_str)
    fake_db.source_content.documents.append(
        make_doc(_id=content_oid, workspace_slug="ws1", source_url="https://x.com/v", status="approved")
    )

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.post(
            f"/source-content/{content_id_str}/generate-snippets/v4",
            json={
                "workspace_slug": "ws1",
                "transcript_run_id": str(run_id),
                "min_score": 0.0,
            },
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["created_count"] > 0
    item = data["items"][0]
    assert item["simulation_only"] is True
    assert item["outbound_actions_taken"] == 0
    assert item["status"] == "needs_review"


def test_snippet_generation_v4_safety_fields():
    """All snippet records carry simulation_only=True, outbound_actions_taken=0."""
    fake_db = FakeDatabase()
    content_id_str = str(ObjectId())
    run_id = ObjectId()
    run_doc = make_doc(
        _id=run_id,
        workspace_slug="ws1",
        source_content_id=content_id_str,
        status="complete",
        provider="stub",
    )
    fake_db.transcript_runs.documents.append(run_doc)
    fake_db.transcript_segments.documents.append(
        make_doc(
            workspace_slug="ws1",
            source_content_id=content_id_str,
            transcript_run_id=str(run_id),
            index=0,
            start_ms=0,
            end_ms=3000,
            text="Trust is everything in business. Results always speak louder than words.",
            speaker="speaker_1",
            confidence=0.9,
            provider="stub",
        )
    )
    content_oid = ObjectId(content_id_str)
    fake_db.source_content.documents.append(
        make_doc(_id=content_oid, workspace_slug="ws1", source_url="https://x.com/v", status="approved")
    )

    fake_get_client, fake_get_db = make_db_patch(fake_db)
    with patch.object(main, "get_client", fake_get_client), \
         patch.object(main, "get_database", fake_get_db):
        client = TestClient(app)
        resp = client.post(
            f"/source-content/{content_id_str}/generate-snippets/v4",
            json={"workspace_slug": "ws1", "min_score": 0.0},
        )

    items = resp.json()["items"]
    for item in items:
        assert item["simulation_only"] is True
        assert item["outbound_actions_taken"] == 0


# ---------------------------------------------------------------------------
# Part 6 — media_intake module unit tests
# ---------------------------------------------------------------------------


def test_register_local_file_with_valid_path():
    """register_local_file returns registered status for a real file path."""
    from media_intake import register_local_file

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        tmp_path = f.name

    try:
        result = register_local_file(tmp_path)
        assert result.status == "registered"
        assert result.intake_method == "local_file"
        assert result.extension == ".mp4"
        assert result.simulation_only is True
        assert result.outbound_actions_taken == 0
    finally:
        os.unlink(tmp_path)


def test_register_local_file_nonexistent_path_fails_safely():
    """register_local_file with a nonexistent path returns status=failed safely."""
    from media_intake import register_local_file

    result = register_local_file("/nonexistent/path/video.mp4")
    assert result.status == "failed"
    assert result.error != ""
    assert result.simulation_only is True


def test_register_local_file_invalid_extension():
    """register_local_file with an unsupported extension returns status=failed."""
    from media_intake import register_local_file

    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
        tmp_path = f.name

    try:
        result = register_local_file(tmp_path)
        assert result.status == "failed"
        assert "extension" in result.error.lower()
    finally:
        os.unlink(tmp_path)


def test_register_url_metadata_only_unit():
    """register_url_metadata stores URL without fetching it."""
    from media_intake import register_url_metadata

    result = register_url_metadata("https://youtube.com/watch?v=abc123")
    assert result.status == "registered"
    assert result.intake_method == "url_metadata_only"
    assert result.skip_reason == "url_download_not_enabled"
    assert result.simulation_only is True
    assert result.outbound_actions_taken == 0


def test_register_url_metadata_invalid_scheme():
    """register_url_metadata with ftp:// URL returns status=failed."""
    from media_intake import register_url_metadata

    result = register_url_metadata("ftp://example.com/video.mp4")
    assert result.status == "failed"


# ---------------------------------------------------------------------------
# Part 7 — audio_extractor unit tests
# ---------------------------------------------------------------------------


def test_ffmpeg_extractor_empty_media_path_fails_safely():
    """FFmpegAudioExtractor.extract() with empty media_path returns status=failed."""
    from audio_extractor import FFmpegAudioExtractor

    extractor = FFmpegAudioExtractor()
    result = extractor.extract(source_url="", media_path="", output_dir="/tmp")
    assert result.status == "failed"
    assert result.simulation_only is True
    assert result.outbound_actions_taken == 0


def test_stub_extractor_returns_skipped():
    """StubAudioExtractor always returns status=skipped safely."""
    from audio_extractor import StubAudioExtractor

    extractor = StubAudioExtractor()
    result = extractor.extract(source_url="https://x.com/v", media_path="", output_dir="/tmp")
    assert result.status == "skipped"
    assert result.simulation_only is True


# ---------------------------------------------------------------------------
# Part 8 — transcript_provider unit tests
# ---------------------------------------------------------------------------


def test_whisper_provider_raises_not_implemented():
    """WhisperTranscriptProvider.transcribe() raises NotImplementedError."""
    from transcript_provider import WhisperTranscriptProvider

    provider = WhisperTranscriptProvider()
    with pytest.raises(NotImplementedError):
        provider.transcribe("content-1")


def test_stub_provider_returns_segments():
    """StubTranscriptProvider returns at least one segment for any text."""
    from transcript_provider import StubTranscriptProvider

    provider = StubTranscriptProvider()
    segments = provider.transcribe("content-1", text_hint="Hello world test.")
    assert len(segments) > 0
    seg = segments[0]
    assert "text" in seg
    assert "start_ms" in seg
    assert "end_ms" in seg
    assert seg["provider"] == "stub"


def test_get_transcript_provider_returns_stub_by_default():
    """get_transcript_provider() returns StubTranscriptProvider by default."""
    from transcript_provider import get_transcript_provider, StubTranscriptProvider

    with patch.dict(os.environ, {"TRANSCRIPT_PROVIDER": "stub", "TRANSCRIPT_LIVE_ENABLED": "false"}):
        provider = get_transcript_provider()
    assert isinstance(provider, StubTranscriptProvider)


def test_get_transcript_provider_whisper_requires_live_enabled():
    """get_transcript_provider() returns stub unless TRANSCRIPT_LIVE_ENABLED=true."""
    from transcript_provider import get_transcript_provider, StubTranscriptProvider

    with patch.dict(os.environ, {"TRANSCRIPT_PROVIDER": "whisper", "TRANSCRIPT_LIVE_ENABLED": "false"}):
        provider = get_transcript_provider()
    assert isinstance(provider, StubTranscriptProvider)
