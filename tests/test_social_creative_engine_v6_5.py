"""
Tests for Social Creative Engine v6.5 — Snippet Scoring and Hook Optimization

Covers:
- snippet_scorer.score_snippet(): all required fields returned
- Each score dimension stays in [0.0, 10.0]
- overall_score is weighted average of dimensions
- hook_text extracted, hook_type detected, 3 alternatives generated
- Safety invariants: simulation_only=True, outbound_actions_taken=0
- POST /content-snippets/{id}/score → 200, all fields stored, scored_at set
- POST /content-snippets/{id}/score → 404 on missing snippet
- Score gate in POST /prompt-generations:
    - overall_score < threshold + scored_at → 422
    - overall_score >= threshold + scored_at → passes gate
    - no scored_at (unscored) → passes gate (backwards compat)
- GET /content-snippets?min_score= filters by overall_score
- hook_text from snippet flows into prompt scene_beats[0] and caption_overlay_suggestion
- Workspace isolation: scoring updates only the targeted snippet
- All new code paths carry simulation_only=True, outbound_actions_taken=0
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

from snippet_scorer import (
    SCORE_THRESHOLD_DEFAULT,
    SnippetScoreResult,
    score_snippet,
)

# ---------------------------------------------------------------------------
# Shared helpers (same FakeDatabase/FakeCollection/FakeCursor/FakeClient pattern)
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
# TestSnippetScorerBasic
# ---------------------------------------------------------------------------

class TestSnippetScorerBasic:
    def test_returns_snippet_score_result(self):
        result = score_snippet("Every contractor who uses this system books more calls every single week.")
        assert isinstance(result, SnippetScoreResult)

    def test_all_required_fields_present(self):
        result = score_snippet("Real results come from consistent action every day.")
        assert hasattr(result, "hook_strength")
        assert hasattr(result, "clarity_score")
        assert hasattr(result, "emotional_impact")
        assert hasattr(result, "shareability_score")
        assert hasattr(result, "platform_fit_score")
        assert hasattr(result, "overall_score")
        assert hasattr(result, "score_reason")
        assert hasattr(result, "hook_text")
        assert hasattr(result, "hook_type")
        assert hasattr(result, "alternative_hooks")

    def test_empty_text_returns_zeros(self):
        result = score_snippet("")
        assert result.hook_strength == 0.0
        assert result.clarity_score == 0.0
        assert result.overall_score == 0.0

    def test_score_reason_is_string(self):
        result = score_snippet("Never underestimate the power of a simple daily system.")
        assert isinstance(result.score_reason, str)
        assert len(result.score_reason) > 0


# ---------------------------------------------------------------------------
# TestSnippetScorerDimensions
# ---------------------------------------------------------------------------

class TestSnippetScorerDimensions:
    def test_all_dimensions_in_range(self):
        for text in [
            "Every contractor who books calls uses this system consistently.",
            "",
            "Hello world.",
            "What if I told you that the biggest mistake most contractors make is trusting the wrong leads every single week?",
        ]:
            r = score_snippet(text)
            for dim in (r.hook_strength, r.clarity_score, r.emotional_impact,
                        r.shareability_score, r.platform_fit_score, r.overall_score):
                assert 0.0 <= dim <= 10.0, f"Dimension {dim} out of range for: {text!r}"

    def test_overall_score_is_weighted_average(self):
        result = score_snippet("Real results come from consistent daily action.")
        expected = round(
            result.hook_strength * 0.30
            + result.clarity_score * 0.20
            + result.emotional_impact * 0.20
            + result.shareability_score * 0.20
            + result.platform_fit_score * 0.10,
            1,
        )
        assert abs(result.overall_score - expected) < 0.05, (
            f"overall_score {result.overall_score} != weighted avg {expected}"
        )

    def test_overall_score_single_decimal(self):
        result = score_snippet("Never stop building your system every week.")
        # overall_score should be rounded to 1 decimal
        assert result.overall_score == round(result.overall_score, 1)


# ---------------------------------------------------------------------------
# TestSnippetScorerHooks
# ---------------------------------------------------------------------------

class TestSnippetScorerHooks:
    def test_hook_text_extracted(self):
        result = score_snippet("This one strategy changed everything for my business.")
        assert isinstance(result.hook_text, str)

    def test_hook_type_is_valid(self):
        from snippet_scorer import HOOK_TYPES
        result = score_snippet("What if I told you that this secret system doubles your bookings?")
        assert result.hook_type in HOOK_TYPES

    def test_alternative_hooks_count(self):
        result = score_snippet("Real numbers don't lie — I booked 5 calls this week using this simple strategy.")
        assert isinstance(result.alternative_hooks, list)
        assert 2 <= len(result.alternative_hooks) <= 3

    def test_alternative_hooks_are_strings(self):
        result = score_snippet("Every contractor I know who uses this system gets consistent results.")
        for alt in result.alternative_hooks:
            assert isinstance(alt, str)

    def test_hook_type_empty_text(self):
        result = score_snippet("")
        assert result.hook_type in ("", "educational", "story", "bold_statement",
                                    "curiosity", "contrarian", "emotional")


# ---------------------------------------------------------------------------
# TestSnippetScorerSafety
# ---------------------------------------------------------------------------

class TestSnippetScorerSafety:
    def test_simulation_only_true(self):
        result = score_snippet("The biggest mistake contractors make is ignoring follow-up.")
        assert result.simulation_only is True

    def test_outbound_actions_taken_zero(self):
        result = score_snippet("Never give up on your goals every single day.")
        assert result.outbound_actions_taken == 0


# ---------------------------------------------------------------------------
# TestScoreEndpoint
# ---------------------------------------------------------------------------

class TestScoreEndpoint:
    def test_score_endpoint_returns_200(self):
        db = FakeDatabase()
        snippet_id = ObjectId()
        db.content_snippets.documents.append(make_doc(
            _id=snippet_id,
            transcript_text="Every contractor who follows this system books more calls every week.",
            status="approved",
            overall_score=0.0,
            scored_at=None,
            simulation_only=True,
            outbound_actions_taken=0,
        ))
        get_client, get_database = make_db_patch(db)
        with patch.object(main, "get_client", get_client), \
             patch.object(main, "get_database", get_database):
            client = TestClient(app)
            resp = client.post(f"/content-snippets/{snippet_id}/score")
        assert resp.status_code == 200

    def test_score_endpoint_populates_fields(self):
        db = FakeDatabase()
        snippet_id = ObjectId()
        db.content_snippets.documents.append(make_doc(
            _id=snippet_id,
            transcript_text="Real results come from consistent daily action. Never underestimate this.",
            status="approved",
            overall_score=0.0,
            scored_at=None,
            simulation_only=True,
            outbound_actions_taken=0,
        ))
        get_client, get_database = make_db_patch(db)
        with patch.object(main, "get_client", get_client), \
             patch.object(main, "get_database", get_database):
            client = TestClient(app)
            resp = client.post(f"/content-snippets/{snippet_id}/score")
        data = resp.json()
        item = data["item"]
        assert item["scored_at"] is not None
        assert item["overall_score"] >= 0.0
        assert "hook_type" in item
        assert "hook_text" in item
        assert isinstance(item["alternative_hooks"], list)

    def test_score_endpoint_stores_in_db(self):
        db = FakeDatabase()
        snippet_id = ObjectId()
        db.content_snippets.documents.append(make_doc(
            _id=snippet_id,
            transcript_text="The biggest mistake contractors make is giving up too soon.",
            status="approved",
            overall_score=0.0,
            scored_at=None,
            simulation_only=True,
            outbound_actions_taken=0,
        ))
        get_client, get_database = make_db_patch(db)
        with patch.object(main, "get_client", get_client), \
             patch.object(main, "get_database", get_database):
            client = TestClient(app)
            client.post(f"/content-snippets/{snippet_id}/score")
        stored = db.content_snippets.find_one({"_id": snippet_id})
        assert stored is not None
        assert stored.get("scored_at") is not None
        assert stored.get("overall_score", 0.0) >= 0.0

    def test_score_endpoint_simulation_only(self):
        db = FakeDatabase()
        snippet_id = ObjectId()
        db.content_snippets.documents.append(make_doc(
            _id=snippet_id,
            transcript_text="Never stop growing your business every single day.",
            status="approved",
            overall_score=0.0,
            scored_at=None,
            simulation_only=True,
            outbound_actions_taken=0,
        ))
        get_client, get_database = make_db_patch(db)
        with patch.object(main, "get_client", get_client), \
             patch.object(main, "get_database", get_database):
            client = TestClient(app)
            resp = client.post(f"/content-snippets/{snippet_id}/score")
        data = resp.json()
        assert data.get("simulation_only") is True
        assert data.get("outbound_actions_taken") == 0


# ---------------------------------------------------------------------------
# TestScoreEndpointNotFound
# ---------------------------------------------------------------------------

class TestScoreEndpointNotFound:
    def test_missing_snippet_returns_404(self):
        db = FakeDatabase()
        get_client, get_database = make_db_patch(db)
        with patch.object(main, "get_client", get_client), \
             patch.object(main, "get_database", get_database):
            client = TestClient(app)
            resp = client.post(f"/content-snippets/{ObjectId()}/score")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestScoreGateBlocksLow
# ---------------------------------------------------------------------------

class TestScoreGateBlocksLow:
    def test_low_scored_snippet_blocked(self):
        db = FakeDatabase()
        snippet_id = ObjectId()
        db.content_snippets.documents.append(make_doc(
            _id=snippet_id,
            transcript_text="Uh, yeah, so, um, like, I guess...",
            status="approved",
            overall_score=2.0,  # below threshold of 6.0
            scored_at=NOW,
            simulation_only=True,
            outbound_actions_taken=0,
        ))
        get_client, get_database = make_db_patch(db)
        with patch.object(main, "get_client", get_client), \
             patch.object(main, "get_database", get_database), \
             patch.dict(os.environ, {"SNIPPET_SCORE_THRESHOLD": "6.0"}):
            client = TestClient(app)
            resp = client.post("/prompt-generations", json={
                "snippet_id": str(snippet_id),
                "prompt_type": "faceless_motivational",
                "generation_engine_target": "comfyui",
                "workspace_slug": "test-ws",
            })
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        detail_str = detail if isinstance(detail, str) else str(detail)
        assert "threshold" in detail_str.lower() or "score" in detail_str.lower()


# ---------------------------------------------------------------------------
# TestScoreGateAllowsHigh
# ---------------------------------------------------------------------------

class TestScoreGateAllowsHigh:
    def test_high_scored_snippet_passes_gate(self):
        db = FakeDatabase()
        snippet_id = ObjectId()
        db.content_snippets.documents.append(make_doc(
            _id=snippet_id,
            transcript_text="Every contractor who uses this system books more calls every single week.",
            status="approved",
            overall_score=8.0,  # above threshold of 6.0
            scored_at=NOW,
            hook_text="Every contractor who uses this system books more calls.",
            hook_type="bold_statement",
            simulation_only=True,
            outbound_actions_taken=0,
        ))
        get_client, get_database = make_db_patch(db)
        with patch.object(main, "get_client", get_client), \
             patch.object(main, "get_database", get_database), \
             patch.dict(os.environ, {"SNIPPET_SCORE_THRESHOLD": "6.0"}):
            client = TestClient(app)
            resp = client.post("/prompt-generations", json={
                "snippet_id": str(snippet_id),
                "prompt_type": "faceless_motivational",
                "generation_engine_target": "comfyui",
            })
        # Should NOT be blocked by score gate (422 with threshold message)
        if resp.status_code == 422:
            detail = resp.json().get("detail", "")
            detail_str = detail if isinstance(detail, str) else str(detail)
            assert "threshold" not in detail_str.lower(), (
                f"Score gate blocked a high-scored snippet: {detail}"
            )


# ---------------------------------------------------------------------------
# TestScoreGateAllowsUnscored
# ---------------------------------------------------------------------------

class TestScoreGateAllowsUnscored:
    def test_unscored_snippet_passes_gate(self):
        """Backwards compat: snippets without scored_at should still generate prompts."""
        db = FakeDatabase()
        snippet_id = ObjectId()
        db.content_snippets.documents.append(make_doc(
            _id=snippet_id,
            transcript_text="Consistency is the key to growth.",
            status="approved",
            overall_score=0.0,
            scored_at=None,  # never scored — must not be blocked
            simulation_only=True,
            outbound_actions_taken=0,
        ))
        get_client, get_database = make_db_patch(db)
        with patch.object(main, "get_client", get_client), \
             patch.object(main, "get_database", get_database):
            client = TestClient(app)
            resp = client.post("/prompt-generations", json={
                "snippet_id": str(snippet_id),
                "prompt_type": "faceless_motivational",
                "generation_engine_target": "comfyui",
            })
        # Score gate must NOT fire for unscored snippets
        if resp.status_code == 422:
            detail = resp.json().get("detail", "")
            detail_str = detail if isinstance(detail, str) else str(detail)
            assert "threshold" not in detail_str.lower(), (
                f"Score gate incorrectly blocked an unscored snippet: {detail}"
            )


# ---------------------------------------------------------------------------
# TestListSnippetsMinScore
# ---------------------------------------------------------------------------

class TestListSnippetsMinScore:
    def test_min_score_filters_results(self):
        db = FakeDatabase()
        db.content_snippets.documents.extend([
            make_doc(overall_score=3.0, status="approved", workspace_slug="ws1"),
            make_doc(overall_score=7.5, status="approved", workspace_slug="ws1"),
            make_doc(overall_score=8.0, status="approved", workspace_slug="ws1"),
        ])
        get_client, get_database = make_db_patch(db)
        with patch.object(main, "get_client", get_client), \
             patch.object(main, "get_database", get_database):
            client = TestClient(app)
            resp = client.get("/content-snippets?min_score=7.0&workspace_slug=ws1")
        assert resp.status_code == 200
        items = resp.json()["items"]
        for item in items:
            assert item["overall_score"] >= 7.0, f"Item with score {item['overall_score']} below filter"

    def test_zero_min_score_returns_all(self):
        db = FakeDatabase()
        db.content_snippets.documents.extend([
            make_doc(overall_score=2.0, status="approved", workspace_slug="ws2"),
            make_doc(overall_score=9.0, status="approved", workspace_slug="ws2"),
        ])
        get_client, get_database = make_db_patch(db)
        with patch.object(main, "get_client", get_client), \
             patch.object(main, "get_database", get_database):
            client = TestClient(app)
            resp = client.get("/content-snippets?min_score=0&workspace_slug=ws2")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2


# ---------------------------------------------------------------------------
# TestHookEnhancesPrompt
# ---------------------------------------------------------------------------

class TestHookEnhancesPrompt:
    def test_hook_text_in_prompt_result(self):
        from prompt_generator import generate_prompt
        hook = "Every contractor who uses this system books more calls."
        result = generate_prompt(
            prompt_type="faceless_motivational",
            snippet_text="Every contractor who uses this system books more calls every single week.",
            hook_text=hook,
        )
        assert result.hook_text == hook

    def test_hook_text_in_scene_beats(self):
        from prompt_generator import generate_prompt
        hook = "Real results come from consistent action."
        result = generate_prompt(
            prompt_type="faceless_motivational",
            snippet_text="Real results come from consistent daily action every week.",
            hook_text=hook,
        )
        assert len(result.scene_beats) > 0
        assert result.scene_beats[0].startswith("Hook:")

    def test_hook_text_in_caption_overlay(self):
        from prompt_generator import generate_prompt
        hook = "Never underestimate the power of this system."
        result = generate_prompt(
            prompt_type="faceless_motivational",
            snippet_text="Never underestimate the power of a consistent daily system.",
            hook_text=hook,
        )
        assert result.caption_overlay_suggestion == hook

    def test_no_hook_text_unchanged(self):
        from prompt_generator import generate_prompt
        result = generate_prompt(
            prompt_type="faceless_motivational",
            snippet_text="Consistency is what separates top performers.",
            hook_text="",
        )
        assert result.hook_text == ""


# ---------------------------------------------------------------------------
# TestWorkspaceIsolation
# ---------------------------------------------------------------------------

class TestWorkspaceIsolation:
    def test_scoring_updates_only_target_snippet(self):
        db = FakeDatabase()
        target_id = ObjectId()
        other_id = ObjectId()
        db.content_snippets.documents.extend([
            make_doc(_id=target_id, transcript_text="Every contractor books calls with this system.", overall_score=0.0, scored_at=None, simulation_only=True, outbound_actions_taken=0),
            make_doc(_id=other_id, transcript_text="Other snippet text here.", overall_score=0.0, scored_at=None, simulation_only=True, outbound_actions_taken=0),
        ])
        get_client, get_database = make_db_patch(db)
        with patch.object(main, "get_client", get_client), \
             patch.object(main, "get_database", get_database):
            client = TestClient(app)
            client.post(f"/content-snippets/{target_id}/score")
        target = db.content_snippets.find_one({"_id": target_id})
        other = db.content_snippets.find_one({"_id": other_id})
        assert target.get("scored_at") is not None
        assert other.get("scored_at") is None, "Other snippet should not have been scored"


# ---------------------------------------------------------------------------
# TestSafetyGuaranteesV65
# ---------------------------------------------------------------------------

class TestSafetyGuaranteesV65:
    def test_score_endpoint_outbound_zero(self):
        db = FakeDatabase()
        snippet_id = ObjectId()
        db.content_snippets.documents.append(make_doc(
            _id=snippet_id,
            transcript_text="The real secret to consistent bookings every week.",
            status="approved",
            overall_score=0.0,
            scored_at=None,
            simulation_only=True,
            outbound_actions_taken=0,
        ))
        get_client, get_database = make_db_patch(db)
        with patch.object(main, "get_client", get_client), \
             patch.object(main, "get_database", get_database):
            client = TestClient(app)
            resp = client.post(f"/content-snippets/{snippet_id}/score")
        stored = db.content_snippets.find_one({"_id": snippet_id})
        assert stored.get("outbound_actions_taken") == 0
        assert stored.get("simulation_only") is True

    def test_scorer_module_never_calls_external(self):
        """score_snippet must complete without any network calls."""
        import socket
        original_connect = socket.socket.connect

        def no_connect(*args, **kwargs):
            raise AssertionError("score_snippet made a network call!")

        socket.socket.connect = no_connect
        try:
            result = score_snippet("Every contractor books more calls with this system every week.")
            assert isinstance(result, SnippetScoreResult)
        finally:
            socket.socket.connect = original_connect

    def test_snippet_score_threshold_default(self):
        assert SCORE_THRESHOLD_DEFAULT == 6.0
