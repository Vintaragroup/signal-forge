from fastapi.testclient import TestClient

from main import app


def test_gpt_runtime_settings_disabled_without_key(monkeypatch):
    monkeypatch.delenv("GPT_AGENT_ENABLED", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    response = TestClient(app).get("/settings/gpt-runtime")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "model": "gpt-4o-mini",
        "has_api_key": False,
        "safety_mode": "local_human_review_only",
    }


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