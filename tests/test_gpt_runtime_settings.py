from fastapi.testclient import TestClient

from main import app


def test_gpt_runtime_settings_disabled_without_key(monkeypatch):
    monkeypatch.delenv("GPT_AGENT_ENABLED", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_ROUTING_ENABLED", raising=False)
    monkeypatch.delenv("OPENAI_AGENT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_DRAFT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_REVIEW_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_FALLBACK_MODEL", raising=False)

    response = TestClient(app).get("/settings/gpt-runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is False
    assert payload["model"] == "gpt-4o-mini"
    assert payload["has_api_key"] is False
    assert payload["safety_mode"] == "local_human_review_only"
    assert payload["model_routing_enabled"] is False
    assert "agent_model" in payload
    assert "draft_model" in payload
    assert "review_model" in payload
    assert "fallback_model" in payload


def test_gpt_runtime_settings_enabled_with_configured_model(monkeypatch):
    monkeypatch.setenv("GPT_AGENT_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-returned")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")

    response = TestClient(app).get("/settings/gpt-runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["model"] == "gpt-4.1-mini"
    assert payload["has_api_key"] is True
    assert payload["safety_mode"] == "local_human_review_only"
    assert "test-key-not-returned" not in response.text