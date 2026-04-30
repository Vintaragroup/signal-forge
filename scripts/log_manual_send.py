import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient

from core.constants import MANUAL_SEND_CHANNELS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_PATH = PROJECT_ROOT / "vault"
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"
VALID_CHANNELS = MANUAL_SEND_CHANNELS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log a manually sent SignalForge message draft.")
    parser.add_argument("draft", help="Message draft ObjectId, draft key, note slug, or note path.")
    parser.add_argument("--channel", choices=VALID_CHANNELS, default="other", help="Manual send channel.")
    parser.add_argument("--note", default="", help="Optional send note.")
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


def require_approved(draft: dict) -> None:
    if draft.get("review_status") != "approved":
        raise SystemExit(
            "Manual send logging requires review_status=approved. "
            f"Current review_status={draft.get('review_status', 'not_set')}."
        )


def send_event(draft: dict, channel: str, note: str, sent_at: datetime) -> dict:
    return {
        "channel": channel,
        "note": note,
        "sent_at": sent_at,
        "logged_at": sent_at,
        "manual": True,
        "draft_id": draft["_id"],
        "recipient_name": draft.get("recipient_name", ""),
    }


def update_draft(db, draft: dict, channel: str, note: str, sent_at: datetime) -> None:
    event = send_event(draft, channel, note, sent_at)
    db.message_drafts.update_one(
        {"_id": draft["_id"]},
        {
            "$set": {
                "send_status": "sent",
                "sent_at": sent_at,
                "send_channel": channel,
                "send_note": note,
                "updated_at": sent_at,
            },
            "$push": {"send_events": event},
        },
    )


def update_linked_target(db, draft: dict, channel: str, note: str, sent_at: datetime) -> str:
    target_type = draft.get("target_type")
    target_id = draft.get("target_id")
    if not target_id or not is_object_id(str(target_id)):
        return "No linked target updated; draft target_id is missing or invalid."

    object_id = ObjectId(str(target_id))
    if target_type == "lead":
        event = {
            "status": "sent",
            "note": note,
            "channel": channel,
            "created_at": sent_at,
            "message_draft_id": draft["_id"],
        }
        result = db.leads.update_one(
            {"_id": object_id},
            {
                "$set": {
                    "outreach_status": "sent",
                    "outreach_status_updated_at": sent_at,
                    "outreach_status_note": note,
                    "latest_message_draft_id": draft["_id"],
                    "updated_at": sent_at,
                },
                "$push": {"outreach_lifecycle": event},
            },
        )
        return "Linked lead outreach_status set to sent." if result.matched_count else "Linked lead not found."

    if target_type == "contact":
        event = {
            "status": "contacted",
            "note": note,
            "channel": channel,
            "created_at": sent_at,
            "message_draft_id": draft["_id"],
        }
        result = db.contacts.update_one(
            {"_id": object_id},
            {
                "$set": {
                    "contact_status": "contacted",
                    "contacted_at": sent_at,
                    "contact_channel": channel,
                    "contact_note": note,
                    "latest_message_draft_id": draft["_id"],
                    "updated_at": sent_at,
                },
                "$push": {"contact_lifecycle": event},
            },
        )
        return "Linked contact contact_status set to contacted." if result.matched_count else "Linked contact not found."

    return f"No linked target updated; unsupported target_type={target_type}."


def append_send_log(vault_path: Path, draft: dict, channel: str, note: str, target_result: str, sent_at: datetime) -> Path:
    relative_path = draft.get("message_note_path")
    if not relative_path:
        raise SystemExit("Message draft is missing message_note_path.")

    path = vault_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"# Message Draft: {draft.get('recipient_name', 'Unknown')}\n", encoding="utf-8")

    note_line = f"- Note: {note}\n" if note else ""
    entry = f"""

## Manual Send Log

### {sent_at.isoformat()}

- Send status: sent
- Channel: {channel}
- Draft ID: {draft["_id"]}
- Recipient: {draft.get("recipient_name", "")}
- Target type: {draft.get("target_type", "")}
- Linked target update: {target_result}
{note_line}- Outbound action performed manually outside SignalForge.
- SignalForge did not send this message.
"""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(entry)

    return path


def main() -> None:
    args = parse_args()
    vault_path = Path(args.vault)
    sent_at = utc_now()

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
        db = get_database(client)
        draft = find_draft(db, args.draft)
        require_approved(draft)
        update_draft(db, draft, args.channel, args.note, sent_at)
        target_result = update_linked_target(db, draft, args.channel, args.note, sent_at)
        note_path = append_send_log(vault_path, draft, args.channel, args.note, target_result, sent_at)
    finally:
        client.close()

    print(f"Manual send logged for: {draft.get('recipient_name')}")
    print(f"Channel: {args.channel}")
    print("Send status: sent")
    print(target_result)
    print(f"Message note updated: {note_path}")
    print("SignalForge did not send this message.")


if __name__ == "__main__":
    main()
