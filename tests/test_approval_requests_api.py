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

    def count_documents(self, query):
        return len(list(self.find(query)))

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
        self.approval_id = ObjectId()
        self.contact_id = ObjectId()
        self.approval_requests = FakeCollection(
            [
                {
                    "_id": self.approval_id,
                    "run_id": "run-approval-1",
                    "agent_name": "outreach",
                    "module": "insurance_growth",
                    "request_type": "gpt_message_generation_review",
                    "status": "open",
                    "title": "Review GPT outreach result",
                    "summary": "Low confidence output.",
                    "reason_for_review": "Needs operator review.",
                    "target": "approval-contact",
                    "target_type": "contact",
                    "linked_target_id": str(self.contact_id),
                    "gpt_confidence": 0.42,
                    "created_at": datetime.now(timezone.utc),
                    "simulation_only": True,
                }
            ]
        )
        self.contacts = FakeCollection(
            [
                {
                    "_id": self.contact_id,
                    "contact_key": "approval-contact",
                    "name": "Approval Contact",
                    "company": "Queue Test Co",
                    "module": "insurance_growth",
                }
            ]
        )
        self.leads = FakeCollection([])
        self.message_drafts = FakeCollection([])
        self.agent_artifacts = FakeCollection([])


class FakeClient:
    def close(self):
        return None


def patch_database(monkeypatch, db):
    monkeypatch.setattr(main, "get_client", lambda: FakeClient())
    monkeypatch.setattr(main, "get_database", lambda _client: db)


def test_approval_requests_endpoint_returns_enriched_open_items(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)

    response = TestClient(app).get("/approval-requests")

    assert response.status_code == 200
    payload = response.json()
    assert payload["simulation_only"] is True
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["request_type"] == "gpt_message_generation_review"
    assert item["request_origin"] == "gpt"
    assert item["is_test"] is False
    assert item["severity"] == "needs_review"
    assert item["user_facing_summary"] == "Needs operator review."
    assert item["technical_reason"] == "Needs operator review."
    assert item["linked_contact"]["name"] == "Approval Contact"


def test_approval_requests_default_hides_test_and_system_items(monkeypatch):
    db = FakeDatabase()
    db.approval_requests.documents.extend(
        [
            {
                "_id": ObjectId(),
                "request_type": "gpt_message_generation_review",
                "status": "open",
                "title": "Synthetic GPT test approval",
                "request_origin": "test",
                "is_test": True,
                "severity": "info",
                "created_at": datetime.now(timezone.utc),
            },
            {
                "_id": ObjectId(),
                "request_type": "gpt_message_generation_review",
                "status": "open",
                "title": "GPT request failed",
                "request_origin": "system",
                "is_test": False,
                "severity": "error",
                "created_at": datetime.now(timezone.utc),
            },
        ]
    )
    patch_database(monkeypatch, db)

    response = TestClient(app).get("/approval-requests")

    assert response.status_code == 200
    titles = [item["title"] for item in response.json()["items"]]
    assert "Review GPT outreach result" in titles
    assert "Synthetic GPT test approval" not in titles
    assert "GPT request failed" not in titles


def test_approval_requests_filter_system_and_test_views(monkeypatch):
    db = FakeDatabase()
    test_id = ObjectId()
    system_id = ObjectId()
    db.approval_requests.documents.extend(
        [
            {"_id": test_id, "request_type": "gpt_message_generation_review", "status": "open", "title": "Synthetic approval", "request_origin": "test", "is_test": True, "severity": "info", "created_at": datetime.now(timezone.utc)},
            {"_id": system_id, "request_type": "gpt_message_generation_review", "status": "open", "title": "System issue", "request_origin": "system", "is_test": False, "severity": "error", "created_at": datetime.now(timezone.utc)},
        ]
    )
    patch_database(monkeypatch, db)

    system_response = TestClient(app).get("/approval-requests?view=system")
    test_response = TestClient(app).get("/approval-requests?view=test")

    assert [item["title"] for item in system_response.json()["items"]] == ["System issue"]
    assert [item["title"] for item in test_response.json()["items"]] == ["Synthetic approval"]


def test_approval_decision_approve_updates_internal_status(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)

    response = TestClient(app).post(
        f"/approval-requests/{db.approval_id}/decision",
        json={"decision": "approve", "note": "Approved as internal guidance."},
    )

    assert response.status_code == 200
    updated = db.approval_requests.documents[0]
    assert updated["status"] == "approved"
    assert updated["operator_note"] == "Approved as internal guidance."
    assert updated["outbound_actions_taken"] == 0
    assert db.message_drafts.documents == []


def test_approval_decision_needs_revision_stores_operator_note(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)

    response = TestClient(app).post(
        f"/approval-requests/{db.approval_id}/decision",
        json={"decision": "needs_revision", "note": "Needs more context before drafting."},
    )

    assert response.status_code == 200
    updated = db.approval_requests.documents[0]
    assert updated["status"] == "needs_revision"
    assert updated["operator_note"] == "Needs more context before drafting."
    assert updated["decision_events"][0]["simulation_only"] is True


def test_convert_to_draft_creates_review_only_message_draft(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)

    response = TestClient(app).post(
        f"/approval-requests/{db.approval_id}/decision",
        json={"decision": "convert_to_draft", "note": "Create editable draft shell."},
    )

    assert response.status_code == 200
    updated = db.approval_requests.documents[0]
    assert updated["status"] == "converted_to_draft"
    assert updated["created_record_type"] == "message_draft"
    assert len(db.message_drafts.documents) == 1
    draft = db.message_drafts.documents[0]
    assert draft["review_status"] == "needs_review"
    assert draft["send_status"] == "not_sent"
    assert draft["source"] == "approval_queue"
    assert draft["approval_request_id"] == str(db.approval_id)


def test_convert_to_draft_creates_artifact_draft_when_not_message_request(monkeypatch):
    db = FakeDatabase()
    artifact_approval_id = ObjectId()
    db.approval_requests.documents = [
        {
            "_id": artifact_approval_id,
            "run_id": "run-content-1",
            "agent_name": "content",
            "module": "artist_growth",
            "request_type": "gpt_content_plan_review",
            "status": "open",
            "title": "Review GPT content plan",
            "summary": "Needs content review.",
            "target": "artist_growth",
            "target_type": "module",
            "gpt_confidence": 0.33,
            "created_at": datetime.now(timezone.utc),
            "simulation_only": True,
        }
    ]
    patch_database(monkeypatch, db)

    response = TestClient(app).post(
        f"/approval-requests/{artifact_approval_id}/decision",
        json={"decision": "convert_to_draft", "note": "Turn into an artifact draft."},
    )

    assert response.status_code == 200
    assert db.approval_requests.documents[0]["status"] == "converted_to_draft"
    assert db.approval_requests.documents[0]["created_record_type"] == "artifact_draft"
    assert len(db.agent_artifacts.documents) == 1
    artifact = db.agent_artifacts.documents[0]
    assert artifact["artifact_type"] == "approval_queue_draft"
    assert artifact["review_status"] == "needs_review"
    assert artifact["content"]["simulation_only"] is True
    assert artifact["content"]["outbound_actions_taken"] == 0