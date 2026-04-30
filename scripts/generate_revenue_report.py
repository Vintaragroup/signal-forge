import argparse
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymongo import MongoClient

from core.constants import NURTURE_STATUSES, OPEN_DEAL_OUTCOMES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_PATH = PROJECT_ROOT / "vault"
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"
REPORT_PATH = "reports/revenue_performance_report.md"



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a SignalForge revenue and performance report from MongoDB.")
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


def value_or_dash(value: Any) -> str:
    text = clean_text(value)
    return text if text else "-"


def table_text(value: Any) -> str:
    return value_or_dash(value).replace("|", "\\|").replace("\n", " ")


def money_text(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"${value:,.2f}"
    return "$0.00"


def numeric_value(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def module_for_lead(lead: dict) -> str:
    module = clean_text(lead.get("module"))
    if module:
        return module

    engine = clean_text(lead.get("engine")).lower()
    business_type = clean_text(lead.get("business_type")).lower()
    if "contractor" in engine or "contractor" in business_type:
        return "contractor_growth"
    return "unknown"


def module_for(record: dict) -> str:
    return clean_text(record.get("module")) or "unknown"


def count_by_module(records: list[dict], module_getter=module_for) -> Counter:
    return Counter(module_getter(record) for record in records)


def nested_count_by_module(records: list[dict], status_field: str, module_getter=module_for) -> dict[str, Counter]:
    counts: dict[str, Counter] = defaultdict(Counter)
    for record in records:
        module = module_getter(record)
        status = clean_text(record.get(status_field)) or "not_set"
        counts[module][status] += 1
    return counts


def count_response_events(messages: list[dict], outcome: str) -> int:
    total = 0
    for message in messages:
        events = message.get("response_events") or []
        matched_events = [event for event in events if event.get("outcome") == outcome]
        if matched_events:
            total += len(matched_events)
        elif message.get("response_status") == outcome:
            total += 1
    return total


def module_count_table(counts: Counter, empty_label: str) -> str:
    rows = ["| Module | Count |", "| --- | ---: |"]
    for module, count in sorted(counts.items()):
        rows.append(f"| `{table_text(module)}` | {count} |")
    if len(rows) == 2:
        rows.append(f"| {empty_label} | 0 |")
    return "\n".join(rows)


def status_count_table(counts: Counter, empty_label: str) -> str:
    rows = ["| Status | Count |", "| --- | ---: |"]
    for status, count in sorted(counts.items()):
        rows.append(f"| `{table_text(status)}` | {count} |")
    if len(rows) == 2:
        rows.append(f"| {empty_label} | 0 |")
    return "\n".join(rows)


def module_status_table(counts: dict[str, Counter], empty_label: str) -> str:
    rows = ["| Module | Status | Count |", "| --- | --- | ---: |"]
    for module in sorted(counts):
        for status, count in sorted(counts[module].items()):
            rows.append(f"| `{table_text(module)}` | `{table_text(status)}` | {count} |")
    if len(rows) == 2:
        rows.append(f"| {empty_label} | - | 0 |")
    return "\n".join(rows)


def conversion_path_summary(deals: list[dict]) -> str:
    won_deals = [deal for deal in deals if deal.get("outcome") == "closed_won" or deal.get("deal_status") == "closed_won"]
    won_deals.sort(key=lambda deal: numeric_value(deal.get("deal_value")), reverse=True)

    rows = [
        "| Company | Module | Source | Deal Value | Path To Conversion | Deal Note |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for deal in won_deals[:10]:
        path = deal.get("path_to_conversion") or []
        path_text = " -> ".join(clean_text(item) for item in path if clean_text(item))
        rows.append(
            "| "
            f"{table_text(deal.get('company') or deal.get('person'))} | "
            f"`{table_text(deal.get('module'))}` | "
            f"{table_text(deal.get('source'))} | "
            f"{money_text(deal.get('deal_value'))} | "
            f"{table_text(path_text)} | "
            f"{table_text(deal.get('deal_note_path'))} |"
        )
    if len(rows) == 2:
        rows.append("| No closed-won deals found | - | - | $0.00 | - | - |")
    return "\n".join(rows)


def top_modules_table(
    contacts: list[dict],
    leads: list[dict],
    messages: list[dict],
    deals: list[dict],
) -> str:
    module_stats: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for contact in contacts:
        module_stats[module_for(contact)]["contacts"] += 1
    for lead in leads:
        module_stats[module_for_lead(lead)]["leads"] += 1
    for message in messages:
        module = module_for(message)
        module_stats[module]["messages"] += 1
        if message.get("send_status") == "sent":
            module_stats[module]["sent"] += 1
        if message.get("response_status") == "call_booked":
            module_stats[module]["booked"] += 1
    for deal in deals:
        module = module_for(deal)
        module_stats[module]["deals"] += 1
        if deal.get("outcome") == "closed_won" or deal.get("deal_status") == "closed_won":
            module_stats[module]["closed_won"] += 1
            module_stats[module]["closed_won_value"] += numeric_value(deal.get("deal_value"))

    ranked = sorted(
        module_stats.items(),
        key=lambda item: (item[1]["closed_won_value"], item[1]["closed_won"], item[1]["booked"], item[1]["sent"]),
        reverse=True,
    )

    rows = [
        "| Module | Contacts | Leads | Messages | Sent | Booked Calls | Deals | Closed Won | Closed Won Value |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for module, stats in ranked:
        rows.append(
            "| "
            f"`{table_text(module)}` | "
            f"{int(stats['contacts'])} | "
            f"{int(stats['leads'])} | "
            f"{int(stats['messages'])} | "
            f"{int(stats['sent'])} | "
            f"{int(stats['booked'])} | "
            f"{int(stats['deals'])} | "
            f"{int(stats['closed_won'])} | "
            f"{money_text(stats['closed_won_value'])} |"
        )
    if len(rows) == 2:
        rows.append("| No module activity found | 0 | 0 | 0 | 0 | 0 | 0 | 0 | $0.00 |")
    return "\n".join(rows)


def contacts_needing_nurture_table(contacts: list[dict]) -> str:
    nurture_contacts = [
        contact
        for contact in contacts
        if contact.get("segment") == "nurture"
        or contact.get("deal_outcome") == "nurture"
        or contact.get("contact_status") in NURTURE_STATUSES
        or contact.get("response_status") in NURTURE_STATUSES
    ]
    nurture_contacts.sort(key=lambda contact: (module_for(contact), clean_text(contact.get("company")), clean_text(contact.get("name"))))

    rows = ["| Contact | Company | Module | Status | Segment | Reason |", "| --- | --- | --- | --- | --- | --- |"]
    for contact in nurture_contacts[:25]:
        rows.append(
            "| "
            f"{table_text(contact.get('name'))} | "
            f"{table_text(contact.get('company'))} | "
            f"`{table_text(contact.get('module'))}` | "
            f"`{table_text(contact.get('contact_status'))}` | "
            f"`{table_text(contact.get('segment'))}` | "
            f"{table_text(contact.get('priority_reason') or contact.get('response_note') or contact.get('notes'))} |"
        )
    if len(rows) == 2:
        rows.append("| No nurture contacts found | - | - | - | - | - |")
    return "\n".join(rows)


def open_opportunities_table(contacts: list[dict], leads: list[dict], deals: list[dict]) -> str:
    rows = ["| Type | Name | Company | Module | Status | Value | Note |", "| --- | --- | --- | --- | --- | ---: | --- |"]

    for deal in deals:
        if deal.get("outcome") in OPEN_DEAL_OUTCOMES or deal.get("deal_status") in OPEN_DEAL_OUTCOMES:
            rows.append(
                "| "
                "deal | "
                f"{table_text(deal.get('person'))} | "
                f"{table_text(deal.get('company'))} | "
                f"`{table_text(deal.get('module'))}` | "
                f"`{table_text(deal.get('outcome') or deal.get('deal_status'))}` | "
                f"{money_text(deal.get('deal_value'))} | "
                f"{table_text(deal.get('deal_note_path'))} |"
            )

    for contact in contacts:
        if contact.get("contact_status") in ("interested", "call_booked", "contacted"):
            rows.append(
                "| "
                "contact | "
                f"{table_text(contact.get('name'))} | "
                f"{table_text(contact.get('company'))} | "
                f"`{table_text(contact.get('module'))}` | "
                f"`{table_text(contact.get('contact_status'))}` | "
                "$0.00 | "
                f"{table_text(contact.get('latest_deal_note_path') or contact.get('recommended_action'))} |"
            )

    for lead in leads:
        if lead.get("outreach_status") in ("sent", "replied", "follow_up_needed", "booked_call"):
            rows.append(
                "| "
                "lead | "
                f"{table_text(lead.get('company_name'))} | "
                f"{table_text(lead.get('company_name'))} | "
                f"`{table_text(module_for_lead(lead))}` | "
                f"`{table_text(lead.get('outreach_status'))}` | "
                "$0.00 | "
                f"{table_text(lead.get('outreach_note_path') or lead.get('note_path'))} |"
            )

    if len(rows) == 2:
        rows.append("| No open opportunities found | - | - | - | - | $0.00 | - |")
    return "\n".join(rows)


def build_report(
    contacts: list[dict],
    leads: list[dict],
    messages: list[dict],
    deals: list[dict],
) -> str:
    generated_at = utc_now().isoformat()

    contacts_by_module = count_by_module(contacts)
    leads_by_module = count_by_module(leads, module_for_lead)
    message_review_counts = Counter(clean_text(message.get("review_status")) or "not_set" for message in messages)
    message_send_counts = Counter(clean_text(message.get("send_status")) or "not_set" for message in messages)
    response_counts = Counter(clean_text(message.get("response_status")) or "not_set" for message in messages)
    deal_outcome_counts = Counter(clean_text(deal.get("outcome") or deal.get("deal_status")) or "not_set" for deal in deals)

    closed_won_deals = [deal for deal in deals if deal.get("outcome") == "closed_won" or deal.get("deal_status") == "closed_won"]
    closed_won_value = sum(numeric_value(deal.get("deal_value")) for deal in closed_won_deals)
    call_booked_drafts = sum(1 for message in messages if message.get("response_status") == "call_booked")
    call_booked_events = count_response_events(messages, "call_booked")
    deals_with_meetings = sum(1 for deal in deals if clean_text(deal.get("meeting_note_path")))

    return f"""---
type: revenue_performance_report
generated_at: {generated_at}
source: mongodb
---

# Revenue And Performance Report

Generated at: {generated_at}

## Executive Summary

| Metric | Value |
| --- | ---: |
| Total contacts | {len(contacts)} |
| Total leads | {len(leads)} |
| Message drafts | {len(messages)} |
| Messages sent | {message_send_counts.get("sent", 0)} |
| Responses logged | {len(messages) - response_counts.get("not_set", 0)} |
| Meetings generated | {call_booked_events} |
| Deals tracked | {len(deals)} |
| Closed won count | {len(closed_won_deals)} |
| Closed won deal value | {money_text(closed_won_value)} |

## Contacts By Module

{module_count_table(contacts_by_module, "No contacts found")}

## Leads By Module

{module_count_table(leads_by_module, "No leads found")}

## Message Drafts By Review Status

{status_count_table(message_review_counts, "No message drafts found")}

## Message Drafts By Send Status

{status_count_table(message_send_counts, "No message drafts found")}

## Message Statuses By Module

### Review Status

{module_status_table(nested_count_by_module(messages, "review_status"), "No message drafts found")}

### Send Status

{module_status_table(nested_count_by_module(messages, "send_status"), "No message drafts found")}

## Responses By Status

{status_count_table(response_counts, "No responses found")}

## Meetings Generated

SignalForge does not store meetings in a dedicated collection yet. This section uses MongoDB-only meeting indicators.

| Indicator | Count |
| --- | ---: |
| Current drafts with `response_status=call_booked` | {call_booked_drafts} |
| Call-booked response events | {call_booked_events} |
| Deals linked to a meeting prep note | {deals_with_meetings} |

## Deals By Outcome

{status_count_table(deal_outcome_counts, "No deals found")}

## Closed Won

| Metric | Value |
| --- | ---: |
| Closed won count | {len(closed_won_deals)} |
| Closed won deal value total | {money_text(closed_won_value)} |

## Conversion Path Summary

{conversion_path_summary(deals)}

## Top Performing Modules

{top_modules_table(contacts, leads, messages, deals)}

## Contacts Needing Nurture

{contacts_needing_nurture_table(contacts)}

## Open Opportunities

{open_opportunities_table(contacts, leads, deals)}
"""


def main() -> None:
    args = parse_args()
    vault_path = Path(args.vault)
    report_path = vault_path / REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
        db = get_database(client)
        contacts = list(db.contacts.find({}))
        leads = list(db.leads.find({}))
        messages = list(db.message_drafts.find({}))
        deals = list(db.deals.find({}))

        report_path.write_text(build_report(contacts, leads, messages, deals), encoding="utf-8")
        print(f"Revenue performance report written: {report_path}")
        print(f"Closed won: {sum(1 for deal in deals if deal.get('outcome') == 'closed_won' or deal.get('deal_status') == 'closed_won')}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
