#!/usr/bin/env python3
"""
SignalForge Backup & Restore CLI  (Phase 6V)

Usage:
    python scripts/backup_restore.py backup [--collections COL1,COL2] [--no-compress] [--out FILE]
    python scripts/backup_restore.py restore --file FILE [--dry-run]
    python scripts/backup_restore.py status

Environment:
    SIGNALFORGE_API_URL  Base URL of the API (default: http://localhost:8000)
    SIGNALFORGE_API_KEY  API key for authenticated deployments (optional)
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

API_URL = os.environ.get("SIGNALFORGE_API_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("SIGNALFORGE_API_KEY", "")


def _headers():
    h = {"Content-Type": "application/json"}
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    return h


def _request(method: str, path: str, body: dict | None = None) -> dict:
    url = API_URL + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        payload = {}
        try:
            payload = json.loads(exc.read())
        except Exception:
            pass
        print(f"ERROR {exc.code}: {payload.get('error', exc.reason)}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Cannot reach {API_URL}: {exc.reason}", file=sys.stderr)
        sys.exit(1)


def cmd_backup(args):
    body: dict = {}
    if args.collections:
        body["collections"] = [c.strip() for c in args.collections.split(",")]
    if args.no_compress:
        body["compress"] = False

    print(f"Creating backup from {API_URL} ...")
    result = _request("POST", "/system/backup", body)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outfile = args.out or f"signalforge_backup_{ts}.json"
    with open(outfile, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Backup saved → {outfile}")
    print(f"  Collections : {', '.join(result.get('collections', []))}")
    print(f"  Documents   : {result.get('total_documents', 0)}")
    print(f"  Bytes       : {result.get('bytes', 0)}")
    print(f"  Compressed  : {result.get('compressed', True)}")


def cmd_restore(args):
    if not args.file:
        print("ERROR: --file is required for restore", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(args.file):
        print(f"ERROR: file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    with open(args.file) as f:
        backup = json.load(f)

    payload = backup.get("payload")
    if not payload:
        print("ERROR: backup file does not contain a 'payload' field", file=sys.stderr)
        sys.exit(1)

    compressed = backup.get("compressed", True)
    body = {
        "payload": payload,
        "compressed": compressed,
        "dry_run": args.dry_run,
    }

    mode = "DRY RUN — no data will be written" if args.dry_run else "LIVE RESTORE"
    print(f"Restoring from {args.file} [{mode}] ...")
    result = _request("POST", "/system/restore", body)

    print(f"Restore complete (dry_run={result.get('dry_run')})")
    for coll, info in result.get("collections", {}).items():
        status = info.get("status", "?")
        count = info.get("documents", info.get("would_restore", 0))
        print(f"  {coll:40s}  {status}  ({count} docs)")


def cmd_status(args):
    print(f"Fetching recovery status from {API_URL} ...")
    data = _request("GET", "/system/recovery-status")
    stuck = data.get("stuck_orchestrations", [])
    wh = data.get("worker_health", {})

    print(f"\nOrchestration health:")
    print(f"  Stuck orchestrations : {len(stuck)}")
    if stuck:
        for o in stuck[:5]:
            print(f"    • {o.get('orchestration_id')}  ({o.get('workspace_slug', '?')})")
    print(f"  Risk flag            : {data.get('orphaned_task_risk', False)}")

    print(f"\nWorker health:")
    print(f"  Total    : {wh.get('total_workers', 0)}")
    print(f"  Healthy  : {wh.get('healthy', 0)}")
    print(f"  Stale    : {wh.get('stale', 0)}")
    if wh.get("stale_worker_ids"):
        for wid in wh["stale_worker_ids"][:5]:
            print(f"    • {wid}")

    if data.get("orphaned_task_risk"):
        print(f"\nRecommendation: {data.get('recommendation')}")

    print(f"\nEvaluated at: {data.get('evaluated_at')}")


def main():
    parser = argparse.ArgumentParser(
        prog="backup_restore.py",
        description="SignalForge backup / restore CLI (Phase 6V)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_backup = sub.add_parser("backup", help="Create a portable snapshot of the database")
    p_backup.add_argument("--collections", metavar="COL1,COL2",
                          help="Comma-separated list of collections (default: all)")
    p_backup.add_argument("--no-compress", action="store_true",
                          help="Skip gzip compression")
    p_backup.add_argument("--out", metavar="FILE",
                          help="Output filename (default: signalforge_backup_<ts>.json)")

    p_restore = sub.add_parser("restore", help="Restore from a snapshot file")
    p_restore.add_argument("--file", metavar="FILE", required=True,
                           help="Path to the backup JSON file created by 'backup'")
    p_restore.add_argument("--dry-run", action="store_true",
                           help="Preview what would be restored without writing")

    sub.add_parser("status", help="Show current recovery / worker status")

    args = parser.parse_args()
    {"backup": cmd_backup, "restore": cmd_restore, "status": cmd_status}[args.command](args)


if __name__ == "__main__":
    main()
