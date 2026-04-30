import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient

from core.constants import RESPONSE_OUTCOMES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_PATH = PROJECT_ROOT / "vault"
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"
VALID_OUTCOMES = RESPONSE_OUTCOMES

CONTACT_STATUS_BY_OUTCOME = {
    "interested": "interested",
    "not_interested": "not_interested",
    "call_booked": "call_booked",
    "do_not_contact": "do_not_contact",
    "bounced": "invalid",
}

LEAD_STATUS_BY_OUTCOME = {
    "interested": "replied",
    "call_booked": "booked_call",
    "not_interested": "closed_lost",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log a response to a manually sent SignalForge message draft.")
    parser.add_argument("draft", help="Message draft ObjectId, draft key, note slug, or note path.")
    parser.add_argument("--outcome", required=True, choices=VALID_OUTCOMES, help="Response outcome.")
    parser.add_argument("--note", default="", help="Optional response note.")
    parser.add_argument(
        "--mongo-uri",
        default=os.getenv("MONGO_URI", DEFAULT_MONGO_URI),
        help="MongoDB URI. Defaults to MONGO_URI or localhost signalForge.",
    )
    parser.add_argument(
        "--vault",
        default=os.getenv("VAULT_PATH", str(DEFAULT_VAULT_PATH)),
        help="Vault path. Defaults to VAULT_PATH or local ./vault.",
    )
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "untitled"


def get_database(client: MongoClient):
    try:
        return client.get_default_database()
    except Exception:
        return client["signalforge"]


def is_object_id(value: str) -> bool:
    return ObjectId.is_valid(value)


def find_draft(db, identifier: str) -> dict:
    raw = identifier.strip()
    stem = Path(raw).stem
    slug = slugify(stem)
    escaped_raw = re.escape(raw)
    escaped_slug = re.escape(slug)

    conditions = [
        {"draft_key": raw},
        {"draft_key": slug},
        {"message_note_path": raw},
        {"message_note_path": {"$regex": escaped_raw}},
        {"message_note_path": {"$regex": escaped_slug}},
    ]

    if is_object_id(raw):
        conditions.insert(0, {"_id": ObjectId(raw)})

    matches = list(db.message_drafts.find({"$or": conditions}).sort("updated_at", -1).limit(5))
    if not matches:
        raise SystemExit(f"No message draft found for identifier: {identifier}")

    if len(matches) > 1:
        print(f"Multiple message drafts matched {identifier!r}; using most recently updated record.")

    return matches[0]


def require_sent(draft: dict) -> None:
    if draft.get("send_status") != "sent":
        raise SystemExit(
            "Response logging requires send_status=sent. "
            f"Current send_status={draft.get('send_status', 'not_set')}."
        )


def response_event(draft: dict, outcome: str, note: str, responded_at: datetime) -> dict:
    return {
        "outcome": outcome,
        "note": note,
        "responded_at": responded_at,
        "logged_at": responded_at,
        "draft_id": draft["_id"],
        "recipient_name": draft.get("recipient_name", ""),
    }


def update_draft(db, draft: dict, outcome: str, note: str, responded_at: datetime) -> None:
    event = response_event(draft, outcome, note, responded_at)
    db.message_drafts.update_one(
        {"_id": draft["_id"]},
        {
            "$set": {
                "response_status": outcome,
                "response_note": note,
                "responded_at": responded_at,
                "updated_at": responded_at,
            },
            "$push": {"response_events": event},
        },
    )


def update_linked_target(db, draft: dict, outcome: str, note: str, responded_at: datetime) -> str:
    target_type = draft.get("target_type")
    target_id = draft.get("target_id")
    if not target_id or not is_object_id(str(target_id)):
        return "No linked target updated; draft target_id is missing or invalid."

    object_id = ObjectId(str(target_id))
    if target_type == "contact":
        contact_status = CONTACT_STATUS_BY_OUTCOME.get(outcome)
        if not contact_status:
            return f"No contact status mapping for outcome={outcome}; contact left unchanged."

        event = {
            "status": contact_status,
            "outcome": outcome,
            "note": note,
            "created_at": responded_at,
            "message_draft_id": draft["_id"],
        }
        result = db.contacts.update_one(
            {"_id": object_id},
            {
                "$set": {
                    "contact_status": contact_status,
                    "response_status": outcome,
                    "response_note": note,
                    "responded_at": responded_at,
                    "latest_message_draft_id": draft["_id"],
                    "updated_at": responded_at,
                },
                "$push": {"contact_lifecycle": event},
            },
        )
        return f"Linked contact contact_status set to {contact_status}." if result.matched_count else "Linked contact not found."

    if target_type == "lead":
        outreach_status = LEAD_STATUS_BY_OUTCOME.get(outcome)
        if not outreach_status:
            return f"No lead outreach_status mapping for outcome={outcome}; lead left unchanged."

        event = {
            "status": outreach_status,
            "outcome": outcome,
            "note": note,
            "created_at": responded_at,
            "message_draft_id": draft["_id"],
        }
        result = db.leads.update_one(
            {"_id": object_id},
            {
                "$set": {
                    "outreach_status": outreach_status,
                    "outreach_status_updated_at": responded_at,
                    "outreach_status_note": note,
                    "response_status": outcome,
                    "latest_message_draft_id": draft["_id"],
                    "updated_at": responded_at,
                },
                "$push": {"outreach_lifecycle": event},
            },
        )
        return f"Linked lead outreach_status set to {outreach_status}." if result.matched_count else "Linked lead not found."

    return f"No linked target updated; unsupported target_type={target_type}."


def build_meeting_prep(draft: dict, note: str, responded_at: datetime) -> str:
    return f"""

## Meeting Prep

### {responded_at.isoformat()}

## Objective

Prepare for a human-led follow-up conversation with {draft.get("recipient_name", "the recipient")}.

## Context

- Module: {draft.get("module", "")}
- Target type: {draft.get("target_type", "")}
- Company: {draft.get("company", "")}
- Subject line: {draft.get("subject_line", "")}
- Response note: {note or "Call booked from manual response logging."}

## Questions To Prepare

- What problem or opportunity did the recipient respond to?
- What context should be verified before the conversation?
- What offer or next step should be discussed?
- What outcome should be logged after the call?

## Checklist

- [ ] Review the original message draft.
- [ ] Review contact or lead context in Mongo/vault notes.
- [ ] Prepare a short agenda.
- [ ] Log the call outcome after the meeting.
"""


def append_response_log(
    vault_path: Path,
    draft: dict,
    outcome: str,
    note: str,
    target_result: str,
    responded_at: datetime,
) -> Path:
    relative_path = draft.get("message_note_path")
    if not relative_path:
        raise SystemExit("Message draft is missing message_note_path.")

    path = vault_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"# Message Draft: {draft.get('recipient_name', 'Unknown')}\n", encoding="utf-8")

    note_line = f"- Note: {note}\n" if note else ""
    entry = f"""

## Response Log

### {responded_at.isoformat()}

- Outcome: {outcome}
- Response status: {outcome}
- Draft ID: {draft["_id"]}
- Recipient: {draft.get("recipient_name", "")}
- Target type: {draft.get("target_type", "")}
- Linked target update: {target_result}
{note_line}- No message sent.
- No calendar event created.
"""
    if outcome == "call_booked":
        entry += build_meeting_prep(draft, note, responded_at)

    with path.open("a", encoding="utf-8") as handle:
        handle.write(entry)

    return path


def main() -> None:
    args = parse_args()
    vault_path = Path(args.vault)
    responded_at = utc_now()

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
        db = get_database(client)
        draft = find_draft(db, args.draft)
        require_sent(draft)
        update_draft(db, draft, args.outcome, args.note, responded_at)
        target_result = update_linked_target(db, draft, args.outcome, args.note, responded_at)
        note_path = append_response_log(vault_path, draft, args.outcome, args.note, target_result, responded_at)
    finally:
        client.close()

    print(f"Response logged for: {draft.get('recipient_name')}")
    print(f"Outcome: {args.outcome}")
    print(f"Response status: {args.outcome}")
    print(target_result)
    print(f"Message note updated: {note_path}")
    print("No message sent. No calendar event created.")


if __name__ == "__main__":
    main()
