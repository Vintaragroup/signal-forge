from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId


SAFETY_RULES = [
    "read_only",
    "no_form_submission",
    "no_login",
    "no_posting",
    "no_messaging",
    "no_captcha_bypass",
    "no_protected_or_private_scraping",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def slugify(value: str) -> str:
    import re

    value = clean_text(value).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "untitled"


def safe_tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key.lower() not in {"api_key", "token", "password", "secret"}}


class BaseTool:
    tool_name = "base_tool"
    tool_version = "v1"
    mode = "read_only"

    def record_tool_run(self, db, input_payload: dict[str, Any], output_payload: dict[str, Any], status: str = "completed", error: str | None = None) -> str | None:
        if db is None:
            return None
        now = utc_now()
        document = {
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "mode": self.mode,
            "status": status,
            "input": safe_tool_input(input_payload),
            "output_summary": output_payload,
            "error": error,
            "safety_rules": SAFETY_RULES,
            "outbound_actions_taken": 0,
            "created_at": now,
            "updated_at": now,
        }
        result = db.tool_runs.insert_one(document)
        return str(result.inserted_id)

    def candidate_document(self, candidate: dict[str, Any], tool_run_id: str | None = None) -> dict[str, Any]:
        now = utc_now()
        return {
            **candidate,
            "tool_run_id": tool_run_id,
            "status": "needs_review",
            "created_record_type": None,
            "created_record_id": None,
            "decision_events": [],
            "outbound_actions_taken": 0,
            "simulation_only": True,
            "created_at": candidate.get("created_at") or now,
            "updated_at": now,
        }

    def insert_candidates(self, db, candidates: list[dict[str, Any]], tool_run_id: str | None = None) -> list[str]:
        if db is None or not candidates:
            return []
        ids = []
        for candidate in candidates:
            document = self.candidate_document(candidate, tool_run_id)
            result = db.scraped_candidates.insert_one(document)
            ids.append(str(result.inserted_id if isinstance(result.inserted_id, ObjectId) else result.inserted_id))
        return ids
