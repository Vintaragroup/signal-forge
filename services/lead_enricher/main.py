import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient


SERVICE_NAME = "lead_enricher"
SERVICE_DESCRIPTION = "Contractor Lead Engine v3 lead intelligence and outreach generator."
ENGINE_NAME = "contractor_lead_engine_v3"
INPUT_ENGINES = ["contractor_lead_engine_v2", ENGINE_NAME]
SOURCE_NAME = "google_search_v1"
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"
DEFAULT_REVIEW_STATUS = "needs_review"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=SERVICE_DESCRIPTION)
    parser.add_argument(
        "--run-id",
        default=os.getenv("PIPELINE_RUN_ID"),
        help="Pipeline run id to enrich. If omitted, enriches unreviewed v2/v3 leads.",
    )
    parser.add_argument(
        "--business-type",
        default=os.getenv("BUSINESS_TYPE"),
        help="Optional business type filter.",
    )
    parser.add_argument(
        "--location",
        default=os.getenv("LOCATION"),
        help="Optional location filter.",
    )
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


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


def display(value: str, fallback: str = "Not available") -> str:
    return value if value else fallback


def bool_text(value: bool) -> str:
    return "yes" if value else "no"


def normalize_location(value: str) -> str:
    return value.strip().lower().replace(" ", "")


def category_matches(lead: dict) -> bool:
    business_type = lead.get("business_type", "").lower()
    source_query = lead.get("source_query", "").lower()
    return bool(business_type) and (business_type in source_query or "contractor" in business_type)


def location_matches(lead: dict) -> bool:
    location = normalize_location(lead.get("location", ""))
    source_query = normalize_location(lead.get("source_query", ""))
    return bool(location) and (location in source_query or any(part in source_query for part in location.split(",")))


def website_quality_signal(lead: dict) -> str:
    if not lead.get("website"):
        return "Website missing from source listing; this is a clear local marketing gap."

    rank = int(lead.get("source_rank", 999))
    if rank <= 2:
        return "Website present and listing ranks near the top of the source set."
    if rank <= 5:
        return "Website present, but listing is not in the top local results."
    return "Website present, but source visibility appears weaker."


def marketing_gap(lead: dict) -> str:
    if not lead.get("website"):
        return "No website is attached to the listing, so the business may need a stronger owned web presence."

    rank = int(lead.get("source_rank", 999))
    if rank <= 2:
        return "The business is discoverable; the likely gap is converting local search interest into booked jobs."
    if rank <= 5:
        return "The business appears in local listings but may need stronger follow-up and positioning."
    return "The business has basic web presence but may need better local visibility."


def recommended_offer(lead: dict) -> str:
    if not lead.get("website"):
        return "Contractor local presence starter: simple website, quote request path, and missed-lead follow-up."

    rank = int(lead.get("source_rank", 999))
    if rank <= 2:
        return "Missed-lead follow-up and conversion tracking workflow for local contractor searches."
    return "Local search conversion audit with follow-up workflow and offer cleanup."


def data_quality_signal(lead: dict) -> tuple[int, str]:
    available = [
        bool(lead.get("company_name")),
        bool(lead.get("business_type")),
        bool(lead.get("location")),
        bool(lead.get("source_rank")),
        bool(lead.get("source_url")),
        bool(lead.get("website")),
    ]
    count = sum(available)
    if count >= 5:
        return 15, "Strong listing data: company, category, location, source rank, and web presence are available."
    if count >= 4:
        return 10, "Useful listing data is available, but one key field needs research."
    return 6, "Limited data; research is needed before outreach."


def source_visibility_points(lead: dict) -> tuple[int, str]:
    rank = int(lead.get("source_rank", 999))
    if rank <= 1:
        return 15, "Top-ranked listing in the source set."
    if rank <= 3:
        return 12, "High-visibility listing in the source set."
    if rank <= 5:
        return 8, "Visible in the source set, but not a top listing."
    return 4, "Lower visibility in the source set."


def marketing_opportunity_points(lead: dict) -> tuple[int, str]:
    if not lead.get("website"):
        return 20, "Missing website creates a direct local presence opportunity."

    rank = int(lead.get("source_rank", 999))
    if rank <= 2:
        return 12, "Strong discovery creates an opportunity to improve conversion and follow-up."
    return 10, "Existing web presence creates an opportunity to improve positioning and follow-up."


def build_insights(lead: dict) -> dict:
    website_present = bool(lead.get("website"))
    category_match = category_matches(lead)
    location_match = location_matches(lead)
    data_points, data_reason = data_quality_signal(lead)
    visibility_points, visibility_reason = source_visibility_points(lead)
    opportunity_points, opportunity_reason = marketing_opportunity_points(lead)

    score_breakdown = [
        {
            "factor": "business_category_match",
            "points": 20 if category_match else 5,
            "reason": "Business type matches the requested contractor category."
            if category_match
            else "Business type needs manual confirmation.",
        },
        {
            "factor": "location_match",
            "points": 20 if location_match else 5,
            "reason": "Location matches the requested market."
            if location_match
            else "Location needs manual confirmation.",
        },
        {
            "factor": "website_presence",
            "points": 15 if website_present else 10,
            "reason": "Website is available for review."
            if website_present
            else "Website is missing, which lowers data confidence but creates an opportunity.",
        },
        {
            "factor": "data_quality",
            "points": data_points,
            "reason": data_reason,
        },
        {
            "factor": "source_visibility",
            "points": visibility_points,
            "reason": visibility_reason,
        },
        {
            "factor": "marketing_opportunity",
            "points": opportunity_points,
            "reason": opportunity_reason,
        },
    ]

    lead_score = max(1, min(sum(item["points"] for item in score_breakdown), 100))
    gap = marketing_gap(lead)
    offer = recommended_offer(lead)

    if lead_score >= 85:
        next_action = "Pursue after quick human review of website and local fit."
    elif lead_score >= 70:
        next_action = "Research more, then pursue if the business is active and relevant."
    else:
        next_action = "Research more before outreach; skip if the listing is stale or irrelevant."

    priority_reason = (
        f"{lead.get('company_name')} scored {lead_score}/100 because it matches the requested "
        f"{lead.get('business_type')} category in {lead.get('location')} and shows this opportunity: {gap}"
    )

    return {
        "source": lead.get("source", SOURCE_NAME),
        "business_type": lead.get("business_type", ""),
        "location": lead.get("location", ""),
        "website_present": website_present,
        "website_quality_signal": website_quality_signal(lead),
        "marketing_gap": gap,
        "priority_reason": priority_reason,
        "recommended_offer": offer,
        "lead_score": lead_score,
        "next_action": next_action,
        "review_status": lead.get("review_status", DEFAULT_REVIEW_STATUS),
        "category_match": category_match,
        "location_match": location_match,
        "data_quality_signal": data_reason,
        "score_breakdown": score_breakdown,
    }


def generate_outreach(lead: dict, insights: dict) -> str:
    company = lead["company_name"]
    business_type = lead["business_type"]
    location = lead["location"]
    signal = lead.get("signal", "")
    gap = insights["marketing_gap"].strip().rstrip(".")
    offer = insights["recommended_offer"].strip().rstrip(".")
    gap_fragment = gap[:1].lower() + gap[1:] if gap else "there is a local marketing gap"
    offer_fragment = offer[:1].lower() + offer[1:] if offer else "a simple contractor follow-up workflow"

    return (
        f"Hi, I found {company} while reviewing {business_type} listings in {location}. "
        f"The listing signal was: {signal} The main opportunity I noticed is that {gap_fragment}. "
        f"A useful first step could be {offer_fragment}. Worth a quick look?"
    )


def score_breakdown_markdown(insights: dict) -> str:
    return "\n".join(
        f"- {item['factor']}: +{item['points']} - {item['reason']}"
        for item in insights["score_breakdown"]
    )


def schema_markdown(lead: dict, insights: dict) -> str:
    return f"""| Field | Value |
| --- | --- |
| Source | {lead.get("source", SOURCE_NAME)} |
| Business type | {lead.get("business_type", "")} |
| Location | {lead.get("location", "")} |
| Website present | {bool_text(insights["website_present"])} |
| Website quality signal | {insights["website_quality_signal"]} |
| Marketing gap | {insights["marketing_gap"]} |
| Priority reason | {insights["priority_reason"]} |
| Recommended offer | {insights["recommended_offer"]} |
| Lead score | {insights["lead_score"]}/100 |
| Next action | {insights["next_action"]} |
| Review status | {insights["review_status"]} |"""


def build_lead_note(lead: dict) -> str:
    created = lead["created_at"].date().isoformat()
    updated = lead["updated_at"].date().isoformat()
    insights = lead["insights"]
    return f"""---
type: lead
status: enriched
engine: {ENGINE_NAME}
run_id: {yaml_quote(lead["run_id"])}
business_type: {yaml_quote(lead["business_type"])}
location: {yaml_quote(lead["location"])}
company: {yaml_quote(lead["company_name"])}
contact: {yaml_quote(lead.get("contact_name", ""))}
lead_score: {lead["lead_score"]}
review_status: {lead["review_status"]}
source: {lead["source"]}
created: {created}
updated: {updated}
---

# Lead: {lead["company_name"]}

## Summary

Structured contractor listing enriched by Contractor Lead Engine v3.

## Intelligence Snapshot

{schema_markdown(lead, insights)}

## Source

- Source: {lead["source"]}
- Source mode: {lead.get("source_mode", "unknown")}
- Source query: {lead.get("source_query", "")}
- Source rank: {lead.get("source_rank", "unknown")}
- Source URL: {display(lead.get("source_url", ""))}
- Imported at: {lead["created_at"].isoformat()}
- Enriched at: {lead["updated_at"].isoformat()}

## Company

- Name: {lead["company_name"]}
- Website: {display(lead.get("website", ""))}
- Location: {lead["location"]}

## Signal

- {lead.get("signal", "")}

## Why This Lead Is Valuable

{insights["priority_reason"]}

## Score Breakdown

{score_breakdown_markdown(insights)}

## Outreach Draft

{lead["outreach_draft"]}

## Next Action

- {lead["next_action"]}
"""


def build_company_note(lead: dict) -> str:
    created = lead["created_at"].date().isoformat()
    updated = lead["updated_at"].date().isoformat()
    insights = lead["insights"]
    lead_link = f"../{lead['note_path']}"
    review_link = f"../{lead['review_queue_path']}"
    return f"""---
type: company
status: enriched
engine: {ENGINE_NAME}
run_id: {yaml_quote(lead["run_id"])}
company: {yaml_quote(lead["company_name"])}
business_type: {yaml_quote(lead["business_type"])}
location: {yaml_quote(lead["location"])}
lead_score: {lead["lead_score"]}
review_status: {lead["review_status"]}
source: {lead["source"]}
created: {created}
updated: {updated}
---

# Company: {lead["company_name"]}

## Summary

Structured company profile imported from contractor listing data and enriched for outreach review.

## Firmographics

- Website: {display(lead.get("website", ""))}
- Website present: {bool_text(insights["website_present"])}
- Location: {lead["location"]}
- Business type: {lead["business_type"]}
- Source: {lead["source"]}
- Source rank: {lead.get("source_rank", "unknown")}

## Marketing Intelligence

- Website quality signal: {insights["website_quality_signal"]}
- Marketing gap: {insights["marketing_gap"]}
- Recommended offer: {insights["recommended_offer"]}
- Priority reason: {insights["priority_reason"]}

## Associated Notes

- Lead note: [{lead["company_name"]}]({lead_link})
- Review queue: [{lead["company_name"]}]({review_link})

## Outreach Angle

{lead["outreach_draft"]}

## Next Action

- {lead["next_action"]}
"""


def build_review_queue_note(lead: dict) -> str:
    created = lead["updated_at"].date().isoformat()
    insights = lead["insights"]
    lead_link = f"../{lead['note_path']}"
    company_link = f"../{lead['company_note_path']}"
    return f"""---
type: lead_review
review_status: {lead["review_status"]}
engine: {ENGINE_NAME}
run_id: {yaml_quote(lead["run_id"])}
company: {yaml_quote(lead["company_name"])}
lead_score: {lead["lead_score"]}
source: {lead["source"]}
created: {created}
---

# Review: {lead["company_name"]}

## Decision

- [ ] Pursue
- [ ] Research more
- [ ] Skip

## Lead Snapshot

- Company: {lead["company_name"]}
- Business type: {lead["business_type"]}
- Location: {lead["location"]}
- Website: {display(lead.get("website", ""))}
- Website present: {bool_text(insights["website_present"])}
- Source: {lead["source"]}
- Source rank: {lead.get("source_rank", "unknown")}
- Lead score: {lead["lead_score"]}/100

## Why It May Be Valuable

{insights["priority_reason"]}

## Marketing Gap

{insights["marketing_gap"]}

## Offer To Lead With

{insights["recommended_offer"]}

## Message To Send

{lead["outreach_draft"]}

## Next Action

{lead["next_action"]}

## Score Breakdown

{score_breakdown_markdown(insights)}

## Linked Notes

- Lead: [{lead["company_name"]}]({lead_link})
- Company: [{lead["company_name"]}]({company_link})
"""


def review_queue_path_for(lead: dict) -> str:
    return f"review_queue/{slugify(lead['run_id'])}-{lead['company_slug']}.md"


def write_updated_notes(vault_path: Path, lead: dict) -> None:
    for folder in ("leads", "companies", "review_queue", "logs"):
        (vault_path / folder).mkdir(parents=True, exist_ok=True)

    lead_path = vault_path / lead["note_path"]
    company_path = vault_path / lead["company_note_path"]
    review_path = vault_path / lead["review_queue_path"]

    lead_path.write_text(build_lead_note(lead), encoding="utf-8")
    company_path.write_text(build_company_note(lead), encoding="utf-8")
    review_path.write_text(build_review_queue_note(lead), encoding="utf-8")


def build_query(args: argparse.Namespace) -> dict:
    query = {"engine": {"$in": INPUT_ENGINES}, "source": SOURCE_NAME}

    if args.run_id:
        query["run_id"] = args.run_id
    else:
        query["$or"] = [
            {"lead_score": {"$exists": False}},
            {"lead_score": None},
            {"review_status": DEFAULT_REVIEW_STATUS},
        ]

    if args.business_type:
        query["business_type"] = args.business_type
    if args.location:
        query["location"] = args.location

    return query


def write_run_log(vault_path: Path, run_id: str, leads: list[dict]) -> str:
    log_dir = vault_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"contractor_lead_engine_v3_{slugify(run_id)}.md"

    business_type = leads[0]["business_type"] if leads else ""
    location = leads[0]["location"] if leads else ""
    source = leads[0]["source"] if leads else SOURCE_NAME
    source_mode = leads[0].get("source_mode", "") if leads else ""
    rows = "\n".join(
        f"| {lead['company_name']} | {display(lead.get('website', ''))} | {lead['lead_score']} | {lead['review_status']} | {lead['review_queue_path']} |"
        for lead in leads
    )

    if not rows:
        rows = "| No leads found |  |  |  |  |"

    content = f"""---
type: pipeline_log
engine: {ENGINE_NAME}
run_id: {yaml_quote(run_id)}
business_type: {yaml_quote(business_type)}
location: {yaml_quote(location)}
source: {source}
created: {utc_now().date().isoformat()}
---

# Contractor Lead Engine v3 Run: {run_id}

## Input

- Business type: {business_type or "not provided"}
- Location: {location or "not provided"}
- Source: {source}
- Source mode: {source_mode or "not provided"}

## Results

- Leads enriched: {len(leads)}
- Mongo collections updated: `leads`, `companies`, `pipeline_runs`
- Vault folders updated: `leads`, `companies`, `review_queue`, `logs`

| Company | Website | Lead Score | Review Status | Review Note |
| --- | --- | ---: | --- | --- |
{rows}

## Notes

- This run used structured listing data from the v2 importer.
- Enrichment added v3 insights, lead intelligence, and review queue notes.
- Outreach drafts require human review before use.
"""
    log_path.write_text(content, encoding="utf-8")
    return f"logs/{log_path.name}"


def build_schema_fields(lead: dict, insights: dict, outreach: str) -> dict:
    return {
        "source": lead.get("source", SOURCE_NAME),
        "business_type": lead.get("business_type", ""),
        "location": lead.get("location", ""),
        "website_present": insights["website_present"],
        "website_quality_signal": insights["website_quality_signal"],
        "marketing_gap": insights["marketing_gap"],
        "priority_reason": insights["priority_reason"],
        "recommended_offer": insights["recommended_offer"],
        "lead_score": insights["lead_score"],
        "score": insights["lead_score"],
        "outreach_draft": outreach,
        "next_action": insights["next_action"],
        "review_status": insights["review_status"],
        "insights": insights,
    }


def main() -> None:
    args = parse_args()
    vault_path = get_vault_path()

    print(f"signalForge service: {SERVICE_NAME}")
    print(SERVICE_DESCRIPTION)
    print(f"Started at: {iso_now()}")
    print(f"Environment: {os.getenv('SIGNALFORGE_ENV', 'local')}")
    print(f"Run ID filter: {args.run_id or 'unreviewed v2/v3 leads'}")
    print(f"Vault path: {vault_path} | exists={vault_path.exists()}")
    print(f"OpenAI key configured: {bool(os.getenv('OPENAI_API_KEY'))} | not used in v3")

    client = MongoClient(os.getenv("MONGO_URI", DEFAULT_MONGO_URI), serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
        print("MongoDB: ready")
        db = get_database(client)
        query = build_query(args)
        leads = list(db.leads.find(query).sort("created_at", 1))

        enriched = []
        for lead in leads:
            insights = build_insights(lead)
            outreach = generate_outreach(lead, insights)
            now = utc_now()
            review_queue_path = lead.get("review_queue_path") or review_queue_path_for(lead)
            schema_fields = build_schema_fields(lead, insights, outreach)

            lead.update(schema_fields)
            lead["engine"] = ENGINE_NAME
            lead["status"] = "enriched"
            lead["updated_at"] = now
            lead["review_queue_path"] = review_queue_path

            update_fields = {
                **schema_fields,
                "engine": ENGINE_NAME,
                "status": "enriched",
                "updated_at": now,
                "review_queue_path": review_queue_path,
            }

            db.leads.update_one({"_id": lead["_id"]}, {"$set": update_fields})
            db.companies.update_one(
                {"run_id": lead["run_id"], "company_slug": lead["company_slug"]},
                {"$set": update_fields},
            )
            write_updated_notes(vault_path, lead)
            enriched.append(lead)

        run_id = args.run_id or (enriched[0]["run_id"] if enriched else "unreviewed")
        log_path = write_run_log(vault_path, run_id, enriched)
        db.pipeline_runs.update_one(
            {"run_id": run_id},
            {
                "$setOnInsert": {"created_at": utc_now()},
                "$set": {
                    "engine": ENGINE_NAME,
                    "source": SOURCE_NAME,
                    "status": "enriched",
                    "lead_count": len(enriched),
                    "log_path": log_path,
                    "review_queue_count": len(enriched),
                    "updated_at": utc_now(),
                    "completed_at": utc_now(),
                },
            },
            upsert=True,
        )

        print(f"Enriched {len(enriched)} leads with v3 intelligence.")
        print(f"Run log written to /vault/{log_path}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
