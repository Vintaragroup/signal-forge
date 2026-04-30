import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymongo import MongoClient

from core.constants import MESSAGE_REVIEW_STATUSES, SEND_STATUSES, VALID_MODULES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_PATH = PROJECT_ROOT / "vault"
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"
SUPPORTED_MODULES = VALID_MODULES

LEAD_QUERIES = {
    "contractor_growth": {
        "$or": [
            {"engine": {"$regex": "contractor_lead_engine"}},
            {"business_type": {"$regex": "contractor", "$options": "i"}},
        ]
    },
    "insurance_growth": {"module": "insurance_growth"},
    "artist_growth": {"module": "artist_growth"},
    "media_growth": {"module": "media_growth"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Draft safe, human-reviewed messages for scored contacts and approved leads.")
    parser.add_argument("--module", required=True, choices=SUPPORTED_MODULES, help="SignalForge module name.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum total drafts to create.")
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


def get_database(client: MongoClient):
    try:
        return client.get_default_database()
    except Exception:
        return client["signalforge"]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "draft"


def table_safe(value: Any) -> str:
    text = clean_text(value) or "-"
    return text.replace("|", "\\|").replace("\n", " ")


def first_name(name: str) -> str:
    parts = clean_text(name).split()
    return parts[0] if parts else "there"


def contractor_business_type(contact: dict) -> str:
    haystack = " ".join(
        clean_text(contact.get(field)).lower()
        for field in ("company", "role", "notes", "source")
    )
    if "roof" in haystack:
        return "roofing contractor"
    if "hvac" in haystack or "heating" in haystack or "cooling" in haystack:
        return "HVAC contractor"
    if "plumb" in haystack:
        return "plumbing contractor"
    return "contractor"


def contractor_location(contact: dict) -> str:
    city = clean_text(contact.get("city"))
    state = clean_text(contact.get("state"))
    if city and state:
        return f"{city}, {state}"
    return city or state or "your local market"


def contractor_contact_target(contact: dict, recipient: str, company: str, priority_reason: str) -> dict:
    business_type = contractor_business_type(contact)
    location = contractor_location(contact)
    subject_company = company or recipient
    recommended_action = (
        "Review their website/contact flow, missed lead capture, and quote follow-up process, "
        "then prepare a short human-approved outreach note."
    )
    subject = f"Quick lead follow-up idea for {subject_company}"
    body = (
        f"Hi {first_name(recipient)},\n\n"
        f"I am testing a simple growth workflow for {location} {business_type}s and thought {subject_company} looked like a fit.\n\n"
        "Most contractors lose opportunities when website requests, missed calls, or quote follow-ups are not handled quickly.\n\n"
        "I can put together a short audit of where leads may be slipping through and outline a simple follow-up system to help turn more requests into booked estimates.\n\n"
        "Worth sending over a quick example?\n\n"
        "Best,\n"
        "SignalForge operator"
    )

    return {
        "recommended_action": recommended_action,
        "priority_reason": priority_reason,
        "subject_line": subject,
        "message_body": body,
    }


def fetch_contacts(db, module: str, limit: int) -> list[dict]:
    return list(
        db.contacts.find({"module": module, "segment": "high_priority"})
        .sort([("contact_score", -1), ("company", 1), ("name", 1)])
        .limit(limit)
    )


def fetch_leads(db, module: str, limit: int) -> list[dict]:
    query = {
        "$and": [
            LEAD_QUERIES[module],
            {"review_status": {"$in": ["pursue", "approved"]}},
        ]
    }
    return list(
        db.leads.find(query)
        .sort([("lead_score", -1), ("updated_at", -1)])
        .limit(limit)
    )


def contact_target(contact: dict) -> dict:
    recipient = clean_text(contact.get("name")) or clean_text(contact.get("company")) or "Contact"
    company = clean_text(contact.get("company"))
    subject_company = company or recipient
    recommended_action = clean_text(contact.get("recommended_action")) or "Review this contact before any manual outreach."
    priority_reason = clean_text(contact.get("priority_reason")) or clean_text(contact.get("notes")) or "High-priority imported contact."
    contact_id = str(contact["_id"])

    if contact.get("module") == "contractor_growth":
        contractor_target = contractor_contact_target(contact, recipient, company, priority_reason)
        recommended_action = contractor_target["recommended_action"]
        subject = contractor_target["subject_line"]
        body = contractor_target["message_body"]
    else:
        subject = f"Quick idea for {subject_company}"
        body = (
            f"Hi {first_name(recipient)},\n\n"
            f"I was reviewing {subject_company} in the context of our growth workflow and noticed a potential fit for a simple next step.\n\n"
            f"Reason for review: {priority_reason}\n\n"
            f"Suggested next step: {recommended_action}\n\n"
            "If this looks relevant, I would tailor this note before sending and keep the message short, specific, and useful.\n\n"
            "Best,\n"
            "SignalForge operator"
        )

    return {
        "target_type": "contact",
        "target_id": contact_id,
        "target_key": clean_text(contact.get("contact_key")) or contact_id,
        "recipient_name": recipient,
        "company": company,
        "segment": clean_text(contact.get("segment")),
        "lead_score": None,
        "recommended_action": recommended_action,
        "priority_reason": priority_reason,
        "subject_line": subject,
        "message_body": body,
        "source": clean_text(contact.get("source")),
    }


def lead_target(lead: dict) -> dict:
    company = clean_text(lead.get("company_name")) or "Company"
    recommended_action = (
        clean_text(lead.get("recommended_offer"))
        or clean_text(lead.get("next_action"))
        or "Review lead context and prepare a short manual outreach note."
    )
    priority_reason = clean_text(lead.get("priority_reason")) or "Lead was approved for pursuit."
    lead_id = str(lead["_id"])
    score = lead.get("lead_score") or lead.get("score")

    if module_from_lead(lead) == "contractor_growth":
        subject = f"Quick lead follow-up idea for {company}"
        body = (
            f"Hi there,\n\n"
            f"I am reviewing local contractor lead follow-up workflows and noticed {company} could be a fit for a short audit.\n\n"
            "Most contractors lose opportunities when website requests, missed calls, or quote follow-ups are not handled quickly.\n\n"
            f"Suggested next step: {recommended_action}\n\n"
            "I can outline a simple follow-up system to help turn more requests into booked estimates. Worth sending over a quick example?\n\n"
            "Best,\n"
            "SignalForge operator"
        )
    else:
        subject = f"Quick idea for {company}"
        body = (
            f"Hi there,\n\n"
            f"I was reviewing {company} and noticed a possible opportunity that may be worth a short conversation.\n\n"
            f"Reason for review: {priority_reason}\n\n"
            f"Suggested next step: {recommended_action}\n\n"
            "If this is useful, I would personalize this draft against the company note before sending anything manually.\n\n"
            "Best,\n"
            "SignalForge operator"
        )

    return {
        "target_type": "lead",
        "target_id": lead_id,
        "target_key": clean_text(lead.get("company_slug")) or lead_id,
        "recipient_name": company,
        "company": company,
        "segment": "",
        "lead_score": score,
        "recommended_action": recommended_action,
        "priority_reason": priority_reason,
        "subject_line": subject,
        "message_body": clean_text(lead.get("outreach_draft")) or body,
        "source": clean_text(lead.get("source")),
    }


def module_from_lead(lead: dict) -> str:
    module = clean_text(lead.get("module"))
    if module:
        return module
    engine = clean_text(lead.get("engine")).lower()
    business_type = clean_text(lead.get("business_type")).lower()
    if "contractor" in engine or "contractor" in business_type:
        return "contractor_growth"
    return ""


def draft_key(module: str, target: dict) -> str:
    return slugify(f"{module}-{target['target_type']}-{target['target_key']}")


def note_path_for(module: str, target: dict) -> str:
    return f"messages/{draft_key(module, target)}.md"


def build_note(module: str, target: dict, draft: dict) -> str:
    score_or_segment = target.get("segment") or target.get("lead_score") or "-"
    return f"""---
type: message_draft
module: {module}
target_type: {target["target_type"]}
review_status: {MESSAGE_REVIEW_STATUSES[0]}
send_status: {SEND_STATUSES[0]}
created_at: {draft["created_at"].isoformat()}
---

# Message Draft: {target["recipient_name"]}

## Review State

| Field | Value |
| --- | --- |
| Recipient | {table_safe(target["recipient_name"])} |
| Module | `{module}` |
| Target type | `{target["target_type"]}` |
| Segment or lead score | {table_safe(score_or_segment)} |
| Recommended action | {table_safe(target["recommended_action"])} |
| Review status | `{MESSAGE_REVIEW_STATUSES[0]}` |
| Send status | `{SEND_STATUSES[0]}` |
| Created at | {draft["created_at"].isoformat()} |

## Subject Line

{target["subject_line"]}

## Message Body

{target["message_body"]}

## Human Review Checklist

- [ ] Verify recipient and company context.
- [ ] Edit for accuracy and tone.
- [ ] Remove anything that feels assumed or unsupported.
- [ ] Choose channel manually if approved.
- [ ] Update status after any human action.

## Safety

- No message has been sent.
- No external API was called.
- This draft is editable and requires human approval.
"""


def upsert_draft(db, module: str, target: dict, vault_path: Path, generated_at: datetime) -> tuple[dict, bool]:
    key = draft_key(module, target)
    relative_note_path = note_path_for(module, target)
    existing = db.message_drafts.find_one({"draft_key": key}, {"created_at": 1})
    created_at = existing.get("created_at") if existing and existing.get("created_at") else generated_at

    draft = {
        "draft_key": key,
        "module": module,
        "target_type": target["target_type"],
        "target_id": target["target_id"],
        "target_key": target["target_key"],
        "recipient_name": target["recipient_name"],
        "company": target["company"],
        "segment": target.get("segment"),
        "lead_score": target.get("lead_score"),
        "recommended_action": target["recommended_action"],
        "priority_reason": target["priority_reason"],
        "subject_line": target["subject_line"],
        "message_body": target["message_body"],
        "review_status": MESSAGE_REVIEW_STATUSES[0],
        "send_status": SEND_STATUSES[0],
        "source": target.get("source"),
        "message_note_path": relative_note_path,
        "created_at": created_at,
        "updated_at": generated_at,
    }

    note_path = vault_path / relative_note_path
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(build_note(module, target, draft), encoding="utf-8")

    result = db.message_drafts.update_one(
        {"draft_key": key},
        {
            "$set": draft,
            "$setOnInsert": {"first_created_at": created_at},
        },
        upsert=True,
    )
    return draft, bool(result.upserted_id)


def select_targets(contacts: list[dict], leads: list[dict], module: str, limit: int) -> list[dict]:
    targets = [contact_target(contact) for contact in contacts]
    targets.extend(lead_target(lead) for lead in leads)
    return targets[:limit]


def main() -> None:
    args = parse_args()
    generated_at = utc_now()
    vault_path = Path(args.vault)
    limit = max(1, args.limit)

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
        db = get_database(client)
        contacts = fetch_contacts(db, args.module, limit)
        leads = fetch_leads(db, args.module, limit)
        targets = select_targets(contacts, leads, args.module, limit)

        inserted = 0
        updated = 0
        drafts = []
        for target in targets:
            draft, was_inserted = upsert_draft(db, args.module, target, vault_path, generated_at)
            drafts.append(draft)
            if was_inserted:
                inserted += 1
            else:
                updated += 1
    finally:
        client.close()

    print(f"Module: {args.module}")
    print(f"Targets found: {len(targets)}")
    print(f"Drafts inserted: {inserted}")
    print(f"Drafts updated: {updated}")
    for draft in drafts:
        print(f"- {draft['recipient_name']}: {vault_path / draft['message_note_path']}")
    print("No messages sent. No external APIs called.")


if __name__ == "__main__":
    main()
