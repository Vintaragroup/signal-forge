from datetime import datetime, timezone

from bson import ObjectId
from fastapi.testclient import TestClient

import main
from main import app


class InsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, sort_spec):
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
        self.workspaces = FakeCollection([
            {
                "_id": ObjectId(),
                "slug": "default",
                "name": "Default Workspace",
                "type": "internal",
                "module": "",
                "notes": "",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        ])
        self.contacts = FakeCollection([
            {"_id": ObjectId(), "name": "Alice", "workspace_slug": "acme", "module": "contractor_growth"},
            {"_id": ObjectId(), "name": "Bob", "workspace_slug": "default", "module": "contractor_growth"},
        ])
        self.message_drafts = FakeCollection([])
        self.deals = FakeCollection([])


class FakeClient:
    def close(self):
        return None


def make_client(db):
    client = TestClient(app)
    fake_client = FakeClient()

    def fake_get_client():
        return fake_client

    def fake_get_database(_client):
        return db

    import pytest

    return client, fake_get_client, fake_get_database


def test_list_workspaces_returns_existing(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/workspaces")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["slug"] == "default"


def test_list_workspaces_seeds_default_when_empty(monkeypatch):
    db = FakeDatabase()
    db.workspaces = FakeCollection([])  # empty
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/workspaces")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["slug"] == "default"


def test_create_workspace(monkeypatch):
    db = FakeDatabase()
    db.workspaces = FakeCollection([])
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/workspaces", json={"name": "Acme Corp", "type": "client", "module": "contractor_growth"})
    assert response.status_code == 200
    data = response.json()
    assert data["item"]["slug"] == "acme-corp"
    assert data["item"]["name"] == "Acme Corp"
    assert data["item"]["status"] == "active"


def test_create_workspace_duplicate_slug_rejected(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    # "default" slug already exists in FakeDatabase
    response = client.post("/workspaces", json={"name": "default"})
    assert response.status_code == 409


def test_create_workspace_empty_name_rejected(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/workspaces", json={"name": "   "})
    assert response.status_code == 400


def test_get_workspace_by_slug(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/workspaces/default")
    assert response.status_code == 200
    assert response.json()["item"]["slug"] == "default"


def test_get_workspace_not_found(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/workspaces/nonexistent")
    assert response.status_code == 404


def test_update_workspace_status(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.patch("/workspaces/default/status", json={"status": "paused"})
    assert response.status_code == 200
    assert response.json()["item"]["status"] == "paused"


def test_contacts_filtered_by_workspace_slug(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/contacts?workspace_slug=acme")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Alice"


def test_contacts_all_when_no_workspace_filter(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/contacts")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
