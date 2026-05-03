"""
Tests for Social Creative Engine v8.5 — Client Export Package

Covers:
- Create markdown export (status_code=201)
- Create zip export (status_code=201, manifest.json inside zip)
- Create pdf_placeholder export
- Export requires valid campaign_pack_id
- Export requires valid campaign_report_id
- Rejects wrong workspace
- Rejects wrong client
- Includes rendered asset if local file exists
- Handles missing local asset safely (no crash)
- Export review: approve / reject / revise
- List exports (200, workspace-filtered)
- Get export detail (200, 404, 422)
- Workspace isolation
- Client isolation
- simulation_only=True on all records
- outbound_actions_taken=0 on all records
- No external calls at any step
- Safety notes present on all exports
"""

from __future__ import annotations

import json
import os
import sys
import zipfile
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
# Shared helpers (copied from v8 test file for isolation)
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
# Fixtures / constants
# ---------------------------------------------------------------------------

WS = "test-workspace"
WS_OTHER = "other-workspace"
CLIENT_ID = str(ObjectId())
CLIENT_OTHER = str(ObjectId())

PACK_PAYLOAD = {
    "workspace_slug": WS,
    "client_id": CLIENT_ID,
    "campaign_name": "v8.5 Export Test Campaign",
    "campaign_goal": "Test export generation",
    "target_platforms": ["instagram"],
    "target_audience": "Test audience",
    "content_themes": ["education"],
}


def _setup_pack_and_report(client_obj, fake_db, workspace=WS, client_id=CLIENT_ID):
    """Create a pack and generate a report for it. Returns (pack_id, report_id)."""
    pr = client_obj.post("/campaign-packs", json={**PACK_PAYLOAD, "workspace_slug": workspace, "client_id": client_id})
    pack_id = pr.json()["item"]["_id"]
    rr = client_obj.post(f"/campaign-packs/{pack_id}/generate-report")
    report_id = rr.json()["item"]["_id"]
    return pack_id, report_id


# ---------------------------------------------------------------------------
# TestCampaignExportCreate
# ---------------------------------------------------------------------------

class TestCampaignExportCreate:
    def test_create_markdown_returns_201(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_name": "test_md_export",
                "export_format": "markdown",
            })
        assert resp.status_code == 201

    def test_create_zip_returns_201(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_name": "test_zip_export",
                "export_format": "zip",
            })
        assert resp.status_code == 201

    def test_create_pdf_placeholder_returns_201(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_name": "test_pdf_placeholder",
                "export_format": "pdf_placeholder",
            })
        assert resp.status_code == 201

    def test_create_simulation_only(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "markdown",
            })
        data = resp.json()
        assert data["simulation_only"] is True
        assert data["outbound_actions_taken"] == 0
        assert data["item"]["simulation_only"] is True
        assert data["item"]["outbound_actions_taken"] == 0

    def test_create_message_confirms_no_external(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "markdown",
            })
        msg = resp.json()["message"].lower()
        assert any(word in msg for word in ["local", "no publish", "no upload", "outbound"])

    def test_export_status_generated(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "markdown",
            })
        assert resp.json()["item"]["export_status"] == "generated"

    def test_export_path_set_for_markdown(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "markdown",
                "export_name": "md_test",
            })
        path = resp.json()["item"]["export_path"]
        assert path.endswith(".md")
        assert os.path.isfile(path), f"Markdown file not found at: {path}"

    def test_export_path_set_for_zip(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "zip",
                "export_name": "zip_test",
            })
        path = resp.json()["item"]["export_path"]
        assert path.endswith(".zip")
        assert os.path.isfile(path), f"Zip file not found at: {path}"

    def test_invalid_format_returns_422(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "docx",
            })
        assert resp.status_code == 422

    def test_missing_pack_returns_404(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": str(ObjectId()),
                "campaign_report_id": str(ObjectId()),
                "export_format": "markdown",
            })
        assert resp.status_code == 404
        assert "pack" in resp.json()["detail"].lower()

    def test_missing_report_returns_404(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pr = c.post("/campaign-packs", json=PACK_PAYLOAD)
            pack_id = pr.json()["item"]["_id"]
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": str(ObjectId()),
                "export_format": "markdown",
            })
        assert resp.status_code == 404
        assert "report" in resp.json()["detail"].lower()

    def test_invalid_pack_id_returns_422(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": "not-valid-oid",
                "campaign_report_id": str(ObjectId()),
                "export_format": "markdown",
            })
        assert resp.status_code == 422

    def test_wrong_workspace_returns_422(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db, workspace=WS)
            # Supply a different workspace_slug in the export request
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS_OTHER,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "markdown",
            })
        assert resp.status_code == 422
        assert "workspace" in resp.json()["detail"].lower()

    def test_wrong_client_returns_422(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db, client_id=CLIENT_ID)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "client_id": CLIENT_OTHER,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "markdown",
            })
        assert resp.status_code == 422
        assert "client" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# TestCampaignExportZip
# ---------------------------------------------------------------------------

class TestCampaignExportZip:
    def _create_zip_export(self, fake_db, extra_setup=None):
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            if extra_setup:
                extra_setup(c)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "zip",
                "export_name": "zip_test_run",
            })
        return resp

    def test_zip_contains_manifest(self):
        fake_db = FakeDatabase()
        resp = self._create_zip_export(fake_db)
        assert resp.status_code == 201
        zip_path = resp.json()["item"]["export_path"]
        assert os.path.isfile(zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            assert "manifest.json" in zf.namelist()

    def test_zip_manifest_is_valid_json(self):
        fake_db = FakeDatabase()
        resp = self._create_zip_export(fake_db)
        zip_path = resp.json()["item"]["export_path"]
        with zipfile.ZipFile(zip_path, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["export_format"] == "zip"
        assert manifest["simulation_only"] is True
        assert manifest["outbound_actions_taken"] == 0

    def test_zip_contains_report_md(self):
        fake_db = FakeDatabase()
        resp = self._create_zip_export(fake_db)
        zip_path = resp.json()["item"]["export_path"]
        with zipfile.ZipFile(zip_path, "r") as zf:
            assert "report.md" in zf.namelist()

    def test_zip_report_md_contains_safety_section(self):
        fake_db = FakeDatabase()
        resp = self._create_zip_export(fake_db)
        zip_path = resp.json()["item"]["export_path"]
        with zipfile.ZipFile(zip_path, "r") as zf:
            md_content = zf.read("report.md").decode("utf-8")
        assert "Safety & Audit Notes" in md_content
        assert "simulation_only: true" in md_content

    def test_zip_includes_local_asset_when_exists(self, tmp_path):
        """If a pack item has a local_file_path that exists on disk, it goes into the zip."""
        fake_db = FakeDatabase()
        # Create a real temp file as a fake rendered asset
        asset_file = tmp_path / "test_render.mp4"
        asset_file.write_bytes(b"fake mp4 data")
        render_id = ObjectId()
        fake_db.asset_renders.documents.append(make_doc(
            _id=render_id,
            workspace_slug=WS,
            local_file_path=str(asset_file),
            status="approved",
        ))

        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            # Add asset render item to pack
            c.post(f"/campaign-packs/{pack_id}/items", json={
                "workspace_slug": WS,
                "item_type": "asset_render",
                "item_id": str(render_id),
            })
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "zip",
                "export_name": "zip_with_asset",
            })

        assert resp.status_code == 201
        zip_path = resp.json()["item"]["export_path"]
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        assert any("test_render.mp4" in n for n in names), f"asset not in zip: {names}"
        # included_assets should list the path
        assert str(asset_file) in resp.json()["item"]["included_assets"]

    def test_zip_handles_missing_local_asset_safely(self, tmp_path):
        """If local_file_path doesn't exist on disk, zip still created without crashing."""
        fake_db = FakeDatabase()
        render_id = ObjectId()
        fake_db.asset_renders.documents.append(make_doc(
            _id=render_id,
            workspace_slug=WS,
            local_file_path="/nonexistent/path/to/asset.mp4",
            status="approved",
        ))

        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            c.post(f"/campaign-packs/{pack_id}/items", json={
                "workspace_slug": WS,
                "item_type": "asset_render",
                "item_id": str(render_id),
            })
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "zip",
                "export_name": "zip_missing_asset",
            })

        assert resp.status_code == 201
        assert resp.json()["item"]["export_status"] == "generated"
        # included_assets should be empty since file doesn't exist
        assert resp.json()["item"]["included_assets"] == []


# ---------------------------------------------------------------------------
# TestCampaignExportSafetyNotes
# ---------------------------------------------------------------------------

class TestCampaignExportSafetyNotes:
    def test_export_has_safety_notes(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "markdown",
            })
        assert len(resp.json()["item"]["safety_notes"]) > 0

    def test_safety_notes_mention_simulation(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "markdown",
            })
        notes_text = " ".join(resp.json()["item"]["safety_notes"]).lower()
        assert "simulation" in notes_text or "outbound" in notes_text

    def test_markdown_file_contains_safety_section(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "markdown",
            })
        path = resp.json()["item"]["export_path"]
        content = Path(path).read_text(encoding="utf-8")
        assert "Safety & Audit Notes" in content
        assert "simulation_only: true" in content
        assert "outbound_actions_taken: 0" in content


# ---------------------------------------------------------------------------
# TestCampaignExportList
# ---------------------------------------------------------------------------

class TestCampaignExportList:
    def test_list_returns_200(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.get(f"/campaign-exports?workspace_slug={WS}")
        assert resp.status_code == 200

    def test_list_empty_initially(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.get(f"/campaign-exports?workspace_slug={WS}")
        assert resp.json()["total"] == 0

    def test_list_returns_created_export(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "markdown",
            })
            resp = c.get(f"/campaign-exports?workspace_slug={WS}")
        assert resp.json()["total"] == 1

    def test_list_simulation_only(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.get(f"/campaign-exports?workspace_slug={WS}")
        assert resp.json()["simulation_only"] is True
        assert resp.json()["outbound_actions_taken"] == 0


# ---------------------------------------------------------------------------
# TestCampaignExportDetail
# ---------------------------------------------------------------------------

class TestCampaignExportDetail:
    def _create_export(self, client_obj, fake_db):
        pack_id, report_id = _setup_pack_and_report(client_obj, fake_db)
        resp = client_obj.post("/campaign-exports", json={
            "workspace_slug": WS,
            "campaign_pack_id": pack_id,
            "campaign_report_id": report_id,
            "export_format": "markdown",
        })
        return resp.json()["item"]["_id"]

    def test_get_detail_returns_200(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            export_id = self._create_export(c, fake_db)
            resp = c.get(f"/campaign-exports/{export_id}")
        assert resp.status_code == 200

    def test_get_detail_missing_returns_404(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.get(f"/campaign-exports/{str(ObjectId())}")
        assert resp.status_code == 404

    def test_get_detail_invalid_id_returns_422(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.get("/campaign-exports/not-a-valid-oid")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TestCampaignExportReview
# ---------------------------------------------------------------------------

class TestCampaignExportReview:
    def _create_export(self, client_obj, fake_db):
        pack_id, report_id = _setup_pack_and_report(client_obj, fake_db)
        resp = client_obj.post("/campaign-exports", json={
            "workspace_slug": WS,
            "campaign_pack_id": pack_id,
            "campaign_report_id": report_id,
            "export_format": "markdown",
        })
        return resp.json()["item"]["_id"]

    def test_approve_returns_200(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            export_id = self._create_export(c, fake_db)
            resp = c.post(f"/campaign-exports/{export_id}/review", json={
                "workspace_slug": WS,
                "decision": "approve",
            })
        assert resp.status_code == 200

    def test_approve_sets_status_approved(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            export_id = self._create_export(c, fake_db)
            resp = c.post(f"/campaign-exports/{export_id}/review", json={
                "workspace_slug": WS, "decision": "approve",
            })
        assert resp.json()["item"]["export_status"] == "approved"

    def test_reject_sets_status_rejected(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            export_id = self._create_export(c, fake_db)
            resp = c.post(f"/campaign-exports/{export_id}/review", json={
                "workspace_slug": WS, "decision": "reject",
            })
        assert resp.json()["item"]["export_status"] == "rejected"

    def test_revise_sets_status_needs_review(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            export_id = self._create_export(c, fake_db)
            resp = c.post(f"/campaign-exports/{export_id}/review", json={
                "workspace_slug": WS, "decision": "revise",
            })
        assert resp.json()["item"]["export_status"] == "needs_review"

    def test_invalid_decision_returns_422(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            export_id = self._create_export(c, fake_db)
            resp = c.post(f"/campaign-exports/{export_id}/review", json={
                "workspace_slug": WS, "decision": "send_to_client",
            })
        assert resp.status_code == 422

    def test_review_simulation_only(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            export_id = self._create_export(c, fake_db)
            resp = c.post(f"/campaign-exports/{export_id}/review", json={
                "workspace_slug": WS, "decision": "approve",
            })
        assert resp.json()["simulation_only"] is True
        assert resp.json()["outbound_actions_taken"] == 0

    def test_approve_message_confirms_no_external(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            export_id = self._create_export(c, fake_db)
            resp = c.post(f"/campaign-exports/{export_id}/review", json={
                "workspace_slug": WS, "decision": "approve",
            })
        msg = resp.json()["message"].lower()
        assert any(w in msg for w in ["no upload", "no publish", "outbound"])

    def test_missing_export_returns_404(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            resp = c.post(f"/campaign-exports/{str(ObjectId())}/review", json={
                "workspace_slug": WS, "decision": "approve",
            })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestWorkspaceIsolation
# ---------------------------------------------------------------------------

class TestWorkspaceIsolation:
    def test_list_exports_only_returns_own_workspace(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            # Export in WS
            pack_id, report_id = _setup_pack_and_report(c, fake_db, workspace=WS)
            c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "markdown",
            })
            # Export in WS_OTHER
            pack_id2, report_id2 = _setup_pack_and_report(c, fake_db, workspace=WS_OTHER)
            c.post("/campaign-exports", json={
                "campaign_pack_id": pack_id2,
                "campaign_report_id": report_id2,
                "export_format": "markdown",
            })
            resp = c.get(f"/campaign-exports?workspace_slug={WS}")
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["workspace_slug"] == WS


# ---------------------------------------------------------------------------
# TestClientIsolation
# ---------------------------------------------------------------------------

class TestClientIsolation:
    def test_list_exports_only_returns_own_client(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db, client_id=CLIENT_ID)
            c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "markdown",
            })
            pack_id2, report_id2 = _setup_pack_and_report(c, fake_db, client_id=CLIENT_OTHER)
            c.post("/campaign-exports", json={
                "campaign_pack_id": pack_id2,
                "campaign_report_id": report_id2,
                "export_format": "markdown",
            })
            resp = c.get(f"/campaign-exports?workspace_slug={WS}&client_id={CLIENT_ID}")
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["client_id"] == CLIENT_ID


# ---------------------------------------------------------------------------
# TestSafetyInvariants
# ---------------------------------------------------------------------------

class TestSafetyInvariants:
    def test_all_export_records_have_simulation_only(self):
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "markdown",
            })
        for doc in fake_db.campaign_exports.documents:
            assert doc.get("simulation_only") is True, f"simulation_only missing: {doc}"
            assert doc.get("outbound_actions_taken") == 0, f"outbound_actions_taken not 0: {doc}"

    def test_approve_does_not_change_pack_status(self):
        """Approving an export must not alter the campaign pack's status."""
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            original_pack_status = fake_db.campaign_packs.documents[0].get("status")
            ex_resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "markdown",
            })
            export_id = ex_resp.json()["item"]["_id"]
            c.post(f"/campaign-exports/{export_id}/review", json={
                "workspace_slug": WS, "decision": "approve",
            })
        # Pack status must be unchanged
        assert fake_db.campaign_packs.documents[0].get("status") == original_pack_status

    def test_approve_does_not_change_report_status(self):
        """Approving an export must not alter the campaign report's status."""
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            original_report_status = fake_db.campaign_reports.documents[0].get("status")
            ex_resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "markdown",
            })
            export_id = ex_resp.json()["item"]["_id"]
            c.post(f"/campaign-exports/{export_id}/review", json={
                "workspace_slug": WS, "decision": "approve",
            })
        assert fake_db.campaign_reports.documents[0].get("status") == original_report_status

    def test_export_writes_to_local_filesystem_only(self):
        """Export path must be under the local export directory."""
        from main import EXPORT_BASE_DIR
        fake_db = FakeDatabase()
        gc, gd = make_db_patch(fake_db)
        with patch("main.get_client", gc), patch("main.get_database", gd):
            c = TestClient(app)
            pack_id, report_id = _setup_pack_and_report(c, fake_db)
            resp = c.post("/campaign-exports", json={
                "workspace_slug": WS,
                "campaign_pack_id": pack_id,
                "campaign_report_id": report_id,
                "export_format": "markdown",
            })
        export_path = resp.json()["item"]["export_path"]
        assert export_path.startswith(EXPORT_BASE_DIR), (
            f"Export path {export_path!r} is outside EXPORT_BASE_DIR {EXPORT_BASE_DIR!r}"
        )
