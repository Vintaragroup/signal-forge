import argparse
import csv
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymongo import MongoClient

from core.constants import VALID_MODULES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_PATH = PROJECT_ROOT / "vault"
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"
SUPPORTED_MODULES = VALID_MODULES
EXPECTED_FIELDS = (
    "name",
    "email",
    "phone",
    "company",
    "role",
    "city",
    "state",
    "notes",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a provided contact CSV into SignalForge.")
    parser.add_argument("csv_path", help="Path to the contact CSV file.")
    parser.add_argument("--module", required=True, choices=SUPPORTED_MODULES, help="SignalForge module name.")
    parser.add_argument("--source", default="csv_import", help="Optional source label for the import.")
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
    return slug or "contact"


def normalize_row(row: dict[str, Any], module: str, source: str, imported_at: datetime, row_number: int) -> dict:
    normalized = {field: clean_text(row.get(field, "")) for field in EXPECTED_FIELDS}
    normalized["email"] = normalized["email"].lower()
    normalized["state"] = normalized["state"].upper()

    identity = normalized["email"] or "|".join(
        [
            normalized["name"],
            normalized["company"],
            normalized["phone"],
            normalized["city"],
            normalized["state"],
            str(row_number),
        ]
    )

    contact_key = slugify(f"{module}-{identity}")
    return {
        **normalized,
        "module": module,
        "source": source,
        "contact_status": "imported",
        "contact_key": contact_key,
        "imported_at": imported_at,
        "updated_at": imported_at,
    }


def is_empty_contact(row: dict[str, Any]) -> bool:
    return not any(clean_text(row.get(field, "")) for field in EXPECTED_FIELDS)


def load_contacts(csv_path: Path, module: str, source: str, imported_at: datetime) -> list[dict]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV file has no header row.")

        fields = {field.strip().lower() for field in reader.fieldnames}
        missing = [field for field in EXPECTED_FIELDS if field not in fields]
        if missing:
            raise ValueError(f"CSV is missing required fields: {', '.join(missing)}")

        contacts = []
        for row_number, row in enumerate(reader, start=2):
            normalized_row = {clean_text(key).lower(): value for key, value in row.items()}
            if is_empty_contact(normalized_row):
                continue
            contacts.append(normalize_row(normalized_row, module, source, imported_at, row_number))

    return contacts


def upsert_contacts(db, contacts: list[dict]) -> tuple[int, int]:
    inserted = 0
    updated = 0

    for contact in contacts:
        result = db.contacts.update_one(
            {"module": contact["module"], "contact_key": contact["contact_key"]},
            {
                "$set": contact,
                "$setOnInsert": {"created_at": contact["imported_at"]},
            },
            upsert=True,
        )
        if result.upserted_id:
            inserted += 1
        else:
            updated += result.modified_count

    return inserted, updated


def table_text(value: Any) -> str:
    text = clean_text(value) or "-"
    return text.replace("|", "\\|").replace("\n", " ")


def write_summary_note(
    vault_path: Path,
    csv_path: Path,
    module: str,
    source: str,
    contacts: list[dict],
    inserted: int,
    updated: int,
    imported_at: datetime,
) -> Path:
    contacts_dir = vault_path / "contacts"
    contacts_dir.mkdir(parents=True, exist_ok=True)
    timestamp = imported_at.strftime("%Y%m%dT%H%M%SZ")
    note_path = contacts_dir / f"contact_import_{module}_{timestamp}.md"

    rows = [
        "| Name | Email | Phone | Company | Role | Location | Status |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for contact in contacts[:50]:
        location = ", ".join(part for part in [contact.get("city"), contact.get("state")] if part)
        rows.append(
            "| "
            f"{table_text(contact.get('name'))} | "
            f"{table_text(contact.get('email'))} | "
            f"{table_text(contact.get('phone'))} | "
            f"{table_text(contact.get('company'))} | "
            f"{table_text(contact.get('role'))} | "
            f"{table_text(location)} | "
            f"{table_text(contact.get('contact_status'))} |"
        )

    if len(rows) == 2:
        rows.append("| No contacts imported | - | - | - | - | - | - |")

    content = f"""---
type: contact_import
module: {module}
source: {source}
imported_at: {imported_at.isoformat()}
---

# Contact Import: {module}

## Summary

| Metric | Value |
| --- | ---: |
| Contacts read | {len(contacts)} |
| Inserted | {inserted} |
| Updated | {updated} |

## Source

- CSV: `{csv_path}`
- Module: `{module}`
- Source label: `{source}`
- Contact status: `imported`
- External enrichment: none
- Outbound messages sent: none

## Imported Contacts

{chr(10).join(rows)}
"""
    note_path.write_text(content, encoding="utf-8")
    return note_path


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv_path)
    vault_path = Path(args.vault)
    imported_at = utc_now()

    contacts = load_contacts(csv_path, args.module, args.source, imported_at)

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
        db = get_database(client)
        inserted, updated = upsert_contacts(db, contacts)
        note_path = write_summary_note(
            vault_path=vault_path,
            csv_path=csv_path,
            module=args.module,
            source=args.source,
            contacts=contacts,
            inserted=inserted,
            updated=updated,
            imported_at=imported_at,
        )
    finally:
        client.close()

    print(f"Contacts read: {len(contacts)}")
    print(f"Inserted: {inserted}")
    print(f"Updated: {updated}")
    print(f"Import summary: {note_path}")
    print("No messages sent. No external enrichment performed.")


if __name__ == "__main__":
    main()
