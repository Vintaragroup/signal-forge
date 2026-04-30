import argparse
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient

from core.constants import LEAD_REVIEW_STATUSES, OUTREACH_STATUSES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_PATH = PROJECT_ROOT / "vault"
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"
REPORT_PATH = "reports/contractor_pipeline_report.md"
REVIEW_STATUSES = LEAD_REVIEW_STATUSES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a markdown contractor pipeline report from MongoDB.")
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
    parser.add_argument(
        "--latest-runs",
        type=int,
        default=10,
        help="Number of latest pipeline runs to include.",
    )
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_database(client: MongoClient):
    try:
        return client.get_default_database()
    except Exception:
        return client["signalforge"]


def value_or_dash(value) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def table_text(value) -> str:
    text = value_or_dash(value)
    return text.replace("|", "\\|").replace("\n", " ")


def score_for(lead: dict) -> int | None:
    score = lead.get("lead_score", lead.get("score"))
    if isinstance(score, (int, float)):
        return int(score)
    return None


def iso_date(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return value_or_dash(value)


def status_table(counts: Counter, statuses: tuple[str, ...], missing_label: str = "not_set") -> str:
    rows = ["| Status | Count |", "| --- | ---: |"]
    for status in statuses:
        rows.append(f"| `{status}` | {counts.get(status, 0)} |")
    if counts.get(missing_label, 0):
        rows.append(f"| `{missing_label}` | {counts[missing_label]} |")
    return "\n".join(rows)


def top_leads_table(leads: list[dict]) -> str:
    rows = [
        "| Rank | Company | Score | Review | Outreach | Priority Reason | Lead Note |",
        "| ---: | --- | ---: | --- | --- | --- | --- |",
    ]
    scored = [lead for lead in leads if score_for(lead) is not None]
    scored.sort(key=lambda lead: score_for(lead) or 0, reverse=True)

    for index, lead in enumerate(scored[:10], start=1):
        rows.append(
            "| "
            f"{index} | "
            f"{table_text(lead.get('company_name'))} | "
            f"{score_for(lead)} | "
            f"{table_text(lead.get('review_status'))} | "
            f"{table_text(lead.get('outreach_status'))} | "
            f"{table_text(lead.get('priority_reason'))} | "
            f"{table_text(lead.get('note_path'))} |"
        )

    if len(rows) == 2:
        rows.append("| - | No scored leads found | - | - | - | - | - |")

    return "\n".join(rows)


def lead_list_table(leads: list[dict], empty_label: str) -> str:
    rows = [
        "| Company | Score | Review | Outreach | Next Action | Note |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for lead in leads:
        rows.append(
            "| "
            f"{table_text(lead.get('company_name'))} | "
            f"{value_or_dash(score_for(lead))} | "
            f"{table_text(lead.get('review_status'))} | "
            f"{table_text(lead.get('outreach_status'))} | "
            f"{table_text(lead.get('next_action'))} | "
            f"{table_text(lead.get('note_path'))} |"
        )

    if len(rows) == 2:
        rows.append(f"| {empty_label} | - | - | - | - | - |")

    return "\n".join(rows)


def latest_runs_table(runs: list[dict]) -> str:
    rows = [
        "| Run ID | Engine | Status | Leads | Source | Updated | Log |",
        "| --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for run in runs:
        rows.append(
            "| "
            f"{table_text(run.get('run_id'))} | "
            f"{table_text(run.get('engine'))} | "
            f"{table_text(run.get('status'))} | "
            f"{value_or_dash(run.get('lead_count'))} | "
            f"{table_text(run.get('source'))} | "
            f"{table_text(iso_date(run.get('updated_at') or run.get('completed_at') or run.get('created_at')))} | "
            f"{table_text(run.get('log_path'))} |"
        )

    if len(rows) == 2:
        rows.append("| No pipeline runs found | - | - | - | - | - | - |")

    return "\n".join(rows)


def build_report(leads: list[dict], runs: list[dict]) -> str:
    generated_at = utc_now().isoformat()
    total_leads = len(leads)
    scores = [score_for(lead) for lead in leads if score_for(lead) is not None]
    average_score = round(sum(scores) / len(scores), 1) if scores else 0

    review_counts = Counter(lead.get("review_status") or "not_set" for lead in leads)
    outreach_counts = Counter(lead.get("outreach_status") or "not_set" for lead in leads)

    follow_up_leads = [lead for lead in leads if lead.get("outreach_status") == "follow_up_needed"]
    booked_call_leads = [lead for lead in leads if lead.get("outreach_status") == "booked_call"]
    closed_won = outreach_counts.get("closed_won", 0)
    closed_lost = outreach_counts.get("closed_lost", 0)

    return f"""---
type: pipeline_report
engine: contractor_lead_engine
generated_at: {generated_at}
---

# Contractor Pipeline Report

Generated at: {generated_at}

## Summary

| Metric | Value |
| --- | ---: |
| Total leads | {total_leads} |
| Average lead score | {average_score} |
| Leads needing follow-up | {len(follow_up_leads)} |
| Booked calls | {len(booked_call_leads)} |
| Closed won | {closed_won} |
| Closed lost | {closed_lost} |

## Leads By Review Status

{status_table(review_counts, REVIEW_STATUSES)}

## Leads By Outreach Status

{status_table(outreach_counts, OUTREACH_STATUSES)}

## Top 10 Leads By Score

{top_leads_table(leads)}

## Leads Needing Follow-Up

{lead_list_table(follow_up_leads, "No leads currently need follow-up")}

## Booked Calls

{lead_list_table(booked_call_leads, "No booked calls found")}

## Latest Pipeline Runs

{latest_runs_table(runs)}
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
        leads = list(
            db.leads.find(
                {},
                {
                    "company_name": 1,
                    "lead_score": 1,
                    "score": 1,
                    "review_status": 1,
                    "outreach_status": 1,
                    "priority_reason": 1,
                    "next_action": 1,
                    "note_path": 1,
                },
            )
        )
        runs = list(
            db.pipeline_runs.find(
                {},
                {
                    "run_id": 1,
                    "engine": 1,
                    "status": 1,
                    "lead_count": 1,
                    "source": 1,
                    "updated_at": 1,
                    "completed_at": 1,
                    "created_at": 1,
                    "log_path": 1,
                },
            )
            .sort("updated_at", -1)
            .limit(args.latest_runs)
        )

        report_path.write_text(build_report(leads, runs), encoding="utf-8")
        print(f"Pipeline report written: {report_path}")
        print(f"Total leads: {len(leads)}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
