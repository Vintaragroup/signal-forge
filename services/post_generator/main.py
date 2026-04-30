import os
from datetime import datetime, timezone
from pathlib import Path

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None


SERVICE_NAME = "post_generator"
SERVICE_DESCRIPTION = "Generates outreach and content drafts from enriched records and signals."
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"


def check_vault() -> bool:
    vault_path = Path(os.getenv("VAULT_PATH", "/vault"))
    prompt_path = vault_path / "prompts" / "content_generation_prompt.md"
    exists = vault_path.exists()
    print(f"Vault path: {vault_path} | exists={exists}")
    print(f"Content generation prompt available: {prompt_path.exists()}")
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
    print(f"OpenAI key configured: {bool(os.getenv('OPENAI_API_KEY'))}")
    check_vault()
    check_mongo()
    print("Placeholder run complete. Next step: generate drafts and write markdown content notes.")


if __name__ == "__main__":
    main()
