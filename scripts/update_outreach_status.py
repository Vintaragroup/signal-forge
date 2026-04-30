import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient

from core.constants import OUTREACH_STATUSES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_PATH = PROJECT_ROOT / "vault"
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"
VALID_STATUSES = OUTREACH_STATUSES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Track outreach lifecycle progress for a reviewed lead.")
    parser.add_argument("lead", help="Lead ObjectId, company slug, lead note slug, review note slug, or outreach note slug")
    parser.add_argument("status", choices=VALID_STATUSES, help="New outreach lifecycle status")
    parser.add_argument("--note", default="", help="Optional lifecycle note")
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


def timestamp_slug(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "untitled"


def yaml_quote(value: str) -> str:
    return '"' + str(value).replace('"', '\\"') + '"'


def get_database(client: MongoClient):
    try:
        return client.get_default_database()
    except Exception:
        return client["signalforge"]


def is_object_id(value: str) -> bool:
    return ObjectId.is_valid(value)


def find_lead(db, identifier: str) -> dict:
    raw = identifier.strip()
    stem = Path(raw).stem
    slug = slugify(stem)
    escaped_raw = re.escape(raw)
    escaped_slug = re.escape(slug)

    conditions = [
        {"company_slug": slug},
        {"note_path": {"$regex": escaped_raw}},
        {"review_queue_path": {"$regex": escaped_raw}},
        {"outreach_note_path": {"$regex": escaped_raw}},
        {"note_path": {"$regex": escaped_slug}},
        {"review_queue_path": {"$regex": escaped_slug}},
        {"outreach_note_path": {"$regex": escaped_slug}},
    ]

    if is_object_id(raw):
        conditions.insert(0, {"_id": ObjectId(raw)})

    matches = list(db.leads.find({"$or": conditions}).sort("updated_at", -1).limit(5))
    if not matches:
        raise SystemExit(f"No lead found for identifier: {identifier}")

    if len(matches) > 1:
        print(f"Multiple leads matched {identifier!r}; using most recently updated record.")

    return matches[0]


def vault_file(vault_path: Path, relative_path: str) -> Path | None:
    if not relative_path:
        return None
    return vault_path / relative_path


def infer_outreach_path(lead: dict) -> str:
    return f"outreach/{slugify(lead.get('run_id', 'manual'))}-{lead.get('company_slug', slugify(lead.get('company_name', 'lead')))}.md"


def resolve_outreach_file(vault_path: Path, lead: dict) -> tuple[str | None, Path | None]:
    relative_path = lead.get("outreach_note_path") or infer_outreach_path(lead)
    path = vault_path / relative_path
    if path.exists():
        return relative_path, path
    return None, None


def append_lifecycle_log(path: Path, lead: dict, status: str, note: str, followup_path: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now().isoformat()
    note_line = f"- Note: {note}\n" if note else ""
    followup_line = f"- Follow-up note: {followup_path}\n" if followup_path else ""
    entry = f"""

## Outreach Lifecycle Log

### {timestamp}

- Status: {status}
- Lead ID: {lead["_id"]}
- Company: {lead.get("company_name", "")}
{note_line}{followup_line}"""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(entry)


def followup_note_path(lead: dict, now: datetime) -> str:
    return f"followups/{slugify(lead.get('run_id', 'manual'))}-{lead['company_slug']}-{timestamp_slug(now).lower()}.md"


def build_followup_note(lead: dict, status: str, note: str, now: datetime) -> str:
    lead_score = lead.get("lead_score") or lead.get("score", "")
    return f"""---
type: follow_up
status: open
outreach_status: {status}
run_id: {yaml_quote(lead.get("run_id", ""))}
company: {yaml_quote(lead.get("company_name", ""))}
lead_score: {lead_score}
created: {now.date().isoformat()}
---

# Follow-Up: {lead.get("company_name", "")}

## Context

- Company: {lead.get("company_name", "")}
- Lead score: {lead_score}/100
- Outreach status: {status}
- Outreach note: {lead.get("outreach_note_path", "Not available")}

## Reason

{note or "Follow-up needed after human outreach activity."}

## Recommended Offer

{lead.get("recommended_offer", "")}

## Next Action

- Review the latest outreach note.
- Choose the follow-up channel.
- Send only after human approval.
- Log the next status with `scripts/update_outreach_status.py`.
"""


def create_followup_note(vault_path: Path, lead: dict, status: str, note: str, now: datetime) -> str:
    relative_path = followup_note_path(lead, now)
    path = vault_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_followup_note(lead, status, note, now), encoding="utf-8")
    return relative_path


def append_meeting_prep(outreach_file: Path, lead: dict, note: str) -> None:
    timestamp = utc_now().isoformat()
    prep = f"""

## Meeting Prep

### {timestamp}

## Call Objective

Understand whether {lead.get("company_name", "this company")} needs a better local lead follow-up workflow and whether the recommended offer is relevant.

## Prep Notes

- Lead score: {lead.get("lead_score") or lead.get("score", "")}/100
- Priority reason: {lead.get("priority_reason", "")}
- Recommended offer: {lead.get("recommended_offer", "")}
- Lifecycle note: {note or "Booked call logged."}

## Questions To Ask

- What happens today when a new local lead comes in?
- Where do leads usually get lost or delayed?
- Which service area or job type matters most right now?
- What would make follow-up easier for the team?

## Meeting Checklist

- [ ] Review lead and company notes.
- [ ] Verify website and local positioning.
- [ ] Confirm the offer before the call.
- [ ] Log the outcome after the meeting.
"""
    with outreach_file.open("a", encoding="utf-8") as handle:
        handle.write(prep)


def update_mongo(db, lead: dict, status: str, note: str, followup_path: str | None) -> None:
    now = utc_now()
    event = {
        "status": status,
        "note": note,
        "created_at": now,
    }
    if followup_path:
        event["followup_note_path"] = followup_path

    update = {
        "outreach_status": status,
        "outreach_status_updated_at": now,
        "outreach_status_note": note,
        "updated_at": now,
    }
    if followup_path:
        update["latest_followup_note_path"] = followup_path

    db.leads.update_one({"_id": lead["_id"]}, {"$set": update, "$push": {"outreach_lifecycle": event}})
    db.companies.update_one(
        {"run_id": lead.get("run_id"), "company_slug": lead.get("company_slug")},
        {"$set": update},
    )


def main() -> None:
    args = parse_args()
    vault_path = Path(args.vault)
    vault_path.mkdir(parents=True, exist_ok=True)
    (vault_path / "followups").mkdir(parents=True, exist_ok=True)

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
        db = get_database(client)
        lead = find_lead(db, args.lead)

        now = utc_now()
        outreach_relative_path, outreach_file = resolve_outreach_file(vault_path, lead)
        followup_path = None

        if args.status == "follow_up_needed":
            followup_path = create_followup_note(vault_path, lead, args.status, args.note, now)

        update_mongo(db, lead, args.status, args.note, followup_path)

        lead_note = vault_file(vault_path, lead.get("note_path", ""))
        if lead_note and lead_note.exists():
            append_lifecycle_log(lead_note, lead, args.status, args.note, followup_path)

        if outreach_file:
            append_lifecycle_log(outreach_file, lead, args.status, args.note, followup_path)
            if args.status == "booked_call":
                append_meeting_prep(outreach_file, lead, args.note)
        elif args.status == "booked_call":
            print("No outreach note found; skipped meeting prep append.")

        print(f"Updated outreach status for: {lead.get('company_name')}")
        print(f"Status: {args.status}")
        if lead_note:
            print(f"Lead note checked: {lead_note}")
        if outreach_relative_path:
            print(f"Outreach note updated: {vault_path / outreach_relative_path}")
        if followup_path:
            print(f"Follow-up note created: {vault_path / followup_path}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
