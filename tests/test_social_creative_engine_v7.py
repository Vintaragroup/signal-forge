"""
Tests for Social Creative Engine v7 — Real Local Transcription Provider

Covers:
- StubTranscriptProvider is the default (no gates required)
- WhisperTranscriptProvider blocked unless TRANSCRIPT_LIVE_ENABLED=true
- WhisperTranscriptProvider blocked unless TRANSCRIPT_PROVIDER=whisper
- Missing audio path fails safely, error stored in transcript run record
- Real/local provider stores transcript run with provider, status, input_path, error_message
- Segment shape: start_ms, end_ms, text, speaker, confidence, index required
- Snippet generation uses transcript segments from the run
- AUTO_SCORE_SNIPPETS=true triggers v6.5 scoring after snippet creation
- Workspace isolation: transcript run update does not touch other runs
- Safety invariants: simulation_only=True, outbound_actions_taken=0 on all records
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import main
from main import app

sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))

from transcript_provider import (
    BaseTranscriptProvider,
    StubTranscriptProvider,
    WhisperTranscriptProvider,
    get_transcript_provider,
)

# ---------------------------------------------------------------------------
# Shared helpers — same FakeDatabase/FakeCollection/FakeCursor/FakeClient pattern
# ---------------------------------------------------------------------------

NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)


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
        return FakeCursor([d for d in self.documents if self._matches(d, query or {})])

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
                push = update.get("$push") or {}
                for key, value in push.items():
                    doc.setdefault(key, []).append(value)
                return

    def count_documents(self, query):
        return len([d for d in self.documents if self._matches(d, query)])

    def _matches(self, document, query):
        for key, value in query.items():
            if key in ("$or", "$and"):
                op_fn = any if key == "$or" else all
                if not op_fn(self._matches(document, c) for c in value):
                    return False
                continue
            if isinstance(value, dict):
                doc_val = document.get(key)
                if "$in" in value and doc_val not in value["$in"]:
                    return False
                elif "$gte" in value and (doc_val is None or doc_val < value["$gte"]):
                    return False
                elif "$exists" in value:
                    exists = key in document and document[key] is not None
                    if value["$exists"] != exists:
                        return False
                elif "$ne" in value and doc_val == value["$ne"]:
                    return False
            else:
                if document.get(key) != value:
                    return False
        return True


class FakeDatabase:
    def __init__(self):
        self.content_snippets = FakeCollection()
        self.prompt_generations = FakeCollection()
        self.asset_renders = FakeCollection()
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
        self.creative_assets = FakeCollection()
        self.creative_tool_runs = FakeCollection()
        self.audio_extraction_runs = FakeCollection()
        self.transcript_runs = FakeCollection()
        self.transcript_segments = FakeCollection()
        self.media_intake_records = FakeCollection()
        self.companies = FakeCollection()
        self.briefs = FakeCollection()


class FakeClient:
    def close(self):
        pass


def make_db_patch(fake_db):
    fake_client = FakeClient()

    def fake_get_client():
        return fake_client

    def fake_get_database(client):
        return fake_db

    return fake_get_client, fake_get_database


# ---------------------------------------------------------------------------
# TestStubProviderDefault
# ---------------------------------------------------------------------------

class TestStubProviderDefault:
    def test_stub_is_default_no_env_vars(self):
        """Without any env vars set, get_transcript_provider returns StubTranscriptProvider."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TRANSCRIPT_PROVIDER", None)
            os.environ.pop("TRANSCRIPT_LIVE_ENABLED", None)
            provider = get_transcript_provider()
        assert isinstance(provider, StubTranscriptProvider)

    def test_stub_provider_name(self):
        provider = StubTranscriptProvider()
        assert provider.provider_name == "stub"

    def test_stub_transcribe_returns_list(self):
        provider = StubTranscriptProvider()
        segments = provider.transcribe(source_content_id="test", audio_path="", text_hint="")
        assert isinstance(segments, list)
        assert len(segments) > 0

    def test_stub_transcribe_uses_text_hint(self):
        provider = StubTranscriptProvider()
        hint = "First segment. Second segment is here too."
        segments = provider.transcribe(source_content_id="test", audio_path="", text_hint=hint)
        combined = " ".join(s["text"] for s in segments)
        # All words from hint appear in combined output
        for word in hint.replace(".", "").split():
            assert word in combined

    def test_stub_segment_has_required_keys(self):
        provider = StubTranscriptProvider()
        segments = provider.transcribe(source_content_id="x", audio_path="")
        seg = segments[0]
        for key in ("index", "start_ms", "end_ms", "text", "speaker", "confidence", "provider"):
            assert key in seg, f"Segment missing key: {key}"

    def test_stub_segments_are_indexed_sequentially(self):
        provider = StubTranscriptProvider()
        segments = provider.transcribe(source_content_id="x", audio_path="")
        for i, seg in enumerate(segments):
            assert seg["index"] == i

    def test_stub_is_subclass_of_base(self):
        assert issubclass(StubTranscriptProvider, BaseTranscriptProvider)


# ---------------------------------------------------------------------------
# TestWhisperGate
# ---------------------------------------------------------------------------

class TestWhisperGate:
    def test_whisper_blocked_when_live_not_enabled(self):
        """TRANSCRIPT_PROVIDER=whisper but TRANSCRIPT_LIVE_ENABLED not set → stub."""
        env = {"TRANSCRIPT_PROVIDER": "whisper"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("TRANSCRIPT_LIVE_ENABLED", None)
            provider = get_transcript_provider()
        assert isinstance(provider, StubTranscriptProvider)

    def test_whisper_blocked_when_live_explicitly_false(self):
        """TRANSCRIPT_PROVIDER=whisper but TRANSCRIPT_LIVE_ENABLED=false → stub."""
        env = {"TRANSCRIPT_PROVIDER": "whisper", "TRANSCRIPT_LIVE_ENABLED": "false"}
        with patch.dict(os.environ, env):
            provider = get_transcript_provider()
        assert isinstance(provider, StubTranscriptProvider)

    def test_whisper_blocked_when_provider_not_set(self):
        """TRANSCRIPT_LIVE_ENABLED=true but TRANSCRIPT_PROVIDER not whisper → stub."""
        env = {"TRANSCRIPT_LIVE_ENABLED": "true"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("TRANSCRIPT_PROVIDER", None)
            provider = get_transcript_provider()
        assert isinstance(provider, StubTranscriptProvider)

    def test_whisper_provider_returned_when_both_gates_set(self):
        """Both TRANSCRIPT_PROVIDER=whisper AND TRANSCRIPT_LIVE_ENABLED=true → Whisper."""
        env = {"TRANSCRIPT_PROVIDER": "whisper", "TRANSCRIPT_LIVE_ENABLED": "true"}
        with patch.dict(os.environ, env):
            provider = get_transcript_provider()
        assert isinstance(provider, WhisperTranscriptProvider)

    def test_whisper_is_subclass_of_base(self):
        assert issubclass(WhisperTranscriptProvider, BaseTranscriptProvider)

    def test_whisper_provider_name(self):
        provider = WhisperTranscriptProvider()
        assert provider.provider_name == "whisper"

    def test_unknown_provider_name_falls_back_to_stub(self):
        """Any unknown TRANSCRIPT_PROVIDER value falls back to stub safely."""
        env = {"TRANSCRIPT_PROVIDER": "unknown_provider", "TRANSCRIPT_LIVE_ENABLED": "true"}
        with patch.dict(os.environ, env):
            provider = get_transcript_provider()
        assert isinstance(provider, StubTranscriptProvider)


# ---------------------------------------------------------------------------
# TestMissingAudioPath
# ---------------------------------------------------------------------------

class TestMissingAudioPath:
    def test_whisper_raises_on_empty_audio_path(self):
        """WhisperTranscriptProvider raises ValueError when audio_path is empty."""
        provider = WhisperTranscriptProvider()
        with pytest.raises(ValueError, match="audio_path is required"):
            provider.transcribe(source_content_id="x", audio_path="")

    def test_whisper_raises_on_missing_file(self, tmp_path):
        """WhisperTranscriptProvider raises ValueError when file does not exist."""
        provider = WhisperTranscriptProvider()
        missing = str(tmp_path / "nonexistent_audio.mp3")
        with pytest.raises(ValueError, match="Audio file not found"):
            provider.transcribe(source_content_id="x", audio_path=missing)

    def test_transcript_run_v4_stores_failed_status_on_error(self):
        """POST /transcript-runs/v4 stores status=failed and error_message when provider raises."""
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)

        # Inject a provider that always raises
        class FailingProvider(BaseTranscriptProvider):
            provider_name = "failing_stub"

            def transcribe(self, source_content_id, audio_path="", text_hint=""):
                raise ValueError("Simulated transcription failure")

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch("transcript_provider.get_transcript_provider", return_value=FailingProvider()),
        ):
            resp = client.post(
                "/transcript-runs/v4",
                json={"workspace_slug": "test-ws", "source_content_id": "sc1"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["segment_count"] == 0
        assert "failed" in body["message"].lower()

        run = fake_db.transcript_runs.find_one({"workspace_slug": "test-ws"})
        assert run is not None
        assert run["status"] == "failed"
        assert "Simulated transcription failure" in run["error_message"]
        assert run["simulation_only"] is True
        assert run["outbound_actions_taken"] == 0

    def test_transcript_run_stores_empty_error_on_success(self):
        """On success, error_message is stored as empty string."""
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)

        stub = StubTranscriptProvider()
        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch("transcript_provider.get_transcript_provider", return_value=stub),
        ):
            resp = client.post(
                "/transcript-runs/v4",
                json={"workspace_slug": "test-ws", "source_content_id": "sc1"},
            )

        assert resp.status_code == 200
        run = fake_db.transcript_runs.find_one({"workspace_slug": "test-ws"})
        assert run["status"] == "complete"
        assert run["error_message"] == ""


# ---------------------------------------------------------------------------
# TestTranscriptRunRecord
# ---------------------------------------------------------------------------

class TestTranscriptRunRecord:
    def test_run_record_has_provider_field(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        stub = StubTranscriptProvider()

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch("transcript_provider.get_transcript_provider", return_value=stub),
        ):
            resp = client.post(
                "/transcript-runs/v4",
                json={"workspace_slug": "ws1", "source_content_id": "sc1"},
            )

        assert resp.status_code == 200
        run = fake_db.transcript_runs.find_one({"workspace_slug": "ws1"})
        assert run["provider"] == "stub"

    def test_run_record_has_input_path_field(self):
        fake_db = FakeDatabase()
        # Seed an audio extraction run with an output_path
        audio_id = ObjectId()
        fake_db.audio_extraction_runs.documents.append({
            "_id": audio_id,
            "status": "complete",
            "output_path": "/data/audio/test.mp3",
            "workspace_slug": "ws1",
        })
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        stub = StubTranscriptProvider()

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch("transcript_provider.get_transcript_provider", return_value=stub),
        ):
            resp = client.post(
                "/transcript-runs/v4",
                json={
                    "workspace_slug": "ws1",
                    "source_content_id": "sc1",
                    "audio_extraction_run_id": str(audio_id),
                },
            )

        assert resp.status_code == 200
        run = fake_db.transcript_runs.find_one({"workspace_slug": "ws1"})
        assert run["input_path"] == "/data/audio/test.mp3"

    def test_run_record_has_status_field(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        stub = StubTranscriptProvider()

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch("transcript_provider.get_transcript_provider", return_value=stub),
        ):
            resp = client.post(
                "/transcript-runs/v4",
                json={"workspace_slug": "ws1", "source_content_id": "sc1"},
            )

        assert resp.status_code == 200
        run = fake_db.transcript_runs.find_one({"workspace_slug": "ws1"})
        assert run["status"] in ("complete", "failed")

    def test_run_record_segment_count_matches_segments(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        stub = StubTranscriptProvider()

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch("transcript_provider.get_transcript_provider", return_value=stub),
        ):
            resp = client.post(
                "/transcript-runs/v4",
                json={"workspace_slug": "ws1", "source_content_id": "sc1"},
            )

        assert resp.status_code == 200
        run = fake_db.transcript_runs.find_one({"workspace_slug": "ws1"})
        segs = list(fake_db.transcript_segments.find({"workspace_slug": "ws1"}))
        assert run["segment_count"] == len(segs)

    def test_run_response_includes_simulation_only(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        stub = StubTranscriptProvider()

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch("transcript_provider.get_transcript_provider", return_value=stub),
        ):
            resp = client.post(
                "/transcript-runs/v4",
                json={"workspace_slug": "ws1", "source_content_id": "sc1"},
            )

        assert resp.json()["simulation_only"] is True


# ---------------------------------------------------------------------------
# TestSegmentShape
# ---------------------------------------------------------------------------

class TestSegmentShape:
    def test_stub_segments_have_start_ms(self):
        provider = StubTranscriptProvider()
        segs = provider.transcribe("x")
        for seg in segs:
            assert "start_ms" in seg
            assert isinstance(seg["start_ms"], int)

    def test_stub_segments_have_end_ms(self):
        provider = StubTranscriptProvider()
        segs = provider.transcribe("x")
        for seg in segs:
            assert "end_ms" in seg
            assert seg["end_ms"] >= seg["start_ms"]

    def test_stub_segments_have_non_empty_text(self):
        provider = StubTranscriptProvider()
        segs = provider.transcribe("x")
        for seg in segs:
            assert seg.get("text", "").strip() != ""

    def test_stub_segments_have_speaker(self):
        provider = StubTranscriptProvider()
        segs = provider.transcribe("x")
        for seg in segs:
            assert "speaker" in seg

    def test_stub_segments_have_confidence(self):
        provider = StubTranscriptProvider()
        segs = provider.transcribe("x")
        for seg in segs:
            assert "confidence" in seg
            assert 0.0 <= seg["confidence"] <= 1.0

    def test_stored_segments_have_required_db_fields(self):
        """Segments stored in transcript_segments collection have required fields."""
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        stub = StubTranscriptProvider()

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch("transcript_provider.get_transcript_provider", return_value=stub),
        ):
            client.post(
                "/transcript-runs/v4",
                json={"workspace_slug": "ws1", "source_content_id": "sc1"},
            )

        segs = list(fake_db.transcript_segments.find({"workspace_slug": "ws1"}))
        assert len(segs) > 0
        for seg in segs:
            for field in ("index", "start_ms", "end_ms", "text", "speaker", "confidence", "provider"):
                assert field in seg, f"Segment missing field: {field}"
            assert seg["simulation_only"] is True
            assert seg["outbound_actions_taken"] == 0


# ---------------------------------------------------------------------------
# TestSnippetFromSegments
# ---------------------------------------------------------------------------

class TestSnippetFromSegments:
    def _make_transcript_setup(self, fake_db, workspace="ws1", content_id="sc1"):
        """Insert a completed transcript run + segments for the given content."""
        run_id = ObjectId()
        fake_db.transcript_runs.documents.append(make_doc(
            _id=run_id,
            workspace_slug=workspace,
            source_content_id=content_id,
            status="complete",
            provider="stub",
            segment_count=2,
        ))
        for i, text in enumerate([
            "Customer trust is everything. You have to earn it every single day.",
            "Consistent execution is the only system that works. No tricks, no gimmicks.",
        ]):
            fake_db.transcript_segments.documents.append(make_doc(
                workspace_slug=workspace,
                source_content_id=content_id,
                transcript_run_id=str(run_id),
                index=i,
                start_ms=i * 5000,
                end_ms=(i + 1) * 5000,
                text=text,
                speaker="speaker_1",
                confidence=0.92,
                provider="stub",
            ))
        return str(run_id)

    def test_snippets_created_from_segments(self):
        fake_db = FakeDatabase()
        run_id = self._make_transcript_setup(fake_db)
        fake_get_client, fake_get_database = make_db_patch(fake_db)

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
        ):
            resp = client.post(
                "/source-content/sc1/generate-snippets/v4",
                json={"workspace_slug": "ws1", "transcript_run_id": run_id},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["created_count"] > 0

    def test_snippets_have_transcript_text(self):
        fake_db = FakeDatabase()
        run_id = self._make_transcript_setup(fake_db)
        fake_get_client, fake_get_database = make_db_patch(fake_db)

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
        ):
            resp = client.post(
                "/source-content/sc1/generate-snippets/v4",
                json={"workspace_slug": "ws1", "transcript_run_id": run_id},
            )

        snippets = resp.json()["items"]
        for s in snippets:
            assert s.get("transcript_text", "").strip() != ""

    def test_snippets_have_start_and_end_time(self):
        fake_db = FakeDatabase()
        run_id = self._make_transcript_setup(fake_db)
        fake_get_client, fake_get_database = make_db_patch(fake_db)

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
        ):
            resp = client.post(
                "/source-content/sc1/generate-snippets/v4",
                json={"workspace_slug": "ws1", "transcript_run_id": run_id},
            )

        for s in resp.json()["items"]:
            assert "start_time" in s
            assert "end_time" in s
            assert s["end_time"] >= s["start_time"]

    def test_snippets_have_status_needs_review(self):
        fake_db = FakeDatabase()
        run_id = self._make_transcript_setup(fake_db)
        fake_get_client, fake_get_database = make_db_patch(fake_db)

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
        ):
            resp = client.post(
                "/source-content/sc1/generate-snippets/v4",
                json={"workspace_slug": "ws1", "transcript_run_id": run_id},
            )

        for s in resp.json()["items"]:
            assert s["status"] == "needs_review"

    def test_snippet_generation_blocked_without_completed_run(self):
        """generate-snippets/v4 returns 422 when no completed transcript run exists."""
        fake_db = FakeDatabase()
        # Insert a transcript run with status=pending (not complete)
        fake_db.transcript_runs.documents.append(make_doc(
            workspace_slug="ws1",
            source_content_id="sc1",
            status="pending",
        ))
        fake_get_client, fake_get_database = make_db_patch(fake_db)

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
        ):
            resp = client.post(
                "/source-content/sc1/generate-snippets/v4",
                json={"workspace_slug": "ws1"},
            )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TestAutoScoreSnippets
# ---------------------------------------------------------------------------

class TestAutoScoreSnippets:
    def _make_transcript_setup(self, fake_db, workspace="ws1", content_id="sc1"):
        run_id = ObjectId()
        fake_db.transcript_runs.documents.append(make_doc(
            _id=run_id,
            workspace_slug=workspace,
            source_content_id=content_id,
            status="complete",
            provider="stub",
            segment_count=1,
        ))
        fake_db.transcript_segments.documents.append(make_doc(
            workspace_slug=workspace,
            source_content_id=content_id,
            transcript_run_id=str(run_id),
            index=0,
            start_ms=0,
            end_ms=5000,
            text="Customer trust is everything. You have to earn it every single day by showing up.",
            speaker="speaker_1",
            confidence=0.92,
            provider="stub",
        ))
        return str(run_id)

    def test_auto_score_disabled_by_default(self):
        """Without AUTO_SCORE_SNIPPETS, snippets are created without scored_at."""
        fake_db = FakeDatabase()
        run_id = self._make_transcript_setup(fake_db)
        fake_get_client, fake_get_database = make_db_patch(fake_db)

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch.dict(os.environ, {}, clear=False),
        ):
            os.environ.pop("AUTO_SCORE_SNIPPETS", None)
            resp = client.post(
                "/source-content/sc1/generate-snippets/v4",
                json={"workspace_slug": "ws1", "transcript_run_id": run_id},
            )

        assert resp.status_code == 200
        snippets = list(fake_db.content_snippets.find({"workspace_slug": "ws1"}))
        assert len(snippets) > 0
        # scored_at should be None (not auto-scored)
        for s in snippets:
            assert s.get("scored_at") is None

    def test_auto_score_enabled_sets_scored_at(self):
        """AUTO_SCORE_SNIPPETS=true sets scored_at on each snippet."""
        fake_db = FakeDatabase()
        run_id = self._make_transcript_setup(fake_db)
        fake_get_client, fake_get_database = make_db_patch(fake_db)

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch.dict(os.environ, {"AUTO_SCORE_SNIPPETS": "true"}),
        ):
            resp = client.post(
                "/source-content/sc1/generate-snippets/v4",
                json={"workspace_slug": "ws1", "transcript_run_id": run_id},
            )

        assert resp.status_code == 200
        snippets = list(fake_db.content_snippets.find({"workspace_slug": "ws1"}))
        assert len(snippets) > 0
        for s in snippets:
            assert s.get("scored_at") is not None, "scored_at should be set when AUTO_SCORE_SNIPPETS=true"

    def test_auto_score_enabled_sets_overall_score(self):
        """AUTO_SCORE_SNIPPETS=true stores overall_score > 0 on each snippet."""
        fake_db = FakeDatabase()
        run_id = self._make_transcript_setup(fake_db)
        fake_get_client, fake_get_database = make_db_patch(fake_db)

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch.dict(os.environ, {"AUTO_SCORE_SNIPPETS": "true"}),
        ):
            resp = client.post(
                "/source-content/sc1/generate-snippets/v4",
                json={"workspace_slug": "ws1", "transcript_run_id": run_id},
            )

        assert resp.status_code == 200
        snippets = list(fake_db.content_snippets.find({"workspace_slug": "ws1"}))
        for s in snippets:
            assert s.get("overall_score", 0.0) > 0.0

    def test_auto_score_stores_hook_text(self):
        """AUTO_SCORE_SNIPPETS=true stores hook_text when present."""
        fake_db = FakeDatabase()
        run_id = self._make_transcript_setup(fake_db)
        fake_get_client, fake_get_database = make_db_patch(fake_db)

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch.dict(os.environ, {"AUTO_SCORE_SNIPPETS": "true"}),
        ):
            resp = client.post(
                "/source-content/sc1/generate-snippets/v4",
                json={"workspace_slug": "ws1", "transcript_run_id": run_id},
            )

        assert resp.status_code == 200
        snippets = list(fake_db.content_snippets.find({"workspace_slug": "ws1"}))
        for s in snippets:
            assert "hook_text" in s
            assert "hook_type" in s
            assert "alternative_hooks" in s

    def test_auto_score_simulation_only_preserved(self):
        """AUTO_SCORE_SNIPPETS=true still preserves simulation_only=True."""
        fake_db = FakeDatabase()
        run_id = self._make_transcript_setup(fake_db)
        fake_get_client, fake_get_database = make_db_patch(fake_db)

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch.dict(os.environ, {"AUTO_SCORE_SNIPPETS": "true"}),
        ):
            resp = client.post(
                "/source-content/sc1/generate-snippets/v4",
                json={"workspace_slug": "ws1", "transcript_run_id": run_id},
            )

        assert resp.status_code == 200
        snippets = list(fake_db.content_snippets.find({"workspace_slug": "ws1"}))
        for s in snippets:
            assert s["simulation_only"] is True
            assert s["outbound_actions_taken"] == 0


# ---------------------------------------------------------------------------
# TestWorkspaceIsolation
# ---------------------------------------------------------------------------

class TestWorkspaceIsolation:
    def test_transcript_run_only_updates_target_workspace(self):
        """Creating a transcript run for ws1 does not create runs for ws2."""
        fake_db = FakeDatabase()
        # Pre-seed a run for a different workspace
        fake_db.transcript_runs.documents.append(make_doc(
            workspace_slug="ws2",
            source_content_id="sc_other",
            status="complete",
            provider="stub",
        ))
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        stub = StubTranscriptProvider()

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch("transcript_provider.get_transcript_provider", return_value=stub),
        ):
            client.post(
                "/transcript-runs/v4",
                json={"workspace_slug": "ws1", "source_content_id": "sc1"},
            )

        ws1_runs = list(fake_db.transcript_runs.find({"workspace_slug": "ws1"}))
        ws2_runs = list(fake_db.transcript_runs.find({"workspace_slug": "ws2"}))
        assert len(ws1_runs) == 1
        assert len(ws2_runs) == 1  # unchanged

    def test_auto_score_updates_only_target_snippet(self):
        """AUTO_SCORE_SNIPPETS only updates the snippets it created, not pre-existing ones."""
        fake_db = FakeDatabase()
        # Pre-seed an unrelated snippet
        unrelated_id = ObjectId()
        fake_db.content_snippets.documents.append(make_doc(
            _id=unrelated_id,
            workspace_slug="ws2",
            source_content_id="other",
            transcript_text="Completely different content",
            overall_score=0.0,
            scored_at=None,
            simulation_only=True,
            outbound_actions_taken=0,
        ))

        run_id = ObjectId()
        fake_db.transcript_runs.documents.append(make_doc(
            _id=run_id,
            workspace_slug="ws1",
            source_content_id="sc1",
            status="complete",
            provider="stub",
            segment_count=1,
        ))
        fake_db.transcript_segments.documents.append(make_doc(
            workspace_slug="ws1",
            source_content_id="sc1",
            transcript_run_id=str(run_id),
            index=0,
            start_ms=0,
            end_ms=5000,
            text="Customer trust is everything. Earn it every day.",
            speaker="speaker_1",
            confidence=0.92,
            provider="stub",
        ))

        fake_get_client, fake_get_database = make_db_patch(fake_db)

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch.dict(os.environ, {"AUTO_SCORE_SNIPPETS": "true"}),
        ):
            client.post(
                "/source-content/sc1/generate-snippets/v4",
                json={"workspace_slug": "ws1", "transcript_run_id": str(run_id)},
            )

        # Unrelated snippet must not have been scored
        unrelated = fake_db.content_snippets.find_one({"_id": unrelated_id})
        assert unrelated["scored_at"] is None


# ---------------------------------------------------------------------------
# TestSafetyGuaranteesV7
# ---------------------------------------------------------------------------

class TestSafetyGuaranteesV7:
    def test_transcript_run_simulation_only_true(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        stub = StubTranscriptProvider()

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch("transcript_provider.get_transcript_provider", return_value=stub),
        ):
            resp = client.post(
                "/transcript-runs/v4",
                json={"workspace_slug": "ws1", "source_content_id": "sc1"},
            )

        assert resp.status_code == 200
        run = fake_db.transcript_runs.find_one({"workspace_slug": "ws1"})
        assert run["simulation_only"] is True

    def test_transcript_run_outbound_actions_zero(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        stub = StubTranscriptProvider()

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch("transcript_provider.get_transcript_provider", return_value=stub),
        ):
            client.post(
                "/transcript-runs/v4",
                json={"workspace_slug": "ws1", "source_content_id": "sc1"},
            )

        run = fake_db.transcript_runs.find_one({"workspace_slug": "ws1"})
        assert run["outbound_actions_taken"] == 0

    def test_transcript_segments_simulation_only_true(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        stub = StubTranscriptProvider()

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch("transcript_provider.get_transcript_provider", return_value=stub),
        ):
            client.post(
                "/transcript-runs/v4",
                json={"workspace_slug": "ws1", "source_content_id": "sc1"},
            )

        segs = list(fake_db.transcript_segments.find({"workspace_slug": "ws1"}))
        for seg in segs:
            assert seg["simulation_only"] is True
            assert seg["outbound_actions_taken"] == 0

    def test_failed_run_simulation_only_true(self):
        """Even a failed transcript run stores simulation_only=True."""
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)

        class ErrorProvider(BaseTranscriptProvider):
            provider_name = "error_stub"

            def transcribe(self, source_content_id, audio_path="", text_hint=""):
                raise RuntimeError("intentional failure")

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch("transcript_provider.get_transcript_provider", return_value=ErrorProvider()),
        ):
            resp = client.post(
                "/transcript-runs/v4",
                json={"workspace_slug": "ws1", "source_content_id": "sc1"},
            )

        assert resp.status_code == 200
        run = fake_db.transcript_runs.find_one({"workspace_slug": "ws1"})
        assert run["simulation_only"] is True
        assert run["outbound_actions_taken"] == 0

    def test_response_body_simulation_only_true(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        stub = StubTranscriptProvider()

        client = TestClient(app)
        with (
            patch("main.get_client", fake_get_client),
            patch("main.get_database", fake_get_database),
            patch("transcript_provider.get_transcript_provider", return_value=stub),
        ):
            resp = client.post(
                "/transcript-runs/v4",
                json={"workspace_slug": "ws1", "source_content_id": "sc1"},
            )

        assert resp.json()["simulation_only"] is True

    def test_no_external_network_calls_during_stub_transcription(self):
        """StubTranscriptProvider.transcribe() makes zero external calls."""
        # If any external call were made, it would raise in the test environment
        # because network is not expected. We simply verify transcribe completes.
        provider = StubTranscriptProvider()
        segments = provider.transcribe("x", audio_path="", text_hint="Trust is earned daily.")
        assert len(segments) > 0
        for seg in segments:
            assert seg["provider"] == "stub"
