"""
Tests for Social Creative Engine v7.5 — Performance Feedback & Learning Loop

Covers:
- Manual publish log creation (simulation_only, outbound_actions_taken)
- Asset performance record creation with score calculation
- Deterministic performance_score (same inputs → same output)
- Negative/invalid metrics are rejected (422)
- Performance CSV import: valid rows stored, bad rows in import_errors
- Creative performance summary generation (upsert, advisory_only)
- Learning-loop recommendations are advisory_only=True
- Workspace isolation: records from other workspaces are not returned
- Client isolation: records from other clients are not returned
- Safety invariants: simulation_only=True, outbound_actions_taken=0 always
- No automatic snippet approvals triggered by performance data
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
from main import app, calculate_performance_score

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
        # Existing collections required by main.py
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
# Helpers
# ---------------------------------------------------------------------------

RENDER_ID = str(ObjectId())
WS = "test-workspace"
CLIENT_ID = str(ObjectId())

VALID_PERF_PAYLOAD = {
    "workspace_slug": WS,
    "asset_render_id": RENDER_ID,
    "platform": "instagram",
    "views": 5000,
    "likes": 200,
    "comments": 50,
    "shares": 30,
    "saves": 80,
    "clicks": 60,
    "follows": 20,
    "watch_time_seconds": 10000,
    "average_view_duration": 12.5,
    "retention_rate": 0.55,
    "engagement_rate": -1.0,
    "imported_from": "manual",
}


# ---------------------------------------------------------------------------
# TestManualPublishLog
# ---------------------------------------------------------------------------

class TestManualPublishLog:
    def test_create_publish_log_returns_201(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/manual-publish-logs", json={
                "workspace_slug": WS,
                "asset_render_id": RENDER_ID,
                "platform": "instagram",
                "posted_by": "operator1",
            })
        assert resp.status_code == 201
        data = resp.json()
        assert data["item"]["platform"] == "instagram"
        assert data["item"]["simulation_only"] is True
        assert data["item"]["outbound_actions_taken"] == 0

    def test_list_publish_logs(self):
        fake_db = FakeDatabase()
        fake_db.manual_publish_logs.insert_one(make_doc(
            workspace_slug=WS, platform="tiktok",
            simulation_only=True, outbound_actions_taken=0,
        ))
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.get(f"/manual-publish-logs?workspace_slug={WS}")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

    def test_publish_log_simulation_only(self):
        """Every publish log must have simulation_only=True."""
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/manual-publish-logs", json={
                "workspace_slug": WS,
                "asset_render_id": RENDER_ID,
                "platform": "youtube",
            })
        assert resp.json()["item"]["simulation_only"] is True

    def test_publish_log_outbound_zero(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/manual-publish-logs", json={
                "workspace_slug": WS,
                "asset_render_id": RENDER_ID,
                "platform": "tiktok",
            })
        assert resp.json()["item"]["outbound_actions_taken"] == 0


# ---------------------------------------------------------------------------
# TestAssetPerformanceRecord
# ---------------------------------------------------------------------------

class TestAssetPerformanceRecord:
    def test_create_record_returns_201(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/asset-performance-records", json=VALID_PERF_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()
        assert "performance_score" in data["item"]
        assert data["item"]["simulation_only"] is True
        assert data["item"]["outbound_actions_taken"] == 0

    def test_performance_score_in_range(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/asset-performance-records", json=VALID_PERF_PAYLOAD)
        score = resp.json()["item"]["performance_score"]
        assert 0.0 <= score <= 10.0

    def test_list_performance_records(self):
        fake_db = FakeDatabase()
        fake_db.asset_performance_records.insert_one(make_doc(
            workspace_slug=WS, platform="tiktok",
            performance_score=5.5, simulation_only=True, outbound_actions_taken=0,
        ))
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.get(f"/asset-performance-records?workspace_slug={WS}")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

    def test_negative_views_rejected(self):
        fake_db = FakeDatabase()
        payload = {**VALID_PERF_PAYLOAD, "views": -1}
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/asset-performance-records", json=payload)
        assert resp.status_code == 422

    def test_negative_likes_rejected(self):
        fake_db = FakeDatabase()
        payload = {**VALID_PERF_PAYLOAD, "likes": -5}
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/asset-performance-records", json=payload)
        assert resp.status_code == 422

    def test_retention_rate_out_of_range_rejected(self):
        fake_db = FakeDatabase()
        payload = {**VALID_PERF_PAYLOAD, "retention_rate": 1.5}
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/asset-performance-records", json=payload)
        assert resp.status_code == 422

    def test_engagement_rate_out_of_range_rejected(self):
        fake_db = FakeDatabase()
        payload = {**VALID_PERF_PAYLOAD, "engagement_rate": 2.0}
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/asset-performance-records", json=payload)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TestPerformanceScore — deterministic, pure function
# ---------------------------------------------------------------------------

class TestPerformanceScore:
    def test_deterministic_same_inputs(self):
        """Same inputs must always return the same score."""
        inputs = dict(
            views=5000, likes=200, comments=50, shares=30,
            saves=80, clicks=60, follows=20,
            watch_time_seconds=10000, average_view_duration=12.5,
            retention_rate=0.55, engagement_rate=-1.0,
        )
        score_a, _ = calculate_performance_score(**inputs)
        score_b, _ = calculate_performance_score(**inputs)
        assert score_a == score_b

    def test_zero_inputs_returns_zero(self):
        score, _ = calculate_performance_score(
            views=0, likes=0, comments=0, shares=0, saves=0,
            clicks=0, follows=0, watch_time_seconds=0,
            average_view_duration=0, retention_rate=0.0, engagement_rate=0.0,
        )
        assert score == 0.0

    def test_perfect_inputs_returns_ten(self):
        """Clamped inputs at or above each weight threshold → score of 10."""
        score, _ = calculate_performance_score(
            views=10000, likes=5000, comments=1000, shares=200, saves=500,
            clicks=500, follows=100, watch_time_seconds=60000,
            average_view_duration=60, retention_rate=1.0, engagement_rate=1.0,
        )
        assert score == 10.0

    def test_score_is_float(self):
        score, _ = calculate_performance_score(
            views=1000, likes=100, comments=10, shares=5, saves=20,
            clicks=10, follows=5, watch_time_seconds=5000,
            average_view_duration=10, retention_rate=0.3, engagement_rate=-1.0,
        )
        assert isinstance(score, float)

    def test_auto_derived_engagement_rate(self):
        """When engagement_rate < 0, it is auto-derived from likes+comments+shares+saves/views."""
        score_derived, reason = calculate_performance_score(
            views=1000, likes=50, comments=10, shares=20, saves=30,
            clicks=0, follows=0, watch_time_seconds=0,
            average_view_duration=0, retention_rate=0.0, engagement_rate=-1.0,
        )
        # derived_eng = (50+10+20+30)/1000 = 0.11
        score_explicit, _ = calculate_performance_score(
            views=1000, likes=50, comments=10, shares=20, saves=30,
            clicks=0, follows=0, watch_time_seconds=0,
            average_view_duration=0, retention_rate=0.0, engagement_rate=0.11,
        )
        assert score_derived == score_explicit

    def test_score_bounded_between_0_and_10(self):
        """Score must never exceed 10 or go below 0."""
        score, _ = calculate_performance_score(
            views=999999, likes=999999, comments=999999, shares=999999, saves=999999,
            clicks=999999, follows=999999, watch_time_seconds=999999,
            average_view_duration=999, retention_rate=999.0, engagement_rate=999.0,
        )
        assert 0.0 <= score <= 10.0

    def test_reason_string_returned(self):
        _, reason = calculate_performance_score(
            views=5000, likes=200, comments=50, shares=30, saves=80,
            clicks=60, follows=0, watch_time_seconds=10000,
            average_view_duration=12.5, retention_rate=0.55, engagement_rate=-1.0,
        )
        assert isinstance(reason, str)
        assert len(reason) > 0


# ---------------------------------------------------------------------------
# TestPerformanceCSVImport
# ---------------------------------------------------------------------------

class TestPerformanceCSVImport:
    def _make_valid_row(self):
        return {
            "workspace_slug": WS,
            "asset_render_id": RENDER_ID,
            "platform": "instagram",
            "views": "5000",
            "likes": "200",
            "comments": "50",
            "shares": "30",
            "saves": "80",
            "clicks": "60",
            "follows": "20",
            "watch_time_seconds": "10000",
            "average_view_duration": "12.5",
            "retention_rate": "0.55",
            "engagement_rate": "-1",
        }

    def test_csv_import_valid_rows(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        rows = [self._make_valid_row() for _ in range(3)]
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/asset-performance-records/import-csv", json={
                "workspace_slug": WS,
                "rows": rows,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported_count"] == 3
        assert data["error_count"] == 0
        assert data["import_errors"] == []

    def test_csv_import_bad_row_stored_in_errors(self):
        """A row with a non-numeric views field should be stored in import_errors, not crash."""
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        bad_row = {**self._make_valid_row(), "views": "not_a_number"}
        good_row = self._make_valid_row()
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/asset-performance-records/import-csv", json={
                "workspace_slug": WS,
                "rows": [bad_row, good_row],
            })
        data = resp.json()
        assert data["imported_count"] >= 1
        assert data["error_count"] >= 1
        assert len(data["import_errors"]) >= 1
        # The error entry must identify the row
        err = data["import_errors"][0]
        assert "row_index" in err
        assert "errors" in err

    def test_csv_import_max_1000_rows(self):
        """More than 1000 rows should be rejected with 422."""
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        rows = [self._make_valid_row() for _ in range(1001)]
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/asset-performance-records/import-csv", json={
                "workspace_slug": WS,
                "rows": rows,
            })
        assert resp.status_code == 422

    def test_csv_import_empty_rows_rejected(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/asset-performance-records/import-csv", json={
                "workspace_slug": WS,
                "rows": [],
            })
        assert resp.status_code == 422

    def test_csv_import_simulation_only(self):
        """All imported records must have simulation_only=True."""
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        rows = [self._make_valid_row()]
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            client.post("/asset-performance-records/import-csv", json={"workspace_slug": WS, "rows": rows})
        stored = fake_db.asset_performance_records.documents
        assert len(stored) >= 1
        for doc in stored:
            assert doc.get("simulation_only") is True

    def test_csv_import_outbound_zero(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        rows = [self._make_valid_row()]
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            client.post("/asset-performance-records/import-csv", json={"workspace_slug": WS, "rows": rows})
        for doc in fake_db.asset_performance_records.documents:
            assert doc.get("outbound_actions_taken") == 0

    def test_csv_import_negative_views_stored_as_error(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        bad_row = {**self._make_valid_row(), "views": "-100"}
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/asset-performance-records/import-csv", json={
                "workspace_slug": WS,
                "rows": [bad_row],
            })
        data = resp.json()
        assert data["error_count"] >= 1


# ---------------------------------------------------------------------------
# TestCreativePerformanceSummary
# ---------------------------------------------------------------------------

class TestCreativePerformanceSummary:
    def test_generate_summary_no_records(self):
        """Generating a summary with no records should still succeed (score=0)."""
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/creative-performance-summaries/generate", json={
                "workspace_slug": WS,
                "asset_render_id": RENDER_ID,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "item" in data
        assert "recommendations" in data
        assert data["item"]["simulation_only"] is True
        assert data["item"]["outbound_actions_taken"] == 0

    def test_generate_summary_with_records(self):
        fake_db = FakeDatabase()
        # Pre-insert a performance record
        fake_db.asset_performance_records.insert_one(make_doc(
            workspace_slug=WS, asset_render_id=RENDER_ID, platform="instagram",
            performance_score=7.5, simulation_only=True, outbound_actions_taken=0,
        ))
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/creative-performance-summaries/generate", json={
                "workspace_slug": WS,
                "asset_render_id": RENDER_ID,
            })
        assert resp.status_code == 200
        item = resp.json()["item"]
        assert item["performance_score"] is not None

    def test_summary_is_upserted(self):
        """Calling generate twice for the same asset should not duplicate summaries."""
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            client.post("/creative-performance-summaries/generate", json={
                "workspace_slug": WS, "asset_render_id": RENDER_ID,
            })
            client.post("/creative-performance-summaries/generate", json={
                "workspace_slug": WS, "asset_render_id": RENDER_ID,
            })
        count = len([
            d for d in fake_db.creative_performance_summaries.documents
            if d.get("asset_render_id") == RENDER_ID and d.get("workspace_slug") == WS
        ])
        assert count == 1

    def test_list_summaries(self):
        fake_db = FakeDatabase()
        fake_db.creative_performance_summaries.insert_one(make_doc(
            workspace_slug=WS, asset_render_id=RENDER_ID, performance_score=6.0,
            simulation_only=True, outbound_actions_taken=0,
        ))
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.get(f"/creative-performance-summaries?workspace_slug={WS}")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 1


# ---------------------------------------------------------------------------
# TestPerformanceRecommendations
# ---------------------------------------------------------------------------

class TestPerformanceRecommendations:
    def test_recommendations_are_advisory_only(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.get(f"/creative-performance-summaries/recommendations?workspace_slug={WS}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["advisory_only"] is True

    def test_recommendations_empty_with_no_summaries(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.get(f"/creative-performance-summaries/recommendations?workspace_slug={WS}")
        data = resp.json()
        assert data["based_on_summary_count"] == 0
        assert data["top_hook_types"] == []
        assert data["top_prompt_types"] == []
        assert data["top_platforms"] == []

    def test_recommendations_do_not_auto_approve(self):
        """Generating recommendations must NOT change any snippet approval status."""
        fake_db = FakeDatabase()
        snippet_id = ObjectId()
        fake_db.content_snippets.insert_one(make_doc(
            _id=snippet_id, workspace_slug=WS, status="pending",
            simulation_only=True, outbound_actions_taken=0,
        ))
        fake_db.creative_performance_summaries.insert_one(make_doc(
            workspace_slug=WS, asset_render_id=RENDER_ID, performance_score=9.9,
            simulation_only=True, outbound_actions_taken=0,
        ))
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            client.get(f"/creative-performance-summaries/recommendations?workspace_slug={WS}")
        snippet = fake_db.content_snippets.find_one({"_id": snippet_id})
        assert snippet["status"] == "pending"

    def test_generate_summary_does_not_auto_approve(self):
        """Generating a high-scoring summary must NOT auto-approve any snippet."""
        fake_db = FakeDatabase()
        snippet_id = ObjectId()
        fake_db.content_snippets.insert_one(make_doc(
            _id=snippet_id, workspace_slug=WS, status="pending",
            simulation_only=True, outbound_actions_taken=0,
        ))
        fake_db.asset_performance_records.insert_one(make_doc(
            workspace_slug=WS, asset_render_id=RENDER_ID, performance_score=9.9,
            simulation_only=True, outbound_actions_taken=0,
        ))
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            client.post("/creative-performance-summaries/generate", json={
                "workspace_slug": WS, "asset_render_id": RENDER_ID,
            })
        snippet = fake_db.content_snippets.find_one({"_id": snippet_id})
        assert snippet["status"] == "pending"


# ---------------------------------------------------------------------------
# TestSafetyInvariants
# ---------------------------------------------------------------------------

class TestSafetyInvariants:
    def test_publish_log_simulation_only_true(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/manual-publish-logs", json={
                "workspace_slug": WS, "asset_render_id": RENDER_ID, "platform": "youtube",
            })
        assert resp.json()["item"]["simulation_only"] is True

    def test_performance_record_simulation_only_true(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/asset-performance-records", json=VALID_PERF_PAYLOAD)
        assert resp.json()["item"]["simulation_only"] is True

    def test_summary_simulation_only_true(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/creative-performance-summaries/generate", json={
                "workspace_slug": WS, "asset_render_id": RENDER_ID,
            })
        assert resp.json()["item"]["simulation_only"] is True

    def test_publish_log_outbound_actions_zero(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/manual-publish-logs", json={
                "workspace_slug": WS, "asset_render_id": RENDER_ID, "platform": "facebook",
            })
        assert resp.json()["item"]["outbound_actions_taken"] == 0

    def test_performance_record_outbound_zero(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/asset-performance-records", json=VALID_PERF_PAYLOAD)
        assert resp.json()["item"]["outbound_actions_taken"] == 0

    def test_summary_outbound_zero(self):
        fake_db = FakeDatabase()
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.post("/creative-performance-summaries/generate", json={
                "workspace_slug": WS, "asset_render_id": RENDER_ID,
            })
        assert resp.json()["item"]["outbound_actions_taken"] == 0


# ---------------------------------------------------------------------------
# TestWorkspaceIsolation
# ---------------------------------------------------------------------------

class TestWorkspaceIsolation:
    def test_publish_logs_workspace_isolation(self):
        fake_db = FakeDatabase()
        fake_db.manual_publish_logs.insert_one(make_doc(
            workspace_slug="other-ws", platform="instagram",
            simulation_only=True, outbound_actions_taken=0,
        ))
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.get(f"/manual-publish-logs?workspace_slug={WS}")
        assert resp.json()["items"] == []

    def test_performance_records_workspace_isolation(self):
        fake_db = FakeDatabase()
        fake_db.asset_performance_records.insert_one(make_doc(
            workspace_slug="other-ws", platform="tiktok", performance_score=5.0,
            simulation_only=True, outbound_actions_taken=0,
        ))
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.get(f"/asset-performance-records?workspace_slug={WS}")
        assert resp.json()["items"] == []

    def test_summaries_workspace_isolation(self):
        fake_db = FakeDatabase()
        fake_db.creative_performance_summaries.insert_one(make_doc(
            workspace_slug="other-ws", asset_render_id=RENDER_ID, performance_score=7.0,
            simulation_only=True, outbound_actions_taken=0,
        ))
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.get(f"/creative-performance-summaries?workspace_slug={WS}")
        assert resp.json()["items"] == []


# ---------------------------------------------------------------------------
# TestClientIsolation
# ---------------------------------------------------------------------------

class TestClientIsolation:
    def test_publish_logs_client_isolation(self):
        """Logs from a different client_id should not appear in another client's results."""
        fake_db = FakeDatabase()
        other_client_id = str(ObjectId())
        fake_db.manual_publish_logs.insert_one(make_doc(
            workspace_slug=WS, client_id=other_client_id, platform="instagram",
            simulation_only=True, outbound_actions_taken=0,
        ))
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.get(f"/manual-publish-logs?workspace_slug={WS}&client_id={CLIENT_ID}")
        assert resp.json()["items"] == []

    def test_performance_records_client_isolation(self):
        fake_db = FakeDatabase()
        other_client_id = str(ObjectId())
        fake_db.asset_performance_records.insert_one(make_doc(
            workspace_slug=WS, client_id=other_client_id, platform="tiktok", performance_score=5.0,
            simulation_only=True, outbound_actions_taken=0,
        ))
        fake_get_client, fake_get_database = make_db_patch(fake_db)
        with patch("main.get_client", fake_get_client), patch("main.get_database", fake_get_database):
            client = TestClient(app)
            resp = client.get(f"/asset-performance-records?workspace_slug={WS}&client_id={CLIENT_ID}")
        assert resp.json()["items"] == []
