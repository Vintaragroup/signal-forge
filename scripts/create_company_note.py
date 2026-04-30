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
    return value.strip("-") or "untitled-company"


def build_note(args: argparse.Namespace) -> str:
    created_at = datetime.now(timezone.utc).date().isoformat()

    return f"""---
type: company
status: new
company: {args.company}
website: {args.website or ""}
industry: {args.industry or ""}
created: {created_at}
updated: {created_at}
---

# Company: {args.company}

## Summary

New company profile created for enrichment.

## Firmographics

- Website: {args.website or ""}
- Industry: {args.industry or ""}
- Size:
- Location:
- Funding:

## ICP Fit

- Fit:
- Reasoning:

## Signals

-

## Value Hypothesis

-

## Contacts

| Name | Role | Profile | Notes |
| --- | --- | --- | --- |
|  |  |  |  |

## Risks And Unknowns

-

## Next Action

- Enrich this company profile.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a signalForge company note.")
    parser.add_argument("--company", required=True, help="Company name")
    parser.add_argument("--website", default="", help="Company website")
    parser.add_argument("--industry", default="", help="Company industry")
    parser.add_argument(
        "--vault",
        default=os.getenv("VAULT_PATH", str(DEFAULT_VAULT_PATH)),
        help="Vault path, defaults to local vault or VAULT_PATH",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault)
    companies_dir = vault_path / "companies"
    companies_dir.mkdir(parents=True, exist_ok=True)

    note_path = companies_dir / f"{slugify(args.company)}.md"

    if note_path.exists():
        raise SystemExit(f"Company note already exists: {note_path}")

    note_path.write_text(build_note(args), encoding="utf-8")
    print(f"Created company note: {note_path}")


if __name__ == "__main__":
    main()
