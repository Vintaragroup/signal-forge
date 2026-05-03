"""
Tests for Social Creative Engine v8 — Client Campaign Packs

Covers:
- Create campaign pack (status_code=201, simulation_only, outbound_actions_taken)
- List campaign packs
- Get campaign pack detail (items included)
- Add item to pack (valid)
- Reject item from wrong workspace
- Reject item from wrong client
- Generate campaign report (status_code=201, advisory_only)
- Report includes performance summaries when available
- Report handles empty performance data safely
- Review report: approve / reject / revise
- List campaign reports
- Workspace isolation
- Client isolation
- simulation_only=True always
- outbound_actions_taken=0 always
- No external calls (all local fake DB)
"""

from __future__ import annotations

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
                push = update.get("$push") or {}
                for key, value in push.items():
                    doc.setdefault(key, []).append(value)
                return
        if upsert:
            new_doc = {"_id": ObjectId()}
            for key, value in (update.get("$set") or {}).items():
                new_doc[key] = value
            for key, value in (update.get("$setOnInsert") or {}).items():
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
        # Core collections required by main.py
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
        # v7.5 collections
        self.manual_publish_logs = FakeCollection()
        self.asset_performance_records = FakeCollection()
        self.creative_performance_summaries = FakeCollection()
        # v8 collections
        self.campaign_packs = FakeCollection()
        self.campaign_pack_items = FakeCollection()
        self.campaign_reports = FakeCollection()


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
# Fixtures
# ---------------------------------------------------------------------------

WS = "test-workspace"
WS_OTHER = "other-workspace"
CLIENT_ID = str(ObjectId())
CLIENT_OTHER = str(ObjectId())

VALID_PACK_PAYLOAD = {
    "workspace_slug": WS,
    "client_id": CLIENT_ID,
    "campaign_name": "Spring 2025 Launch",
    "campaign_goal": "Drive awareness for new product line",
    "target_platforms": ["instagram", "tiktok"],
    "target_audience": "Adults 25-40 interested in fitness",
    "content_themes": ["education", "behind-the-scenes"],
}


# ---------------------------------------------------------------------------
# TestCampaignPackCreate
# ---------------------------------------------------------------------------

class TestCampaignPackCreate:
    def test_create_returns_201(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/campaign-packs", json=VALID_PACK_PAYLOAD)
        assert resp.status_code == 201

    def test_create_simulation_only(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/campaign-packs", json=VALID_PACK_PAYLOAD)
        data = resp.json()
        assert data["simulation_only"] is True
        assert data["outbound_actions_taken"] == 0
        assert data["item"]["simulation_only"] is True
        assert data["item"]["outbound_actions_taken"] == 0

    def test_create_status_is_draft(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/campaign-packs", json=VALID_PACK_PAYLOAD)
        assert resp.json()["item"]["status"] == "draft"

    def test_create_stores_campaign_name(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/campaign-packs", json=VALID_PACK_PAYLOAD)
        assert resp.json()["item"]["campaign_name"] == "Spring 2025 Launch"

    def test_create_stores_platforms(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/campaign-packs", json=VALID_PACK_PAYLOAD)
        assert "instagram" in resp.json()["item"]["target_platforms"]

    def test_create_message_confirms_no_publish(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/campaign-packs", json=VALID_PACK_PAYLOAD)
        assert "not published" in resp.json()["message"].lower() or "not publish" in resp.json()["message"].lower()


# ---------------------------------------------------------------------------
# TestCampaignPackList
# ---------------------------------------------------------------------------

class TestCampaignPackList:
    def test_list_returns_200(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.get(f"/campaign-packs?workspace_slug={WS}")
        assert resp.status_code == 200

    def test_list_empty_initially(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.get(f"/campaign-packs?workspace_slug={WS}")
        assert resp.json()["total"] == 0

    def test_list_returns_created_pack(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            client.post("/campaign-packs", json=VALID_PACK_PAYLOAD)
            resp = client.get(f"/campaign-packs?workspace_slug={WS}")
        assert resp.json()["total"] == 1

    def test_list_simulation_only(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.get(f"/campaign-packs?workspace_slug={WS}")
        assert resp.json()["simulation_only"] is True
        assert resp.json()["outbound_actions_taken"] == 0


# ---------------------------------------------------------------------------
# TestCampaignPackDetail
# ---------------------------------------------------------------------------

class TestCampaignPackDetail:
    def _create_pack(self, client, payload=None):
        resp = client.post("/campaign-packs", json=payload or VALID_PACK_PAYLOAD)
        return resp.json()["item"]["_id"]

    def test_get_detail_returns_200(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pack_id = self._create_pack(c)
            resp = c.get(f"/campaign-packs/{pack_id}")
        assert resp.status_code == 200

    def test_get_detail_includes_pack_items(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pack_id = self._create_pack(c)
            resp = c.get(f"/campaign-packs/{pack_id}")
        data = resp.json()
        assert "pack_items" in data
        assert isinstance(data["pack_items"], list)

    def test_get_detail_invalid_id_returns_422(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            resp = c.get("/campaign-packs/not-a-valid-id")
        assert resp.status_code == 422

    def test_get_detail_missing_pack_returns_404(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            resp = c.get(f"/campaign-packs/{str(ObjectId())}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestCampaignPackItems
# ---------------------------------------------------------------------------

class TestCampaignPackItems:
    def _create_pack(self, client, workspace=WS, client_id=CLIENT_ID):
        resp = client.post("/campaign-packs", json={
            **VALID_PACK_PAYLOAD,
            "workspace_slug": workspace,
            "client_id": client_id,
        })
        return resp.json()["item"]["_id"]

    def test_add_valid_item_returns_201(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pack_id = self._create_pack(c)
            resp = c.post(f"/campaign-packs/{pack_id}/items", json={
                "workspace_slug": WS,
                "client_id": CLIENT_ID,
                "item_type": "snippet",
                "item_id": str(ObjectId()),
                "title": "Hook test snippet",
            })
        assert resp.status_code == 201

    def test_add_item_simulation_only(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pack_id = self._create_pack(c)
            resp = c.post(f"/campaign-packs/{pack_id}/items", json={
                "workspace_slug": WS,
                "item_type": "asset_render",
                "item_id": str(ObjectId()),
            })
        data = resp.json()
        assert data["simulation_only"] is True
        assert data["outbound_actions_taken"] == 0
        assert data["item"]["simulation_only"] is True
        assert data["item"]["outbound_actions_taken"] == 0

    def test_add_item_wrong_workspace_rejected(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pack_id = self._create_pack(c, workspace=WS)
            resp = c.post(f"/campaign-packs/{pack_id}/items", json={
                "workspace_slug": WS_OTHER,  # different workspace
                "item_type": "snippet",
                "item_id": str(ObjectId()),
            })
        assert resp.status_code == 422
        assert "workspace" in resp.json()["detail"].lower()

    def test_add_item_wrong_client_rejected(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pack_id = self._create_pack(c, client_id=CLIENT_ID)
            resp = c.post(f"/campaign-packs/{pack_id}/items", json={
                "workspace_slug": WS,
                "client_id": CLIENT_OTHER,  # different client
                "item_type": "snippet",
                "item_id": str(ObjectId()),
            })
        assert resp.status_code == 422
        assert "client" in resp.json()["detail"].lower()

    def test_add_item_invalid_type_rejected(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pack_id = self._create_pack(c)
            resp = c.post(f"/campaign-packs/{pack_id}/items", json={
                "workspace_slug": WS,
                "item_type": "not_a_real_type",
                "item_id": str(ObjectId()),
            })
        assert resp.status_code == 422

    def test_add_all_item_types(self):
        """All six valid item types can be added."""
        valid_types = [
            "source_content", "snippet", "prompt_generation",
            "asset_render", "publish_log", "performance_record",
        ]
        for item_type in valid_types:
            fake_db = FakeDatabase()
            fake_get_client, fake_get_database = make_db_patch(fake_db)
            with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
                c = TestClient(app)
                pack_id = self._create_pack(c)
                resp = c.post(f"/campaign-packs/{pack_id}/items", json={
                    "workspace_slug": WS,
                    "item_type": item_type,
                    "item_id": str(ObjectId()),
                })
            assert resp.status_code == 201, f"Failed for item_type={item_type}: {resp.json()}"

    def test_items_appear_in_pack_detail(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pack_id = self._create_pack(c)
            c.post(f"/campaign-packs/{pack_id}/items", json={
                "workspace_slug": WS,
                "item_type": "snippet",
                "item_id": str(ObjectId()),
                "title": "My snippet",
            })
            resp = c.get(f"/campaign-packs/{pack_id}")
        assert len(resp.json()["pack_items"]) == 1
        assert resp.json()["pack_items"][0]["title"] == "My snippet"


# ---------------------------------------------------------------------------
# TestCampaignReportGenerate
# ---------------------------------------------------------------------------

class TestCampaignReportGenerate:
    def _create_pack(self, client):
        resp = client.post("/campaign-packs", json=VALID_PACK_PAYLOAD)
        return resp.json()["item"]["_id"]

    def test_generate_returns_201(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pack_id = self._create_pack(c)
            resp = c.post(f"/campaign-packs/{pack_id}/generate-report")
        assert resp.status_code == 201

    def test_generate_simulation_only(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pack_id = self._create_pack(c)
            resp = c.post(f"/campaign-packs/{pack_id}/generate-report")
        data = resp.json()
        assert data["simulation_only"] is True
        assert data["outbound_actions_taken"] == 0
        assert data["item"]["simulation_only"] is True
        assert data["item"]["outbound_actions_taken"] == 0

    def test_generate_report_advisory_only(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pack_id = self._create_pack(c)
            resp = c.post(f"/campaign-packs/{pack_id}/generate-report")
        assert resp.json()["item"]["advisory_only"] is True

    def test_generate_report_status_is_draft(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pack_id = self._create_pack(c)
            resp = c.post(f"/campaign-packs/{pack_id}/generate-report")
        assert resp.json()["item"]["status"] == "draft"

    def test_generate_report_has_executive_summary(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pack_id = self._create_pack(c)
            resp = c.post(f"/campaign-packs/{pack_id}/generate-report")
        assert resp.json()["item"]["executive_summary"]

    def test_generate_report_handles_empty_performance_data(self):
        """Report must not crash when no performance records exist."""
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pack_id = self._create_pack(c)
            resp = c.post(f"/campaign-packs/{pack_id}/generate-report")
        assert resp.status_code == 201
        perf_summary = resp.json()["item"]["performance_summary"]
        assert perf_summary["record_count"] == 0
        assert perf_summary["avg_score"] is None
        assert perf_summary["top_score"] is None

    def test_generate_report_includes_performance_when_present(self):
        """When perf records exist for pack assets, report includes non-null avg_score."""
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        render_id = str(ObjectId())
        # Pre-seed a performance record for the render
        fake_db.asset_performance_records.documents.append(make_doc(
            workspace_slug=WS,
            client_id=CLIENT_ID,
            asset_render_id=render_id,
            performance_score=8.0,
            platform="instagram",
        ))
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pack_id = self._create_pack(c)
            # Add an asset_render item pointing to render_id
            c.post(f"/campaign-packs/{pack_id}/items", json={
                "workspace_slug": WS,
                "item_type": "asset_render",
                "item_id": render_id,
            })
            resp = c.post(f"/campaign-packs/{pack_id}/generate-report")
        assert resp.status_code == 201
        perf_summary = resp.json()["item"]["performance_summary"]
        assert perf_summary["record_count"] == 1
        assert perf_summary["avg_score"] == 8.0

    def test_generate_invalid_pack_id_returns_422(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            resp = c.post("/campaign-packs/not-valid/generate-report")
        assert resp.status_code == 422

    def test_generate_missing_pack_returns_404(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            resp = c.post(f"/campaign-packs/{str(ObjectId())}/generate-report")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestCampaignReportList
# ---------------------------------------------------------------------------

class TestCampaignReportList:
    def test_list_returns_200(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            resp = c.get(f"/campaign-reports?workspace_slug={WS}")
        assert resp.status_code == 200

    def test_list_empty_initially(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            resp = c.get(f"/campaign-reports?workspace_slug={WS}")
        assert resp.json()["total"] == 0

    def test_list_returns_generated_reports(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pack_resp = c.post("/campaign-packs", json=VALID_PACK_PAYLOAD)
            pack_id = pack_resp.json()["item"]["_id"]
            c.post(f"/campaign-packs/{pack_id}/generate-report")
            resp = c.get(f"/campaign-reports?workspace_slug={WS}")
        assert resp.json()["total"] == 1

    def test_list_simulation_only(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            resp = c.get(f"/campaign-reports?workspace_slug={WS}")
        assert resp.json()["simulation_only"] is True
        assert resp.json()["outbound_actions_taken"] == 0


# ---------------------------------------------------------------------------
# TestCampaignReportReview
# ---------------------------------------------------------------------------

class TestCampaignReportReview:
    def _create_report(self, client):
        pack_resp = client.post("/campaign-packs", json=VALID_PACK_PAYLOAD)
        pack_id = pack_resp.json()["item"]["_id"]
        report_resp = client.post(f"/campaign-packs/{pack_id}/generate-report")
        return report_resp.json()["item"]["_id"]

    def test_approve_returns_200(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            report_id = self._create_report(c)
            resp = c.post(f"/campaign-reports/{report_id}/review", json={
                "workspace_slug": WS,
                "decision": "approve",
                "reviewer_notes": "Looks good.",
            })
        assert resp.status_code == 200

    def test_approve_sets_status_approved(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            report_id = self._create_report(c)
            resp = c.post(f"/campaign-reports/{report_id}/review", json={
                "workspace_slug": WS,
                "decision": "approve",
            })
        assert resp.json()["item"]["status"] == "approved"

    def test_reject_sets_status_draft(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            report_id = self._create_report(c)
            resp = c.post(f"/campaign-reports/{report_id}/review", json={
                "workspace_slug": WS,
                "decision": "reject",
            })
        assert resp.json()["item"]["status"] == "draft"

    def test_revise_sets_status_needs_review(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            report_id = self._create_report(c)
            resp = c.post(f"/campaign-reports/{report_id}/review", json={
                "workspace_slug": WS,
                "decision": "revise",
            })
        assert resp.json()["item"]["status"] == "needs_review"

    def test_invalid_decision_returns_422(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            report_id = self._create_report(c)
            resp = c.post(f"/campaign-reports/{report_id}/review", json={
                "workspace_slug": WS,
                "decision": "publish_now",  # invalid
            })
        assert resp.status_code == 422

    def test_review_simulation_only(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            report_id = self._create_report(c)
            resp = c.post(f"/campaign-reports/{report_id}/review", json={
                "workspace_slug": WS,
                "decision": "approve",
            })
        assert resp.json()["simulation_only"] is True
        assert resp.json()["outbound_actions_taken"] == 0

    def test_approve_does_not_auto_publish(self):
        """Approving a report MUST NOT change any snippet or asset to published."""
        fake_db = FakeDatabase()
        snippet_id = ObjectId()
        fake_db.content_snippets.documents.append(make_doc(
            _id=snippet_id,
            workspace_slug=WS,
            status="needs_review",
        ))
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            report_id = self._create_report(c)
            c.post(f"/campaign-reports/{report_id}/review", json={
                "workspace_slug": WS,
                "decision": "approve",
            })
        # Snippet must still be needs_review — approving a report never changes snippets
        snippet = fake_db.content_snippets.find_one({"_id": snippet_id})
        assert snippet["status"] == "needs_review"

    def test_missing_report_returns_404(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            resp = c.post(f"/campaign-reports/{str(ObjectId())}/review", json={
                "workspace_slug": WS,
                "decision": "approve",
            })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestWorkspaceIsolation
# ---------------------------------------------------------------------------

class TestWorkspaceIsolation:
    def test_list_packs_only_returns_own_workspace(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            # Create pack in WS
            c.post("/campaign-packs", json={**VALID_PACK_PAYLOAD, "workspace_slug": WS})
            # Create pack in WS_OTHER
            c.post("/campaign-packs", json={**VALID_PACK_PAYLOAD, "workspace_slug": WS_OTHER})
            resp = c.get(f"/campaign-packs?workspace_slug={WS}")
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["workspace_slug"] == WS

    def test_list_reports_only_returns_own_workspace(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            # Pack + report in WS
            pr = c.post("/campaign-packs", json={**VALID_PACK_PAYLOAD, "workspace_slug": WS})
            c.post(f"/campaign-packs/{pr.json()['item']['_id']}/generate-report")
            # Pack + report in WS_OTHER
            pr2 = c.post("/campaign-packs", json={**VALID_PACK_PAYLOAD, "workspace_slug": WS_OTHER})
            c.post(f"/campaign-packs/{pr2.json()['item']['_id']}/generate-report")
            resp = c.get(f"/campaign-reports?workspace_slug={WS}")
        assert resp.json()["total"] == 1


# ---------------------------------------------------------------------------
# TestClientIsolation
# ---------------------------------------------------------------------------

class TestClientIsolation:
    def test_list_packs_only_returns_own_client(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            c.post("/campaign-packs", json={**VALID_PACK_PAYLOAD, "client_id": CLIENT_ID})
            c.post("/campaign-packs", json={**VALID_PACK_PAYLOAD, "client_id": CLIENT_OTHER})
            resp = c.get(f"/campaign-packs?workspace_slug={WS}&client_id={CLIENT_ID}")
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["client_id"] == CLIENT_ID


# ---------------------------------------------------------------------------
# TestSafetyInvariants
# ---------------------------------------------------------------------------

class TestSafetyInvariants:
    def test_all_pack_records_have_simulation_only(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            c.post("/campaign-packs", json=VALID_PACK_PAYLOAD)
        for doc in fake_db.campaign_packs.documents:
            assert doc.get("simulation_only") is True, f"simulation_only missing on: {doc}"
            assert doc.get("outbound_actions_taken") == 0, f"outbound_actions_taken not 0 on: {doc}"

    def test_all_report_records_have_simulation_only(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pr = c.post("/campaign-packs", json=VALID_PACK_PAYLOAD)
            c.post(f"/campaign-packs/{pr.json()['item']['_id']}/generate-report")
        for doc in fake_db.campaign_reports.documents:
            assert doc.get("simulation_only") is True, f"simulation_only missing on: {doc}"
            assert doc.get("outbound_actions_taken") == 0, f"outbound_actions_taken not 0 on: {doc}"

    def test_all_item_records_have_simulation_only(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pr = c.post("/campaign-packs", json=VALID_PACK_PAYLOAD)
            pack_id = pr.json()["item"]["_id"]
            c.post(f"/campaign-packs/{pack_id}/items", json={
                "workspace_slug": WS,
                "item_type": "snippet",
                "item_id": str(ObjectId()),
            })
        for doc in fake_db.campaign_pack_items.documents:
            assert doc.get("simulation_only") is True
            assert doc.get("outbound_actions_taken") == 0

    def test_generate_report_message_confirms_no_publish(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pr = c.post("/campaign-packs", json=VALID_PACK_PAYLOAD)
            resp = c.post(f"/campaign-packs/{pr.json()['item']['_id']}/generate-report")
        msg = resp.json()["message"].lower()
        assert "advisory" in msg or "no publish" in msg or "outbound" in msg

    def test_review_approve_message_confirms_no_publish(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            c = TestClient(app)
            pr = c.post("/campaign-packs", json=VALID_PACK_PAYLOAD)
            rr = c.post(f"/campaign-packs/{pr.json()['item']['_id']}/generate-report")
            resp = c.post(f"/campaign-reports/{rr.json()['item']['_id']}/review", json={
                "workspace_slug": WS,
                "decision": "approve",
            })
        msg = resp.json()["message"].lower()
        assert "no publish" in msg or "outbound" in msg
