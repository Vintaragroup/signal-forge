import json
import os
from typing import Any
from urllib import error, request


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"

# ---------------------------------------------------------------------------
# Routing constants — task keywords matched in lower-case task strings
# ---------------------------------------------------------------------------

_CRITICAL_KEYWORDS = frozenset([
    "high_value_deal_review", "legal_review", "compliance_review",
    "multi_step_autonomous_planning", "autonomous_planning",
    "legal", "compliance", "high-value", "high_value", "autonomous",
])

_HIGH_COMPLEXITY_KEYWORDS = frozenset([
    "campaign_strategy", "campaign strategy",
    "multi_contact_reasoning", "multi-contact",
    "lead_scoring_rationale", "lead scoring",
    "next_best_action", "next best action",
    "next_best", "multi_step",
])

_MEDIUM_COMPLEXITY_KEYWORDS = frozenset([
    "follow_up_recommendation", "generate_followup", "generate_follow_up",
    "followup_recommendation", "follow-up recommendation",
    "content_planning", "generate_content_plan", "content plan",
    "fan_engagement_plan", "generate_fan_engagement_plan", "fan engagement",
    "follow_up", "follow-up", "followup",
])

_LOW_COMPLEXITY_KEYWORDS = frozenset([
    "generate_outreach_message", "outreach_message", "outreach message",
    "draft_message", "draft message",
    "rewrite", "summarize", "summariz",
    "classify", "classif", "simple_classification",
    "summarize_lead",
])


def _env_enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _resolved_model(env_key: str) -> str:
    return os.getenv(env_key, "").strip() or DEFAULT_MODEL


def select_model(agent_name: str, task: str, context: Any) -> dict:
    """Route to the right OpenAI model based on task complexity.

    Returns a dict with keys:
        model          — the model name to use
        routing_reason — human-readable reason string
        complexity     — 'low' | 'medium' | 'high' | 'critical'
    """
    routing_enabled = _env_enabled(os.getenv("OPENAI_MODEL_ROUTING_ENABLED", "false"))
    fallback = _resolved_model("OPENAI_FALLBACK_MODEL")

    if not routing_enabled:
        model = os.getenv("OPENAI_MODEL", "").strip() or fallback
        return {"model": model, "routing_reason": "model_routing_disabled", "complexity": "low"}

    task_lower = (task or "").lower()

    # Check critical first (highest priority)
    if any(kw in task_lower for kw in _CRITICAL_KEYWORDS):
        model = _resolved_model("OPENAI_REVIEW_MODEL")
        return {"model": model, "routing_reason": f"critical_task:{task_lower}", "complexity": "critical"}

    # High complexity
    if any(kw in task_lower for kw in _HIGH_COMPLEXITY_KEYWORDS):
        model = _resolved_model("OPENAI_REVIEW_MODEL")
        return {"model": model, "routing_reason": f"high_complexity_task:{task_lower}", "complexity": "high"}

    # Medium complexity
    if any(kw in task_lower for kw in _MEDIUM_COMPLEXITY_KEYWORDS):
        model = _resolved_model("OPENAI_AGENT_MODEL")
        return {"model": model, "routing_reason": f"medium_complexity_task:{task_lower}", "complexity": "medium"}

    # Low complexity
    if any(kw in task_lower for kw in _LOW_COMPLEXITY_KEYWORDS):
        model = _resolved_model("OPENAI_DRAFT_MODEL")
        return {"model": model, "routing_reason": f"low_complexity_task:{task_lower}", "complexity": "low"}

    # Unclassified → fallback
    return {"model": fallback, "routing_reason": f"unclassified_task:{task_lower}", "complexity": "low"}


def _empty_response(
    enabled: bool,
    used_gpt: bool,
    output: str,
    confidence: float,
    reasoning_summary: str,
    error_text: str | None,
    routing: dict | None = None,
) -> dict:
    r = routing or {"model": DEFAULT_MODEL, "routing_reason": "not_routed", "complexity": "low"}
    return {
        "enabled": enabled,
        "used_gpt": used_gpt,
        "output": output,
        "confidence": confidence,
        "reasoning_summary": reasoning_summary,
        "error": error_text,
        "selected_model": r["model"],
        "routing_reason": r["routing_reason"],
        "complexity": r["complexity"],
    }


def _safe_context(context: Any) -> str:
    try:
        return json.dumps(context or {}, indent=2, sort_keys=True, default=str)
    except TypeError:
        return json.dumps({"context": str(context)}, indent=2, sort_keys=True)


def _build_payload(agent_name: str, module: str, task: str, context: Any, model: str | None = None) -> dict:
    resolved_model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL
    return {
        "model": resolved_model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a SignalForge planning assistant. Return concise, safe, human-reviewed guidance only. "
                    "Do not claim that any outbound message was sent, scheduled, published, invoiced, or synced."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Agent: {agent_name}\n"
                    f"Module: {module}\n"
                    f"Task: {task}\n\n"
                    "Context:\n"
                    f"{_safe_context(context)}"
                ),
            },
        ],
    }


def _extract_output(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "").strip()


def generate_agent_response(agent_name, module, task, context) -> dict:
    enabled = _env_enabled(os.getenv("GPT_AGENT_ENABLED", "false"))
    routing = select_model(str(agent_name), str(task), context)

    if not enabled:
        return _empty_response(
            enabled=False,
            used_gpt=False,
            output="",
            confidence=0.0,
            reasoning_summary="GPT agent runtime is disabled by GPT_AGENT_ENABLED.",
            error_text=None,
            routing=routing,
        )

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return _empty_response(
            enabled=True,
            used_gpt=False,
            output="",
            confidence=0.0,
            reasoning_summary="GPT agent runtime is enabled, but no OpenAI API key is configured.",
            error_text="missing_openai_api_key",
            routing=routing,
        )

    payload = json.dumps(_build_payload(str(agent_name), str(module), str(task), context, model=routing["model"])).encode("utf-8")
    http_request = request.Request(
        OPENAI_CHAT_COMPLETIONS_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(http_request, timeout=30) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        output = _extract_output(response_payload)
        return _empty_response(
            enabled=True,
            used_gpt=True,
            output=output,
            confidence=0.7 if output else 0.2,
            reasoning_summary="GPT generated a planning response for human review.",
            error_text=None if output else "empty_gpt_response",
            routing=routing,
        )
    except error.HTTPError as exc:
        return _empty_response(
            enabled=True,
            used_gpt=False,
            output="",
            confidence=0.0,
            reasoning_summary="GPT request failed before producing a usable response.",
            error_text=f"openai_http_error_{exc.code}",
            routing=routing,
        )
    except Exception as exc:
        return _empty_response(
            enabled=True,
            used_gpt=False,
            output="",
            confidence=0.0,
            reasoning_summary="GPT request failed safely without changing agent behavior.",
            error_text=f"openai_request_error_{exc.__class__.__name__}",
            routing=routing,
        )
