"""
Phase 6A — Backend tests for /client-profiles and /workflow-definitions endpoints.
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
        self.workspaces = FakeCollection([
            {
                "_id": ObjectId(),
                "slug": "acme-corp",
                "name": "Acme Corp",
                "type": "client",
                "module": "contractor_growth",
                "notes": "",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        ])
        self.admin_client_profiles = FakeCollection([])
        self.workflow_definitions = FakeCollection([])


class FakeClient:
    def close(self):
        return None


def make_test_client(db):
    client = TestClient(app)
    fake_client = FakeClient()
    return client, fake_client, db


# ── Client Profile tests ──────────────────────────────────────────────────────


def test_create_client_profile(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/admin/client-profiles", json={
        "slug": "john-maxwell",
        "display_name": "John Maxwell",
        "system_profile_id": "executive_growth",
        "module": "media_growth",
        "tier": "growth",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["item"]["slug"] == "john-maxwell"
    assert data["item"]["display_name"] == "John Maxwell"
    assert data["item"]["system_profile_id"] == "executive_growth"
    assert data["item"]["module"] == "media_growth"
    assert data["item"]["status"] == "active"


def test_create_client_profile_duplicate_slug_rejected(monkeypatch):
    db = FakeDatabase()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    db.admin_client_profiles = FakeCollection([
        {"_id": ObjectId(), "slug": "john-maxwell", "display_name": "John Maxwell",
         "status": "active", "created_at": now, "updated_at": now}
    ])
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/admin/client-profiles", json={
        "slug": "john-maxwell",
        "display_name": "John Maxwell Duplicate",
    })
    assert response.status_code == 409


def test_create_client_profile_invalid_workspace_slug_rejected(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/admin/client-profiles", json={
        "slug": "test-profile",
        "display_name": "Test Profile",
        "workspace_slug": "nonexistent-workspace",
    })
    assert response.status_code == 422


def test_create_client_profile_valid_workspace_slug_accepted(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/admin/client-profiles", json={
        "slug": "acme-profile",
        "display_name": "Acme Profile",
        "workspace_slug": "acme-corp",  # exists in FakeDatabase
    })
    assert response.status_code == 200
    assert response.json()["item"]["workspace_slug"] == "acme-corp"


def test_list_client_profiles(monkeypatch):
    db = FakeDatabase()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    db.admin_client_profiles = FakeCollection([
        {"_id": ObjectId(), "slug": "profile-a", "display_name": "Profile A",
         "status": "active", "created_at": now, "updated_at": now},
        {"_id": ObjectId(), "slug": "profile-b", "display_name": "Profile B",
         "status": "archived", "created_at": now, "updated_at": now},
    ])
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/admin/client-profiles")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2


def test_list_client_profiles_filtered_by_status(monkeypatch):
    db = FakeDatabase()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    db.admin_client_profiles = FakeCollection([
        {"_id": ObjectId(), "slug": "profile-a", "display_name": "A",
         "status": "active", "created_at": now, "updated_at": now},
        {"_id": ObjectId(), "slug": "profile-b", "display_name": "B",
         "status": "archived", "created_at": now, "updated_at": now},
    ])
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/admin/client-profiles?status=active")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["slug"] == "profile-a"


def test_get_client_profile_by_slug(monkeypatch):
    db = FakeDatabase()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    db.admin_client_profiles = FakeCollection([
        {"_id": ObjectId(), "slug": "john-maxwell", "display_name": "John Maxwell",
         "status": "active", "created_at": now, "updated_at": now},
    ])
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/admin/client-profiles/john-maxwell")
    assert response.status_code == 200
    assert response.json()["item"]["slug"] == "john-maxwell"


def test_get_client_profile_not_found(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/admin/client-profiles/does-not-exist")
    assert response.status_code == 404


def test_patch_client_profile(monkeypatch):
    db = FakeDatabase()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    db.admin_client_profiles = FakeCollection([
        {"_id": ObjectId(), "slug": "john-maxwell", "display_name": "John Maxwell",
         "industry": "", "status": "active", "created_at": now, "updated_at": now},
    ])
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.patch("/admin/client-profiles/john-maxwell", json={"industry": "Leadership"})
    assert response.status_code == 200
    assert response.json()["item"]["industry"] == "Leadership"


def test_patch_client_profile_not_found(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.patch("/admin/client-profiles/ghost", json={"industry": "X"})
    assert response.status_code == 404


def test_patch_client_profile_status(monkeypatch):
    db = FakeDatabase()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    db.admin_client_profiles = FakeCollection([
        {"_id": ObjectId(), "slug": "john-maxwell", "display_name": "John Maxwell",
         "status": "active", "created_at": now, "updated_at": now},
    ])
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.patch("/admin/client-profiles/john-maxwell/status", json={"status": "archived"})
    assert response.status_code == 200
    assert response.json()["item"]["status"] == "archived"


def test_patch_client_profile_status_not_found(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.patch("/admin/client-profiles/ghost/status", json={"status": "archived"})
    assert response.status_code == 404


# ── Workflow Definition tests ─────────────────────────────────────────────────


def test_create_workflow_definition(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/admin/workflow-definitions", json={
        "slug": "exec-growth-v1",
        "display_name": "Executive Growth — v1",
        "system_profile_id": "executive_growth",
        "module": "media_growth",
        "stages": [
            {"stage_number": 1, "label": "Identify Targets", "required": True},
            {"stage_number": 2, "label": "Draft Content", "required": True},
        ],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["item"]["slug"] == "exec-growth-v1"
    assert len(data["item"]["stages"]) == 2
    assert data["item"]["system_profile_id"] == "executive_growth"
    assert data["item"]["module"] == "media_growth"


def test_create_workflow_definition_duplicate_slug_rejected(monkeypatch):
    db = FakeDatabase()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    db.workflow_definitions = FakeCollection([
        {"_id": ObjectId(), "slug": "exec-growth-v1", "display_name": "Exec v1",
         "stages": [], "status": "active", "created_at": now, "updated_at": now},
    ])
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/admin/workflow-definitions", json={
        "slug": "exec-growth-v1",
        "display_name": "Duplicate",
        "stages": [],
    })
    assert response.status_code == 409


def test_create_workflow_definition_invalid_stage_number_rejected(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/admin/workflow-definitions", json={
        "slug": "bad-stages",
        "display_name": "Bad Stages",
        "stages": [{"stage_number": 8, "label": "Beyond 7", "required": True}],
    })
    assert response.status_code == 422


def test_list_workflow_definitions(monkeypatch):
    db = FakeDatabase()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    db.workflow_definitions = FakeCollection([
        {"_id": ObjectId(), "slug": "def-a", "display_name": "Def A",
         "stages": [], "status": "active", "created_at": now, "updated_at": now},
        {"_id": ObjectId(), "slug": "def-b", "display_name": "Def B",
         "stages": [], "status": "active", "created_at": now, "updated_at": now},
    ])
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/admin/workflow-definitions")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


def test_get_workflow_definition_by_slug(monkeypatch):
    db = FakeDatabase()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    db.workflow_definitions = FakeCollection([
        {"_id": ObjectId(), "slug": "exec-growth-v1", "display_name": "Exec v1",
         "stages": [], "status": "active", "created_at": now, "updated_at": now},
    ])
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/admin/workflow-definitions/exec-growth-v1")
    assert response.status_code == 200
    assert response.json()["item"]["slug"] == "exec-growth-v1"


def test_get_workflow_definition_not_found(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/admin/workflow-definitions/ghost")
    assert response.status_code == 404


def test_patch_workflow_definition(monkeypatch):
    db = FakeDatabase()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    db.workflow_definitions = FakeCollection([
        {"_id": ObjectId(), "slug": "exec-growth-v1", "display_name": "Exec v1",
         "stages": [], "notes": "", "status": "active", "created_at": now, "updated_at": now},
    ])
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.patch("/admin/workflow-definitions/exec-growth-v1", json={"notes": "Updated notes"})
    assert response.status_code == 200
    assert response.json()["item"]["notes"] == "Updated notes"


def test_patch_workflow_definition_stages_validated(monkeypatch):
    db = FakeDatabase()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    db.workflow_definitions = FakeCollection([
        {"_id": ObjectId(), "slug": "exec-growth-v1", "display_name": "Exec v1",
         "stages": [], "status": "active", "created_at": now, "updated_at": now},
    ])
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.patch("/admin/workflow-definitions/exec-growth-v1", json={
        "stages": [{"stage_number": 0, "label": "Bad"}]
    })
    assert response.status_code == 422


# ── Workflow definition lookup via client profile ─────────────────────────────


def test_client_profile_workflow_definition_lookup(monkeypatch):
    db = FakeDatabase()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    db.workflow_definitions = FakeCollection([
        {"_id": ObjectId(), "slug": "exec-growth-v1", "display_name": "Exec v1",
         "stages": [], "status": "active", "created_at": now, "updated_at": now},
    ])
    db.admin_client_profiles = FakeCollection([
        {"_id": ObjectId(), "slug": "john-maxwell", "display_name": "John Maxwell",
         "workflow_definition_id": "exec-growth-v1", "status": "active",
         "created_at": now, "updated_at": now},
    ])
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/admin/client-profiles/john-maxwell/workflow-definition")
    assert response.status_code == 200
    assert response.json()["item"]["slug"] == "exec-growth-v1"


def test_client_profile_workflow_definition_no_link_returns_404(monkeypatch):
    db = FakeDatabase()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    db.admin_client_profiles = FakeCollection([
        {"_id": ObjectId(), "slug": "john-maxwell", "display_name": "John Maxwell",
         "workflow_definition_id": "", "status": "active",
         "created_at": now, "updated_at": now},
    ])
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/admin/client-profiles/john-maxwell/workflow-definition")
    assert response.status_code == 404


def test_client_profile_workflow_definition_profile_not_found(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.get("/admin/client-profiles/ghost/workflow-definition")
    assert response.status_code == 404


# ── Workspace still works without client_profile_id ──────────────────────────


def test_create_workspace_still_works_without_client_profile_id(monkeypatch):
    db = FakeDatabase()
    db.workspaces = FakeCollection([])
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/workspaces", json={"name": "Test WS", "type": "client"})
    assert response.status_code == 200
    data = response.json()
    assert data["item"]["slug"] == "test-ws"
    assert "client_profile_id" not in data["item"]


def test_create_workspace_with_client_profile_id(monkeypatch):
    db = FakeDatabase()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    db.workspaces = FakeCollection([])
    db.admin_client_profiles = FakeCollection([
        {"_id": ObjectId(), "slug": "john-maxwell", "display_name": "John Maxwell",
         "status": "active", "created_at": now, "updated_at": now},
    ])
    fake_client = FakeClient()
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/workspaces", json={
        "name": "Maxwell Workspace",
        "type": "client",
        "client_profile_id": "john-maxwell",
    })
    assert response.status_code == 200
    assert response.json()["item"]["client_profile_id"] == "john-maxwell"
