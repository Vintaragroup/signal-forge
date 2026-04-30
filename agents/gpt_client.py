import json
import os
from typing import Any
from urllib import error, request


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"


def _empty_response(enabled: bool, used_gpt: bool, output: str, confidence: float, reasoning_summary: str, error_text: str | None) -> dict:
    return {
        "enabled": enabled,
        "used_gpt": used_gpt,
        "output": output,
        "confidence": confidence,
        "reasoning_summary": reasoning_summary,
        "error": error_text,
    }


def _env_enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_context(context: Any) -> str:
    try:
        return json.dumps(context or {}, indent=2, sort_keys=True, default=str)
    except TypeError:
        return json.dumps({"context": str(context)}, indent=2, sort_keys=True)


def _build_payload(agent_name: str, module: str, task: str, context: Any) -> dict:
    return {
        "model": os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
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
    if not enabled:
        return _empty_response(
            enabled=False,
            used_gpt=False,
            output="",
            confidence=0.0,
            reasoning_summary="GPT agent runtime is disabled by GPT_AGENT_ENABLED.",
            error_text=None,
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
        )

    payload = json.dumps(_build_payload(str(agent_name), str(module), str(task), context)).encode("utf-8")
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
        )
    except error.HTTPError as exc:
        return _empty_response(
            enabled=True,
            used_gpt=False,
            output="",
            confidence=0.0,
            reasoning_summary="GPT request failed before producing a usable response.",
            error_text=f"openai_http_error_{exc.code}",
        )
    except Exception as exc:
        return _empty_response(
            enabled=True,
            used_gpt=False,
            output="",
            confidence=0.0,
            reasoning_summary="GPT request failed safely without changing agent behavior.",
            error_text=f"openai_request_error_{exc.__class__.__name__}",
        )
