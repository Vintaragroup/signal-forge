import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient

from core.constants import MESSAGE_REVIEW_DECISIONS, MESSAGE_REVIEW_STATUSES, SEND_STATUSES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_PATH = PROJECT_ROOT / "vault"
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"
VALID_DECISIONS = MESSAGE_REVIEW_DECISIONS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review a SignalForge message draft.")
    parser.add_argument("draft", help="Message draft ObjectId, draft key, note slug, or note path.")
    parser.add_argument("decision", choices=VALID_DECISIONS, help="Review decision.")
    parser.add_argument("--note", default="", help="Optional operator review note.")
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


def review_status_for(decision: str) -> str:
    if decision == "approve":
        return "approved"
    if decision == "reject":
        return "rejected"
    return "needs_revision"


def update_mongo(db, draft: dict, decision: str, note: str, reviewed_at: datetime) -> None:
    review_status = review_status_for(decision)
    update = {
        "review_status": review_status,
        "review_decision": decision,
        "review_note": note,
        "reviewed_at": reviewed_at,
        "updated_at": reviewed_at,
    }
    if decision == "approve":
        update["send_status"] = SEND_STATUSES[0]

    db.message_drafts.update_one({"_id": draft["_id"]}, {"$set": update})


def append_review_log(vault_path: Path, draft: dict, decision: str, note: str, reviewed_at: datetime) -> Path:
    relative_path = draft.get("message_note_path")
    if not relative_path:
        raise SystemExit("Message draft is missing message_note_path.")

    path = vault_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"# Message Draft: {draft.get('recipient_name', 'Unknown')}\n", encoding="utf-8")

    review_status = review_status_for(decision)
    note_line = f"- Note: {note}\n" if note else ""
    entry = f"""

## Message Review Log

### {reviewed_at.isoformat()}

- Decision: {decision}
- Review status: {review_status}
- Send status: {draft.get("send_status", "not_sent") if decision != "approve" else "not_sent"}
- Draft ID: {draft["_id"]}
- Recipient: {draft.get("recipient_name", "")}
{note_line}- No message sent.
"""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(entry)

    return path


def main() -> None:
    args = parse_args()
    vault_path = Path(args.vault)
    reviewed_at = utc_now()

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
        db = get_database(client)
        draft = find_draft(db, args.draft)
        update_mongo(db, draft, args.decision, args.note, reviewed_at)
        note_path = append_review_log(vault_path, draft, args.decision, args.note, reviewed_at)
    finally:
        client.close()

    print(f"Reviewed message draft: {draft.get('recipient_name')}")
    print(f"Decision: {args.decision}")
    print(f"Review status: {review_status_for(args.decision)}")
    print("Send status: not_sent" if args.decision == "approve" else f"Send status: {draft.get('send_status', 'not_sent')}")
    print(f"Message note updated: {note_path}")
    print("No message sent.")


if __name__ == "__main__":
    main()
