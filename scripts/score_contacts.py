import argparse
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymongo import MongoClient

from core.constants import CONTACT_SEGMENTS, VALID_MODULES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_PATH = PROJECT_ROOT / "vault"
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"
SUPPORTED_MODULES = VALID_MODULES
SEGMENTS = CONTACT_SEGMENTS

MODULE_KEYWORDS = {
    "contractor_growth": ("contractor", "roof", "hvac", "plumb", "remodel", "local service", "quote"),
    "insurance_growth": ("insurance", "risk", "agency", "agent", "benefits", "quote", "commercial lines"),
    "artist_growth": ("artist", "music", "fan", "release", "show", "venue", "stream"),
    "media_growth": ("media", "newsletter", "podcast", "creator", "editor", "publication", "sponsor"),
}

TRUSTED_SOURCE_HINTS = ("client", "provided", "referral", "crm", "warm", "event", "manual")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score and segment imported SignalForge contacts.")
    parser.add_argument("--module", required=True, choices=SUPPORTED_MODULES, help="SignalForge module name.")
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


def has_value(contact: dict, field: str) -> bool:
    return bool(clean_text(contact.get(field)))


def source_is_trusted(source: str) -> bool:
    normalized = source.lower()
    return any(hint in normalized for hint in TRUSTED_SOURCE_HINTS)


def module_relevance_score(contact: dict, module: str) -> tuple[int, str]:
    haystack = " ".join(
        clean_text(contact.get(field)).lower()
        for field in ("company", "role", "notes", "source")
    )
    matched = [keyword for keyword in MODULE_KEYWORDS[module] if keyword in haystack]
    if matched:
        return 15, f"module keywords matched: {', '.join(matched[:3])}"
    return 8, "module assignment present, but no explicit module keywords found"


def score_contact(contact: dict, module: str, scored_at: datetime) -> dict:
    score = 10
    reasons = ["base imported contact score"]

    if has_value(contact, "email"):
        score += 20
        reasons.append("has email")
    if has_value(contact, "phone"):
        score += 15
        reasons.append("has phone")
    if has_value(contact, "company"):
        score += 15
        reasons.append("has company")
    if has_value(contact, "role"):
        score += 15
        reasons.append("has role")
    if has_value(contact, "notes"):
        score += 10
        reasons.append("has notes")

    source = clean_text(contact.get("source"))
    if source_is_trusted(source):
        score += 10
        reasons.append(f"trusted source label: {source}")
    elif source:
        score += 5
        reasons.append(f"source label present: {source}")

    relevance_points, relevance_reason = module_relevance_score(contact, module)
    score += relevance_points
    reasons.append(relevance_reason)

    score = max(1, min(100, score))
    segment = segment_for_score(score, contact)

    return {
        "contact_score": score,
        "segment": segment,
        "priority_reason": build_priority_reason(score, segment, reasons),
        "recommended_action": recommended_action_for(segment),
        "scored_at": scored_at,
        "updated_at": scored_at,
    }


def segment_for_score(score: int, contact: dict) -> str:
    if score >= 80:
        return "high_priority"
    if score >= 55:
        return "nurture"
    if score >= 35:
        return "research_more"
    return "low_priority"


def recommended_action_for(segment: str) -> str:
    if segment == "high_priority":
        return "Review first and prepare a human-approved outreach or engagement plan."
    if segment == "nurture":
        return "Add to a light nurture list and use for content or future campaign planning."
    if segment == "research_more":
        return "Research missing context before deciding whether to pursue."
    return "Keep on file; do not prioritize unless new context appears."


def build_priority_reason(score: int, segment: str, reasons: list[str]) -> str:
    return f"Score {score} / segment {segment}: " + "; ".join(reasons)


def score_contacts(db, module: str, scored_at: datetime) -> list[dict]:
    contacts = list(db.contacts.find({"module": module}))
    scored_contacts = []

    for contact in contacts:
        scoring = score_contact(contact, module, scored_at)
        db.contacts.update_one({"_id": contact["_id"]}, {"$set": scoring})
        scored_contacts.append({**contact, **scoring})

    return sort_contacts(scored_contacts)


def sort_contacts(contacts: list[dict]) -> list[dict]:
    segment_rank = {
        "high_priority": 0,
        "nurture": 1,
        "research_more": 2,
        "low_priority": 3,
    }
    return sorted(
        contacts,
        key=lambda contact: (
            segment_rank.get(contact.get("segment"), 99),
            -(contact.get("contact_score") or 0),
            clean_text(contact.get("company")).lower(),
            clean_text(contact.get("name")).lower(),
        ),
    )


def table_text(value: Any) -> str:
    text = clean_text(value) or "-"
    return text.replace("|", "\\|").replace("\n", " ")


def write_report(vault_path: Path, module: str, contacts: list[dict], scored_at: datetime) -> Path:
    contacts_dir = vault_path / "contacts"
    contacts_dir.mkdir(parents=True, exist_ok=True)
    timestamp = scored_at.strftime("%Y%m%dT%H%M%SZ")
    report_path = contacts_dir / f"contact_segmentation_{module}_{timestamp}.md"

    counts = Counter(contact.get("segment", "unscored") for contact in contacts)
    score_values = [contact.get("contact_score") for contact in contacts if isinstance(contact.get("contact_score"), int)]
    average_score = round(sum(score_values) / len(score_values), 1) if score_values else 0

    segment_rows = ["| Segment | Count |", "| --- | ---: |"]
    for segment in SEGMENTS:
        segment_rows.append(f"| `{segment}` | {counts.get(segment, 0)} |")

    contact_rows = [
        "| Score | Segment | Name | Company | Role | Source | Recommended Action |",
        "| ---: | --- | --- | --- | --- | --- | --- |",
    ]
    for contact in contacts:
        contact_rows.append(
            "| "
            f"{contact.get('contact_score', '-')} | "
            f"`{table_text(contact.get('segment'))}` | "
            f"{table_text(contact.get('name'))} | "
            f"{table_text(contact.get('company'))} | "
            f"{table_text(contact.get('role'))} | "
            f"{table_text(contact.get('source'))} | "
            f"{table_text(contact.get('recommended_action'))} |"
        )

    if len(contact_rows) == 2:
        contact_rows.append("| - | No contacts found | - | - | - | - | - |")

    content = f"""---
type: contact_segmentation
module: {module}
scored_at: {scored_at.isoformat()}
---

# Contact Segmentation: {module}

## Summary

| Metric | Value |
| --- | ---: |
| Contacts scored | {len(contacts)} |
| Average contact score | {average_score} |

## Segment Counts

{chr(10).join(segment_rows)}

## Scoring Rules

- Has email: +20
- Has phone: +15
- Has company: +15
- Has role: +15
- Has notes: +10
- Trusted source label: +10
- Other source label: +5
- Module relevance: +8 to +15
- Score is capped between 1 and 100.

## Segments

- `high_priority`: 80-100
- `nurture`: 55-79
- `research_more`: 35-54
- `low_priority`: 1-34

## Contacts

{chr(10).join(contact_rows)}

## Safety

- No messages sent.
- No external enrichment performed.
- This report is for human review and simulation-agent planning only.
"""
    report_path.write_text(content, encoding="utf-8")
    return report_path


def main() -> None:
    args = parse_args()
    scored_at = utc_now()
    vault_path = Path(args.vault)

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
        db = get_database(client)
        contacts = score_contacts(db, args.module, scored_at)
        report_path = write_report(vault_path, args.module, contacts, scored_at)
    finally:
        client.close()

    print(f"Contacts scored: {len(contacts)}")
    print(f"Segmentation report: {report_path}")
    print("No messages sent. No external enrichment performed.")


if __name__ == "__main__":
    main()
