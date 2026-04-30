import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient


SERVICE_NAME = "lead_scraper"
SERVICE_DESCRIPTION = "Contractor Lead Engine v2 structured contractor listing importer."
ENGINE_NAME = "contractor_lead_engine_v2"
SOURCE_NAME = "google_search_v1"
SOURCE_MODE = "local_structured_dataset"
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"
DEFAULT_DATA_FILE = "/data/raw/contractor_listings_seed.json"

FALLBACK_LISTINGS = [
    {
        "business_name": "Austin Roof Works",
        "business_type": "roofing contractor",
        "city": "Austin",
        "state": "TX",
        "website": "https://austinroofworks.example",
        "source_rank": 1,
    },
    {
        "business_name": "Capital City Roofing Co",
        "business_type": "roofing contractor",
        "city": "Austin",
        "state": "TX",
        "website": "https://capitalcityroofing.example",
        "source_rank": 2,
    },
    {
        "business_name": "Hill Country Roof Pros",
        "business_type": "roofing contractor",
        "city": "Austin",
        "state": "TX",
        "website": "",
        "source_rank": 3,
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=SERVICE_DESCRIPTION)
    parser.add_argument(
        "--business-type",
        default=os.getenv("BUSINESS_TYPE", "roofing contractor"),
        help="Business type to import from the structured listing dataset.",
    )
    parser.add_argument(
        "--location",
        default=os.getenv("LOCATION", "Austin, TX"),
        help="City/state location to import, for example 'Austin, TX'.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=int(os.getenv("LEAD_COUNT", "5")),
        help="Maximum number of listings to import.",
    )
    parser.add_argument(
        "--run-id",
        default=os.getenv("PIPELINE_RUN_ID"),
        help="Optional pipeline run id. Defaults to current UTC timestamp.",
    )
    parser.add_argument(
        "--data-file",
        default=os.getenv("LEAD_SOURCE_FILE", DEFAULT_DATA_FILE),
        help="Path to a JSON contractor listing dataset mounted in the container.",
    )
    args = parser.parse_args()

    if args.count < 1:
        raise SystemExit("--count must be at least 1")

    return args


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def make_run_id(value: str | None) -> str:
    if value:
        return value
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


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


def get_vault_path() -> Path:
    return Path(os.getenv("VAULT_PATH", "/vault"))


def ensure_vault(vault_path: Path) -> None:
    for folder in ("leads", "companies", "logs"):
        (vault_path / folder).mkdir(parents=True, exist_ok=True)


def parse_location(location: str) -> tuple[str, str]:
    parts = [part.strip() for part in location.split(",")]
    city = parts[0] if parts else location.strip()
    state = parts[1] if len(parts) > 1 else ""
    return city, state.upper()


def load_listings(path: str) -> list[dict]:
    data_path = Path(path)
    if not data_path.exists():
        print(f"Dataset not found at {data_path}. Using built-in fallback listings.")
        return FALLBACK_LISTINGS

    with data_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, dict):
        listings = payload.get("listings", [])
    else:
        listings = payload

    if not isinstance(listings, list):
        raise ValueError("Contractor listing dataset must be a list or an object with a 'listings' list.")

    return listings


def clean_listing(raw: dict) -> dict:
    return {
        "business_name": str(raw.get("business_name", "")).strip(),
        "business_type": str(raw.get("business_type", "")).strip().lower(),
        "city": str(raw.get("city", "")).strip(),
        "state": str(raw.get("state", "")).strip().upper(),
        "website": str(raw.get("website", "")).strip(),
        "source_url": str(raw.get("source_url", "")).strip(),
        "source_rank": int(raw.get("source_rank", 999)),
    }


def listing_matches(listing: dict, business_type: str, city: str, state: str) -> bool:
    listing_type = listing["business_type"].lower()
    requested_type = business_type.strip().lower()
    city_matches = listing["city"].lower() == city.lower()
    state_matches = not state or listing["state"].upper() == state.upper()
    type_matches = requested_type in listing_type or listing_type in requested_type
    return city_matches and state_matches and type_matches


def select_listings(listings: list[dict], business_type: str, location: str, count: int) -> list[dict]:
    city, state = parse_location(location)
    cleaned = [clean_listing(item) for item in listings]
    matched = [
        item
        for item in cleaned
        if item["business_name"] and listing_matches(item, business_type, city, state)
    ]
    matched.sort(key=lambda item: item["source_rank"])
    return matched[:count]


def source_query(business_type: str, location: str) -> str:
    return f"{business_type} {location}".strip()


def build_signal(listing: dict, business_type: str, location: str) -> str:
    rank = listing.get("source_rank", 999)
    website_note = "with a website" if listing.get("website") else "without a website listed"
    return (
        f"Appears as result {rank} in the structured {business_type} listing set "
        f"for {location}, {website_note}."
    )


def signal_strength(listing: dict) -> int:
    rank = int(listing.get("source_rank", 999))
    if rank <= 2:
        base = 5
    elif rank <= 5:
        base = 4
    else:
        base = 3
    if not listing.get("website"):
        base -= 1
    return max(1, min(base, 5))


def normalize_leads(
    listings: list[dict],
    business_type: str,
    location: str,
    run_id: str,
) -> list[dict]:
    leads = []
    safe_run_id = slugify(run_id)
    query = source_query(business_type, location)

    for listing in listings:
        now = utc_now()
        company_name = listing["business_name"]
        company_slug = slugify(company_name)
        lead_file = f"{safe_run_id}-{company_slug}.md"
        company_file = f"{safe_run_id}-{company_slug}.md"
        normalized_location = f"{listing['city']}, {listing['state']}".strip().strip(",")

        leads.append(
            {
                "engine": ENGINE_NAME,
                "source": SOURCE_NAME,
                "source_mode": SOURCE_MODE,
                "source_query": query,
                "source_url": listing.get("source_url", ""),
                "source_rank": listing.get("source_rank", 999),
                "status": "sourced",
                "run_id": run_id,
                "business_type": business_type,
                "location": normalized_location or location,
                "company_name": company_name,
                "company_slug": company_slug,
                "website": listing.get("website", ""),
                "contact_name": "",
                "contact_title": "Owner/Operator",
                "email": "",
                "phone": "",
                "signal": build_signal(listing, business_type, location),
                "signal_strength": signal_strength(listing),
                "score": None,
                "outreach_draft": "",
                "note_path": f"leads/{lead_file}",
                "company_note_path": f"companies/{company_file}",
                "created_at": now,
                "updated_at": now,
            }
        )

    return leads


def display(value: str, fallback: str = "Not available") -> str:
    return value if value else fallback


def build_lead_note(lead: dict) -> str:
    created = lead["created_at"].date().isoformat()
    return f"""---
type: lead
status: sourced
engine: {ENGINE_NAME}
run_id: {yaml_quote(lead["run_id"])}
business_type: {yaml_quote(lead["business_type"])}
location: {yaml_quote(lead["location"])}
company: {yaml_quote(lead["company_name"])}
contact: {yaml_quote(lead["contact_name"])}
score:
source: {lead["source"]}
created: {created}
---

# Lead: {lead["company_name"]}

## Summary

Structured contractor listing imported for {lead["business_type"]} in {lead["location"]}.

## Source

- Source: {lead["source"]}
- Source mode: {lead["source_mode"]}
- Source query: {lead["source_query"]}
- Source rank: {lead["source_rank"]}
- Source URL: {display(lead["source_url"])}
- Run ID: {lead["run_id"]}
- Imported at: {lead["created_at"].isoformat()}

## Company

- Name: {lead["company_name"]}
- Website: {display(lead["website"])}
- Location: {lead["location"]}

## Contact

- Name: Not available
- Role: {lead["contact_title"]}
- Email: Not available
- Phone: Not available

## Signal

- {lead["signal"]}

## Lead Score

Pending enrichment.

## Outreach Draft

Pending enrichment.

## Next Action

- Run lead enrichment and review the generated outreach draft.
"""


def build_company_note(lead: dict) -> str:
    created = lead["created_at"].date().isoformat()
    lead_link = f"../{lead['note_path']}"
    return f"""---
type: company
status: sourced
engine: {ENGINE_NAME}
run_id: {yaml_quote(lead["run_id"])}
company: {yaml_quote(lead["company_name"])}
business_type: {yaml_quote(lead["business_type"])}
location: {yaml_quote(lead["location"])}
source: {lead["source"]}
created: {created}
---

# Company: {lead["company_name"]}

## Summary

Structured company profile imported from the contractor listing source.

## Firmographics

- Website: {display(lead["website"])}
- Location: {lead["location"]}
- Business type: {lead["business_type"]}
- Source: {lead["source"]}
- Source rank: {lead["source_rank"]}

## Signal

- {lead["signal"]}

## Associated Lead

- [{lead["company_name"]}]({lead_link})

## Value Hypothesis

- This contractor may benefit from faster local lead follow-up and clearer campaign tracking.

## Next Action

- Review the lead score and outreach draft after enrichment.
"""


def write_notes(vault_path: Path, leads: list[dict]) -> None:
    for lead in leads:
        lead_path = vault_path / lead["note_path"]
        company_path = vault_path / lead["company_note_path"]
        lead_path.write_text(build_lead_note(lead), encoding="utf-8")
        company_path.write_text(build_company_note(lead), encoding="utf-8")


def persist_records(db, leads: list[dict], run_id: str, business_type: str, location: str) -> None:
    db.leads.create_index([("run_id", 1), ("company_slug", 1)], unique=True)
    db.companies.create_index([("run_id", 1), ("company_slug", 1)], unique=True)

    for lead in leads:
        db.leads.replace_one(
            {"run_id": run_id, "company_slug": lead["company_slug"]},
            lead,
            upsert=True,
        )
        db.companies.replace_one(
            {"run_id": run_id, "company_slug": lead["company_slug"]},
            {
                "engine": ENGINE_NAME,
                "source": lead["source"],
                "source_mode": lead["source_mode"],
                "source_query": lead["source_query"],
                "source_url": lead["source_url"],
                "source_rank": lead["source_rank"],
                "status": "sourced",
                "run_id": run_id,
                "business_type": business_type,
                "location": lead["location"],
                "company_name": lead["company_name"],
                "company_slug": lead["company_slug"],
                "website": lead["website"],
                "signal": lead["signal"],
                "lead_note_path": lead["note_path"],
                "company_note_path": lead["company_note_path"],
                "created_at": lead["created_at"],
                "updated_at": lead["updated_at"],
            },
            upsert=True,
        )

    db.pipeline_runs.update_one(
        {"run_id": run_id},
        {
            "$setOnInsert": {"created_at": utc_now()},
            "$set": {
                "engine": ENGINE_NAME,
                "source": SOURCE_NAME,
                "source_mode": SOURCE_MODE,
                "status": "leads_sourced",
                "business_type": business_type,
                "location": location,
                "lead_count": len(leads),
                "updated_at": utc_now(),
            },
        },
        upsert=True,
    )


def main() -> None:
    args = parse_args()
    run_id = make_run_id(args.run_id)
    vault_path = get_vault_path()

    print(f"signalForge service: {SERVICE_NAME}")
    print(SERVICE_DESCRIPTION)
    print(f"Started at: {iso_now()}")
    print(f"Environment: {os.getenv('SIGNALFORGE_ENV', 'local')}")
    print(f"Run ID: {run_id}")
    print(f"Business type: {args.business_type}")
    print(f"Location: {args.location}")
    print(f"Lead count: {args.count}")
    print(f"Source: {SOURCE_NAME} ({SOURCE_MODE})")
    print(f"Dataset: {args.data_file}")

    ensure_vault(vault_path)
    print(f"Vault path: {vault_path} | exists={vault_path.exists()}")

    listings = load_listings(args.data_file)
    selected = select_listings(listings, args.business_type, args.location, args.count)
    if not selected:
        raise SystemExit(
            f"No listings matched business_type={args.business_type!r} and location={args.location!r}."
        )

    client = MongoClient(os.getenv("MONGO_URI", DEFAULT_MONGO_URI), serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
        print("MongoDB: ready")
        db = get_database(client)
        leads = normalize_leads(selected, args.business_type, args.location, run_id)
        persist_records(db, leads, run_id, args.business_type, args.location)
        write_notes(vault_path, leads)
        print(f"Imported {len(leads)} structured leads into MongoDB and the vault.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
