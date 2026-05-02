from agents.gpt_client import generate_agent_response, select_model


ROUTING_KEYS = {"model", "routing_reason", "complexity"}
RESPONSE_ROUTING_KEYS = {"selected_model", "routing_reason", "complexity"}
COMPLEXITY_VALUES = {"low", "medium", "high", "critical"}


# ---------------------------------------------------------------------------
# select_model shape
# ---------------------------------------------------------------------------


def test_select_model_returns_expected_shape(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "true")
    result = select_model("outreach_agent", "generate_outreach_message", {})
    assert ROUTING_KEYS == set(result), f"Unexpected keys: {set(result)}"
    assert isinstance(result["model"], str) and result["model"]
    assert isinstance(result["routing_reason"], str) and result["routing_reason"]
    assert result["complexity"] in COMPLEXITY_VALUES


# ---------------------------------------------------------------------------
# Routing disabled
# ---------------------------------------------------------------------------


def test_select_model_routing_disabled_uses_openai_model(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "false")
    monkeypatch.setenv("OPENAI_MODEL", "explicit-model")
    result = select_model("outreach_agent", "generate_outreach_message", {})
    assert result["model"] == "explicit-model"
    assert result["routing_reason"] == "model_routing_disabled"
    assert result["complexity"] == "low"


def test_select_model_routing_disabled_falls_back_when_no_openai_model(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "false")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_FALLBACK_MODEL", "fallback-x")
    result = select_model("outreach_agent", "generate_outreach_message", {})
    assert result["model"] == "fallback-x"


# ---------------------------------------------------------------------------
# Low complexity
# ---------------------------------------------------------------------------


def test_select_model_low_complexity_outreach_draft(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENAI_DRAFT_MODEL", "draft-model")
    result = select_model("outreach_agent", "generate_outreach_message", {})
    assert result["model"] == "draft-model"
    assert result["complexity"] == "low"


def test_select_model_low_complexity_summarize(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENAI_DRAFT_MODEL", "draft-model")
    result = select_model("outreach_agent", "summarize_lead", {})
    assert result["model"] == "draft-model"
    assert result["complexity"] == "low"


def test_select_model_low_complexity_rewrite(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENAI_DRAFT_MODEL", "draft-model")
    result = select_model("outreach_agent", "rewrite_intro_paragraph", {})
    assert result["model"] == "draft-model"
    assert result["complexity"] == "low"


# ---------------------------------------------------------------------------
# Medium complexity
# ---------------------------------------------------------------------------


def test_select_model_medium_complexity_followup(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENAI_AGENT_MODEL", "agent-model")
    result = select_model("followup_agent", "generate_followup", {})
    assert result["model"] == "agent-model"
    assert result["complexity"] == "medium"


def test_select_model_medium_complexity_content_plan(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENAI_AGENT_MODEL", "agent-model")
    result = select_model("content_agent", "generate_content_plan", {})
    assert result["model"] == "agent-model"
    assert result["complexity"] == "medium"


def test_select_model_medium_complexity_fan_engagement(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENAI_AGENT_MODEL", "agent-model")
    result = select_model("fan_engagement_agent", "generate_fan_engagement_plan", {})
    assert result["model"] == "agent-model"
    assert result["complexity"] == "medium"


# ---------------------------------------------------------------------------
# High complexity
# ---------------------------------------------------------------------------


def test_select_model_high_complexity_campaign_strategy(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENAI_REVIEW_MODEL", "review-model")
    result = select_model("outreach_agent", "campaign_strategy", {})
    assert result["model"] == "review-model"
    assert result["complexity"] == "high"


def test_select_model_high_complexity_lead_scoring(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENAI_REVIEW_MODEL", "review-model")
    result = select_model("outreach_agent", "lead_scoring_rationale", {})
    assert result["model"] == "review-model"
    assert result["complexity"] == "high"


def test_select_model_high_complexity_next_best_action(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENAI_REVIEW_MODEL", "review-model")
    result = select_model("outreach_agent", "next_best_action", {})
    assert result["model"] == "review-model"
    assert result["complexity"] == "high"


# ---------------------------------------------------------------------------
# Critical complexity
# ---------------------------------------------------------------------------


def test_select_model_critical_high_value_deal(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENAI_REVIEW_MODEL", "review-model")
    result = select_model("outreach_agent", "high_value_deal_review", {})
    assert result["model"] == "review-model"
    assert result["complexity"] == "critical"


def test_select_model_critical_compliance(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENAI_REVIEW_MODEL", "review-model")
    result = select_model("outreach_agent", "compliance_review_messaging", {})
    assert result["model"] == "review-model"
    assert result["complexity"] == "critical"


# ---------------------------------------------------------------------------
# Unclassified task → fallback
# ---------------------------------------------------------------------------


def test_select_model_unclassified_task_uses_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENAI_FALLBACK_MODEL", "fallback-model")
    result = select_model("outreach_agent", "some_completely_unknown_task_xyz", {})
    assert result["model"] == "fallback-model"
    assert result["complexity"] == "low"
    assert "unclassified_task" in result["routing_reason"]


# ---------------------------------------------------------------------------
# generate_agent_response includes routing fields
# ---------------------------------------------------------------------------


def test_generate_agent_response_includes_routing_fields_when_disabled(monkeypatch):
    monkeypatch.setenv("GPT_AGENT_ENABLED", "false")
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENAI_DRAFT_MODEL", "draft-model")
    result = generate_agent_response("outreach", "contractor_growth", "generate_outreach_message", {})
    assert RESPONSE_ROUTING_KEYS.issubset(set(result))
    assert result["selected_model"] == "draft-model"
    assert result["complexity"] == "low"
    assert result["routing_reason"] != ""


def test_generate_agent_response_routing_fields_when_routing_disabled(monkeypatch):
    monkeypatch.setenv("GPT_AGENT_ENABLED", "false")
    monkeypatch.setenv("OPENAI_MODEL_ROUTING_ENABLED", "false")
    monkeypatch.setenv("OPENAI_MODEL", "base-model")
    result = generate_agent_response("outreach", "contractor_growth", "generate_outreach_message", {})
    assert result["selected_model"] == "base-model"
    assert result["routing_reason"] == "model_routing_disabled"
