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
        if isinstance(sort_spec, str):
            key = sort_spec
            reverse = False
        else:
            key, direction = sort_spec[0]
            reverse = direction < 0
        self.documents.sort(key=lambda item: item.get(key) or 0, reverse=reverse)
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
            if document.get(key) != value:
                return False
        return True


class FakeDatabase:
    def __init__(self):
        self.agent_tasks = FakeCollection([])
        self.agent_runs = FakeCollection([])


class FakeClient:
    def close(self):
        return None


def patch_database(monkeypatch, db):
    monkeypatch.setattr(main, "get_client", lambda: FakeClient())
    monkeypatch.setattr(main, "get_database", lambda _client: db)


def patch_supported_agents(monkeypatch, db, run_status="waiting_for_approval"):
    class FakeAgent:
        agent_role = "Fake safe dry-run agent"

        def __init__(self, module, dry_run=True, mongo_uri=None, vault_path=None, limit=10):
            self.module = module
            self.dry_run = dry_run
            self.limit = limit

        def run(self):
            db.agent_runs.insert_one(
                {
                    "run_id": "run-task-1",
                    "agent_name": "outreach",
                    "module": self.module,
                    "status": run_status,
                    "started_at": datetime.now(timezone.utc),
                    "completed_at": datetime.now(timezone.utc),
                }
            )
            return {"run_id": "run-task-1", "actions": [{"title": "Review"}], "log_path": "logs/agents/fake.md"}

    monkeypatch.setattr(main, "AGENT_CLASSES", {"outreach": FakeAgent, "followup": FakeAgent, "content": FakeAgent, "fan_engagement": FakeAgent})
    monkeypatch.setattr(main, "SUPPORTED_MODULES", {"insurance_growth": {}, "contractor_growth": {}, "artist_growth": {}, "media_growth": {}})


def test_create_and_list_agent_task(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)
    patch_supported_agents(monkeypatch, db)

    response = TestClient(app).post(
        "/agent-tasks",
        json={"agent_name": "outreach", "module": "insurance_growth", "task_type": "run_outreach", "priority": "high", "input_config": {"limit": 3}},
    )

    assert response.status_code == 200
    task = response.json()["item"]
    assert task["status"] == "queued"
    assert task["agent_name"] == "outreach"
    assert task["task_type"] == "run_outreach"
    assert task["priority"] == "high"
    assert task["input_config"]["dry_run"] is True
    assert task["outbound_actions_taken"] == 0

    list_response = TestClient(app).get("/agent-tasks")
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 1


def test_run_agent_task_links_run_and_waiting_for_approval(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)
    patch_supported_agents(monkeypatch, db, run_status="waiting_for_approval")
    task_id = ObjectId()
    db.agent_tasks.insert_one(
        {
            "_id": task_id,
            "agent_name": "outreach",
            "module": "insurance_growth",
            "task_type": "run_outreach",
            "status": "queued",
            "priority": "normal",
            "input_config": {"limit": 2},
            "created_at": datetime.now(timezone.utc),
            "started_at": None,
            "completed_at": None,
            "linked_run_id": None,
        }
    )

    response = TestClient(app).post(f"/agent-tasks/{task_id}/run")

    assert response.status_code == 200
    updated = db.agent_tasks.documents[0]
    assert updated["status"] == "waiting_for_approval"
    assert updated["linked_run_id"] == "run-task-1"
    assert updated["result_summary"]["outbound_actions_taken"] == 0
    assert updated["outbound_actions_taken"] == 0


def test_run_agent_task_marks_completed_when_run_completed(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)
    patch_supported_agents(monkeypatch, db, run_status="completed")
    task_id = ObjectId()
    db.agent_tasks.insert_one(
        {
            "_id": task_id,
            "agent_name": "outreach",
            "module": "insurance_growth",
            "task_type": "run_outreach",
            "status": "queued",
            "priority": "normal",
            "input_config": {},
            "created_at": datetime.now(timezone.utc),
        }
    )

    response = TestClient(app).post(f"/agent-tasks/{task_id}/run")

    assert response.status_code == 200
    assert db.agent_tasks.documents[0]["status"] == "completed"
    assert db.agent_tasks.documents[0]["linked_run_id"] == "run-task-1"


def test_cancel_agent_task_updates_internal_status(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)
    patch_supported_agents(monkeypatch, db)
    task_id = ObjectId()
    db.agent_tasks.insert_one(
        {
            "_id": task_id,
            "agent_name": "outreach",
            "module": "insurance_growth",
            "task_type": "run_outreach",
            "status": "queued",
            "priority": "low",
            "input_config": {},
            "created_at": datetime.now(timezone.utc),
        }
    )

    response = TestClient(app).post(f"/agent-tasks/{task_id}/cancel")

    assert response.status_code == 200
    updated = db.agent_tasks.documents[0]
    assert updated["status"] == "cancelled"
    assert updated["outbound_actions_taken"] == 0
    assert updated["simulation_only"] is True


def test_completed_agent_task_cannot_be_cancelled(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)
    patch_supported_agents(monkeypatch, db)
    task_id = ObjectId()
    db.agent_tasks.insert_one(
        {
            "_id": task_id,
            "agent_name": "outreach",
            "module": "insurance_growth",
            "task_type": "run_outreach",
            "status": "completed",
            "priority": "normal",
            "input_config": {},
            "created_at": datetime.now(timezone.utc),
        }
    )

    response = TestClient(app).post(f"/agent-tasks/{task_id}/cancel")

    assert response.status_code == 400