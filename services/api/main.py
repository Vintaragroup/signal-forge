import os
import re
import inspect
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from bson import ObjectId
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pymongo import MongoClient

from core.constants import MESSAGE_REVIEW_DECISIONS, OPEN_DEAL_OUTCOMES, VALID_MODULES

try:
    from prompt_generator import (
        generate_prompt as _generate_visual_prompt,
        PROMPT_TYPES as VISUAL_PROMPT_TYPES,
        GENERATION_ENGINES,
    )
except Exception:  # pragma: no cover — import guard for test isolation
    _generate_visual_prompt = None  # type: ignore[assignment]
    VISUAL_PROMPT_TYPES = frozenset()
    GENERATION_ENGINES = frozenset()

try:
    from agents.base_agent import SUPPORTED_MODULES
    from agents.content_agent import ContentAgent
    from agents.fan_engagement_agent import FanEngagementAgent
    from agents.followup_agent import FollowupAgent
    from agents.outreach_agent import OutreachAgent
except Exception:
    SUPPORTED_MODULES = {}
    OutreachAgent = None
    ContentAgent = None
    FanEngagementAgent = None
    FollowupAgent = None


SERVICE_NAME = "api"
SERVICE_DESCRIPTION = "Local-first SignalForge dashboard API."
PROJECT_ROOT = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name == "services" else Path.cwd()
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"
DEFAULT_VAULT_PATH = Path(os.getenv("VAULT_PATH", "/vault"))
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
GPT_SAFETY_MODE = "local_human_review_only"
VALID_MESSAGE_DECISIONS = MESSAGE_REVIEW_DECISIONS

AGENT_CLASSES = {
    "outreach": OutreachAgent,
    "content": ContentAgent,
    "fan_engagement": FanEngagementAgent,
    "followup": FollowupAgent,
}

AGENT_TASK_TYPES = {
    "outreach": "run_outreach",
    "followup": "run_followup",
    "content": "generate_content",
    "fan_engagement": "engage_fans",
}

AGENT_TASK_PRIORITY_ORDER = {"high": 3, "normal": 2, "low": 1}


class MessageReviewRequest(BaseModel):
    decision: Literal["approve", "reject", "revise"]
    note: str = ""


class AgentRunRequest(BaseModel):
    agent: Literal["outreach", "content", "fan_engagement", "followup"]
    module: str
    dry_run: bool = True
    limit: int = 10
    use_tools: bool = False
    workspace_slug: str = ""


class AgentTaskCreateRequest(BaseModel):
    agent_name: Literal["outreach", "followup", "content", "fan_engagement"]
    module: str
    task_type: Literal["run_outreach", "run_followup", "generate_content", "engage_fans"] | None = None
    priority: Literal["low", "normal", "high"] = "normal"
    input_config: dict[str, Any] = Field(default_factory=dict)
    workspace_slug: str = ""


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "reject", "convert_to_draft", "needs_revision"]
    note: str = ""


class ScrapedCandidateDecisionRequest(BaseModel):
    decision: Literal["approve", "reject", "convert_to_contact", "convert_to_lead"]
    note: str = ""


class WebSearchToolRunRequest(BaseModel):
    query: str
    module: str = "contractor_growth"
    location: str = ""
    limit: int = Field(default=2, ge=1, le=25)


class CandidateImportRequest(BaseModel):
    module: str = "contractor_growth"
    source_label: str = "manual_upload"
    csv_path: str = ""
    csv_text: str = ""
    workspace_slug: str = ""


class BulkCandidateActionRequest(BaseModel):
    action: Literal["approve", "reject", "convert_to_contact", "convert_to_lead"]
    candidate_ids: list[str]
    note: str = ""


class WorkspaceCreateRequest(BaseModel):
    name: str
    type: Literal["internal", "client", "demo", "test"] = "client"
    module: str = ""
    notes: str = ""


class WorkspaceStatusRequest(BaseModel):
    status: Literal["active", "paused", "archived"]


# ---------------------------------------------------------------------------
# Creative Studio models
# ---------------------------------------------------------------------------

class ContentBriefCreateRequest(BaseModel):
    workspace_slug: str = ""
    module: str = ""
    campaign_name: str = ""
    audience: str = ""
    platform: str = ""
    goal: str = ""
    offer: str = ""
    tone: str = ""
    notes: str = ""
    status: Literal["draft", "needs_review", "approved", "rejected"] = "draft"


class ContentDraftCreateRequest(BaseModel):
    workspace_slug: str = ""
    module: str = ""
    brief_id: str = ""
    platform: str = ""
    content_type: Literal["post", "caption", "carousel", "reel_script", "ad_copy"] = "post"
    title: str = ""
    body: str = ""
    hashtags: list[str] = Field(default_factory=list)
    call_to_action: str = ""
    status: Literal["needs_review", "approved", "rejected"] = "needs_review"
    generated_by_agent: str = ""
    agent_run_id: str = ""
    selected_model: str = ""
    routing_reason: str = ""
    complexity: str = ""


class ContentDraftReviewRequest(BaseModel):
    decision: Literal["approve", "reject", "revise"]
    note: str = ""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def vault_path() -> Path:
    return Path(os.getenv("VAULT_PATH", str(DEFAULT_VAULT_PATH)))


def mongo_uri() -> str:
    return os.getenv("MONGO_URI", DEFAULT_MONGO_URI)


def get_client() -> MongoClient:
    return MongoClient(mongo_uri(), serverSelectionTimeoutMS=3000)


def get_database(client: MongoClient):
    try:
        return client.get_default_database()
    except Exception:
        return client["signalforge"]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "untitled"


def is_object_id(value: str) -> bool:
    return ObjectId.is_valid(value)


def serialize(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    return value


def module_for_lead(lead: dict) -> str:
    module = clean_text(lead.get("module"))
    if module:
        return module
    engine = clean_text(lead.get("engine")).lower()
    business_type = clean_text(lead.get("business_type")).lower()
    if "contractor" in engine or "contractor" in business_type:
        return "contractor_growth"
    return "unknown"


def score_for(record: dict) -> int:
    score = record.get("contact_score", record.get("lead_score", record.get("score", 0)))
    return int(score) if isinstance(score, (int, float)) else 0


def status_value(record: dict) -> str:
    return (
        clean_text(record.get("contact_status"))
        or clean_text(record.get("outreach_status"))
        or clean_text(record.get("review_status"))
        or "not_set"
    )


def numeric_value(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def vault_status() -> dict:
    path = vault_path()
    return {
        "path": str(path),
        "exists": path.exists(),
        "dashboard_exists": (path / "00_Dashboard.md").exists(),
    }


def mongo_status() -> dict:
    try:
        client = get_client()
        client.admin.command("ping")
        return {"ready": True, "detail": "ping ok"}
    except Exception as exc:
        return {"ready": False, "detail": f"{exc.__class__.__name__}: {exc}"}
    finally:
        try:
            client.close()
        except Exception:
            pass


def env_enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def gpt_runtime_status() -> dict:
    return {
        "enabled": env_enabled(os.getenv("GPT_AGENT_ENABLED", "false")),
        "model": clean_text(os.getenv("OPENAI_MODEL")) or DEFAULT_OPENAI_MODEL,
        "has_api_key": bool(clean_text(os.getenv("OPENAI_API_KEY"))),
        "safety_mode": GPT_SAFETY_MODE,
        "model_routing_enabled": env_enabled(os.getenv("OPENAI_MODEL_ROUTING_ENABLED", "false")),
        "agent_model": clean_text(os.getenv("OPENAI_AGENT_MODEL")) or DEFAULT_OPENAI_MODEL,
        "draft_model": clean_text(os.getenv("OPENAI_DRAFT_MODEL")) or DEFAULT_OPENAI_MODEL,
        "review_model": clean_text(os.getenv("OPENAI_REVIEW_MODEL")) or DEFAULT_OPENAI_MODEL,
        "fallback_model": clean_text(os.getenv("OPENAI_FALLBACK_MODEL")) or DEFAULT_OPENAI_MODEL,
    }


def gpt_client_available() -> bool:
    try:
        from agents import gpt_client  # noqa: F401
    except Exception:
        return False
    return True


def safe_gpt_step_summary(step: dict) -> dict:
    output = step.get("output") or {}
    return {
        "run_id": step.get("run_id"),
        "agent_name": step.get("agent_name"),
        "module": step.get("module"),
        "step_name": step.get("step_name"),
        "status": step.get("status"),
        "timestamp": step.get("timestamp"),
        "enabled": output.get("enabled"),
        "used_gpt": output.get("used_gpt"),
        "confidence": output.get("confidence"),
        "reasoning_summary": clean_text(output.get("reasoning_summary")),
        "output_length": output.get("output_length"),
        "error": clean_text(output.get("error")),
        "selected_model": clean_text(output.get("selected_model")),
        "routing_reason": clean_text(output.get("routing_reason")),
        "complexity": clean_text(output.get("complexity")),
    }


def safe_gpt_approval_error_summary(request: dict) -> dict:
    apply_approval_defaults(request)
    return {
        "_id": request.get("_id"),
        "run_id": request.get("run_id"),
        "agent_name": request.get("agent_name"),
        "module": request.get("module"),
        "request_type": request.get("request_type"),
        "status": request.get("status"),
        "title": request.get("title"),
        "severity": request.get("severity"),
        "request_origin": request.get("request_origin"),
        "user_facing_summary": request.get("user_facing_summary"),
        "technical_reason": request.get("technical_reason"),
        "created_at": request.get("created_at"),
    }


def gpt_diagnostics_status(db=None) -> dict:
    runtime = gpt_runtime_status()
    diagnostics = {
        "gpt_agent_enabled": runtime["enabled"],
        "openai_model": runtime["model"],
        "has_api_key": runtime["has_api_key"],
        "api_key_source": "env" if runtime["has_api_key"] else "missing",
        "client_available": gpt_client_available(),
        "model_routing_enabled": runtime["model_routing_enabled"],
        "agent_model": runtime["agent_model"],
        "draft_model": runtime["draft_model"],
        "review_model": runtime["review_model"],
        "fallback_model": runtime["fallback_model"],
        "last_gpt_error_summary": None,
        "last_gpt_error_at": None,
        "last_successful_gpt_call_at": None,
        "recent_gpt_agent_steps": [],
        "recent_system_approval_errors": [],
        "safety_mode": GPT_SAFETY_MODE,
    }
    if db is None:
        return diagnostics

    gpt_steps = list(db.agent_steps.find({"step_name": {"$regex": "^gpt_"}}).sort([("timestamp", -1)]).limit(10))
    diagnostics["recent_gpt_agent_steps"] = [safe_gpt_step_summary(step) for step in gpt_steps]

    error_steps = [step for step in gpt_steps if clean_text((step.get("output") or {}).get("error")) or step.get("status") == "failed"]
    if error_steps:
        latest_error = error_steps[0]
        output = latest_error.get("output") or {}
        diagnostics["last_gpt_error_summary"] = clean_text(output.get("error") or output.get("reasoning_summary") or latest_error.get("status"))
        diagnostics["last_gpt_error_at"] = latest_error.get("timestamp")

    success_step = next((step for step in gpt_steps if (step.get("output") or {}).get("used_gpt") is True and not clean_text((step.get("output") or {}).get("error"))), None)
    if success_step:
        diagnostics["last_successful_gpt_call_at"] = success_step.get("timestamp")

    approval_errors = list(
        db.approval_requests.find(
            {
                "$or": [
                    {"request_origin": "system"},
                    {"severity": "error"},
                    {"request_type": {"$regex": "^gpt_"}, "severity": "error"},
                ]
            }
        )
        .sort([("created_at", -1)])
        .limit(10)
    )
    diagnostics["recent_system_approval_errors"] = [safe_gpt_approval_error_summary(request) for request in approval_errors]
    if diagnostics["last_gpt_error_summary"] is None and approval_errors:
        latest_approval = approval_errors[0]
        diagnostics["last_gpt_error_summary"] = clean_text(latest_approval.get("technical_reason") or latest_approval.get("user_facing_summary") or latest_approval.get("summary"))
        diagnostics["last_gpt_error_at"] = latest_approval.get("created_at")
    return diagnostics


def count_response_events(messages: list[dict], outcome: str) -> int:
    total = 0
    for message in messages:
        events = message.get("response_events") or []
        matches = [event for event in events if event.get("outcome") == outcome]
        if matches:
            total += len(matches)
        elif message.get("response_status") == outcome:
            total += 1
    return total


def latest_agent_logs(limit: int = 8) -> list[dict]:
    logs_dir = vault_path() / "logs" / "agents"
    if not logs_dir.exists():
        return []

    logs = []
    for path in sorted(logs_dir.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        planned = len(re.findall(r"^\| \d+ \|", text, flags=re.MULTILINE))
        logs.append(
            {
                "name": path.stem,
                "path": str(path.relative_to(vault_path())),
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                "planned_actions": planned,
                "excerpt": "\n".join(text.splitlines()[:18]),
            }
        )
    return logs


def latest_agent_runs(db, limit: int = 25) -> list[dict]:
    return list(db.agent_runs.find({}).sort([("started_at", -1)]).limit(limit))


def find_agent_task(db, task_id: str) -> dict | None:
    query: dict[str, Any] = {"_id": task_id}
    if ObjectId.is_valid(task_id):
        query = {"$or": [{"_id": ObjectId(task_id)}, {"_id": task_id}]}
    return db.agent_tasks.find_one(query)


def validate_agent_task(agent_name: str, module: str) -> None:
    if agent_name not in AGENT_CLASSES or AGENT_CLASSES.get(agent_name) is None:
        raise HTTPException(status_code=400, detail="Unsupported agent.")
    if SUPPORTED_MODULES and module not in SUPPORTED_MODULES:
        raise HTTPException(status_code=400, detail="Unsupported module.")


def validate_agent_task_type(agent_name: str, task_type: str) -> None:
    expected = AGENT_TASK_TYPES.get(agent_name)
    if expected and task_type != expected:
        raise HTTPException(status_code=400, detail=f"Task type '{task_type}' is not supported for agent '{agent_name}'.")


def agent_task_query(status: str, agent_name: str, module: str) -> dict:
    query: dict[str, Any] = {}
    if status:
        query["status"] = status
    if agent_name:
        query["agent_name"] = agent_name
    if module:
        query["module"] = module
    return query


def sort_agent_tasks(records: list[dict]) -> list[dict]:
    return sorted(
        records,
        key=lambda task: (AGENT_TASK_PRIORITY_ORDER.get(clean_text(task.get("priority")), 0), str(task.get("created_at") or "")),
        reverse=True,
    )


def report_file(path: Path, label: str) -> dict:
    exists = path.exists()
    content = path.read_text(encoding="utf-8", errors="ignore") if exists else ""
    return {
        "label": label,
        "path": str(path.relative_to(vault_path())) if exists else str(path),
        "exists": exists,
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat() if exists else None,
        "content": content,
        "excerpt": "\n".join(content.splitlines()[:40]),
    }


def review_status_for(decision: str) -> str:
    if decision == "approve":
        return "approved"
    if decision == "reject":
        return "rejected"
    return "needs_revision"


def find_message_draft(db, identifier: str) -> dict | None:
    raw = identifier.strip()
    stem = Path(raw).stem
    slug = slugify(stem)
    escaped_raw = re.escape(raw)
    escaped_slug = re.escape(slug)
    conditions = [
        {"draft_key": raw},
        {"draft_key": slug},
        {"message_note_path": raw},
        {"message_note_path": {"$regex": escaped_raw}},
        {"message_note_path": {"$regex": escaped_slug}},
    ]
    if is_object_id(raw):
        conditions.insert(0, {"_id": ObjectId(raw)})
    return db.message_drafts.find_one({"$or": conditions}, sort=[("updated_at", -1)])


def object_id_or_raw(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    raw = str(value)
    values: list[Any] = [raw]
    if ObjectId.is_valid(raw):
        values.append(ObjectId(raw))
    return values


def message_timeline(message: dict, linked_deal: dict | None = None) -> list[dict]:
    timeline = []
    created_at = message.get("created_at")
    if created_at:
        timeline.append(
            {
                "event": "drafted",
                "status": message.get("review_status", "needs_review"),
                "timestamp": created_at,
                "note": message.get("subject_line", ""),
            }
        )
    for event in message.get("review_events") or []:
        timeline.append(
            {
                "event": "reviewed",
                "status": event.get("review_status") or event.get("decision"),
                "timestamp": event.get("reviewed_at"),
                "note": event.get("note", ""),
            }
        )
    for event in message.get("send_events") or []:
        timeline.append(
            {
                "event": "manual_send_logged",
                "status": event.get("channel") or "sent",
                "timestamp": event.get("sent_at"),
                "note": event.get("note", ""),
            }
        )
    for event in message.get("response_events") or []:
        timeline.append(
            {
                "event": "response_logged",
                "status": event.get("outcome"),
                "timestamp": event.get("responded_at"),
                "note": event.get("note", ""),
            }
        )
    if linked_deal:
        timeline.append(
            {
                "event": "deal_outcome",
                "status": linked_deal.get("outcome") or linked_deal.get("deal_status"),
                "timestamp": linked_deal.get("updated_at") or linked_deal.get("created_at"),
                "note": linked_deal.get("note", ""),
            }
        )
    return sorted(timeline, key=lambda item: str(item.get("timestamp") or ""))


# ---------------------------------------------------------------------------
# Workspace data quality helpers
# ---------------------------------------------------------------------------

_MOCK_SOURCES = {
    "mock",
    "demo",
    "synthetic",
    "contractor_test_campaign",
    "contractor_test_campaign_v1",
    "gpt_runtime_test_campaign_v1",
    "tool_layer_review",
}

_MOCK_PATTERN = re.compile(
    r"\bmock\b|\bdemo\b|\bsynthetic\b|\btest\b|\bsample\b"
    r"|contractor_test_campaign|module-v\d|module\d+-test"
    r"|gpt_runtime_test|manual_contractor_test_cli|tool_layer_review",
    re.IGNORECASE,
)

_MOCK_SCAN_FIELDS = ("source", "source_label", "run_id", "name", "notes", "company", "company_name")


def _is_mock_record(doc: dict) -> bool:
    if doc.get("is_demo") or doc.get("is_test"):
        return True
    for field in _MOCK_SCAN_FIELDS:
        value = doc.get(field)
        if isinstance(value, str) and _MOCK_PATTERN.search(value):
            return True
    return False


def _is_legacy_record(doc: dict) -> bool:
    ws = doc.get("workspace_slug")
    return not ws or not isinstance(ws, str) or ws.strip() == ""


def apply_real_mode_filters(
    records: list[dict],
    *,
    workspace_slug: str = "",
    include_legacy: bool = False,
    include_test: bool = False,
) -> list[dict]:
    """In Real Mode (workspace_slug provided), exclude legacy and mock records unless opted in."""
    if not workspace_slug:
        # No workspace filter active — show everything as before
        return records
    result = records
    if not include_legacy:
        result = [r for r in result if not _is_legacy_record(r)]
    if not include_test:
        result = [r for r in result if not _is_mock_record(r)]
        result = [r for r in result if r.get("workspace_slug") not in ("demo", "synthetic")]
    return result


def enrich_messages(records: list[dict], db) -> list[dict]:
    contacts = list(db.contacts.find({}))
    leads = list(db.leads.find({}))
    deals = list(db.deals.find({}))
    contacts_by_key = {}
    for contact in contacts:
        for key in (str(contact.get("_id")), contact.get("contact_key"), contact.get("email")):
            if key:
                contacts_by_key[str(key)] = contact
    leads_by_key = {}
    for lead in leads:
        for key in (str(lead.get("_id")), lead.get("company_slug")):
            if key:
                leads_by_key[str(key)] = lead
    deals_by_key = defaultdict(list)
    for deal in deals:
        for key in (deal.get("message_draft_id"), deal.get("contact_id"), deal.get("lead_id")):
            if key:
                deals_by_key[str(key)].append(deal)

    enriched = []
    for message in records:
        target_id = str(message.get("target_id") or "")
        target_key = str(message.get("target_key") or "")
        message_id = str(message.get("_id"))
        linked_contact = contacts_by_key.get(target_id) or contacts_by_key.get(target_key)
        linked_lead = leads_by_key.get(target_id) or leads_by_key.get(target_key)
        raw_linked_deals = deals_by_key.get(message_id, []) + deals_by_key.get(target_id, []) + deals_by_key.get(target_key, [])
        linked_deals = list({str(deal.get("_id")): deal for deal in raw_linked_deals}.values())
        linked_deal = linked_deals[0] if linked_deals else None
        message["linked_contact"] = linked_contact
        message["linked_lead"] = linked_lead
        message["linked_deal"] = linked_deal
        message["linked_deals"] = linked_deals
        message["timeline"] = message_timeline(message, linked_deal)
        enriched.append(message)
    return enriched


def enrich_approval_requests(records: list[dict], db) -> list[dict]:
    enriched = []
    for request in records:
        apply_approval_defaults(request)
        target = clean_text(request.get("target"))
        linked_target_id = clean_text(request.get("linked_target_id"))
        target_values = [value for raw in (target, linked_target_id) for value in object_id_or_raw(raw)]
        request_type = clean_text(request.get("request_type"))
        target_type = clean_text(request.get("target_type"))

        linked_contact = None
        linked_lead = None
        linked_message = None

        if target_type == "contact" or request_type.startswith("gpt_"):
            contact_conditions = []
            for value in target_values:
                if isinstance(value, ObjectId):
                    contact_conditions.append({"_id": value})
                else:
                    contact_conditions.extend([{"contact_key": value}, {"email": value}])
            if contact_conditions:
                linked_contact = db.contacts.find_one({"$or": contact_conditions})

        if target_type == "lead" or request_type.startswith("gpt_"):
            lead_conditions = []
            for value in target_values:
                if isinstance(value, ObjectId):
                    lead_conditions.append({"_id": value})
                else:
                    lead_conditions.append({"company_slug": value})
            if lead_conditions:
                linked_lead = db.leads.find_one({"$or": lead_conditions})

        message_id = clean_text(request.get("message_draft_id") or request.get("draft_key"))
        if not message_id and target_type == "message":
            message_id = target or linked_target_id
        if message_id:
            linked_message = find_message_draft(db, message_id)

        request["linked_contact"] = linked_contact
        request["linked_lead"] = linked_lead
        request["linked_message"] = linked_message
        enriched.append(request)
    return enriched


def apply_approval_defaults(request: dict) -> dict:
    request_type = clean_text(request.get("request_type"))
    reason = clean_text(request.get("reason_for_review") or request.get("summary") or request.get("technical_reason"))
    if "request_origin" not in request:
        request["request_origin"] = "gpt" if request_type.startswith("gpt_") else "agent"
    if "is_test" not in request:
        request["is_test"] = request.get("request_origin") == "test"
    if "severity" not in request:
        request["severity"] = "error" if request.get("request_origin") == "system" else "needs_review"
    if "user_facing_summary" not in request:
        request["user_facing_summary"] = reason or "Human review is needed before the operator takes any manual action."
    if "technical_reason" not in request:
        request["technical_reason"] = reason or "No technical reason recorded."
    return request


def approval_matches_view(request: dict, view: str) -> bool:
    request = apply_approval_defaults(request)
    origin = clean_text(request.get("request_origin"))
    request_type = clean_text(request.get("request_type"))
    severity = clean_text(request.get("severity"))
    is_test = request.get("is_test") is True
    if view == "all":
        return True
    if view == "gpt":
        return not is_test and (origin == "gpt" or request_type.startswith("gpt_")) and severity != "error"
    if view == "system":
        return not is_test and (origin == "system" or severity == "error")
    if view == "test":
        return is_test or origin == "test"
    return not is_test and origin not in {"system", "test"} and severity != "error"


def find_approval_request(db, approval_id: str) -> dict | None:
    query: dict[str, Any] = {"_id": approval_id}
    if ObjectId.is_valid(approval_id):
        query = {"$or": [{"_id": ObjectId(approval_id)}, {"_id": approval_id}]}
    return db.approval_requests.find_one(query)


def approval_status_for_decision(decision: str) -> str:
    if decision == "approve":
        return "approved"
    if decision == "reject":
        return "rejected"
    if decision == "convert_to_draft":
        return "converted_to_draft"
    return "needs_revision"


def approval_record_label(record: dict | None) -> str:
    if not record:
        return "Unknown"
    return clean_text(record.get("name") or record.get("recipient_name") or record.get("company") or record.get("company_name")) or "Unknown"


def create_message_draft_from_approval(db, request: dict, note: str, decided_at: datetime) -> dict:
    existing = db.message_drafts.find_one({"approval_request_id": str(request.get("_id"))})
    if existing:
        return existing

    enriched = enrich_approval_requests([dict(request)], db)[0]
    linked_contact = enriched.get("linked_contact")
    linked_lead = enriched.get("linked_lead")
    target_type = clean_text(request.get("target_type")) or ("contact" if linked_contact else "lead" if linked_lead else "approval")
    target_record = linked_contact or linked_lead or {}
    recipient = approval_record_label(target_record) if target_record else clean_text(request.get("target")) or "Approval Request"
    target_id = clean_text(target_record.get("_id") if target_record else request.get("linked_target_id") or request.get("target"))
    target_key = clean_text(target_record.get("contact_key") or target_record.get("company_slug") if target_record else request.get("target"))
    draft_key = slugify(f"approval-{request.get('_id')}-{recipient}")
    reasoning = clean_text(request.get("reason_for_review") or request.get("summary"))
    body_parts = [
        "Converted from approval request for human review.",
        f"Request type: {clean_text(request.get('request_type')) or 'approval_request'}",
    ]
    if reasoning:
        body_parts.append(f"Reasoning summary: {reasoning}")
    if note:
        body_parts.append(f"Operator note: {note}")
    body_parts.append("No message has been sent by SignalForge.")
    draft = {
        "draft_key": draft_key,
        "module": clean_text(request.get("module")),
        "target_type": target_type,
        "target_id": target_id,
        "target_key": target_key,
        "recipient_name": recipient,
        "company": clean_text(target_record.get("company") or target_record.get("company_name") if target_record else request.get("target")),
        "subject_line": f"Review converted approval for {recipient}",
        "message_body": "\n\n".join(body_parts),
        "review_status": "needs_review",
        "send_status": "not_sent",
        "source": "approval_queue",
        "approval_request_id": str(request.get("_id")),
        "generated_by_agent": clean_text(request.get("agent_name")),
        "agent_run_id": clean_text(request.get("run_id")),
        "agent_step_name": clean_text(request.get("agent_step_name")),
        "gpt_confidence": request.get("gpt_confidence"),
        "gpt_reasoning_summary": reasoning,
        "created_at": decided_at,
        "updated_at": decided_at,
    }
    db.message_drafts.insert_one(draft)
    return draft


def create_artifact_draft_from_approval(db, request: dict, note: str, decided_at: datetime) -> dict:
    existing = db.agent_artifacts.find_one({"approval_request_id": str(request.get("_id")), "artifact_type": "approval_queue_draft"})
    if existing:
        return existing
    artifact = {
        "run_id": clean_text(request.get("run_id")),
        "agent_name": clean_text(request.get("agent_name")),
        "module": clean_text(request.get("module")),
        "artifact_type": "approval_queue_draft",
        "label": f"Converted approval draft: {clean_text(request.get('title')) or clean_text(request.get('request_type'))}",
        "approval_request_id": str(request.get("_id")),
        "review_status": "needs_review",
        "source": "approval_queue",
        "content": {
            "request_type": request.get("request_type"),
            "title": request.get("title"),
            "summary": request.get("summary"),
            "reasoning_summary": request.get("reason_for_review") or request.get("summary"),
            "operator_note": note,
            "gpt_confidence": request.get("gpt_confidence"),
            "generated_by_agent": request.get("generated_by_agent") or request.get("agent_name"),
            "agent_run_id": request.get("agent_run_id") or request.get("run_id"),
            "agent_step_name": request.get("agent_step_name"),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        },
        "created_at": decided_at,
    }
    db.agent_artifacts.insert_one(artifact)
    return artifact


def convert_approval_to_draft(db, request: dict, note: str, decided_at: datetime) -> tuple[str, dict]:
    request_type = clean_text(request.get("request_type"))
    target_type = clean_text(request.get("target_type"))
    if request_type == "gpt_message_generation_review" or target_type in {"contact", "lead", "message"}:
        return "message_draft", create_message_draft_from_approval(db, request, note, decided_at)
    return "artifact_draft", create_artifact_draft_from_approval(db, request, note, decided_at)


def instantiate_agent(agent_cls, *, module: str, dry_run: bool, mongo_uri: str, vault_path: Path, limit: int, use_tools: bool = False, workspace_slug: str = ""):
    kwargs = {
        "module": module,
        "dry_run": dry_run,
        "mongo_uri": mongo_uri,
        "vault_path": vault_path,
        "limit": limit,
    }
    try:
        parameters = inspect.signature(agent_cls).parameters
        if "use_tools" in parameters:
            kwargs["use_tools"] = use_tools
        if "workspace_slug" in parameters:
            kwargs["workspace_slug"] = workspace_slug
    except (TypeError, ValueError):
        pass
    return agent_cls(**kwargs)


def find_scraped_candidate(db, candidate_id: str) -> dict | None:
    query: dict[str, Any] = {"_id": candidate_id}
    if ObjectId.is_valid(candidate_id):
        query = {"$or": [{"_id": ObjectId(candidate_id)}, {"_id": candidate_id}]}
    return db.scraped_candidates.find_one(query)


def find_tool_run(db, run_id: str) -> dict | None:
    query: dict[str, Any] = {"_id": run_id}
    if ObjectId.is_valid(run_id):
        query = {"$or": [{"_id": ObjectId(run_id)}, {"_id": run_id}]}
    return db.tool_runs.find_one(query)


def candidate_display_name(candidate: dict) -> str:
    return clean_text(candidate.get("company") or candidate.get("name") or candidate.get("source_url")) or "Research Candidate"


def create_contact_from_candidate(db, candidate: dict, decided_at: datetime) -> dict:
    candidate_id = str(candidate.get("_id"))
    existing = db.contacts.find_one({"source_candidate_id": candidate_id})
    if existing:
        return existing
    company = candidate_display_name(candidate)
    contact = {
        "contact_key": slugify(f"research-{candidate_id}-{company}"),
        "name": company,
        "company": company,
        "email": clean_text(candidate.get("email")),
        "phone": clean_text(candidate.get("phone")),
        "city": clean_text(candidate.get("city")),
        "state": clean_text(candidate.get("state")),
        "module": clean_text(candidate.get("module")) or "contractor_growth",
        "source": "tool_layer_review",
        "source_url": clean_text(candidate.get("source_url")),
        "source_candidate_id": candidate_id,
        "contact_status": "needs_review",
        "segment": "research_candidate",
        "notes": "Converted from scraped candidate by explicit operator decision. No outbound action taken.",
        "confidence": candidate.get("confidence"),
        "source_quality": candidate.get("source_quality"),
        "created_at": decided_at,
        "updated_at": decided_at,
    }
    if candidate.get("workspace_slug"):
        contact["workspace_slug"] = candidate["workspace_slug"]
    result = db.contacts.insert_one(contact)
    contact["_id"] = result.inserted_id
    return contact


def create_lead_from_candidate(db, candidate: dict, decided_at: datetime) -> dict:
    candidate_id = str(candidate.get("_id"))
    existing = db.leads.find_one({"source_candidate_id": candidate_id})
    if existing:
        return existing
    company = candidate_display_name(candidate)
    lead = {
        "company_slug": slugify(f"research-{company}"),
        "company_name": company,
        "business_type": clean_text(candidate.get("service_category")) or "unknown",
        "location": ", ".join(part for part in [clean_text(candidate.get("city")), clean_text(candidate.get("state"))] if part),
        "module": clean_text(candidate.get("module")) or "contractor_growth",
        "source": "tool_layer_review",
        "source_url": clean_text(candidate.get("source_url")),
        "source_candidate_id": candidate_id,
        "review_status": "needs_review",
        "outreach_status": "not_started",
        "lead_score": int(float(candidate.get("confidence") or 0) * 100),
        "score": int(float(candidate.get("confidence") or 0) * 100),
        "priority_reason": "Converted from scraped candidate by explicit operator decision. No outbound action taken.",
        "source_quality": candidate.get("source_quality"),
        "created_at": decided_at,
        "updated_at": decided_at,
    }
    if candidate.get("workspace_slug"):
        lead["workspace_slug"] = candidate["workspace_slug"]
    result = db.leads.insert_one(lead)
    lead["_id"] = result.inserted_id
    return lead


def append_message_review_log(draft: dict, decision: str, note: str, reviewed_at: datetime) -> None:
    relative_path = draft.get("message_note_path")
    if not relative_path:
        return

    path = vault_path() / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"# Message Draft: {draft.get('recipient_name', 'Unknown')}\n", encoding="utf-8")

    note_line = f"- Note: {note}\n" if note else ""
    review_status = review_status_for(decision)
    entry = f"""

## Message Review Log

### {reviewed_at.isoformat()}

- Decision: {decision}
- Review status: {review_status}
- Send status: {draft.get("send_status", "not_sent") if decision != "approve" else "not_sent"}
- Draft ID: {draft["_id"]}
- Recipient: {draft.get("recipient_name", "")}
{note_line}- No message sent.
"""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(entry)


def dashboard_tasks(leads: list[dict], contacts: list[dict], messages: list[dict], deals: list[dict]) -> list[dict]:
    tasks = []
    needs_review = sum(1 for message in messages if message.get("review_status") == "needs_review")
    if needs_review:
        tasks.append({"label": "Review message drafts", "count": needs_review, "tone": "amber"})

    followups = sum(1 for lead in leads if lead.get("outreach_status") == "follow_up_needed")
    if followups:
        tasks.append({"label": "Follow up with leads", "count": followups, "tone": "blue"})

    research = sum(1 for lead in leads if lead.get("review_status") == "research_more")
    if research:
        tasks.append({"label": "Research leads", "count": research, "tone": "purple"})

    nurture = sum(1 for contact in contacts if contact.get("segment") == "nurture" or contact.get("deal_outcome") == "nurture")
    if nurture:
        tasks.append({"label": "Nurture contacts", "count": nurture, "tone": "green"})

    open_deals = sum(1 for deal in deals if deal.get("outcome") in ("proposal_sent", "negotiation"))
    if open_deals:
        tasks.append({"label": "Advance open deals", "count": open_deals, "tone": "blue"})

    if not tasks:
        tasks.append({"label": "No urgent operator tasks", "count": 0, "tone": "green"})
    return tasks


def next_action_counts(contacts: list[dict], messages: list[dict], deals: list[dict]) -> list[dict]:
    open_outcomes = {*OPEN_DEAL_OUTCOMES, "nurture"}
    return [
        {
            "key": "contacts_needing_scoring",
            "label": "Contacts needing scoring",
            "count": sum(1 for contact in contacts if not contact.get("contact_score") or not contact.get("segment")),
            "page": "pipeline",
            "filters": {"type": "contact", "segment": "unscored"},
            "helper": "Run contact scoring before drafting messages.",
            "tone": "blue",
        },
        {
            "key": "drafts_needing_review",
            "label": "Drafts needing review",
            "count": sum(1 for message in messages if message.get("review_status") == "needs_review"),
            "page": "messages",
            "filters": {"review_status": "needs_review"},
            "helper": "Approve, revise, or reject before any manual send.",
            "tone": "amber",
        },
        {
            "key": "approved_not_sent",
            "label": "Approved messages not sent",
            "count": sum(1 for message in messages if message.get("review_status") == "approved" and message.get("send_status") == "not_sent"),
            "page": "messages",
            "filters": {"review_status": "approved", "send_status": "not_sent"},
            "helper": "Ready for a human to send outside SignalForge.",
            "tone": "green",
        },
        {
            "key": "sent_no_response",
            "label": "Sent messages with no response",
            "count": sum(1 for message in messages if message.get("send_status") == "sent" and not message.get("response_status")),
            "page": "messages",
            "filters": {"send_status": "sent", "response_status": "not_set"},
            "helper": "Check whether manual follow-up is needed.",
            "tone": "purple",
        },
        {
            "key": "interested_responses",
            "label": "Interested responses",
            "count": sum(1 for message in messages if message.get("response_status") in {"interested", "requested_info"}),
            "page": "messages",
            "filters": {"response_status": "interested"},
            "helper": "Prepare a next step or meeting.",
            "tone": "blue",
        },
        {
            "key": "call_booked_responses",
            "label": "Call-booked responses / meeting prep",
            "count": sum(1 for message in messages if message.get("response_status") == "call_booked"),
            "page": "messages",
            "filters": {"response_status": "call_booked"},
            "helper": "Generate or review meeting prep.",
            "tone": "green",
        },
        {
            "key": "open_deals",
            "label": "Open deals",
            "count": sum(1 for deal in deals if (deal.get("outcome") or deal.get("deal_status")) in open_outcomes),
            "page": "deals",
            "filters": {"outcome": "open"},
            "helper": "Advance proposal, negotiation, or nurture opportunities.",
            "tone": "amber",
        },
    ]


def top_modules(contacts: list[dict], leads: list[dict], messages: list[dict], deals: list[dict]) -> list[dict]:
    stats: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for contact in contacts:
        stats[clean_text(contact.get("module")) or "unknown"]["contacts"] += 1
    for lead in leads:
        stats[module_for_lead(lead)]["leads"] += 1
    for message in messages:
        module = clean_text(message.get("module")) or "unknown"
        stats[module]["messages"] += 1
        if message.get("send_status") == "sent":
            stats[module]["sent"] += 1
        if message.get("response_status") == "call_booked":
            stats[module]["meetings"] += 1
    for deal in deals:
        module = clean_text(deal.get("module")) or "unknown"
        stats[module]["deals"] += 1
        if deal.get("outcome") == "closed_won" or deal.get("deal_status") == "closed_won":
            stats[module]["closed_won"] += 1
            stats[module]["revenue"] += numeric_value(deal.get("deal_value"))

    ranked = sorted(
        stats.items(),
        key=lambda item: (item[1]["revenue"], item[1]["closed_won"], item[1]["meetings"], item[1]["sent"]),
        reverse=True,
    )
    return [{"module": module, **dict(values)} for module, values in ranked[:8]]


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"signalForge service: {SERVICE_NAME}")
    print(SERVICE_DESCRIPTION)
    print(f"Environment: {os.getenv('SIGNALFORGE_ENV', 'local')}")
    print(f"Vault status: {vault_status()}")
    print(f"MongoDB status: {mongo_status()}")
    yield


app = FastAPI(
    title="SignalForge Dashboard API",
    description="Local-first API for the SignalForge Web Dashboard v1.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict:
    return {
        "service": SERVICE_NAME,
        "description": SERVICE_DESCRIPTION,
        "docs": "/docs",
        "health": "/health",
        "dashboard_api": True,
    }


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "environment": os.getenv("SIGNALFORGE_ENV", "local"),
        "checked_at": utc_now().isoformat(),
        "vault": vault_status(),
        "mongo": mongo_status(),
    }


@app.get("/health/comfyui")
def health_comfyui() -> dict:
    """Return ComfyUI availability diagnostics."""
    try:
        from comfyui_client import comfyui_diagnostics  # type: ignore
        return comfyui_diagnostics()
    except ImportError:
        return {
            "comfyui_enabled": False,
            "comfyui_base_url": os.getenv("COMFYUI_BASE_URL", "http://comfyui:8188"),
            "comfyui_reachable": False,
            "comfyui_error": "comfyui_client module not importable",
            "system_stats": None,
        }


@app.get("/health/ffmpeg")
def health_ffmpeg() -> dict:
    """Return FFmpeg availability diagnostics. No subprocess is spawned if FFmpeg is not installed."""
    try:
        from video_assembler import ffmpeg_diagnostics  # type: ignore
        return ffmpeg_diagnostics()
    except ImportError:
        return {
            "ffmpeg_available": False,
            "ffmpeg_path": "",
            "ffmpeg_version": "",
            "ffmpeg_enabled": False,
            "error": "video_assembler module not importable",
        }


@app.get("/settings/gpt-runtime")
def gpt_runtime_settings() -> dict:
    return gpt_runtime_status()


@app.get("/diagnostics/gpt")
def gpt_diagnostics() -> dict:
    client = get_client()
    try:
        db = get_database(client)
        return serialize(gpt_diagnostics_status(db))
    finally:
        client.close()


@app.get("/vault")
def vault() -> dict:
    path = vault_path()
    if not path.exists():
        return {"path": str(path), "exists": False, "items": []}
    items = sorted(item.name for item in path.iterdir())
    return {"path": str(path), "exists": True, "items": items}


@app.get("/stats/overview")
def stats_overview() -> dict:
    client = get_client()
    try:
        client.admin.command("ping")
        db = get_database(client)
        contacts = list(db.contacts.find({}))
        leads = list(db.leads.find({}))
        messages = list(db.message_drafts.find({}))
        deals = list(db.deals.find({}))

        response_counts = Counter(clean_text(message.get("response_status")) or "not_set" for message in messages)
        deal_counts = Counter(clean_text(deal.get("outcome") or deal.get("deal_status")) or "not_set" for deal in deals)
        closed_won_deals = [deal for deal in deals if deal.get("outcome") == "closed_won" or deal.get("deal_status") == "closed_won"]
        revenue = sum(numeric_value(deal.get("deal_value")) for deal in closed_won_deals)
        meetings = count_response_events(messages, "call_booked")

        funnel = [
            {"stage": "Contacts", "count": len(contacts), "tone": "blue"},
            {"stage": "High Priority", "count": sum(1 for contact in contacts if contact.get("segment") == "high_priority"), "tone": "green"},
            {"stage": "Drafts", "count": len(messages), "tone": "purple"},
            {"stage": "Approved", "count": sum(1 for message in messages if message.get("review_status") == "approved"), "tone": "blue"},
            {"stage": "Sent", "count": sum(1 for message in messages if message.get("send_status") == "sent"), "tone": "amber"},
            {"stage": "Responses", "count": len(messages) - response_counts.get("not_set", 0), "tone": "green"},
            {"stage": "Meetings", "count": meetings, "tone": "purple"},
            {"stage": "Closed Won", "count": len(closed_won_deals), "tone": "green"},
        ]

        revenue_by_date: dict[str, float] = defaultdict(float)
        for deal in closed_won_deals:
            when = deal.get("updated_at") or deal.get("created_at")
            date_key = when.date().isoformat() if isinstance(when, datetime) else "unknown"
            revenue_by_date[date_key] += numeric_value(deal.get("deal_value"))

        return serialize(
            {
                "kpis": {
                    "total_contacts": len(contacts),
                    "total_leads": len(leads),
                    "message_drafts": len(messages),
                    "sent_messages": sum(1 for message in messages if message.get("send_status") == "sent"),
                    "responses": len(messages) - response_counts.get("not_set", 0),
                    "meetings": meetings,
                    "deals": len(deals),
                    "closed_won_revenue": revenue,
                },
                "pipeline_funnel": funnel,
                "responses_by_status": dict(response_counts),
                "deals_by_outcome": dict(deal_counts),
                "revenue_over_time": [{"date": date, "revenue": value} for date, value in sorted(revenue_by_date.items())],
                "top_modules": top_modules(contacts, leads, messages, deals),
                "tasks": dashboard_tasks(leads, contacts, messages, deals),
                "next_actions": next_action_counts(contacts, messages, deals),
                "agent_activity": latest_agent_logs(),
            }
        )
    finally:
        client.close()


@app.get("/contacts")
def contacts(
    q: str = "",
    module: str = "",
    source: str = "",
    segment: str = "",
    status: str = "",
    workspace_slug: str = Query(""),
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if module:
            query["module"] = module
        if source:
            query["source"] = source
        if segment:
            if segment == "unscored":
                query["$or"] = [{"segment": {"$exists": False}}, {"segment": ""}, {"contact_score": {"$exists": False}}]
            else:
                query["segment"] = segment
        if status:
            query["contact_status"] = status
        if q:
            query["$or"] = [
                {"name": {"$regex": re.escape(q), "$options": "i"}},
                {"company": {"$regex": re.escape(q), "$options": "i"}},
                {"email": {"$regex": re.escape(q), "$options": "i"}},
                {"notes": {"$regex": re.escape(q), "$options": "i"}},
            ]
        records = list(db.contacts.find(query).sort([("updated_at", -1), ("imported_at", -1)]).limit(limit))
        records = apply_real_mode_filters(records, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        return {"items": serialize(records)}
    finally:
        client.close()


@app.get("/leads")
def leads(
    q: str = "",
    module: str = "",
    source: str = "",
    review_status: str = "",
    outreach_status: str = "",
    status: str = "",
    workspace_slug: str = Query(""),
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if module:
            if module == "contractor_growth":
                query["$or"] = [
                    {"engine": {"$regex": "contractor_lead_engine"}},
                    {"business_type": {"$regex": "contractor", "$options": "i"}},
                ]
            else:
                query["module"] = module
        if source:
            query["source"] = source
        if review_status:
            query["review_status"] = review_status
        if outreach_status:
            query["outreach_status"] = outreach_status
        if status:
            query["$or"] = query.get("$or", [])
            query["$or"].extend([{"review_status": status}, {"outreach_status": status}])
        if q:
            search_conditions = [
                {"company_name": {"$regex": re.escape(q), "$options": "i"}},
                {"business_type": {"$regex": re.escape(q), "$options": "i"}},
                {"location": {"$regex": re.escape(q), "$options": "i"}},
            ]
            if "$or" in query:
                query = {"$and": [query, {"$or": search_conditions}]}
            else:
                query["$or"] = search_conditions
        records = list(db.leads.find(query).sort([("updated_at", -1), ("lead_score", -1)]).limit(limit))
        for record in records:
            record["module"] = module_for_lead(record)
            record["score"] = score_for(record)
            record["status"] = status_value(record)
        records = apply_real_mode_filters(records, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        return {"items": serialize(records)}
    finally:
        client.close()


@app.get("/messages")
def messages(
    q: str = "",
    module: str = "",
    source: str = "",
    segment: str = "",
    review_status: str = "",
    send_status: str = "",
    response_status: str = "",
    workspace_slug: str = Query(""),
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if module:
            query["module"] = module
        if source:
            query["source"] = source
        if segment:
            query["segment"] = segment
        if review_status:
            query["review_status"] = review_status
        if send_status:
            query["send_status"] = send_status
        if response_status:
            if response_status == "not_set":
                query["$or"] = [{"response_status": {"$exists": False}}, {"response_status": ""}, {"response_status": None}]
            else:
                query["response_status"] = response_status
        if q:
            query["$or"] = [
                {"recipient_name": {"$regex": re.escape(q), "$options": "i"}},
                {"company": {"$regex": re.escape(q), "$options": "i"}},
                {"subject_line": {"$regex": re.escape(q), "$options": "i"}},
            ]
        records = list(db.message_drafts.find(query).sort([("updated_at", -1), ("created_at", -1)]).limit(limit))
        records = apply_real_mode_filters(records, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        records = enrich_messages(records, db)
        return {"items": serialize(records)}
    finally:
        client.close()


@app.post("/messages/{message_id}/review")
def review_message(message_id: str, payload: MessageReviewRequest) -> dict:
    if payload.decision not in VALID_MESSAGE_DECISIONS:
        raise HTTPException(status_code=400, detail="Unsupported review decision.")

    client = get_client()
    reviewed_at = utc_now()
    try:
        db = get_database(client)
        draft = find_message_draft(db, message_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Message draft not found.")

        review_status = review_status_for(payload.decision)
        event = {
            "decision": payload.decision,
            "review_status": review_status,
            "note": payload.note,
            "reviewed_at": reviewed_at,
            "source": "web_dashboard",
        }
        update = {
            "review_status": review_status,
            "review_decision": payload.decision,
            "review_note": payload.note,
            "reviewed_at": reviewed_at,
            "updated_at": reviewed_at,
        }
        if payload.decision == "approve":
            update["send_status"] = "not_sent"

        db.message_drafts.update_one(
            {"_id": draft["_id"]},
            {"$set": update, "$push": {"review_events": event}},
        )
        append_message_review_log(draft, payload.decision, payload.note, reviewed_at)
        updated = db.message_drafts.find_one({"_id": draft["_id"]})
        return {"item": serialize(updated), "message": "Review saved. No message sent."}
    finally:
        client.close()


@app.get("/approval-requests")
def approval_requests(
    status: str = "open",
    view: Literal["actionable", "all", "gpt", "system", "test"] = "actionable",
    request_type: str = "",
    agent_name: str = "",
    module: str = "",
    workspace_slug: str = Query(""),
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if status:
            query["status"] = status
        if request_type:
            query["request_type"] = request_type
        if agent_name:
            query["agent_name"] = agent_name
        if module:
            query["module"] = module
        records = [record for record in db.approval_requests.find(query).sort([("created_at", -1)]) if approval_matches_view(record, view)][:limit]
        records = apply_real_mode_filters(records, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        records = enrich_approval_requests(records, db)
        return {"items": serialize(records), "simulation_only": True}
    finally:
        client.close()


@app.get("/tool-runs")
def tool_runs(limit: int = Query(100, ge=1, le=500), status: str = "", agent_run_id: str = "", workspace_slug: str = Query(""), include_legacy: bool = Query(False), include_test: bool = Query(False)) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if status:
            query["status"] = status
        if agent_run_id:
            query["linked_agent_run_id"] = agent_run_id
        items = list(db.tool_runs.find(query).sort([("created_at", -1)]).limit(limit))
        items = apply_real_mode_filters(items, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        return {"items": serialize(items), "count": len(items), "simulation_only": True}
    finally:
        client.close()


@app.post("/tools/web-search")
def run_web_search_tool(payload: WebSearchToolRunRequest) -> dict:
    if payload.module not in VALID_MODULES:
        raise HTTPException(status_code=400, detail="Unsupported module.")
    from tools.web_search_tool import WebSearchTool

    client = get_client()
    try:
        db = get_database(client)
        result = WebSearchTool().run(payload.query, payload.module, payload.location, payload.limit, db=db)
        return serialize({**result, "message": "Mock research completed. No outbound action taken."})
    finally:
        client.close()


def resolve_import_csv_path(csv_path: str) -> Path:
    raw_path = clean_text(csv_path)
    if not raw_path:
        raise HTTPException(status_code=400, detail="Provide a CSV file or csv_path.")
    path = Path(raw_path)
    if not path.is_absolute():
        parts = path.parts
        path = Path("/data", *parts[1:]) if parts and parts[0] == "data" else PROJECT_ROOT / path
    resolved = path.resolve()
    project_root = PROJECT_ROOT.resolve()
    data_root = Path("/data").resolve()
    if resolved != project_root and project_root not in resolved.parents and resolved != data_root and data_root not in resolved.parents:
        raise HTTPException(status_code=400, detail="CSV path must be inside the SignalForge workspace.")
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"CSV file not found: {csv_path}")
    if resolved.suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Import path must point to a .csv file.")
    return resolved


async def read_candidate_import_request(request: Request) -> tuple[str, str, str, str, str]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        module = clean_text(form.get("module")) or "contractor_growth"
        source_label = clean_text(form.get("source_label")) or "manual_upload"
        workspace_slug = clean_text(form.get("workspace_slug")) or ""
        uploaded = form.get("file")
        csv_path = clean_text(form.get("csv_path"))
        if uploaded and hasattr(uploaded, "read"):
            content = await uploaded.read()
            file_name = clean_text(getattr(uploaded, "filename", "uploaded.csv")) or "uploaded.csv"
            return module, source_label, content.decode("utf-8-sig"), file_name, workspace_slug
        if csv_path:
            path = resolve_import_csv_path(csv_path)
            return module, source_label, path.read_text(encoding="utf-8-sig"), str(path), workspace_slug
        raise HTTPException(status_code=400, detail="Provide a CSV file or csv_path.")

    try:
        payload = CandidateImportRequest(**(await request.json()))
    except Exception as error:
        raise HTTPException(status_code=400, detail="Invalid import request payload.") from error
    workspace_slug = clean_text(getattr(payload, "workspace_slug", "")) or ""
    if payload.csv_text:
        return payload.module, payload.source_label, payload.csv_text, "inline_csv", workspace_slug
    path = resolve_import_csv_path(payload.csv_path)
    return payload.module, payload.source_label, path.read_text(encoding="utf-8-sig"), str(path), workspace_slug


@app.post("/tools/import-candidates")
async def import_candidates_tool(request: Request) -> dict:
    from tools.manual_import_tool import CandidateImportError, ManualCandidateImportTool

    module, source_label, csv_text, file_name, workspace_slug = await read_candidate_import_request(request)
    if module not in VALID_MODULES:
        raise HTTPException(status_code=400, detail="Unsupported module.")
    if not source_label:
        raise HTTPException(status_code=400, detail="source_label is required.")

    client = get_client()
    try:
        db = get_database(client)
        result = ManualCandidateImportTool().run_text(csv_text, module, source_label, db=db, file_name=file_name, workspace_slug=workspace_slug)
        return serialize({**result, "message": "CSV import completed. No contacts, leads, or outbound actions were created automatically."})
    except CandidateImportError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        client.close()


@app.get("/scraped-candidates")
def scraped_candidates(
    status: str = "",
    agent_run_id: str = "",
    tool_run_id: str = "",
    include_duplicates: bool = False,
    source_label: str = "",
    module: str = "",
    min_quality: int | None = None,
    max_quality: int | None = None,
    converted: bool | None = None,
    workspace_slug: str = Query(""),
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if status:
            query["status"] = status
        if agent_run_id:
            query["linked_agent_run_id"] = agent_run_id
        if tool_run_id:
            query["tool_run_id"] = tool_run_id
        if source_label:
            query["source_label"] = source_label
        if module:
            query["module"] = module
        items = list(db.scraped_candidates.find(query))
        if not include_duplicates:
            items = [item for item in items if not item.get("is_duplicate")]
        if min_quality is not None:
            items = [item for item in items if int(item.get("quality_score") or 0) >= min_quality]
        if max_quality is not None:
            items = [item for item in items if int(item.get("quality_score") or 0) <= max_quality]
        if converted is True:
            items = [item for item in items if str(item.get("status", "")).startswith("converted_to_")]
        elif converted is False:
            items = [item for item in items if not str(item.get("status", "")).startswith("converted_to_")]
        items.sort(key=lambda item: (int(item.get("quality_score") or 0), float(item.get("confidence") or 0), item.get("created_at") or utc_now()), reverse=True)
        items = items[:limit]
        items = apply_real_mode_filters(items, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        return {"items": serialize(items), "count": len(items), "simulation_only": True}
    finally:
        client.close()


@app.post("/scraped-candidates/{candidate_id}/decision")
def decide_scraped_candidate(candidate_id: str, payload: ScrapedCandidateDecisionRequest) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        candidate = find_scraped_candidate(db, candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="Scraped candidate not found")
        decided_at = utc_now()
        decision = payload.decision
        update_fields = {
            "status": "approved" if decision == "approve" else "rejected" if decision == "reject" else f"converted_to_{decision.removeprefix('convert_to_')}",
            "last_decision": decision,
            "decision_note": clean_text(payload.note),
            "decided_at": decided_at,
            "updated_at": decided_at,
            "outbound_actions_taken": 0,
        }
        if decision.startswith("convert_to_") and candidate.get("status") != "approved":
            raise HTTPException(status_code=400, detail="Scraped candidate must be approved before local conversion.")
        created_record = None
        if decision == "convert_to_contact":
            created_record = create_contact_from_candidate(db, candidate, decided_at)
            update_fields.update({"created_record_type": "contact", "created_record_id": str(created_record.get("_id"))})
        elif decision == "convert_to_lead":
            created_record = create_lead_from_candidate(db, candidate, decided_at)
            update_fields.update({"created_record_type": "lead", "created_record_id": str(created_record.get("_id"))})
        event = {"decision": decision, "note": clean_text(payload.note), "decided_at": decided_at, "outbound_actions_taken": 0}
        db.scraped_candidates.update_one({"_id": candidate.get("_id")}, {"$set": update_fields, "$push": {"decision_events": event}})
        approval_request_id = clean_text(candidate.get("approval_request_id"))
        if approval_request_id:
            approval_update = {
                "status": "approved" if decision in {"approve", "convert_to_contact", "convert_to_lead"} else "rejected",
                "decision": decision,
                "decision_note": clean_text(payload.note),
                "resolved_at": decided_at,
            }
            approval_query: dict[str, Any] = {"_id": approval_request_id}
            if ObjectId.is_valid(approval_request_id):
                approval_query = {"$or": [{"_id": ObjectId(approval_request_id)}, {"_id": approval_request_id}]}
            db.approval_requests.update_one(approval_query, {"$set": approval_update})
        updated = find_scraped_candidate(db, candidate_id) or {**candidate, **update_fields}
        return {
            "item": serialize(updated),
            "created_record": serialize(created_record) if created_record else None,
            "message": "Candidate decision recorded. No outbound actions were taken.",
            "simulation_only": True,
        }
    finally:
        client.close()


@app.post("/scraped-candidates/bulk-action")
def bulk_candidate_action(payload: BulkCandidateActionRequest) -> dict:
    if not payload.candidate_ids:
        raise HTTPException(status_code=400, detail="candidate_ids must not be empty.")

    client = get_client()
    decided_at = utc_now()
    results = []
    try:
        db = get_database(client)
        for candidate_id in payload.candidate_ids:
            candidate = find_scraped_candidate(db, candidate_id)
            if not candidate:
                results.append({"id": candidate_id, "ok": False, "reason": "not_found"})
                continue

            decision = payload.action
            if decision.startswith("convert_to_") and candidate.get("status") != "approved":
                results.append({"id": candidate_id, "ok": False, "reason": "must_be_approved_before_conversion"})
                continue

            new_status = (
                "approved" if decision == "approve"
                else "rejected" if decision == "reject"
                else f"converted_to_{decision.removeprefix('convert_to_')}"
            )
            update_fields: dict[str, Any] = {
                "status": new_status,
                "last_decision": decision,
                "decision_note": clean_text(payload.note),
                "decided_at": decided_at,
                "updated_at": decided_at,
                "outbound_actions_taken": 0,
            }
            created_record = None
            if decision == "convert_to_contact":
                created_record = create_contact_from_candidate(db, candidate, decided_at)
                update_fields.update({"created_record_type": "contact", "created_record_id": str(created_record.get("_id"))})
            elif decision == "convert_to_lead":
                created_record = create_lead_from_candidate(db, candidate, decided_at)
                update_fields.update({"created_record_type": "lead", "created_record_id": str(created_record.get("_id"))})

            event = {"decision": decision, "note": clean_text(payload.note), "decided_at": decided_at, "outbound_actions_taken": 0, "bulk": True}
            db.scraped_candidates.update_one({"_id": candidate.get("_id")}, {"$set": update_fields, "$push": {"decision_events": event}})

            approval_request_id = clean_text(candidate.get("approval_request_id"))
            if approval_request_id:
                approval_update = {
                    "status": "approved" if decision in {"approve", "convert_to_contact", "convert_to_lead"} else "rejected",
                    "decision": decision,
                    "decision_note": clean_text(payload.note),
                    "resolved_at": decided_at,
                }
                approval_query: dict[str, Any] = {"_id": approval_request_id}
                if ObjectId.is_valid(approval_request_id):
                    approval_query = {"$or": [{"_id": ObjectId(approval_request_id)}, {"_id": approval_request_id}]}
                db.approval_requests.update_one(approval_query, {"$set": approval_update})

            results.append({
                "id": candidate_id,
                "ok": True,
                "new_status": new_status,
                "created_record_type": update_fields.get("created_record_type"),
                "created_record_id": update_fields.get("created_record_id"),
            })

        ok_count = sum(1 for r in results if r.get("ok"))
        fail_count = len(results) - ok_count
        return {
            "results": serialize(results),
            "ok_count": ok_count,
            "fail_count": fail_count,
            "message": f"Bulk action '{payload.action}' applied. {ok_count} succeeded, {fail_count} failed. No outbound actions taken.",
            "simulation_only": True,
        }
    finally:
        client.close()


@app.get("/tools/import-history")
def import_history(
    module: str = "",
    source_label: str = "",
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        items = list(db.tool_runs.find({"tool_name": "manual_upload"}).sort([("created_at", -1)]))
        if module:
            items = [item for item in items if (item.get("input") or {}).get("module") == module]
        if source_label:
            items = [item for item in items if (item.get("input") or {}).get("source_label") == source_label]
        items = items[:limit]
        for item in items:
            output = item.get("output_summary") or {}
            item["candidate_count"] = output.get("candidate_count", 0)
            item["duplicate_count"] = output.get("duplicate_count", 0)
            item["error_count"] = len(output.get("row_errors") or [])
            item["row_count"] = (item.get("input") or {}).get("row_count", 0)
            item["source_label"] = (item.get("input") or {}).get("source_label", "")
            item["module"] = (item.get("input") or {}).get("module", "")
        return {"items": serialize(items), "count": len(items)}
    finally:
        client.close()


@app.get("/tools/import-history/{tool_run_id}/candidates")
def import_history_candidates(
    tool_run_id: str,
    include_duplicates: bool = False,
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        run = find_tool_run(db, tool_run_id)
        if not run or clean_text(run.get("tool_name")) != "manual_upload":
            raise HTTPException(status_code=404, detail="Import run not found.")
        run_id_str = str(run.get("_id"))
        items = list(db.scraped_candidates.find({"tool_run_id": run_id_str}))
        if not include_duplicates:
            items = [item for item in items if not item.get("is_duplicate")]
        items = items[:limit]
        return {"items": serialize(items), "count": len(items), "tool_run_id": run_id_str}
    finally:
        client.close()


@app.get("/tools/import-history/{tool_run_id}/errors")
def import_history_errors(tool_run_id: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        run = find_tool_run(db, tool_run_id)
        if not run or clean_text(run.get("tool_name")) != "manual_upload":
            raise HTTPException(status_code=404, detail="Import run not found.")
        row_errors = (run.get("output_summary") or {}).get("row_errors") or []
        return {"items": row_errors, "count": len(row_errors), "tool_run_id": str(run.get("_id"))}
    finally:
        client.close()


@app.get("/agent-tasks")
def agent_tasks(
    status: str = "",
    agent_name: str = "",
    module: str = "",
    workspace_slug: str = Query(""),
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        base_query = agent_task_query(status, agent_name, module)
        if workspace_slug:
            base_query["workspace_slug"] = workspace_slug
        records = sort_agent_tasks(list(db.agent_tasks.find(base_query)))[:limit]
        records = apply_real_mode_filters(records, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        return {"items": serialize(records), "simulation_only": True}
    finally:
        client.close()


@app.post("/agent-tasks")
def create_agent_task(payload: AgentTaskCreateRequest) -> dict:
    validate_agent_task(payload.agent_name, payload.module)
    task_type = payload.task_type or AGENT_TASK_TYPES[payload.agent_name]
    validate_agent_task_type(payload.agent_name, task_type)
    now = utc_now()
    task = {
        "agent_name": payload.agent_name,
        "module": payload.module,
        "task_type": task_type,
        "status": "queued",
        "priority": payload.priority,
        "input_config": {
            **(payload.input_config or {}),
            "dry_run": True,
            "simulation_only": True,
        },
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "linked_run_id": None,
        "outbound_actions_taken": 0,
        "simulation_only": True,
        **({"workspace_slug": payload.workspace_slug} if payload.workspace_slug else {}),
    }
    client = get_client()
    try:
        db = get_database(client)
        result = db.agent_tasks.insert_one(task)
        created = db.agent_tasks.find_one({"_id": result.inserted_id})
        return serialize({"item": created, "message": "Agent task queued. No outbound action taken.", "simulation_only": True})
    finally:
        client.close()


@app.post("/agent-tasks/{task_id}/run")
def run_agent_task(task_id: str) -> dict:
    client = get_client()
    started_at = utc_now()
    try:
        db = get_database(client)
        task = find_agent_task(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Agent task not found.")
        if task.get("status") in {"running", "completed", "cancelled"}:
            raise HTTPException(status_code=400, detail="Agent task cannot be run from its current status.")

        agent_name = clean_text(task.get("agent_name"))
        module = clean_text(task.get("module"))
        task_type = clean_text(task.get("task_type"))
        validate_agent_task(agent_name, module)
        validate_agent_task_type(agent_name, task_type)
        db.agent_tasks.update_one(
            {"_id": task["_id"]},
            {"$set": {"status": "running", "started_at": started_at, "updated_at": started_at, "outbound_actions_taken": 0}},
        )

        try:
            agent_cls = AGENT_CLASSES[agent_name]
            limit = int((task.get("input_config") or {}).get("limit") or 10)
            agent = instantiate_agent(
                agent_cls,
                module=module,
                dry_run=True,
                mongo_uri=mongo_uri(),
                vault_path=vault_path(),
                limit=max(1, min(limit, 50)),
                use_tools=bool((task.get("input_config") or {}).get("use_tools")),
                workspace_slug=clean_text(task.get("workspace_slug") or ""),
            )
            result = agent.run()
            run = db.agent_runs.find_one({"run_id": result.get("run_id")})
            run_status = clean_text(run.get("status") if run else "completed") or "completed"
            final_status = "waiting_for_approval" if run_status == "waiting_for_approval" else "completed"
            completed_at = utc_now()
            update = {
                "status": final_status,
                "completed_at": completed_at,
                "updated_at": completed_at,
                "linked_run_id": result.get("run_id"),
                "result_summary": {
                    "agent_run_status": run_status,
                    "planned_action_count": len(result.get("actions") or []),
                    "log_path": result.get("log_path"),
                    "simulation_only": True,
                    "outbound_actions_taken": 0,
                },
                "error": None,
                "outbound_actions_taken": 0,
            }
            db.agent_tasks.update_one({"_id": task["_id"]}, {"$set": update})
            updated = db.agent_tasks.find_one({"_id": task["_id"]})
            return serialize(
                {
                    "item": updated,
                    "run": run,
                    "result": result,
                    "message": "Agent task dry-run completed. No outbound action taken.",
                    "simulation_only": True,
                }
            )
        except Exception as exc:
            failed_at = utc_now()
            db.agent_tasks.update_one(
                {"_id": task["_id"]},
                {
                    "$set": {
                        "status": "failed",
                        "completed_at": failed_at,
                        "updated_at": failed_at,
                        "error": f"{exc.__class__.__name__}: {exc}",
                        "result_summary": {
                            "error": f"{exc.__class__.__name__}: {exc}",
                            "simulation_only": True,
                            "outbound_actions_taken": 0,
                        },
                        "outbound_actions_taken": 0,
                    }
                },
            )
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        client.close()


@app.post("/agent-tasks/{task_id}/cancel")
def cancel_agent_task(task_id: str) -> dict:
    client = get_client()
    cancelled_at = utc_now()
    try:
        db = get_database(client)
        task = find_agent_task(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Agent task not found.")
        if task.get("status") in {"completed", "cancelled", "running"}:
            raise HTTPException(status_code=400, detail="Agent task cannot be cancelled from its current status.")
        db.agent_tasks.update_one(
            {"_id": task["_id"]},
            {
                "$set": {
                    "status": "cancelled",
                    "completed_at": cancelled_at,
                    "updated_at": cancelled_at,
                    "outbound_actions_taken": 0,
                    "simulation_only": True,
                }
            },
        )
        updated = db.agent_tasks.find_one({"_id": task["_id"]})
        return serialize({"item": updated, "message": "Agent task cancelled. No outbound action taken.", "simulation_only": True})
    finally:
        client.close()


@app.post("/approval-requests/{approval_id}/decision")
def decide_approval_request(approval_id: str, payload: ApprovalDecisionRequest) -> dict:
    client = get_client()
    decided_at = utc_now()
    try:
        db = get_database(client)
        request = find_approval_request(db, approval_id)
        if not request:
            raise HTTPException(status_code=404, detail="Approval request not found.")

        created_record_type = None
        created_record = None
        if payload.decision == "convert_to_draft":
            created_record_type, created_record = convert_approval_to_draft(db, request, payload.note, decided_at)

        event = {
            "decision": payload.decision,
            "status": approval_status_for_decision(payload.decision),
            "note": payload.note,
            "decided_at": decided_at,
            "source": "web_dashboard",
            "created_record_type": created_record_type,
            "created_record_id": str(created_record.get("_id")) if created_record and created_record.get("_id") else None,
            "simulation_only": True,
        }
        update = {
            "status": approval_status_for_decision(payload.decision),
            "decision": payload.decision,
            "operator_note": payload.note,
            "decided_at": decided_at,
            "resolved_at": decided_at,
            "updated_at": decided_at,
            "created_record_type": created_record_type,
            "created_record_id": str(created_record.get("_id")) if created_record and created_record.get("_id") else None,
            "outbound_actions_taken": 0,
            "simulation_only": True,
        }
        db.approval_requests.update_one(
            {"_id": request["_id"]},
            {"$set": update, "$push": {"decision_events": event}},
        )
        updated = db.approval_requests.find_one({"_id": request["_id"]})
        enriched = enrich_approval_requests([updated], db)[0] if updated else None
        return serialize(
            {
                "item": enriched,
                "created_record_type": created_record_type,
                "created_record": created_record,
                "message": "Approval decision saved. No outbound action taken.",
                "simulation_only": True,
            }
        )
    finally:
        client.close()


@app.get("/agents")
def agents() -> dict:
    client = get_client()
    try:
        db = get_database(client)
        runs = latest_agent_runs(db, limit=12)
    except Exception:
        runs = []
    finally:
        try:
            client.close()
        except Exception:
            pass

    available = []
    for name, agent_cls in AGENT_CLASSES.items():
        available.append(
            {
                "name": name,
                "available": agent_cls is not None,
                "description": getattr(agent_cls, "agent_role", "Simulation-only planning agent") if agent_cls else "Unavailable",
            }
        )
    return {
        "items": available,
        "modules": sorted(SUPPORTED_MODULES.keys()) if SUPPORTED_MODULES else list(VALID_MODULES),
        "logs": latest_agent_logs(),
        "runs": serialize(runs),
        "simulation_only": True,
    }


@app.post("/agents/run")
def run_agent(payload: AgentRunRequest) -> dict:
    agent_cls = AGENT_CLASSES.get(payload.agent)
    if agent_cls is None:
        raise HTTPException(status_code=503, detail="Agent classes are unavailable in the API runtime.")
    if SUPPORTED_MODULES and payload.module not in SUPPORTED_MODULES:
        raise HTTPException(status_code=400, detail="Unsupported module.")

    try:
        agent = instantiate_agent(
            agent_cls,
            module=payload.module,
            dry_run=True,
            mongo_uri=mongo_uri(),
            vault_path=vault_path(),
            limit=max(1, min(payload.limit, 50)),
            use_tools=payload.use_tools,
            workspace_slug=payload.workspace_slug,
        )
        result = agent.run()
        client = get_client()
        try:
            db = get_database(client)
            run = db.agent_runs.find_one({"run_id": result.get("run_id")})
            steps = list(db.agent_steps.find({"run_id": result.get("run_id")}).sort("step_number", 1))
            approvals = list(db.approval_requests.find({"run_id": result.get("run_id")}).sort("created_at", -1))
            approvals = enrich_approval_requests(approvals, db)
        finally:
            client.close()
        return serialize(
            {
                "result": result,
                "run": run,
                "steps": steps,
                "approval_requests": approvals,
                "simulation_only": True,
                "message": "Agent dry-run completed. No outbound action taken.",
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/agent-runs")
def agent_runs(
    agent_name: str = "",
    module: str = "",
    status: str = "",
    workspace_slug: str = Query(""),
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if agent_name:
            query["agent_name"] = agent_name
        if module:
            query["module"] = module
        if status:
            query["status"] = status
        runs = list(db.agent_runs.find(query).sort([("started_at", -1)]).limit(limit))
        runs = apply_real_mode_filters(runs, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        return {"items": serialize(runs)}
    finally:
        client.close()


@app.get("/agent-runs/{run_id}")
def agent_run_detail(run_id: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {"run_id": run_id}
        if ObjectId.is_valid(run_id):
            query = {"$or": [{"run_id": run_id}, {"_id": ObjectId(run_id)}]}
        run = db.agent_runs.find_one(query)
        if not run:
            raise HTTPException(status_code=404, detail="Agent run not found.")
        actual_run_id = run.get("run_id") or str(run.get("_id"))
        steps = list(db.agent_steps.find({"run_id": actual_run_id}).sort("step_number", 1))
        artifacts = list(db.agent_artifacts.find({"run_id": actual_run_id}).sort("created_at", 1))
        approvals = list(db.approval_requests.find({"run_id": actual_run_id}).sort("created_at", -1))
        approvals = enrich_approval_requests(approvals, db)
        tool_runs = list(db.tool_runs.find({"linked_agent_run_id": actual_run_id}).sort("created_at", -1).limit(25))
        scraped = list(db.scraped_candidates.find({"linked_agent_run_id": actual_run_id}).sort("created_at", -1).limit(25))

        related_contacts = []
        for value in run.get("related_contacts") or []:
            conditions = [{"contact_key": value}]
            conditions.extend({"_id": item} for item in object_id_or_raw(value) if isinstance(item, ObjectId))
            found = db.contacts.find_one({"$or": conditions})
            if found:
                related_contacts.append(found)

        related_leads = []
        for value in run.get("related_leads") or []:
            conditions = [{"company_slug": value}]
            conditions.extend({"_id": item} for item in object_id_or_raw(value) if isinstance(item, ObjectId))
            found = db.leads.find_one({"$or": conditions})
            if found:
                related_leads.append(found)

        related_messages = []
        for value in run.get("related_messages") or []:
            found = find_message_draft(db, value)
            if found:
                related_messages.append(found)

        contact_values = [item for value in run.get("related_contacts") or [] for item in object_id_or_raw(value)]
        lead_values = [item for value in run.get("related_leads") or [] for item in object_id_or_raw(value)]
        message_values = [item for value in run.get("related_messages") or [] for item in object_id_or_raw(value)]
        related_deals = list(
            db.deals.find(
                {
                    "$or": [
                        {"contact_id": {"$in": contact_values}},
                        {"lead_id": {"$in": lead_values}},
                        {"message_draft_id": {"$in": message_values}},
                    ]
                }
            )
        )

        return serialize(
            {
                "run": run,
                "steps": steps,
                "artifacts": artifacts,
                "approval_requests": approvals,
                "tool_runs": tool_runs,
                "scraped_candidates": scraped,
                "related": {
                    "contacts": related_contacts,
                    "leads": related_leads,
                    "messages": enrich_messages(related_messages, db),
                    "deals": related_deals,
                },
            }
        )
    finally:
        client.close()


@app.get("/deals")
def deals(
    module: str = "",
    outcome: str = "",
    workspace_slug: str = Query(""),
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(200, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if module:
            query["module"] = module
        if outcome:
            query["$or"] = [{"outcome": outcome}, {"deal_status": outcome}]
        records = list(db.deals.find(query).sort([("updated_at", -1), ("deal_value", -1)]).limit(limit))
        records = apply_real_mode_filters(records, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        return {"items": serialize(records)}
    finally:
        client.close()


@app.get("/reports")
def reports() -> dict:
    reports_dir = vault_path() / "reports"
    return {
        "items": [
            report_file(reports_dir / "contractor_pipeline_report.md", "Contractor Pipeline Report"),
            report_file(reports_dir / "revenue_performance_report.md", "Revenue Performance Report"),
        ]
    }


@app.get("/workspaces")
def list_workspaces(status: str = "") -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        items = list(db.workspaces.find(query).sort([("created_at", 1)]))
        if not items:
            now = utc_now()
            default: dict[str, Any] = {
                "slug": "default",
                "name": "Default Workspace",
                "type": "internal",
                "module": "",
                "notes": "Auto-created default workspace.",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
            db.workspaces.insert_one(default)
            items = [db.workspaces.find_one({"slug": "default"})]
        return {"items": serialize(items)}
    finally:
        client.close()


@app.post("/workspaces")
def create_workspace(payload: WorkspaceCreateRequest) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Workspace name is required.")
    slug = slugify(name)
    if not slug:
        raise HTTPException(status_code=400, detail="Workspace name produced an empty slug.")
    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        existing = db.workspaces.find_one({"slug": slug})
        if existing:
            raise HTTPException(status_code=409, detail=f"A workspace with slug '{slug}' already exists.")
        workspace: dict[str, Any] = {
            "slug": slug,
            "name": name,
            "type": payload.type,
            "module": payload.module.strip() if payload.module else "",
            "notes": payload.notes.strip() if payload.notes else "",
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        result = db.workspaces.insert_one(workspace)
        created = db.workspaces.find_one({"_id": result.inserted_id})
        return {"item": serialize(created), "message": "Workspace created."}
    finally:
        client.close()


@app.get("/workspaces/{slug}")
def get_workspace(slug: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        workspace = db.workspaces.find_one({"slug": slug})
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        return {"item": serialize(workspace)}
    finally:
        client.close()


@app.patch("/workspaces/{slug}/status")
def update_workspace_status(slug: str, payload: WorkspaceStatusRequest) -> dict:
    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        workspace = db.workspaces.find_one({"slug": slug})
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        db.workspaces.update_one(
            {"slug": slug},
            {"$set": {"status": payload.status, "updated_at": now}},
        )
        updated = db.workspaces.find_one({"slug": slug})
        return {"item": serialize(updated), "message": f"Workspace status updated to '{payload.status}'."}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Creative Studio: Content Briefs
# ---------------------------------------------------------------------------


def find_content_brief(db, brief_id: str) -> dict | None:
    query: dict[str, Any] = {"_id": brief_id}
    if ObjectId.is_valid(brief_id):
        query = {"$or": [{"_id": ObjectId(brief_id)}, {"_id": brief_id}]}
    return db.content_briefs.find_one(query)


def find_content_draft(db, draft_id: str) -> dict | None:
    query: dict[str, Any] = {"_id": draft_id}
    if ObjectId.is_valid(draft_id):
        query = {"$or": [{"_id": ObjectId(draft_id)}, {"_id": draft_id}]}
    return db.content_drafts.find_one(query)


def content_draft_status_for(decision: str) -> str:
    if decision == "approve":
        return "approved"
    if decision == "reject":
        return "rejected"
    return "needs_review"


@app.get("/content-briefs")
def content_briefs(
    workspace_slug: str = Query(""),
    module: str = "",
    platform: str = "",
    status: str = "",
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if module:
            query["module"] = module
        if platform:
            query["platform"] = platform
        if status:
            query["status"] = status
        records = list(db.content_briefs.find(query).sort([("created_at", -1)]).limit(limit))
        records = apply_real_mode_filters(records, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        return {"items": serialize(records)}
    finally:
        client.close()


@app.post("/content-briefs")
def create_content_brief(payload: ContentBriefCreateRequest) -> dict:
    now = utc_now()
    brief: dict[str, Any] = {
        "workspace_slug": clean_text(payload.workspace_slug),
        "module": clean_text(payload.module),
        "campaign_name": clean_text(payload.campaign_name),
        "audience": clean_text(payload.audience),
        "platform": clean_text(payload.platform),
        "goal": clean_text(payload.goal),
        "offer": clean_text(payload.offer),
        "tone": clean_text(payload.tone),
        "notes": clean_text(payload.notes),
        "status": payload.status,
        "created_at": now,
        "updated_at": now,
    }
    client = get_client()
    try:
        db = get_database(client)
        result = db.content_briefs.insert_one(brief)
        created = db.content_briefs.find_one({"_id": result.inserted_id})
        return {"item": serialize(created), "message": "Content brief created."}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Creative Studio: Content Drafts
# ---------------------------------------------------------------------------


@app.get("/content-drafts")
def content_drafts(
    workspace_slug: str = Query(""),
    module: str = "",
    platform: str = "",
    content_type: str = "",
    status: str = "",
    brief_id: str = "",
    generated_by_agent: bool | None = None,
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if module:
            query["module"] = module
        if platform:
            query["platform"] = platform
        if content_type:
            query["content_type"] = content_type
        if status:
            query["status"] = status
        if brief_id:
            query["brief_id"] = brief_id
        if generated_by_agent is True:
            query["generated_by_agent"] = {"$nin": ["", None]}
        elif generated_by_agent is False:
            query["$or"] = [{"generated_by_agent": ""}, {"generated_by_agent": None}, {"generated_by_agent": {"$exists": False}}]
        records = list(db.content_drafts.find(query).sort([("created_at", -1)]).limit(limit))
        records = apply_real_mode_filters(records, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        return {"items": serialize(records)}
    finally:
        client.close()


@app.post("/content-drafts")
def create_content_draft(payload: ContentDraftCreateRequest) -> dict:
    now = utc_now()
    draft: dict[str, Any] = {
        "workspace_slug": clean_text(payload.workspace_slug),
        "module": clean_text(payload.module),
        "brief_id": clean_text(payload.brief_id),
        "platform": clean_text(payload.platform),
        "content_type": payload.content_type,
        "title": clean_text(payload.title),
        "body": clean_text(payload.body),
        "hashtags": [clean_text(tag) for tag in payload.hashtags if clean_text(tag)],
        "call_to_action": clean_text(payload.call_to_action),
        "status": payload.status,
        "generated_by_agent": clean_text(payload.generated_by_agent),
        "agent_run_id": clean_text(payload.agent_run_id),
        "selected_model": clean_text(payload.selected_model),
        "routing_reason": clean_text(payload.routing_reason),
        "complexity": clean_text(payload.complexity),
        "review_events": [],
        "outbound_actions_taken": 0,
        "simulation_only": True,
        "created_at": now,
        "updated_at": now,
    }
    client = get_client()
    try:
        db = get_database(client)
        result = db.content_drafts.insert_one(draft)
        created = db.content_drafts.find_one({"_id": result.inserted_id})
        return {"item": serialize(created), "message": "Content draft created. No post published or scheduled."}
    finally:
        client.close()


@app.post("/content-drafts/{draft_id}/review")
def review_content_draft(draft_id: str, payload: ContentDraftReviewRequest) -> dict:
    client = get_client()
    reviewed_at = utc_now()
    try:
        db = get_database(client)
        draft = find_content_draft(db, draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Content draft not found.")
        new_status = content_draft_status_for(payload.decision)
        event = {
            "decision": payload.decision,
            "status": new_status,
            "note": clean_text(payload.note),
            "reviewed_at": reviewed_at,
            "source": "web_dashboard",
        }
        db.content_drafts.update_one(
            {"_id": draft["_id"]},
            {
                "$set": {
                    "status": new_status,
                    "review_decision": payload.decision,
                    "review_note": clean_text(payload.note),
                    "reviewed_at": reviewed_at,
                    "updated_at": reviewed_at,
                    "outbound_actions_taken": 0,
                },
                "$push": {"review_events": event},
            },
        )
        updated = db.content_drafts.find_one({"_id": draft["_id"]})
        return {
            "item": serialize(updated),
            "message": "Draft review saved. No post published or scheduled.",
            "simulation_only": True,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Social Creative Engine v2 — Pydantic models
# ---------------------------------------------------------------------------

class ClientProfileCreateRequest(BaseModel):
    workspace_slug: str = ""
    client_name: str
    brand_name: str = ""
    approved_source_channels: list[str] = Field(default_factory=list)
    allowed_content_types: list[str] = Field(default_factory=list)
    disallowed_topics: list[str] = Field(default_factory=list)
    likeness_permissions: bool = False
    voice_permissions: bool = False
    avatar_permissions: bool = False
    compliance_notes: str = ""
    status: Literal["active", "archived"] = "active"


class SourceChannelCreateRequest(BaseModel):
    workspace_slug: str = ""
    client_id: str = ""
    platform: str = ""
    channel_name: str = ""
    channel_url: str = ""
    approved_for_ingestion: bool = False
    approved_for_reuse: bool = False
    notes: str = ""


class SourceContentCreateRequest(BaseModel):
    workspace_slug: str = ""
    client_id: str = ""
    source_channel_id: str = ""
    platform: str = ""
    source_url: str = ""
    title: str = ""
    creator: str = ""
    published_at: str = ""
    duration_seconds: int = 0
    performance_metadata: dict = Field(default_factory=dict)
    discovery_score: float = 0.0
    discovery_reason: str = ""
    status: Literal["needs_review", "approved", "rejected"] = "needs_review"


class ContentTranscriptCreateRequest(BaseModel):
    workspace_slug: str = ""
    source_content_id: str = ""
    transcript_text: str = ""
    status: Literal["pending", "complete", "failed"] = "pending"


class ContentSnippetCreateRequest(BaseModel):
    workspace_slug: str = ""
    source_content_id: str = ""
    transcript_id: str = ""
    speaker: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    transcript_text: str = ""
    score: float = 0.0
    score_reason: str = ""
    theme: str = ""
    hook_angle: str = ""
    platform_fit: list[str] = Field(default_factory=list)
    status: Literal["needs_review", "approved", "rejected"] = "needs_review"


class ContentSnippetReviewRequest(BaseModel):
    decision: Literal["approve", "reject", "revise"]
    note: str = ""


class CreativeAssetCreateRequest(BaseModel):
    workspace_slug: str = ""
    client_id: str = ""
    source_content_id: str = ""
    snippet_id: str = ""
    asset_type: Literal["image", "video", "carousel", "reel", "other"] = "image"
    title: str = ""
    description: str = ""
    file_path: str = ""
    prompt_used: str = ""
    tool_run_id: str = ""
    status: Literal["needs_review", "approved", "rejected"] = "needs_review"


class CreativeToolRunRequest(BaseModel):
    workspace_slug: str = ""
    client_id: str = ""
    snippet_id: str = ""
    source_content_id: str = ""
    tool_name: Literal["comfyui", "manual"] = "comfyui"
    workflow_path: str = ""
    prompt_inputs: dict = Field(default_factory=dict)
    notes: str = ""


# ---------------------------------------------------------------------------
# Social Creative Engine v2 — helper functions
# ---------------------------------------------------------------------------

def find_client_profile(db, profile_id: str) -> dict | None:
    query: dict[str, Any] = {"_id": profile_id}
    if ObjectId.is_valid(profile_id):
        query = {"$or": [{"_id": ObjectId(profile_id)}, {"_id": profile_id}]}
    return db.client_profiles.find_one(query)


def find_source_channel(db, channel_id: str) -> dict | None:
    query: dict[str, Any] = {"_id": channel_id}
    if ObjectId.is_valid(channel_id):
        query = {"$or": [{"_id": ObjectId(channel_id)}, {"_id": channel_id}]}
    return db.source_channels.find_one(query)


def find_source_content(db, content_id: str) -> dict | None:
    query: dict[str, Any] = {"_id": content_id}
    if ObjectId.is_valid(content_id):
        query = {"$or": [{"_id": ObjectId(content_id)}, {"_id": content_id}]}
    return db.source_content.find_one(query)


def find_content_transcript(db, transcript_id: str) -> dict | None:
    query: dict[str, Any] = {"_id": transcript_id}
    if ObjectId.is_valid(transcript_id):
        query = {"$or": [{"_id": ObjectId(transcript_id)}, {"_id": transcript_id}]}
    return db.content_transcripts.find_one(query)


def find_content_snippet(db, snippet_id: str) -> dict | None:
    query: dict[str, Any] = {"_id": snippet_id}
    if ObjectId.is_valid(snippet_id):
        query = {"$or": [{"_id": ObjectId(snippet_id)}, {"_id": snippet_id}]}
    return db.content_snippets.find_one(query)


def find_creative_asset(db, asset_id: str) -> dict | None:
    query: dict[str, Any] = {"_id": asset_id}
    if ObjectId.is_valid(asset_id):
        query = {"$or": [{"_id": ObjectId(asset_id)}, {"_id": asset_id}]}
    return db.creative_assets.find_one(query)


def find_creative_tool_run(db, run_id: str) -> dict | None:
    query: dict[str, Any] = {"_id": run_id}
    if ObjectId.is_valid(run_id):
        query = {"$or": [{"_id": ObjectId(run_id)}, {"_id": run_id}]}
    return db.creative_tool_runs.find_one(query)


def snippet_status_for(decision: str) -> str:
    if decision == "approve":
        return "approved"
    if decision == "reject":
        return "rejected"
    return "needs_review"


# ---------------------------------------------------------------------------
# Social Creative Engine v2 — Part 1: Client Profiles
# ---------------------------------------------------------------------------

@app.get("/client-profiles")
def list_client_profiles(
    workspace_slug: str = Query(""),
    status: str = "",
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if status:
            query["status"] = status
        records = list(db.client_profiles.find(query).sort([("created_at", -1)]).limit(limit))
        records = apply_real_mode_filters(records, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        return {"items": serialize(records)}
    finally:
        client.close()


@app.post("/client-profiles")
def create_client_profile(payload: ClientProfileCreateRequest) -> dict:
    if not payload.client_name.strip():
        raise HTTPException(status_code=400, detail="client_name is required.")
    now = utc_now()
    record: dict[str, Any] = {
        "workspace_slug": clean_text(payload.workspace_slug),
        "client_name": clean_text(payload.client_name),
        "brand_name": clean_text(payload.brand_name),
        "approved_source_channels": [clean_text(c) for c in payload.approved_source_channels if clean_text(c)],
        "allowed_content_types": [clean_text(c) for c in payload.allowed_content_types if clean_text(c)],
        "disallowed_topics": [clean_text(t) for t in payload.disallowed_topics if clean_text(t)],
        "likeness_permissions": False,
        "voice_permissions": False,
        "avatar_permissions": False,
        "compliance_notes": clean_text(payload.compliance_notes),
        "status": payload.status,
        "created_at": now,
        "updated_at": now,
    }
    client = get_client()
    try:
        db = get_database(client)
        result = db.client_profiles.insert_one(record)
        created = db.client_profiles.find_one({"_id": result.inserted_id})
        return {"item": serialize(created), "message": "Client profile created. No post published or scheduled."}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Social Creative Engine v2 — Part 2: Source Channels
# ---------------------------------------------------------------------------

@app.get("/source-channels")
def list_source_channels(
    workspace_slug: str = Query(""),
    client_id: str = "",
    platform: str = "",
    approved_for_ingestion: bool | None = None,
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if client_id:
            query["client_id"] = client_id
        if platform:
            query["platform"] = platform
        if approved_for_ingestion is not None:
            query["approved_for_ingestion"] = approved_for_ingestion
        records = list(db.source_channels.find(query).sort([("created_at", -1)]).limit(limit))
        records = apply_real_mode_filters(records, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        return {"items": serialize(records)}
    finally:
        client.close()


@app.post("/source-channels")
def create_source_channel(payload: SourceChannelCreateRequest) -> dict:
    now = utc_now()
    record: dict[str, Any] = {
        "workspace_slug": clean_text(payload.workspace_slug),
        "client_id": clean_text(payload.client_id),
        "platform": clean_text(payload.platform),
        "channel_name": clean_text(payload.channel_name),
        "channel_url": clean_text(payload.channel_url),
        "approved_for_ingestion": payload.approved_for_ingestion,
        "approved_for_reuse": payload.approved_for_reuse,
        "notes": clean_text(payload.notes),
        "created_at": now,
        "updated_at": now,
    }
    client = get_client()
    try:
        db = get_database(client)
        result = db.source_channels.insert_one(record)
        created = db.source_channels.find_one({"_id": result.inserted_id})
        return {"item": serialize(created), "message": "Source channel created. No post published or scheduled."}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Social Creative Engine v2 — Part 3: Source Content
# ---------------------------------------------------------------------------

@app.get("/source-content")
def list_source_content(
    workspace_slug: str = Query(""),
    client_id: str = "",
    source_channel_id: str = "",
    status: str = "",
    platform: str = "",
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if client_id:
            query["client_id"] = client_id
        if source_channel_id:
            query["source_channel_id"] = source_channel_id
        if status:
            query["status"] = status
        if platform:
            query["platform"] = platform
        records = list(db.source_content.find(query).sort([("created_at", -1)]).limit(limit))
        records = apply_real_mode_filters(records, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        return {"items": serialize(records)}
    finally:
        client.close()


@app.post("/source-content")
def create_source_content(payload: SourceContentCreateRequest) -> dict:
    now = utc_now()
    record: dict[str, Any] = {
        "workspace_slug": clean_text(payload.workspace_slug),
        "client_id": clean_text(payload.client_id),
        "source_channel_id": clean_text(payload.source_channel_id),
        "platform": clean_text(payload.platform),
        "source_url": clean_text(payload.source_url),
        "title": clean_text(payload.title),
        "creator": clean_text(payload.creator),
        "published_at": clean_text(payload.published_at),
        "duration_seconds": payload.duration_seconds,
        "performance_metadata": payload.performance_metadata or {},
        "discovery_score": payload.discovery_score,
        "discovery_reason": clean_text(payload.discovery_reason),
        "status": payload.status,
        "review_events": [],
        "simulation_only": True,
        "outbound_actions_taken": 0,
        "created_at": now,
        "updated_at": now,
    }
    client = get_client()
    try:
        db = get_database(client)
        result = db.source_content.insert_one(record)
        created = db.source_content.find_one({"_id": result.inserted_id})
        return {"item": serialize(created), "message": "Source content created. No post published or scheduled."}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Social Creative Engine v2 — Part 4: Transcripts + Snippets
# ---------------------------------------------------------------------------

@app.get("/content-transcripts")
def list_content_transcripts(
    workspace_slug: str = Query(""),
    source_content_id: str = "",
    status: str = "",
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if source_content_id:
            query["source_content_id"] = source_content_id
        if status:
            query["status"] = status
        records = list(db.content_transcripts.find(query).sort([("created_at", -1)]).limit(limit))
        records = apply_real_mode_filters(records, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        return {"items": serialize(records)}
    finally:
        client.close()


@app.post("/content-transcripts")
def create_content_transcript(payload: ContentTranscriptCreateRequest) -> dict:
    now = utc_now()
    record: dict[str, Any] = {
        "workspace_slug": clean_text(payload.workspace_slug),
        "source_content_id": clean_text(payload.source_content_id),
        "transcript_text": clean_text(payload.transcript_text),
        "status": payload.status,
        "created_at": now,
        "updated_at": now,
    }
    client = get_client()
    try:
        db = get_database(client)
        result = db.content_transcripts.insert_one(record)
        created = db.content_transcripts.find_one({"_id": result.inserted_id})
        return {"item": serialize(created), "message": "Transcript created. No post published or scheduled."}
    finally:
        client.close()


@app.get("/content-snippets")
def list_content_snippets(
    workspace_slug: str = Query(""),
    source_content_id: str = "",
    transcript_id: str = "",
    status: str = "",
    theme: str = "",
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if source_content_id:
            query["source_content_id"] = source_content_id
        if transcript_id:
            query["transcript_id"] = transcript_id
        if status:
            query["status"] = status
        if theme:
            query["theme"] = theme
        records = list(db.content_snippets.find(query).sort([("score", -1), ("created_at", -1)]).limit(limit))
        records = apply_real_mode_filters(records, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        return {"items": serialize(records)}
    finally:
        client.close()


@app.post("/content-snippets")
def create_content_snippet(payload: ContentSnippetCreateRequest) -> dict:
    now = utc_now()
    record: dict[str, Any] = {
        "workspace_slug": clean_text(payload.workspace_slug),
        "source_content_id": clean_text(payload.source_content_id),
        "transcript_id": clean_text(payload.transcript_id),
        "speaker": clean_text(payload.speaker),
        "start_time": payload.start_time,
        "end_time": payload.end_time,
        "transcript_text": clean_text(payload.transcript_text),
        "score": payload.score,
        "score_reason": clean_text(payload.score_reason),
        "theme": clean_text(payload.theme),
        "hook_angle": clean_text(payload.hook_angle),
        "platform_fit": [clean_text(p) for p in payload.platform_fit if clean_text(p)],
        "status": payload.status,
        "review_events": [],
        "simulation_only": True,
        "outbound_actions_taken": 0,
        "created_at": now,
        "updated_at": now,
    }
    client = get_client()
    try:
        db = get_database(client)
        result = db.content_snippets.insert_one(record)
        created = db.content_snippets.find_one({"_id": result.inserted_id})
        return {"item": serialize(created), "message": "Content snippet created. No post published or scheduled."}
    finally:
        client.close()


@app.post("/content-snippets/{snippet_id}/review")
def review_content_snippet(snippet_id: str, payload: ContentSnippetReviewRequest) -> dict:
    client = get_client()
    reviewed_at = utc_now()
    try:
        db = get_database(client)
        snippet = find_content_snippet(db, snippet_id)
        if not snippet:
            raise HTTPException(status_code=404, detail="Content snippet not found.")
        new_status = snippet_status_for(payload.decision)
        event = {
            "decision": payload.decision,
            "status": new_status,
            "note": clean_text(payload.note),
            "reviewed_at": reviewed_at,
            "source": "web_dashboard",
        }
        db.content_snippets.update_one(
            {"_id": snippet["_id"]},
            {
                "$set": {
                    "status": new_status,
                    "review_decision": payload.decision,
                    "review_note": clean_text(payload.note),
                    "reviewed_at": reviewed_at,
                    "updated_at": reviewed_at,
                    "outbound_actions_taken": 0,
                },
                "$push": {"review_events": event},
            },
        )
        updated = db.content_snippets.find_one({"_id": snippet["_id"]})
        return {
            "item": serialize(updated),
            "message": "Snippet review saved. No post published or scheduled.",
            "simulation_only": True,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Social Creative Engine v2 — Part 5: Creative Assets + Tool Runs
# ---------------------------------------------------------------------------

@app.get("/creative-assets")
def list_creative_assets(
    workspace_slug: str = Query(""),
    client_id: str = "",
    snippet_id: str = "",
    status: str = "",
    asset_type: str = "",
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if client_id:
            query["client_id"] = client_id
        if snippet_id:
            query["snippet_id"] = snippet_id
        if status:
            query["status"] = status
        if asset_type:
            query["asset_type"] = asset_type
        records = list(db.creative_assets.find(query).sort([("created_at", -1)]).limit(limit))
        records = apply_real_mode_filters(records, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        return {"items": serialize(records)}
    finally:
        client.close()


@app.post("/creative-assets")
def create_creative_asset(payload: CreativeAssetCreateRequest) -> dict:
    now = utc_now()
    record: dict[str, Any] = {
        "workspace_slug": clean_text(payload.workspace_slug),
        "client_id": clean_text(payload.client_id),
        "source_content_id": clean_text(payload.source_content_id),
        "snippet_id": clean_text(payload.snippet_id),
        "asset_type": payload.asset_type,
        "title": clean_text(payload.title),
        "description": clean_text(payload.description),
        "file_path": clean_text(payload.file_path),
        "prompt_used": clean_text(payload.prompt_used),
        "tool_run_id": clean_text(payload.tool_run_id),
        "status": payload.status,
        "review_events": [],
        "simulation_only": True,
        "outbound_actions_taken": 0,
        "created_at": now,
        "updated_at": now,
    }
    client = get_client()
    try:
        db = get_database(client)
        result = db.creative_assets.insert_one(record)
        created = db.creative_assets.find_one({"_id": result.inserted_id})
        return {"item": serialize(created), "message": "Creative asset created. No post published or scheduled."}
    finally:
        client.close()


@app.get("/creative-tool-runs")
def list_creative_tool_runs(
    workspace_slug: str = Query(""),
    client_id: str = "",
    status: str = "",
    tool_name: str = "",
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if client_id:
            query["client_id"] = client_id
        if status:
            query["status"] = status
        if tool_name:
            query["tool_name"] = tool_name
        records = list(db.creative_tool_runs.find(query).sort([("created_at", -1)]).limit(limit))
        records = apply_real_mode_filters(records, workspace_slug=workspace_slug, include_legacy=include_legacy, include_test=include_test)
        return {"items": serialize(records), "simulation_only": True}
    finally:
        client.close()


@app.post("/creative-tool-runs")
def trigger_creative_tool_run(payload: CreativeToolRunRequest) -> dict:
    now = utc_now()
    comfyui_enabled = env_enabled(os.getenv("COMFYUI_ENABLED", "false"))

    run_record: dict[str, Any] = {
        "workspace_slug": clean_text(payload.workspace_slug),
        "client_id": clean_text(payload.client_id),
        "snippet_id": clean_text(payload.snippet_id),
        "source_content_id": clean_text(payload.source_content_id),
        "tool_name": payload.tool_name,
        "workflow_path": clean_text(payload.workflow_path),
        "prompt_inputs": payload.prompt_inputs or {},
        "notes": clean_text(payload.notes),
        "status": "pending",
        "comfyui_enabled": comfyui_enabled,
        "simulation_only": True,
        "outbound_actions_taken": 0,
        "created_at": now,
        "updated_at": now,
    }

    client = get_client()
    try:
        db = get_database(client)
        result = db.creative_tool_runs.insert_one(run_record)
        run_id = result.inserted_id

        if payload.tool_name == "comfyui":
            if not comfyui_enabled:
                db.creative_tool_runs.update_one(
                    {"_id": run_id},
                    {"$set": {"status": "skipped", "skip_reason": "comfyui_disabled", "updated_at": utc_now()}},
                )
                created = db.creative_tool_runs.find_one({"_id": run_id})
                return {
                    "item": serialize(created),
                    "message": "ComfyUI is disabled. Tool run recorded but not executed. No post published or scheduled.",
                    "simulation_only": True,
                }

            try:
                from agents.comfyui_client import ComfyUIClient
                comfyui = ComfyUIClient()
                comfyui_result = comfyui.run_workflow(
                    workflow_path=clean_text(payload.workflow_path),
                    prompt_inputs=payload.prompt_inputs or {},
                )
                db.creative_tool_runs.update_one(
                    {"_id": run_id},
                    {"$set": {"status": "completed", "comfyui_result": comfyui_result, "updated_at": utc_now()}},
                )
            except Exception as exc:
                db.creative_tool_runs.update_one(
                    {"_id": run_id},
                    {
                        "$set": {
                            "status": "failed",
                            "error": f"{exc.__class__.__name__}: {exc}",
                            "updated_at": utc_now(),
                        }
                    },
                )
                created = db.creative_tool_runs.find_one({"_id": run_id})
                return {
                    "item": serialize(created),
                    "message": "ComfyUI tool run failed safely. No post published or scheduled.",
                    "simulation_only": True,
                    "error": f"{exc.__class__.__name__}: {exc}",
                }
        else:
            db.creative_tool_runs.update_one(
                {"_id": run_id},
                {"$set": {"status": "completed", "updated_at": utc_now()}},
            )

        created = db.creative_tool_runs.find_one({"_id": run_id})
        return {
            "item": serialize(created),
            "message": "Creative tool run recorded. No post published or scheduled.",
            "simulation_only": True,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Social Creative Engine v3 — Request Models
# ---------------------------------------------------------------------------


class SourceContentMetadataUpdateRequest(BaseModel):
    thumbnail_url: str = ""
    tags: list[str] = Field(default_factory=list)
    language: str = "en"
    content_type_hint: str = ""
    description: str = ""
    notes: str = ""


class AudioExtractionRunCreateRequest(BaseModel):
    workspace_slug: str = ""
    source_content_id: str = ""
    source_url: str = ""
    notes: str = ""


class TranscriptRunCreateRequest(BaseModel):
    workspace_slug: str = ""
    source_content_id: str = ""
    audio_extraction_run_id: str = ""
    provider: str = "stub"
    language: str = "en"
    text_hint: str = ""


class SnippetGenerationRequest(BaseModel):
    workspace_slug: str = ""
    source_content_id: str = ""
    transcript_run_id: str = ""
    max_snippets: int = Field(default=10, ge=1, le=50)
    min_score: float = Field(default=0.5, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Social Creative Engine v3 — Snippet scoring helpers
# ---------------------------------------------------------------------------

_HIGH_SIGNAL_WORDS = frozenset({
    "every", "always", "never", "secret", "biggest", "mistake",
    "important", "simple", "trust", "real", "proven", "booked",
    "week", "day", "results", "numbers", "system", "strategy",
    "consistent", "consistently", "nothing", "everything",
})

_THEME_MAP: dict[str, str] = {
    "trust": "trust_building",
    "real": "authenticity",
    "results": "results",
    "booked": "results",
    "numbers": "results",
    "system": "system",
    "strategy": "system",
    "mistake": "lessons",
    "simple": "simplicity",
    "every": "consistency",
    "always": "consistency",
    "consistently": "consistency",
    "week": "urgency",
    "day": "urgency",
    "important": "priority",
    "nothing": "origin_story",
}


def _score_segment(text: str) -> tuple[float, str]:
    """Heuristic scoring for a transcript segment.

    Returns (score: float, reason: str).
    Local computation only — no external API calls.
    """
    words = text.split()
    word_count = len(words)
    score = 0.5
    reasons: list[str] = []

    if 10 <= word_count <= 30:
        score += 0.2
        reasons.append("good length for social")
    elif word_count < 8:
        score -= 0.2
        reasons.append("too short")
    elif word_count > 40:
        score -= 0.1
        reasons.append("may be too long")

    keyword_hits = sum(
        1 for w in words if w.lower().rstrip(".,!?") in _HIGH_SIGNAL_WORDS
    )
    if keyword_hits >= 2:
        score += 0.15
        reasons.append("strong signal keywords")
    elif keyword_hits == 1:
        score += 0.05
        reasons.append("has signal keyword")

    if text.rstrip().endswith((".", "!", "?")):
        score += 0.05
        reasons.append("complete sentence")

    score = round(min(1.0, max(0.0, score)), 3)
    reason = "; ".join(reasons) if reasons else "heuristic score"
    return score, reason


def _infer_theme(text: str) -> str:
    words = [w.lower().rstrip(".,!?") for w in text.split()]
    for word in words:
        if word in _THEME_MAP:
            return _THEME_MAP[word]
    return "general"


# ---------------------------------------------------------------------------
# Social Creative Engine v3 — Part 1: Source Content Metadata Update
# ---------------------------------------------------------------------------


@app.patch("/source-content/{source_content_id}/metadata")
def update_source_content_metadata(
    source_content_id: str,
    payload: SourceContentMetadataUpdateRequest,
) -> dict:
    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)
        doc = find_source_content(db, source_content_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Source content not found.")
        update_fields = {
            "thumbnail_url": clean_text(payload.thumbnail_url),
            "tags": [clean_text(t) for t in payload.tags if clean_text(t)],
            "language": clean_text(payload.language) or "en",
            "content_type_hint": clean_text(payload.content_type_hint),
            "description": clean_text(payload.description),
            "notes": clean_text(payload.notes),
            "updated_at": now,
        }
        db.source_content.update_one({"_id": doc["_id"]}, {"$set": update_fields})
        updated = db.source_content.find_one({"_id": doc["_id"]})
        return {
            "item": serialize(updated),
            "message": "Source content metadata updated. No post published or scheduled.",
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Social Creative Engine v3 — Part 2: Audio Extraction Runs
# ---------------------------------------------------------------------------


@app.get("/audio-extraction-runs")
def list_audio_extraction_runs(
    workspace_slug: str = Query(""),
    source_content_id: str = "",
    status: str = "",
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if source_content_id:
            query["source_content_id"] = source_content_id
        if status:
            query["status"] = status
        records = list(
            db.audio_extraction_runs.find(query).sort([("created_at", -1)]).limit(limit)
        )
        records = apply_real_mode_filters(
            records,
            workspace_slug=workspace_slug,
            include_legacy=include_legacy,
            include_test=include_test,
        )
        return {"items": serialize(records), "simulation_only": True}
    finally:
        client.close()


@app.post("/audio-extraction-runs")
def create_audio_extraction_run(payload: AudioExtractionRunCreateRequest) -> dict:
    from audio_extractor import get_audio_extractor

    now = utc_now()
    extractor = get_audio_extractor()
    result = extractor.extract(source_url=clean_text(payload.source_url))

    record: dict[str, Any] = {
        "workspace_slug": clean_text(payload.workspace_slug),
        "source_content_id": clean_text(payload.source_content_id),
        "source_url": clean_text(payload.source_url),
        "notes": clean_text(payload.notes),
        "extractor": extractor.extractor_name,
        "status": result.status,
        "skip_reason": result.skip_reason,
        "output_path": result.output_path,
        "error": result.error,
        "simulation_only": True,
        "outbound_actions_taken": 0,
        "created_at": now,
        "updated_at": now,
    }
    client = get_client()
    try:
        db = get_database(client)
        res = db.audio_extraction_runs.insert_one(record)
        created = db.audio_extraction_runs.find_one({"_id": res.inserted_id})
        return {
            "item": serialize(created),
            "message": (
                "Audio extraction run recorded. FFMPEG disabled — no audio downloaded or processed."
                if result.skip_reason == "ffmpeg_disabled"
                else "Audio extraction run recorded. No post published or scheduled."
            ),
            "simulation_only": True,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Social Creative Engine v3 — Part 3: Transcript Runs and Segments
# ---------------------------------------------------------------------------


@app.get("/transcript-runs")
def list_transcript_runs(
    workspace_slug: str = Query(""),
    source_content_id: str = "",
    status: str = "",
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if source_content_id:
            query["source_content_id"] = source_content_id
        if status:
            query["status"] = status
        records = list(
            db.transcript_runs.find(query).sort([("created_at", -1)]).limit(limit)
        )
        records = apply_real_mode_filters(
            records,
            workspace_slug=workspace_slug,
            include_legacy=include_legacy,
            include_test=include_test,
        )
        return {"items": serialize(records), "simulation_only": True}
    finally:
        client.close()


@app.post("/transcript-runs")
def create_transcript_run(payload: TranscriptRunCreateRequest) -> dict:
    from transcript_provider import get_transcript_provider

    now = utc_now()
    provider = get_transcript_provider()
    segments = provider.transcribe(
        source_content_id=clean_text(payload.source_content_id),
        audio_path="",
        text_hint=clean_text(payload.text_hint),
    )

    run_record: dict[str, Any] = {
        "workspace_slug": clean_text(payload.workspace_slug),
        "source_content_id": clean_text(payload.source_content_id),
        "audio_extraction_run_id": clean_text(payload.audio_extraction_run_id),
        "provider": provider.provider_name,
        "language": clean_text(payload.language) or "en",
        "segment_count": len(segments),
        "status": "complete",
        "simulation_only": True,
        "outbound_actions_taken": 0,
        "created_at": now,
        "updated_at": now,
    }

    client = get_client()
    try:
        db = get_database(client)
        res = db.transcript_runs.insert_one(run_record)
        run_id = res.inserted_id

        for seg in segments:
            seg_record: dict[str, Any] = {
                "workspace_slug": clean_text(payload.workspace_slug),
                "source_content_id": clean_text(payload.source_content_id),
                "transcript_run_id": str(run_id),
                "index": seg["index"],
                "start_ms": seg["start_ms"],
                "end_ms": seg["end_ms"],
                "text": seg["text"],
                "speaker": seg["speaker"],
                "confidence": seg["confidence"],
                "provider": seg["provider"],
                "simulation_only": True,
                "outbound_actions_taken": 0,
                "created_at": now,
            }
            db.transcript_segments.insert_one(seg_record)

        created = db.transcript_runs.find_one({"_id": run_id})
        return {
            "item": serialize(created),
            "segment_count": len(segments),
            "message": (
                f"Transcript run complete. {len(segments)} segments created. "
                "No post published or scheduled."
            ),
            "simulation_only": True,
        }
    finally:
        client.close()


@app.get("/transcript-segments")
def list_transcript_segments(
    workspace_slug: str = Query(""),
    transcript_run_id: str = "",
    source_content_id: str = "",
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if transcript_run_id:
            query["transcript_run_id"] = transcript_run_id
        if source_content_id:
            query["source_content_id"] = source_content_id
        records = list(
            db.transcript_segments.find(query).sort([("index", 1)]).limit(limit)
        )
        records = apply_real_mode_filters(
            records,
            workspace_slug=workspace_slug,
            include_legacy=include_legacy,
            include_test=include_test,
        )
        return {"items": serialize(records), "simulation_only": True}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Social Creative Engine v3 — Part 4: Snippet Generation
# ---------------------------------------------------------------------------


@app.post("/source-content/{source_content_id}/generate-snippets")
def generate_snippets_from_transcript(
    source_content_id: str,
    payload: SnippetGenerationRequest,
) -> dict:
    now = utc_now()
    workspace_slug = clean_text(payload.workspace_slug)
    transcript_run_id = clean_text(payload.transcript_run_id)

    client = get_client()
    try:
        db = get_database(client)

        seg_query: dict[str, Any] = {"source_content_id": source_content_id}
        if transcript_run_id:
            seg_query["transcript_run_id"] = transcript_run_id
        segments = list(db.transcript_segments.find(seg_query).sort([("index", 1)]))

        if not segments:
            return {
                "items": [],
                "created_count": 0,
                "message": "No transcript segments found for this source content.",
                "simulation_only": True,
            }

        candidates: list[tuple[float, str, dict]] = []
        for seg in segments:
            score, reason = _score_segment(seg.get("text", ""))
            if score >= payload.min_score:
                candidates.append((score, reason, seg))

        candidates.sort(key=lambda x: x[0], reverse=True)
        top_candidates = candidates[: payload.max_snippets]

        created_snippets = []
        for score, reason, seg in top_candidates:
            start_s = round(seg.get("start_ms", 0) / 1000, 3)
            end_s = round(seg.get("end_ms", 0) / 1000, 3)
            theme = _infer_theme(seg.get("text", ""))
            snippet_record: dict[str, Any] = {
                "workspace_slug": workspace_slug,
                "source_content_id": source_content_id,
                "transcript_run_id": transcript_run_id,
                "transcript_id": transcript_run_id,
                "speaker": seg.get("speaker", ""),
                "start_time": start_s,
                "end_time": end_s,
                "transcript_text": seg.get("text", ""),
                "score": score,
                "score_reason": reason,
                "theme": theme,
                "hook_angle": "",
                "platform_fit": [],
                "status": "needs_review",
                "review_events": [],
                "generation_source": "auto",
                "segment_index": seg.get("index", 0),
                "simulation_only": True,
                "outbound_actions_taken": 0,
                "created_at": now,
                "updated_at": now,
            }
            insert_res = db.content_snippets.insert_one(snippet_record)
            created = db.content_snippets.find_one({"_id": insert_res.inserted_id})
            created_snippets.append(serialize(created))

        return {
            "items": created_snippets,
            "created_count": len(created_snippets),
            "segment_count": len(segments),
            "message": (
                f"{len(created_snippets)} snippet candidates created from "
                f"{len(segments)} transcript segments. "
                "All require operator review. No post published or scheduled."
            ),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


# ===========================================================================
# Social Creative Engine v4 — Media Intake, Approval Gates, FFmpeg
# ===========================================================================
#
# v4 adds:
#   1. MediaIntakeRecord registration (local file or URL metadata)
#   2. Approval gate on source content before audio extraction
#   3. FFmpegAudioExtractor support when FFMPEG_ENABLED=true
#   4. Approval gate: audio extraction must complete before transcript
#      (unless stub/manual text_hint is used)
#   5. Approval gate: transcript must exist before snippet generation
#   6. Source content status update endpoint
#
# Safety: all records carry simulation_only=True, outbound_actions_taken=0.
# ===========================================================================


# ---------------------------------------------------------------------------
# v4 Pydantic models
# ---------------------------------------------------------------------------

class MediaIntakeCreateRequest(BaseModel):
    workspace_slug: str = ""
    source_content_id: str = ""
    media_path: str = ""          # local file path (preferred)
    source_url: str = ""          # URL for metadata-only registration
    notes: str = ""


class SourceContentStatusUpdateRequest(BaseModel):
    status: Literal["needs_review", "approved", "rejected"]
    note: str = ""


# ---------------------------------------------------------------------------
# v4 helper: find_audio_extraction_run
# ---------------------------------------------------------------------------

def find_audio_extraction_run(db, run_id: str) -> dict | None:
    query: dict[str, Any] = {"_id": run_id}
    if ObjectId.is_valid(run_id):
        query = {"$or": [{"_id": ObjectId(run_id)}, {"_id": run_id}]}
    return db.audio_extraction_runs.find_one(query)


def find_transcript_run(db, run_id: str) -> dict | None:
    query: dict[str, Any] = {"_id": run_id}
    if ObjectId.is_valid(run_id):
        query = {"$or": [{"_id": ObjectId(run_id)}, {"_id": run_id}]}
    return db.transcript_runs.find_one(query)


# ---------------------------------------------------------------------------
# v4 — Part 1: Source Content Status Update
# ---------------------------------------------------------------------------

@app.patch("/source-content/{source_content_id}/status")
def update_source_content_status(
    source_content_id: str,
    payload: SourceContentStatusUpdateRequest,
) -> dict:
    """
    Approve or reject a source content item.

    Source content must be approved before audio extraction can proceed.
    """
    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)
        doc = find_source_content(db, source_content_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Source content not found.")

        update_fields: dict[str, Any] = {
            "status": payload.status,
            "updated_at": now,
        }
        if payload.note.strip():
            update_fields["status_note"] = clean_text(payload.note)

        db.source_content.update_one({"_id": doc["_id"]}, {"$set": update_fields})
        updated = db.source_content.find_one({"_id": doc["_id"]})
        return {
            "item": serialize(updated),
            "message": (
                f"Source content status updated to '{payload.status}'. "
                "No post published or scheduled."
            ),
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# v4 — Part 2: Media Intake Registration
# ---------------------------------------------------------------------------

@app.post("/media-intake-records")
def create_media_intake_record(payload: MediaIntakeCreateRequest) -> dict:
    """
    Register a local media file or URL metadata for a source content item.

    For local files: validates path and extension; does not read file contents.
    For URLs: stores metadata only; never fetches the URL.

    Gate: source content must have status='approved'.
    """
    from media_intake import register_local_file, register_url_metadata

    now = utc_now()
    workspace_slug = clean_text(payload.workspace_slug)
    source_content_id = clean_text(payload.source_content_id)

    client = get_client()
    try:
        db = get_database(client)

        # Approval gate
        content_doc = find_source_content(db, source_content_id) if source_content_id else None
        if source_content_id and content_doc and content_doc.get("status") != "approved":
            raise HTTPException(
                status_code=422,
                detail=(
                    "Source content must be approved before registering media. "
                    f"Current status: '{content_doc.get('status', 'unknown')}'."
                ),
            )

        media_path = clean_text(payload.media_path)
        source_url = clean_text(payload.source_url)

        if media_path:
            result = register_local_file(media_path)
        elif source_url:
            result = register_url_metadata(source_url)
        else:
            raise HTTPException(
                status_code=400,
                detail="Either media_path or source_url is required.",
            )

        record: dict[str, Any] = {
            "workspace_slug": workspace_slug,
            "source_content_id": source_content_id,
            "intake_method": result.intake_method,
            "status": result.status,
            "media_path": result.media_path,
            "source_url": result.source_url or source_url,
            "extension": result.extension,
            "approved_for_download": False,  # always starts False; operator must set explicitly
            "error": result.error,
            "skip_reason": result.skip_reason,
            "notes": clean_text(payload.notes),
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "created_at": now,
            "updated_at": now,
        }
        res = db.media_intake_records.insert_one(record)
        created = db.media_intake_records.find_one({"_id": res.inserted_id})
        return {
            "item": serialize(created),
            "message": (
                f"Media intake record created (method: {result.intake_method}). "
                "No file downloaded. No content published."
            ),
            "simulation_only": True,
        }
    finally:
        client.close()


@app.get("/media-intake-records")
def list_media_intake_records(
    workspace_slug: str = Query(""),
    source_content_id: str = "",
    status: str = "",
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if source_content_id:
            query["source_content_id"] = source_content_id
        if status:
            query["status"] = status
        records = list(
            db.media_intake_records.find(query).sort([("created_at", -1)]).limit(limit)
        )
        records = apply_real_mode_filters(
            records,
            workspace_slug=workspace_slug,
            include_legacy=include_legacy,
            include_test=include_test,
        )
        return {"items": serialize(records), "simulation_only": True}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# v4 — Part 3: Audio Extraction with approval gate + media_path support
# ---------------------------------------------------------------------------
# Overrides v3 POST /audio-extraction-runs with approval gate + media_path.
# The GET /audio-extraction-runs endpoint from v3 is reused unchanged.

@app.post("/audio-extraction-runs/v4")
def create_audio_extraction_run_v4(payload: AudioExtractionRunCreateRequest) -> dict:
    """
    Create an audio extraction run with v4 approval gate.

    Gate: source content must be status='approved'.
    If FFMPEG_ENABLED=true, uses FFmpegAudioExtractor with media_path.
    If FFMPEG_ENABLED=false (default), returns skipped safely.
    """
    from audio_extractor import get_audio_extractor, FFmpegAudioExtractor

    now = utc_now()
    workspace_slug = clean_text(payload.workspace_slug)
    source_content_id = clean_text(payload.source_content_id)

    client = get_client()
    try:
        db = get_database(client)

        # Approval gate
        content_doc = find_source_content(db, source_content_id) if source_content_id else None
        if source_content_id and content_doc and content_doc.get("status") != "approved":
            raise HTTPException(
                status_code=422,
                detail=(
                    "Source content must be approved before audio extraction. "
                    f"Current status: '{content_doc.get('status', 'unknown')}'."
                ),
            )

        extractor = get_audio_extractor()
        media_path = clean_text(payload.notes)  # notes field reused as media_path hint

        # Resolve media_path from registered intake records
        intake_doc = db.media_intake_records.find_one(
            {"source_content_id": source_content_id, "intake_method": "local_file", "status": "registered"}
        ) if source_content_id else None
        resolved_media_path = (
            intake_doc.get("media_path", "") if intake_doc else ""
        )

        output_dir = os.getenv("FFMPEG_OUTPUT_DIR", "/tmp/signalforge_audio")
        result = extractor.extract(
            source_url=clean_text(payload.source_url),
            media_path=resolved_media_path,
            output_dir=output_dir,
        )

        record: dict[str, Any] = {
            "workspace_slug": workspace_slug,
            "source_content_id": source_content_id,
            "source_url": clean_text(payload.source_url),
            "media_path": resolved_media_path,
            "notes": clean_text(payload.notes),
            "extractor": result.extractor,
            "status": result.status,
            "skip_reason": result.skip_reason,
            "output_path": result.output_path,
            "duration_seconds": getattr(result, "duration_seconds", 0.0),
            "error": result.error,
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "created_at": now,
            "updated_at": now,
        }

        res = db.audio_extraction_runs.insert_one(record)
        created = db.audio_extraction_runs.find_one({"_id": res.inserted_id})

        if result.status == "skipped":
            msg = "Audio extraction skipped — FFMPEG disabled. No audio downloaded or processed."
        elif result.status == "complete":
            msg = f"Audio extracted to {result.output_path}. No content published."
        else:
            msg = f"Audio extraction failed: {result.error}"

        return {
            "item": serialize(created),
            "message": msg,
            "simulation_only": True,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# v4 — Part 4: Transcript run with approval gate
# ---------------------------------------------------------------------------
# Overrides v3 POST /transcript-runs with stricter approval chain.
# GET /transcript-runs and GET /transcript-segments are reused unchanged.

@app.post("/transcript-runs/v4")
def create_transcript_run_v4(payload: TranscriptRunCreateRequest) -> dict:
    """
    Create a transcript run with v4 approval gate.

    Gate: if audio_extraction_run_id is provided, that run must exist and
    have status='complete'. If no run_id is given, only the stub provider
    (or a manual text_hint) is allowed — this enables stub/manual text flow
    without requiring FFmpeg.
    """
    from transcript_provider import get_transcript_provider

    now = utc_now()
    workspace_slug = clean_text(payload.workspace_slug)
    source_content_id = clean_text(payload.source_content_id)
    audio_run_id = clean_text(payload.audio_extraction_run_id)

    client = get_client()
    try:
        db = get_database(client)

        # Approval gate: if audio run id is given, it must be complete
        if audio_run_id:
            audio_run = find_audio_extraction_run(db, audio_run_id)
            if not audio_run:
                raise HTTPException(
                    status_code=422,
                    detail=f"Audio extraction run '{audio_run_id}' not found.",
                )
            if audio_run.get("status") not in ("complete", "skipped"):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Audio extraction run must be complete (or skipped/stub) "
                        f"before transcript generation. Current status: '{audio_run.get('status')}'."
                    ),
                )

        provider = get_transcript_provider()
        # Pass audio path from extraction run if available
        audio_path = ""
        if audio_run_id:
            audio_run = find_audio_extraction_run(db, audio_run_id)
            if audio_run:
                audio_path = audio_run.get("output_path", "")

        segments = provider.transcribe(
            source_content_id=source_content_id,
            audio_path=audio_path,
            text_hint=clean_text(payload.text_hint),
        )

        run_record: dict[str, Any] = {
            "workspace_slug": workspace_slug,
            "source_content_id": source_content_id,
            "audio_extraction_run_id": audio_run_id,
            "provider": provider.provider_name,
            "language": clean_text(payload.language) or "en",
            "segment_count": len(segments),
            "status": "complete",
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "created_at": now,
            "updated_at": now,
        }

        res = db.transcript_runs.insert_one(run_record)
        run_id = res.inserted_id

        for seg in segments:
            seg_record: dict[str, Any] = {
                "workspace_slug": workspace_slug,
                "source_content_id": source_content_id,
                "transcript_run_id": str(run_id),
                "index": seg["index"],
                "start_ms": seg["start_ms"],
                "end_ms": seg["end_ms"],
                "text": seg["text"],
                "speaker": seg["speaker"],
                "confidence": seg["confidence"],
                "provider": seg["provider"],
                "simulation_only": True,
                "outbound_actions_taken": 0,
                "created_at": now,
            }
            db.transcript_segments.insert_one(seg_record)

        created = db.transcript_runs.find_one({"_id": run_id})
        return {
            "item": serialize(created),
            "segment_count": len(segments),
            "message": (
                f"Transcript run complete. {len(segments)} segments created. "
                "No post published or scheduled."
            ),
            "simulation_only": True,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# v4 — Part 5: Snippet generation with transcript gate
# ---------------------------------------------------------------------------

@app.post("/source-content/{source_content_id}/generate-snippets/v4")
def generate_snippets_from_transcript_v4(
    source_content_id: str,
    payload: SnippetGenerationRequest,
) -> dict:
    """
    Generate snippet candidates with v4 approval gate.

    Gate: a transcript run with status='complete' must exist for this
    source_content_id before snippet generation is permitted.
    """
    now = utc_now()
    workspace_slug = clean_text(payload.workspace_slug)
    transcript_run_id = clean_text(payload.transcript_run_id)

    client = get_client()
    try:
        db = get_database(client)

        # Approval gate: at least one completed transcript run must exist
        transcript_query: dict[str, Any] = {
            "source_content_id": source_content_id,
            "status": "complete",
        }
        if transcript_run_id:
            transcript_query["_id_str"] = transcript_run_id  # resolved below

        existing_run = None
        if transcript_run_id:
            existing_run = find_transcript_run(db, transcript_run_id)
            if not existing_run:
                raise HTTPException(
                    status_code=422,
                    detail=f"Transcript run '{transcript_run_id}' not found.",
                )
            if existing_run.get("status") != "complete":
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Transcript run must be complete before generating snippets. "
                        f"Current status: '{existing_run.get('status')}'."
                    ),
                )
        else:
            # No specific run given — check any completed run for this content
            completed = db.transcript_runs.find_one(
                {"source_content_id": source_content_id, "status": "complete"}
            )
            if not completed:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "No completed transcript run found for this source content. "
                        "Run a transcript first."
                    ),
                )

        # Fetch segments
        seg_query: dict[str, Any] = {"source_content_id": source_content_id}
        if transcript_run_id:
            seg_query["transcript_run_id"] = transcript_run_id
        segments = list(db.transcript_segments.find(seg_query).sort([("index", 1)]))

        if not segments:
            return {
                "items": [],
                "created_count": 0,
                "message": "No transcript segments found for this source content.",
                "simulation_only": True,
            }

        candidates: list[tuple[float, str, dict]] = []
        for seg in segments:
            score, reason = _score_segment(seg.get("text", ""))
            if score >= payload.min_score:
                candidates.append((score, reason, seg))

        candidates.sort(key=lambda x: x[0], reverse=True)
        top_candidates = candidates[: payload.max_snippets]

        created_snippets = []
        for score, reason, seg in top_candidates:
            start_s = round(seg.get("start_ms", 0) / 1000, 3)
            end_s = round(seg.get("end_ms", 0) / 1000, 3)
            theme = _infer_theme(seg.get("text", ""))
            snippet_record: dict[str, Any] = {
                "workspace_slug": workspace_slug,
                "source_content_id": source_content_id,
                "transcript_run_id": transcript_run_id,
                "transcript_id": transcript_run_id,
                "speaker": seg.get("speaker", ""),
                "start_time": start_s,
                "end_time": end_s,
                "transcript_text": seg.get("text", ""),
                "score": score,
                "score_reason": reason,
                "theme": theme,
                "hook_angle": "",
                "platform_fit": [],
                "status": "needs_review",
                "review_events": [],
                "generation_source": "auto",
                "segment_index": seg.get("index", 0),
                "simulation_only": True,
                "outbound_actions_taken": 0,
                "created_at": now,
                "updated_at": now,
            }
            insert_res = db.content_snippets.insert_one(snippet_record)
            created = db.content_snippets.find_one({"_id": insert_res.inserted_id})
            created_snippets.append(serialize(created))

        return {
            "items": created_snippets,
            "created_count": len(created_snippets),
            "segment_count": len(segments),
            "message": (
                f"{len(created_snippets)} snippet candidates created from "
                f"{len(segments)} transcript segments. "
                "All require operator review. No post published or scheduled."
            ),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()



# ---------------------------------------------------------------------------
# Social Creative Engine v4.5 — Prompt Generator Library
# ---------------------------------------------------------------------------
# Generates structured visual prompts for faceless short-form creative content.
# All prompts are stored with status='draft' and require operator review before
# any asset generation can occur.  No external API calls are made.
# ---------------------------------------------------------------------------


class PromptGenerationCreateRequest(BaseModel):
    workspace_slug: str
    client_id: str = ""
    snippet_id: str = ""
    brief_id: str = ""
    prompt_type: Literal[
        "faceless_motivational",
        "cinematic_broll",
        "abstract_motion",
        "business_explainer",
        "quote_card_motion",
        "podcast_clip_visual",
        "educational_breakdown",
        "luxury_brand_story",
        "product_service_ad",
    ] = "faceless_motivational"
    generation_engine_target: Literal[
        "comfyui", "seedance", "higgsfield", "runway", "manual"
    ] = "comfyui"
    use_likeness: bool = False
    notes: str = ""


class PromptGenerationReviewRequest(BaseModel):
    decision: Literal["approve", "reject", "revise"]
    note: str = ""


def find_prompt_generation(db: Any, gen_id: str) -> dict | None:
    """Return a single prompt_generations record by str or ObjectId."""
    record = db.prompt_generations.find_one({"_id": gen_id})
    if record:
        return record
    try:
        record = db.prompt_generations.find_one({"_id": ObjectId(gen_id)})
    except Exception:
        pass
    return record


@app.post("/prompt-generations")
def create_prompt_generation(payload: PromptGenerationCreateRequest):
    """
    Generate a visual prompt from an approved content snippet.

    Rules
    -----
    * The snippet must exist and have ``status='approved'``.
    * ``use_likeness=True`` requires avatar_permissions or likeness_permissions
      on the client profile; returns 422 otherwise.
    * No external calls are made.  ``simulation_only`` is always ``True``.
    """
    client = get_client()
    try:
        db = get_database(client)

        # Validate snippet exists and is approved
        snippet = None
        if payload.snippet_id:
            snippet = db.content_snippets.find_one({"_id": payload.snippet_id})
            if not snippet:
                try:
                    snippet = db.content_snippets.find_one(
                        {"_id": ObjectId(payload.snippet_id)}
                    )
                except Exception:
                    pass
        if not snippet:
            raise HTTPException(
                status_code=404, detail="Snippet not found."
            )
        if snippet.get("status") != "approved":
            raise HTTPException(
                status_code=422,
                detail=(
                    "Snippet must be in 'approved' status before generating a "
                    "visual prompt. Current status: "
                    f"'{snippet.get('status', 'unknown')}'."
                ),
            )

        # Fetch client profile for permissions check
        client_profile: dict = {}
        if payload.client_id:
            client_profile = db.companies.find_one({"_id": payload.client_id}) or {}
            if not client_profile:
                try:
                    client_profile = (
                        db.companies.find_one({"_id": ObjectId(payload.client_id)}) or {}
                    )
                except Exception:
                    pass

        avatar_permissions: bool = bool(client_profile.get("avatar_permissions", False))
        likeness_permissions: bool = bool(
            client_profile.get("likeness_permissions", False)
        )

        # Likeness gate
        if payload.use_likeness and not (avatar_permissions or likeness_permissions):
            raise HTTPException(
                status_code=422,
                detail=(
                    "use_likeness=True requires avatar_permissions or "
                    "likeness_permissions on the client profile. "
                    "Update the client profile before enabling likeness prompts."
                ),
            )

        # Load brief if provided
        brief: dict = {}
        if payload.brief_id:
            brief = db.briefs.find_one({"_id": payload.brief_id}) or {}
            if not brief:
                try:
                    brief = db.briefs.find_one({"_id": ObjectId(payload.brief_id)}) or {}
                except Exception:
                    pass

        # Guard: ensure prompt_generator module loaded
        if _generate_visual_prompt is None:
            raise HTTPException(
                status_code=500,
                detail="Prompt generator module is unavailable.",
            )

        snippet_text: str = snippet.get("transcript_text", "")
        source_url: str = snippet.get("source_url", "")
        snippet_usage_status: str = snippet.get("status", "")

        try:
            result = _generate_visual_prompt(
                prompt_type=payload.prompt_type,
                snippet_text=snippet_text,
                brief=brief,
                engine=payload.generation_engine_target,
                client_id=payload.client_id,
                snippet_id=payload.snippet_id,
                brief_id=payload.brief_id,
                source_url=source_url,
                snippet_usage_status=snippet_usage_status,
                avatar_permissions=avatar_permissions,
                likeness_permissions=likeness_permissions,
                use_likeness=payload.use_likeness,
            )
        except (ValueError, PermissionError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        now = datetime.now(timezone.utc).isoformat()
        record = {
            "workspace_slug": payload.workspace_slug,
            "client_id": payload.client_id,
            "snippet_id": payload.snippet_id,
            "brief_id": payload.brief_id,
            "prompt_type": result.prompt_type,
            "generation_engine_target": result.generation_engine_target,
            "positive_prompt": result.positive_prompt,
            "negative_prompt": result.negative_prompt,
            "visual_style": result.visual_style,
            "camera_direction": result.camera_direction,
            "lighting": result.lighting,
            "motion_notes": result.motion_notes,
            "scene_beats": result.scene_beats,
            "caption_overlay_suggestion": result.caption_overlay_suggestion,
            "safety_notes": result.safety_notes,
            "status": "draft",
            "review_events": [],
            "notes": payload.notes,
            "use_likeness": payload.use_likeness,
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "source_url": result.source_url,
            "snippet_transcript": result.snippet_transcript,
            "snippet_usage_status": result.snippet_usage_status,
            "created_at": now,
            "updated_at": now,
        }

        insert_res = db.prompt_generations.insert_one(record)
        created = db.prompt_generations.find_one({"_id": insert_res.inserted_id})

        return {
            "item": serialize(created),
            "message": (
                "Visual prompt generated and saved as draft. "
                "Requires operator review before any asset generation."
            ),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.get("/prompt-generations")
def list_prompt_generations(
    workspace_slug: str = Query(""),
    snippet_id: str = Query(""),
    client_id: str = Query(""),
    brief_id: str = Query(""),
    status: str = Query(""),
    prompt_type: str = Query(""),
    generation_engine_target: str = Query(""),
    demo: str = Query("false"),
):
    """List prompt generation records with optional filters."""
    client = get_client()
    try:
        db = get_database(client)

        query: dict = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if snippet_id:
            query["snippet_id"] = snippet_id
        if client_id:
            query["client_id"] = client_id
        if brief_id:
            query["brief_id"] = brief_id
        if status:
            query["status"] = status
        if prompt_type:
            query["prompt_type"] = prompt_type
        if generation_engine_target:
            query["generation_engine_target"] = generation_engine_target

        # Exclude demo workspace when not in demo mode
        demo_flag = str(demo).lower() not in ("true", "1")
        if demo_flag and not workspace_slug:
            query["workspace_slug"] = {"$nin": ["demo", "test"]}
        elif demo_flag and workspace_slug and workspace_slug in ("demo", "test"):
            return {
                "items": [],
                "count": 0,
                "simulation_only": True,
                "outbound_actions_taken": 0,
            }

        raw_items = [serialize(r) for r in db.prompt_generations.find(query)]
        items = apply_real_mode_filters(raw_items, workspace_slug=workspace_slug)

        return {
            "items": items,
            "count": len(items),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.post("/prompt-generations/{gen_id}/review")
def review_prompt_generation(gen_id: str, payload: PromptGenerationReviewRequest):
    """
    Approve, reject, or request revision on a prompt generation record.

    * ``approve`` -> status becomes ``'approved'``
    * ``reject``  -> status becomes ``'rejected'``
    * ``revise``  -> status becomes ``'needs_revision'``
    """
    client = get_client()
    try:
        db = get_database(client)

        record = find_prompt_generation(db, gen_id)
        if not record:
            raise HTTPException(status_code=404, detail="Prompt generation not found.")

        status_map = {
            "approve": "approved",
            "reject": "rejected",
            "revise": "needs_revision",
        }
        new_status = status_map[payload.decision]

        now = datetime.now(timezone.utc).isoformat()
        review_event = {
            "decision": payload.decision,
            "note": payload.note,
            "reviewed_at": now,
        }

        db.prompt_generations.update_one(
            {"_id": record["_id"]},
            {
                "$set": {"status": new_status, "updated_at": now},
                "$push": {"review_events": review_event},
            },
        )

        updated = find_prompt_generation(db, str(record["_id"]))

        return {
            "item": serialize(updated),
            "message": f"Prompt generation {payload.decision}d.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


# ===========================================================================
# Social Creative Engine v5 — Asset Rendering
# ===========================================================================

# ---------------------------------------------------------------------------
# v5: video_assembler import (graceful degradation if not available)
# ---------------------------------------------------------------------------

try:
    from video_assembler import assemble_video as _assemble_video  # type: ignore
    _VIDEO_ASSEMBLER_AVAILABLE = True
except Exception:
    _assemble_video = None  # type: ignore
    _VIDEO_ASSEMBLER_AVAILABLE = False


# ---------------------------------------------------------------------------
# v5: Request / Response models
# ---------------------------------------------------------------------------


class AssetRenderRequest(BaseModel):
    workspace_slug: str = ""
    client_id: str = ""
    snippet_id: str
    prompt_generation_id: str
    asset_type: str = "video"
    generation_engine: str = "comfyui"
    source_audio_path: str = ""
    add_captions: bool = False
    notes: str = ""


class AssetRenderReviewRequest(BaseModel):
    decision: str  # "approve" | "reject" | "revise"
    note: str = ""


# ---------------------------------------------------------------------------
# v5: Helper
# ---------------------------------------------------------------------------


def find_asset_render(db: Any, render_id: str) -> dict | None:
    """Lookup asset render by string id or ObjectId."""
    try:
        record = db.asset_renders.find_one({"_id": ObjectId(render_id)})
        if record:
            return record
    except Exception:
        pass
    return db.asset_renders.find_one({"_id": render_id})


# ---------------------------------------------------------------------------
# v5: Endpoints
# ---------------------------------------------------------------------------


@app.post("/assets/render")
def render_asset(payload: AssetRenderRequest) -> dict:
    """
    Enqueue an asset render from an approved snippet + approved prompt_generation.

    Validates both prerequisites, creates a render record (status=queued), then:
    - If Redis is reachable: enqueues the job and returns immediately (async path).
    - If Redis unavailable: falls back to synchronous inline rendering (sync path).

    ComfyUI and FFmpeg are individually gated via environment variables.
    All results are simulation_only=True; no external content is published.
    """
    now = utc_now()
    comfyui_enabled = env_enabled(os.getenv("COMFYUI_ENABLED", "false"))
    ffmpeg_enabled = env_enabled(os.getenv("FFMPEG_ENABLED", "false"))

    client = get_client()
    try:
        db = get_database(client)

        # --- Validate snippet ---
        snippet = None
        try:
            snippet = db.content_snippets.find_one({"_id": ObjectId(clean_text(payload.snippet_id))})
        except Exception:
            pass
        if not snippet:
            snippet = db.content_snippets.find_one({"_id": clean_text(payload.snippet_id)})
        if not snippet:
            raise HTTPException(status_code=404, detail="Snippet not found.")
        if snippet.get("status") != "approved":
            raise HTTPException(
                status_code=422,
                detail=f"Snippet must be approved before rendering. Current status: {snippet.get('status', 'unknown')}",
            )

        # --- Validate prompt_generation ---
        prompt_gen = find_prompt_generation(db, clean_text(payload.prompt_generation_id))
        if not prompt_gen:
            raise HTTPException(status_code=404, detail="Prompt generation not found.")
        if prompt_gen.get("status") != "approved":
            raise HTTPException(
                status_code=422,
                detail=f"Prompt generation must be approved before rendering. Current status: {prompt_gen.get('status', 'unknown')}",
            )

        # --- Create the render record (status: queued) ---
        render_record: dict[str, Any] = {
            "workspace_slug": clean_text(payload.workspace_slug),
            "client_id": clean_text(payload.client_id),
            "snippet_id": clean_text(payload.snippet_id),
            "prompt_generation_id": clean_text(payload.prompt_generation_id),
            "asset_type": payload.asset_type,
            "generation_engine": clean_text(payload.generation_engine),
            "source_audio_path": clean_text(payload.source_audio_path),
            "add_captions": payload.add_captions,
            "notes": clean_text(payload.notes),
            "status": "queued",
            "comfyui_enabled": comfyui_enabled,
            "ffmpeg_enabled": ffmpeg_enabled,
            "comfyui_result": {},
            "assembly_result": {},
            "assembly_status": "",
            "assembly_engine": "",
            "image_source": "",
            "comfyui_partial_failure": False,
            "file_path": "",
            "duration_seconds": 0.0,
            "resolution": "1080x1920",
            "review_events": [],
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "created_at": now,
            "updated_at": now,
        }
        insert_result = db.asset_renders.insert_one(render_record)
        render_id = insert_result.inserted_id
        render_id_str = str(render_id)

        # --- Try to enqueue for async worker processing ---
        job_id: Any = None
        try:
            from job_queue import enqueue_render_job  # type: ignore
            job_id = enqueue_render_job(
                render_id_str,
                {
                    "workspace_slug": clean_text(payload.workspace_slug),
                    "snippet_id": clean_text(payload.snippet_id),
                    "prompt_generation_id": clean_text(payload.prompt_generation_id),
                    "generation_engine": clean_text(payload.generation_engine),
                    "source_audio_path": clean_text(payload.source_audio_path),
                    "add_captions": payload.add_captions,
                },
            )
        except Exception:
            job_id = None

        # --- If Redis is available the job is queued — return immediately ---
        if job_id is not None:
            created = db.asset_renders.find_one({"_id": render_id})
            return {
                "item": serialize(created),
                "job_id": job_id,
                "queued": True,
                "message": "Render job queued. Worker will process asynchronously. No content published or scheduled.",
                "simulation_only": True,
                "outbound_actions_taken": 0,
            }

        # --- Synchronous fallback (Redis unavailable) ---
        # Perform the full pipeline inline so callers without a worker still
        # get a result.  Existing tests rely on this path.

        # ComfyUI step
        comfyui_result: dict[str, Any] = {}
        generated_image_path = ""
        if comfyui_enabled:
            try:
                from agents.comfyui_client import ComfyUIClient  # type: ignore
                comfyui = ComfyUIClient()
                comfyui_result = comfyui.run_from_prompt_generation(
                    serialize(prompt_gen),
                    workflow_path=os.getenv("COMFYUI_WORKFLOW_PATH", ""),
                )
            except Exception as exc:
                comfyui_result = {
                    "error": f"{exc.__class__.__name__}: {exc}",
                    "simulation_only": True,
                    "outbound_actions_taken": 0,
                }
        else:
            comfyui_result = {
                "skipped": True,
                "skip_reason": "comfyui_disabled",
                "mock_image_path": f"/tmp/signalforge_renders/mock_comfyui_{render_id_str}.png",
                "simulation_only": True,
                "outbound_actions_taken": 0,
            }
            generated_image_path = comfyui_result["mock_image_path"]

        db.asset_renders.update_one(
            {"_id": render_id},
            {"$set": {"status": "generated", "comfyui_result": comfyui_result, "updated_at": utc_now()}},
        )

        # FFmpeg / video assembly step
        assembly_result: dict[str, Any] = {}
        final_file_path = ""
        duration_seconds = float(snippet.get("duration_seconds") or 30.0)

        if _VIDEO_ASSEMBLER_AVAILABLE and _assemble_video is not None:
            caption_text = ""
            if payload.add_captions:
                caption_text = (
                    prompt_gen.get("caption_overlay_suggestion")
                    or snippet.get("transcript_text", "")[:120]
                    or ""
                )
            va_result = _assemble_video(
                image_path=generated_image_path,
                audio_path=clean_text(payload.source_audio_path),
                duration_seconds=duration_seconds,
                add_captions=payload.add_captions,
                caption_text=caption_text,
                resolution="1080x1920",
                generation_engine=clean_text(payload.generation_engine),
                asset_render_id=render_id_str,
            )
            assembly_result = va_result.to_dict()
            final_file_path = va_result.file_path
        else:
            assembly_result = {
                "skipped": True,
                "skip_reason": "video_assembler_unavailable",
                "mock": True,
                "mock_file_path": f"/tmp/signalforge_renders/mock_{render_id_str}.mp4",
                "simulation_only": True,
                "outbound_actions_taken": 0,
            }
            final_file_path = assembly_result["mock_file_path"]

        # Transition to needs_review
        db.asset_renders.update_one(
            {"_id": render_id},
            {
                "$set": {
                    "status": "needs_review",
                    "assembly_result": assembly_result,
                    "file_path": final_file_path,
                    "duration_seconds": duration_seconds,
                    "updated_at": utc_now(),
                }
            },
        )

        created = db.asset_renders.find_one({"_id": render_id})
        return {
            "item": serialize(created),
            "queued": False,
            "message": "Asset render complete (synchronous fallback). Awaiting operator review. No content published or scheduled.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.get("/assets")
def list_asset_renders(
    workspace_slug: str = Query(""),
    client_id: str = "",
    snippet_id: str = "",
    prompt_generation_id: str = "",
    status: str = "",
    asset_type: str = "",
    generation_engine: str = "",
    include_legacy: bool = Query(False),
    include_test: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if client_id:
            query["client_id"] = client_id
        if snippet_id:
            query["snippet_id"] = snippet_id
        if prompt_generation_id:
            query["prompt_generation_id"] = prompt_generation_id
        if status:
            query["status"] = status
        if asset_type:
            query["asset_type"] = asset_type
        if generation_engine:
            query["generation_engine"] = generation_engine
        records = list(db.asset_renders.find(query).sort([("created_at", -1)]).limit(limit))
        records = apply_real_mode_filters(
            records,
            workspace_slug=workspace_slug,
            include_legacy=include_legacy,
            include_test=include_test,
        )
        return {"items": serialize(records), "simulation_only": True}
    finally:
        client.close()


@app.post("/assets/{render_id}/review")
def review_asset_render(render_id: str, payload: AssetRenderReviewRequest) -> dict:
    """
    Operator review: approve, reject, or request revision on a rendered asset.
    An asset must be in needs_review status to be reviewed.
    No content is published by this endpoint.
    """
    valid_decisions = {"approve", "reject", "revise"}
    if payload.decision not in valid_decisions:
        raise HTTPException(
            status_code=422,
            detail=f"decision must be one of: {sorted(valid_decisions)}",
        )

    client = get_client()
    try:
        db = get_database(client)
        record = find_asset_render(db, render_id)
        if not record:
            raise HTTPException(status_code=404, detail="Asset render not found.")

        now = utc_now()
        new_status = (
            "approved" if payload.decision == "approve"
            else "rejected" if payload.decision == "reject"
            else "needs_revision"
        )
        review_event = {
            "decision": payload.decision,
            "note": clean_text(payload.note),
            "reviewed_at": now,
        }
        db.asset_renders.update_one(
            {"_id": record["_id"]},
            {
                "$set": {"status": new_status, "updated_at": now},
                "$push": {"review_events": review_event},
            },
        )
        updated = find_asset_render(db, render_id)
        return {
            "item": serialize(updated),
            "message": f"Asset render {payload.decision}d. No content published or scheduled.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()
