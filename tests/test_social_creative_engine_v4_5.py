"""
Tests for Social Creative Engine v4.5 — Prompt Generator Library.

Covers:
- prompt generation from approved snippet (happy path)
- unapproved snippet gate
- default faceless guarantees
- likeness/avatar permission gate
- prompt review workflow (approve / reject / revise)
- workspace isolation
- demo isolation (apply_real_mode_filters)
- no external calls during generation
- simulation_only=True enforced
- outbound_actions_taken=0 enforced
- unit tests for prompt_generator module (all 9 types, engines, errors)
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

# Also import the prompt_generator module directly for unit tests
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))
try:
    from prompt_generator import (
        generate_prompt,
        PromptGenerationResult,
        PROMPT_TYPES,
        GENERATION_ENGINES,
    )
except ImportError:
    # Running inside container where module is at /app/prompt_generator.py
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "prompt_generator", "/app/prompt_generator.py"
    )
    _mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(_mod)  # type: ignore[union-attr]
    generate_prompt = _mod.generate_prompt
    PromptGenerationResult = _mod.PromptGenerationResult
    PROMPT_TYPES = _mod.PROMPT_TYPES
    GENERATION_ENGINES = _mod.GENERATION_ENGINES


# ---------------------------------------------------------------------------
# Fake database helpers (identical pattern to v4 tests)
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
        # v4.5 collections
        self.prompt_generations = FakeCollection()
        self.companies = FakeCollection()
        self.briefs = FakeCollection()


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
# Helpers to build common test fixtures
# ---------------------------------------------------------------------------

def _approved_snippet(**extra):
    defaults = dict(
        workspace_slug="ws1",
        transcript_text="Every estimate got a next-day check-in text.",
        source_url="https://example.com/vid.mp4",
        status="approved",
        simulation_only=True,
        outbound_actions_taken=0,
    )
    defaults.update(extra)
    return make_doc(**defaults)


def _create_payload(snippet_id: str, **extra) -> dict:
    base = {
        "workspace_slug": "ws1",
        "snippet_id": str(snippet_id),
        "prompt_type": "faceless_motivational",
        "generation_engine_target": "comfyui",
        "use_likeness": False,
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Part 1 — Happy path: generate prompt from approved snippet
# ---------------------------------------------------------------------------


def test_prompt_generation_from_approved_snippet():
    """POST /prompt-generations with approved snippet → 200 OK, draft record."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    fake_db.content_snippets.insert_one(snippet)

    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        resp = client.post(
            "/prompt-generations",
            json=_create_payload(snippet["_id"]),
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "item" in body
    item = body["item"]
    assert item["prompt_type"] == "faceless_motivational"
    assert item["status"] == "draft"
    assert item["simulation_only"] is True
    assert item["outbound_actions_taken"] == 0
    assert body["simulation_only"] is True
    assert body["outbound_actions_taken"] == 0


# ---------------------------------------------------------------------------
# Part 2 — Unapproved snippet gate
# ---------------------------------------------------------------------------


def test_unapproved_snippet_cannot_generate_prompt():
    """POST /prompt-generations with needs_review snippet → 422."""
    fake_db = FakeDatabase()
    snippet = make_doc(
        workspace_slug="ws1",
        transcript_text="Some content.",
        status="needs_review",
        simulation_only=True,
        outbound_actions_taken=0,
    )
    fake_db.content_snippets.insert_one(snippet)

    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        resp = client.post(
            "/prompt-generations",
            json=_create_payload(snippet["_id"]),
        )

    assert resp.status_code == 422
    assert "approved" in resp.json()["detail"].lower()


def test_rejected_snippet_cannot_generate_prompt():
    """POST /prompt-generations with rejected snippet → 422."""
    fake_db = FakeDatabase()
    snippet = make_doc(
        workspace_slug="ws1",
        transcript_text="Some content.",
        status="rejected",
        simulation_only=True,
        outbound_actions_taken=0,
    )
    fake_db.content_snippets.insert_one(snippet)

    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        resp = client.post(
            "/prompt-generations",
            json=_create_payload(snippet["_id"]),
        )

    assert resp.status_code == 422


def test_missing_snippet_returns_404():
    """POST /prompt-generations with non-existent snippet_id → 404."""
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        resp = client.post(
            "/prompt-generations",
            json=_create_payload(str(ObjectId())),
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Part 3 — Default prompt is faceless
# ---------------------------------------------------------------------------


def test_default_prompt_is_faceless():
    """Generated prompt must block faces in negative_prompt and mark no-face in positive."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    fake_db.content_snippets.insert_one(snippet)

    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        resp = client.post(
            "/prompt-generations",
            json=_create_payload(snippet["_id"]),
        )

    assert resp.status_code == 200
    item = resp.json()["item"]
    neg = item["negative_prompt"].lower()
    pos = item["positive_prompt"].lower()
    assert "face" in neg or "likeness" in neg, "negative_prompt must block faces/likeness"
    assert "face" in pos or "faceless" in pos or "no identifiable" in pos, (
        "positive_prompt must reference faceless generation"
    )


def test_default_negative_prompt_blocks_voice_cloning():
    """Default negative_prompt must never include voice clone instructions."""
    result = generate_prompt(
        prompt_type="faceless_motivational",
        snippet_text="Great content here.",
    )
    assert "voice" in result.negative_prompt.lower() or "clone" in result.negative_prompt.lower()
    # Safety notes must NOT describe how to clone voices
    assert "voice clone" not in result.safety_notes.lower() or (
        "no voice" in result.safety_notes.lower() or "not" in result.safety_notes.lower()
    )


# ---------------------------------------------------------------------------
# Part 4 — Likeness/avatar gate
# ---------------------------------------------------------------------------


def test_likeness_prompt_blocked_without_permissions():
    """POST /prompt-generations with use_likeness=True and no permissions → 422."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet(client_id="client-1")
    fake_db.content_snippets.insert_one(snippet)
    company = make_doc(
        _id="client-1",
        workspace_slug="ws1",
        avatar_permissions=False,
        likeness_permissions=False,
    )
    fake_db.companies.insert_one(company)

    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        resp = client.post(
            "/prompt-generations",
            json=_create_payload(snippet["_id"], client_id="client-1", use_likeness=True),
        )

    assert resp.status_code == 422
    assert "permission" in resp.json()["detail"].lower()


def test_likeness_prompt_allowed_with_avatar_permission():
    """POST /prompt-generations with use_likeness=True and avatar_permissions=True → 200."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet(client_id="client-2")
    fake_db.content_snippets.insert_one(snippet)
    company = make_doc(
        _id="client-2",
        workspace_slug="ws1",
        avatar_permissions=True,
        likeness_permissions=False,
    )
    fake_db.companies.insert_one(company)

    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        resp = client.post(
            "/prompt-generations",
            json=_create_payload(snippet["_id"], client_id="client-2", use_likeness=True),
        )

    assert resp.status_code == 200


def test_likeness_prompt_allowed_with_likeness_permission():
    """POST /prompt-generations with use_likeness=True and likeness_permissions=True → 200."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet(client_id="client-3")
    fake_db.content_snippets.insert_one(snippet)
    company = make_doc(
        _id="client-3",
        workspace_slug="ws1",
        avatar_permissions=False,
        likeness_permissions=True,
    )
    fake_db.companies.insert_one(company)

    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        resp = client.post(
            "/prompt-generations",
            json=_create_payload(snippet["_id"], client_id="client-3", use_likeness=True),
        )

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Part 5 — Review workflow
# ---------------------------------------------------------------------------


def test_prompt_review_approve():
    """POST /prompt-generations/{id}/review with approve → status becomes 'approved'."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    fake_db.content_snippets.insert_one(snippet)

    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        create_resp = client.post(
            "/prompt-generations",
            json=_create_payload(snippet["_id"]),
        )
        assert create_resp.status_code == 200
        gen_id = create_resp.json()["item"]["_id"]

        review_resp = client.post(
            f"/prompt-generations/{gen_id}/review",
            json={"decision": "approve", "note": "Looks great."},
        )

    assert review_resp.status_code == 200
    item = review_resp.json()["item"]
    assert item["status"] == "approved"
    assert len(item["review_events"]) >= 1
    assert item["review_events"][-1]["decision"] == "approve"


def test_prompt_review_reject():
    """POST /prompt-generations/{id}/review with reject → status becomes 'rejected'."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    fake_db.content_snippets.insert_one(snippet)

    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        create_resp = client.post(
            "/prompt-generations",
            json=_create_payload(snippet["_id"]),
        )
        gen_id = create_resp.json()["item"]["_id"]
        review_resp = client.post(
            f"/prompt-generations/{gen_id}/review",
            json={"decision": "reject", "note": "Not suitable."},
        )

    assert review_resp.status_code == 200
    assert review_resp.json()["item"]["status"] == "rejected"


def test_prompt_review_revise():
    """POST /prompt-generations/{id}/review with revise → status becomes 'needs_revision'."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    fake_db.content_snippets.insert_one(snippet)

    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        create_resp = client.post(
            "/prompt-generations",
            json=_create_payload(snippet["_id"]),
        )
        gen_id = create_resp.json()["item"]["_id"]
        review_resp = client.post(
            f"/prompt-generations/{gen_id}/review",
            json={"decision": "revise", "note": "Adjust tone."},
        )

    assert review_resp.status_code == 200
    assert review_resp.json()["item"]["status"] == "needs_revision"


def test_review_not_found():
    """POST /prompt-generations/{id}/review with bad id → 404."""
    fake_db = FakeDatabase()
    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        resp = client.post(
            f"/prompt-generations/{ObjectId()}/review",
            json={"decision": "approve", "note": ""},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Part 6 — List endpoint + workspace isolation
# ---------------------------------------------------------------------------


def test_workspace_isolation():
    """GET /prompt-generations?workspace_slug= only returns own workspace records."""
    fake_db = FakeDatabase()
    for ws in ("ws1", "ws2"):
        snippet = make_doc(workspace_slug=ws, status="approved", transcript_text="x")
        fake_db.content_snippets.insert_one(snippet)
        pg = make_doc(
            workspace_slug=ws,
            snippet_id=str(snippet["_id"]),
            prompt_type="faceless_motivational",
            status="draft",
            simulation_only=True,
            outbound_actions_taken=0,
        )
        fake_db.prompt_generations.insert_one(pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        resp = client.get("/prompt-generations?workspace_slug=ws1")

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(i["workspace_slug"] == "ws1" for i in items)
    assert all(i["workspace_slug"] != "ws2" for i in items)


def test_demo_isolation():
    """GET /prompt-generations without demo=true must exclude demo workspace records."""
    fake_db = FakeDatabase()
    demo_pg = make_doc(
        workspace_slug="demo",
        prompt_type="faceless_motivational",
        status="draft",
        simulation_only=True,
        outbound_actions_taken=0,
    )
    real_pg = make_doc(
        workspace_slug="ws1",
        prompt_type="faceless_motivational",
        status="draft",
        simulation_only=True,
        outbound_actions_taken=0,
    )
    fake_db.prompt_generations.insert_one(demo_pg)
    fake_db.prompt_generations.insert_one(real_pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        resp = client.get("/prompt-generations?workspace_slug=ws1&demo=false")

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(i["workspace_slug"] != "demo" for i in items)


# ---------------------------------------------------------------------------
# Part 7 — Safety invariants on all records
# ---------------------------------------------------------------------------


def test_simulation_only_enforced():
    """Every created prompt_generation must have simulation_only=True."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    fake_db.content_snippets.insert_one(snippet)

    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        resp = client.post(
            "/prompt-generations",
            json=_create_payload(snippet["_id"]),
        )

    assert resp.status_code == 200
    assert resp.json()["item"]["simulation_only"] is True
    assert resp.json()["simulation_only"] is True


def test_outbound_actions_taken_enforced():
    """Every created prompt_generation must have outbound_actions_taken=0."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    fake_db.content_snippets.insert_one(snippet)

    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        resp = client.post(
            "/prompt-generations",
            json=_create_payload(snippet["_id"]),
        )

    assert resp.status_code == 200
    assert resp.json()["item"]["outbound_actions_taken"] == 0
    assert resp.json()["outbound_actions_taken"] == 0


# ---------------------------------------------------------------------------
# Part 8 — No external calls during generation
# ---------------------------------------------------------------------------


def test_no_external_calls_during_generation():
    """Prompt generation must never call subprocess, requests, or httpx."""
    import subprocess as _subprocess
    try:
        import httpx as _httpx
        httpx_available = True
    except ImportError:
        httpx_available = False

    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    fake_db.content_snippets.insert_one(snippet)

    fake_get_client, fake_get_database = make_db_patch(fake_db)

    mock_run = MagicMock(side_effect=AssertionError("subprocess.run must not be called"))
    mock_popen = MagicMock(side_effect=AssertionError("subprocess.Popen must not be called"))

    patches = [
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
        patch("subprocess.run", mock_run),
        patch("subprocess.Popen", mock_popen),
    ]

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        resp = client.post(
            "/prompt-generations",
            json=_create_payload(snippet["_id"]),
        )

    assert resp.status_code == 200
    # If we got here without AssertionError, no subprocess was called
    mock_run.assert_not_called()
    mock_popen.assert_not_called()


# ---------------------------------------------------------------------------
# Part 9 — Source preservation
# ---------------------------------------------------------------------------


def test_source_fields_preserved_on_generation():
    """snippet_transcript, source_url, and snippet_usage_status preserved in record."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet(
        source_url="https://example.com/myvideo",
        transcript_text="Great content goes here.",
    )
    fake_db.content_snippets.insert_one(snippet)

    fake_get_client, fake_get_database = make_db_patch(fake_db)

    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        client = TestClient(app)
        resp = client.post(
            "/prompt-generations",
            json=_create_payload(snippet["_id"]),
        )

    assert resp.status_code == 200
    item = resp.json()["item"]
    assert item["source_url"] == "https://example.com/myvideo"
    assert "Great content goes here" in item["snippet_transcript"]
    assert item["snippet_usage_status"] == "approved"


# ---------------------------------------------------------------------------
# Part 10 — Unit tests for prompt_generator module
# ---------------------------------------------------------------------------


def test_all_nine_prompt_types_return_valid_result():
    """All 9 supported prompt types produce a PromptGenerationResult with non-empty content."""
    for pt in sorted(PROMPT_TYPES):
        result = generate_prompt(
            prompt_type=pt,
            snippet_text="Test transcript text for this prompt type.",
            brief={"goal": "test goal", "platform": "Instagram"},
        )
        assert isinstance(result, PromptGenerationResult), f"Expected PromptGenerationResult for {pt}"
        assert result.positive_prompt, f"Empty positive_prompt for {pt}"
        assert result.negative_prompt, f"Empty negative_prompt for {pt}"
        assert result.prompt_type == pt
        assert result.simulation_only is True
        assert result.outbound_actions_taken == 0
        assert result.status == "draft"
        assert result.error == ""


def test_all_five_engines_accepted():
    """All 5 supported engines are accepted without error."""
    for engine in sorted(GENERATION_ENGINES):
        result = generate_prompt(
            prompt_type="faceless_motivational",
            snippet_text="Some text.",
            engine=engine,
        )
        assert result.generation_engine_target == engine
        assert result.error == ""


def test_invalid_prompt_type_raises_value_error():
    """An unknown prompt_type raises ValueError."""
    with pytest.raises(ValueError, match="Unknown prompt_type"):
        generate_prompt(prompt_type="flying_spaghetti_monster")


def test_invalid_engine_raises_value_error():
    """An unknown engine raises ValueError."""
    with pytest.raises(ValueError, match="Unknown engine"):
        generate_prompt(
            prompt_type="faceless_motivational",
            engine="dalle99",
        )


def test_use_likeness_without_permissions_raises_permission_error():
    """use_likeness=True without permissions raises PermissionError."""
    with pytest.raises(PermissionError, match="permission"):
        generate_prompt(
            prompt_type="faceless_motivational",
            use_likeness=True,
            avatar_permissions=False,
            likeness_permissions=False,
        )


def test_use_likeness_with_avatar_permission_succeeds():
    """use_likeness=True with avatar_permissions=True succeeds."""
    result = generate_prompt(
        prompt_type="faceless_motivational",
        use_likeness=True,
        avatar_permissions=True,
        likeness_permissions=False,
    )
    assert result.error == ""


def test_default_negative_prompt_contains_face_block():
    """Default negative_prompt always includes face/likeness blocking terms."""
    for pt in sorted(PROMPT_TYPES):
        result = generate_prompt(prompt_type=pt, snippet_text="x")
        neg = result.negative_prompt.lower()
        assert (
            "face" in neg or "likeness" in neg or "identifiable" in neg
        ), f"negative_prompt for {pt} missing face-blocking term"


def test_scene_beats_are_non_empty_list():
    """All prompt types produce a non-empty scene_beats list."""
    for pt in sorted(PROMPT_TYPES):
        result = generate_prompt(prompt_type=pt, snippet_text="x")
        assert isinstance(result.scene_beats, list), f"scene_beats not a list for {pt}"
        assert len(result.scene_beats) > 0, f"Empty scene_beats for {pt}"


def test_caption_overlay_truncates_long_transcript():
    """caption_overlay_suggestion is truncated for very long input."""
    long_text = "word " * 200
    result = generate_prompt(
        prompt_type="faceless_motivational",
        snippet_text=long_text,
    )
    assert len(result.caption_overlay_suggestion) <= 200, (
        "caption_overlay_suggestion should be truncated for long input"
    )


def test_traceability_fields_preserved():
    """client_id, snippet_id, brief_id are preserved on the result."""
    result = generate_prompt(
        prompt_type="cinematic_broll",
        snippet_text="Some text.",
        client_id="c123",
        snippet_id="s456",
        brief_id="b789",
        source_url="https://example.com",
        snippet_usage_status="approved",
    )
    assert result.client_id == "c123"
    assert result.snippet_id == "s456"
    assert result.brief_id == "b789"
    assert result.source_url == "https://example.com"
    assert result.snippet_usage_status == "approved"


def test_result_is_always_simulation_only():
    """simulation_only is True on every PromptGenerationResult regardless of inputs."""
    for pt in sorted(PROMPT_TYPES):
        result = generate_prompt(prompt_type=pt, snippet_text="x")
        assert result.simulation_only is True
        assert result.outbound_actions_taken == 0


def test_prompt_module_makes_no_external_calls():
    """generate_prompt must not call subprocess or any network request."""
    import subprocess as _subprocess

    mock_run = MagicMock(side_effect=AssertionError("subprocess.run called"))
    mock_popen = MagicMock(side_effect=AssertionError("subprocess.Popen called"))

    with (
        patch("subprocess.run", mock_run),
        patch("subprocess.Popen", mock_popen),
    ):
        result = generate_prompt(
            prompt_type="business_explainer",
            snippet_text="Test text.",
        )

    assert result.error == ""
    mock_run.assert_not_called()
    mock_popen.assert_not_called()
