import argparse
import os
import sys
from pathlib import Path

from pymongo import MongoClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.constants import VALID_MODULES
from tools.manual_import_tool import CandidateImportError, ManualCandidateImportTool


DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a real prospect/source CSV into SignalForge Research / Tools.")
    parser.add_argument("csv_path", help="Path to the candidate CSV file.")
    parser.add_argument("--module", required=True, choices=VALID_MODULES, help="SignalForge module name.")
    parser.add_argument("--source-label", required=True, help="Operator-readable source label for this import.")
    parser.add_argument(
        "--mongo-uri",
        default=os.getenv("MONGO_URI", DEFAULT_MONGO_URI),
        help="MongoDB URI. Defaults to MONGO_URI or localhost SignalForge.",
    )
    return parser.parse_args()


def get_database(client: MongoClient):
    try:
        return client.get_default_database()
    except Exception:
        return client["signalforge"]


def resolve_csv_path(csv_path: str) -> Path:
    path = Path(csv_path)
    if not path.is_absolute():
        parts = path.parts
        path = Path("/data", *parts[1:]) if parts and parts[0] == "data" else PROJECT_ROOT / path
    return path


def main() -> None:
    args = parse_args()
    csv_path = resolve_csv_path(args.csv_path)

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
        db = get_database(client)
        result = ManualCandidateImportTool().run_path(csv_path, args.module, args.source_label, db=db)
    except CandidateImportError as error:
        raise SystemExit(f"Import failed safely: {error}") from error
    finally:
        client.close()

    print(f"Candidates imported: {result['candidate_count']}")
    print(f"Duplicates detected: {result['duplicate_count']}")
    print(f"Tool run: {result['tool_run_id']}")
    print(f"Source label: {result['source_label']}")
    print("No contacts or leads created automatically. No outbound actions taken.")


if __name__ == "__main__":
    main()
