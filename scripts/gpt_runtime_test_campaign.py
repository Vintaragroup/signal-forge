import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import agents.outreach_agent as outreach_module
from agents.outreach_agent import OutreachAgent
from main import app, get_client, get_database


MODULE = "media_growth"
TEST_SOURCE = "gpt_runtime_test_campaign_v1"
SAFETY_MODE = "local_human_review_only"


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def assert_condition(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def print_ok(message: str) -> None:
    print(f"[ok] {message}")


def verify_settings_endpoint() -> dict:
    response = TestClient(app).get("/settings/gpt-runtime")
    assert_condition(response.status_code == 200, "GPT runtime settings endpoint did not return 200.")
    payload = response.json()
    for key in ("enabled", "model", "has_api_key", "safety_mode"):
        assert_condition(key in payload, f"GPT runtime settings response missing {key}.")
    assert_condition(isinstance(payload["enabled"], bool), "GPT runtime enabled must be boolean.")
    assert_condition(isinstance(payload["has_api_key"], bool), "GPT runtime has_api_key must be boolean.")
    assert_condition(clean_text(payload["model"]) != "", "GPT runtime model must be present.")
    assert_condition(payload["safety_mode"] == SAFETY_MODE, "GPT runtime safety mode is not local human-review only.")
    print_ok(
        "settings endpoint returned enabled="
        f"{payload['enabled']}, model={payload['model']}, has_api_key={payload['has_api_key']}"
    )
    return payload


def seed_test_contact(db) -> None:
    now = utc_now()
    db.contacts.update_one(
        {"contact_key": "gpt-runtime-test-media-contact"},
        {
            "$set": {
                "contact_key": "gpt-runtime-test-media-contact",
                "name": "Avery Test",
                "company": "AAA GPT Runtime Test Studio",
                "role": "Editorial Partnerships Lead",
                "email": "avery.test@example.invalid",
                "module": MODULE,
                "source": TEST_SOURCE,
                "contact_status": "imported",
                "contact_score": 100,
                "segment": "high_priority",
                "priority_reason": "Local GPT runtime test contact for review-only agent validation.",
                "recommended_action": "Create a review-only outreach angle. Do not send anything.",
                "notes": "Synthetic local test record. No outbound action is allowed.",
                "imported_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
    )
    print_ok("seeded local GPT runtime test contact")


def sent_message_count(db) -> int:
    return db.message_drafts.count_documents({"send_status": "sent"})


def verify_no_send_status_changed(before_count: int, after_count: int) -> None:
    assert_condition(after_count == before_count, "send_status=sent count changed during GPT runtime test.")
    print_ok("no message draft changed to send_status=sent")


def verify_gpt_steps(db, run_id: str) -> None:
    steps = list(db.agent_steps.find({"run_id": run_id, "step_name": {"$regex": "^gpt_"}}))
    assert_condition(steps, f"run {run_id} did not record GPT agent_steps.")
    for step in steps:
        output = step.get("output") or {}
        assert_condition("confidence" in output, f"GPT step {step.get('_id')} missing confidence.")
        assert_condition("reasoning_summary" in output, f"GPT step {step.get('_id')} missing reasoning_summary.")
    print_ok(f"run {run_id} recorded GPT confidence and reasoning_summary")


def verify_gpt_drafts_review_only(db, run_id: str) -> None:
    drafts = list(db.message_drafts.find({"agent_run_id": run_id, "source": "gpt"}))
    for draft in drafts:
        assert_condition(draft.get("review_status") == "needs_review", f"GPT draft {draft.get('_id')} is not needs_review.")
        assert_condition(draft.get("send_status") == "not_sent", f"GPT draft {draft.get('_id')} is not not_sent.")
    print_ok(f"{len(drafts)} GPT-created message drafts are review-only")


def verify_gpt_approval_request(db, run_id: str) -> None:
    approval = db.approval_requests.find_one({"run_id": run_id, "request_type": "gpt_message_generation_review"})
    assert_condition(approval is not None, f"run {run_id} did not create a GPT safety approval request.")
    assert_condition(approval.get("status") == "open", "GPT safety approval request is not open.")
    assert_condition(approval.get("simulation_only") is True, "GPT safety approval request is not simulation-only.")
    print_ok("GPT cannot-proceed path created an open approval request")


def mark_test_approval_requests(db, run_id: str) -> None:
    db.approval_requests.update_many(
        {"run_id": run_id},
        {
            "$set": {
                "request_origin": "test",
                "is_test": True,
                "severity": "info",
                "user_facing_summary": "Synthetic GPT runtime test approval. It exists only to verify review-only safety behavior.",
                "technical_reason": "Created by scripts/gpt_runtime_test_campaign.py while mocking or validating GPT safety paths.",
            }
        },
    )


def run_mocked_cannot_proceed_campaign(db) -> str:
    original_generate = outreach_module.generate_agent_response

    def cannot_proceed_response(**_kwargs):
        return {
            "enabled": True,
            "used_gpt": True,
            "output": "Draft withheld for safety review.",
            "confidence": 0.25,
            "reasoning_summary": "Synthetic test: confidence is too low to create a safe message draft.",
            "error": None,
        }

    try:
        outreach_module.generate_agent_response = cannot_proceed_response
        result = OutreachAgent(module=MODULE, dry_run=True, limit=1).run()
    finally:
        outreach_module.generate_agent_response = original_generate

    run_id = result["run_id"]
    verify_gpt_steps(db, run_id)
    verify_gpt_approval_request(db, run_id)
    mark_test_approval_requests(db, run_id)
    return run_id


def run_live_gpt_campaign_if_configured(db) -> str | None:
    api_key = clean_text(os.getenv("OPENAI_API_KEY"))
    if not api_key:
        print("[skip] OPENAI_API_KEY is not configured; skipped live GPT-enabled outreach dry-run.")
        return None

    os.environ["GPT_AGENT_ENABLED"] = "true"
    settings = verify_settings_endpoint()
    assert_condition(settings["enabled"] is True, "GPT runtime did not report enabled after enabling test campaign.")
    assert_condition(settings["has_api_key"] is True, "GPT runtime did not detect OPENAI_API_KEY.")

    result = OutreachAgent(module=MODULE, dry_run=True, limit=1).run()
    run_id = result["run_id"]
    verify_gpt_steps(db, run_id)
    verify_gpt_drafts_review_only(db, run_id)

    approval_count = db.approval_requests.count_documents({"run_id": run_id, "request_type": "gpt_message_generation_review"})
    draft_count = db.message_drafts.count_documents({"agent_run_id": run_id, "source": "gpt"})
    assert_condition(draft_count or approval_count, "live GPT run created neither a review draft nor a safety approval request.")
    mark_test_approval_requests(db, run_id)
    print_ok("live GPT-enabled outreach dry-run completed without outbound action")
    return run_id


def main() -> None:
    print("GPT Runtime Test Campaign v1")
    print("Safety: no messages, posts, scraping, scheduling, or outbound automation.")
    verify_settings_endpoint()

    client = get_client()
    try:
        db = get_database(client)
        seed_test_contact(db)
        before_sent = sent_message_count(db)
        mocked_run_id = run_mocked_cannot_proceed_campaign(db)
        live_run_id = run_live_gpt_campaign_if_configured(db)
        after_sent = sent_message_count(db)
        verify_no_send_status_changed(before_sent, after_sent)
    finally:
        client.close()

    print_ok(f"mocked safety run: {mocked_run_id}")
    if live_run_id:
        print_ok(f"live GPT run: {live_run_id}")
    print("GPT runtime test campaign passed.")


if __name__ == "__main__":
    main()