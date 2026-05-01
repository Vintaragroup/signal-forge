import re
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi.testclient import TestClient

import main
from main import app


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

    def matches(self, document, query):
        for key, value in query.items():
            if key == "$or":
                if not any(self.matches(document, condition) for condition in value):
                    return False
                continue
            actual = document.get(key)
            if isinstance(value, dict) and "$regex" in value:
                if not re.search(value["$regex"], str(actual or "")):
                    return False
                continue
            if actual != value:
                return False
        return True


class FakeDatabase:
    def __init__(self, agent_steps=None, approval_requests=None):
        self.agent_steps = FakeCollection(agent_steps or [])
        self.approval_requests = FakeCollection(approval_requests or [])


class FakeClient:
    def close(self):
        return None


def patch_database(monkeypatch, db):
    monkeypatch.setattr(main, "get_client", lambda: FakeClient())
    monkeypatch.setattr(main, "get_database", lambda _client: db)


def test_gpt_diagnostics_endpoint_returns_no_secrets(monkeypatch):
    monkeypatch.setenv("GPT_AGENT_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret-key-not-returned")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    patch_database(monkeypatch, FakeDatabase())

    response = TestClient(app).get("/diagnostics/gpt")

    assert response.status_code == 200
    payload = response.json()
    assert payload["gpt_agent_enabled"] is True
    assert payload["openai_model"] == "gpt-4.1-mini"
    assert payload["has_api_key"] is True
    assert payload["api_key_source"] == "env"
    assert "test-secret-key-not-returned" not in response.text
    assert "OPENAI_API_KEY" not in response.text


def test_gpt_diagnostics_disabled_mode_is_safe(monkeypatch):
    monkeypatch.delenv("GPT_AGENT_ENABLED", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    patch_database(monkeypatch, FakeDatabase())

    response = TestClient(app).get("/diagnostics/gpt")

    assert response.status_code == 200
    payload = response.json()
    assert payload["gpt_agent_enabled"] is False
    assert payload["has_api_key"] is False
    assert payload["api_key_source"] == "missing"
    assert payload["last_gpt_error_summary"] is None
    assert payload["recent_gpt_agent_steps"] == []
    assert payload["recent_system_approval_errors"] == []


def test_gpt_diagnostics_missing_key_reported_safely(monkeypatch):
    monkeypatch.setenv("GPT_AGENT_ENABLED", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    patch_database(monkeypatch, FakeDatabase())

    response = TestClient(app).get("/diagnostics/gpt")

    assert response.status_code == 200
    payload = response.json()
    assert payload["gpt_agent_enabled"] is True
    assert payload["has_api_key"] is False
    assert payload["api_key_source"] == "missing"
    assert "OPENAI_API_KEY" not in response.text


def test_gpt_diagnostics_recent_errors_are_returned(monkeypatch):
    monkeypatch.setenv("GPT_AGENT_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "another-secret-not-returned")
    now = datetime.now(timezone.utc)
    db = FakeDatabase(
        agent_steps=[
            {
                "_id": ObjectId(),
                "run_id": "run-success",
                "agent_name": "outreach",
                "module": "media_growth",
                "step_name": "gpt_message_generation",
                "status": "completed",
                "timestamp": now - timedelta(minutes=10),
                "input": {"prompt": "raw prompt must not be returned"},
                "output": {"used_gpt": True, "confidence": 0.8, "reasoning_summary": "GPT generated a planning response.", "output_length": 12, "error": None},
            },
            {
                "_id": ObjectId(),
                "run_id": "run-error",
                "agent_name": "content",
                "module": "artist_growth",
                "step_name": "gpt_content_plan_generation",
                "status": "failed",
                "timestamp": now,
                "input": {"prompt": "raw error prompt must not be returned"},
                "output": {"used_gpt": False, "confidence": 0.0, "reasoning_summary": "Request failed safely.", "output_length": 0, "error": "openai_http_error_401"},
            },
        ],
        approval_requests=[
            {
                "_id": ObjectId(),
                "run_id": "run-error",
                "agent_name": "content",
                "module": "artist_growth",
                "request_type": "gpt_content_plan_review",
                "status": "open",
                "title": "GPT content failure",
                "request_origin": "system",
                "severity": "error",
                "user_facing_summary": "GPT failed before producing a usable content plan.",
                "technical_reason": "openai_http_error_401",
                "created_at": now,
            }
        ],
    )
    patch_database(monkeypatch, db)

    response = TestClient(app).get("/diagnostics/gpt")

    assert response.status_code == 200
    payload = response.json()
    assert payload["last_gpt_error_summary"] == "openai_http_error_401"
    assert payload["last_gpt_error_at"] is not None
    assert payload["last_successful_gpt_call_at"] is not None
    assert len(payload["recent_gpt_agent_steps"]) == 2
    assert len(payload["recent_system_approval_errors"]) == 1
    assert "raw prompt" not in response.text
    assert "another-secret-not-returned" not in response.text