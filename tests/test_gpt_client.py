from agents.gpt_client import generate_agent_response


EXPECTED_KEYS = {"enabled", "used_gpt", "output", "confidence", "reasoning_summary", "error", "selected_model", "routing_reason", "complexity"}


def test_gpt_client_returns_disabled_state(monkeypatch):
    monkeypatch.setenv("GPT_AGENT_ENABLED", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")

    result = generate_agent_response("outreach", "contractor_growth", "Plan next action", {"lead": "Austin Roof Works"})

    assert set(result) == EXPECTED_KEYS
    assert result["enabled"] is False
    assert result["used_gpt"] is False
    assert result["output"] == ""
    assert result["confidence"] == 0.0
    assert result["error"] is None


def test_gpt_client_fails_gracefully_when_enabled_without_key(monkeypatch):
    monkeypatch.setenv("GPT_AGENT_ENABLED", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = generate_agent_response("followup", "insurance_growth", "Summarize follow-up", {})

    assert set(result) == EXPECTED_KEYS
    assert result["enabled"] is True
    assert result["used_gpt"] is False
    assert result["output"] == ""
    assert result["confidence"] == 0.0
    assert result["error"] == "missing_openai_api_key"


def test_gpt_client_safe_shape_with_blank_env(monkeypatch):
    monkeypatch.delenv("GPT_AGENT_ENABLED", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = generate_agent_response("content", "artist_growth", "Draft idea", {"nested": {"value": 1}})

    assert set(result) == EXPECTED_KEYS
    assert isinstance(result["enabled"], bool)
    assert isinstance(result["used_gpt"], bool)
    assert isinstance(result["output"], str)
    assert isinstance(result["confidence"], float)
    assert isinstance(result["reasoning_summary"], str)
    assert result["error"] is None or isinstance(result["error"], str)