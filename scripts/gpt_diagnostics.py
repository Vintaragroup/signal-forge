import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main import DEFAULT_OPENAI_MODEL, gpt_diagnostics_status, get_client, get_database


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DIAGNOSTIC_PROMPT = "Return the word OK."


def clean_text(value) -> str:
    return str(value or "").strip()


def live_gpt_test(model: str, api_key: str) -> dict:
    payload = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "You are a minimal diagnostics endpoint. Follow the user instruction exactly."},
                {"role": "user", "content": DIAGNOSTIC_PROMPT},
            ],
        }
    ).encode("utf-8")
    http_request = request.Request(
        OPENAI_CHAT_COMPLETIONS_URL,
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(http_request, timeout=30) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        choices = response_payload.get("choices") or []
        message = choices[0].get("message") if choices else {}
        output = clean_text((message or {}).get("content"))
        return {
            "used_gpt": True,
            "ok": output.upper() == "OK",
            "response_summary": "OK" if output.upper() == "OK" else "unexpected_response",
            "error": None if output else "empty_gpt_response",
            "output_length": len(output),
        }
    except error.HTTPError as exc:
        return {"used_gpt": False, "ok": False, "response_summary": "http_error", "error": f"openai_http_error_{exc.code}", "output_length": 0}
    except Exception as exc:
        return {"used_gpt": False, "ok": False, "response_summary": "request_error", "error": f"openai_request_error_{exc.__class__.__name__}", "output_length": 0}


def record_live_test(db, diagnostics: dict, result: dict) -> None:
    now = datetime.now(timezone.utc)
    db.agent_steps.insert_one(
        {
            "run_id": f"gpt-diagnostics-{now.strftime('%Y%m%dT%H%M%SZ')}",
            "agent_name": "gpt_diagnostics",
            "module": "system",
            "step_number": 1,
            "step_name": "gpt_diagnostic_live_test",
            "status": "completed" if result.get("ok") else "failed",
            "input": {"prompt_label": "minimal_ok_diagnostic", "model": diagnostics["openai_model"]},
            "decision": "Run only because --live-test was explicitly provided; no outbound automation is performed.",
            "output": {
                "enabled": diagnostics["gpt_agent_enabled"],
                "used_gpt": result.get("used_gpt"),
                "confidence": 1.0 if result.get("ok") else 0.0,
                "reasoning_summary": "Minimal GPT diagnostic returned OK." if result.get("ok") else "Minimal GPT diagnostic did not return OK.",
                "output_length": result.get("output_length", 0),
                "error": result.get("error"),
            },
            "artifact_refs": [],
            "timestamp": now,
        }
    )


def print_diagnostics(diagnostics: dict) -> None:
    print("GPT Diagnostics v1")
    print("Safety: no messages, posts, scraping, scheduling, CRM updates, or agent behavior changes.")
    print(f"GPT agent enabled: {diagnostics['gpt_agent_enabled']}")
    print(f"OpenAI model: {diagnostics['openai_model']}")
    print(f"API key present: {diagnostics['has_api_key']}")
    print(f"API key source: {diagnostics['api_key_source']}")
    print(f"Client available: {diagnostics['client_available']}")
    print(f"Last successful GPT call: {diagnostics['last_successful_gpt_call_at'] or 'none recorded'}")
    print(f"Last GPT error: {diagnostics['last_gpt_error_summary'] or 'none recorded'}")
    print(f"Last GPT error at: {diagnostics['last_gpt_error_at'] or 'none recorded'}")
    print(f"Recent GPT steps: {len(diagnostics['recent_gpt_agent_steps'])}")
    print(f"Recent system approval errors: {len(diagnostics['recent_system_approval_errors'])}")
    print("Environment visibility: this script is running inside the same API/Docker environment used by SignalForge.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Print safe GPT runtime diagnostics without exposing secrets.")
    parser.add_argument("--live-test", action="store_true", help="Send the minimal diagnostic prompt 'Return the word OK.' to OpenAI.")
    args = parser.parse_args()

    client = get_client()
    try:
        db = get_database(client)
        diagnostics = gpt_diagnostics_status(db)
        print_diagnostics(diagnostics)

        if not args.live_test:
            print("Live test: skipped. Pass --live-test to call OpenAI with the minimal OK prompt.")
            return

        api_key = clean_text(os.getenv("OPENAI_API_KEY"))
        if not api_key:
            print("Live test: skipped safely because OPENAI_API_KEY is missing.")
            return

        model = clean_text(os.getenv("OPENAI_MODEL")) or DEFAULT_OPENAI_MODEL
        result = live_gpt_test(model, api_key)
        record_live_test(db, diagnostics, result)
        print(f"Live test used GPT: {result['used_gpt']}")
        print(f"Live test result: {result['response_summary']}")
        if result.get("error"):
            print(f"Live test error: {result['error']}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
