import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bson import ObjectId
from pymongo import MongoClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_PATH = PROJECT_ROOT / "vault"
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a local SignalForge meeting prep note.")
    parser.add_argument("target", help="Contact, lead, or message draft ObjectId/slug/path.")
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


def markdown_value(value: Any, fallback: str = "Not available.") -> str:
    text = clean_text(value)
    return text if text else fallback


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


def resolve_target(db, identifier: str) -> tuple[str, dict, dict | None, dict | None]:
    contact = find_one(db, "contacts", identifier, ("contact_key", "name", "company", "email", "phone"))
    if contact:
        draft = latest_draft_for_target(db, "contact", contact["_id"])
        return "contact", draft or {}, contact, None

    lead = find_one(db, "leads", identifier, ("company_slug", "company_name", "note_path", "review_queue_path", "outreach_note_path"))
    if lead:
        draft = latest_draft_for_target(db, "lead", lead["_id"])
        return "lead", draft or {}, None, lead

    draft = find_one(db, "message_drafts", identifier, ("draft_key", "message_note_path", "recipient_name", "company"))
    if draft:
        contact = linked_contact(db, draft)
        lead = linked_lead(db, draft)
        return "message_draft", draft, contact, lead

    raise SystemExit(f"No contact, lead, or message draft found for identifier: {identifier}")


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


def display_name(draft: dict, contact: dict | None, lead: dict | None) -> str:
    if contact:
        return clean_text(contact.get("name")) or clean_text(contact.get("company")) or "Contact"
    if lead:
        return clean_text(lead.get("company_name")) or "Lead"
    return clean_text(draft.get("recipient_name")) or clean_text(draft.get("company")) or "Meeting"


def company_name(draft: dict, contact: dict | None, lead: dict | None) -> str:
    if contact:
        return clean_text(contact.get("company"))
    if lead:
        return clean_text(lead.get("company_name"))
    return clean_text(draft.get("company"))


def module_name(draft: dict, contact: dict | None, lead: dict | None) -> str:
    return clean_text(draft.get("module")) or clean_text((contact or {}).get("module")) or clean_text((lead or {}).get("module")) or "contractor_growth"


def source_value(draft: dict, contact: dict | None, lead: dict | None) -> str:
    return clean_text(draft.get("source")) or clean_text((contact or {}).get("source")) or clean_text((lead or {}).get("source"))


def priority_reason(draft: dict, contact: dict | None, lead: dict | None) -> str:
    return (
        clean_text(draft.get("priority_reason"))
        or clean_text((contact or {}).get("priority_reason"))
        or clean_text((lead or {}).get("priority_reason"))
        or "Prioritized from existing SignalForge status and operator review history."
    )


def recommended_offer(draft: dict, contact: dict | None, lead: dict | None) -> str:
    return (
        clean_text(draft.get("recommended_action"))
        or clean_text((contact or {}).get("recommended_action"))
        or clean_text((lead or {}).get("recommended_offer"))
        or clean_text((lead or {}).get("next_action"))
        or "Confirm the best offer during discovery before proposing next steps."
    )


def likely_pain_points(draft: dict, contact: dict | None, lead: dict | None) -> list[str]:
    points = []
    notes = clean_text((contact or {}).get("notes"))
    marketing_gap = clean_text((lead or {}).get("marketing_gap"))
    website_signal = clean_text((lead or {}).get("website_quality_signal"))
    response_note = clean_text(draft.get("response_note"))

    if notes:
        points.append(notes)
    if marketing_gap:
        points.append(marketing_gap)
    if website_signal:
        points.append(website_signal)
    if response_note:
        points.append(f"Recent response context: {response_note}")
    if not points:
        points.append("Clarify current growth bottleneck, follow-up process, and highest-value next action.")
    return points


def response_history(draft: dict, contact: dict | None, lead: dict | None) -> list[dict]:
    events = []
    for event in draft.get("response_events", []) or []:
        events.append(
            {
                "time": event.get("responded_at") or event.get("logged_at"),
                "status": event.get("outcome"),
                "note": event.get("note"),
                "source": "message_draft",
            }
        )
    for event in (contact or {}).get("contact_lifecycle", []) or []:
        events.append(
            {
                "time": event.get("created_at"),
                "status": event.get("outcome") or event.get("status"),
                "note": event.get("note"),
                "source": "contact",
            }
        )
    for event in (lead or {}).get("outreach_lifecycle", []) or []:
        events.append(
            {
                "time": event.get("created_at"),
                "status": event.get("outcome") or event.get("status"),
                "note": event.get("note"),
                "source": "lead",
            }
        )
    return events


def history_table(events: list[dict]) -> str:
    rows = ["| Time | Source | Status | Note |", "| --- | --- | --- | --- |"]
    for event in events:
        rows.append(
            "| "
            f"{table_text(event_time(event.get('time')))} | "
            f"{table_text(event.get('source'))} | "
            f"{table_text(event.get('status'))} | "
            f"{table_text(event.get('note'))} |"
        )
    if len(rows) == 2:
        rows.append("| No response history found | - | - | - |")
    return "\n".join(rows)


def bullet_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def discovery_questions(module: str, contact: dict | None, lead: dict | None) -> list[str]:
    if module == "insurance_growth":
        return [
            "Where do new quote or referral conversations usually stall?",
            "Which lines of business are most important to grow right now?",
            "How are follow-ups tracked after the first conversation?",
            "What would make a new lead worth prioritizing this month?",
            "Who else needs to be involved before testing a campaign or follow-up workflow?",
        ]
    if module == "contractor_growth":
        return [
            "What happens today when a local lead requests a quote?",
            "Which services or job types are highest value right now?",
            "Where do leads get delayed, missed, or lost?",
            "How quickly does the team follow up after a form fill or phone call?",
            "What would make a lead follow-up workflow worth testing?",
        ]
    if module == "artist_growth":
        return [
            "Which audience segment matters most for the next release or show?",
            "What fan actions are most valuable right now?",
            "Which content formats are already working?",
            "Where does engagement drop off?",
            "What should happen after a fan or venue responds?",
        ]
    return [
        "Which audience or buyer segment is most valuable right now?",
        "What signal made this conversation worth prioritizing?",
        "What current workflow is slow, manual, or inconsistent?",
        "What would a successful next step look like?",
        "What should be avoided in follow-up messaging?",
    ]


def call_objective(draft: dict, contact: dict | None, lead: dict | None) -> str:
    company = company_name(draft, contact, lead) or display_name(draft, contact, lead)
    offer = recommended_offer(draft, contact, lead)
    return f"Confirm whether {company} has a real need behind the response, validate the context, and decide whether to move forward with: {offer}"


def note_path_for(name: str, generated_at: datetime) -> str:
    return f"meetings/{slugify(name)}-{generated_at.strftime('%Y%m%dT%H%M%SZ')}.md"


def build_note(target_type: str, draft: dict, contact: dict | None, lead: dict | None, generated_at: datetime) -> str:
    name = display_name(draft, contact, lead)
    company = company_name(draft, contact, lead)
    module = module_name(draft, contact, lead)
    source = source_value(draft, contact, lead)
    score_or_segment = clean_text((contact or {}).get("segment")) or clean_text((lead or {}).get("lead_score")) or clean_text(draft.get("segment")) or clean_text(draft.get("lead_score"))
    original_message = clean_text(draft.get("message_body"))
    subject = clean_text(draft.get("subject_line"))

    return f"""---
type: meeting_prep
module: {module}
target_type: {target_type}
created: {generated_at.date().isoformat()}
---

# Meeting Prep: {name}

## Person / Company Summary

| Field | Value |
| --- | --- |
| Person | {table_text(name)} |
| Company | {table_text(company)} |
| Role | {table_text((contact or {}).get("role"))} |
| Email | {table_text((contact or {}).get("email"))} |
| Phone | {table_text((contact or {}).get("phone"))} |
| Status | {table_text((contact or {}).get("contact_status") or (lead or {}).get("outreach_status") or draft.get("response_status"))} |
| Score / Segment | {table_text(score_or_segment)} |

## Source / Module

- Module: `{module}`
- Source: {source or "Not available."}
- Message draft: {draft.get("message_note_path", "Not available.")}
- Lead note: {(lead or {}).get("note_path", "Not available.")}

## Why Prioritized

{priority_reason(draft, contact, lead)}

## Original Message Sent

Subject: {subject or "Not available."}

{original_message or "No message draft found for this target."}

## Response History

{history_table(response_history(draft, contact, lead))}

## Likely Pain Points

{bullet_list(likely_pain_points(draft, contact, lead))}

## Recommended Offer

{recommended_offer(draft, contact, lead)}

## Discovery Questions

{bullet_list(discovery_questions(module, contact, lead))}

## Call Objective

{call_objective(draft, contact, lead)}

## Follow-Up Checklist

- [ ] Confirm the decision maker and best contact path.
- [ ] Verify the problem in the prospect's words.
- [ ] Confirm whether the recommended offer is relevant.
- [ ] Capture objections or missing information.
- [ ] Log the outcome after the call.
- [ ] Create next follow-up if needed.

## Safety

- No calendar event created.
- No message sent.
- Generated from local MongoDB and markdown context only.
"""


def write_meeting_note(vault_path: Path, target_type: str, draft: dict, contact: dict | None, lead: dict | None, generated_at: datetime) -> Path:
    name = display_name(draft, contact, lead)
    relative_path = note_path_for(name, generated_at)
    path = vault_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_note(target_type, draft, contact, lead, generated_at), encoding="utf-8")
    return path


def main() -> None:
    args = parse_args()
    generated_at = utc_now()
    vault_path = Path(args.vault)

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
        db = get_database(client)
        target_type, draft, contact, lead = resolve_target(db, args.target)
        note_path = write_meeting_note(vault_path, target_type, draft, contact, lead, generated_at)
    finally:
        client.close()

    print(f"Meeting prep generated: {note_path}")
    print(f"Target type: {target_type}")
    print("No calendar event created. No message sent.")


if __name__ == "__main__":
    main()
