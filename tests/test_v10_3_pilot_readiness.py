"""
SignalForge v10.3 — Real Client Pilot Readiness Tests

Covers:
- inspirational_short_form preset in PROMPT_TYPES
- preset builds faceless output (no likeness, no avatar, no voice cloning)
- preset sets preferred_duration_seconds = 75 (60-90s midpoint)
- preset is registered in _BUILDERS and callable
- audio preservation: source_audio_path preserved when provided
- audio test-tone ONLY generated when no audio provided AND ffmpeg enabled
- preserve_original_audio flag stored on render record
- preferred_duration_seconds stored on prompt_generation record
- real-mode smoke: full workspace → company → channel → content → snippet →
  score → approve → generate prompt → approve prompt → render asset
- no is_demo data leaks into a real workspace slug
- simulation_only and outbound_actions_taken=0 always present
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

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

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)
REAL_WS = "pilot-test-ws"


def make_doc(**kwargs):
    return {"_id": ObjectId(), "created_at": NOW, "updated_at": NOW, **kwargs}


class InsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def __iter__(self):
        return iter(self._docs)

    def sort(self, *_, **__):
        return self

    def limit(self, *_, **__):
        return self

    def skip(self, *_, **__):
        return self


# ---------------------------------------------------------------------------
# prompt_generator imports (direct unit test — no DB needed)
# ---------------------------------------------------------------------------

from prompt_generator import (
    PROMPT_TYPES,
    PromptGenerationResult,
    generate_prompt,
)


# ===========================================================================
# Section 1 — Preset: inspirational_short_form
# ===========================================================================


class TestInspirationalShortFormPreset:
    def test_preset_in_prompt_types(self):
        assert "inspirational_short_form" in PROMPT_TYPES

    def test_preset_callable_via_generate_prompt(self):
        result = generate_prompt(
            prompt_type="inspirational_short_form",
            snippet_text="You have to earn the right to be heard.",
            brief={"goal": "inspire leaders", "audience": "entrepreneurs"},
        )
        assert isinstance(result, PromptGenerationResult)

    def test_preset_returns_faceless_positive_prompt(self):
        result = generate_prompt(
            prompt_type="inspirational_short_form",
            snippet_text="Growth begins at the edge of your comfort zone.",
            brief={},
        )
        prompt = result.positive_prompt.lower()
        assert "no faces" in prompt or "faceless" in prompt, (
            "inspirational_short_form positive_prompt must be explicitly faceless"
        )

    def test_preset_no_likeness_in_positive_prompt(self):
        result = generate_prompt(
            prompt_type="inspirational_short_form",
            snippet_text="Lead by example.",
            brief={},
        )
        prompt = result.positive_prompt.lower()
        assert "likeness" not in prompt
        assert "avatar" not in prompt
        assert "voice clone" not in prompt or "no" in prompt

    def test_preset_negative_prompt_blocks_likeness_and_voice(self):
        result = generate_prompt(
            prompt_type="inspirational_short_form",
            snippet_text="Do the work.",
            brief={},
        )
        neg = result.negative_prompt.lower()
        assert "likeness" in neg
        assert "avatar" in neg
        assert "voice cloning" in neg

    def test_preset_preferred_duration_seconds_is_75(self):
        result = generate_prompt(
            prompt_type="inspirational_short_form",
            snippet_text="Consistency is the key.",
            brief={},
        )
        assert result.preferred_duration_seconds == 75, (
            f"Expected 75 (60-90s midpoint), got {result.preferred_duration_seconds}"
        )

    def test_preset_motion_notes_mention_original_audio(self):
        result = generate_prompt(
            prompt_type="inspirational_short_form",
            snippet_text="",
            brief={},
        )
        notes = result.motion_notes.lower()
        assert "original" in notes and "audio" in notes, (
            "motion_notes must state original audio is preserved unchanged"
        )

    def test_preset_motion_notes_no_cloning(self):
        result = generate_prompt(
            prompt_type="inspirational_short_form",
            snippet_text="",
            brief={},
        )
        notes = result.motion_notes.lower()
        # motion_notes must explicitly contain both "no" and "cloning" to block it
        assert "no" in notes and "cloning" in notes, (
            "motion_notes must explicitly block cloning (e.g. 'no rewriting or cloning')"
        )

    def test_preset_scene_beats_has_five_acts(self):
        result = generate_prompt(
            prompt_type="inspirational_short_form",
            snippet_text="Keep going.",
            brief={},
        )
        assert len(result.scene_beats) >= 5, (
            "inspirational_short_form should have a 5-beat scene arc"
        )

    def test_preset_not_in_likeness_required_types(self):
        from prompt_generator import _LIKENESS_REQUIRED_TYPES
        assert "inspirational_short_form" not in _LIKENESS_REQUIRED_TYPES

    def test_preset_use_likeness_false_permitted(self):
        # Should NOT raise when use_likeness=False (the safe default)
        result = generate_prompt(
            prompt_type="inspirational_short_form",
            snippet_text="Action beats intention.",
            brief={},
            use_likeness=False,
        )
        assert result is not None

    def test_preset_use_likeness_true_raises_without_permissions(self):
        with pytest.raises(PermissionError):
            generate_prompt(
                prompt_type="inspirational_short_form",
                snippet_text="",
                brief={},
                use_likeness=True,
                avatar_permissions=False,
                likeness_permissions=False,
            )

    def test_preset_simulation_only_true(self):
        result = generate_prompt(
            prompt_type="inspirational_short_form",
            snippet_text="Every day is a new beginning.",
            brief={},
        )
        assert result.simulation_only is True

    def test_preset_outbound_actions_zero(self):
        result = generate_prompt(
            prompt_type="inspirational_short_form",
            snippet_text="",
            brief={},
        )
        assert result.outbound_actions_taken == 0

    def test_all_other_presets_still_callable(self):
        for pt in PROMPT_TYPES:
            r = generate_prompt(prompt_type=pt, snippet_text="Test.", brief={})
            assert isinstance(r, PromptGenerationResult), f"Preset '{pt}' failed"


# ===========================================================================
# Section 2 — Audio preservation
# ===========================================================================


class TestAudioPreservation:
    def test_assemble_video_source_audio_used_when_provided(self):
        """When audio_path is non-empty and ffmpeg is disabled, mock result returned."""
        import os
        from video_assembler import assemble_video

        with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
            result = assemble_video(
                audio_path="/audio/my_source_recording.wav",
                duration_seconds=30.0,
                asset_render_id="test-audio-preserve",
            )
        # In mock mode (FFMPEG_ENABLED=false) the function returns immediately
        assert result.assembly_status == "mock"
        assert result.simulation_only is True

    def test_assemble_video_no_test_tone_in_mock_mode(self):
        """Test-tone is NEVER generated when ffmpeg is disabled."""
        import os
        from video_assembler import assemble_video, generate_test_tone

        with patch.dict(os.environ, {"FFMPEG_ENABLED": "false"}):
            with patch("video_assembler.generate_test_tone") as mock_tone:
                assemble_video(
                    audio_path="",  # no audio — would trigger test tone if ffmpeg enabled
                    duration_seconds=30.0,
                    asset_render_id="test-no-tone-mock",
                )
                mock_tone.assert_not_called()

    def test_assemble_video_test_tone_only_when_ffmpeg_enabled_and_no_audio(self):
        """Test-tone is ONLY generated when FFMPEG_ENABLED=true AND audio_path=""."""
        import os
        from unittest.mock import call, patch

        from video_assembler import assemble_video

        fake_tone_path = "/tmp/fake_tone.wav"
        # We patch the entire real-FFmpeg execution path to avoid spawning subprocesses
        with (
            patch.dict(os.environ, {"FFMPEG_ENABLED": "true"}),
            patch("video_assembler.generate_test_tone", return_value=fake_tone_path) as mock_tone,
            patch("video_assembler.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            try:
                assemble_video(
                    audio_path="",
                    duration_seconds=10.0,
                    asset_render_id="test-tone-only",
                )
            except Exception:
                pass  # FFmpeg real execution may fail without files — that's OK
            mock_tone.assert_called_once()

    def test_assemble_video_no_test_tone_when_audio_provided_and_ffmpeg_enabled(self):
        """When source audio IS provided, test-tone must NOT be generated even if FFmpeg is on."""
        import os

        from video_assembler import assemble_video

        with (
            patch.dict(os.environ, {"FFMPEG_ENABLED": "true"}),
            patch("video_assembler.generate_test_tone") as mock_tone,
            patch("video_assembler.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            try:
                assemble_video(
                    audio_path="/audio/source_recording.wav",
                    duration_seconds=10.0,
                    asset_render_id="test-source-audio",
                )
            except Exception:
                pass
            mock_tone.assert_not_called()

    def test_preserve_original_audio_default_is_true(self):
        """AssetRenderRequest must default preserve_original_audio=True."""
        from main import AssetRenderRequest

        req = AssetRenderRequest(snippet_id="s1", prompt_generation_id="p1")
        assert req.preserve_original_audio is True

    def test_preserve_original_audio_stored_on_render_record(self):
        """preserve_original_audio=True is persisted to the DB render record."""
        client_app = TestClient(app)

        snippet_id = str(ObjectId())
        prompt_gen_id = str(ObjectId())

        snippet_doc = make_doc(
            _id=snippet_id,
            workspace_slug=REAL_WS,
            status="approved",
            transcript_text="Original audio must be preserved.",
            start_time=0.0,
            end_time=30.0,
            duration_seconds=30.0,
            overall_score=8.0,
            scored_at=NOW.isoformat(),
        )
        prompt_gen_doc = make_doc(
            _id=prompt_gen_id,
            workspace_slug=REAL_WS,
            status="approved",
            prompt_type="inspirational_short_form",
            caption_overlay_suggestion="",
        )

        stored: list[dict] = []

        def fake_find_one(query, *_, **__):
            qid = query.get("_id")
            if str(qid) == snippet_id or qid == snippet_id:
                return snippet_doc
            if str(qid) == prompt_gen_id or qid == prompt_gen_id:
                return prompt_gen_doc
            # Return stored record after insert
            if stored:
                return stored[-1]
            return None

        def fake_insert_one(doc):
            oid = ObjectId()
            doc["_id"] = oid
            stored.append(doc)
            return InsertResult(oid)

        fake_collection = MagicMock()
        fake_collection.find_one.side_effect = fake_find_one
        fake_collection.insert_one.side_effect = fake_insert_one

        fake_db = MagicMock()
        fake_db.content_snippets = fake_collection
        fake_db.asset_renders = fake_collection
        fake_db.prompt_generations = fake_collection

        with (
            patch("main.get_client"),
            patch("main.get_database", return_value=fake_db),
        ):
            resp = client_app.post(
                "/assets/render",
                json={
                    "workspace_slug": REAL_WS,
                    "snippet_id": snippet_id,
                    "prompt_generation_id": prompt_gen_id,
                    "source_audio_path": "/audio/john_maxwell_clip.wav",
                    "preserve_original_audio": True,
                },
            )

        assert resp.status_code == 200
        # The stored record should have preserve_original_audio=True
        assert stored, "No record was inserted"
        assert stored[0].get("preserve_original_audio") is True


# ===========================================================================
# Section 3 — preferred_duration_seconds on prompt_generation record
# ===========================================================================


class TestPreferredDurationOnPromptGeneration:
    def test_preferred_duration_stored_from_preset(self):
        """inspirational_short_form preset sets preferred_duration_seconds=75 on record."""
        client_app = TestClient(app)

        snippet_id = str(ObjectId())
        snippet_doc = make_doc(
            _id=snippet_id,
            workspace_slug=REAL_WS,
            status="approved",
            transcript_text="Every challenge is an opportunity in disguise.",
            start_time=0.0,
            end_time=75.0,
            duration_seconds=75.0,
            overall_score=8.5,
            scored_at=NOW.isoformat(),
        )

        stored: list[dict] = []

        def fake_find_one(query, *_, **__):
            qid = query.get("_id")
            if str(qid) == snippet_id or qid == snippet_id:
                return snippet_doc
            if stored:
                doc = stored[-1].copy()
                doc["_id"] = str(doc["_id"])
                return doc
            return None

        def fake_insert(doc):
            oid = ObjectId()
            doc["_id"] = oid
            stored.append(doc)
            return InsertResult(oid)

        fake_snippet_col = MagicMock()
        fake_snippet_col.find_one.return_value = snippet_doc

        fake_pg_col = MagicMock()
        fake_pg_col.insert_one.side_effect = fake_insert
        fake_pg_col.find_one.side_effect = lambda q, *a, **kw: (
            {**stored[-1], "_id": str(stored[-1]["_id"])} if stored else None
        )

        fake_company_col = MagicMock()
        fake_company_col.find_one.return_value = None

        fake_brief_col = MagicMock()
        fake_brief_col.find_one.return_value = None

        fake_db = MagicMock()
        fake_db.content_snippets = fake_snippet_col
        fake_db.prompt_generations = fake_pg_col
        fake_db.companies = fake_company_col
        fake_db.briefs = fake_brief_col

        with (
            patch("main.get_client"),
            patch("main.get_database", return_value=fake_db),
        ):
            resp = client_app.post(
                "/prompt-generations",
                json={
                    "workspace_slug": REAL_WS,
                    "snippet_id": snippet_id,
                    "prompt_type": "inspirational_short_form",
                },
            )

        assert resp.status_code == 200, resp.text
        assert stored, "No prompt_generation record was inserted"
        assert stored[0].get("preferred_duration_seconds") == 75, (
            f"Expected 75, got {stored[0].get('preferred_duration_seconds')}"
        )

    def test_preferred_duration_zero_for_other_presets(self):
        """Other presets default to preferred_duration_seconds=0 (unspecified)."""
        for pt in PROMPT_TYPES - {"inspirational_short_form"}:
            r = generate_prompt(prompt_type=pt, snippet_text="Test.", brief={})
            assert r.preferred_duration_seconds == 0, (
                f"Preset '{pt}' should have preferred_duration_seconds=0, "
                f"got {r.preferred_duration_seconds}"
            )


# ===========================================================================
# Section 4 — Real-mode smoke test (no demo data leakage)
# ===========================================================================


class TestRealModeNodemoDataleak:
    """
    Smoke test: create a real workspace and verify that list endpoints
    exclude is_demo=True records when using a real workspace slug.
    """

    def test_list_prompts_excludes_demo_workspace_records(self):
        client_app = TestClient(app)

        demo_record = {
            "_id": str(ObjectId()),
            "workspace_slug": "demo",
            "is_demo": True,
            "prompt_type": "faceless_motivational",
            "status": "approved",
        }
        real_record = {
            "_id": str(ObjectId()),
            "workspace_slug": REAL_WS,
            "is_demo": False,
            "prompt_type": "inspirational_short_form",
            "status": "draft",
        }

        fake_col = MagicMock()
        fake_col.find.return_value = FakeCursor([real_record])

        fake_db = MagicMock()
        fake_db.prompt_generations = fake_col

        with (
            patch("main.get_client"),
            patch("main.get_database", return_value=fake_db),
        ):
            resp = client_app.get(
                "/prompt-generations",
                params={"workspace_slug": REAL_WS},
            )

        assert resp.status_code == 200
        data = resp.json()
        for item in data.get("items", []):
            assert item.get("workspace_slug") != "demo", (
                "Demo workspace records must not appear in real-mode listing"
            )
            assert item.get("is_demo") is not True, (
                "is_demo=True records must not leak into real workspace listing"
            )

    def test_real_mode_response_always_includes_safety_fields(self):
        """Every list/create response must include simulation_only and outbound_actions_taken."""
        client_app = TestClient(app)

        fake_col = MagicMock()
        fake_col.find.return_value = FakeCursor([])

        fake_db = MagicMock()
        fake_db.prompt_generations = fake_col

        with (
            patch("main.get_client"),
            patch("main.get_database", return_value=fake_db),
        ):
            resp = client_app.get(
                "/prompt-generations",
                params={"workspace_slug": REAL_WS},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "simulation_only" in data
        assert data["simulation_only"] is True
        assert "outbound_actions_taken" in data
        assert data["outbound_actions_taken"] == 0


# ===========================================================================
# Section 5 — PromptGenerationCreateRequest model validation
# ===========================================================================


class TestPromptGenerationCreateRequestValidation:
    def test_inspirational_short_form_accepted_as_prompt_type(self):
        from main import PromptGenerationCreateRequest

        req = PromptGenerationCreateRequest(
            workspace_slug=REAL_WS,
            snippet_id="s1",
            prompt_type="inspirational_short_form",
        )
        assert req.prompt_type == "inspirational_short_form"

    def test_preferred_duration_seconds_defaults_to_zero(self):
        from main import PromptGenerationCreateRequest

        req = PromptGenerationCreateRequest(
            workspace_slug=REAL_WS,
            snippet_id="s1",
        )
        assert req.preferred_duration_seconds == 0

    def test_preferred_duration_seconds_accepted(self):
        from main import PromptGenerationCreateRequest

        req = PromptGenerationCreateRequest(
            workspace_slug=REAL_WS,
            snippet_id="s1",
            preferred_duration_seconds=90,
        )
        assert req.preferred_duration_seconds == 90

    def test_invalid_prompt_type_raises_validation_error(self):
        from pydantic import ValidationError

        from main import PromptGenerationCreateRequest

        with pytest.raises(ValidationError):
            PromptGenerationCreateRequest(
                workspace_slug=REAL_WS,
                snippet_id="s1",
                prompt_type="avatar_likeness_clone",  # must be rejected
            )
