import argparse
import os
import subprocess
import sys
from pathlib import Path

from pymongo import MongoClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_PATH = PROJECT_ROOT / "vault"
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"

REQUIRED_VAULT_FOLDERS = (
    "leads",
    "companies",
    "review_queue",
    "outreach",
    "followups",
    "reports",
    "contacts",
    "messages",
    "meetings",
    "deals",
    "logs",
    "prompts",
)

REQUIRED_SCRIPTS = (
    "scripts/run_daily_pipeline.sh",
    "scripts/review_lead.py",
    "scripts/update_outreach_status.py",
    "scripts/generate_pipeline_report.py",
    "scripts/import_contacts.py",
    "scripts/score_contacts.py",
    "scripts/draft_messages.py",
    "scripts/review_message.py",
    "scripts/log_manual_send.py",
    "scripts/log_response.py",
    "scripts/generate_meeting_prep.py",
    "scripts/log_deal_outcome.py",
    "scripts/generate_revenue_report.py",
    "scripts/check_system.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check the SignalForge v1 operating system.")
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


def ok(message: str) -> None:
    print(f"[ok] {message}")


def fail(message: str) -> None:
    print(f"[fail] {message}")


def check_file(path: Path, label: str) -> bool:
    if path.exists():
        ok(label)
        return True
    fail(f"{label} missing: {path}")
    return False


def check_mongo(mongo_uri: str) -> bool:
    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        count = client.get_default_database().leads.count_documents({})
        ok(f"MongoDB connected; leads collection has {count} records")
        return True
    except Exception as exc:
        fail(f"MongoDB connection failed: {exc}")
        return False
    finally:
        try:
            client.close()
        except Exception:
            pass


def check_vault(vault_path: Path) -> bool:
    success = True
    if not vault_path.exists():
        fail(f"Vault missing: {vault_path}")
        return False

    ok(f"Vault exists: {vault_path}")
    for folder in REQUIRED_VAULT_FOLDERS:
        path = vault_path / folder
        if path.exists() and path.is_dir():
            ok(f"Vault folder exists: {folder}")
        else:
            fail(f"Vault folder missing: {folder}")
            success = False
    return success


def check_required_files() -> bool:
    success = True
    success = check_file(PROJECT_ROOT / "docker-compose.yml", "docker-compose.yml exists") and success
    for script in REQUIRED_SCRIPTS:
        success = check_file(PROJECT_ROOT / script, f"{script} exists") and success
    return success


def check_report_generation(mongo_uri: str, vault_path: Path) -> bool:
    reports = (
        ("generate_pipeline_report.py", "contractor_pipeline_report.md"),
        ("generate_revenue_report.py", "revenue_performance_report.md"),
    )
    success = True
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(PROJECT_ROOT) if not existing_pythonpath else f"{PROJECT_ROOT}{os.pathsep}{existing_pythonpath}"

    for script_name, report_name in reports:
        command = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / script_name),
            "--mongo-uri",
            mongo_uri,
            "--vault",
            str(vault_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, env=env)
        if result.returncode != 0:
            fail(f"Report generation failed: {script_name}")
            if result.stdout:
                print(result.stdout.strip())
            if result.stderr:
                print(result.stderr.strip())
            success = False
            continue

        report_path = vault_path / "reports" / report_name
        if report_path.exists():
            ok(f"Report generated: {report_path}")
        else:
            fail(f"Report command completed but report is missing: {report_path}")
            success = False

    return success


def main() -> None:
    args = parse_args()
    vault_path = Path(args.vault)

    checks = [
        check_required_files(),
        check_vault(vault_path),
        check_mongo(args.mongo_uri),
        check_report_generation(args.mongo_uri, vault_path),
    ]

    if all(checks):
        print("System check passed.")
        return

    raise SystemExit("System check failed.")


if __name__ == "__main__":
    main()
