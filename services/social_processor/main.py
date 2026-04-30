import os
from datetime import datetime, timezone
from pathlib import Path

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None


SERVICE_NAME = "social_processor"
SERVICE_DESCRIPTION = "Normalizes social media events into actionable growth signals."
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"


def check_vault() -> bool:
    vault_path = Path(os.getenv("VAULT_PATH", "/vault"))
    prompt_path = vault_path / "prompts" / "social_signal_prompt.md"
    exists = vault_path.exists()
    print(f"Vault path: {vault_path} | exists={exists}")
    print(f"Social signal prompt available: {prompt_path.exists()}")
    return exists


def check_mongo() -> bool:
    mongo_uri = os.getenv("MONGO_URI", DEFAULT_MONGO_URI)

    if MongoClient is None:
        print("MongoDB check skipped: pymongo is not installed in this environment.")
        return False

    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=1500)
        client.admin.command("ping")
        print("MongoDB: ready")
        return True
    except Exception as exc:
        print(f"MongoDB: not ready ({exc.__class__.__name__}: {exc})")
        return False
    finally:
        try:
            client.close()
        except Exception:
            pass


def main() -> None:
    print(f"signalForge service: {SERVICE_NAME}")
    print(SERVICE_DESCRIPTION)
    print(f"Started at: {datetime.now(timezone.utc).isoformat()}")
    print(f"Environment: {os.getenv('SIGNALFORGE_ENV', 'local')}")
    print(f"X API key configured: {bool(os.getenv('X_API_KEY'))}")
    check_vault()
    check_mongo()
    print("Placeholder run complete. Next step: ingest social events and classify signal relevance.")


if __name__ == "__main__":
    main()
