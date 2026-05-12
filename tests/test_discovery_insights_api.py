"""
Phase 6C — Backend tests for /discovery-insights endpoints.
"""
from datetime import datetime, timezone

from bson import ObjectId
from fastapi.testclient import TestClient

import main
from main import app

# ── Shared fakes ──────────────────────────────────────────────────────────────


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
        return FakeCursor([doc for doc in self.documents if self._matches(doc, query)])

    def find_one(self, query):
        docs = list(self.find(query))
        return docs[0] if docs else None

    def insert_one(self, document):
        if "_id" not in document:
            document["_id"] = ObjectId()
        self.documents.append(document)
        return InsertResult(document["_id"])

    def update_one(self, query, update, upsert=False):
        doc = self.find_one(query)
        if not doc:
            return None
        for key, value in (update.get("$set") or {}).items():
            doc[key] = value
        return None

    def _matches(self, document, query):
        for key, value in query.items():
            if key == "$or":
                if not any(self._matches(document, cond) for cond in value):
                    return False
                continue
            if document.get(key) != value:
                return False
        return True


class FakeDatabase:
    def __init__(self):
        now = datetime(2024, 1, 1, tzinfo=timezone.utc)
        self.discovery_insights = FakeCollection([])
        self.workflow_assets = FakeCollection([
            {
                "_id": ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa"),
                "run_id": "run-1",
                "title": "Test Asset",
                "asset_type": "content_idea",
                "approval_state": "needs_review",
                "distribution_state": "not_queued",
                "created_at": now,
                "updated_at": now,
            }
        ])


class FakeClient:
    def close(self):
        return None


def _make_client(db):
    client = TestClient(app)
    fake_client = FakeClient()
    return client, fake_client


VALID_PAYLOAD = {
    "workspace_slug": "acme-corp",
    "insight_type": "content_opportunity",
    "title": "Podcast Content Gap",
    "summary": "Strong demand for leadership content with low competition.",
    "confidence_score": 0.85,
    "evidence": [
        {
            "platform": "YouTube",
            "signal_type": "search_trend",
            "metric": "monthly_searches",
            "value": 45000.0,
            "keyword": "leadership lessons",
            "growth_pct": 32.5,
            "notes": "Growing consistently over 3 months.",
        }
    ],
    "recommendation": {
        "recommended_asset_types": ["script_draft", "video_prompt"],
        "recommended_platforms": ["YouTube Shorts", "LinkedIn"],
        "recommended_next_stage": "generate_content",
        "rationale": "High-intent keyword with strong organic growth.",
    },
    "source_agent": "outreach",
    "source_run_id": "run-abc-123",
    "status": "pending_review",
}


# ── CREATE ────────────────────────────────────────────────────────────────────


def test_create_discovery_insight_success(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/discovery-insights", json=VALID_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    item = body["item"]
    assert item["workspace_slug"] == "acme-corp"
    assert item["title"] == "Podcast Content Gap"
    assert item["confidence_score"] == 0.85
    assert item["status"] == "pending_review"
    assert item["source_run_id"] == "run-abc-123"
    assert len(item["evidence"]) == 1
    assert item["evidence"][0]["platform"] == "YouTube"
    assert item["recommendation"]["recommended_next_stage"] == "generate_content"
    assert item["approved_by"] is None
    assert item["approved_at"] is None
    assert "created_at" in item


def test_create_discovery_insight_minimal(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/discovery-insights", json={
        "workspace_slug": "test-ws",
        "insight_type": "market_signal",
        "title": "Minimal Insight",
        "summary": "Test summary.",
    })
    assert response.status_code == 200
    item = response.json()["item"]
    assert item["confidence_score"] == 0.5
    assert item["evidence"] == []
    assert item["recommendation"] is None
    assert item["linked_workflow_asset_ids"] == []


def test_create_discovery_insight_missing_workspace(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/discovery-insights", json={
        "workspace_slug": "",
        "insight_type": "test",
        "title": "T",
        "summary": "S",
    })
    assert response.status_code == 400
    assert "workspace_slug" in response.json()["detail"].lower()


def test_create_discovery_insight_missing_title(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/discovery-insights", json={
        "workspace_slug": "ws",
        "insight_type": "test",
        "title": "",
        "summary": "S",
    })
    assert response.status_code == 400


def test_create_discovery_insight_invalid_confidence(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/discovery-insights", json={
        **VALID_PAYLOAD,
        "confidence_score": 1.5,
    })
    assert response.status_code == 422


def test_create_discovery_insight_invalid_status(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/discovery-insights", json={
        **VALID_PAYLOAD,
        "status": "not_a_valid_status",
    })
    assert response.status_code == 422


# ── LIST / FILTER ─────────────────────────────────────────────────────────────


def test_list_discovery_insights_empty(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/discovery-insights")
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["count"] == 0


def test_list_discovery_insights_filter_by_workspace(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    # Create two insights in different workspaces
    client.post("/discovery-insights", json={**VALID_PAYLOAD, "workspace_slug": "ws-a"})
    client.post("/discovery-insights", json={**VALID_PAYLOAD, "workspace_slug": "ws-b"})

    resp = client.get("/discovery-insights?workspace_slug=ws-a")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["workspace_slug"] == "ws-a"


def test_list_discovery_insights_filter_by_status(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    client.post("/discovery-insights", json={**VALID_PAYLOAD, "status": "pending_review"})
    client.post("/discovery-insights", json={**VALID_PAYLOAD, "status": "approved"})

    resp = client.get("/discovery-insights?status=approved")
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "approved"


def test_list_discovery_insights_filter_by_source_run_id(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    client.post("/discovery-insights", json={**VALID_PAYLOAD, "source_run_id": "run-111"})
    client.post("/discovery-insights", json={**VALID_PAYLOAD, "source_run_id": "run-222"})

    resp = client.get("/discovery-insights?source_run_id=run-111")
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["source_run_id"] == "run-111"


# ── GET BY ID ─────────────────────────────────────────────────────────────────


def test_get_discovery_insight_by_id(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    create_resp = client.post("/discovery-insights", json=VALID_PAYLOAD)
    insight_id = create_resp.json()["item"]["_id"]

    get_resp = client.get(f"/discovery-insights/{insight_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["item"]["_id"] == insight_id
    assert get_resp.json()["item"]["title"] == "Podcast Content Gap"


def test_get_discovery_insight_not_found(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.get(f"/discovery-insights/{str(ObjectId())}")
    assert resp.status_code == 404


def test_get_discovery_insight_invalid_id(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.get("/discovery-insights/not-a-valid-objectid")
    assert resp.status_code == 400


# ── UPDATE ────────────────────────────────────────────────────────────────────


def test_update_discovery_insight_title(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    create_resp = client.post("/discovery-insights", json=VALID_PAYLOAD)
    insight_id = create_resp.json()["item"]["_id"]

    patch_resp = client.patch(f"/discovery-insights/{insight_id}", json={"title": "Updated Title"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["item"]["title"] == "Updated Title"


def test_update_discovery_insight_confidence_score(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    create_resp = client.post("/discovery-insights", json=VALID_PAYLOAD)
    insight_id = create_resp.json()["item"]["_id"]

    patch_resp = client.patch(f"/discovery-insights/{insight_id}", json={"confidence_score": 0.95})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["item"]["confidence_score"] == 0.95


def test_update_discovery_insight_invalid_confidence(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    create_resp = client.post("/discovery-insights", json=VALID_PAYLOAD)
    insight_id = create_resp.json()["item"]["_id"]

    patch_resp = client.patch(f"/discovery-insights/{insight_id}", json={"confidence_score": 2.0})
    assert patch_resp.status_code == 422


def test_update_discovery_insight_linked_assets(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    create_resp = client.post("/discovery-insights", json=VALID_PAYLOAD)
    insight_id = create_resp.json()["item"]["_id"]

    asset_ids = [str(ObjectId()), str(ObjectId())]
    patch_resp = client.patch(f"/discovery-insights/{insight_id}", json={
        "linked_workflow_asset_ids": asset_ids,
    })
    assert patch_resp.status_code == 200
    assert patch_resp.json()["item"]["linked_workflow_asset_ids"] == asset_ids


def test_update_discovery_insight_recommendation(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    create_resp = client.post("/discovery-insights", json=VALID_PAYLOAD)
    insight_id = create_resp.json()["item"]["_id"]

    patch_resp = client.patch(f"/discovery-insights/{insight_id}", json={
        "recommendation": {
            "recommended_asset_types": ["script_draft"],
            "recommended_platforms": ["TikTok"],
            "recommended_next_stage": "review",
            "rationale": "Updated rationale.",
        }
    })
    assert patch_resp.status_code == 200
    rec = patch_resp.json()["item"]["recommendation"]
    assert rec["recommended_next_stage"] == "review"
    assert "TikTok" in rec["recommended_platforms"]


def test_update_discovery_insight_not_found(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.patch(f"/discovery-insights/{str(ObjectId())}", json={"title": "x"})
    assert resp.status_code == 404


# ── STATUS UPDATE ─────────────────────────────────────────────────────────────


def test_update_status_to_approved(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    create_resp = client.post("/discovery-insights", json=VALID_PAYLOAD)
    insight_id = create_resp.json()["item"]["_id"]

    resp = client.patch(f"/discovery-insights/{insight_id}/status", json={"status": "approved"})
    assert resp.status_code == 200
    item = resp.json()["item"]
    assert item["status"] == "approved"
    assert item["approved_at"] is not None


def test_update_status_to_deferred(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    create_resp = client.post("/discovery-insights", json=VALID_PAYLOAD)
    insight_id = create_resp.json()["item"]["_id"]

    resp = client.patch(f"/discovery-insights/{insight_id}/status", json={"status": "deferred"})
    assert resp.status_code == 200
    assert resp.json()["item"]["status"] == "deferred"


def test_update_status_invalid_value(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    create_resp = client.post("/discovery-insights", json=VALID_PAYLOAD)
    insight_id = create_resp.json()["item"]["_id"]

    resp = client.patch(f"/discovery-insights/{insight_id}/status", json={"status": "nope"})
    assert resp.status_code == 422


def test_update_status_not_found(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.patch(f"/discovery-insights/{str(ObjectId())}/status", json={"status": "approved"})
    assert resp.status_code == 404


# ── LINEAGE: link-insight ─────────────────────────────────────────────────────


def test_link_workflow_asset_to_insight(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    asset_id = str(db.workflow_assets.documents[0]["_id"])
    insight_id = str(ObjectId())

    resp = client.patch(f"/workflow-assets/{asset_id}/link-insight", json={
        "source_discovery_insight_id": insight_id
    })
    assert resp.status_code == 200
    item = resp.json()["item"]
    assert item["source_discovery_insight_id"] == insight_id


def test_link_workflow_asset_clears_insight(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    asset_id = str(db.workflow_assets.documents[0]["_id"])

    # First link it
    insight_id = str(ObjectId())
    client.patch(f"/workflow-assets/{asset_id}/link-insight", json={
        "source_discovery_insight_id": insight_id
    })

    # Then clear it
    resp = client.patch(f"/workflow-assets/{asset_id}/link-insight", json={
        "source_discovery_insight_id": ""
    })
    assert resp.status_code == 200
    assert resp.json()["item"]["source_discovery_insight_id"] is None


def test_link_workflow_asset_not_found(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.patch(f"/workflow-assets/{str(ObjectId())}/link-insight", json={
        "source_discovery_insight_id": str(ObjectId())
    })
    assert resp.status_code == 404


def test_link_workflow_asset_invalid_id(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.patch("/workflow-assets/bad-id/link-insight", json={
        "source_discovery_insight_id": str(ObjectId())
    })
    assert resp.status_code == 400


# ── PERSISTENCE: full round-trip ──────────────────────────────────────────────


def test_insight_persists_evidence_and_recommendation(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    create_resp = client.post("/discovery-insights", json=VALID_PAYLOAD)
    insight_id = create_resp.json()["item"]["_id"]

    get_resp = client.get(f"/discovery-insights/{insight_id}")
    item = get_resp.json()["item"]

    assert item["evidence"][0]["keyword"] == "leadership lessons"
    assert item["evidence"][0]["growth_pct"] == 32.5
    assert item["recommendation"]["rationale"] == "High-intent keyword with strong organic growth."
    assert "script_draft" in item["recommendation"]["recommended_asset_types"]
