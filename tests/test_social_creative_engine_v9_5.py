"""
Tests for Social Creative Engine v9.5 — Client Intelligence Layer

Covers:
- Generate client intelligence (201)
- simulation_only=True, advisory_only=True, outbound_actions_taken=0 on all records
- Missing client returns 404
- Invalid client_id returns 422 (from find_client_profile ObjectId conversion)
- Deterministic ROI formula: avg_score × count × 12.5
- ROI = 0.0 when no performance records
- content_performance_score in generated record
- insights present when performance records exist
- Recommendations always present
- Empty performance data: safe (no crash, zero scores)
- Top performers ranked by avg score (hook types, prompt types, platforms)
- List intelligence: 200, workspace-filtered, client-filtered
- Get intelligence by client_id: 200, 404
- Generate lead-content correlations: 201
- Correlation strength levels: strong / moderate / weak
- Correlation requires client to exist (404)
- Workspace isolation
- Client isolation
- PATCH /client-profiles/{client_id}/intelligence
- PATCH /campaign-packs/{pack_id}/link
- PATCH /asset-performance-records/{record_id}/intelligence
- Safety: no external API calls during generation
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import main
from main import app

sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))

# ---------------------------------------------------------------------------
# Shared helpers
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

    def update_one(self, query, update, upsert=False):
        for doc in self.documents:
            if self._matches(doc, query):
                for key, value in (update.get("$set") or {}).items():
                    doc[key] = value
                return
        if upsert:
            new_doc = {"_id": ObjectId()}
            for key, value in (update.get("$set") or {}).items():
                new_doc[key] = value
            self.documents.append(new_doc)

    def count_documents(self, query):
        return len([d for d in self.documents if self._matches(d, query)])

    def aggregate(self, pipeline):
        return FakeCursor(self.documents)

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
        self.manual_publish_logs = FakeCollection()
        self.asset_performance_records = FakeCollection()
        self.creative_performance_summaries = FakeCollection()
        # v8 collections
        self.campaign_packs = FakeCollection()
        self.campaign_pack_items = FakeCollection()
        self.campaign_reports = FakeCollection()
        # v8.5 collections
        self.campaign_exports = FakeCollection()
        # v9.5 collections
        self.client_intelligence_records = FakeCollection()
        self.lead_content_correlations = FakeCollection()


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
# Constants
# ---------------------------------------------------------------------------

WS = "test-workspace"
WS_OTHER = "other-workspace"


def _setup_client(client_obj, fake_db, workspace=WS):
    """Create a client profile and return its ID."""
    resp = client_obj.post(
        "/client-profiles",
        json={
            "workspace_slug": workspace,
            "client_name": "Test Client",
            "brand_name": "Test Brand",
        },
    )
    assert resp.status_code < 300, resp.text
    return resp.json()["item"]["_id"]


def _add_perf_record(fake_db, client_id, workspace=WS, perf_score=6.0, **kwargs):
    """Insert a fake performance record with a known score."""
    doc = make_doc(
        workspace_slug=workspace,
        client_id=client_id,
        performance_score=perf_score,
        platform=kwargs.get("platform", "instagram"),
        hook_type=kwargs.get("hook_type", "question"),
        prompt_type=kwargs.get("prompt_type", "educational"),
        content_theme=kwargs.get("content_theme", "fitness"),
    )
    fake_db.asset_performance_records.documents.append(doc)
    return doc


# ---------------------------------------------------------------------------
# TestClientIntelligenceGenerate
# ---------------------------------------------------------------------------

class TestClientIntelligenceGenerate:
    def test_generate_returns_201(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            resp = c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
        assert resp.status_code == 201

    def test_generate_simulation_only(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            resp = c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
        data = resp.json()
        assert data["simulation_only"] is True
        assert data["item"]["simulation_only"] is True

    def test_generate_advisory_only(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            resp = c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
        data = resp.json()
        assert data["advisory_only"] is True
        assert data["item"]["advisory_only"] is True

    def test_generate_outbound_zero(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            resp = c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
        data = resp.json()
        assert data["outbound_actions_taken"] == 0
        assert data["item"]["outbound_actions_taken"] == 0

    def test_generate_message_confirms_no_external(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            resp = c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
        assert "no external" in resp.json()["message"].lower()

    def test_generate_contains_insights(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            _add_perf_record(fake_db, client_id)
            resp = c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
        item = resp.json()["item"]
        assert isinstance(item["insights"], list)
        assert len(item["insights"]) > 0

    def test_generate_contains_recommendations(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            resp = c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
        item = resp.json()["item"]
        assert isinstance(item["recommendations"], list)
        assert len(item["recommendations"]) > 0

    def test_generate_has_content_performance_score(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            _add_perf_record(fake_db, client_id, perf_score=7.5)
            resp = c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
        item = resp.json()["item"]
        assert "content_performance_score" in item
        assert item["content_performance_score"] >= 0.0


# ---------------------------------------------------------------------------
# TestClientIntelligenceRequirements
# ---------------------------------------------------------------------------

class TestClientIntelligenceRequirements:
    def test_missing_client_returns_404(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        missing_id = str(ObjectId())
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.post(f"/client-intelligence/{missing_id}/generate", json={"workspace_slug": WS})
        assert resp.status_code == 404

    def test_invalid_client_id_returns_422(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.post("/client-intelligence/not-an-objectid/generate", json={"workspace_slug": WS})
        assert resp.status_code in (422, 404)  # invalid ObjectId → error

    def test_wrong_workspace_returns_422(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db, workspace=WS)
            resp = c.post(
                f"/client-intelligence/{client_id}/generate",
                json={"workspace_slug": WS_OTHER},
            )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TestClientIntelligenceROI
# ---------------------------------------------------------------------------

class TestClientIntelligenceROI:
    def test_roi_zero_when_no_performance_records(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            resp = c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
        item = resp.json()["item"]
        assert item["estimated_roi"] == 0.0

    def test_roi_deterministic_formula(self):
        """avg_score × count × 12.5"""
        from client_intelligence import calculate_estimated_roi
        records = [{"performance_score": 4.0}, {"performance_score": 6.0}]
        # avg = 5.0, count = 2, ROI = 5.0 * 2 * 12.5 = 125.0
        assert calculate_estimated_roi(records) == 125.0

    def test_roi_single_record(self):
        from client_intelligence import calculate_estimated_roi
        records = [{"performance_score": 8.0}]
        # avg = 8.0, count = 1, ROI = 8.0 * 1 * 12.5 = 100.0
        assert calculate_estimated_roi(records) == 100.0

    def test_roi_empty_list_returns_zero(self):
        from client_intelligence import calculate_estimated_roi
        assert calculate_estimated_roi([]) == 0.0


# ---------------------------------------------------------------------------
# TestClientIntelligenceTopPerformers
# ---------------------------------------------------------------------------

class TestClientIntelligenceTopPerformers:
    def test_top_hook_types_ranked_by_avg_score(self):
        from client_intelligence import identify_top_performers
        records = [
            {"hook_type": "question", "performance_score": 8.0, "platform": "", "prompt_type": ""},
            {"hook_type": "question", "performance_score": 7.0, "platform": "", "prompt_type": ""},
            {"hook_type": "statement", "performance_score": 3.0, "platform": "", "prompt_type": ""},
        ]
        result = identify_top_performers(records, [], [])
        assert result["top_hook_types"][0] == "question"

    def test_top_prompt_types_ranked_by_avg_score(self):
        from client_intelligence import identify_top_performers
        records = [
            {"prompt_type": "educational", "performance_score": 9.0, "platform": "", "hook_type": ""},
            {"prompt_type": "motivational", "performance_score": 3.0, "platform": "", "hook_type": ""},
        ]
        result = identify_top_performers(records, [], [])
        assert result["top_prompt_types"][0] == "educational"

    def test_best_platforms_ranked_by_avg_score(self):
        from client_intelligence import identify_top_performers
        records = [
            {"platform": "tiktok", "performance_score": 9.5, "hook_type": "", "prompt_type": ""},
            {"platform": "facebook", "performance_score": 2.0, "hook_type": "", "prompt_type": ""},
        ]
        result = identify_top_performers(records, [], [])
        assert result["best_platforms"][0] == "tiktok"

    def test_top_snippet_ids_from_snippets(self):
        from client_intelligence import identify_top_performers
        snip_id = ObjectId()
        snippets = [
            {"_id": snip_id, "overall_score": 9.0, "workspace_slug": WS},
            {"_id": ObjectId(), "overall_score": 1.0, "workspace_slug": WS},
        ]
        result = identify_top_performers([], snippets, [])
        assert str(snip_id) in result["top_snippet_ids"]

    def test_empty_records_returns_empty_lists(self):
        from client_intelligence import identify_top_performers
        result = identify_top_performers([], [], [])
        assert result["top_hook_types"] == []
        assert result["top_prompt_types"] == []
        assert result["best_platforms"] == []


# ---------------------------------------------------------------------------
# TestClientIntelligenceEmpty
# ---------------------------------------------------------------------------

class TestClientIntelligenceEmpty:
    def test_empty_perf_data_no_crash(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            resp = c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
        assert resp.status_code == 201

    def test_empty_perf_data_zero_scores(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            resp = c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
        item = resp.json()["item"]
        assert item["content_performance_score"] == 0.0
        assert item["estimated_roi"] == 0.0


# ---------------------------------------------------------------------------
# TestClientIntelligenceList
# ---------------------------------------------------------------------------

class TestClientIntelligenceList:
    def test_list_returns_200(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.get("/client-intelligence")
        assert resp.status_code == 200

    def test_list_returns_items(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
            resp = c.get("/client-intelligence")
        assert len(resp.json()["items"]) >= 1

    def test_list_workspace_filter(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
            resp = c.get(f"/client-intelligence?workspace_slug={WS_OTHER}")
        assert len(resp.json()["items"]) == 0

    def test_list_client_filter(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
            resp = c.get(f"/client-intelligence?client_id={client_id}")
        assert len(resp.json()["items"]) >= 1

    def test_list_simulation_only_field(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.get("/client-intelligence")
        data = resp.json()
        assert data["simulation_only"] is True
        assert data["advisory_only"] is True
        assert data["outbound_actions_taken"] == 0


# ---------------------------------------------------------------------------
# TestClientIntelligenceDetail
# ---------------------------------------------------------------------------

class TestClientIntelligenceDetail:
    def test_get_by_client_id_returns_200(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
            resp = c.get(f"/client-intelligence/{client_id}")
        assert resp.status_code == 200

    def test_get_by_client_id_returns_item(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
            resp = c.get(f"/client-intelligence/{client_id}")
        assert resp.json()["item"]["client_id"] == client_id

    def test_get_not_found_returns_404(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        missing = str(ObjectId())
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.get(f"/client-intelligence/{missing}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestLeadContentCorrelations
# ---------------------------------------------------------------------------

class TestLeadContentCorrelations:
    def test_generate_correlations_returns_201(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            _add_perf_record(fake_db, client_id)
            resp = c.post("/lead-content-correlations/generate", json={
                "workspace_slug": WS,
                "client_id": client_id,
                "lead_id": str(ObjectId()),
            })
        assert resp.status_code == 201

    def test_generate_correlations_simulation_only(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            _add_perf_record(fake_db, client_id)
            resp = c.post("/lead-content-correlations/generate", json={
                "workspace_slug": WS,
                "client_id": client_id,
            })
        data = resp.json()
        assert data["simulation_only"] is True
        assert data["advisory_only"] is True
        assert data["outbound_actions_taken"] == 0

    def test_generate_correlations_missing_client_404(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.post("/lead-content-correlations/generate", json={
                "workspace_slug": WS,
                "client_id": str(ObjectId()),
            })
        assert resp.status_code == 404

    def test_generate_correlations_missing_client_id_422(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.post("/lead-content-correlations/generate", json={
                "workspace_slug": WS,
                "client_id": "",
            })
        assert resp.status_code == 422

    def test_correlation_strength_strong(self):
        from client_intelligence import correlate_lead_to_content_patterns
        from unittest.mock import MagicMock
        fake_db = FakeDatabase()
        client_id = str(ObjectId())
        fake_db.asset_performance_records.documents.append(
            make_doc(client_id=client_id, performance_score=8.0, content_theme="fitness",
                     hook_type="question", prompt_type="educational", platform="instagram")
        )
        correlations = correlate_lead_to_content_patterns(fake_db, WS, "lead123", client_id)
        assert any(c["correlation_strength"] == "strong" for c in correlations)

    def test_correlation_strength_moderate(self):
        from client_intelligence import correlate_lead_to_content_patterns
        fake_db = FakeDatabase()
        client_id = str(ObjectId())
        fake_db.asset_performance_records.documents.append(
            make_doc(client_id=client_id, performance_score=4.0, content_theme="nutrition",
                     hook_type="story", prompt_type="motivational", platform="tiktok")
        )
        correlations = correlate_lead_to_content_patterns(fake_db, WS, "lead456", client_id)
        assert any(c["correlation_strength"] == "moderate" for c in correlations)

    def test_correlation_strength_weak(self):
        from client_intelligence import correlate_lead_to_content_patterns
        fake_db = FakeDatabase()
        client_id = str(ObjectId())
        fake_db.asset_performance_records.documents.append(
            make_doc(client_id=client_id, performance_score=1.5, content_theme="misc",
                     hook_type="generic", prompt_type="promo", platform="facebook")
        )
        correlations = correlate_lead_to_content_patterns(fake_db, WS, "lead789", client_id)
        assert any(c["correlation_strength"] == "weak" for c in correlations)

    def test_correlation_empty_records_returns_empty_list(self):
        from client_intelligence import correlate_lead_to_content_patterns
        fake_db = FakeDatabase()
        correlations = correlate_lead_to_content_patterns(fake_db, WS, "lead001", str(ObjectId()))
        assert correlations == []

    def test_list_correlations_returns_200(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.get("/lead-content-correlations")
        assert resp.status_code == 200

    def test_list_correlations_filtered_by_client(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        client_id = str(ObjectId())
        fake_db.lead_content_correlations.documents.append(
            make_doc(workspace_slug=WS, client_id=client_id, lead_id="lead1",
                     correlation_strength="strong")
        )
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.get(f"/lead-content-correlations?client_id={client_id}")
        assert len(resp.json()["items"]) == 1

    def test_list_correlations_workspace_isolated(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        fake_db.lead_content_correlations.documents.append(
            make_doc(workspace_slug=WS, client_id=str(ObjectId()), lead_id="lead1",
                     correlation_strength="moderate")
        )
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.get(f"/lead-content-correlations?workspace_slug={WS_OTHER}")
        assert len(resp.json()["items"]) == 0


# ---------------------------------------------------------------------------
# TestWorkspaceIsolation
# ---------------------------------------------------------------------------

class TestWorkspaceIsolation:
    def test_intelligence_list_only_returns_own_workspace(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            cid1 = _setup_client(c, fake_db, workspace=WS)
            cid2 = _setup_client(c, fake_db, workspace=WS_OTHER)
            c.post(f"/client-intelligence/{cid1}/generate", json={"workspace_slug": WS})
            c.post(f"/client-intelligence/{cid2}/generate", json={"workspace_slug": WS_OTHER})
            resp = c.get(f"/client-intelligence?workspace_slug={WS}")
        items = resp.json()["items"]
        assert all(i["workspace_slug"] == WS for i in items)


# ---------------------------------------------------------------------------
# TestClientIsolation
# ---------------------------------------------------------------------------

class TestClientIsolation:
    def test_client_filter_returns_only_that_client(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            cid1 = _setup_client(c, fake_db)
            cid2 = _setup_client(c, fake_db)
            c.post(f"/client-intelligence/{cid1}/generate", json={"workspace_slug": WS})
            c.post(f"/client-intelligence/{cid2}/generate", json={"workspace_slug": WS})
            resp = c.get(f"/client-intelligence?client_id={cid1}")
        items = resp.json()["items"]
        assert all(i["client_id"] == cid1 for i in items)


# ---------------------------------------------------------------------------
# TestSafetyInvariants
# ---------------------------------------------------------------------------

class TestSafetyInvariants:
    def test_all_generated_records_simulation_only(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
        for doc in fake_db.client_intelligence_records.documents:
            assert doc.get("simulation_only") is True

    def test_all_generated_records_advisory_only(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
        for doc in fake_db.client_intelligence_records.documents:
            assert doc.get("advisory_only") is True

    def test_all_generated_records_outbound_zero(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
        for doc in fake_db.client_intelligence_records.documents:
            assert doc.get("outbound_actions_taken") == 0

    def test_correlation_records_simulation_only(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            _add_perf_record(fake_db, client_id)
            c.post("/lead-content-correlations/generate", json={
                "workspace_slug": WS,
                "client_id": client_id,
            })
        for doc in fake_db.lead_content_correlations.documents:
            assert doc.get("simulation_only") is True
            assert doc.get("advisory_only") is True
            assert doc.get("outbound_actions_taken") == 0

    def test_no_external_http_calls_during_generation(self):
        """build_client_intelligence must not make any HTTP requests."""
        import httpx
        import requests as requests_lib
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)

        with patch("main.get_client", gc), patch("main.get_database", gd), \
             patch.object(httpx, "get", side_effect=AssertionError("External HTTP call!")), \
             patch.object(httpx, "post", side_effect=AssertionError("External HTTP call!")):
            try:
                with patch.object(requests_lib, "get", side_effect=AssertionError("External HTTP call!")), \
                     patch.object(requests_lib, "post", side_effect=AssertionError("External HTTP call!")):
                    c = TestClient(app)
                    client_id = _setup_client(c, fake_db)
                    resp = c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
            except ImportError:
                c = TestClient(app)
                client_id = _setup_client(c, fake_db)
                resp = c.post(f"/client-intelligence/{client_id}/generate", json={"workspace_slug": WS})
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# TestPatchEndpoints
# ---------------------------------------------------------------------------

class TestPatchClientProfileIntelligence:
    def test_patch_intelligence_fields_returns_200(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            resp = c.patch(f"/client-profiles/{client_id}/intelligence", json={
                "workspace_slug": WS,
                "acquisition_score": 8.5,
                "conversion_status": "converted",
                "acquisition_notes": "Converted via campaign v9.5",
                "lifetime_value_estimate": 5000.0,
            })
        assert resp.status_code == 200

    def test_patch_simulation_only(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            resp = c.patch(f"/client-profiles/{client_id}/intelligence", json={
                "workspace_slug": WS,
            })
        data = resp.json()
        assert data["simulation_only"] is True
        assert data["outbound_actions_taken"] == 0

    def test_patch_invalid_conversion_status_returns_422(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            resp = c.patch(f"/client-profiles/{client_id}/intelligence", json={
                "workspace_slug": WS,
                "conversion_status": "invalid_status",
            })
        assert resp.status_code == 422

    def test_patch_missing_client_returns_404(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.patch(f"/client-profiles/{str(ObjectId())}/intelligence", json={
                "workspace_slug": WS,
            })
        assert resp.status_code == 404


class TestPatchCampaignPackLink:
    def _setup_pack(self, client_obj, fake_db, workspace=WS):
        client_id = _setup_client(client_obj, fake_db, workspace=workspace)
        resp = client_obj.post("/campaign-packs", json={
            "workspace_slug": workspace,
            "client_id": client_id,
            "campaign_name": "v9.5 Link Test",
            "campaign_goal": "test",
            "target_platforms": ["instagram"],
            "target_audience": "test audience",
            "content_themes": ["test theme"],
        })
        assert resp.status_code == 201
        return resp.json()["item"]["_id"]

    def test_patch_link_returns_200(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id = self._setup_pack(c, fake_db)
            resp = c.patch(f"/campaign-packs/{pack_id}/link", json={
                "workspace_slug": WS,
                "linked_lead_id": str(ObjectId()),
                "linked_deal_id": str(ObjectId()),
                "campaign_roi_estimate": 1500.0,
            })
        assert resp.status_code == 200

    def test_patch_link_simulation_only(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id = self._setup_pack(c, fake_db)
            resp = c.patch(f"/campaign-packs/{pack_id}/link", json={"workspace_slug": WS})
        data = resp.json()
        assert data["simulation_only"] is True
        assert data["outbound_actions_taken"] == 0

    def test_patch_link_invalid_pack_id_returns_422(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.patch("/campaign-packs/not-an-objectid/link", json={"workspace_slug": WS})
        assert resp.status_code == 422

    def test_patch_link_missing_pack_returns_404(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.patch(f"/campaign-packs/{str(ObjectId())}/link", json={"workspace_slug": WS})
        assert resp.status_code == 404


class TestPatchAssetPerformanceIntelligence:
    def _setup_perf_record(self, client_obj, fake_db, client_id, workspace=WS):
        resp = client_obj.post("/asset-performance-records", json={
            "workspace_slug": workspace,
            "client_id": client_id,
            "platform": "instagram",
            "views": 1000,
        })
        assert resp.status_code == 201
        return resp.json()["item"]["_id"]

    def test_patch_intelligence_returns_200(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            record_id = self._setup_perf_record(c, fake_db, client_id)
            resp = c.patch(f"/asset-performance-records/{record_id}/intelligence", json={
                "workspace_slug": WS,
                "estimated_revenue_impact": 250.0,
                "funnel_stage_impact": "conversion",
                "attribution_notes": "Linked to campaign v9.5",
            })
        assert resp.status_code == 200

    def test_patch_invalid_funnel_stage_returns_422(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            record_id = self._setup_perf_record(c, fake_db, client_id)
            resp = c.patch(f"/asset-performance-records/{record_id}/intelligence", json={
                "workspace_slug": WS,
                "funnel_stage_impact": "invalid_stage",
            })
        assert resp.status_code == 422

    def test_patch_invalid_record_id_returns_422(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.patch("/asset-performance-records/bad-id/intelligence", json={"workspace_slug": WS})
        assert resp.status_code == 422

    def test_patch_missing_record_returns_404(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.patch(f"/asset-performance-records/{str(ObjectId())}/intelligence", json={"workspace_slug": WS})
        assert resp.status_code == 404

    def test_patch_simulation_only(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            client_id = _setup_client(c, fake_db)
            record_id = self._setup_perf_record(c, fake_db, client_id)
            resp = c.patch(f"/asset-performance-records/{record_id}/intelligence", json={"workspace_slug": WS})
        data = resp.json()
        assert data["simulation_only"] is True
        assert data["outbound_actions_taken"] == 0
