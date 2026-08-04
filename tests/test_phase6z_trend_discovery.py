"""
tests/test_phase6z_trend_discovery.py
Phase 6Z — main.py wiring tests: agent registration, request-model Literal
acceptance, and the SourceContentCreateRequest content-rights/attribution
schema extension (POST /source-content).
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import sys, os, types

# ── Stub heavy optional dependencies ─────────────────────────────────────────
for _mod in [
    "whisper", "yt_dlp", "core.constants", "prompt_generator", "snippet_scorer",
    "agents.base_agent", "agents.content_agent", "agents.fan_engagement_agent",
    "agents.followup_agent", "agents.outreach_agent", "agents.trend_discovery_agent",
    "media_folder_scanner", "approved_url_downloader",
]:
    _parts = _mod.split(".")
    if len(_parts) > 1:
        _parent = types.ModuleType(_parts[0])
        sys.modules.setdefault(_parts[0], _parent)
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

sys.modules["core.constants"].MESSAGE_REVIEW_DECISIONS = []
sys.modules["core.constants"].OPEN_DEAL_OUTCOMES = []
sys.modules["core.constants"].VALID_MODULES = []

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

import main
from main import app

client = TestClient(app, raise_server_exceptions=False)


def _mock_db_6z():
    db = MagicMock()
    db.command.return_value = {"ok": 1}
    db.source_content.insert_one.return_value = MagicMock(inserted_id="fake_id")
    db.source_content.find_one.return_value = None
    db.__getitem__ = MagicMock(side_effect=lambda n: getattr(db, n, MagicMock()))
    return db


def _patch_6z(db):
    mc = MagicMock()
    mc.close = MagicMock()
    return patch.multiple("main", get_client=lambda: mc, get_database=lambda c: db)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Agent registration
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentRegistration6Z:

    def test_trend_discovery_in_agent_classes(self):
        assert "trend_discovery" in main.AGENT_CLASSES

    def test_trend_discovery_task_type_registered(self):
        assert main.AGENT_TASK_TYPES.get("trend_discovery") == "discover_trends"

    def test_agent_run_request_accepts_trend_discovery(self):
        req = main.AgentRunRequest(agent="trend_discovery", module="artist_growth")
        assert req.agent == "trend_discovery"

    def test_agent_task_create_request_accepts_trend_discovery(self):
        req = main.AgentTaskCreateRequest(agent_name="trend_discovery", module="artist_growth")
        assert req.agent_name == "trend_discovery"
        assert req.task_type is None

    def test_agent_task_create_request_accepts_discover_trends_task_type(self):
        req = main.AgentTaskCreateRequest(
            agent_name="trend_discovery", module="artist_growth", task_type="discover_trends"
        )
        assert req.task_type == "discover_trends"

    def test_agent_run_request_rejects_unknown_agent(self):
        with pytest.raises(Exception):
            main.AgentRunRequest(agent="not_a_real_agent", module="artist_growth")


# ══════════════════════════════════════════════════════════════════════════════
# 2. SourceContentCreateRequest — content-rights & attribution schema
# ══════════════════════════════════════════════════════════════════════════════

class TestSourceContentSchema6Z:

    def test_content_rights_defaults_owned_licensed(self):
        req = main.SourceContentCreateRequest(title="Test")
        assert req.content_rights == "owned_licensed"

    def test_attribution_fields_default_empty(self):
        req = main.SourceContentCreateRequest(title="Test")
        assert req.creator_handle == ""
        assert req.creator_platform_url == ""
        assert req.attribution_caption == ""

    def test_third_party_curated_accepted(self):
        req = main.SourceContentCreateRequest(title="Test", content_rights="third_party_curated")
        assert req.content_rights == "third_party_curated"

    def test_invalid_content_rights_rejected(self):
        with pytest.raises(Exception):
            main.SourceContentCreateRequest(title="Test", content_rights="not_a_valid_value")


# ══════════════════════════════════════════════════════════════════════════════
# 3. POST /source-content — persists new fields
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateSourceContentEndpoint6Z:

    def test_creates_with_default_owned_licensed(self):
        db = _mock_db_6z()
        with _patch_6z(db):
            resp = client.post("/source-content", json={
                "workspace_slug": "test-ws",
                "title": "Owned video",
                "source_url": "https://example.com/video",
            })
        assert resp.status_code == 200
        inserted_doc = db.source_content.insert_one.call_args[0][0]
        assert inserted_doc["content_rights"] == "owned_licensed"

    def test_creates_third_party_curated_with_attribution(self):
        db = _mock_db_6z()
        with _patch_6z(db):
            resp = client.post("/source-content", json={
                "workspace_slug": "test-ws",
                "title": "Curated clip",
                "source_url": "https://creator.example.com/clip",
                "content_rights": "third_party_curated",
                "creator_handle": "creator.example.com",
                "creator_platform_url": "https://creator.example.com/clip",
                "attribution_caption": "Content via creator.example.com",
            })
        assert resp.status_code == 200
        inserted_doc = db.source_content.insert_one.call_args[0][0]
        assert inserted_doc["content_rights"] == "third_party_curated"
        assert inserted_doc["creator_handle"] == "creator.example.com"
        assert inserted_doc["attribution_caption"] == "Content via creator.example.com"

    def test_simulation_safety_fields_present(self):
        db = _mock_db_6z()
        with _patch_6z(db):
            resp = client.post("/source-content", json={
                "workspace_slug": "test-ws",
                "title": "Test",
                "source_url": "https://example.com",
            })
        assert resp.status_code == 200
        inserted_doc = db.source_content.insert_one.call_args[0][0]
        assert inserted_doc["simulation_only"] is True
        assert inserted_doc["outbound_actions_taken"] == 0
