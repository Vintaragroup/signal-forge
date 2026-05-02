"""
Tests for Social Creative Engine v5 — Asset Rendering.

Covers:
- render blocked if snippet not approved
- render blocked if prompt_generation not approved
- render blocked if snippet missing (404)
- render blocked if prompt_generation missing (404)
- successful mock render (comfyui disabled, ffmpeg disabled)
- asset goes to needs_review status after render
- asset review: approve / reject / revise
- review not found (404)
- review invalid decision (422)
- workspace isolation (GET /assets)
- demo isolation (apply_real_mode_filters)
- simulation_only enforced
- outbound_actions_taken enforced
- no external subprocess calls during render
- prompt_generation_id stored in render record
- snippet_id stored in render record
- add_captions field stored and honoured
- unit tests for video_assembler module
- unit tests for comfyui_client.build_prompt_inputs_from_generation
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

# Import video_assembler directly for unit tests
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))
try:
    from video_assembler import assemble_video, VideoAssemblyResult
except ImportError:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "video_assembler", "/app/video_assembler.py"
    )
    _vmod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(_vmod)  # type: ignore[union-attr]
    assemble_video = _vmod.assemble_video
    VideoAssemblyResult = _vmod.VideoAssemblyResult

# Import comfyui_client directly for unit tests
try:
    sys.path.insert(0, str(Path(__file__).parent.parent / "agents"))
    from comfyui_client import ComfyUIClient
except ImportError:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "comfyui_client", "/app/agents/comfyui_client.py"
    )
    _cmod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(_cmod)  # type: ignore[union-attr]
    ComfyUIClient = _cmod.ComfyUIClient


# ---------------------------------------------------------------------------
# Fake database helpers (identical pattern to v4.5 tests)
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
        # v5 collections
        self.asset_renders = FakeCollection()


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
# Fixture helpers
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


def _approved_prompt_gen(snippet_id, **extra):
    defaults = dict(
        workspace_slug="ws1",
        snippet_id=str(snippet_id),
        prompt_type="faceless_motivational",
        generation_engine_target="comfyui",
        positive_prompt="Cinematic faceless motivational, 9:16 vertical",
        negative_prompt="realistic face, nsfw",
        visual_style="cinematic",
        lighting="dramatic",
        camera_direction="slow push-in",
        status="approved",
        use_likeness=False,
        simulation_only=True,
        outbound_actions_taken=0,
    )
    defaults.update(extra)
    return make_doc(**defaults)


def _render_payload(snippet_id, prompt_gen_id, **extra):
    base = {
        "workspace_slug": "ws1",
        "snippet_id": str(snippet_id),
        "prompt_generation_id": str(prompt_gen_id),
        "asset_type": "video",
        "generation_engine": "comfyui",
        "add_captions": False,
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Part 1 — Gate: snippet must be approved
# ---------------------------------------------------------------------------


def test_render_blocked_if_snippet_not_approved():
    """POST /assets/render with unapproved snippet → 422."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet(status="needs_review")
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))
    assert resp.status_code == 422
    assert "approved" in resp.json()["detail"].lower()


def test_render_blocked_if_snippet_rejected():
    """POST /assets/render with rejected snippet → 422."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet(status="rejected")
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))
    assert resp.status_code == 422


def test_render_blocked_if_snippet_missing():
    """POST /assets/render with non-existent snippet → 404."""
    fake_db = FakeDatabase()
    pg = _approved_prompt_gen(ObjectId())
    fake_db.prompt_generations.insert_one(pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(str(ObjectId()), pg["_id"]))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Part 2 — Gate: prompt_generation must be approved
# ---------------------------------------------------------------------------


def test_render_blocked_if_prompt_not_approved():
    """POST /assets/render with unapproved prompt_generation → 422."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"], status="draft")
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))
    assert resp.status_code == 422
    assert "approved" in resp.json()["detail"].lower()


def test_render_blocked_if_prompt_generation_missing():
    """POST /assets/render with non-existent prompt_generation → 404."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    fake_db.content_snippets.insert_one(snippet)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.post(
            "/assets/render",
            json=_render_payload(snippet["_id"], str(ObjectId())),
        )
    assert resp.status_code == 404


def test_render_blocked_if_prompt_needs_revision():
    """POST /assets/render with needs_revision prompt_generation → 422."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"], status="needs_revision")
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Part 3 — Successful mock render (all gates disabled)
# ---------------------------------------------------------------------------


def test_successful_mock_render_comfyui_disabled():
    """POST /assets/render with COMFYUI_ENABLED=false → 200, mock render, needs_review."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
        patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}),
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))

    assert resp.status_code == 200
    data = resp.json()
    item = data["item"]
    assert item["status"] == "needs_review"
    assert item["comfyui_result"].get("skip_reason") == "comfyui_disabled"


def test_successful_mock_render_ffmpeg_disabled():
    """POST /assets/render with FFMPEG_ENABLED=false → 200, mock assembly result."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
        patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}),
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))

    assert resp.status_code == 200
    item = resp.json()["item"]
    # assembly_result should indicate mock or skip
    assembly = item.get("assembly_result", {})
    assert assembly.get("mock") or assembly.get("skipped") or assembly.get("skip_reason")


def test_render_asset_goes_to_needs_review():
    """After successful render, final status must be needs_review."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
        patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}),
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))

    assert resp.status_code == 200
    assert resp.json()["item"]["status"] == "needs_review"


def test_render_stores_prompt_generation_id():
    """Render record must store the prompt_generation_id for traceability."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
        patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}),
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))

    assert resp.status_code == 200
    assert resp.json()["item"]["prompt_generation_id"] == str(pg["_id"])


def test_render_stores_snippet_id():
    """Render record must store the snippet_id for traceability."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
        patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}),
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))

    assert resp.status_code == 200
    assert resp.json()["item"]["snippet_id"] == str(snippet["_id"])


def test_render_add_captions_field_stored():
    """add_captions field is stored correctly in the render record."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
        patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}),
    ):
        c = TestClient(app)
        resp = c.post(
            "/assets/render",
            json=_render_payload(snippet["_id"], pg["_id"], add_captions=True),
        )

    assert resp.status_code == 200
    assert resp.json()["item"]["add_captions"] is True


# ---------------------------------------------------------------------------
# Part 4 — simulation_only and outbound_actions_taken
# ---------------------------------------------------------------------------


def test_simulation_only_enforced_on_render():
    """simulation_only must be True on every render record."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
        patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}),
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))

    assert resp.status_code == 200
    item = resp.json()["item"]
    assert item["simulation_only"] is True
    assert resp.json()["simulation_only"] is True


def test_outbound_actions_taken_enforced_on_render():
    """outbound_actions_taken must be 0 on every render record."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
        patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}),
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))

    assert resp.status_code == 200
    item = resp.json()["item"]
    assert item["outbound_actions_taken"] == 0
    assert resp.json()["outbound_actions_taken"] == 0


# ---------------------------------------------------------------------------
# Part 5 — No external subprocess calls during render (COMFYUI+FFMPEG disabled)
# ---------------------------------------------------------------------------


def test_no_subprocess_calls_when_gates_disabled():
    """With COMFYUI_ENABLED=false and FFMPEG_ENABLED=false, subprocess must not be called."""
    fake_db = FakeDatabase()
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
        patch.dict(os.environ, {"COMFYUI_ENABLED": "false", "FFMPEG_ENABLED": "false"}),
        patch("subprocess.run") as mock_run,
        patch("subprocess.Popen") as mock_popen,
    ):
        c = TestClient(app)
        resp = c.post("/assets/render", json=_render_payload(snippet["_id"], pg["_id"]))

    assert resp.status_code == 200
    mock_run.assert_not_called()
    mock_popen.assert_not_called()


# ---------------------------------------------------------------------------
# Part 6 — Asset review workflow
# ---------------------------------------------------------------------------


def _create_render_record(fake_db, status="needs_review"):
    snippet = _approved_snippet()
    pg = _approved_prompt_gen(snippet["_id"])
    fake_db.content_snippets.insert_one(snippet)
    fake_db.prompt_generations.insert_one(pg)

    render = make_doc(
        workspace_slug="ws1",
        snippet_id=str(snippet["_id"]),
        prompt_generation_id=str(pg["_id"]),
        asset_type="video",
        status=status,
        review_events=[],
        simulation_only=True,
        outbound_actions_taken=0,
    )
    fake_db.asset_renders.insert_one(render)
    return render


def test_asset_review_approve():
    """POST /assets/{id}/review with decision=approve → status=approved."""
    fake_db = FakeDatabase()
    render = _create_render_record(fake_db)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.post(
            f"/assets/{render['_id']}/review",
            json={"decision": "approve", "note": "Looks good."},
        )

    assert resp.status_code == 200
    assert resp.json()["item"]["status"] == "approved"


def test_asset_review_reject():
    """POST /assets/{id}/review with decision=reject → status=rejected."""
    fake_db = FakeDatabase()
    render = _create_render_record(fake_db)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.post(
            f"/assets/{render['_id']}/review",
            json={"decision": "reject", "note": "Not suitable."},
        )

    assert resp.status_code == 200
    assert resp.json()["item"]["status"] == "rejected"


def test_asset_review_revise():
    """POST /assets/{id}/review with decision=revise → status=needs_revision."""
    fake_db = FakeDatabase()
    render = _create_render_record(fake_db)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.post(
            f"/assets/{render['_id']}/review",
            json={"decision": "revise", "note": "Needs tweaks."},
        )

    assert resp.status_code == 200
    assert resp.json()["item"]["status"] == "needs_revision"


def test_asset_review_invalid_decision():
    """POST /assets/{id}/review with invalid decision → 422."""
    fake_db = FakeDatabase()
    render = _create_render_record(fake_db)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.post(
            f"/assets/{render['_id']}/review",
            json={"decision": "publish"},  # invalid
        )

    assert resp.status_code == 422


def test_asset_review_not_found():
    """POST /assets/{id}/review with unknown id → 404."""
    fake_db = FakeDatabase()

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.post(
            f"/assets/{ObjectId()}/review",
            json={"decision": "approve"},
        )

    assert resp.status_code == 404


def test_asset_review_event_recorded():
    """Review event must be appended to review_events list."""
    fake_db = FakeDatabase()
    render = _create_render_record(fake_db)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.post(
            f"/assets/{render['_id']}/review",
            json={"decision": "approve", "note": "Great!"},
        )

    assert resp.status_code == 200
    events = resp.json()["item"]["review_events"]
    assert len(events) == 1
    assert events[0]["decision"] == "approve"


def test_review_simulation_only_enforced():
    """Review response must carry simulation_only=True."""
    fake_db = FakeDatabase()
    render = _create_render_record(fake_db)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.post(
            f"/assets/{render['_id']}/review",
            json={"decision": "approve"},
        )

    assert resp.status_code == 200
    assert resp.json()["simulation_only"] is True
    assert resp.json()["outbound_actions_taken"] == 0


# ---------------------------------------------------------------------------
# Part 7 — GET /assets: workspace isolation and demo isolation
# ---------------------------------------------------------------------------


def test_workspace_isolation():
    """GET /assets only returns records matching the workspace_slug."""
    fake_db = FakeDatabase()
    render_ws1 = make_doc(workspace_slug="ws1", status="needs_review", simulation_only=True, outbound_actions_taken=0)
    render_ws2 = make_doc(workspace_slug="ws2", status="needs_review", simulation_only=True, outbound_actions_taken=0)
    fake_db.asset_renders.insert_one(render_ws1)
    fake_db.asset_renders.insert_one(render_ws2)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.get("/assets?workspace_slug=ws1")

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["workspace_slug"] == "ws1"


def test_demo_isolation():
    """GET /assets with workspace_slug set excludes demo records."""
    fake_db = FakeDatabase()
    real_render = make_doc(workspace_slug="ws1", status="needs_review", simulation_only=True, outbound_actions_taken=0)
    demo_render = make_doc(workspace_slug="demo", status="needs_review", is_demo=True, simulation_only=True, outbound_actions_taken=0)
    fake_db.asset_renders.insert_one(real_render)
    fake_db.asset_renders.insert_one(demo_render)

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.get("/assets?workspace_slug=ws1")

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(i.get("workspace_slug") == "ws1" for i in items)
    assert not any(i.get("is_demo") for i in items)


def test_list_assets_returns_simulation_only_flag():
    """GET /assets response body must include simulation_only=True."""
    fake_db = FakeDatabase()

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.get("/assets?workspace_slug=ws1")

    assert resp.status_code == 200
    assert resp.json()["simulation_only"] is True


def test_list_assets_filter_by_status():
    """GET /assets?status=approved returns only approved renders."""
    fake_db = FakeDatabase()
    fake_db.asset_renders.insert_one(make_doc(workspace_slug="ws1", status="approved", simulation_only=True, outbound_actions_taken=0))
    fake_db.asset_renders.insert_one(make_doc(workspace_slug="ws1", status="needs_review", simulation_only=True, outbound_actions_taken=0))

    fake_get_client, fake_get_database = make_db_patch(fake_db)
    with (
        patch("main.get_client", fake_get_client),
        patch("main.get_database", fake_get_database),
    ):
        c = TestClient(app)
        resp = c.get("/assets?workspace_slug=ws1&status=approved")

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "approved"


# ---------------------------------------------------------------------------
# Part 8 — Unit tests for video_assembler module
# ---------------------------------------------------------------------------


def test_ffmpeg_disabled_returns_mock_result():
    """assemble_video with FFMPEG_ENABLED=false returns mock VideoAssemblyResult."""
    with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
        result = assemble_video(
            image_path="/tmp/test.png",
            audio_path="/tmp/test.mp3",
            duration_seconds=30.0,
            generation_engine="comfyui",
        )
    assert result.mock is True
    assert result.skip_reason == "ffmpeg_disabled"
    assert result.ffmpeg_enabled is False
    assert result.file_path != ""


def test_video_assembler_makes_no_subprocess_calls_when_disabled():
    """With FFMPEG_ENABLED=false, subprocess.run must not be called."""
    with (
        patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}),
        patch("subprocess.run") as mock_run,
        patch("subprocess.Popen") as mock_popen,
    ):
        result = assemble_video(
            image_path="/tmp/test.png",
            audio_path="/tmp/test.mp3",
            duration_seconds=30.0,
        )
    assert result.mock is True
    mock_run.assert_not_called()
    mock_popen.assert_not_called()


def test_assembly_result_is_simulation_only():
    """VideoAssemblyResult always has simulation_only=True and outbound_actions_taken=0."""
    with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
        result = assemble_video(duration_seconds=15.0)
    assert result.simulation_only is True
    assert result.outbound_actions_taken == 0


def test_assembly_result_to_dict():
    """VideoAssemblyResult.to_dict() returns a plain dict with all expected keys."""
    with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
        result = assemble_video(duration_seconds=20.0, resolution="1080x1920")
    d = result.to_dict()
    assert isinstance(d, dict)
    for key in ("file_path", "duration_seconds", "resolution", "has_captions",
                 "mock", "skip_reason", "simulation_only", "outbound_actions_taken"):
        assert key in d, f"Missing key: {key}"


def test_assembly_respects_resolution():
    """assemble_video passes resolution through to the result."""
    with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
        result = assemble_video(resolution="720x1280")
    assert result.resolution == "720x1280"


def test_assembly_add_captions_stored():
    """add_captions=True is reflected in VideoAssemblyResult.has_captions."""
    with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
        result = assemble_video(add_captions=True, caption_text="Test caption")
    assert result.has_captions is True


# ---------------------------------------------------------------------------
# Part 9 — Unit tests for comfyui_client.build_prompt_inputs_from_generation
# ---------------------------------------------------------------------------


def test_build_prompt_inputs_basic():
    """build_prompt_inputs_from_generation maps positive and negative prompts."""
    client_obj = ComfyUIClient(base_url="http://localhost:8188")
    pg = {
        "_id": ObjectId(),
        "positive_prompt": "Cinematic faceless motivational, 9:16 vertical",
        "negative_prompt": "realistic face, nsfw",
        "visual_style": "",
        "lighting": "",
        "camera_direction": "",
    }
    inputs = client_obj.build_prompt_inputs_from_generation(pg)
    assert "6" in inputs
    assert "7" in inputs
    assert inputs["6"]["text"] == pg["positive_prompt"]
    assert inputs["7"]["text"] == pg["negative_prompt"]


def test_build_prompt_inputs_appends_style():
    """Style, lighting, and camera_direction are appended to the positive prompt."""
    client_obj = ComfyUIClient(base_url="http://localhost:8188")
    pg = {
        "positive_prompt": "Base positive",
        "negative_prompt": "Base negative",
        "visual_style": "cinematic",
        "lighting": "dramatic",
        "camera_direction": "slow push-in",
    }
    inputs = client_obj.build_prompt_inputs_from_generation(pg)
    positive = inputs["6"]["text"]
    assert "cinematic" in positive
    assert "dramatic" in positive
    assert "slow push-in" in positive
    assert positive.startswith("Base positive")


def test_build_prompt_inputs_no_external_calls():
    """build_prompt_inputs_from_generation must make no HTTP calls."""
    client_obj = ComfyUIClient(base_url="http://localhost:8188")
    pg = {
        "positive_prompt": "Test",
        "negative_prompt": "Test neg",
        "visual_style": "",
        "lighting": "",
        "camera_direction": "",
    }
    with patch("urllib.request.urlopen") as mock_urlopen:
        inputs = client_obj.build_prompt_inputs_from_generation(pg)
    mock_urlopen.assert_not_called()
    assert "6" in inputs


def test_run_from_prompt_generation_stores_traceability():
    """run_from_prompt_generation result includes prompt_generation_id and engine_notes."""
    client_obj = ComfyUIClient(base_url="http://localhost:8188")
    gen_id = ObjectId()
    pg = {
        "_id": gen_id,
        "positive_prompt": "Test prompt",
        "negative_prompt": "Test negative",
        "visual_style": "cinematic",
        "lighting": "",
        "camera_direction": "",
        "motion_notes": "smooth fade",
        "caption_overlay_suggestion": "Great caption",
    }

    mock_response = MagicMock()
    mock_response.__enter__ = MagicMock(
        return_value=MagicMock(
            read=MagicMock(return_value=b'{"prompt_id": "abc123", "number": 1, "node_errors": {}}')
        )
    )
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = client_obj.run_from_prompt_generation(pg)

    assert result["prompt_generation_id"] == str(gen_id)
    assert result["engine_notes"] == "smooth fade"
    assert result["caption_overlay_suggestion"] == "Great caption"
    assert result["simulation_only"] is True
    assert result["outbound_actions_taken"] == 0
