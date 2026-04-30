import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_PATH = PROJECT_ROOT / "vault"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "untitled-lead"


def build_note(args: argparse.Namespace) -> str:
    created_at = datetime.now(timezone.utc).date().isoformat()
    title = args.contact or args.company

    return f"""---
type: lead
status: new
score: 0
company: {args.company}
contact: {args.contact or ""}
source: {args.source or ""}
created: {created_at}
updated: {created_at}
---

# Lead: {title}

## Summary

New lead created for review.

## Source

- Source: {args.source or ""}
- Source URL: {args.source_url or ""}
- Collected date: {created_at}

## Company

- Name: {args.company}
- Website: {args.website or ""}
- Industry:
- Location:

## Contact

- Name: {args.contact or ""}
- Role: {args.role or ""}
- Profile: {args.profile_url or ""}
- Email:

## Signals

-

## Score

- ICP fit:
- Timing:
- Contact relevance:
- Data confidence:
- Total:

## Next Action

- Review and enrich this lead.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a signalForge lead note.")
    parser.add_argument("--company", required=True, help="Company name")
    parser.add_argument("--contact", default="", help="Contact name")
    parser.add_argument("--role", default="", help="Contact role")
    parser.add_argument("--website", default="", help="Company website")
    parser.add_argument("--source", default="", help="Lead source")
    parser.add_argument("--source-url", default="", help="Source URL")
    parser.add_argument("--profile-url", default="", help="Contact profile URL")
    parser.add_argument(
        "--vault",
        default=os.getenv("VAULT_PATH", str(DEFAULT_VAULT_PATH)),
        help="Vault path, defaults to local vault or VAULT_PATH",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault)
    leads_dir = vault_path / "leads"
    leads_dir.mkdir(parents=True, exist_ok=True)

    file_stem = slugify(args.contact or args.company)
    note_path = leads_dir / f"{file_stem}.md"

    if note_path.exists():
        raise SystemExit(f"Lead note already exists: {note_path}")

    note_path.write_text(build_note(args), encoding="utf-8")
    print(f"Created lead note: {note_path}")


if __name__ == "__main__":
    main()
