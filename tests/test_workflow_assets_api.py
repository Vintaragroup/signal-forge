from datetime import datetime, timezone
from pathlib import Path
import sys

from bson import ObjectId
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

import main
from main import app


class InsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, sort_spec):
        if isinstance(sort_spec, str):
            key = sort_spec
            reverse = False
        else:
            key, direction = sort_spec[0]
            reverse = direction < 0
        self.documents.sort(key=lambda item: item.get(key) or datetime.min.replace(tzinfo=timezone.utc), reverse=reverse)
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
        return FakeCursor([document for document in self.documents if self.matches(document, query)])

    def find_one(self, query, sort=None):
        documents = list(self.find(query))
        if sort:
            documents = list(FakeCursor(documents).sort(sort))
        return documents[0] if documents else None

    def insert_one(self, document):
        if "_id" not in document:
            document["_id"] = ObjectId()
        self.documents.append(document)
        return InsertResult(document["_id"])

    def update_one(self, query, update, upsert=False):
        document = self.find_one(query)
        if not document:
            if not upsert:
                return None
            document = {"_id": ObjectId()}
            self.documents.append(document)
        for key, value in (update.get("$set") or {}).items():
            document[key] = value
        for key, value in (update.get("$push") or {}).items():
            document.setdefault(key, []).append(value)
        return None

    def matches(self, document, query):
        for key, value in query.items():
            if key == "$or":
                if not any(self.matches(document, condition) for condition in value):
                    return False
                continue
            if isinstance(value, dict):
                if "$exists" in value:
                    exists = key in document
                    if exists != value["$exists"]:
                        return False
                    continue
                if "$in" in value:
                    if document.get(key) not in value["$in"]:
                        return False
                    continue
            if document.get(key) != value:
                return False
        return True


class FakeDatabase:
    def __init__(self):
        approved_asset_id = ObjectId()
        queued_asset_id = ObjectId()
        published_asset_id = ObjectId()
        rejected_asset_id = ObjectId()
        missing_distribution_id = ObjectId()
        self.workflow_assets = FakeCollection(
            [
                {
                    "_id": approved_asset_id,
                    "run_id": "run-1",
                    "asset_type": "content_idea",
                    "title": "Approved asset",
                    "approval_state": "approved",
                    "distribution_state": "not_queued",
                    "distribution_channel": None,
                    "distribution_notes": None,
                    "published_at": None,
                    "published_url": None,
                    "created_at": datetime.now(timezone.utc),
                },
                {
                    "_id": queued_asset_id,
                    "run_id": "run-1",
                    "asset_type": "content_idea",
                    "title": "Queued asset",
                    "approval_state": "approved",
                    "distribution_state": "queued",
                    "distribution_channel": "LinkedIn",
                    "distribution_notes": "Post tomorrow morning.",
                    "published_at": None,
                    "published_url": None,
                    "created_at": datetime.now(timezone.utc),
                },
                {
                    "_id": published_asset_id,
                    "run_id": "run-1",
                    "asset_type": "content_idea",
                    "title": "Published asset",
                    "approval_state": "approved",
                    "distribution_state": "published",
                    "distribution_channel": "LinkedIn",
                    "distribution_notes": "Already live.",
                    "published_at": datetime.now(timezone.utc),
                    "published_url": "https://example.com/post",
                    "created_at": datetime.now(timezone.utc),
                },
                {
                    "_id": rejected_asset_id,
                    "run_id": "run-1",
                    "asset_type": "content_idea",
                    "title": "Rejected asset",
                    "approval_state": "rejected",
                    "distribution_state": "not_queued",
                    "created_at": datetime.now(timezone.utc),
                },
                {
                    "_id": missing_distribution_id,
                    "run_id": "run-1",
                    "asset_type": "content_idea",
                    "title": "Legacy approved asset",
                    "approval_state": "approved",
                    "created_at": datetime.now(timezone.utc),
                },
            ]
        )


class FakeClient:
    def close(self):
        return None


def patch_database(monkeypatch, db):
    monkeypatch.setattr(main, "get_client", lambda: FakeClient())
    monkeypatch.setattr(main, "get_database", lambda _client: db)


def test_workflow_assets_not_queued_filter_includes_legacy_records(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)

    response = TestClient(app).get("/workflow-assets?run_id=run-1&distribution_state=not_queued")

    assert response.status_code == 200
    payload = response.json()
    titles = [item["title"] for item in payload["items"]]
    assert "Approved asset" in titles
    assert "Legacy approved asset" in titles
    legacy = next(item for item in payload["items"] if item["title"] == "Legacy approved asset")
    assert legacy["distribution_state"] == "not_queued"
    assert legacy["distribution_channel"] is None
    assert legacy["published_url"] is None


def test_queue_distribution_updates_metadata(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)
    asset_id = str(db.workflow_assets.documents[0]["_id"])

    response = TestClient(app).patch(
        f"/workflow-assets/{asset_id}/distribution",
        json={
            "action": "queue",
            "distribution_channel": "LinkedIn organic",
            "distribution_notes": "Queue after caption review.",
        },
    )

    assert response.status_code == 200
    item = response.json()["item"]
    assert item["distribution_state"] == "queued"
    assert item["distribution_channel"] == "LinkedIn organic"
    assert item["distribution_notes"] == "Queue after caption review."


def test_mark_published_sets_terminal_distribution_fields(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)
    queued_asset_id = str(db.workflow_assets.documents[1]["_id"])

    response = TestClient(app).patch(
        f"/workflow-assets/{queued_asset_id}/distribution",
        json={
            "action": "mark_published",
            "distribution_channel": "LinkedIn organic",
            "distribution_notes": "Posted manually.",
            "published_url": "https://linkedin.com/posts/example",
        },
    )

    assert response.status_code == 200
    item = response.json()["item"]
    assert item["distribution_state"] == "published"
    assert item["published_at"]
    assert item["published_url"] == "https://linkedin.com/posts/example"


def test_distribution_route_blocks_non_approved_assets(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)
    rejected_asset_id = str(db.workflow_assets.documents[3]["_id"])

    response = TestClient(app).patch(
        f"/workflow-assets/{rejected_asset_id}/distribution",
        json={"action": "queue", "distribution_channel": "LinkedIn"},
    )

    assert response.status_code == 400
    assert "Only approved workflow assets" in response.json()["detail"]


def test_distribution_route_blocks_invalid_state_transition(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)
    published_asset_id = str(db.workflow_assets.documents[2]["_id"])

    response = TestClient(app).patch(
        f"/workflow-assets/{published_asset_id}/distribution",
        json={"action": "unqueue"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot unqueue from distribution_state=published."


def test_distribution_route_allows_archive_from_published(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)
    published_asset_id = str(db.workflow_assets.documents[2]["_id"])

    response = TestClient(app).patch(
        f"/workflow-assets/{published_asset_id}/distribution",
        json={"action": "archive"},
    )

    assert response.status_code == 200
    item = response.json()["item"]
    assert item["distribution_state"] == "archived"
    assert item["published_url"] == "https://example.com/post"