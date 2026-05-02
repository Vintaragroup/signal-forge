#!/usr/bin/env python3
"""
workspace_data_cleanup.py

Inspect, archive, and/or backfill workspace_slug across SignalForge MongoDB collections.

Usage examples:
  python scripts/workspace_data_cleanup.py --dry-run
  python scripts/workspace_data_cleanup.py --dry-run --workspace-slug austin-contractor-test
  python scripts/workspace_data_cleanup.py --backfill-default
  python scripts/workspace_data_cleanup.py --archive-legacy
  python scripts/workspace_data_cleanup.py --archive-mock
  python scripts/workspace_data_cleanup.py --archive-mock --archive-legacy

Safety:
  - Never deletes records without archiving first.
  - Archives go to <collection>_archive collections.
  - Never touches Demo Mode browser storage (localStorage only, not MongoDB).
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone

from pymongo import MongoClient

COLLECTIONS = [
    "contacts",
    "leads",
    "companies",
    "scraped_candidates",
    "tool_runs",
    "message_drafts",
    "approval_requests",
    "agent_tasks",
    "agent_runs",
    "deals",
]

# Patterns that indicate mock/test/demo data — checked against string field values
MOCK_PATTERNS = [
    r"\bmock\b",
    r"\bdemo\b",
    r"\bsynthetic\b",
    r"\btest\b",
    r"\bsample\b",
    r"contractor_test_campaign",
    r"module-v\d",
    r"module\d+-test",
    r"gpt_runtime_test",
    r"manual_contractor_test_cli",
    r"tool_layer_review",
]

# Fields to scan for mock patterns
MOCK_SCAN_FIELDS = [
    "source",
    "source_label",
    "run_id",
    "name",
    "notes",
    "company",
    "company_name",
    "module",
    "agent_name",
]

_MOCK_RE = re.compile("|".join(MOCK_PATTERNS), re.IGNORECASE)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_mock_record(doc: dict) -> bool:
    """Return True if any inspected field matches a known mock/test/demo pattern."""
    for field in MOCK_SCAN_FIELDS:
        value = doc.get(field)
        if isinstance(value, str) and _MOCK_RE.search(value):
            return True
    # Also check is_demo / is_test flags
    if doc.get("is_demo") or doc.get("is_test"):
        return True
    return False


def is_missing_workspace(doc: dict) -> bool:
    ws = doc.get("workspace_slug")
    return not ws or not isinstance(ws, str) or ws.strip() == ""


def get_client(mongo_uri: str) -> MongoClient:
    return MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)


def count_stats(db, workspace_slug: str = "") -> dict:
    """Return per-collection counts: total, missing_ws, mock, real."""
    stats = {}
    for coll_name in COLLECTIONS:
        coll = db[coll_name]
        base_query: dict = {}
        if workspace_slug:
            base_query["workspace_slug"] = workspace_slug

        all_docs = list(coll.find(base_query))
        total = len(all_docs)
        missing = [d for d in all_docs if is_missing_workspace(d)]
        mock = [d for d in all_docs if is_mock_record(d)]
        real = [d for d in all_docs if not is_missing_workspace(d) and not is_mock_record(d)]

        stats[coll_name] = {
            "total": total,
            "missing_workspace_slug": len(missing),
            "likely_mock_or_test": len(mock),
            "real_looking": len(real),
        }
    return stats


def print_stats(stats: dict, workspace_slug: str = "") -> None:
    scope = f"workspace_slug={workspace_slug}" if workspace_slug else "all records"
    print(f"\n{'='*62}")
    print(f"  DRY RUN — Workspace Data Inspection ({scope})")
    print(f"{'='*62}")
    fmt = f"  {'Collection':<22} {'Total':>6} {'Missing WS':>11} {'Mock/Test':>10} {'Real':>6}"
    print(fmt)
    print(f"  {'-'*56}")
    for coll_name, s in stats.items():
        print(
            f"  {coll_name:<22} {s['total']:>6} {s['missing_workspace_slug']:>11} "
            f"{s['likely_mock_or_test']:>10} {s['real_looking']:>6}"
        )
    print(f"{'='*62}\n")


def archive_and_remove(db, coll_name: str, docs: list, reason: str, dry_run: bool) -> int:
    """Copy docs to <coll>_archive with archive metadata, then remove from active collection."""
    if not docs:
        return 0
    archive_coll = db[f"{coll_name}_archive"]
    archived_at = utc_now()
    count = 0
    for doc in docs:
        archive_doc = {**doc, "_archived_at": archived_at, "_archive_reason": reason}
        if not dry_run:
            archive_coll.insert_one(archive_doc)
            db[coll_name].delete_one({"_id": doc["_id"]})
        count += 1
    return count


def run_backfill_default(db, dry_run: bool) -> None:
    """Assign workspace_slug='default' to all records missing it."""
    print("\n--- Backfill Default ---")
    total = 0
    updated_at = utc_now()
    for coll_name in COLLECTIONS:
        coll = db[coll_name]
        docs = [d for d in coll.find({}) if is_missing_workspace(d)]
        if not docs:
            continue
        print(f"  {coll_name}: {len(docs)} records to backfill")
        if not dry_run:
            ids = [d["_id"] for d in docs]
            coll.update_many(
                {"_id": {"$in": ids}},
                {"$set": {"workspace_slug": "default", "updated_at": updated_at}},
            )
        total += len(docs)
    label = "Would update" if dry_run else "Updated"
    print(f"\n  {label} {total} records → workspace_slug='default'")
    if dry_run:
        print("  (dry-run: no changes made)")


def run_archive_legacy(db, dry_run: bool) -> None:
    """Archive all records with missing workspace_slug."""
    print("\n--- Archive Legacy (missing workspace_slug) ---")
    total = 0
    for coll_name in COLLECTIONS:
        docs = [d for d in db[coll_name].find({}) if is_missing_workspace(d)]
        if not docs:
            continue
        count = archive_and_remove(db, coll_name, docs, "missing_workspace_slug", dry_run)
        label = "Would archive" if dry_run else "Archived"
        print(f"  {coll_name}: {label} {count} records → {coll_name}_archive")
        total += count
    label = "Would archive" if dry_run else "Archived"
    print(f"\n  {label} {total} total legacy records.")
    if dry_run:
        print("  (dry-run: no changes made)")


def run_archive_mock(db, dry_run: bool) -> None:
    """Archive all records identified as mock/test/demo data."""
    print("\n--- Archive Mock/Test/Demo Records ---")
    total = 0
    for coll_name in COLLECTIONS:
        docs = [d for d in db[coll_name].find({}) if is_mock_record(d)]
        if not docs:
            continue
        count = archive_and_remove(db, coll_name, docs, "mock_or_test_data", dry_run)
        label = "Would archive" if dry_run else "Archived"
        print(f"  {coll_name}: {label} {count} mock/test records → {coll_name}_archive")
        total += count
    label = "Would archive" if dry_run else "Archived"
    print(f"\n  {label} {total} total mock/test records.")
    if dry_run:
        print("  (dry-run: no changes made)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SignalForge workspace data cleanup utility.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dry-run", action="store_true", help="Print counts only; make no changes.")
    parser.add_argument("--backfill-default", action="store_true", help="Set workspace_slug='default' on records missing it.")
    parser.add_argument("--archive-legacy", action="store_true", help="Archive records missing workspace_slug.")
    parser.add_argument("--archive-mock", action="store_true", help="Archive records identified as mock/test/demo.")
    parser.add_argument("--workspace-slug", default="", help="Scope dry-run stats to a specific workspace_slug.")
    parser.add_argument("--mongo-uri", default="", help="MongoDB URI (default: MONGO_URI env or mongodb://localhost:27017).")
    args = parser.parse_args()

    mongo_uri = args.mongo_uri or os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB_NAME", "signalforge")

    if not any([args.dry_run, args.backfill_default, args.archive_legacy, args.archive_mock]):
        parser.print_help()
        print("\nNo action specified. Use --dry-run to inspect data.")
        sys.exit(0)

    if args.archive_legacy and args.backfill_default:
        print("ERROR: --archive-legacy and --backfill-default are mutually exclusive.")
        sys.exit(1)

    try:
        client = get_client(mongo_uri)
        db = client[db_name]
        # Trigger connection check
        db.command("ping")
    except Exception as exc:
        print(f"ERROR: Cannot connect to MongoDB at {mongo_uri}: {exc}")
        sys.exit(1)

    try:
        if args.dry_run:
            stats = count_stats(db, workspace_slug=args.workspace_slug)
            print_stats(stats, workspace_slug=args.workspace_slug)

        if args.backfill_default:
            run_backfill_default(db, dry_run=args.dry_run)

        if args.archive_legacy:
            run_archive_legacy(db, dry_run=args.dry_run)

        if args.archive_mock:
            run_archive_mock(db, dry_run=args.dry_run)

    finally:
        client.close()


if __name__ == "__main__":
    main()
