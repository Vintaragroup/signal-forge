import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient

from core.constants import LEAD_REVIEW_DECISIONS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_PATH = PROJECT_ROOT / "vault"
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"
VALID_DECISIONS = LEAD_REVIEW_DECISIONS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review a signalForge lead and prepare outreach if approved.")
    parser.add_argument("lead", help="Lead ObjectId, company slug, lead note slug, or review queue note slug")
    parser.add_argument("decision", choices=VALID_DECISIONS, help="Review decision")
    parser.add_argument("--note", default="", help="Optional human note to append to the decision log")
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
        {"note_path": {"$regex": escaped_slug}},
        {"review_queue_path": {"$regex": escaped_slug}},
    ]

    if is_object_id(raw):
        conditions.insert(0, {"_id": ObjectId(raw)})

    matches = list(db.leads.find({"$or": conditions}).sort("updated_at", -1).limit(5))
    if not matches:
        raise SystemExit(f"No lead found for identifier: {identifier}")

    if len(matches) > 1:
        print(f"Multiple leads matched {identifier!r}; using most recently updated record.")

    return matches[0]


def vault_file(vault_path: Path, relative_path: str) -> Path:
    if not relative_path:
        raise SystemExit("Lead record is missing a vault note path.")
    return vault_path / relative_path


def append_decision_log(path: Path, lead: dict, decision: str, note: str, outreach_path: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now().isoformat()
    note_line = f"- Note: {note}\n" if note else ""
    outreach_line = f"- Outreach note: {outreach_path}\n" if outreach_path else ""
    entry = f"""

## Decision Log

### {timestamp}

- Decision: {decision}
- Review status: {decision}
- Lead ID: {lead["_id"]}
- Company: {lead.get("company_name", "")}
{note_line}{outreach_line}"""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(entry)


def outreach_note_path(lead: dict) -> str:
    return f"outreach/{slugify(lead['run_id'])}-{lead['company_slug']}.md"


def build_outreach_note(lead: dict, decision_note: str) -> str:
    created = utc_now().date().isoformat()
    priority_reason = lead.get("priority_reason") or lead.get("insights", {}).get("priority_reason", "")
    recommended_offer = lead.get("recommended_offer") or lead.get("insights", {}).get("recommended_offer", "")
    next_action = lead.get("next_action") or lead.get("insights", {}).get("next_action", "")
    lead_score = lead.get("lead_score") or lead.get("score", "")

    return f"""---
type: outreach
status: ready_for_human_review
review_status: pursue
run_id: {yaml_quote(lead.get("run_id", ""))}
company: {yaml_quote(lead.get("company_name", ""))}
lead_score: {lead_score}
source: {lead.get("source", "")}
created: {created}
---

# Outreach: {lead.get("company_name", "")}

## Company

{lead.get("company_name", "")}

## Lead Score

{lead_score}/100

## Priority Reason

{priority_reason}

## Recommended Offer

{recommended_offer}

## Outreach Draft

{lead.get("outreach_draft", "")}

## Next Action

{next_action}

## Follow-Up Checklist

- [ ] Verify company website and local fit.
- [ ] Confirm the offer is relevant.
- [ ] Edit outreach for tone and accuracy.
- [ ] Decide send channel.
- [ ] Log any reply or next step.

## Decision Note

{decision_note or "No additional note provided."}
"""


def create_outreach_note(vault_path: Path, lead: dict, decision_note: str) -> str:
    relative_path = outreach_note_path(lead)
    path = vault_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_outreach_note(lead, decision_note), encoding="utf-8")
    return relative_path


def update_mongo(db, lead: dict, decision: str, note: str, outreach_path: str | None) -> None:
    now = utc_now()
    update = {
        "review_status": decision,
        "reviewed_at": now,
        "review_decision_note": note,
        "updated_at": now,
    }
    if outreach_path:
        update["outreach_note_path"] = outreach_path

    db.leads.update_one({"_id": lead["_id"]}, {"$set": update})
    db.companies.update_one(
        {"run_id": lead.get("run_id"), "company_slug": lead.get("company_slug")},
        {"$set": update},
    )


def main() -> None:
    args = parse_args()
    vault_path = Path(args.vault)
    vault_path.mkdir(parents=True, exist_ok=True)
    (vault_path / "outreach").mkdir(parents=True, exist_ok=True)

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
        db = get_database(client)
        lead = find_lead(db, args.lead)

        outreach_path = None
        if args.decision == "pursue":
            outreach_path = create_outreach_note(vault_path, lead, args.note)

        update_mongo(db, lead, args.decision, args.note, outreach_path)

        lead_note = vault_file(vault_path, lead.get("note_path", ""))
        review_note = vault_file(vault_path, lead.get("review_queue_path", ""))
        append_decision_log(lead_note, lead, args.decision, args.note, outreach_path)
        append_decision_log(review_note, lead, args.decision, args.note, outreach_path)

        print(f"Reviewed lead: {lead.get('company_name')}")
        print(f"Decision: {args.decision}")
        print(f"Lead note updated: {lead_note}")
        print(f"Review note updated: {review_note}")
        if outreach_path:
            print(f"Outreach note created: {vault_path / outreach_path}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
