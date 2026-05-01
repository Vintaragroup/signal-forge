import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main import get_client, get_database


def test_approval_query() -> dict:
    return {"$or": [{"is_test": True}, {"request_origin": "test"}]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up synthetic/test approval requests without touching real approvals.")
    parser.add_argument("--dry-run", action="store_true", help="Show matching approval requests without deleting or archiving them.")
    parser.add_argument("--archive", action="store_true", help="Copy matching requests to approval_requests_archive before deleting them.")
    args = parser.parse_args()

    client = get_client()
    try:
        db = get_database(client)
        query = test_approval_query()
        records = list(db.approval_requests.find(query).sort([("created_at", -1)]))
        print(f"Found {len(records)} synthetic/test approval request(s).")
        for record in records[:20]:
            print(f"- {record.get('_id')} | {record.get('title') or record.get('request_type')} | {record.get('created_at')}")
        if len(records) > 20:
            print(f"...and {len(records) - 20} more.")

        if args.dry_run or not records:
            print("Dry run only. No approval requests were changed.")
            return

        if args.archive:
            archived_at = datetime.now(timezone.utc)
            archive_records = [{**record, "archived_at": archived_at, "archived_from": "approval_requests"} for record in records]
            db.approval_requests_archive.insert_many(archive_records)
            print(f"Archived {len(archive_records)} approval request(s) to approval_requests_archive.")

        ids = [record["_id"] for record in records]
        result = db.approval_requests.delete_many({"_id": {"$in": ids}})
        print(f"Deleted {result.deleted_count} synthetic/test approval request(s). Real approvals were not matched.")
    finally:
        client.close()


if __name__ == "__main__":
    main()