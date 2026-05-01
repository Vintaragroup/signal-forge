from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from urllib import robotparser

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


def robots_allowed(public_url: str, user_agent: str = "SignalForgeToolLayer/1.0") -> bool:
    parsed = urlparse(clean_text(public_url))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
        return parser.can_fetch(user_agent, public_url)
    except Exception:
        return True


class BaseTool:
    tool_name = "base_tool"
    tool_version = "v1"
    mode = "read_only"

    def record_tool_run(
        self,
        db,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
        status: str = "completed",
        error: str | None = None,
        agent_name: str | None = None,
        agent_run_id: str | None = None,
    ) -> str | None:
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
            "source_url": output_payload.get("source_url") or input_payload.get("source_url") or input_payload.get("public_url"),
            "extracted_fields": output_payload.get("extracted_fields") or output_payload.get("fields") or {},
            "confidence": output_payload.get("confidence"),
            "source_quality": output_payload.get("source_quality"),
            "agent_name": agent_name,
            "agent_run_id": agent_run_id,
            "linked_agent_run_id": agent_run_id,
            "safety_rules": SAFETY_RULES,
            "outbound_actions_taken": 0,
            "created_at": now,
            "updated_at": now,
        }
        result = db.tool_runs.insert_one(document)
        return str(result.inserted_id)

    def candidate_document(self, candidate: dict[str, Any], tool_run_id: str | None = None, agent_run_id: str | None = None) -> dict[str, Any]:
        now = utc_now()
        extracted_fields = candidate.get("extracted_fields") or {
            "company": candidate.get("company"),
            "website": candidate.get("website"),
            "phone": candidate.get("phone"),
            "email": candidate.get("email"),
            "city": candidate.get("city"),
            "state": candidate.get("state"),
            "service_category": candidate.get("service_category"),
            "source_url": candidate.get("source_url"),
        }
        return {
            **candidate,
            "source": candidate.get("source") or self.tool_name,
            "extracted_fields": {key: value for key, value in extracted_fields.items() if value not in (None, "")},
            "tool_run_id": tool_run_id,
            "linked_agent_run_id": agent_run_id,
            "status": candidate.get("status") or "needs_review",
            "created_record_type": None,
            "created_record_id": None,
            "decision_events": [],
            "outbound_actions_taken": 0,
            "simulation_only": True,
            "created_at": candidate.get("created_at") or now,
            "updated_at": now,
        }

    def create_tool_artifact(
        self,
        db,
        tool_run_id: str | None,
        content: dict[str, Any],
        agent_name: str | None = None,
        agent_run_id: str | None = None,
    ) -> str | None:
        if db is None or not hasattr(db, "agent_artifacts"):
            return None
        artifact = {
            "run_id": agent_run_id,
            "agent_name": agent_name or "tool_layer",
            "module": content.get("module") or content.get("input", {}).get("module"),
            "artifact_type": "tool_run_result",
            "label": f"{self.tool_name} result",
            "tool_name": self.tool_name,
            "tool_run_id": tool_run_id,
            "content": content,
            "created_at": utc_now(),
        }
        result = db.agent_artifacts.insert_one(artifact)
        return str(result.inserted_id)

    def create_candidate_approval(self, db, candidate_id: str, candidate: dict[str, Any], agent_name: str | None = None, agent_run_id: str | None = None) -> str | None:
        if db is None or not hasattr(db, "approval_requests"):
            return None
        now = utc_now()
        title = candidate.get("company") or candidate.get("name") or candidate.get("source_url") or "Scraped candidate"
        request = {
            "run_id": agent_run_id,
            "agent_name": agent_name or "tool_layer",
            "module": candidate.get("module"),
            "request_type": "scraped_candidate_review",
            "status": "open",
            "title": f"Review scraped candidate: {title}",
            "summary": candidate.get("raw_summary") or candidate.get("source_url") or "Review this discovered research candidate.",
            "request_origin": "tool_layer",
            "is_test": bool(candidate.get("is_mock")),
            "severity": "needs_review",
            "user_facing_summary": "Review this read-only research candidate before approving or converting it locally.",
            "technical_reason": "Created by SignalForge Tool Layer v1. No outbound action was taken.",
            "target": str(candidate_id),
            "target_type": "scraped_candidate",
            "linked_candidate_id": str(candidate_id),
            "source_url": candidate.get("source_url"),
            "confidence": candidate.get("confidence"),
            "source_quality": candidate.get("source_quality"),
            "created_at": now,
            "resolved_at": None,
            "simulation_only": True,
        }
        result = db.approval_requests.insert_one(request)
        return str(result.inserted_id)

    def insert_candidates(
        self,
        db,
        candidates: list[dict[str, Any]],
        tool_run_id: str | None = None,
        agent_name: str | None = None,
        agent_run_id: str | None = None,
        create_approval: bool = True,
    ) -> list[str]:
        if db is None or not candidates:
            return []
        ids = []
        for candidate in candidates:
            document = self.candidate_document(candidate, tool_run_id, agent_run_id)
            result = db.scraped_candidates.insert_one(document)
            candidate_id = str(result.inserted_id if isinstance(result.inserted_id, ObjectId) else result.inserted_id)
            if create_approval:
                approval_id = self.create_candidate_approval(db, candidate_id, document, agent_name, agent_run_id)
                if approval_id:
                    db.scraped_candidates.update_one({"_id": result.inserted_id}, {"$set": {"approval_request_id": approval_id}})
            ids.append(candidate_id)
        return ids
