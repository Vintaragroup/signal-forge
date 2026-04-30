import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bson import ObjectId
from pymongo import MongoClient

from core.constants import DEAL_OUTCOMES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_PATH = PROJECT_ROOT / "vault"
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"
VALID_OUTCOMES = DEAL_OUTCOMES

LEAD_OUTREACH_STATUS = {
    "proposal_sent": "replied",
    "negotiation": "replied",
    "closed_won": "closed_won",
    "closed_lost": "closed_lost",
    "nurture": "follow_up_needed",
    "no_show": "follow_up_needed",
    "not_fit": "closed_lost",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log a SignalForge deal outcome.")
    parser.add_argument("target", help="Contact, lead, message draft, or meeting prep ObjectId/slug/path.")
    parser.add_argument("--outcome", required=True, choices=VALID_OUTCOMES, help="Deal outcome.")
    parser.add_argument("--deal-value", type=float, default=None, help="Optional deal value.")
    parser.add_argument("--note", default="", help="Optional outcome note.")
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


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def table_text(value: Any) -> str:
    text = clean_text(value) or "-"
    return text.replace("|", "\\|").replace("\n", " ")


def money_text(value: float | None) -> str:
    if value is None:
        return "Not provided"
    return f"${value:,.2f}"


def event_time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return table_text(value)


def lookup_conditions(identifier: str, fields: tuple[str, ...]) -> list[dict]:
    raw = identifier.strip()
    stem = Path(raw).stem
    slug = slugify(stem)
    escaped_raw = re.escape(raw)
    escaped_slug = re.escape(slug)
    words_pattern = r"[^a-z0-9]+".join(re.escape(part) for part in slug.split("-") if part)
    conditions = []

    if is_object_id(raw):
        conditions.append({"_id": ObjectId(raw)})

    for field in fields:
        conditions.extend(
            [
                {field: raw},
                {field: slug},
                {field: {"$regex": escaped_raw}},
                {field: {"$regex": escaped_slug}},
            ]
        )
        if words_pattern:
            conditions.append({field: {"$regex": words_pattern, "$options": "i"}})

    return conditions


def find_one(db, collection: str, identifier: str, fields: tuple[str, ...]) -> dict | None:
    conditions = lookup_conditions(identifier, fields)
    if not conditions:
        return None
    return db[collection].find_one({"$or": conditions}, sort=[("updated_at", -1)])


def find_meeting_file(vault_path: Path, identifier: str, explicit_only: bool = False) -> Path | None:
    raw = identifier.strip()
    raw_path = Path(raw)
    candidates = []

    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.extend(
            [
                PROJECT_ROOT / raw,
                vault_path / raw,
                vault_path / "meetings" / raw,
            ]
        )
        if not raw.endswith(".md"):
            candidates.extend(
                [
                    PROJECT_ROOT / f"{raw}.md",
                    vault_path / f"{raw}.md",
                    vault_path / "meetings" / f"{raw}.md",
                ]
            )

    for candidate in candidates:
        if candidate.exists() and candidate.is_file() and "meetings" in candidate.parts:
            return candidate

    if explicit_only and "meeting" not in raw and "meetings" not in raw:
        return None

    slug = slugify(Path(raw).stem)
    meetings_dir = vault_path / "meetings"
    if not meetings_dir.exists():
        return None

    matches = [
        path
        for path in meetings_dir.glob("*.md")
        if slug == slugify(path.stem) or slug in slugify(path.stem)
    ]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def parse_meeting_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    message_match = re.search(r"^- Message draft:\s*(.+)$", text, flags=re.MULTILINE)
    lead_match = re.search(r"^- Lead note:\s*(.+)$", text, flags=re.MULTILINE)
    module_match = re.search(r"^- Module:\s*`?([^`\n]+)`?$", text, flags=re.MULTILINE)
    person_match = re.search(r"^\| Person \|\s*([^|]+)\|", text, flags=re.MULTILINE)
    company_match = re.search(r"^\| Company \|\s*([^|]+)\|", text, flags=re.MULTILINE)

    message_path = clean_text(message_match.group(1)) if message_match else ""
    lead_path = clean_text(lead_match.group(1)) if lead_match else ""
    return {
        "meeting_note_path": str(path.relative_to(path.parents[1])) if "vault" in path.parts else str(path),
        "message_note_path": "" if message_path == "Not available." else message_path,
        "lead_note_path": "" if lead_path == "Not available." else lead_path,
        "module": clean_text(module_match.group(1)) if module_match else "",
        "person": clean_text(person_match.group(1)) if person_match else "",
        "company": clean_text(company_match.group(1)) if company_match else "",
    }


def linked_contact(db, draft: dict) -> dict | None:
    if draft.get("target_type") == "contact" and is_object_id(str(draft.get("target_id", ""))):
        return db.contacts.find_one({"_id": ObjectId(str(draft["target_id"]))})
    return None


def linked_lead(db, draft: dict) -> dict | None:
    if draft.get("target_type") == "lead" and is_object_id(str(draft.get("target_id", ""))):
        return db.leads.find_one({"_id": ObjectId(str(draft["target_id"]))})
    return None


def latest_draft_for_target(db, target_type: str, target_id: ObjectId) -> dict | None:
    return db.message_drafts.find_one(
        {"target_type": target_type, "target_id": str(target_id)},
        sort=[("updated_at", -1), ("created_at", -1)],
    )


def resolve_from_meeting(db, meeting: dict) -> tuple[dict, dict | None, dict | None]:
    draft = {}
    if meeting.get("message_note_path"):
        draft = find_one(db, "message_drafts", meeting["message_note_path"], ("message_note_path", "draft_key")) or {}

    contact = linked_contact(db, draft) if draft else None
    lead = linked_lead(db, draft) if draft else None

    if not lead and meeting.get("lead_note_path"):
        lead = find_one(db, "leads", meeting["lead_note_path"], ("note_path", "company_slug", "company_name"))
    if not contact and meeting.get("person"):
        contact = find_one(db, "contacts", meeting["person"], ("name", "company", "contact_key"))
    if not contact and meeting.get("company"):
        contact = find_one(db, "contacts", meeting["company"], ("company", "name", "contact_key"))
    if not lead and meeting.get("company"):
        lead = find_one(db, "leads", meeting["company"], ("company_name", "company_slug", "note_path"))

    if not draft:
        if contact:
            draft = latest_draft_for_target(db, "contact", contact["_id"]) or {}
        elif lead:
            draft = latest_draft_for_target(db, "lead", lead["_id"]) or {}

    return draft, contact, lead


def resolve_target(db, vault_path: Path, identifier: str) -> dict:
    explicit_meeting = find_meeting_file(vault_path, identifier, explicit_only=True)
    if explicit_meeting:
        meeting = parse_meeting_file(explicit_meeting)
        draft, contact, lead = resolve_from_meeting(db, meeting)
        return {"target_type": "meeting_prep", "draft": draft, "contact": contact, "lead": lead, "meeting": meeting}

    draft = find_one(db, "message_drafts", identifier, ("draft_key", "message_note_path", "recipient_name", "company"))
    if draft:
        return {
            "target_type": "message_draft",
            "draft": draft,
            "contact": linked_contact(db, draft),
            "lead": linked_lead(db, draft),
            "meeting": {},
        }

    contact = find_one(db, "contacts", identifier, ("contact_key", "name", "company", "email", "phone"))
    if contact:
        draft = latest_draft_for_target(db, "contact", contact["_id"]) or {}
        return {"target_type": "contact", "draft": draft, "contact": contact, "lead": None, "meeting": {}}

    lead = find_one(db, "leads", identifier, ("company_slug", "company_name", "note_path", "review_queue_path", "outreach_note_path"))
    if lead:
        draft = latest_draft_for_target(db, "lead", lead["_id"]) or {}
        return {"target_type": "lead", "draft": draft, "contact": None, "lead": lead, "meeting": {}}

    meeting_file = find_meeting_file(vault_path, identifier)
    if meeting_file:
        meeting = parse_meeting_file(meeting_file)
        draft, contact, lead = resolve_from_meeting(db, meeting)
        return {"target_type": "meeting_prep", "draft": draft, "contact": contact, "lead": lead, "meeting": meeting}

    raise SystemExit(f"No contact, lead, message draft, or meeting prep found for identifier: {identifier}")


def display_name(context: dict) -> str:
    contact = context.get("contact") or {}
    lead = context.get("lead") or {}
    draft = context.get("draft") or {}
    meeting = context.get("meeting") or {}
    return (
        clean_text(contact.get("name"))
        or clean_text(lead.get("company_name"))
        or clean_text(draft.get("recipient_name"))
        or clean_text(meeting.get("person"))
        or clean_text(meeting.get("company"))
        or "Deal"
    )


def company_name(context: dict) -> str:
    contact = context.get("contact") or {}
    lead = context.get("lead") or {}
    draft = context.get("draft") or {}
    meeting = context.get("meeting") or {}
    return (
        clean_text(contact.get("company"))
        or clean_text(lead.get("company_name"))
        or clean_text(draft.get("company"))
        or clean_text(meeting.get("company"))
    )


def module_name(context: dict) -> str:
    draft = context.get("draft") or {}
    contact = context.get("contact") or {}
    lead = context.get("lead") or {}
    meeting = context.get("meeting") or {}
    return (
        clean_text(draft.get("module"))
        or clean_text(contact.get("module"))
        or clean_text(lead.get("module"))
        or clean_text(meeting.get("module"))
        or "contractor_growth"
    )


def source_value(context: dict) -> str:
    draft = context.get("draft") or {}
    contact = context.get("contact") or {}
    lead = context.get("lead") or {}
    return clean_text(draft.get("source")) or clean_text(contact.get("source")) or clean_text(lead.get("source"))


def stable_target_key(context: dict) -> str:
    contact = context.get("contact")
    lead = context.get("lead")
    draft = context.get("draft")
    meeting = context.get("meeting") or {}
    if contact:
        return f"contact-{contact['_id']}"
    if lead:
        return f"lead-{lead['_id']}"
    if draft:
        return f"draft-{draft['_id']}"
    return f"meeting-{slugify(meeting.get('meeting_note_path', display_name(context)))}"


def deal_key(context: dict) -> str:
    return slugify(f"{module_name(context)}-{stable_target_key(context)}")


def deal_note_path(context: dict) -> str:
    return f"deals/{deal_key(context)}.md"


def target_ids(context: dict) -> dict:
    contact = context.get("contact")
    lead = context.get("lead")
    draft = context.get("draft")
    return {
        "contact_id": contact["_id"] if contact else None,
        "lead_id": lead["_id"] if lead else None,
        "message_draft_id": draft["_id"] if draft else None,
    }


def path_to_conversion(context: dict, outcome: str) -> list[str]:
    draft = context.get("draft") or {}
    contact = context.get("contact") or {}
    lead = context.get("lead") or {}
    meeting = context.get("meeting") or {}
    path = []
    source = source_value(context)
    if source:
        path.append(f"Source captured: {source}")
    if contact:
        path.append(f"Contact status: {contact.get('contact_status', 'unknown')}")
    if lead:
        path.append(f"Lead review/outreach: {lead.get('review_status', '-')}/{lead.get('outreach_status', '-')}")
    if draft:
        path.append(
            f"Message lifecycle: review={draft.get('review_status', '-')}, send={draft.get('send_status', '-')}, response={draft.get('response_status', '-')}"
        )
    if meeting.get("meeting_note_path"):
        path.append(f"Meeting prep created: {meeting['meeting_note_path']}")
    path.append(f"Deal outcome logged: {outcome}")
    return path


def recommended_offer(context: dict) -> str:
    draft = context.get("draft") or {}
    contact = context.get("contact") or {}
    lead = context.get("lead") or {}
    return (
        clean_text(draft.get("recommended_action"))
        or clean_text(contact.get("recommended_action"))
        or clean_text(lead.get("recommended_offer"))
        or clean_text(lead.get("next_action"))
        or "Define the next commercial step with the operator."
    )


def next_onboarding_action(context: dict) -> str:
    return (
        "Create an onboarding checklist, confirm owner and timeline, collect required access/context, "
        "and schedule the first delivery checkpoint manually."
    )


def future_nurture_recommendation(note: str) -> str:
    if note:
        return f"Keep this account in a low-frequency nurture track and reference the loss reason: {note}"
    return "Keep this account in a low-frequency nurture track and revisit when fit, timing, or need changes."


def deal_event(outcome: str, deal_value: float | None, note: str, logged_at: datetime) -> dict:
    return {
        "outcome": outcome,
        "deal_value": deal_value,
        "note": note,
        "logged_at": logged_at,
    }


def upsert_deal(db, context: dict, outcome: str, deal_value: float | None, note: str, logged_at: datetime, note_path: str) -> ObjectId:
    key = deal_key(context)
    ids = target_ids(context)
    update = {
        "deal_key": key,
        "module": module_name(context),
        "source": source_value(context),
        "person": display_name(context),
        "company": company_name(context),
        "outcome": outcome,
        "deal_status": outcome,
        "deal_value": deal_value,
        "note": note,
        "deal_note_path": note_path,
        "path_to_conversion": path_to_conversion(context, outcome),
        "recommended_offer": recommended_offer(context),
        "updated_at": logged_at,
        **ids,
    }
    if context.get("meeting", {}).get("meeting_note_path"):
        update["meeting_note_path"] = context["meeting"]["meeting_note_path"]
    if outcome == "closed_won":
        update["next_onboarding_action"] = next_onboarding_action(context)
    if outcome == "closed_lost":
        update["loss_reason_note"] = note
        update["future_nurture_recommendation"] = future_nurture_recommendation(note)

    result = db.deals.update_one(
        {"deal_key": key},
        {
            "$set": update,
            "$setOnInsert": {"created_at": logged_at},
            "$push": {"deal_events": deal_event(outcome, deal_value, note, logged_at)},
        },
        upsert=True,
    )
    if result.upserted_id:
        return result.upserted_id
    deal = db.deals.find_one({"deal_key": key}, {"_id": 1})
    return deal["_id"]


def update_linked_records(db, context: dict, deal_id: ObjectId, outcome: str, deal_value: float | None, note: str, logged_at: datetime, note_path: str) -> None:
    event = {
        "deal_id": deal_id,
        "outcome": outcome,
        "deal_value": deal_value,
        "note": note,
        "logged_at": logged_at,
        "deal_note_path": note_path,
    }
    common_set = {
        "deal_outcome": outcome,
        "deal_status": outcome,
        "deal_value": deal_value,
        "latest_deal_id": deal_id,
        "latest_deal_note_path": note_path,
        "updated_at": logged_at,
    }

    contact = context.get("contact")
    if contact:
        db.contacts.update_one(
            {"_id": contact["_id"]},
            {
                "$set": {**common_set, "contact_status": outcome},
                "$push": {"deal_lifecycle": event},
            },
        )

    lead = context.get("lead")
    if lead:
        outreach_status = LEAD_OUTREACH_STATUS.get(outcome, lead.get("outreach_status"))
        db.leads.update_one(
            {"_id": lead["_id"]},
            {
                "$set": {**common_set, "outreach_status": outreach_status, "outreach_status_updated_at": logged_at},
                "$push": {"deal_lifecycle": event, "outreach_lifecycle": {"status": outreach_status, **event}},
            },
        )

    draft = context.get("draft")
    if draft:
        db.message_drafts.update_one(
            {"_id": draft["_id"]},
            {
                "$set": common_set,
                "$push": {"deal_events": event},
            },
        )


def outcome_log_text(context: dict, deal_id: ObjectId, outcome: str, deal_value: float | None, note: str, logged_at: datetime, note_path: str) -> str:
    note_line = f"- Note: {note}\n" if note else ""
    return f"""

## Deal Outcome Log

### {logged_at.isoformat()}

- Outcome: {outcome}
- Deal ID: {deal_id}
- Deal value: {money_text(deal_value)}
- Company: {company_name(context) or "Not available"}
- Person: {display_name(context)}
- Module: {module_name(context)}
- Deal note: {note_path}
{note_line}- No invoice created.
- No CRM API called.
- No message sent.
"""


def related_note_paths(context: dict, deal_note: str) -> list[str]:
    paths = [deal_note]
    draft = context.get("draft") or {}
    lead = context.get("lead") or {}
    meeting = context.get("meeting") or {}
    for path in (
        draft.get("message_note_path"),
        lead.get("note_path"),
        lead.get("review_queue_path"),
        lead.get("outreach_note_path"),
        meeting.get("meeting_note_path"),
    ):
        if path and path not in paths:
            paths.append(path)
    return paths


def append_to_related_notes(vault_path: Path, context: dict, deal_id: ObjectId, outcome: str, deal_value: float | None, note: str, logged_at: datetime, deal_note: str) -> None:
    entry = outcome_log_text(context, deal_id, outcome, deal_value, note, logged_at, deal_note)
    for relative_path in related_note_paths(context, deal_note):
        path = vault_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(f"# {Path(relative_path).stem}\n", encoding="utf-8")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry)


def deal_note_content(context: dict, deal_id: ObjectId, outcome: str, deal_value: float | None, note: str, logged_at: datetime) -> str:
    conversion = "\n".join(f"- {item}" for item in path_to_conversion(context, outcome))
    closed_won = ""
    if outcome == "closed_won":
        closed_won = f"""
## Closed Won Details

- Source: {source_value(context) or "Not available"}
- Module: `{module_name(context)}`
- Deal value: {money_text(deal_value)}

## Path To Conversion

{conversion}

## Next Onboarding Action

{next_onboarding_action(context)}
"""

    closed_lost = ""
    if outcome == "closed_lost":
        closed_lost = f"""
## Closed Lost Details

## Loss Reason Note

{note or "No loss reason note provided."}

## Future Nurture Recommendation

{future_nurture_recommendation(note)}
"""

    return f"""---
type: deal
deal_key: {deal_key(context)}
module: {module_name(context)}
outcome: {outcome}
updated: {logged_at.date().isoformat()}
---

# Deal: {company_name(context) or display_name(context)}

## Summary

| Field | Value |
| --- | --- |
| Deal ID | {deal_id} |
| Outcome | `{outcome}` |
| Deal value | {money_text(deal_value)} |
| Person | {table_text(display_name(context))} |
| Company | {table_text(company_name(context))} |
| Module | `{module_name(context)}` |
| Source | {table_text(source_value(context))} |
| Message draft | {table_text((context.get("draft") or {}).get("message_note_path"))} |
| Meeting prep | {table_text((context.get("meeting") or {}).get("meeting_note_path"))} |

## Recommended Offer

{recommended_offer(context)}

## Latest Outcome Note

{note or "No note provided."}

## Path To Conversion

{conversion}
{closed_won}{closed_lost}
## Safety

- No message sent.
- No invoice created.
- No CRM API called.
"""


def write_deal_note(vault_path: Path, context: dict, deal_id: ObjectId, outcome: str, deal_value: float | None, note: str, logged_at: datetime) -> str:
    relative_path = deal_note_path(context)
    path = vault_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(deal_note_content(context, deal_id, outcome, deal_value, note, logged_at), encoding="utf-8")
    return relative_path


def main() -> None:
    args = parse_args()
    logged_at = utc_now()
    vault_path = Path(args.vault)

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
        db = get_database(client)
        context = resolve_target(db, vault_path, args.target)
        note_path = deal_note_path(context)
        deal_id = upsert_deal(db, context, args.outcome, args.deal_value, args.note, logged_at, note_path)
        update_linked_records(db, context, deal_id, args.outcome, args.deal_value, args.note, logged_at, note_path)
        note_path = write_deal_note(vault_path, context, deal_id, args.outcome, args.deal_value, args.note, logged_at)
        append_to_related_notes(vault_path, context, deal_id, args.outcome, args.deal_value, args.note, logged_at, note_path)
    finally:
        client.close()

    print(f"Deal outcome logged: {args.outcome}")
    print(f"Deal value: {money_text(args.deal_value)}")
    print(f"Deal note: {vault_path / note_path}")
    print("No message sent. No invoice created. No CRM API called.")


if __name__ == "__main__":
    main()
