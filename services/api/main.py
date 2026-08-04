import json
import os
import re
import zipfile
import inspect
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from bson import ObjectId
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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
    from snippet_scorer import score_snippet as _score_snippet, SCORE_THRESHOLD_DEFAULT, clean_hook_and_title as _clean_hook_and_title
except Exception:  # pragma: no cover
    _score_snippet = None  # type: ignore[assignment]
    _clean_hook_and_title = None  # type: ignore[assignment]
    SCORE_THRESHOLD_DEFAULT = 6.0

try:
    from agents.base_agent import SUPPORTED_MODULES
    from agents.content_agent import ContentAgent
    from agents.fan_engagement_agent import FanEngagementAgent
    from agents.followup_agent import FollowupAgent
    from agents.outreach_agent import OutreachAgent
    from agents.trend_discovery_agent import TrendDiscoveryAgent
except Exception:
    SUPPORTED_MODULES = {}
    OutreachAgent = None
    ContentAgent = None
    FanEngagementAgent = None
    FollowupAgent = None
    TrendDiscoveryAgent = None

try:
    from media_folder_scanner import scan_media_folder as _scan_media_folder, SUPPORTED_EXTENSIONS as _SCANNER_EXTENSIONS
    from approved_url_downloader import download_approved_url as _download_approved_url, get_diagnostics as _ytdlp_diagnostics
except Exception:  # pragma: no cover
    _scan_media_folder = None  # type: ignore[assignment]
    _SCANNER_EXTENSIONS = frozenset()
    _download_approved_url = None  # type: ignore[assignment]
    _ytdlp_diagnostics = None  # type: ignore[assignment]


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
    "trend_discovery": TrendDiscoveryAgent,
}

AGENT_TASK_TYPES = {
    "outreach": "run_outreach",
    "followup": "run_followup",
    "content": "generate_content",
    "fan_engagement": "engage_fans",
    "trend_discovery": "discover_trends",
}

AGENT_TASK_PRIORITY_ORDER = {"high": 3, "normal": 2, "low": 1}


class MessageReviewRequest(BaseModel):
    decision: Literal["approve", "reject", "revise"]
    note: str = ""


class AgentRunRequest(BaseModel):
    agent: Literal["outreach", "content", "fan_engagement", "followup", "trend_discovery"]
    module: str
    dry_run: bool = True
    limit: int = 10
    use_tools: bool = False
    workspace_slug: str = ""


class AgentTaskCreateRequest(BaseModel):
    agent_name: Literal["outreach", "followup", "content", "fan_engagement", "trend_discovery"]
    module: str
    task_type: Literal["run_outreach", "run_followup", "generate_content", "engage_fans", "content_build", "discover_trends"] | None = None
    priority: Literal["low", "normal", "high"] = "normal"
    input_config: dict[str, Any] = Field(default_factory=dict)
    workspace_slug: str = ""
    card_id: str = ""  # Phase 6D: run card identifier for discovery routing


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "reject", "convert_to_draft", "needs_revision"]
    note: str = ""


class WorkflowAssetDistributionRequest(BaseModel):
    action: Literal["queue", "unqueue", "mark_published", "archive"] | None = None
    distribution_channel: str | None = None
    distribution_notes: str | None = None
    published_url: str | None = None


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
    client_profile_id: str = ""


class WorkspaceStatusRequest(BaseModel):
    status: Literal["active", "paused", "archived"]


# ---------------------------------------------------------------------------
# Phase 6A — Client Profiles & Workflow Definitions models
# ---------------------------------------------------------------------------

class WorkflowStageDefinition(BaseModel):
    stage_number: int
    label: str
    agent_key: str = ""
    run_card_type: str = ""
    chips: list[str] = Field(default_factory=list)
    required: bool = True
    notes: str = ""


class AdminClientProfileCreateRequest(BaseModel):
    slug: str
    display_name: str
    workspace_slug: str = ""
    system_profile_id: str = ""
    module: str = ""
    industry: str = ""
    tier: str = ""
    primary_goal: str = ""
    target_audience: str = ""
    tone_preference: str = ""
    content_cadence: str = ""
    workflow_definition_id: str = ""
    scoring_rule_set: str = "default"
    notes: str = ""
    status: str = "active"


class AdminClientProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    workspace_slug: str | None = None
    system_profile_id: str | None = None
    module: str | None = None
    industry: str | None = None
    tier: str | None = None
    primary_goal: str | None = None
    target_audience: str | None = None
    tone_preference: str | None = None
    content_cadence: str | None = None
    workflow_definition_id: str | None = None
    scoring_rule_set: str | None = None
    notes: str | None = None


class AdminClientProfileStatusRequest(BaseModel):
    status: Literal["active", "paused", "archived"]


class AdminWorkflowDefinitionCreateRequest(BaseModel):
    slug: str
    display_name: str
    system_profile_id: str = ""
    module: str = ""
    stages: list[WorkflowStageDefinition] = Field(default_factory=list)
    notes: str = ""
    status: str = "active"


class AdminWorkflowDefinitionUpdateRequest(BaseModel):
    display_name: str | None = None
    system_profile_id: str | None = None
    module: str | None = None
    stages: list[WorkflowStageDefinition] | None = None
    notes: str | None = None
    status: str | None = None


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


WORKFLOW_ASSET_DISTRIBUTION_DEFAULTS = {
    "distribution_state": "not_queued",
    "distribution_channel": None,
    "distribution_notes": None,
    "published_at": None,
    "published_url": None,
}


def normalize_workflow_asset(asset: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(asset)
    for key, default_value in WORKFLOW_ASSET_DISTRIBUTION_DEFAULTS.items():
        normalized.setdefault(key, default_value)
    return normalized


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
    client = None
    try:
        client = get_client()
        client.admin.command("ping")
        return {"ready": True, "detail": "ping ok"}
    except Exception as exc:
        return {"ready": False, "detail": f"{exc.__class__.__name__}: {exc}"}
    finally:
        try:
            if client is not None:
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


def render_cost_status() -> dict:
    """
    Runway image-generation credit cost, derived from live env config. Only
    the "runway" engine incurs real cost; comfyui/placeholder are $0.
    """
    runway_enabled = env_enabled(os.getenv("RUNWAY_ENABLED", "false"))
    comfyui_enabled = env_enabled(os.getenv("COMFYUI_ENABLED", "false"))
    ratio = os.getenv("RUNWAY_IMAGE_RATIO", "1080:1920")
    try:
        w, h = (int(x) for x in ratio.split(":"))
        credits_per_image = 8 if max(w, h) >= 1080 else 5
    except Exception:
        credits_per_image = 8
    usd_per_credit = 0.01
    return {
        "engine_active": "runway" if runway_enabled else ("comfyui" if comfyui_enabled else "placeholder"),
        "model": os.getenv("RUNWAY_IMAGE_MODEL", "gen4_image"),
        "ratio": ratio,
        "credits_per_image": credits_per_image,
        "usd_per_credit": usd_per_credit,
        "usd_per_image": round(credits_per_image * usd_per_credit, 2),
        # Explicit tiers so the frontend never has to hardcode credit-tier
        # math (e.g. for a per-render resolution picker).
        "tiers": {
            "1080p": {"ratio": "1080:1920", "credits_per_image": 8, "usd_per_image": round(8 * usd_per_credit, 2)},
            "720p": {"ratio": "720:1280", "credits_per_image": 5, "usd_per_image": round(5 * usd_per_credit, 2)},
        },
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
    # content agent also accepts content_build (Phase 6H/6I) for direct workflow_run dispatch
    extra_allowed: dict[str, set[str]] = {"content": {"content_build"}}
    if expected and task_type != expected and task_type not in extra_allowed.get(agent_name, set()):
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


def instantiate_agent(agent_cls, *, module: str, dry_run: bool, mongo_uri: str, vault_path: Path, limit: int, use_tools: bool = False, workspace_slug: str = "", task_id: str | None = None):
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
        if "task_id" in parameters:
            kwargs["task_id"] = task_id
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
    # Phase 6U: ensure production indexes on startup
    try:
        _c = get_client()
        _db = get_database(_c)
        ensure_indexes_6u(_db)  # type: ignore[name-defined]
        _c.close()
    except Exception as _idx_err:
        print(f"[Phase 6U] Index setup warning: {_idx_err}")
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


@app.get("/settings/render-cost")
def render_cost_settings() -> dict:
    return render_cost_status()


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


@app.get("/workflow-assets")
def get_workflow_assets(
    run_id: str = Query(""),
    module: str = Query(""),
    profile_id: str = Query(""),
    approval_state: str = Query(""),
    distribution_state: str = Query(""),
    asset_type: str = Query(""),
    workspace_slug: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if run_id:
            query["run_id"] = run_id
        if module:
            query["module"] = module
        if profile_id:
            query["profile_id"] = profile_id
        if approval_state:
            query["approval_state"] = approval_state
        if distribution_state:
            if distribution_state == "not_queued":
                query["$or"] = [
                    {"distribution_state": "not_queued"},
                    {"distribution_state": {"$exists": False}},
                ]
            else:
                query["distribution_state"] = distribution_state
        if asset_type:
            query["asset_type"] = asset_type
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        items = [normalize_workflow_asset(item) for item in db.workflow_assets.find(query).sort([("created_at", -1)]).limit(limit)]
        return {"items": serialize(items), "count": len(items)}
    finally:
        client.close()


@app.patch("/workflow-assets/{asset_id}/decision")
def decide_workflow_asset(asset_id: str, payload: dict) -> dict:
    decision = payload.get("decision", "")
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'.")
    client = get_client()
    try:
        db = get_database(client)
        asset = db.workflow_assets.find_one({"_id": ObjectId(asset_id)})
        if not asset:
            raise HTTPException(status_code=404, detail="Workflow asset not found.")
        state_map = {"approve": "approved", "reject": "rejected"}
        db.workflow_assets.update_one(
            {"_id": ObjectId(asset_id)},
            {"$set": {
                "approval_state": state_map[decision],
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        updated = db.workflow_assets.find_one({"_id": ObjectId(asset_id)})

        # Phase 6M: auto-propose memory update on approval
        if decision == "approve" and updated:
            _ws6m = updated.get("workspace_slug") or ""
            _asset_type = updated.get("asset_type") or "content"
            _platform = updated.get("platform") or ""
            _pattern = f"Operator approved {_asset_type}{' on ' + _platform if _platform else ''}"
            _try_propose_memory_update(
                db,
                workspace_slug=_ws6m,
                workflow_run_id=updated.get("workflow_run_id") or "",
                source="asset_approval",
                proposed_change={
                    "field": "winning_patterns",
                    "change_type": "add",
                    "new_value": _pattern,
                    "old_value": None,
                },
                evidence=f"Asset '{updated.get('title', 'Untitled')}' was approved by operator.",
                confidence=0.65,
            )

        return {"item": serialize([normalize_workflow_asset(updated)])[0], "message": f"Asset {decision}d."}
    finally:
        client.close()


@app.patch("/workflow-assets/{asset_id}/distribution")
def update_workflow_asset_distribution(asset_id: str, payload: WorkflowAssetDistributionRequest) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        asset = db.workflow_assets.find_one({"_id": ObjectId(asset_id)})
        if not asset:
            raise HTTPException(status_code=404, detail="Workflow asset not found.")

        asset = normalize_workflow_asset(asset)
        if asset.get("approval_state") != "approved":
            raise HTTPException(status_code=400, detail="Only approved workflow assets can be updated for distribution.")

        action = payload.action
        current_state = asset.get("distribution_state") or "not_queued"

        allowed_transitions = {
            "queue": {"not_queued"},
            "unqueue": {"queued"},
            "mark_published": {"queued"},
            "archive": {"not_queued", "queued", "published"},
        }
        if action and current_state not in allowed_transitions[action]:
            raise HTTPException(status_code=400, detail=f"Cannot {action.replace('_', ' ')} from distribution_state={current_state}.")

        payload_dict = payload.dict(exclude_unset=True)
        updates: dict[str, Any] = {"updated_at": utc_now()}

        if "distribution_channel" in payload_dict:
            updates["distribution_channel"] = clean_text(payload.distribution_channel) or None
        if "distribution_notes" in payload_dict:
            updates["distribution_notes"] = clean_text(payload.distribution_notes) or None
        if "published_url" in payload_dict and (action == "mark_published" or current_state == "published"):
            updates["published_url"] = clean_text(payload.published_url) or None

        if action == "queue":
            updates["distribution_state"] = "queued"
        elif action == "unqueue":
            updates["distribution_state"] = "not_queued"
        elif action == "mark_published":
            updates["distribution_state"] = "published"
            updates["published_at"] = utc_now()
            updates.setdefault("published_url", clean_text(payload.published_url) or None)
        elif action == "archive":
            updates["distribution_state"] = "archived"

        db.workflow_assets.update_one({"_id": ObjectId(asset_id)}, {"$set": updates})
        updated = db.workflow_assets.find_one({"_id": ObjectId(asset_id)})

        # Phase 6K: when an asset is published, create a distribution workflow_run record
        # and check if the parent content_build workflow_run is now fully complete.
        if action == "mark_published" and updated:
            _wf_run_id = updated.get("workflow_run_id")
            _ws = updated.get("workspace_slug") or ""
            _now = utc_now()
            # Phase 6L: guard against duplicate distribution runs for the same asset
            _existing_dist = db.workflow_runs.find_one({
                "run_type": "distribution",
                "inputs.asset_id": asset_id,
            })
            if not _existing_dist:
                # Create a distribution workflow_run linked to the content_build run
                dist_run: dict[str, Any] = {
                    "workspace_slug": _ws,
                    "client_profile_id": None,
                    "workflow_stage": 5,
                    "run_type": "distribution",
                    "status": "completed",
                    "title": "Distribution Run",
                    "summary": f"Asset published: {updated.get('title', 'Untitled')}",
                    "source_task_id": None,
                    "source_agent_run_id": None,
                    "source_workflow_run_id": _wf_run_id or None,
                    "inputs": {
                        "asset_id": asset_id,
                        "distribution_channel": updates.get("distribution_channel"),
                        "published_url": updates.get("published_url"),
                    },
                    "outputs": {
                        "assets_published": 1,
                        "workflow_run_id": None,  # filled after insert
                    },
                    "started_at": _now,
                    "completed_at": _now,
                    "created_at": _now,
                    "updated_at": _now,
                }
                dist_result = db.workflow_runs.insert_one(dist_run)
                db.workflow_runs.update_one(
                    {"_id": dist_result.inserted_id},
                    {"$set": {"outputs.workflow_run_id": str(dist_result.inserted_id)}},
                )
            # Check if all assets for this content_build workflow_run are published/archived
            if _wf_run_id:
                _terminal = {"published", "archived"}
                all_assets = list(db.workflow_assets.find({"workflow_run_id": _wf_run_id}))
                all_done = all_assets and all(
                    (a.get("distribution_state") or "not_queued") in _terminal
                    for a in all_assets
                )
                if all_done:
                    try:
                        from bson import ObjectId as _ObjId6kd
                        db.workflow_runs.update_one(
                            {"_id": _ObjId6kd(_wf_run_id)},
                            {"$set": {"status": "completed", "updated_at": _now}},
                        )
                    except Exception:
                        pass  # non-fatal

        # Phase 6M: auto-propose memory update on mark_published
        if action == "mark_published" and updated:
            _ws6m_d = updated.get("workspace_slug") or ""
            _channel = (updates.get("distribution_channel") or updated.get("distribution_channel") or "unknown")
            _try_propose_memory_update(
                db,
                workspace_slug=_ws6m_d,
                workflow_run_id=updated.get("workflow_run_id") or "",
                source="mark_published",
                proposed_change={
                    "field": "distribution_preferences",
                    "change_type": "update",
                    "new_value": {"last_published_channel": _channel},
                    "old_value": None,
                },
                evidence=f"Asset '{updated.get('title', 'Untitled')}' published on {_channel}.",
                confidence=0.6,
            )

        message_map = {
            "queue": "Asset queued for manual distribution.",
            "unqueue": "Asset removed from distribution queue.",
            "mark_published": "Asset marked as manually published.",
            "archive": "Asset archived from distribution queue.",
            None: "Distribution details updated.",
        }
        return {"item": serialize([normalize_workflow_asset(updated)])[0], "message": message_map[action]}
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
        **({"card_id": payload.card_id} if payload.card_id else {}),
    }
    client = get_client()
    try:
        db = get_database(client)
        result = db.agent_tasks.insert_one(task)
        created = db.agent_tasks.find_one({"_id": result.inserted_id})
        return serialize({"item": created, "message": "Agent task queued. No outbound action taken.", "simulation_only": True})
    finally:
        client.close()


def _run_content_discovery_task(db, task: dict, started_at: Any) -> dict:
    """Dedicated handler for card_id='content_discovery' agent tasks.

    Skips normal agent execution so NO approval_requests are created.
    Outputs: discovery_insights + discovery_run_summary only.
    A synthetic agent_run record is written so Step 3 shows execution details.
    """
    from bson import ObjectId as _ObjId
    from discovery_engine import generate_discovery_insights as _gen_insights, get_configured_sources as _get_sources

    ws = clean_text(task.get("workspace_slug") or "")
    module = clean_text(task.get("module") or "")
    input_cfg = task.get("input_config") or {}
    max_insights = max(1, min(int(input_cfg.get("limit") or 4), 10))

    # Phase 6N: load client memory context for memory-aware execution
    memory_ctx = build_memory_context(db, ws)

    run_id = str(_ObjId())

    # Mark task as running
    db.agent_tasks.update_one(
        {"_id": task["_id"]},
        {"$set": {"status": "running", "started_at": started_at, "updated_at": started_at, "outbound_actions_taken": 0}},
    )

    # Create synthetic agent_run for Step 3 LiveAgentRunPanel
    run_doc: dict[str, Any] = {
        "_id": _ObjId(run_id),
        "run_id": run_id,
        "task_id": str(task["_id"]),
        "agent_name": "content_discovery",
        "agent_role": "Scan configured sources for content signals and discovery themes",
        "module": module,
        "status": "running",
        "started_at": started_at,
        "completed_at": None,
        "input_summary": {"agent": "content_discovery", "module": module, "dry_run": True, "simulation_only": True},
        "output_summary": {},
        "steps": [],
        "related_contacts": [],
        "related_leads": [],
        "related_messages": [],
        "related_deals": [],
        "warnings": ["Discovery scan only. No outbound actions taken."],
        "errors": [],
        "workspace_slug": ws,
    }
    db.agent_runs.insert_one(run_doc)

    # Generate insights
    completion_state = "completed"
    created_insights: list[dict] = []
    try:
        created_insights = _gen_insights(
            db=db,
            workspace_slug=ws,
            client_profile_slug=None,
            module=module,
            source_run_id=run_id,
            max_insights=max_insights,
        )
    except Exception:
        completion_state = "failed"
    if completion_state == "completed" and not created_insights:
        completion_state = "partial"

    disc_completed = utc_now()

    # Gather source/platform metadata for a human-readable summary
    configured_sources: list[dict] = []
    try:
        configured_sources = _get_sources(ws, None, db)
    except Exception:
        pass
    source_labels = [s.get("label", "") for s in configured_sources if s.get("status") == "active"]
    platforms_from_insights: list[str] = []
    for ins in created_insights:
        for ev in ins.get("evidence", []):
            p = clean_text(ev.get("platform", ""))
            if p and p not in platforms_from_insights:
                platforms_from_insights.append(p)
    high_conf = sum(1 for i in created_insights if (i.get("confidence_score") or 0) >= 0.8)

    if completion_state == "completed" and created_insights:
        src_count = len(configured_sources)
        plat_str = ", ".join(platforms_from_insights[:3]) if platforms_from_insights else "configured sources"
        summary_text = (
            f"Checked {src_count} configured source{'s' if src_count != 1 else ''} across {plat_str}. "
            f"Generated {len(created_insights)} discovery insight{'s' if len(created_insights) != 1 else ''} "
            f"with {high_conf} high-confidence signal{'s' if high_conf != 1 else ''}."
        )
        next_action = "Review discovery insights in Step 2, then run Content Asset Creation to generate reviewable content."
    elif completion_state == "partial":
        summary_text = "Discovery ran but no insights were generated for this workspace and module."
        next_action = "Add more client sources or rerun Content Discovery."
    else:
        summary_text = "Discovery run encountered an error."
        next_action = "Check system logs and retry Content Discovery."

    # Persist discovery_run_summary
    try:
        db.discovery_run_summaries.insert_one({
            "workspace_slug": ws,
            "run_id": run_id,
            "agent_name": "content_discovery",
            "started_at": started_at,
            "completed_at": disc_completed,
            "sources_checked": len(configured_sources),
            "insights_generated": len(created_insights),
            "high_confidence_insights": high_conf,
            "configured_sources_used": source_labels,
            "platforms_checked": platforms_from_insights,
            "completion_state": completion_state,
            "summary": summary_text,
            "next_recommended_action": next_action,
            "metadata": {"module": module, "card_id": "content_discovery"},
            "created_at": disc_completed,
            "updated_at": disc_completed,
        })
    except Exception:
        pass

    # Phase 6H: persist workflow_run for structured execution lineage
    try:
        db.workflow_runs.insert_one({
            "workspace_slug": ws,
            "client_profile_id": None,
            "workflow_stage": 2,
            "run_type": "discovery",
            "status": "completed" if completion_state in ("completed", "partial") else "failed",
            "title": "Content Discovery Run",
            "summary": summary_text,
            "source_task_id": str(task["_id"]),
            "source_agent_run_id": run_id,
            "inputs": {"module": module, "max_insights": max_insights},
            "outputs": {
                "insights_generated": len(created_insights),
                "high_confidence_count": high_conf,
                "platforms_checked": platforms_from_insights,
                "configured_sources_used": source_labels,
                "recommended_next_step": "content_build",
                # Phase 6N
                "memory_informed": memory_ctx.get("has_memory", False),
                "memory_version_used": memory_ctx.get("memory_version") if memory_ctx.get("has_memory") else None,
            },
            # Phase 6N: memory traceability
            "client_memory_id": memory_ctx.get("memory_id", ""),
            "client_memory_version": memory_ctx.get("memory_version", 0),
            "memory_context_hash": memory_ctx.get("memory_context_hash", ""),
            "memory_snapshot": memory_ctx.get("snapshot", {}),
            "started_at": started_at,
            "completed_at": disc_completed,
            "created_at": disc_completed,
            "updated_at": disc_completed,
        })
    except Exception:
        pass

    # Update agent_run to completed
    db.agent_runs.update_one(
        {"run_id": run_id},
        {"$set": {
            "status": completion_state,
            "completed_at": disc_completed,
            "output_summary": {
                "sources_checked": len(configured_sources),
                "insights_generated": len(created_insights),
                "high_confidence_insights": high_conf,
                "completion_state": completion_state,
                "simulation_only": True,
                "outbound_actions_taken": 0,
            },
        }},
    )

    # Complete agent_task — status always "completed", never "waiting_for_approval"
    completed_update: dict[str, Any] = {
        "status": "completed",
        "completed_at": disc_completed,
        "updated_at": disc_completed,
        "linked_run_id": run_id,
        "result_summary": {
            "agent_run_status": completion_state,
            "sources_checked": len(configured_sources),
            "insights_generated": len(created_insights),
            "completion_state": completion_state,
            "simulation_only": True,
            "outbound_actions_taken": 0,
        },
        "error": None,
        "outbound_actions_taken": 0,
    }
    db.agent_tasks.update_one({"_id": task["_id"]}, {"$set": completed_update})
    updated = db.agent_tasks.find_one({"_id": task["_id"]})
    run = db.agent_runs.find_one({"run_id": run_id})

    return serialize({
        "item": updated,
        "run": run,
        "result": {
            "run_id": run_id,
            "actions": [],
            "insights_generated": len(created_insights),
            "completion_state": completion_state,
            "summary": summary_text,
            "next_recommended_action": next_action,
        },
        "message": f"Content discovery completed. {len(created_insights)} insight(s) generated. No outbound action taken.",
        "simulation_only": True,
    })


def _run_content_build_task(db, task: dict, started_at: Any) -> dict:
    """Dedicated handler for card_id='content_build' agent tasks.

    Generates reviewable content assets from approved discovery insights.
    Creates workflow_run(run_type='content_build'), workflow_assets, and
    approval_requests linked to this workflow_run. Does NOT create
    approval_requests for discovery.
    """
    from bson import ObjectId as _ObjId

    ws = clean_text(task.get("workspace_slug") or "")
    module = clean_text(task.get("module") or "")
    input_cfg = task.get("input_config") or {}
    max_assets = max(1, min(int(input_cfg.get("limit") or 3), 10))
    discovery_run_id = clean_text(input_cfg.get("discovery_run_id") or "")

    # Phase 6N: load client memory for memory-aware content generation
    memory_ctx = build_memory_context(db, ws)

    run_id = str(_ObjId())
    now = started_at

    # Mark task running
    db.agent_tasks.update_one(
        {"_id": task["_id"]},
        {"$set": {"status": "running", "started_at": now, "updated_at": now, "outbound_actions_taken": 0}},
    )

    # Create synthetic agent_run
    run_doc: dict[str, Any] = {
        "_id": _ObjId(run_id),
        "run_id": run_id,
        "task_id": str(task["_id"]),
        "agent_name": "content_build",
        "agent_role": "Generate reviewable content assets from discovery insights",
        "module": module,
        "status": "running",
        "started_at": now,
        "completed_at": None,
        "input_summary": {"agent": "content_build", "module": module, "max_assets": max_assets},
        "output_summary": {},
        "steps": [],
        "related_contacts": [],
        "related_leads": [],
        "related_messages": [],
        "related_deals": [],
        "warnings": [],
        "errors": [],
        "workspace_slug": ws,
    }
    db.agent_runs.insert_one(run_doc)

    # Pull approved discovery insights to base content on
    source_insights: list[dict] = []
    try:
        q: dict[str, Any] = {"workspace_slug": ws}
        if module:
            q["module"] = module
        raw = list(db.discovery_insights.find(q).sort([("confidence_score", -1)]).limit(max_assets))
        source_insights = raw
    except Exception:
        pass

    # Build simulated content assets
    CONTENT_TYPES = ["social_post", "outreach_script", "content_outline", "hook_set", "email_draft"]
    PLATFORMS = ["LinkedIn", "Email", "Instagram", "TikTok", "YouTube"]
    completed_at = utc_now()

    created_assets: list[dict] = []
    created_approval_ids: list[str] = []

    # Insert workflow_run first so we have the workflow_run_id for linkage
    wf_run_doc: dict[str, Any] = {
        "workspace_slug": ws,
        "client_profile_id": None,
        "workflow_stage": 2,
        "run_type": "content_build",
        "status": "needs_review",
        "title": "Content Build Run",
        "summary": None,  # filled after assets are known
        "source_task_id": str(task["_id"]),
        "source_agent_run_id": run_id,
        "inputs": {"module": module, "max_assets": max_assets, "discovery_run_id": discovery_run_id or None},
        "outputs": {},
        # Phase 6N: memory traceability
        "client_memory_id": memory_ctx.get("memory_id", ""),
        "client_memory_version": memory_ctx.get("memory_version", 0),
        "memory_context_hash": memory_ctx.get("memory_context_hash", ""),
        "memory_snapshot": memory_ctx.get("snapshot", {}),
        "started_at": now,
        "completed_at": completed_at,
        "created_at": completed_at,
        "updated_at": completed_at,
    }
    wf_run_result = db.workflow_runs.insert_one(wf_run_doc)
    workflow_run_id = str(wf_run_result.inserted_id)

    for i, insight in enumerate(source_insights[:max_assets]):
        content_type = CONTENT_TYPES[i % len(CONTENT_TYPES)]
        platform = PLATFORMS[i % len(PLATFORMS)]
        insight_id = str(insight.get("_id", ""))
        insight_title = clean_text(insight.get("title") or insight.get("summary") or f"Insight {i+1}")

        # Phase 6N: apply memory context to asset body
        tone_label, signal_block = _build_memory_asset_hints(memory_ctx)
        asset_body = (
            f"[{content_type.replace('_', ' ').title()}"
            + (f" — {tone_label}" if tone_label else "")
            + "]\n\n"
            + f"Based on insight: {insight_title}\n\n"
            + f"Platform: {platform}\n"
            + f"Module: {module}\n\n"
            + (signal_block + "\n\n" if signal_block else "")
            + "This is a generated draft ready for operator review. "
            + "Edit before publishing."
        )
        # Phase 6N: enforce blocked claims
        constraint_result = _enforce_memory_constraints(asset_body, memory_ctx)
        asset_memory_violations = constraint_result["violations"]
        asset_memory_warnings = constraint_result["warnings"]

        asset_doc: dict[str, Any] = {
            "workspace_slug": ws,
            "module": module,
            "run_id": run_id,
            "workflow_run_id": workflow_run_id,
            "source_insight_id": insight_id,
            "asset_type": content_type,
            "platform": platform,
            "title": f"{platform} {content_type.replace('_', ' ').title()} — {insight_title[:40]}",
            "body": asset_body,
            "approval_state": "pending",
            "distribution_state": "not_queued",
            "distribution_channel": None,
            "distribution_notes": None,
            "published_at": None,
            "published_url": None,
            # Phase 6N: memory context used
            "memory_context_used": memory_ctx.get("has_memory", False),
            "memory_violations": asset_memory_violations,
            "memory_warnings": asset_memory_warnings,
            "created_at": completed_at,
            "updated_at": completed_at,
        }
        asset_result = db.workflow_assets.insert_one(asset_doc)
        asset_id = str(asset_result.inserted_id)
        created_assets.append({"_id": asset_id, "title": asset_doc["title"], "asset_type": content_type})

        # Create approval_request linked to this workflow_run
        approval_doc: dict[str, Any] = {
            "workspace_slug": ws,
            "module": module,
            "status": "open",
            "request_type": "content_asset_review",
            "agent_name": "content_build",
            "run_id": run_id,
            "workflow_run_id": workflow_run_id,
            "source_card_id": "content_build",
            "workflow_asset_id": asset_id,
            "source_insight_id": insight_id,
            "title": asset_doc["title"],
            "summary": f"Review generated {content_type.replace('_', ' ')} for {platform}.",
            "content_preview": asset_body[:200],
            "created_at": completed_at,
            "updated_at": completed_at,
        }
        approval_result = db.approval_requests.insert_one(approval_doc)
        created_approval_ids.append(str(approval_result.inserted_id))

    # If no insights found, generate generic placeholder asset
    if not created_assets:
        tone_label, signal_block = _build_memory_asset_hints(memory_ctx)
        placeholder_body = (
            "[Content Draft"
            + (f" — {tone_label}" if tone_label else "")
            + "]\n\n"
            + f"Generic content draft for {module.replace('_', ' ')} module.\n\n"
            + (signal_block + "\n\n" if signal_block else "")
            + "No discovery insights found. Add client sources to improve content relevance."
        )
        asset_doc = {
            "workspace_slug": ws,
            "module": module,
            "run_id": run_id,
            "workflow_run_id": workflow_run_id,
            "source_insight_id": None,
            "asset_type": "social_post",
            "platform": "LinkedIn",
            "title": f"LinkedIn Social Post — {module.replace('_', ' ').title()} Campaign",
            "body": placeholder_body,
            "approval_state": "pending",
            "distribution_state": "not_queued",
            "distribution_channel": None,
            "distribution_notes": None,
            "published_at": None,
            "published_url": None,
            # Phase 6N: memory context
            "memory_context_used": memory_ctx.get("has_memory", False),
            "memory_violations": [],
            "memory_warnings": [],
            "created_at": completed_at,
            "updated_at": completed_at,
        }
        asset_result = db.workflow_assets.insert_one(asset_doc)
        asset_id = str(asset_result.inserted_id)
        created_assets.append({"_id": asset_id, "title": asset_doc["title"], "asset_type": "social_post"})

        approval_doc = {
            "workspace_slug": ws,
            "module": module,
            "status": "open",
            "request_type": "content_asset_review",
            "agent_name": "content_build",
            "run_id": run_id,
            "workflow_run_id": workflow_run_id,
            "source_card_id": "content_build",
            "workflow_asset_id": asset_id,
            "source_insight_id": None,
            "title": asset_doc["title"],
            "summary": "Review generated social post content.",
            "content_preview": asset_doc["body"][:200],
            "created_at": completed_at,
            "updated_at": completed_at,
        }
        approval_result = db.approval_requests.insert_one(approval_doc)
        created_approval_ids.append(str(approval_result.inserted_id))

    summary_text = (
        f"Generated {len(created_assets)} content asset{'s' if len(created_assets) != 1 else ''} "
        f"for review. {len(created_approval_ids)} approval request{'s' if len(created_approval_ids) != 1 else ''} created."
    )

    # Aggregate memory violations across all assets
    all_violations: list[str] = []
    all_memory_warnings: list[str] = []
    for a_rec in db.workflow_assets.find({"workflow_run_id": workflow_run_id}):
        all_violations.extend(a_rec.get("memory_violations") or [])
        all_memory_warnings.extend(a_rec.get("memory_warnings") or [])

    # Update workflow_run with final outputs
    db.workflow_runs.update_one(
        {"_id": wf_run_result.inserted_id},
        {"$set": {
            "summary": summary_text,
            "outputs": {
                "assets_generated": len(created_assets),
                "approval_requests_created": len(created_approval_ids),
                "asset_types": list({a["asset_type"] for a in created_assets}),
                "workflow_run_id": workflow_run_id,
                # Phase 6N
                "memory_informed": memory_ctx.get("has_memory", False),
                "memory_version_used": memory_ctx.get("memory_version") if memory_ctx.get("has_memory") else None,
                "memory_violations": all_violations,
                "memory_warnings": all_memory_warnings,
            },
            "updated_at": completed_at,
        }},
    )

    # Update agent_run
    db.agent_runs.update_one(
        {"run_id": run_id},
        {"$set": {
            "status": "waiting_for_approval",
            "completed_at": completed_at,
            "output_summary": {
                "assets_generated": len(created_assets),
                "approval_requests_created": len(created_approval_ids),
                "workflow_run_id": workflow_run_id,
            },
        }},
    )

    # Complete task
    completed_update: dict[str, Any] = {
        "status": "waiting_for_approval",
        "completed_at": completed_at,
        "updated_at": completed_at,
        "linked_run_id": run_id,
        "result_summary": {
            "assets_generated": len(created_assets),
            "approval_requests_created": len(created_approval_ids),
            "workflow_run_id": workflow_run_id,
        },
        "error": None,
    }
    db.agent_tasks.update_one({"_id": task["_id"]}, {"$set": completed_update})
    updated = db.agent_tasks.find_one({"_id": task["_id"]})
    run = db.agent_runs.find_one({"run_id": run_id})

    return serialize({
        "item": updated,
        "run": run,
        "workflow_run_id": workflow_run_id,
        "result": {
            "run_id": run_id,
            "assets_generated": len(created_assets),
            "approval_requests_created": len(created_approval_ids),
            "workflow_run_id": workflow_run_id,
            "summary": summary_text,
            "next_recommended_action": "Review generated content assets in Step 4.",
        },
        "message": f"Content build completed. {len(created_assets)} asset(s) queued for review.",
    })


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

        # ── content_discovery: dedicated handler — no approval_requests created ──────
        _early_card_id = clean_text(task.get("card_id") or (task.get("input_config") or {}).get("card_id") or "")
        _early_ws = clean_text(task.get("workspace_slug") or "")
        _early_module = module
        if _early_card_id == "content_discovery" and _early_ws and _early_module:
            return _run_content_discovery_task(db, task, started_at)

        # ── content_build: dedicated handler — creates workflow_run + assets + approvals ─
        if _early_card_id == "content_build" and _early_ws and _early_module:
            return _run_content_build_task(db, task, started_at)

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
                task_id=str(task["_id"]),
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

            # Phase 6D: auto-generate discovery insights for content_discovery runs
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

        # Phase 6K: when approving an approval_request that is linked to a workflow_asset,
        # automatically approve the asset so the operator doesn't need a separate action.
        if payload.decision == "approve":
            asset_id_str = request.get("workflow_asset_id")
            if asset_id_str:
                try:
                    from bson import ObjectId as _ObjId6k
                    db.workflow_assets.update_one(
                        {"_id": _ObjId6k(asset_id_str)},
                        {"$set": {"approval_state": "approved", "updated_at": decided_at}},
                    )
                except Exception:
                    pass  # non-fatal — asset may not exist or id may be invalid

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


# ---------------------------------------------------------------------------
# Phase 6L — Workflow Lineage & Lifecycle Summary endpoints
# ---------------------------------------------------------------------------

@app.get("/workflow-lineage")
def workflow_lineage(
    workspace_slug: str = Query(""),
    limit: int = Query(5, ge=1, le=20),
) -> dict:
    """Return a structured lineage graph: discovery → content_build → assets → distribution runs.

    Each item in ``cycles`` represents one content-build cycle anchored by a content_build
    workflow_run and enriched with its parent discovery run, child assets, and per-asset
    distribution runs.
    """
    client = get_client()
    try:
        db = get_database(client)
        q: dict[str, Any] = {}
        if workspace_slug:
            q["workspace_slug"] = workspace_slug

        # Fetch recent content_build runs as the anchor for each cycle
        cb_runs = list(
            db.workflow_runs.find({**q, "run_type": "content_build"})
            .sort([("created_at", -1)])
            .limit(limit)
        )

        cycles = []
        for cb in cb_runs:
            cb_id_str = str(cb["_id"])

            # Parent discovery run (linked via source_workflow_run_id → content_build, or
            # same workspace, run_type=discovery, created just before this cb run)
            disc_run = None
            src_disc_id = cb.get("source_workflow_run_id")
            if src_disc_id and ObjectId.is_valid(src_disc_id):
                disc_run = db.workflow_runs.find_one({"_id": ObjectId(src_disc_id), "run_type": "discovery"})
            if not disc_run and workspace_slug:
                # Fallback: most recent discovery run in the same workspace created before this cb
                disc_run = db.workflow_runs.find_one(
                    {**q, "run_type": "discovery", "created_at": {"$lte": cb.get("created_at", utc_now())}},
                    sort=[("created_at", -1)],
                )

            # Assets belonging to this content_build run
            raw_assets = list(db.workflow_assets.find({"workflow_run_id": cb_id_str}))
            asset_nodes = []
            for asset in raw_assets:
                asset_id_str = str(asset["_id"])
                dist_runs = list(
                    db.workflow_runs.find({"run_type": "distribution", "inputs.asset_id": asset_id_str})
                    .sort([("created_at", -1)])
                )
                asset_nodes.append({
                    "asset": serialize(normalize_workflow_asset(asset)),
                    "distribution_runs": serialize(dist_runs),
                })

            cycles.append({
                "content_build_run": serialize(cb),
                "discovery_run": serialize(disc_run) if disc_run else None,
                "assets": asset_nodes,
            })

        return {
            "workspace_slug": workspace_slug,
            "cycles": cycles,
            "count": len(cycles),
        }
    finally:
        client.close()


@app.get("/workflow-lifecycle-summary")
def workflow_lifecycle_summary(workspace_slug: str = Query("")) -> dict:
    """Return a concise snapshot of the current lifecycle state for a workspace.

    ``lifecycle_stage`` reflects the highest active stage:
    ``complete`` → ``distribution`` → ``review`` → ``content_build`` → ``discovery`` → ``idle``
    """
    client = get_client()
    try:
        db = get_database(client)
        q: dict[str, Any] = {}
        if workspace_slug:
            q["workspace_slug"] = workspace_slug

        # Latest runs by type
        def _latest(run_type: str) -> dict | None:
            return db.workflow_runs.find_one({**q, "run_type": run_type}, sort=[("created_at", -1)])

        disc = _latest("discovery")
        cb = _latest("content_build")

        # Assets for the latest content_build run
        cb_id_str = str(cb["_id"]) if cb else None
        assets: list[dict] = list(db.workflow_assets.find({"workflow_run_id": cb_id_str})) if cb_id_str else []
        dist_runs = list(db.workflow_runs.find({**q, "run_type": "distribution"}).sort([("created_at", -1)]).limit(50)) if cb_id_str else []

        # Open approval requests
        open_approvals = list(db.approval_requests.find({**q, "status": "open"})) if workspace_slug else []

        # Asset breakdowns
        def _count_assets(state: str) -> int:
            return sum(1 for a in assets if (a.get("distribution_state") or "not_queued") == state)

        approved_count = sum(1 for a in assets if a.get("approval_state") == "approved")
        pending_count = sum(1 for a in assets if a.get("approval_state") == "pending")
        queued = _count_assets("queued")
        published = _count_assets("published")
        archived = _count_assets("archived")
        not_queued = _count_assets("not_queued")

        # Determine lifecycle stage
        is_complete = (
            cb is not None
            and cb.get("status") == "completed"
            and len(assets) > 0
            and all((a.get("distribution_state") or "not_queued") in {"published", "archived"} for a in assets)
        )

        if is_complete:
            stage = "complete"
        elif published > 0 or queued > 0:
            stage = "distribution"
        elif open_approvals or approved_count > 0 or pending_count > 0:
            stage = "review"
        elif cb is not None:
            stage = "content_build"
        elif disc is not None:
            stage = "discovery"
        else:
            stage = "idle"

        return serialize({
            "workspace_slug": workspace_slug,
            "lifecycle_stage": stage,
            "is_complete": is_complete,
            "discovery": {
                "run_id": str(disc["_id"]) if disc else None,
                "status": disc.get("status") if disc else None,
                "insights_generated": ((disc.get("outputs") or {}).get("insights_generated")) if disc else None,
                "created_at": disc.get("created_at") if disc else None,
            },
            "content_build": {
                "run_id": cb_id_str,
                "status": cb.get("status") if cb else None,
                "asset_count": len(assets),
                "created_at": cb.get("created_at") if cb else None,
            },
            "review": {
                "open_approvals": len(open_approvals),
                "approved_assets": approved_count,
                "pending_assets": pending_count,
            },
            "distribution": {
                "not_queued": not_queued,
                "queued": queued,
                "published": published,
                "archived": archived,
                "distribution_runs": len(dist_runs),
            },
        })
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
        if payload.client_profile_id:
            workspace["client_profile_id"] = payload.client_profile_id.strip()
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
    # Phase 6Z — content-rights & attribution model
    content_rights: Literal["owned_licensed", "third_party_curated"] = "owned_licensed"
    creator_handle: str = ""
    creator_platform_url: str = ""
    attribution_caption: str = ""


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
    # v6.5 scoring fields (populated by POST /content-snippets/{id}/score)
    hook_strength: float = 0.0
    clarity_score: float = 0.0
    emotional_impact: float = 0.0
    shareability_score: float = 0.0
    platform_fit_score: float = 0.0
    overall_score: float = 0.0
    hook_text: str = ""
    hook_type: str = ""
    alternative_hooks: list[str] = Field(default_factory=list)


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
        "content_rights": payload.content_rights,
        "creator_handle": clean_text(payload.creator_handle),
        "creator_platform_url": clean_text(payload.creator_platform_url),
        "attribution_caption": clean_text(payload.attribution_caption),
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
    min_score: float = Query(0.0, ge=0.0, le=10.0),
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
        if min_score > 0.0:
            query["overall_score"] = {"$gte": min_score}
        records = list(db.content_snippets.find(query).sort([("overall_score", -1), ("score", -1), ("created_at", -1)]).limit(limit))
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
        # v6.5 scoring fields — zero/empty until POST /{id}/score is called
        "hook_strength": 0.0,
        "clarity_score": 0.0,
        "emotional_impact": 0.0,
        "shareability_score": 0.0,
        "platform_fit_score": 0.0,
        "overall_score": 0.0,
        "hook_text": "",
        "hook_type": "",
        "alternative_hooks": [],
        "scored_at": None,
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


@app.post("/content-snippets/{snippet_id}/score")
def score_content_snippet(snippet_id: str) -> dict:
    """Score a content snippet using deterministic NLP analysis (v6.5).

    Rules
    -----
    * No external API calls.  All scoring is local and deterministic.
    * ``simulation_only`` is always ``True``.
    * ``scored_at`` is set on the snippet after scoring.
    """
    if _score_snippet is None:
        raise HTTPException(status_code=500, detail="Snippet scorer module is unavailable.")
    client = get_client()
    scored_at = utc_now()
    try:
        db = get_database(client)
        snippet = find_content_snippet(db, snippet_id)
        if not snippet:
            raise HTTPException(status_code=404, detail="Content snippet not found.")
        result = _score_snippet(snippet.get("transcript_text", ""))
        update_fields = {
            "hook_strength": result.hook_strength,
            "clarity_score": result.clarity_score,
            "emotional_impact": result.emotional_impact,
            "shareability_score": result.shareability_score,
            "platform_fit_score": result.platform_fit_score,
            "overall_score": result.overall_score,
            "score_reason": result.score_reason,
            "hook_text": result.hook_text,
            "hook_type": result.hook_type,
            "alternative_hooks": result.alternative_hooks,
            "scored_at": scored_at,
            "updated_at": scored_at,
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
        db.content_snippets.update_one({"_id": snippet["_id"]}, {"$set": update_fields})
        updated = db.content_snippets.find_one({"_id": snippet["_id"]})
        return {
            "item": serialize(updated),
            "message": "Snippet scored. No post published or scheduled.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.post("/content-snippets/{snippet_id}/cleanup-hook")
def cleanup_snippet_hook(snippet_id: str) -> dict:
    """Run editorial hook cleanup on a scored snippet (v10.3).

    Reads the existing ``hook_text`` from the snippet, runs
    ``clean_hook_and_title()`` (deterministic, no external calls), and
    stores four new display fields:

    * ``cleaned_hook_text`` — polished declarative sentence
    * ``display_title`` — title-cased heading for content cards
    * ``caption_hook_suggestions`` — 2–3 short-form caption variants
    * ``hook_cleanup_notes`` — editorial rationale

    The original ``hook_text`` and ``transcript_text`` are never modified.
    ``simulation_only`` is always ``True``, ``outbound_actions_taken`` always 0.
    """
    if _clean_hook_and_title is None:
        raise HTTPException(status_code=500, detail="Hook cleanup module is unavailable.")
    client = get_client()
    cleaned_at = utc_now()
    try:
        db = get_database(client)
        snippet = find_content_snippet(db, snippet_id)
        if not snippet:
            raise HTTPException(status_code=404, detail="Content snippet not found.")
        raw_hook = snippet.get("hook_text", "")
        transcript_text = snippet.get("transcript_text", "")
        result = _clean_hook_and_title(raw_hook, transcript_text)
        update_fields = {
            "cleaned_hook_text": result.cleaned_hook_text,
            "display_title": result.display_title,
            "caption_hook_suggestions": result.caption_hook_suggestions,
            "hook_cleanup_notes": result.hook_cleanup_notes,
            "cleaned_at": cleaned_at,
            "updated_at": cleaned_at,
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
        db.content_snippets.update_one({"_id": snippet["_id"]}, {"$set": update_fields})
        updated = db.content_snippets.find_one({"_id": snippet["_id"]})
        return {
            "item": serialize(updated),
            "message": "Hook cleanup complete. Original hook_text preserved. No post published or scheduled.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


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
    audio_path: str = ""  # v7.1: direct path to local audio — skips extraction run lookup
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


# ---------------------------------------------------------------------------
# v10.4 — Media Folder Scan + Approved URL Download models
# ---------------------------------------------------------------------------

class MediaFolderScanRequest(BaseModel):
    workspace_slug: str = ""
    client_id: str = ""
    folder_path: str = ""
    source_label: str = ""
    ingestion_source: str = "local_folder"   # local_folder | google_drive_sync | dropbox_sync
    compute_hashes: bool = False


class ApprovedUrlDownloadRequest(BaseModel):
    workspace_slug: str = ""
    client_id: str = ""
    source_content_id: str = ""
    url: str = ""
    permission_confirmed: bool = False
    requested_format: str = "video"    # video | audio
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


class MediaIntakeRecordPatchRequest(BaseModel):
    source_content_id: str = ""
    status: str = ""
    notes: str = ""


@app.patch("/media-intake-records/{record_id}")
def patch_media_intake_record(record_id: str, payload: MediaIntakeRecordPatchRequest) -> dict:
    """Update linkage fields on a media intake record (e.g. source_content_id)."""
    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)
        try:
            from bson import ObjectId
            oid = ObjectId(record_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid record_id.")
        doc = db.media_intake_records.find_one({"_id": oid})
        if not doc:
            raise HTTPException(status_code=404, detail="Media intake record not found.")
        update: dict[str, Any] = {"updated_at": now}
        if payload.source_content_id:
            update["source_content_id"] = clean_text(payload.source_content_id)
        if payload.status:
            update["status"] = clean_text(payload.status)
        if payload.notes:
            update["notes"] = clean_text(payload.notes)
        db.media_intake_records.update_one({"_id": oid}, {"$set": update})
        updated = db.media_intake_records.find_one({"_id": oid})
        return {"item": serialize(updated), "simulation_only": True}
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
        # v7.1: direct audio_path override — used for yt_dlp-ingested media
        if clean_text(payload.audio_path):
            audio_path = clean_text(payload.audio_path)

        # v7: wrap transcription in try/except — errors stored on the run record
        transcript_error = ""
        transcript_language = clean_text(payload.language) or "en"
        try:
            segments = provider.transcribe(
                source_content_id=source_content_id,
                audio_path=audio_path,
                text_hint=clean_text(payload.text_hint),
            )
            run_status = "complete"
        except Exception as exc:
            segments = []
            run_status = "failed"
            transcript_error = str(exc)

        run_record: dict[str, Any] = {
            "workspace_slug": workspace_slug,
            "source_content_id": source_content_id,
            "audio_extraction_run_id": audio_run_id,
            "provider": provider.provider_name,
            "language": transcript_language,
            "segment_count": len(segments),
            "status": run_status,
            "input_path": audio_path,
            "error_message": transcript_error,
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
        if run_status == "failed":
            return {
                "item": serialize(created),
                "segment_count": 0,
                "message": f"Transcript run failed: {transcript_error}",
                "simulation_only": True,
            }
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

            # v7: AUTO_SCORE_SNIPPETS — score immediately after creation if enabled
            _auto_score = os.getenv("AUTO_SCORE_SNIPPETS", "false").lower() in (
                "1", "true", "yes", "on"
            )
            if _auto_score and _score_snippet is not None and created:
                try:
                    score_result = _score_snippet(snippet_record["transcript_text"])
                    score_update = {
                        "hook_strength": score_result.hook_strength,
                        "clarity_score": score_result.clarity_score,
                        "emotional_impact": score_result.emotional_impact,
                        "shareability_score": score_result.shareability_score,
                        "platform_fit_score": score_result.platform_fit_score,
                        "overall_score": score_result.overall_score,
                        "hook_text": score_result.hook_text,
                        "hook_type": score_result.hook_type,
                        "alternative_hooks": score_result.alternative_hooks,
                        "scored_at": now,
                    }
                    db.content_snippets.update_one(
                        {"_id": insert_res.inserted_id},
                        {"$set": score_update},
                    )
                    created = db.content_snippets.find_one({"_id": insert_res.inserted_id})
                except Exception:
                    pass  # auto-scoring failure must not block snippet creation

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
        "inspirational_short_form",
    ] = "faceless_motivational"
    generation_engine_target: Literal[
        "comfyui", "seedance", "higgsfield", "runway", "manual"
    ] = "comfyui"
    use_likeness: bool = False
    # Operator-supplied preferred duration in seconds (0 = unspecified).
    # Preset inspirational_short_form sets this to 75 automatically.
    preferred_duration_seconds: int = 0
    notes: str = ""


class PromptGenerationReviewRequest(BaseModel):
    decision: Literal["approve", "reject", "revise"]
    note: str = ""


class PromptGenerationUpdateRequest(BaseModel):
    scene_beats: list[str] | None = None


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

        # v6.5 score gate: block snippets that have been scored but score below threshold.
        # Operator manual approval (status="approved" with reviewed_at set) bypasses the gate.
        _threshold = float(
            __import__("os").environ.get("SNIPPET_SCORE_THRESHOLD", str(SCORE_THRESHOLD_DEFAULT))
        )
        _overall = float(snippet.get("overall_score", 0.0))
        _manually_approved = bool(snippet.get("reviewed_at") or snippet.get("review_note"))
        if snippet.get("scored_at") and _overall < _threshold and not _manually_approved:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Snippet overall_score {_overall:.1f} is below the required "
                    f"threshold {_threshold:.1f}. Improve the snippet content or "
                    "lower SNIPPET_SCORE_THRESHOLD."
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
                hook_text=snippet.get("hook_text", ""),
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
            "preferred_duration_seconds": result.preferred_duration_seconds
            or payload.preferred_duration_seconds,
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


@app.patch("/prompt-generations/{gen_id}")
def update_prompt_generation(gen_id: str, payload: PromptGenerationUpdateRequest) -> dict:
    """
    Edit content fields (currently: scene_beats) on a prompt generation.

    Locked to draft/needs_revision — once approved, scene beats are final,
    matching the approval panel's semantics (edit before approving, not
    after).
    """
    client = get_client()
    try:
        db = get_database(client)

        record = find_prompt_generation(db, gen_id)
        if not record:
            raise HTTPException(status_code=404, detail="Prompt generation not found.")
        if record.get("status") not in ("draft", "needs_revision"):
            raise HTTPException(
                status_code=409,
                detail=f"Cannot edit a prompt generation with status {record.get('status')!r}.",
            )

        updates: dict[str, Any] = {"updated_at": utc_now()}
        if payload.scene_beats is not None:
            updates["scene_beats"] = [clean_text(b) for b in payload.scene_beats if clean_text(b)]

        db.prompt_generations.update_one({"_id": record["_id"]}, {"$set": updates})
        updated = find_prompt_generation(db, str(record["_id"]))

        return {
            "item": serialize(updated),
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
    # When True (default), source_audio_path is used unchanged.
    # Test-tone is ONLY generated as a safe fallback when source_audio_path=""
    # AND FFMPEG_ENABLED=true.  Never clone, rewrite, or replace original audio.
    preserve_original_audio: bool = True
    add_captions: bool = False
    notes: str = ""
    # Optional per-render Runway image ratio override (e.g. "720:1280" for
    # the cheaper 720p tier). Empty string = use the server's configured
    # RUNWAY_IMAGE_RATIO default.
    image_ratio: str = ""


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
            "preserve_original_audio": payload.preserve_original_audio,
            "add_captions": payload.add_captions,
            "notes": clean_text(payload.notes),
            "image_ratio": clean_text(payload.image_ratio),
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


@app.get("/asset-renders/{render_id}/stream")
def stream_asset_render(render_id: str) -> FileResponse:
    """
    Stream a locally rendered MP4 for in-browser preview.

    Security guarantees
    -------------------
    - Only serves files whose path is stored on a known asset_render record.
    - The resolved absolute path must be inside one of the allowed render
      directories (FFMPEG_OUTPUT_DIR or /tmp/signalforge_renders).
    - Raw file paths are never accepted from the frontend; only the render_id
      is accepted and the path is looked up server-side.
    - Returns 403 if the resolved path escapes the allowed directory (path
      traversal guard).
    - Returns 404 if the render record does not exist or the file is absent.
    """
    # Determine allowed render directories
    allowed_dirs = set()
    ffmpeg_out = os.getenv("FFMPEG_OUTPUT_DIR", "").strip()
    if ffmpeg_out:
        allowed_dirs.add(os.path.realpath(ffmpeg_out))
    allowed_dirs.add(os.path.realpath("/tmp/signalforge_renders"))

    db_client = get_client()
    try:
        db = get_database(db_client)
        record = find_asset_render(db, clean_text(render_id))
        if not record:
            raise HTTPException(status_code=404, detail="Asset render not found.")

        file_path = record.get("file_path", "")
        if not file_path or not file_path.endswith(".mp4"):
            raise HTTPException(status_code=404, detail="No MP4 file path on this render record.")

        real_path = os.path.realpath(file_path)

        # Path traversal guard: resolved path must be inside an allowed dir
        if not any(real_path.startswith(d + os.sep) or real_path == d for d in allowed_dirs):
            raise HTTPException(
                status_code=403,
                detail="File is outside the allowed render directory.",
            )

        if not os.path.isfile(real_path):
            raise HTTPException(
                status_code=404,
                detail="Render file not found on disk. It may have been cleaned up.",
            )

        return FileResponse(
            path=real_path,
            media_type="video/mp4",
            filename=os.path.basename(real_path),
        )
    finally:
        db_client.close()
# ===========================================================================
#
# v7.5 adds:
#   - manual_publish_logs   — human records of posts made outside the system
#   - asset_performance_records — manually entered or CSV-imported metrics
#   - creative_performance_summaries — aggregated insight per asset/snippet
#   - Deterministic performance_score formula (0.0 – 10.0)
#   - Advisory learning-loop recommendations (no auto-approvals)
#   - CSV import via JSON rows (no platform API calls)
#
# Safety:
#   - SignalForge does NOT publish, schedule, DM, or call social APIs.
#   - All records carry simulation_only=True, outbound_actions_taken=0.
#   - Recommendations are advisory only; no automatic approvals.
# ===========================================================================


# ---------------------------------------------------------------------------
# v7.5: Performance score helper
# ---------------------------------------------------------------------------

def calculate_performance_score(
    views: int = 0,
    likes: int = 0,
    comments: int = 0,
    shares: int = 0,
    saves: int = 0,
    clicks: int = 0,
    follows: int = 0,
    watch_time_seconds: float = 0.0,
    average_view_duration: float = 0.0,
    retention_rate: float = 0.0,
    engagement_rate: float = -1.0,
) -> tuple[float, str]:
    """Deterministic performance score in the range 0.0 – 10.0.

    Formula (weights sum to 1.0):
        0.25 × clamp(views / 10_000)        — reach (normalised to 10k views)
        0.20 × clamp(derived_engagement)    — engagement rate (0–1)
        0.20 × clamp(saves / 500)           — saves (normalised to 500)
        0.15 × clamp(shares / 200)          — shares (normalised to 200)
        0.15 × clamp(retention_rate)        — retention rate (0–1, provided)
        0.05 × clamp(clicks / 500)          — clicks (normalised to 500)

    engagement_rate is auto-derived from (likes + comments + shares + saves)
    / views when the caller passes engagement_rate < 0 or the default -1.
    Scores are rounded to 3 decimal places.
    """
    def clamp(x: float) -> float:
        return max(0.0, min(float(x), 1.0))

    if engagement_rate < 0:
        eng = (likes + comments + shares + saves) / views if views > 0 else 0.0
    else:
        eng = engagement_rate

    score = (
        0.25 * clamp(views / 10_000.0) +
        0.20 * clamp(eng) +
        0.20 * clamp(saves / 500.0) +
        0.15 * clamp(shares / 200.0) +
        0.15 * clamp(retention_rate) +
        0.05 * clamp(clicks / 500.0)
    ) * 10.0

    reason = (
        f"views_norm={clamp(views/10_000.0):.3f}, "
        f"engagement={clamp(eng):.3f}, "
        f"saves_norm={clamp(saves/500.0):.3f}, "
        f"shares_norm={clamp(shares/200.0):.3f}, "
        f"retention={clamp(retention_rate):.3f}, "
        f"clicks_norm={clamp(clicks/500.0):.3f}"
    )
    return round(score, 3), reason


# ---------------------------------------------------------------------------
# v7.5: Pydantic models
# ---------------------------------------------------------------------------

VALID_PLATFORMS_V75 = frozenset({
    "instagram", "tiktok", "youtube", "youtube_shorts", "facebook",
    "twitter", "linkedin", "pinterest", "snapchat", "other",
})


class ManualPublishLogCreateRequest(BaseModel):
    workspace_slug: str = ""
    client_id: str = ""
    asset_render_id: str = ""
    platform: str = ""
    manual_post_url: str = ""
    posted_by: str = ""
    posted_at: str = ""
    caption_used: str = ""
    hook_used: str = ""
    notes: str = ""


class AssetPerformanceRecordCreateRequest(BaseModel):
    workspace_slug: str = ""
    client_id: str = ""
    asset_render_id: str = ""
    manual_publish_log_id: str = ""
    platform: str = ""
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    clicks: int = 0
    follows: int = 0
    watch_time_seconds: float = 0.0
    average_view_duration: float = 0.0
    retention_rate: float = 0.0
    engagement_rate: float = -1.0
    imported_from: Literal["manual", "csv"] = "manual"
    notes: str = ""


class PerformanceCSVImportRequest(BaseModel):
    """Import performance records from pre-parsed CSV rows.

    Each row dict must contain at least asset_render_id or manual_publish_log_id
    and numeric metric fields.  Rows that fail validation are stored in
    import_errors rather than silently discarded.
    """
    workspace_slug: str = ""
    client_id: str = ""
    rows: list[dict]


class PerformanceSummaryGenerateRequest(BaseModel):
    workspace_slug: str = ""
    client_id: str = ""
    asset_render_id: str = ""
    snippet_id: str = ""
    prompt_generation_id: str = ""
    notes: str = ""


# ---------------------------------------------------------------------------
# v7.5: Manual Publish Logs
# ---------------------------------------------------------------------------

@app.post("/manual-publish-logs", status_code=201)
def create_manual_publish_log(payload: ManualPublishLogCreateRequest) -> dict:
    """Record a post that was published manually outside SignalForge.

    SignalForge does not publish or schedule anything.  This endpoint records
    the fact that a human manually published a rendered asset so that
    performance data can later be linked to the asset.
    """
    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)
        doc = {
            "workspace_slug": clean_text(payload.workspace_slug),
            "client_id": clean_text(payload.client_id),
            "asset_render_id": clean_text(payload.asset_render_id),
            "platform": clean_text(payload.platform),
            "manual_post_url": clean_text(payload.manual_post_url),
            "posted_by": clean_text(payload.posted_by),
            "posted_at": clean_text(payload.posted_at),
            "caption_used": clean_text(payload.caption_used),
            "hook_used": clean_text(payload.hook_used),
            "notes": clean_text(payload.notes),
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "created_at": now,
            "updated_at": now,
        }
        result = db.manual_publish_logs.insert_one(doc)
        created = db.manual_publish_logs.find_one({"_id": result.inserted_id})
        return {
            "item": serialize(created),
            "message": "Manual publish log recorded. SignalForge did not publish or schedule anything.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.get("/manual-publish-logs")
def list_manual_publish_logs(
    workspace_slug: str = Query(""),
    client_id: str = Query(""),
    asset_render_id: str = Query(""),
    platform: str = Query(""),
    limit: int = Query(100),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if client_id:
            query["client_id"] = client_id
        if asset_render_id:
            query["asset_render_id"] = asset_render_id
        if platform:
            query["platform"] = platform
        cursor = db.manual_publish_logs.find(query).sort("created_at").limit(limit)
        items = [serialize(d) for d in cursor]
        return {"items": items, "total": len(items), "simulation_only": True, "outbound_actions_taken": 0}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# v7.5: Asset Performance Records
# ---------------------------------------------------------------------------

@app.post("/asset-performance-records", status_code=201)
def create_asset_performance_record(payload: AssetPerformanceRecordCreateRequest) -> dict:
    """Store manually entered performance metrics for a published asset.

    Calculates a deterministic performance_score (0.0 – 10.0) from the
    provided metrics.  The score is advisory only and does not trigger
    any automatic approvals or outbound actions.
    """
    now = utc_now()

    # Validate numeric fields
    for field_name, field_val in [
        ("views", payload.views), ("likes", payload.likes), ("comments", payload.comments),
        ("shares", payload.shares), ("saves", payload.saves), ("clicks", payload.clicks),
        ("follows", payload.follows),
    ]:
        if field_val < 0:
            raise HTTPException(status_code=422, detail=f"{field_name} must be >= 0.")
    if not (0.0 <= payload.retention_rate <= 1.0) and payload.retention_rate != -1.0:
        raise HTTPException(status_code=422, detail="retention_rate must be between 0.0 and 1.0.")
    if payload.engagement_rate != -1.0 and not (0.0 <= payload.engagement_rate <= 1.0):
        raise HTTPException(status_code=422, detail="engagement_rate must be between 0.0 and 1.0 (or -1.0 for auto).")

    perf_score, score_reason = calculate_performance_score(
        views=payload.views,
        likes=payload.likes,
        comments=payload.comments,
        shares=payload.shares,
        saves=payload.saves,
        clicks=payload.clicks,
        follows=payload.follows,
        watch_time_seconds=payload.watch_time_seconds,
        average_view_duration=payload.average_view_duration,
        retention_rate=payload.retention_rate,
        engagement_rate=payload.engagement_rate,
    )

    client = get_client()
    try:
        db = get_database(client)
        doc = {
            "workspace_slug": clean_text(payload.workspace_slug),
            "client_id": clean_text(payload.client_id),
            "asset_render_id": clean_text(payload.asset_render_id),
            "manual_publish_log_id": clean_text(payload.manual_publish_log_id),
            "platform": clean_text(payload.platform),
            "views": payload.views,
            "likes": payload.likes,
            "comments": payload.comments,
            "shares": payload.shares,
            "saves": payload.saves,
            "clicks": payload.clicks,
            "follows": payload.follows,
            "watch_time_seconds": payload.watch_time_seconds,
            "average_view_duration": payload.average_view_duration,
            "retention_rate": payload.retention_rate,
            "engagement_rate": payload.engagement_rate,
            "performance_score": perf_score,
            "score_reason": score_reason,
            "imported_from": payload.imported_from,
            "notes": clean_text(payload.notes),
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "recorded_at": now,
            "created_at": now,
            "updated_at": now,
        }
        result = db.asset_performance_records.insert_one(doc)
        created = db.asset_performance_records.find_one({"_id": result.inserted_id})
        return {
            "item": serialize(created),
            "performance_score": perf_score,
            "score_reason": score_reason,
            "message": "Performance record stored. Score is advisory only. No automatic approvals or outbound actions.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.get("/asset-performance-records")
def list_asset_performance_records(
    workspace_slug: str = Query(""),
    client_id: str = Query(""),
    asset_render_id: str = Query(""),
    manual_publish_log_id: str = Query(""),
    platform: str = Query(""),
    limit: int = Query(100),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if client_id:
            query["client_id"] = client_id
        if asset_render_id:
            query["asset_render_id"] = asset_render_id
        if manual_publish_log_id:
            query["manual_publish_log_id"] = manual_publish_log_id
        if platform:
            query["platform"] = platform
        cursor = db.asset_performance_records.find(query).sort("recorded_at").limit(limit)
        items = [serialize(d) for d in cursor]
        return {"items": items, "total": len(items), "simulation_only": True, "outbound_actions_taken": 0}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# v7.5: CSV import for performance records
# ---------------------------------------------------------------------------

_CSV_INT_FIELDS = {"views", "likes", "comments", "shares", "saves", "clicks", "follows"}
_CSV_FLOAT_FIELDS = {"watch_time_seconds", "average_view_duration", "retention_rate", "engagement_rate"}


@app.post("/asset-performance-records/import-csv")
def import_performance_csv(payload: PerformanceCSVImportRequest) -> dict:
    """Import performance records from pre-parsed CSV rows.

    The caller is responsible for parsing the CSV into a list of dicts.
    No platform API calls are made.  Rows that fail validation are stored
    in import_errors and the valid rows are written to the database.
    """
    if not payload.rows:
        raise HTTPException(status_code=422, detail="rows must be a non-empty list.")
    if len(payload.rows) > 1000:
        raise HTTPException(status_code=422, detail="Maximum 1000 rows per import.")

    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)
        imported: list[dict] = []
        import_errors: list[dict] = []

        for idx, row in enumerate(payload.rows):
            row_errors: list[str] = []

            # Coerce and validate int fields
            coerced: dict[str, Any] = {}
            for f in _CSV_INT_FIELDS:
                raw = row.get(f, 0)
                try:
                    v = int(raw)
                    if v < 0:
                        row_errors.append(f"{f} must be >= 0 (got {v})")
                    coerced[f] = max(0, v)
                except (TypeError, ValueError):
                    row_errors.append(f"{f} is not a valid integer (got {raw!r})")
                    coerced[f] = 0

            for f in _CSV_FLOAT_FIELDS:
                raw = row.get(f, 0.0 if f != "engagement_rate" else -1.0)
                try:
                    v = float(raw)
                    coerced[f] = v
                except (TypeError, ValueError):
                    row_errors.append(f"{f} is not a valid float (got {raw!r})")
                    coerced[f] = -1.0 if f == "engagement_rate" else 0.0

            # Validate retention_rate bounds
            ret = coerced.get("retention_rate", 0.0)
            eng = coerced.get("engagement_rate", -1.0)
            if ret < 0.0 or ret > 1.0:
                row_errors.append(f"retention_rate must be 0.0–1.0 (got {ret})")
                coerced["retention_rate"] = 0.0
            if eng != -1.0 and (eng < 0.0 or eng > 1.0):
                row_errors.append(f"engagement_rate must be 0.0–1.0 or -1.0 for auto (got {eng})")
                coerced["engagement_rate"] = -1.0

            if row_errors:
                import_errors.append({"row_index": idx, "errors": row_errors, "row": row})
                continue

            perf_score, score_reason = calculate_performance_score(**{k: coerced[k] for k in _CSV_INT_FIELDS | _CSV_FLOAT_FIELDS})

            doc = {
                "workspace_slug": clean_text(payload.workspace_slug or str(row.get("workspace_slug", ""))),
                "client_id": clean_text(payload.client_id or str(row.get("client_id", ""))),
                "asset_render_id": clean_text(str(row.get("asset_render_id", ""))),
                "manual_publish_log_id": clean_text(str(row.get("manual_publish_log_id", ""))),
                "platform": clean_text(str(row.get("platform", ""))),
                **{k: coerced[k] for k in _CSV_INT_FIELDS | _CSV_FLOAT_FIELDS},
                "performance_score": perf_score,
                "score_reason": score_reason,
                "imported_from": "csv",
                "notes": clean_text(str(row.get("notes", ""))),
                "simulation_only": True,
                "outbound_actions_taken": 0,
                "recorded_at": now,
                "created_at": now,
                "updated_at": now,
            }
            insert_result = db.asset_performance_records.insert_one(doc)
            created = db.asset_performance_records.find_one({"_id": insert_result.inserted_id})
            imported.append(serialize(created))

        return {
            "imported_count": len(imported),
            "error_count": len(import_errors),
            "import_errors": import_errors,
            "items": imported,
            "message": f"Imported {len(imported)} record(s). {len(import_errors)} row(s) had validation errors.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# v7.5: Creative Performance Summaries
# ---------------------------------------------------------------------------

@app.post("/creative-performance-summaries/generate")
def generate_creative_performance_summary(payload: PerformanceSummaryGenerateRequest) -> dict:
    """Aggregate performance records for an asset into a summary.

    Pulls asset_performance_records for the given asset_render_id, looks up
    the associated snippet/prompt metadata, computes aggregate metrics, and
    upserts a creative_performance_summary record.

    The summary is advisory only; it does not approve snippets or trigger
    outbound actions.  It also returns learning-loop recommendations based
    on historically top-performing hook_types and prompt_types for the
    client/platform.
    """
    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)

        asset_render_id = clean_text(payload.asset_render_id)
        workspace_slug = clean_text(payload.workspace_slug)
        client_id = clean_text(payload.client_id)

        # Resolve asset render for metadata
        render_doc: dict[str, Any] = {}
        if asset_render_id:
            rd = find_asset_render(db, asset_render_id)
            if rd:
                render_doc = rd

        snippet_id = clean_text(payload.snippet_id) or clean_text(str(render_doc.get("snippet_id", "")))
        prompt_generation_id = (
            clean_text(payload.prompt_generation_id) or
            clean_text(str(render_doc.get("prompt_generation_id", "")))
        )
        generation_engine = clean_text(str(render_doc.get("generation_engine", "")))
        platform = clean_text(str(render_doc.get("platform", "")))

        # Pull performance records
        perf_query: dict[str, Any] = {}
        if workspace_slug:
            perf_query["workspace_slug"] = workspace_slug
        if asset_render_id:
            perf_query["asset_render_id"] = asset_render_id
        perf_records = list(db.asset_performance_records.find(perf_query))

        # Aggregate
        if perf_records:
            scores = [r.get("performance_score", 0.0) for r in perf_records]
            avg_score = round(sum(scores) / len(scores), 3)
            best_score = round(max(scores), 3)
        else:
            avg_score = 0.0
            best_score = 0.0

        # Determine winning_factors from metrics
        if perf_records:
            total_views = sum(r.get("views", 0) for r in perf_records)
            total_saves = sum(r.get("saves", 0) for r in perf_records)
            total_shares = sum(r.get("shares", 0) for r in perf_records)
            avg_retention = sum(r.get("retention_rate", 0.0) for r in perf_records) / len(perf_records)
            winning_factors: list[str] = []
            if total_views > 5000:
                winning_factors.append("high_reach")
            if total_saves > 100:
                winning_factors.append("high_saves")
            if total_shares > 50:
                winning_factors.append("high_shares")
            if avg_retention > 0.5:
                winning_factors.append("strong_retention")
            if not winning_factors:
                winning_factors = ["no_standout_factors"]
        else:
            winning_factors = []

        # Resolve hook_type / prompt_type from snippet / prompt_gen
        hook_type = ""
        prompt_type = ""
        snippet_doc = db.content_snippets.find_one({"_id": snippet_id}) if snippet_id else None
        if snippet_doc:
            hook_type = clean_text(str(snippet_doc.get("hook_type", "")))
        prompt_doc = find_prompt_generation(db, prompt_generation_id) if prompt_generation_id else None
        if prompt_doc:
            prompt_type = clean_text(str(prompt_doc.get("prompt_type", "")))
            if not generation_engine:
                generation_engine = clean_text(str(prompt_doc.get("generation_engine_target", "")))

        improvement_notes = clean_text(payload.notes) or (
            "No performance records linked yet. Enter metrics via POST /asset-performance-records."
            if not perf_records else ""
        )

        summary_doc = {
            "workspace_slug": workspace_slug,
            "client_id": client_id,
            "snippet_id": snippet_id,
            "prompt_generation_id": prompt_generation_id,
            "asset_render_id": asset_render_id,
            "hook_type": hook_type,
            "prompt_type": prompt_type,
            "generation_engine": generation_engine,
            "platform": platform,
            "performance_score": avg_score,
            "best_performance_score": best_score,
            "record_count": len(perf_records),
            "score_reason": f"avg of {len(perf_records)} record(s); best={best_score}",
            "winning_factors": winning_factors,
            "improvement_notes": improvement_notes,
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "created_at": now,
            "updated_at": now,
        }

        # Upsert by asset_render_id + workspace_slug
        upsert_query: dict[str, Any] = {}
        if asset_render_id:
            upsert_query["asset_render_id"] = asset_render_id
        if workspace_slug:
            upsert_query["workspace_slug"] = workspace_slug

        if upsert_query:
            existing = db.creative_performance_summaries.find_one(upsert_query)
            if existing:
                db.creative_performance_summaries.update_one(
                    upsert_query,
                    {"$set": {**summary_doc, "updated_at": now}},
                )
                created_summary = db.creative_performance_summaries.find_one(upsert_query)
            else:
                res = db.creative_performance_summaries.insert_one(summary_doc)
                created_summary = db.creative_performance_summaries.find_one({"_id": res.inserted_id})
        else:
            res = db.creative_performance_summaries.insert_one(summary_doc)
            created_summary = db.creative_performance_summaries.find_one({"_id": res.inserted_id})

        # --- Learning loop recommendations ---
        recommendations = _build_recommendations(db, workspace_slug, client_id, platform)

        return {
            "item": serialize(created_summary),
            "recommendations": recommendations,
            "message": "Summary generated. Recommendations are advisory only. No approvals or outbound actions taken.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.get("/creative-performance-summaries")
def list_creative_performance_summaries(
    workspace_slug: str = Query(""),
    client_id: str = Query(""),
    platform: str = Query(""),
    hook_type: str = Query(""),
    prompt_type: str = Query(""),
    limit: int = Query(100),
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
        if hook_type:
            query["hook_type"] = hook_type
        if prompt_type:
            query["prompt_type"] = prompt_type
        cursor = db.creative_performance_summaries.find(query).sort("performance_score").limit(limit)
        items = [serialize(d) for d in cursor]
        return {"items": items, "total": len(items), "simulation_only": True, "outbound_actions_taken": 0}
    finally:
        client.close()


@app.get("/creative-performance-summaries/recommendations")
def get_performance_recommendations(
    workspace_slug: str = Query(""),
    client_id: str = Query(""),
    platform: str = Query(""),
    limit: int = Query(5),
) -> dict:
    """Return advisory learning-loop recommendations.

    Aggregates creative_performance_summaries to find historically top-
    performing hook_types and prompt_types for the given client/platform.
    Results are advisory only; no approvals or outbound actions occur.
    """
    client = get_client()
    try:
        db = get_database(client)
        recommendations = _build_recommendations(db, workspace_slug, client_id, platform, limit=limit)
        return {
            **recommendations,
            "message": "Advisory recommendations only. No automatic approvals or outbound actions.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# v7.5: Learning loop helper
# ---------------------------------------------------------------------------

def _build_recommendations(
    db: Any,
    workspace_slug: str,
    client_id: str,
    platform: str,
    limit: int = 5,
) -> dict:
    """Aggregate performance summaries into advisory recommendations.

    Returns top hook_types and prompt_types ranked by average performance_score.
    These are advisory only — SignalForge never auto-approves based on them.
    """
    query: dict[str, Any] = {}
    if workspace_slug:
        query["workspace_slug"] = workspace_slug
    if client_id:
        query["client_id"] = client_id
    if platform:
        query["platform"] = platform

    summaries = list(db.creative_performance_summaries.find(query))

    # Group by hook_type
    hook_scores: dict[str, list[float]] = defaultdict(list)
    prompt_scores: dict[str, list[float]] = defaultdict(list)
    engine_scores: dict[str, list[float]] = defaultdict(list)
    platform_scores: dict[str, list[float]] = defaultdict(list)

    for s in summaries:
        score = float(s.get("performance_score", 0.0))
        if s.get("hook_type"):
            hook_scores[s["hook_type"]].append(score)
        if s.get("prompt_type"):
            prompt_scores[s["prompt_type"]].append(score)
        if s.get("generation_engine"):
            engine_scores[s["generation_engine"]].append(score)
        if s.get("platform"):
            platform_scores[s["platform"]].append(score)

    def top_n(score_map: dict[str, list[float]], n: int) -> list[dict]:
        ranked = sorted(
            [
                {"value": k, "avg_score": round(sum(v) / len(v), 3), "record_count": len(v)}
                for k, v in score_map.items()
            ],
            key=lambda x: x["avg_score"],
            reverse=True,
        )
        return ranked[:n]

    return {
        "top_hook_types": top_n(hook_scores, limit),
        "top_prompt_types": top_n(prompt_scores, limit),
        "top_generation_engines": top_n(engine_scores, limit),
        "top_platforms": top_n(platform_scores, limit),
        "based_on_summary_count": len(summaries),
        "advisory_only": True,
        "note": (
            "These recommendations are based on historical performance data. "
            "They are advisory only. No automatic approvals or outbound actions are taken."
        ),
    }


# ===========================================================================
# v8: Client Campaign Packs
# ===========================================================================
# Adds three collections:
#   campaign_packs           — top-level pack record per client/campaign
#   campaign_pack_items      — individual pipeline items attached to a pack
#   campaign_reports         — advisory reports generated from a pack
#
# Safety guarantees:
#   - simulation_only: True and outbound_actions_taken: 0 on every record
#   - No publishing, scheduling, or social API calls at any point
#   - Reports are advisory and human-review only
#   - Items are cross-checked for workspace + client match before insertion
# ===========================================================================

VALID_PACK_STATUSES = frozenset({"draft", "needs_review", "approved", "archived"})
VALID_REPORT_STATUSES = frozenset({"draft", "needs_review", "approved"})
VALID_REVIEW_DECISIONS = frozenset({"approve", "reject", "revise"})
VALID_ITEM_TYPES = frozenset({
    "source_content",
    "snippet",
    "prompt_generation",
    "asset_render",
    "publish_log",
    "performance_record",
})


# ---------------------------------------------------------------------------
# v8: Pydantic models
# ---------------------------------------------------------------------------

class CampaignPackCreateRequest(BaseModel):
    workspace_slug: str
    client_id: str = ""
    campaign_name: str
    campaign_goal: str = ""
    target_platforms: list[str] = Field(default_factory=list)
    target_audience: str = ""
    content_themes: list[str] = Field(default_factory=list)
    source_content_ids: list[str] = Field(default_factory=list)
    snippet_ids: list[str] = Field(default_factory=list)
    prompt_generation_ids: list[str] = Field(default_factory=list)
    asset_render_ids: list[str] = Field(default_factory=list)
    manual_publish_log_ids: list[str] = Field(default_factory=list)
    performance_record_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    recommendations: str = ""


class CampaignPackItemCreateRequest(BaseModel):
    workspace_slug: str
    client_id: str = ""
    item_type: str
    item_id: str
    title: str = ""
    description: str = ""
    status: str = "draft"
    sort_order: int = 0


class CampaignReportReviewRequest(BaseModel):
    workspace_slug: str
    decision: str  # approve | reject | revise
    reviewer_notes: str = ""


# ---------------------------------------------------------------------------
# v8: Helpers
# ---------------------------------------------------------------------------

def _build_campaign_report(db: Any, pack: dict) -> dict:
    """Aggregate pack items into an advisory report dict.

    Pulls performance data from asset_performance_records and
    creative_performance_summaries where they exist.  Safe when empty.
    """
    workspace_slug = pack.get("workspace_slug", "")
    client_id = pack.get("client_id", "")
    pack_id = str(pack["_id"])

    # Pull items for this pack
    items = list(db.campaign_pack_items.find({"campaign_pack_id": pack_id}))

    # Collect referenced IDs by type
    render_ids = [i["item_id"] for i in items if i.get("item_type") == "asset_render"]
    snippet_ids = [i["item_id"] for i in items if i.get("item_type") == "snippet"]

    # Performance records for pack assets
    perf_query: dict[str, Any] = {"workspace_slug": workspace_slug}
    if client_id:
        perf_query["client_id"] = client_id
    perf_records = list(db.asset_performance_records.find(perf_query))

    # Filter to only records whose asset_render_id appears in this pack
    if render_ids:
        perf_records = [r for r in perf_records if r.get("asset_render_id") in render_ids]

    # Score aggregation
    scores = [float(r.get("performance_score", 0.0)) for r in perf_records if r.get("performance_score") is not None]
    avg_score = round(sum(scores) / len(scores), 3) if scores else None
    top_score = round(max(scores), 3) if scores else None

    # Top assets by score
    asset_scores: dict[str, list[float]] = defaultdict(list)
    for r in perf_records:
        aid = r.get("asset_render_id", "")
        if aid:
            asset_scores[aid].append(float(r.get("performance_score", 0.0)))
    top_assets = sorted(
        [{"asset_render_id": k, "avg_score": round(sum(v) / len(v), 3)} for k, v in asset_scores.items()],
        key=lambda x: x["avg_score"],
        reverse=True,
    )[:5]

    # Hook aggregation from performance summaries
    summaries = list(db.creative_performance_summaries.find(perf_query))
    if render_ids:
        summaries = [s for s in summaries if s.get("asset_render_id") in render_ids]

    hook_scores: dict[str, list[float]] = defaultdict(list)
    prompt_type_scores: dict[str, list[float]] = defaultdict(list)
    for s in summaries:
        sc = float(s.get("performance_score", 0.0))
        if s.get("hook_type"):
            hook_scores[s["hook_type"]].append(sc)
        if s.get("prompt_type"):
            prompt_type_scores[s["prompt_type"]].append(sc)

    def _rank(d: dict[str, list[float]]) -> list[dict]:
        return sorted(
            [{"value": k, "avg_score": round(sum(v) / len(v), 3)} for k, v in d.items()],
            key=lambda x: x["avg_score"],
            reverse=True,
        )[:5]

    # Top snippets: prefer approved, sort by created_at desc
    top_snippet_ids = snippet_ids[:5]

    now = utc_now()
    return {
        "workspace_slug": workspace_slug,
        "client_id": client_id,
        "campaign_pack_id": pack_id,
        "report_title": f"Campaign Report — {pack.get('campaign_name', '')}",
        "executive_summary": (
            f"This campaign pack contains {len(items)} item(s) across "
            f"{len(set(i.get('item_type') for i in items))} pipeline stage(s). "
            f"Performance data covers {len(perf_records)} record(s)."
            + (f" Average performance score: {avg_score}/10." if avg_score is not None else " No performance data yet.")
        ),
        "top_snippets": top_snippet_ids,
        "top_hooks": _rank(hook_scores),
        "top_prompt_types": _rank(prompt_type_scores),
        "top_assets": top_assets,
        "performance_summary": {
            "record_count": len(perf_records),
            "avg_score": avg_score,
            "top_score": top_score,
        },
        "lessons_learned": (
            "Review the top-performing hooks and prompt types above to inform the next creative batch. "
            "Focus on assets with avg_score ≥ 7 for repeat use."
        ),
        "next_recommendations": (
            "Use top hook types and prompt types when generating the next batch of prompts. "
            "Archive low-performing source content (score < 4) and review for replacement."
        ),
        "status": "draft",
        "advisory_only": True,
        "simulation_only": True,
        "outbound_actions_taken": 0,
        "created_at": now,
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# v8: Campaign Packs endpoints
# ---------------------------------------------------------------------------

@app.post("/campaign-packs", status_code=201)
def create_campaign_pack(payload: CampaignPackCreateRequest) -> dict:
    """Create a new campaign pack.

    A campaign pack aggregates all pipeline records for a single client
    campaign into one reviewable package.  SignalForge does not publish,
    schedule, or take any outbound action.
    """
    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)
        doc = {
            "workspace_slug": clean_text(payload.workspace_slug),
            "client_id": clean_text(payload.client_id),
            "campaign_name": clean_text(payload.campaign_name),
            "campaign_goal": clean_text(payload.campaign_goal),
            "target_platforms": [clean_text(p) for p in payload.target_platforms],
            "target_audience": clean_text(payload.target_audience),
            "content_themes": [clean_text(t) for t in payload.content_themes],
            "source_content_ids": [clean_text(i) for i in payload.source_content_ids],
            "snippet_ids": [clean_text(i) for i in payload.snippet_ids],
            "prompt_generation_ids": [clean_text(i) for i in payload.prompt_generation_ids],
            "asset_render_ids": [clean_text(i) for i in payload.asset_render_ids],
            "manual_publish_log_ids": [clean_text(i) for i in payload.manual_publish_log_ids],
            "performance_record_ids": [clean_text(i) for i in payload.performance_record_ids],
            "status": "draft",
            "summary": clean_text(payload.summary),
            "recommendations": clean_text(payload.recommendations),
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "created_at": now,
            "updated_at": now,
        }
        result = db.campaign_packs.insert_one(doc)
        created = db.campaign_packs.find_one({"_id": result.inserted_id})
        return {
            "item": serialize(created),
            "message": "Campaign pack created. SignalForge has not published or scheduled anything.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.get("/campaign-packs")
def list_campaign_packs(
    workspace_slug: str = Query(""),
    client_id: str = Query(""),
    status: str = Query(""),
    limit: int = Query(100),
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
        cursor = db.campaign_packs.find(query).sort("created_at").limit(limit)
        items = [serialize(d) for d in cursor]
        return {"items": items, "total": len(items), "simulation_only": True, "outbound_actions_taken": 0}
    finally:
        client.close()


@app.get("/campaign-packs/{pack_id}")
def get_campaign_pack(pack_id: str) -> dict:
    """Return a single campaign pack with its items."""
    client = get_client()
    try:
        db = get_database(client)
        try:
            oid = ObjectId(pack_id)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid pack_id format.")
        pack = db.campaign_packs.find_one({"_id": oid})
        if not pack:
            raise HTTPException(status_code=404, detail="Campaign pack not found.")
        items = list(db.campaign_pack_items.find({"campaign_pack_id": pack_id}).sort("sort_order"))
        return {
            "item": serialize(pack),
            "pack_items": [serialize(i) for i in items],
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.post("/campaign-packs/{pack_id}/items", status_code=201)
def add_campaign_pack_item(pack_id: str, payload: CampaignPackItemCreateRequest) -> dict:
    """Add a pipeline item to a campaign pack.

    Validates that the item's workspace and client match the pack.
    Items from a different workspace or client are rejected.
    """
    if payload.item_type not in VALID_ITEM_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"item_type must be one of: {sorted(VALID_ITEM_TYPES)}",
        )
    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)
        try:
            oid = ObjectId(pack_id)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid pack_id format.")
        pack = db.campaign_packs.find_one({"_id": oid})
        if not pack:
            raise HTTPException(status_code=404, detail="Campaign pack not found.")

        # Workspace isolation check
        req_ws = clean_text(payload.workspace_slug)
        if req_ws and pack.get("workspace_slug") and req_ws != pack["workspace_slug"]:
            raise HTTPException(
                status_code=422,
                detail="Item workspace_slug does not match pack workspace_slug.",
            )

        # Client isolation check
        req_client = clean_text(payload.client_id)
        if req_client and pack.get("client_id") and req_client != pack["client_id"]:
            raise HTTPException(
                status_code=422,
                detail="Item client_id does not match pack client_id.",
            )

        doc = {
            "workspace_slug": pack.get("workspace_slug", ""),
            "campaign_pack_id": pack_id,
            "item_type": clean_text(payload.item_type),
            "item_id": clean_text(payload.item_id),
            "title": clean_text(payload.title),
            "description": clean_text(payload.description),
            "status": clean_text(payload.status) or "draft",
            "sort_order": int(payload.sort_order),
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "created_at": now,
        }
        result = db.campaign_pack_items.insert_one(doc)
        created = db.campaign_pack_items.find_one({"_id": result.inserted_id})
        return {
            "item": serialize(created),
            "message": "Item added to campaign pack.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.post("/campaign-packs/{pack_id}/generate-report", status_code=201)
def generate_campaign_report(pack_id: str) -> dict:
    """Generate an advisory campaign report for a pack.

    Aggregates performance data and learning-loop insights into a
    human-readable report.  The report is advisory only — it does not
    trigger publishing, approvals, or any outbound action.
    """
    client = get_client()
    try:
        db = get_database(client)
        try:
            oid = ObjectId(pack_id)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid pack_id format.")
        pack = db.campaign_packs.find_one({"_id": oid})
        if not pack:
            raise HTTPException(status_code=404, detail="Campaign pack not found.")

        report_doc = _build_campaign_report(db, pack)
        result = db.campaign_reports.insert_one(report_doc)
        created = db.campaign_reports.find_one({"_id": result.inserted_id})
        return {
            "item": serialize(created),
            "message": (
                "Campaign report generated. Advisory only — "
                "no publishing, scheduling, or outbound actions taken."
            ),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# v8: Campaign Reports endpoints
# ---------------------------------------------------------------------------

@app.get("/campaign-reports")
def list_campaign_reports(
    workspace_slug: str = Query(""),
    client_id: str = Query(""),
    campaign_pack_id: str = Query(""),
    status: str = Query(""),
    limit: int = Query(100),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if client_id:
            query["client_id"] = client_id
        if campaign_pack_id:
            query["campaign_pack_id"] = campaign_pack_id
        if status:
            query["status"] = status
        cursor = db.campaign_reports.find(query).sort("created_at").limit(limit)
        items = [serialize(d) for d in cursor]
        return {"items": items, "total": len(items), "simulation_only": True, "outbound_actions_taken": 0}
    finally:
        client.close()


@app.post("/campaign-reports/{report_id}/review")
def review_campaign_report(report_id: str, payload: CampaignReportReviewRequest) -> dict:
    """Mark a campaign report as approved, rejected, or needing revision.

    This is a human-review step only.  Approving a report does NOT trigger
    publishing, scheduling, or any outbound action.
    """
    if payload.decision not in VALID_REVIEW_DECISIONS:
        raise HTTPException(
            status_code=422,
            detail=f"decision must be one of: {sorted(VALID_REVIEW_DECISIONS)}",
        )
    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)
        try:
            oid = ObjectId(report_id)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid report_id format.")
        report = db.campaign_reports.find_one({"_id": oid})
        if not report:
            raise HTTPException(status_code=404, detail="Campaign report not found.")

        status_map = {"approve": "approved", "reject": "draft", "revise": "needs_review"}
        new_status = status_map[payload.decision]
        db.campaign_reports.update_one(
            {"_id": oid},
            {"$set": {
                "status": new_status,
                "reviewer_notes": clean_text(payload.reviewer_notes),
                "reviewed_at": now,
                "updated_at": now,
            }},
        )
        updated = db.campaign_reports.find_one({"_id": oid})
        return {
            "item": serialize(updated),
            "message": (
                f"Report marked as {new_status}. "
                "No publishing or outbound actions triggered."
            ),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()

# ===========================================================================
# v8.5: Client Export Package
# ===========================================================================

VALID_EXPORT_FORMATS = {"markdown", "zip", "pdf_placeholder"}
VALID_EXPORT_STATUSES = {"queued", "generated", "needs_review", "approved", "rejected", "failed"}
VALID_EXPORT_REVIEW_DECISIONS = {"approve", "reject", "revise"}

EXPORT_BASE_DIR = os.environ.get("SIGNALFORGE_EXPORT_DIR", "/tmp/signalforge_exports")


class CampaignExportCreateRequest(BaseModel):
    workspace_slug: str = ""
    client_id: str = ""
    campaign_pack_id: str
    campaign_report_id: str
    export_name: str = ""
    export_format: str = "markdown"
    included_sections: list[str] = []


class CampaignExportReviewRequest(BaseModel):
    workspace_slug: str = ""
    decision: str
    reviewer_notes: str = ""


def _build_export_markdown(pack: dict, report: dict, pack_items: list, asset_renders_by_id: dict) -> str:
    """Build the full markdown export string from pack + report data."""
    lines: list[str] = []

    # 1. Campaign Overview
    lines.append("# Campaign Export Report\n")
    lines.append("## 1. Campaign Overview\n")
    lines.append(f"- **Campaign Name:** {pack.get('campaign_name', '')}")
    lines.append(f"- **Client ID:** {pack.get('client_id', '')}")
    lines.append(f"- **Goal:** {pack.get('campaign_goal', '')}")
    lines.append(f"- **Platforms:** {', '.join(pack.get('target_platforms') or [])}")
    lines.append(f"- **Audience:** {pack.get('target_audience', '')}")
    lines.append(f"- **Themes:** {', '.join(pack.get('content_themes') or [])}")
    lines.append(f"- **Pack Status:** {pack.get('status', '')}\n")

    # 2. Executive Summary
    lines.append("## 2. Executive Summary\n")
    lines.append((report.get("executive_summary") or "_No executive summary available._") + "\n")

    # 3. Source Content Summary
    sc_items = [i for i in pack_items if i.get("item_type") == "source_content"]
    lines.append(f"## 3. Source Content Summary ({len(sc_items)} items)\n")
    if sc_items:
        for item in sc_items:
            lines.append(
                f"- {item.get('title') or item.get('item_id', 'Unknown')} "
                f"— status: {item.get('status', 'unknown')}"
            )
    else:
        lines.append("_No source content items in this pack._")
    lines.append("")

    # 4. Top Snippets
    top_hooks = report.get("top_hooks") or []
    lines.append(f"## 4. Top Snippets ({len(top_hooks)} items)\n")
    if top_hooks:
        for hook in top_hooks[:10]:
            if isinstance(hook, dict):
                lines.append(
                    f"- **Hook:** {hook.get('hook_text', '')} "
                    f"| **Type:** {hook.get('hook_type', '')} "
                    f"| **Score:** {hook.get('overall_score', '')}"
                )
    else:
        lines.append("_No top snippets data available._")
    lines.append("")

    # 5. Prompt Strategy
    prompt_items = [i for i in pack_items if i.get("item_type") == "prompt_generation"]
    lines.append(f"## 5. Prompt Strategy ({len(prompt_items)} items)\n")
    if prompt_items:
        for item in prompt_items:
            lines.append(
                f"- {item.get('title') or item.get('item_id', 'Unknown')} "
                f"— status: {item.get('status', 'unknown')}"
            )
    else:
        lines.append("_No prompt generation items in this pack._")
    lines.append("")

    # 6. Rendered Assets
    asset_items = [i for i in pack_items if i.get("item_type") == "asset_render"]
    lines.append(f"## 6. Rendered Assets ({len(asset_items)} items)\n")
    for item in asset_items:
        item_id = item.get("item_id", "")
        render = asset_renders_by_id.get(item_id) or {}
        local_path = render.get("local_file_path", "")
        lines.append(f"- **ID:** {item_id}")
        lines.append(f"  - Title: {item.get('title', '')}")
        lines.append(f"  - Local path: {local_path or '_not available_'}")
        lines.append(f"  - Status: {render.get('status') or item.get('status', 'unknown')}")
    if not asset_items:
        lines.append("_No rendered assets in this pack._")
    lines.append("")

    # 7. Manual Performance Summary
    perf = report.get("performance_summary") or {}
    lines.append("## 7. Manual Performance Summary\n")
    lines.append(f"- **Records:** {perf.get('record_count', 0)}")
    avg = perf.get("avg_score")
    top = perf.get("top_score")
    lines.append(f"- **Avg Score:** {avg if avg is not None else 'N/A'}")
    lines.append(f"- **Top Score:** {top if top is not None else 'N/A'}\n")

    # 8. Lessons Learned
    lines.append("## 8. Lessons Learned\n")
    learned = report.get("lessons_learned") or []
    if learned:
        for lesson in learned:
            lines.append(f"- {lesson}")
    else:
        lines.append("_No lessons learned data available._")
    lines.append("")

    recs = report.get("next_recommendations") or []
    lines.append("### Next Recommendations\n")
    if recs:
        for rec in recs:
            lines.append(f"- {rec}")
    else:
        lines.append("_No recommendations available._")
    lines.append("")

    # 9. Safety & Audit Notes
    lines.append("## 9. Safety & Audit Notes\n")
    lines.append("- No publishing performed by SignalForge at any step.")
    lines.append("- No scheduling performed by SignalForge at any step.")
    lines.append("- No DMs or outbound messages sent.")
    lines.append("- No social platform API calls made.")
    lines.append("- `simulation_only: true`")
    lines.append("- `outbound_actions_taken: 0`")
    lines.append("- This export is for local review and client delivery only.")
    lines.append("- Human approval required before any external use.")
    lines.append("")

    return "\n".join(lines)


def _generate_export(db: Any, pack: dict, report: dict, payload: "CampaignExportCreateRequest", now: datetime) -> tuple[str, list, list]:
    """Write export files to local filesystem.

    Returns (export_path, included_assets, safety_notes).
    No network calls, no uploads, no email — local filesystem only.
    """
    pack_id_str = str(pack.get("_id", ""))
    ws = clean_text(payload.workspace_slug) or pack.get("workspace_slug", "default")
    ts = now.strftime("%Y%m%d_%H%M%S")
    export_name = clean_text(payload.export_name) or "export"
    fmt = clean_text(payload.export_format)

    # Fetch pack items
    pack_items = list(db.campaign_pack_items.find({"campaign_pack_id": pack_id_str}))

    # Gather asset renders for each asset_render item
    asset_items = [i for i in pack_items if i.get("item_type") == "asset_render"]
    asset_renders_by_id: dict[str, dict] = {}
    for item in asset_items:
        item_id = item.get("item_id", "")
        try:
            render = db.asset_renders.find_one({"_id": ObjectId(item_id)})
        except Exception:
            render = None
        if render:
            asset_renders_by_id[item_id] = render

    md_content = _build_export_markdown(pack, report, pack_items, asset_renders_by_id)

    safety_notes = [
        "No publishing performed by SignalForge.",
        "No scheduling performed by SignalForge.",
        "No outbound actions taken.",
        "simulation_only=true on all records.",
        "Human review required before any external use.",
    ]

    # Create output directory
    base_dir = os.path.join(EXPORT_BASE_DIR, ws, pack_id_str)
    os.makedirs(base_dir, exist_ok=True)

    included_assets: list[str] = []

    if fmt == "markdown":
        export_path = os.path.join(base_dir, f"{export_name}_{ts}.md")
        with open(export_path, "w", encoding="utf-8") as fh:
            fh.write(md_content)

    elif fmt == "zip":
        export_path = os.path.join(base_dir, f"{export_name}_{ts}.zip")
        with zipfile.ZipFile(export_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("report.md", md_content)
            # Include local asset files that actually exist on disk
            for item in asset_items:
                item_id = item.get("item_id", "")
                render = asset_renders_by_id.get(item_id) or {}
                local_path = render.get("local_file_path", "")
                if local_path and os.path.isfile(local_path):
                    asset_name = os.path.basename(local_path)
                    zf.write(local_path, f"assets/{asset_name}")
                    included_assets.append(local_path)
            # manifest.json
            manifest = {
                "export_name": export_name,
                "export_format": "zip",
                "campaign_pack_id": pack_id_str,
                "campaign_report_id": str(report.get("_id", "")),
                "workspace_slug": ws,
                "client_id": pack.get("client_id", ""),
                "generated_at": now.isoformat(),
                "included_assets": included_assets,
                "safety_notes": safety_notes,
                "simulation_only": True,
                "outbound_actions_taken": 0,
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    elif fmt == "pdf_placeholder":
        export_path = os.path.join(base_dir, f"{export_name}_{ts}_placeholder.md")
        pdf_note = (
            "\n\n---\n\n"
            "> **PDF Generation Note:** PDF export is not yet implemented in this version. "
            "This placeholder markdown file contains the full report content. "
            "Use an external markdown-to-PDF converter if a PDF is needed.\n"
        )
        with open(export_path, "w", encoding="utf-8") as fh:
            fh.write(md_content + pdf_note)

    else:
        export_path = ""

    return export_path, included_assets, safety_notes


# ---------------------------------------------------------------------------
# v8.5: Campaign Exports endpoints
# ---------------------------------------------------------------------------

@app.post("/campaign-exports", status_code=201)
def create_campaign_export(payload: CampaignExportCreateRequest) -> dict:
    """Create a local export package for a campaign pack + report.

    Writes files to the local filesystem only.  No uploading, emailing,
    scheduling, or any outbound action is performed.
    """
    if payload.export_format not in VALID_EXPORT_FORMATS:
        raise HTTPException(
            status_code=422,
            detail=f"export_format must be one of: {sorted(VALID_EXPORT_FORMATS)}",
        )
    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)

        # Validate campaign pack
        try:
            pack_oid = ObjectId(payload.campaign_pack_id)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid campaign_pack_id format.")
        pack = db.campaign_packs.find_one({"_id": pack_oid})
        if not pack:
            raise HTTPException(status_code=404, detail="Campaign pack not found.")

        # Validate campaign report
        try:
            report_oid = ObjectId(payload.campaign_report_id)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid campaign_report_id format.")
        report = db.campaign_reports.find_one({"_id": report_oid})
        if not report:
            raise HTTPException(status_code=404, detail="Campaign report not found.")

        # Workspace isolation
        req_ws = clean_text(payload.workspace_slug)
        if req_ws and pack.get("workspace_slug") != req_ws:
            raise HTTPException(status_code=422, detail="workspace_slug does not match campaign pack.")

        # Client isolation
        req_client = clean_text(payload.client_id)
        if req_client and pack.get("client_id") and pack.get("client_id") != req_client:
            raise HTTPException(status_code=422, detail="client_id does not match campaign pack.")

        # Generate local export files
        try:
            export_path, included_assets, safety_notes = _generate_export(db, pack, report, payload, now)
            export_status = "generated"
        except Exception as exc:
            export_path = ""
            included_assets = []
            safety_notes = [str(exc)]
            export_status = "failed"

        doc = {
            "workspace_slug": pack.get("workspace_slug", ""),
            "client_id": pack.get("client_id", ""),
            "campaign_pack_id": str(pack.get("_id", "")),
            "campaign_report_id": str(report.get("_id", "")),
            "export_name": clean_text(payload.export_name) or "export",
            "export_format": clean_text(payload.export_format),
            "export_status": export_status,
            "export_path": export_path,
            "included_assets": included_assets,
            "included_sections": list(payload.included_sections),
            "safety_notes": safety_notes,
            "generated_at": now,
            "reviewed_at": None,
            "reviewer_notes": "",
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "created_at": now,
            "updated_at": now,
        }
        result = db.campaign_exports.insert_one(doc)
        created = db.campaign_exports.find_one({"_id": result.inserted_id})
        return {
            "item": serialize(created),
            "message": (
                "Campaign export generated locally. "
                "No publishing, scheduling, uploading, or outbound actions performed."
            ),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.get("/campaign-exports")
def list_campaign_exports(
    workspace_slug: str = Query(""),
    client_id: str = Query(""),
    campaign_pack_id: str = Query(""),
    status: str = Query(""),
    limit: int = Query(100),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if client_id:
            query["client_id"] = client_id
        if campaign_pack_id:
            query["campaign_pack_id"] = campaign_pack_id
        if status:
            query["export_status"] = status
        cursor = db.campaign_exports.find(query).sort("created_at").limit(limit)
        items = [serialize(d) for d in cursor]
        return {
            "items": items,
            "total": len(items),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.get("/campaign-exports/{export_id}")
def get_campaign_export(export_id: str) -> dict:
    """Return a single campaign export record."""
    client = get_client()
    try:
        db = get_database(client)
        try:
            oid = ObjectId(export_id)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid export_id format.")
        export = db.campaign_exports.find_one({"_id": oid})
        if not export:
            raise HTTPException(status_code=404, detail="Campaign export not found.")
        return {
            "item": serialize(export),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.post("/campaign-exports/{export_id}/review")
def review_campaign_export(export_id: str, payload: CampaignExportReviewRequest) -> dict:
    """Mark an export as approved, rejected, or needing revision.

    This is a human review step only.  Approving an export does NOT upload,
    email, publish, schedule, or trigger any outbound action.
    """
    if payload.decision not in VALID_EXPORT_REVIEW_DECISIONS:
        raise HTTPException(
            status_code=422,
            detail=f"decision must be one of: {sorted(VALID_EXPORT_REVIEW_DECISIONS)}",
        )
    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)
        try:
            oid = ObjectId(export_id)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid export_id format.")
        export = db.campaign_exports.find_one({"_id": oid})
        if not export:
            raise HTTPException(status_code=404, detail="Campaign export not found.")

        status_map = {
            "approve": "approved",
            "reject": "rejected",
            "revise": "needs_review",
        }
        new_status = status_map[payload.decision]
        db.campaign_exports.update_one(
            {"_id": oid},
            {"$set": {
                "export_status": new_status,
                "reviewer_notes": clean_text(payload.reviewer_notes),
                "reviewed_at": now,
                "updated_at": now,
            }},
        )
        updated = db.campaign_exports.find_one({"_id": oid})
        return {
            "item": serialize(updated),
            "message": (
                f"Export marked as {new_status}. "
                "No uploading, publishing, or outbound actions triggered."
            ),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()

# ===========================================================================
# Pillar 3: Commerce — trackable link + hosted checkout for digital assets
# ===========================================================================
#
# Stripe Checkout (hosted payment page) only — card data never touches this
# server. Gated behind STRIPE_ENABLED (default false); simulated/no-key mode
# returns a fake checkout URL with zero network calls, same fallback
# precedent as every other real integration in this file. An offer's public
# link (/o/{slug}) 404s until an operator explicitly approves it, mirroring
# every other approval gate in this codebase (snippets, prompt generations,
# asset renders, campaign exports). The two lead-facing endpoints (webhook,
# download) are NOT protected by _require_auth_6u (nothing in this app is,
# by default) — they carry their own explicit security: Stripe signature
# verification, and a download gate keyed on a completed transaction rather
# than a guessable file path.

VALID_OFFER_REVIEW_DECISIONS = {"approve", "reject"}


@app.get("/settings/stripe-status")
def stripe_status() -> dict:
    from stripe_client import is_configured, health_check  # noqa: PLC0415

    configured = is_configured()
    reachability = health_check() if configured else {"reachable": False, "error": "not configured"}
    return {
        "enabled": env_enabled(os.getenv("STRIPE_ENABLED", "false")),
        "configured": configured,
        **reachability,
    }


class CommerceOfferCreateRequest(BaseModel):
    workspace_slug: str = ""
    client_id: str = ""
    title: str
    description: str = ""
    price_cents: int
    currency: str = "usd"
    source_campaign_export_id: str


class CommerceOfferReviewRequest(BaseModel):
    decision: str
    note: str = ""


def _generate_offer_slug(db: Any) -> str:
    import secrets as _secrets_commerce  # noqa: PLC0415

    for _ in range(10):
        slug = _secrets_commerce.token_urlsafe(6).replace("_", "").replace("-", "")[:8].lower()
        if slug and not db.commerce_offers.find_one({"slug": slug}):
            return slug
    raise HTTPException(status_code=500, detail="Could not generate a unique offer slug.")


@app.post("/commerce/offers")
def create_commerce_offer(payload: CommerceOfferCreateRequest) -> dict:
    """
    Create a draft offer for a digital asset. Draft offers have no live
    public link — only an approved offer's /o/{slug} link is reachable.
    """
    if payload.price_cents <= 0:
        raise HTTPException(status_code=422, detail="price_cents must be greater than 0.")
    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)

        try:
            export_oid = ObjectId(payload.source_campaign_export_id)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid source_campaign_export_id format.")
        export = db.campaign_exports.find_one({"_id": export_oid})
        if not export:
            raise HTTPException(status_code=404, detail="Campaign export not found.")
        if export.get("export_status") != "approved":
            raise HTTPException(
                status_code=422,
                detail=(
                    "Campaign export must be approved before it can be sold. "
                    f"Current status: {export.get('export_status', 'unknown')}"
                ),
            )

        doc = {
            "workspace_slug": clean_text(payload.workspace_slug) or export.get("workspace_slug", ""),
            "client_id": clean_text(payload.client_id) or export.get("client_id", ""),
            "title": clean_text(payload.title),
            "description": clean_text(payload.description),
            "price_cents": int(payload.price_cents),
            "currency": (clean_text(payload.currency) or "usd").lower(),
            "source_campaign_export_id": str(export["_id"]),
            "slug": _generate_offer_slug(db),
            "status": "draft",
            "click_count": 0,
            "review_events": [],
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "created_at": now,
            "updated_at": now,
        }
        result = db.commerce_offers.insert_one(doc)
        created = db.commerce_offers.find_one({"_id": result.inserted_id})
        return {
            "item": serialize(created),
            "message": "Offer created as draft. Approve it before its public link goes live.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.get("/commerce/offers")
def list_commerce_offers(
    workspace_slug: str = Query(""),
    client_id: str = Query(""),
    status: str = Query(""),
    limit: int = Query(100),
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
        cursor = db.commerce_offers.find(query).sort("created_at").limit(limit)
        items = [serialize(d) for d in cursor]
        return {
            "items": items,
            "total": len(items),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.get("/commerce/offers/{offer_id}")
def get_commerce_offer(offer_id: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        try:
            oid = ObjectId(offer_id)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid offer_id format.")
        offer = db.commerce_offers.find_one({"_id": oid})
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found.")
        return {
            "item": serialize(offer),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.post("/commerce/offers/{offer_id}/review")
def review_commerce_offer(offer_id: str, payload: CommerceOfferReviewRequest) -> dict:
    """
    Approve or reject an offer. Only an approved offer's /o/{slug} link is
    publicly reachable — this is the sole gate between a draft offer and a
    real, chargeable Stripe Checkout link.
    """
    if payload.decision not in VALID_OFFER_REVIEW_DECISIONS:
        raise HTTPException(
            status_code=422,
            detail=f"decision must be one of: {sorted(VALID_OFFER_REVIEW_DECISIONS)}",
        )
    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)
        try:
            oid = ObjectId(offer_id)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid offer_id format.")
        offer = db.commerce_offers.find_one({"_id": oid})
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found.")

        new_status = "approved" if payload.decision == "approve" else "rejected"
        review_event = {"decision": payload.decision, "note": payload.note, "reviewed_at": now}
        db.commerce_offers.update_one(
            {"_id": oid},
            {
                "$set": {"status": new_status, "updated_at": now},
                "$push": {"review_events": review_event},
            },
        )
        updated = db.commerce_offers.find_one({"_id": oid})
        return {
            "item": serialize(updated),
            "message": f"Offer {payload.decision}d.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.get("/commerce/transactions")
def list_commerce_transactions(
    offer_id: str = Query(""),
    workspace_slug: str = Query(""),
    status: str = Query(""),
    limit: int = Query(100),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        if offer_id:
            query["offer_id"] = offer_id
        elif workspace_slug:
            offer_ids = [
                str(o["_id"]) for o in db.commerce_offers.find({"workspace_slug": workspace_slug}, {"_id": 1})
            ]
            query["offer_id"] = {"$in": offer_ids}
        cursor = db.checkout_transactions.find(query).sort("occurred_at", -1).limit(limit)
        items = [serialize(d) for d in cursor]
        return {
            "items": items,
            "total": len(items),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


# ── Public/lead-facing endpoints — no _require_auth_6u, explicit own security ──

@app.get("/o/{slug}")
def commerce_offer_redirect(slug: str) -> RedirectResponse:
    """
    Public trackable link. 404s unless the offer is approved. Creates a
    Stripe Checkout Session and redirects the browser to Stripe's hosted
    payment page — no card data ever reaches this server.
    """
    from stripe_client import create_checkout_session  # noqa: PLC0415

    client = get_client()
    try:
        db = get_database(client)
        offer = db.commerce_offers.find_one({"slug": slug, "status": "approved"})
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found or not available.")

        db.commerce_offers.update_one({"_id": offer["_id"]}, {"$inc": {"click_count": 1}})

        base_url = os.getenv("SIGNALFORGE_PUBLIC_BASE_URL", "http://localhost:5174").rstrip("/")
        success_url = f"{base_url}/api/o/{slug}/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{base_url}/api/o/{slug}/cancel"

        session = create_checkout_session(
            {
                "offer_id": str(offer["_id"]),
                "title": offer["title"],
                "price_cents": offer["price_cents"],
                "currency": offer["currency"],
            },
            success_url=success_url,
            cancel_url=cancel_url,
        )

        db.checkout_transactions.insert_one({
            "offer_id": str(offer["_id"]),
            "stripe_session_id": session["session_id"],
            "stripe_payment_intent_id": "",
            "status": "pending",
            "amount_cents": offer["price_cents"],
            "currency": offer["currency"],
            "buyer_email": "",
            "occurred_at": utc_now(),
            "simulation_only": session.get("simulated", True),
        })

        return RedirectResponse(url=session["checkout_url"], status_code=302)
    finally:
        client.close()


@app.get("/o/{slug}/success")
def commerce_offer_success(slug: str, session_id: str = Query("")) -> HTMLResponse:
    """
    Landing point after Stripe Checkout. Verifies payment (via the
    webhook-recorded transaction, falling back to a live Stripe lookup if
    the webhook hasn't landed yet) before revealing the download link — the
    download itself is gated again, independently, at download time.
    """
    from stripe_client import retrieve_session  # noqa: PLC0415

    client = get_client()
    try:
        db = get_database(client)
        offer = db.commerce_offers.find_one({"slug": slug})
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found.")

        txn = db.checkout_transactions.find_one({"stripe_session_id": session_id})
        paid = bool(txn and txn.get("status") == "completed")

        if not paid and session_id.startswith("sim_session_"):
            # Simulated mode: no real Stripe to confirm against — mark paid
            # immediately since STRIPE_ENABLED=false means this is a dry run.
            db.checkout_transactions.update_one(
                {"stripe_session_id": session_id}, {"$set": {"status": "completed"}}
            )
            paid = True
        elif not paid and session_id:
            try:
                remote = retrieve_session(session_id)
                if remote.get("payment_status") == "paid":
                    db.checkout_transactions.update_one(
                        {"stripe_session_id": session_id},
                        {"$set": {
                            "status": "completed",
                            "buyer_email": (remote.get("customer_details") or {}).get("email", ""),
                        }},
                    )
                    paid = True
            except Exception:
                pass

        if paid:
            body = (
                f"<h1>Thank you!</h1><p>Your download is ready: "
                f"<a href=\"/api/commerce/download/{session_id}\">Download {offer.get('title', '')}</a></p>"
            )
        else:
            body = "<h1>Payment not yet confirmed</h1><p>Please refresh this page in a moment.</p>"
        return HTMLResponse(content=body)
    finally:
        client.close()


@app.get("/o/{slug}/cancel")
def commerce_offer_cancel(slug: str) -> HTMLResponse:
    return HTMLResponse(content="<h1>Checkout cancelled</h1><p>No payment was made.</p>")


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request) -> dict:
    """
    Stripe webhook receiver. Verifies the Stripe-Signature header before
    trusting anything in the payload — this is the one endpoint in the app
    where a bypassed check would be a real financial/data-integrity issue.
    """
    from stripe_client import verify_webhook_signature, StripeWebhookError  # noqa: PLC0415

    raw_body = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = verify_webhook_signature(raw_body, sig_header)
    except StripeWebhookError as exc:
        raise HTTPException(status_code=400, detail=f"Webhook verification failed: {exc}")

    client = get_client()
    try:
        db = get_database(client)
        if event.get("type") == "checkout.session.completed":
            session = (event.get("data") or {}).get("object") or {}
            session_id = session.get("id", "")
            if session_id:
                db.checkout_transactions.update_one(
                    {"stripe_session_id": session_id},
                    {"$set": {
                        "status": "completed",
                        "stripe_payment_intent_id": session.get("payment_intent", ""),
                        "buyer_email": (session.get("customer_details") or {}).get("email", ""),
                    }},
                )
        return {"received": True}
    finally:
        client.close()


@app.get("/commerce/download/{stripe_session_id}")
def commerce_download(stripe_session_id: str) -> FileResponse:
    """
    Serve the purchased file. Gated on a COMPLETED transaction for this
    exact session id — not a guessable file path. Reuses the same
    path-traversal guard as GET /asset-renders/{render_id}/stream.
    """
    client = get_client()
    try:
        db = get_database(client)
        txn = db.checkout_transactions.find_one(
            {"stripe_session_id": stripe_session_id, "status": "completed"}
        )
        if not txn:
            raise HTTPException(status_code=404, detail="No completed purchase found for this session.")

        try:
            offer = db.commerce_offers.find_one({"_id": ObjectId(txn["offer_id"])})
            export = (
                db.campaign_exports.find_one({"_id": ObjectId(offer["source_campaign_export_id"])})
                if offer else None
            )
        except Exception:
            offer, export = None, None
        if not offer or not export or not export.get("export_path"):
            raise HTTPException(status_code=404, detail="Deliverable file not found.")

        real_path = os.path.realpath(export["export_path"])
        allowed_dir = os.path.realpath(EXPORT_BASE_DIR)
        if not (real_path.startswith(allowed_dir + os.sep) or real_path == allowed_dir):
            raise HTTPException(status_code=403, detail="File is outside the allowed export directory.")
        if not os.path.isfile(real_path):
            raise HTTPException(status_code=404, detail="Export file not found on disk.")

        return FileResponse(real_path, filename=os.path.basename(real_path))
    finally:
        client.close()


# ===========================================================================
# v9.5: Client Intelligence Layer
# ===========================================================================
#
# Unifies acquisition (leads) + content (campaigns, performance) into a
# structured intelligence record per client.
#
# Safety guarantees:
#   - No posting, scheduling, DMs, or external API calls at any step.
#   - All records carry simulation_only=True, outbound_actions_taken=0.
#   - All intelligence and correlation outputs are advisory_only=True.
#   - Workspace and client isolation enforced at every endpoint.
# ===========================================================================

from client_intelligence import (
    build_client_intelligence,
    correlate_lead_to_content_patterns,
    calculate_estimated_roi,
    identify_top_performers,
)

VALID_CONVERSION_STATUSES = {"prospect", "contacted", "converted", "inactive"}
VALID_FUNNEL_STAGE_IMPACTS = {"awareness", "engagement", "conversion"}


# ---------------------------------------------------------------------------
# v9.5: Models
# ---------------------------------------------------------------------------

class ClientProfileIntelligencePatchRequest(BaseModel):
    workspace_slug: str = ""
    source_lead_id: str = ""
    acquisition_score: float = 0.0
    acquisition_notes: str = ""
    conversion_status: str = "prospect"
    conversion_date: str = ""
    lifetime_value_estimate: float = 0.0
    content_fit_score: float = 0.0


class CampaignPackLinkRequest(BaseModel):
    workspace_slug: str = ""
    linked_lead_id: str = ""
    linked_deal_id: str = ""
    campaign_roi_estimate: float = 0.0
    performance_summary_score: float = 0.0


class AssetPerformanceIntelligencePatchRequest(BaseModel):
    workspace_slug: str = ""
    estimated_revenue_impact: float = 0.0
    funnel_stage_impact: str = ""
    attribution_notes: str = ""


class ClientIntelligenceGenerateRequest(BaseModel):
    workspace_slug: str = ""


class LeadContentCorrelationGenerateRequest(BaseModel):
    workspace_slug: str = ""
    lead_id: str = ""
    client_id: str = ""


# ---------------------------------------------------------------------------
# v9.5: PATCH extensions for existing collections
# ---------------------------------------------------------------------------

@app.patch("/client-profiles/{client_id}/intelligence")
def patch_client_profile_intelligence(
    client_id: str,
    payload: ClientProfileIntelligencePatchRequest,
) -> dict:
    """Add intelligence fields to an existing client profile.

    No external actions. Data linking only.
    """
    if payload.conversion_status and payload.conversion_status not in VALID_CONVERSION_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"conversion_status must be one of: {sorted(VALID_CONVERSION_STATUSES)}",
        )
    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)
        profile = find_client_profile(db, client_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Client profile not found.")

        req_ws = clean_text(payload.workspace_slug)
        if req_ws and profile.get("workspace_slug") != req_ws:
            raise HTTPException(status_code=422, detail="workspace_slug does not match client profile.")

        update_fields: dict[str, Any] = {
            "updated_at": now,
        }
        if payload.source_lead_id:
            update_fields["source_lead_id"] = clean_text(payload.source_lead_id)
        if payload.acquisition_score:
            update_fields["acquisition_score"] = float(payload.acquisition_score)
        if payload.acquisition_notes:
            update_fields["acquisition_notes"] = clean_text(payload.acquisition_notes)
        if payload.conversion_status:
            update_fields["conversion_status"] = payload.conversion_status
        if payload.conversion_date:
            update_fields["conversion_date"] = clean_text(payload.conversion_date)
        if payload.lifetime_value_estimate:
            update_fields["lifetime_value_estimate"] = float(payload.lifetime_value_estimate)
        if payload.content_fit_score:
            update_fields["content_fit_score"] = float(payload.content_fit_score)

        db.client_profiles.update_one({"_id": profile["_id"]}, {"$set": update_fields})
        updated = find_client_profile(db, client_id)
        return {
            "item": serialize(updated),
            "message": "Client profile intelligence fields updated. No external actions taken.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.patch("/campaign-packs/{pack_id}/link")
def patch_campaign_pack_link(pack_id: str, payload: CampaignPackLinkRequest) -> dict:
    """Link a campaign pack to a lead and/or deal for full traceability.

    Data linking only — no external actions.
    """
    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)
        try:
            pack_oid = ObjectId(pack_id)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid pack_id format.")
        pack = db.campaign_packs.find_one({"_id": pack_oid})
        if not pack:
            raise HTTPException(status_code=404, detail="Campaign pack not found.")

        req_ws = clean_text(payload.workspace_slug)
        if req_ws and pack.get("workspace_slug") != req_ws:
            raise HTTPException(status_code=422, detail="workspace_slug does not match campaign pack.")

        update_fields: dict[str, Any] = {"updated_at": now}
        if payload.linked_lead_id:
            update_fields["linked_lead_id"] = clean_text(payload.linked_lead_id)
        if payload.linked_deal_id:
            update_fields["linked_deal_id"] = clean_text(payload.linked_deal_id)
        if payload.campaign_roi_estimate:
            update_fields["campaign_roi_estimate"] = float(payload.campaign_roi_estimate)
        if payload.performance_summary_score:
            update_fields["performance_summary_score"] = float(payload.performance_summary_score)

        db.campaign_packs.update_one({"_id": pack_oid}, {"$set": update_fields})
        updated = db.campaign_packs.find_one({"_id": pack_oid})
        return {
            "item": serialize(updated),
            "message": "Campaign pack linked. No external actions taken.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


@app.patch("/asset-performance-records/{record_id}/intelligence")
def patch_asset_performance_intelligence(
    record_id: str,
    payload: AssetPerformanceIntelligencePatchRequest,
) -> dict:
    """Add intelligence fields (revenue impact, funnel stage) to a performance record.

    Data enrichment only — no external actions.
    """
    if payload.funnel_stage_impact and payload.funnel_stage_impact not in VALID_FUNNEL_STAGE_IMPACTS:
        raise HTTPException(
            status_code=422,
            detail=f"funnel_stage_impact must be one of: {sorted(VALID_FUNNEL_STAGE_IMPACTS)}",
        )
    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)
        try:
            oid = ObjectId(record_id)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid record_id format.")
        record = db.asset_performance_records.find_one({"_id": oid})
        if not record:
            raise HTTPException(status_code=404, detail="Asset performance record not found.")

        req_ws = clean_text(payload.workspace_slug)
        if req_ws and record.get("workspace_slug") != req_ws:
            raise HTTPException(status_code=422, detail="workspace_slug does not match record.")

        update_fields: dict[str, Any] = {"updated_at": now}
        if payload.estimated_revenue_impact:
            update_fields["estimated_revenue_impact"] = float(payload.estimated_revenue_impact)
        if payload.funnel_stage_impact:
            update_fields["funnel_stage_impact"] = payload.funnel_stage_impact
        if payload.attribution_notes:
            update_fields["attribution_notes"] = clean_text(payload.attribution_notes)

        db.asset_performance_records.update_one({"_id": oid}, {"$set": update_fields})
        updated = db.asset_performance_records.find_one({"_id": oid})
        return {
            "item": serialize(updated),
            "message": "Performance record intelligence fields updated. No external actions taken.",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# v9.5: Client Intelligence endpoints
# ---------------------------------------------------------------------------

@app.post("/client-intelligence/{client_id}/generate", status_code=201)
def generate_client_intelligence(
    client_id: str,
    payload: ClientIntelligenceGenerateRequest,
) -> dict:
    """Generate a client intelligence record.

    Aggregates performance data, snippets, and campaign reports into
    structured insights and recommendations.

    Advisory only. No external actions at any step.
    """
    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)

        # Validate client exists
        profile = find_client_profile(db, client_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Client profile not found.")

        req_ws = clean_text(payload.workspace_slug)
        if req_ws and profile.get("workspace_slug") != req_ws:
            raise HTTPException(
                status_code=422,
                detail="workspace_slug does not match client profile.",
            )

        workspace_slug = profile.get("workspace_slug", req_ws)

        intelligence = build_client_intelligence(db, client_id, workspace_slug)
        doc = {
            **intelligence,
            "generated_at": now,
            "created_at": now,
            "updated_at": now,
        }
        result = db.client_intelligence_records.insert_one(doc)
        created = db.client_intelligence_records.find_one({"_id": result.inserted_id})
        return {
            "item": serialize(created),
            "message": (
                "Client intelligence generated. Advisory only. "
                "No external actions, posts, messages, or API calls performed."
            ),
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "advisory_only": True,
        }
    finally:
        client.close()


@app.get("/client-intelligence")
def list_client_intelligence(
    workspace_slug: str = Query(""),
    client_id: str = Query(""),
    limit: int = Query(100),
) -> dict:
    """List client intelligence records, optionally filtered."""
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if client_id:
            query["client_id"] = client_id
        cursor = db.client_intelligence_records.find(query).sort("created_at").limit(limit)
        items = [serialize(d) for d in cursor]
        return {
            "items": items,
            "total": len(items),
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "advisory_only": True,
        }
    finally:
        client.close()


@app.get("/client-intelligence/{client_id}")
def get_client_intelligence(
    client_id: str,
    workspace_slug: str = Query(""),
) -> dict:
    """Return the most recent intelligence record for a client."""
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {"client_id": client_id}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        # Get the most recent record
        cursor = db.client_intelligence_records.find(query).sort("created_at").limit(1)
        records = list(cursor)
        if not records:
            raise HTTPException(
                status_code=404,
                detail="No intelligence record found for this client.",
            )
        return {
            "item": serialize(records[-1]),
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "advisory_only": True,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# v9.5: Lead-Content Correlation endpoints
# ---------------------------------------------------------------------------

@app.post("/lead-content-correlations/generate", status_code=201)
def generate_lead_content_correlations(
    payload: LeadContentCorrelationGenerateRequest,
) -> dict:
    """Generate lead-to-content correlation records.

    Correlates a lead/client's conversion attributes to their content
    performance patterns. Advisory only. No external actions.
    """
    if not clean_text(payload.client_id):
        raise HTTPException(status_code=422, detail="client_id is required.")

    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)

        # Validate client exists
        profile = find_client_profile(db, payload.client_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Client profile not found.")

        req_ws = clean_text(payload.workspace_slug)
        if req_ws and profile.get("workspace_slug") != req_ws:
            raise HTTPException(
                status_code=422,
                detail="workspace_slug does not match client profile.",
            )

        workspace_slug = profile.get("workspace_slug", req_ws)
        lead_id = clean_text(payload.lead_id)

        correlations = correlate_lead_to_content_patterns(
            db, workspace_slug, lead_id, payload.client_id
        )

        inserted_ids: list[str] = []
        for corr in correlations:
            doc = {**corr, "generated_at": now, "created_at": now, "updated_at": now}
            result = db.lead_content_correlations.insert_one(doc)
            inserted_ids.append(str(result.inserted_id))

        return {
            "generated_count": len(inserted_ids),
            "correlation_ids": inserted_ids,
            "message": (
                f"{len(inserted_ids)} correlation record(s) generated. "
                "Advisory only. No external actions performed."
            ),
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "advisory_only": True,
        }
    finally:
        client.close()


@app.get("/lead-content-correlations")
def list_lead_content_correlations(
    workspace_slug: str = Query(""),
    lead_id: str = Query(""),
    client_id: str = Query(""),
    limit: int = Query(100),
) -> dict:
    """List lead-content correlations, optionally filtered."""
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if lead_id:
            query["lead_id"] = lead_id
        if client_id:
            query["client_id"] = client_id
        cursor = db.lead_content_correlations.find(query).sort("created_at").limit(limit)
        items = [serialize(d) for d in cursor]
        return {
            "items": items,
            "total": len(items),
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "advisory_only": True,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# v10.4 — Media Ingestion Layer
# ---------------------------------------------------------------------------
# Part 1: Shared Folder / Drive Ingestion
# Part 2: Approved URL Download (yt-dlp)
# Part 3: Diagnostics
#
# Safety: simulation_only=True, outbound_actions_taken=0 on all records.
# No publishing, no uploading, no social API calls.
# ---------------------------------------------------------------------------


@app.post("/media-folder-scans")
def create_media_folder_scan(payload: MediaFolderScanRequest) -> dict:
    """
    Scan a local folder (or synced Google Drive / Dropbox folder) for
    supported media files and register each as a media_intake_record.

    No files are uploaded, deleted, or transmitted externally.
    All discovered media starts review-gated (ingestion_status=discovered).
    """
    if _scan_media_folder is None:
        raise HTTPException(status_code=503, detail="media_folder_scanner module not available")

    now = utc_now()
    workspace_slug = clean_text(payload.workspace_slug)
    client_id = clean_text(payload.client_id)
    folder_path = clean_text(payload.folder_path)
    source_label = clean_text(payload.source_label)
    ingestion_source = clean_text(payload.ingestion_source) or "local_folder"

    mongo_client = get_client()
    try:
        db = get_database(mongo_client)

        # Collect existing paths and hashes to skip duplicates
        existing_paths: set[str] = set()
        existing_hashes: set[str] = set()
        if workspace_slug:
            for rec in db.media_intake_records.find(
                {"workspace_slug": workspace_slug, "original_file_path": {"$exists": True, "$ne": ""}},
                {"original_file_path": 1, "file_hash": 1},
            ):
                if rec.get("original_file_path"):
                    existing_paths.add(rec["original_file_path"])
                if rec.get("file_hash"):
                    existing_hashes.add(rec["file_hash"])

        scan_result = _scan_media_folder(
            workspace_slug=workspace_slug,
            client_id=client_id,
            folder_path=folder_path,
            source_label=source_label,
            ingestion_source=ingestion_source,
            compute_hashes=payload.compute_hashes,
            existing_paths=existing_paths,
            existing_hashes=existing_hashes,
        )

        # Persist scan record
        scan_doc: dict[str, Any] = {
            "workspace_slug": workspace_slug,
            "client_id": client_id,
            "folder_path": folder_path,
            "source_label": source_label,
            "ingestion_source": ingestion_source,
            "discovered_count": scan_result.discovered_count,
            "registered_count": 0,
            "skipped_count": scan_result.skipped_count,
            "failed_count": scan_result.failed_count,
            "errors": scan_result.errors,
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "created_at": now,
            "updated_at": now,
        }
        scan_res = db.media_folder_scans.insert_one(scan_doc)
        scan_id = str(scan_res.inserted_id)

        # Persist a media_intake_record for each discovered file
        registered_count = 0
        intake_ids: list[str] = []
        for sf in scan_result.items:
            if sf.ingestion_status != "discovered":
                continue
            intake_doc: dict[str, Any] = {
                "workspace_slug": workspace_slug,
                "client_id": client_id,
                "source_content_id": "",
                "scan_id": scan_id,
                "intake_method": "local_folder_scan",
                "ingestion_source": sf.ingestion_source,
                "original_file_path": sf.absolute_path,
                "media_path": sf.absolute_path,
                "filename": sf.filename,
                "extension": sf.extension,
                "media_type": sf.media_type,
                "size_bytes": sf.size_bytes,
                "modified_at": sf.modified_at,
                "duration_seconds": sf.duration_seconds,
                "file_hash": sf.file_hash,
                "source_label": source_label,
                "ingestion_status": "discovered",
                "ingestion_notes": sf.ingestion_notes,
                "status": "registered",
                "approved_for_download": False,
                "source_url": "",
                "error": "",
                "skip_reason": "",
                "notes": "",
                "simulation_only": True,
                "outbound_actions_taken": 0,
                "created_at": now,
                "updated_at": now,
            }
            r = db.media_intake_records.insert_one(intake_doc)
            intake_ids.append(str(r.inserted_id))
            registered_count += 1

        # Update scan record with actual registered_count
        db.media_folder_scans.update_one(
            {"_id": scan_res.inserted_id},
            {"$set": {"registered_count": registered_count, "updated_at": utc_now()}},
        )

        created_scan = serialize(db.media_folder_scans.find_one({"_id": scan_res.inserted_id}))
        return {
            "scan_id": scan_id,
            "item": created_scan,
            "discovered_count": scan_result.discovered_count,
            "registered_count": registered_count,
            "skipped_count": scan_result.skipped_count,
            "failed_count": scan_result.failed_count,
            "intake_ids": intake_ids,
            "errors": scan_result.errors,
            "message": (
                f"Folder scan complete. {scan_result.discovered_count} file(s) discovered, "
                f"{registered_count} registered, {scan_result.skipped_count} skipped. "
                "No uploads or external calls performed."
            ),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        mongo_client.close()


@app.get("/media-folder-scans")
def list_media_folder_scans(
    workspace_slug: str = Query(""),
    client_id: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    mongo_client = get_client()
    try:
        db = get_database(mongo_client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if client_id:
            query["client_id"] = client_id
        items = list(db.media_folder_scans.find(query).sort([("created_at", -1)]).limit(limit))
        return {"items": serialize(items), "total": len(items), "simulation_only": True, "outbound_actions_taken": 0}
    finally:
        mongo_client.close()


@app.get("/media-folder-scans/{scan_id}")
def get_media_folder_scan(scan_id: str) -> dict:
    mongo_client = get_client()
    try:
        db = get_database(mongo_client)
        query: dict[str, Any] = {}
        if ObjectId.is_valid(scan_id):
            query = {"$or": [{"_id": ObjectId(scan_id)}, {"_id": scan_id}]}
        else:
            query = {"_id": scan_id}
        doc = db.media_folder_scans.find_one(query)
        if not doc:
            raise HTTPException(status_code=404, detail="Media folder scan not found")
        return {"item": serialize(doc), "simulation_only": True, "outbound_actions_taken": 0}
    finally:
        mongo_client.close()


# ---------------------------------------------------------------------------
# v10.4 — Approved URL Download (yt-dlp)
# ---------------------------------------------------------------------------


@app.post("/approved-url-downloads")
def create_approved_url_download(payload: ApprovedUrlDownloadRequest) -> dict:
    """
    Download media from an approved URL using yt-dlp.

    Guards:
    - YTDLP_ENABLED must be true
    - permission_confirmed must be true
    - domain must be in YTDLP_ALLOWED_DOMAINS
    - yt-dlp binary must be available

    Downloaded files are stored locally only. Nothing is published.
    """
    if _download_approved_url is None:
        raise HTTPException(status_code=503, detail="approved_url_downloader module not available")

    now = utc_now()
    workspace_slug = clean_text(payload.workspace_slug)
    client_id = clean_text(payload.client_id)
    source_content_id = clean_text(payload.source_content_id)
    url = clean_text(payload.url)
    notes = clean_text(payload.notes)
    requested_format = clean_text(payload.requested_format) or "video"

    mongo_client = get_client()
    try:
        db = get_database(mongo_client)

        # Create download record (status: queued initially)
        download_doc: dict[str, Any] = {
            "workspace_slug": workspace_slug,
            "client_id": client_id,
            "source_content_id": source_content_id,
            "url": url,
            "permission_confirmed": payload.permission_confirmed,
            "requested_format": requested_format,
            "notes": notes,
            "output_path": "",
            "filename": "",
            "duration_seconds": None,
            "status": "queued",
            "error_message": "",
            "skip_reason": "",
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "created_at": now,
            "updated_at": now,
        }
        doc_res = db.approved_url_downloads.insert_one(download_doc)
        download_id = str(doc_res.inserted_id)

        # Attempt download
        result = _download_approved_url(
            workspace_slug=workspace_slug,
            client_id=client_id,
            url=url,
            permission_confirmed=payload.permission_confirmed,
            requested_format=requested_format,
            notes=notes,
            source_content_id=source_content_id,
        )

        # Update record with result
        update: dict[str, Any] = {
            "status": result.status,
            "output_path": result.output_path,
            "filename": result.filename,
            "duration_seconds": result.duration_seconds,
            "error_message": result.error_message,
            "skip_reason": result.skip_reason,
            "updated_at": utc_now(),
        }
        db.approved_url_downloads.update_one({"_id": doc_res.inserted_id}, {"$set": update})

        # If completed, create a media_intake_record
        intake_id = ""
        if result.status == "completed" and result.output_path:
            from pathlib import Path as _Path
            ext = _Path(result.output_path).suffix.lower()
            intake_doc: dict[str, Any] = {
                "workspace_slug": workspace_slug,
                "client_id": client_id,
                "source_content_id": source_content_id,
                "download_id": download_id,
                "intake_method": "yt_dlp",
                "ingestion_source": "yt_dlp",
                "original_file_path": result.output_path,
                "media_path": result.output_path,
                "filename": result.filename,
                "extension": ext,
                "media_type": "audio" if requested_format == "audio" else "video",
                "size_bytes": 0,
                "duration_seconds": result.duration_seconds,
                "file_hash": None,
                "source_url": url,
                "ingestion_status": "discovered",
                "ingestion_notes": f"Downloaded via yt-dlp. notes: {notes}",
                "status": "registered",
                "approved_for_download": True,
                "error": "",
                "skip_reason": "",
                "notes": notes,
                "simulation_only": True,
                "outbound_actions_taken": 0,
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            ir = db.media_intake_records.insert_one(intake_doc)
            intake_id = str(ir.inserted_id)
            db.approved_url_downloads.update_one(
                {"_id": doc_res.inserted_id},
                {"$set": {"intake_id": intake_id, "updated_at": utc_now()}},
            )

        created = serialize(db.approved_url_downloads.find_one({"_id": doc_res.inserted_id}))
        return {
            "download_id": download_id,
            "item": created,
            "intake_id": intake_id,
            "status": result.status,
            "skip_reason": result.skip_reason,
            "error_message": result.error_message,
            "message": _download_status_message(result),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
    finally:
        mongo_client.close()


def _download_status_message(result: Any) -> str:
    if result.status == "completed":
        return f"Download complete. File saved to {result.output_path}. No content published."
    if result.status == "skipped":
        return f"Download skipped: {result.skip_reason}"
    return f"Download failed: {result.error_message}"


@app.get("/approved-url-downloads")
def list_approved_url_downloads(
    workspace_slug: str = Query(""),
    client_id: str = Query(""),
    status: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    mongo_client = get_client()
    try:
        db = get_database(mongo_client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if client_id:
            query["client_id"] = client_id
        if status:
            query["status"] = status
        items = list(
            db.approved_url_downloads.find(query).sort([("created_at", -1)]).limit(limit)
        )
        return {"items": serialize(items), "total": len(items), "simulation_only": True, "outbound_actions_taken": 0}
    finally:
        mongo_client.close()


@app.get("/approved-url-downloads/{download_id}")
def get_approved_url_download(download_id: str) -> dict:
    mongo_client = get_client()
    try:
        db = get_database(mongo_client)
        query: dict[str, Any] = {}
        if ObjectId.is_valid(download_id):
            query = {"$or": [{"_id": ObjectId(download_id)}, {"_id": download_id}]}
        else:
            query = {"_id": download_id}
        doc = db.approved_url_downloads.find_one(query)
        if not doc:
            raise HTTPException(status_code=404, detail="Approved URL download not found")
        return {"item": serialize(doc), "simulation_only": True, "outbound_actions_taken": 0}
    finally:
        mongo_client.close()


@app.get("/media-ingestion/diagnostics")
def media_ingestion_diagnostics() -> dict:
    """
    Health check for the media ingestion layer.
    Returns scanner extension list and yt-dlp availability/configuration.
    No external calls are made.
    """
    ytdlp_diag: dict[str, Any] = {}
    if _ytdlp_diagnostics is not None:
        d = _ytdlp_diagnostics()
        ytdlp_diag = {
            "yt_dlp_enabled": d.yt_dlp_enabled,
            "yt_dlp_available": d.yt_dlp_available,
            "yt_dlp_path": d.yt_dlp_path,
            "yt_dlp_version": d.yt_dlp_version,
            "output_dir": d.output_dir,
            "output_dir_exists": d.output_dir_exists,
            "allowed_domains": d.allowed_domains,
            "max_duration_seconds": d.max_duration_seconds,
        }
    else:
        ytdlp_diag = {"error": "approved_url_downloader module not available"}

    return {
        "scanner": {
            "available": _scan_media_folder is not None,
            "supported_extensions": sorted(_SCANNER_EXTENSIONS),
        },
        "yt_dlp": ytdlp_diag,
        "simulation_only": True,
        "outbound_actions_taken": 0,
    }


# ===========================================================================
# Phase 11 — Renderer Validation Runs
# ===========================================================================

class RendererValidationRunRequest(BaseModel):
    workspace_slug: str
    client_id: str = ""
    prompt_generation_id: str
    renderer_type: str = "comfyui_stub"
    provider: str = "official"
    workflow_path: str = ""
    model_name: str = ""
    prompt_summary: str = ""
    negative_prompt_summary: str = ""
    notes: str = ""
    test_mode: bool = True


class RendererValidationReviewRequest(BaseModel):
    decision: str  # approve_as_usable | needs_revision | reject
    quality_score: float = 0.0
    quality_notes: str = ""
    usable_for_final: bool = False
    reviewer_notes: str = ""


VALID_VALIDATION_DECISIONS = {"approve_as_usable", "needs_revision", "reject"}


@app.post("/renderer-validation-runs", status_code=201)
def create_renderer_validation_run(payload: RendererValidationRunRequest) -> dict:
    """
    Create a renderer validation run record.

    This records an intent to validate a renderer backend.
    It does NOT submit any jobs to Comfy Cloud or any external service.
    All records are simulation_only=True, outbound_actions_taken=0.
    """
    now = utc_now()
    client = get_client()
    db = get_database(client)

    # Validate renderer_type
    allowed_renderer_types = {
        "comfyui_stub", "comfyui_real", "comfyui_cloud", "external_manual",
    }
    rt = clean_text(payload.renderer_type)
    if rt not in allowed_renderer_types:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid renderer_type={rt!r}. Must be one of: {sorted(allowed_renderer_types)}",
        )

    # Validate decision options
    run_record: dict[str, Any] = {
        "workspace_slug": clean_text(payload.workspace_slug),
        "client_id": clean_text(payload.client_id),
        "prompt_generation_id": clean_text(payload.prompt_generation_id),
        "renderer_type": rt,
        "provider": clean_text(payload.provider),
        "workflow_path": clean_text(payload.workflow_path),
        "model_name": clean_text(payload.model_name),
        "prompt_summary": clean_text(payload.prompt_summary)[:500],
        "negative_prompt_summary": clean_text(payload.negative_prompt_summary)[:500],
        "notes": clean_text(payload.notes)[:1000],
        "test_mode": bool(payload.test_mode),
        "status": "pending",
        "generated_output_paths": [],
        "quality_score": 0.0,
        "quality_notes": "",
        "usable_for_final": False,
        "failure_reason": "",
        "review_decision": "",
        "reviewer_notes": "",
        "review_events": [],
        "simulation_only": True,
        "outbound_actions_taken": 0,
        "created_at": now,
        "updated_at": now,
        "reviewed_at": None,
    }

    insert_result = db.renderer_validation_runs.insert_one(run_record)
    run_id = str(insert_result.inserted_id)

    # If this is a cloud validation run, include diagnostics (no API key)
    cloud_diag: dict[str, Any] = {}
    if rt == "comfyui_cloud":
        try:
            from comfyui_cloud_client import cloud_diagnostics  # type: ignore
            cloud_diag = cloud_diagnostics()
        except ImportError:
            cloud_diag = {"error": "comfyui_cloud_client not available"}

    # MCP validation plan if applicable
    mcp_plan: dict[str, Any] = {}
    if rt == "comfyui_cloud" and payload.prompt_generation_id:
        try:
            from comfyui_mcp_validation import create_mcp_validation_plan  # type: ignore
            pg_id_clean = clean_text(payload.prompt_generation_id)
            pg = db.prompt_generations.find_one(
                {"_id": ObjectId(pg_id_clean)} if ObjectId.is_valid(pg_id_clean) else {"_id": pg_id_clean}
            )
            if pg:
                pg["_id"] = str(pg["_id"])
                mcp_plan = create_mcp_validation_plan(pg)
        except ImportError:
            mcp_plan = {"error": "comfyui_mcp_validation not available"}

    run_record["_id"] = run_id
    return {
        "status": "created",
        "item": serialize(run_record),
        "cloud_diagnostics": cloud_diag,
        "mcp_validation_plan": mcp_plan,
        "simulation_only": True,
        "outbound_actions_taken": 0,
    }


@app.get("/renderer-validation-runs")
def list_renderer_validation_runs(
    workspace_slug: str = Query(""),
    renderer_type: str = Query(""),
    status: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """
    List renderer validation runs.

    Filters by workspace_slug, renderer_type, and status.
    Results are ordered newest-first.
    """
    client = get_client()
    db = get_database(client)

    query: dict[str, Any] = {}
    if workspace_slug:
        query["workspace_slug"] = clean_text(workspace_slug)
    if renderer_type:
        query["renderer_type"] = clean_text(renderer_type)
    if status:
        query["status"] = clean_text(status)

    runs = list(
        db.renderer_validation_runs.find(query)
        .sort("created_at", -1)
        .limit(limit)
    )
    return {
        "items": [serialize(r) for r in runs],
        "total": len(runs),
        "simulation_only": True,
        "outbound_actions_taken": 0,
    }


@app.post("/renderer-validation-runs/{run_id}/review")
def review_renderer_validation_run(
    run_id: str,
    payload: RendererValidationReviewRequest,
) -> dict:
    """
    Submit a human review decision for a renderer validation run.

    Valid decisions: approve_as_usable | needs_revision | reject

    This does NOT approve any asset for publishing.
    It only records whether the renderer output is usable for final production.
    """
    now = utc_now()
    client = get_client()
    db = get_database(client)

    decision = clean_text(payload.decision)
    if decision not in VALID_VALIDATION_DECISIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid decision={decision!r}. Must be one of: {sorted(VALID_VALIDATION_DECISIONS)}",
        )

    run = db.renderer_validation_runs.find_one(
        {"_id": ObjectId(run_id)} if ObjectId.is_valid(run_id) else {"_id": run_id}
    )
    if not run:
        raise HTTPException(status_code=404, detail="Renderer validation run not found.")

    usable = decision == "approve_as_usable" and bool(payload.usable_for_final)

    review_event = {
        "decision": decision,
        "quality_score": float(payload.quality_score),
        "quality_notes": clean_text(payload.quality_notes)[:1000],
        "usable_for_final": usable,
        "reviewer_notes": clean_text(payload.reviewer_notes)[:1000],
        "reviewed_at": now,
    }

    new_status = {
        "approve_as_usable": "completed",
        "needs_revision": "needs_review",
        "reject": "failed",
    }[decision]

    db.renderer_validation_runs.update_one(
        {"_id": ObjectId(run_id) if ObjectId.is_valid(run_id) else run_id},
        {
            "$set": {
                "status": new_status,
                "review_decision": decision,
                "quality_score": float(payload.quality_score),
                "quality_notes": clean_text(payload.quality_notes)[:1000],
                "usable_for_final": usable,
                "reviewer_notes": clean_text(payload.reviewer_notes)[:1000],
                "reviewed_at": now,
                "updated_at": now,
            },
            "$push": {"review_events": review_event},
        },
    )

    updated = db.renderer_validation_runs.find_one(
        {"_id": ObjectId(run_id)} if ObjectId.is_valid(run_id) else {"_id": run_id}
    )
    return {
        "status": "reviewed",
        "decision": decision,
        "usable_for_final": usable,
        "item": serialize(updated),
        "simulation_only": True,
        "outbound_actions_taken": 0,
    }


@app.get("/renderer-validation/diagnostics")
def renderer_validation_diagnostics() -> dict:
    """
    Return full renderer diagnostics for all renderer backends.

    This endpoint is safe to call at any time.
    API keys are NEVER returned — only configured=True/False.
    """
    # Local ComfyUI diagnostics
    local_diag: dict[str, Any] = {}
    try:
        from comfyui_client import comfyui_diagnostics  # type: ignore
        local_diag = comfyui_diagnostics()
    except Exception as exc:
        local_diag = {"error": str(exc)}

    # Cloud renderer diagnostics (API key never included)
    cloud_diag: dict[str, Any] = {}
    try:
        from comfyui_cloud_client import cloud_diagnostics  # type: ignore
        cloud_diag = cloud_diagnostics()
    except Exception as exc:
        cloud_diag = {"error": str(exc)}

    # MCP diagnostics
    mcp_diag: dict[str, Any] = {}
    try:
        from comfyui_mcp_validation import mcp_diagnostics  # type: ignore
        mcp_diag = mcp_diagnostics()
    except Exception as exc:
        mcp_diag = {"error": str(exc)}

    # MCP connection instructions
    mcp_instructions: dict[str, Any] = {}
    try:
        from comfyui_mcp_validation import build_mcp_connection_instructions  # type: ignore
        mcp_instructions = build_mcp_connection_instructions()
    except Exception as exc:
        mcp_instructions = {"error": str(exc)}

    return {
        "local": local_diag,
        "cloud": cloud_diag,
        "mcp": mcp_diag,
        "mcp_setup_instructions": mcp_instructions,
        "simulation_only": True,
        "outbound_actions_taken": 0,
    }


# ---------------------------------------------------------------------------
# Phase 6A — Client Profiles endpoints
# ---------------------------------------------------------------------------

def _validate_client_profile_refs(db, payload_workspace_slug: str, payload_workflow_def_id: str) -> None:
    """Raise 422 if referenced workspace or workflow_definition does not exist."""
    if payload_workspace_slug:
        ws = db.workspaces.find_one({"slug": payload_workspace_slug})
        if not ws:
            raise HTTPException(status_code=422, detail=f"Workspace '{payload_workspace_slug}' not found.")
    if payload_workflow_def_id:
        wdef = db.workflow_definitions.find_one({"slug": payload_workflow_def_id})
        if not wdef:
            raise HTTPException(status_code=422, detail=f"Workflow definition '{payload_workflow_def_id}' not found.")


@app.post("/admin/client-profiles")
def admin_create_client_profile(payload: AdminClientProfileCreateRequest) -> dict:
    slug = slugify(payload.slug) if payload.slug else ""
    if not slug:
        raise HTTPException(status_code=400, detail="Client profile slug is required.")
    if not payload.display_name.strip():
        raise HTTPException(status_code=400, detail="Client profile display_name is required.")
    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        if db.admin_client_profiles.find_one({"slug": slug}):
            raise HTTPException(status_code=409, detail=f"A client profile with slug '{slug}' already exists.")
        _validate_client_profile_refs(db, payload.workspace_slug, payload.workflow_definition_id)
        doc: dict[str, Any] = {
            "slug": slug,
            "display_name": payload.display_name.strip(),
            "workspace_slug": payload.workspace_slug.strip(),
            "system_profile_id": payload.system_profile_id.strip(),
            "module": payload.module.strip(),
            "industry": payload.industry.strip(),
            "tier": payload.tier.strip(),
            "primary_goal": payload.primary_goal.strip(),
            "target_audience": payload.target_audience.strip(),
            "tone_preference": payload.tone_preference.strip(),
            "content_cadence": payload.content_cadence.strip(),
            "workflow_definition_id": payload.workflow_definition_id.strip(),
            "scoring_rule_set": payload.scoring_rule_set.strip() or "default",
            "notes": payload.notes.strip(),
            "status": payload.status or "active",
            "created_at": now,
            "updated_at": now,
        }
        result = db.admin_client_profiles.insert_one(doc)
        created = db.admin_client_profiles.find_one({"_id": result.inserted_id})
        return {"item": serialize(created), "message": "Client profile created."}
    finally:
        client.close()


@app.get("/admin/client-profiles")
def admin_list_client_profiles(status: str = "") -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        items = list(db.admin_client_profiles.find(query).sort([("created_at", 1)]))
        return {"items": serialize(items)}
    finally:
        client.close()


@app.get("/admin/client-profiles/{slug}")
def admin_get_client_profile(slug: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        profile = db.admin_client_profiles.find_one({"slug": slug})
        if not profile:
            raise HTTPException(status_code=404, detail="Client profile not found.")
        return {"item": serialize(profile)}
    finally:
        client.close()


@app.patch("/admin/client-profiles/{slug}")
def admin_update_client_profile(slug: str, payload: AdminClientProfileUpdateRequest) -> dict:
    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        profile = db.admin_client_profiles.find_one({"slug": slug})
        if not profile:
            raise HTTPException(status_code=404, detail="Client profile not found.")
        updates: dict[str, Any] = {"updated_at": now}
        for field in [
            "display_name", "workspace_slug", "system_profile_id", "module", "industry",
            "tier", "primary_goal", "target_audience", "tone_preference", "content_cadence",
            "workflow_definition_id", "scoring_rule_set", "notes",
        ]:
            value = getattr(payload, field, None)
            if value is not None:
                updates[field] = value.strip() if isinstance(value, str) else value
        ws_slug = updates.get("workspace_slug", "")
        wdef_id = updates.get("workflow_definition_id", "")
        _validate_client_profile_refs(db, ws_slug, wdef_id)
        db.admin_client_profiles.update_one({"slug": slug}, {"$set": updates})
        updated = db.admin_client_profiles.find_one({"slug": slug})
        return {"item": serialize(updated), "message": "Client profile updated."}
    finally:
        client.close()


@app.patch("/admin/client-profiles/{slug}/status")
def admin_update_client_profile_status(slug: str, payload: AdminClientProfileStatusRequest) -> dict:
    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        profile = db.admin_client_profiles.find_one({"slug": slug})
        if not profile:
            raise HTTPException(status_code=404, detail="Client profile not found.")
        db.admin_client_profiles.update_one(
            {"slug": slug},
            {"$set": {"status": payload.status, "updated_at": now}},
        )
        updated = db.admin_client_profiles.find_one({"slug": slug})
        return {"item": serialize(updated), "message": f"Client profile status updated to '{payload.status}'."}
    finally:
        client.close()


@app.get("/admin/client-profiles/{slug}/workflow-definition")
def admin_get_client_profile_workflow_definition(slug: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        profile = db.admin_client_profiles.find_one({"slug": slug})
        if not profile:
            raise HTTPException(status_code=404, detail="Client profile not found.")
        wdef_id = profile.get("workflow_definition_id", "")
        if not wdef_id:
            raise HTTPException(status_code=404, detail="No workflow definition linked to this client profile.")
        wdef = db.workflow_definitions.find_one({"slug": wdef_id})
        if not wdef:
            raise HTTPException(status_code=404, detail="Linked workflow definition not found.")
        return {"item": serialize(wdef)}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Phase 6A — Workflow Definitions endpoints
# ---------------------------------------------------------------------------

_VALID_STAGE_NUMBERS = set(range(1, 8))  # 1–7 inclusive

# Keep legacy alias for any internal references
_validate_stages = None  # replaced by _validate_workflow_definition_stages below


def _validate_workflow_definition_stages(stages: list[WorkflowStageDefinition]) -> None:
    """
    Phase 6G: Enhanced stage validation.
    Rules:
      - stage_number must be 1–7
      - no duplicate stage_numbers
      - at least one required stage
      - labels cannot be blank
      - max chips length = 10
      - no null stage objects
    """
    if not stages:
        return
    seen: set[int] = set()
    has_required = False
    for stage in stages:
        if stage is None:
            raise HTTPException(status_code=422, detail="Stage objects cannot be null.")
        if stage.stage_number not in _VALID_STAGE_NUMBERS:
            raise HTTPException(
                status_code=422,
                detail=f"stage_number {stage.stage_number} is invalid. Must be 1–7.",
            )
        if stage.stage_number in seen:
            raise HTTPException(
                status_code=422,
                detail=f"Duplicate stage_number {stage.stage_number}. Each stage number must appear at most once.",
            )
        seen.add(stage.stage_number)
        if not stage.label or not stage.label.strip():
            raise HTTPException(
                status_code=422,
                detail=f"Stage {stage.stage_number} has a blank label. All stages must have a non-empty label.",
            )
        if len(stage.chips) > 10:
            raise HTTPException(
                status_code=422,
                detail=f"Stage {stage.stage_number} has {len(stage.chips)} chips. Maximum is 10.",
            )
        if stage.required:
            has_required = True
    if stages and not has_required:
        raise HTTPException(
            status_code=422,
            detail="At least one stage must be marked as required.",
        )


@app.post("/admin/workflow-definitions")
def admin_create_workflow_definition(payload: AdminWorkflowDefinitionCreateRequest) -> dict:
    slug = slugify(payload.slug) if payload.slug else ""
    if not slug:
        raise HTTPException(status_code=400, detail="Workflow definition slug is required.")
    if not payload.display_name.strip():
        raise HTTPException(status_code=400, detail="Workflow definition display_name is required.")
    _validate_workflow_definition_stages(payload.stages)
    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        if db.workflow_definitions.find_one({"slug": slug}):
            raise HTTPException(status_code=409, detail=f"A workflow definition with slug '{slug}' already exists.")
        doc: dict[str, Any] = {
            "slug": slug,
            "display_name": payload.display_name.strip(),
            "system_profile_id": payload.system_profile_id.strip(),
            "module": payload.module.strip(),
            "stages": [s.model_dump() for s in payload.stages],
            "notes": payload.notes.strip(),
            "status": payload.status or "active",
            "created_at": now,
            "updated_at": now,
        }
        result = db.workflow_definitions.insert_one(doc)
        created = db.workflow_definitions.find_one({"_id": result.inserted_id})
        return {"item": serialize(created), "message": "Workflow definition created."}
    finally:
        client.close()


@app.get("/admin/workflow-definitions")
def admin_list_workflow_definitions(status: str = "") -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        items = list(db.workflow_definitions.find(query).sort([("created_at", 1)]))
        return {"items": serialize(items)}
    finally:
        client.close()


@app.get("/admin/workflow-definitions/{slug}")
def admin_get_workflow_definition(slug: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        wdef = db.workflow_definitions.find_one({"slug": slug})
        if not wdef:
            raise HTTPException(status_code=404, detail="Workflow definition not found.")
        return {"item": serialize(wdef)}
    finally:
        client.close()


@app.patch("/admin/workflow-definitions/{slug}")
def admin_update_workflow_definition(slug: str, payload: AdminWorkflowDefinitionUpdateRequest) -> dict:
    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        wdef = db.workflow_definitions.find_one({"slug": slug})
        if not wdef:
            raise HTTPException(status_code=404, detail="Workflow definition not found.")
        updates: dict[str, Any] = {"updated_at": now}
        for field in ["display_name", "system_profile_id", "module", "notes", "status"]:
            value = getattr(payload, field, None)
            if value is not None:
                updates[field] = value.strip() if isinstance(value, str) else value
        if payload.stages is not None:
            _validate_workflow_definition_stages(payload.stages)
            updates["stages"] = [s.model_dump() for s in payload.stages]
        db.workflow_definitions.update_one({"slug": slug}, {"$set": updates})
        updated = db.workflow_definitions.find_one({"slug": slug})
        return {"item": serialize(updated), "message": "Workflow definition updated."}
    finally:
        client.close()


# ══════════════════════════════════════════════════════════════════════════════
# Phase 6C — Discovery Intelligence
# ══════════════════════════════════════════════════════════════════════════════

class DiscoveryEvidence(BaseModel):
    platform: str | None = None
    signal_type: str | None = None
    metric: str | None = None
    value: float | None = None
    keyword: str | None = None
    growth_pct: float | None = None
    source_url: str | None = None
    notes: str | None = None


class DiscoveryRecommendation(BaseModel):
    recommended_asset_types: list[str] = []
    recommended_platforms: list[str] = []
    recommended_next_stage: str | None = None
    rationale: str | None = None


class DiscoveryInsightCreateRequest(BaseModel):
    workspace_slug: str
    client_profile_slug: str | None = None
    insight_type: str
    title: str
    summary: str
    confidence_score: float = 0.5
    evidence: list[DiscoveryEvidence] = []
    recommendation: DiscoveryRecommendation | None = None
    source_agent: str | None = None
    source_run_id: str | None = None
    linked_workflow_asset_ids: list[str] = []
    status: str = "pending_review"


class DiscoveryInsightUpdateRequest(BaseModel):
    insight_type: str | None = None
    title: str | None = None
    summary: str | None = None
    confidence_score: float | None = None
    evidence: list[DiscoveryEvidence] | None = None
    recommendation: DiscoveryRecommendation | None = None
    source_agent: str | None = None
    source_run_id: str | None = None
    linked_workflow_asset_ids: list[str] | None = None
    status: str | None = None
    approved_by: str | None = None


class DiscoveryInsightStatusRequest(BaseModel):
    status: Literal["pending_review", "approved", "deferred", "archived"]


# ── Discovery Insights: helper ─────────────────────────────────────────────

def _get_discovery_insight_or_404(db: Any, insight_id: str) -> dict:
    """Fetch a discovery_insights document by ID or raise 404."""
    try:
        oid = ObjectId(insight_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid insight id format.")
    doc = db.discovery_insights.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Discovery insight not found.")
    return doc


# ── Discovery Insights: endpoints ─────────────────────────────────────────

@app.post("/discovery-insights")
def create_discovery_insight(payload: DiscoveryInsightCreateRequest) -> dict:
    if not payload.workspace_slug.strip():
        raise HTTPException(status_code=400, detail="workspace_slug is required.")
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="title is required.")
    if not payload.summary.strip():
        raise HTTPException(status_code=400, detail="summary is required.")
    if not payload.insight_type.strip():
        raise HTTPException(status_code=400, detail="insight_type is required.")
    valid_statuses = {"pending_review", "approved", "deferred", "archived"}
    if payload.status not in valid_statuses:
        raise HTTPException(status_code=422, detail=f"status must be one of: {sorted(valid_statuses)}")
    if not (0.0 <= payload.confidence_score <= 1.0):
        raise HTTPException(status_code=422, detail="confidence_score must be between 0.0 and 1.0.")

    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        doc: dict[str, Any] = {
            "workspace_slug": payload.workspace_slug.strip(),
            "client_profile_slug": (payload.client_profile_slug or "").strip() or None,
            "insight_type": payload.insight_type.strip(),
            "title": payload.title.strip(),
            "summary": payload.summary.strip(),
            "confidence_score": payload.confidence_score,
            "evidence": [e.model_dump() for e in payload.evidence],
            "recommendation": payload.recommendation.model_dump() if payload.recommendation else None,
            "source_agent": (payload.source_agent or "").strip() or None,
            "source_run_id": (payload.source_run_id or "").strip() or None,
            "linked_workflow_asset_ids": list(payload.linked_workflow_asset_ids),
            "status": payload.status,
            "approved_by": None,
            "approved_at": None,
            "created_at": now,
            "updated_at": now,
        }
        result = db.discovery_insights.insert_one(doc)
        created = db.discovery_insights.find_one({"_id": result.inserted_id})
        return {"item": serialize(created), "message": "Discovery insight created."}
    finally:
        client.close()


@app.get("/discovery-insights")
def list_discovery_insights(
    workspace_slug: str = Query(""),
    status: str = Query(""),
    source_run_id: str = Query(""),
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
        if source_run_id:
            query["source_run_id"] = source_run_id
        items = list(
            db.discovery_insights.find(query).sort([("created_at", -1)]).limit(limit)
        )
        return {"items": serialize(items), "count": len(items)}
    finally:
        client.close()


@app.get("/discovery-insights/{insight_id}")
def get_discovery_insight(insight_id: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        doc = _get_discovery_insight_or_404(db, insight_id)
        return {"item": serialize(doc)}
    finally:
        client.close()


@app.patch("/discovery-insights/{insight_id}")
def update_discovery_insight(insight_id: str, payload: DiscoveryInsightUpdateRequest) -> dict:
    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        doc = _get_discovery_insight_or_404(db, insight_id)
        updates: dict[str, Any] = {"updated_at": now}
        for field in ["insight_type", "title", "summary", "source_agent", "source_run_id", "status", "approved_by"]:
            val = getattr(payload, field, None)
            if val is not None:
                updates[field] = val.strip() if isinstance(val, str) else val
        if payload.confidence_score is not None:
            if not (0.0 <= payload.confidence_score <= 1.0):
                raise HTTPException(status_code=422, detail="confidence_score must be between 0.0 and 1.0.")
            updates["confidence_score"] = payload.confidence_score
        if payload.evidence is not None:
            updates["evidence"] = [e.model_dump() for e in payload.evidence]
        if payload.recommendation is not None:
            updates["recommendation"] = payload.recommendation.model_dump()
        if payload.linked_workflow_asset_ids is not None:
            updates["linked_workflow_asset_ids"] = list(payload.linked_workflow_asset_ids)
        if payload.status == "approved" and not doc.get("approved_at"):
            updates["approved_at"] = now
        db.discovery_insights.update_one({"_id": doc["_id"]}, {"$set": updates})
        updated = db.discovery_insights.find_one({"_id": doc["_id"]})
        return {"item": serialize(updated), "message": "Discovery insight updated."}
    finally:
        client.close()


@app.patch("/discovery-insights/{insight_id}/status")
def update_discovery_insight_status(insight_id: str, payload: DiscoveryInsightStatusRequest) -> dict:
    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        doc = _get_discovery_insight_or_404(db, insight_id)
        updates: dict[str, Any] = {"status": payload.status, "updated_at": now}
        if payload.status == "approved" and not doc.get("approved_at"):
            updates["approved_at"] = now
        db.discovery_insights.update_one({"_id": doc["_id"]}, {"$set": updates})
        updated = db.discovery_insights.find_one({"_id": doc["_id"]})
        return {"item": serialize(updated), "message": f"Insight status updated to '{payload.status}'."}
    finally:
        client.close()


# ── Workflow Asset Lineage: link endpoint ──────────────────────────────────

@app.patch("/workflow-assets/{asset_id}/link-insight")
def link_workflow_asset_to_insight(asset_id: str, payload: dict) -> dict:
    """Set source_discovery_insight_id on a workflow asset (lineage-only, additive)."""
    insight_id = (payload.get("source_discovery_insight_id") or "").strip()
    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        try:
            oid = ObjectId(asset_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid asset_id format.")
        asset = db.workflow_assets.find_one({"_id": oid})
        if not asset:
            raise HTTPException(status_code=404, detail="Workflow asset not found.")
        db.workflow_assets.update_one(
            {"_id": oid},
            {"$set": {"source_discovery_insight_id": insight_id or None, "updated_at": now}},
        )
        updated = db.workflow_assets.find_one({"_id": oid})
        return {"item": serialize([normalize_workflow_asset(updated)])[0], "message": "Asset lineage updated."}
    finally:
        client.close()


# ── Phase 6D: Discovery Engine Endpoints ──────────────────────────────────────

class DiscoveryGenerateRequest(BaseModel):
    workspace_slug: str
    module: str
    client_profile_slug: str | None = None
    source_run_id: str | None = None
    max_insights: int = 4


@app.post("/discovery-insights/generate")
def trigger_discovery_insight_generation(payload: DiscoveryGenerateRequest) -> dict:
    """Manually trigger discovery insight generation for a workspace/module.

    Internally calls the discovery_engine pipeline and persists results.
    Also creates a discovery_run_summary record capturing the operational result.
    Returns the batch of created insights.
    """
    ws = clean_text(payload.workspace_slug)
    if not ws:
        raise HTTPException(status_code=400, detail="workspace_slug is required.")
    module = clean_text(payload.module)
    if not module:
        raise HTTPException(status_code=400, detail="module is required.")

    from discovery_engine import generate_discovery_insights as _gen_insights, get_configured_sources as _get_sources

    client = get_client()
    started = utc_now()
    try:
        db = get_database(client)
        completion_state = "completed"
        created: list[dict] = []
        try:
            created = _gen_insights(
                db=db,
                workspace_slug=ws,
                client_profile_slug=payload.client_profile_slug,
                module=module,
                source_run_id=payload.source_run_id,
                max_insights=max(1, min(int(payload.max_insights), 10)),
            )
        except Exception:
            completion_state = "failed"

        if completion_state == "completed" and not created:
            completion_state = "partial"

        completed = utc_now()
        run_id = payload.source_run_id or slugify(f"{ws}-{module}-{int(completed.timestamp())}")

        # Gather source / platform metadata for summary
        configured_sources: list[dict] = []
        try:
            configured_sources = _get_sources(ws, payload.client_profile_slug, db)
        except Exception:
            pass
        source_labels = [s.get("label", "") for s in configured_sources if s.get("status") == "active"]
        platforms_from_insights: list[str] = []
        for ins in created:
            for ev in ins.get("evidence", []):
                p = ev.get("platform", "")
                if p and p not in platforms_from_insights:
                    platforms_from_insights.append(p)

        high_conf = sum(1 for i in created if (i.get("confidence_score") or 0) >= 0.8)

        # Build human-readable summary
        if completion_state == "completed" and created:
            src_count = len(configured_sources)
            plat_str = ", ".join(platforms_from_insights[:3]) if platforms_from_insights else "configured sources"
            summary_text = (
                f"Checked {src_count} configured source{'s' if src_count != 1 else ''} across {plat_str}. "
                f"Generated {len(created)} discovery insight{'s' if len(created) != 1 else ''} "
                f"with {high_conf} high-confidence signal{'s' if high_conf != 1 else ''}."
            )
            next_action = "Review discovery insights and approve content directions."
        elif completion_state == "partial":
            summary_text = "Discovery ran but no insights were generated for this workspace and module."
            next_action = "Add more client sources or rerun discovery later."
        else:
            summary_text = "Discovery run encountered an error."
            next_action = "Check system logs and retry."

        # Persist run summary (non-fatal)
        try:
            existing = db.discovery_run_summaries.find_one({"run_id": run_id})
            summary_doc: dict[str, Any] = {
                "workspace_slug": ws,
                "run_id": run_id,
                "agent_name": "content_discovery",
                "started_at": started,
                "completed_at": completed,
                "sources_checked": len(configured_sources),
                "insights_generated": len(created),
                "high_confidence_insights": high_conf,
                "configured_sources_used": source_labels,
                "platforms_checked": platforms_from_insights,
                "completion_state": completion_state,
                "summary": summary_text,
                "next_recommended_action": next_action,
                "metadata": {"module": module},
                "updated_at": completed,
            }
            if existing:
                db.discovery_run_summaries.update_one({"run_id": run_id}, {"$set": summary_doc})
            else:
                summary_doc["created_at"] = completed
                db.discovery_run_summaries.insert_one(summary_doc)
        except Exception:
            pass  # Non-fatal: never block insight delivery

        return {
            "items": serialize(created),
            "count": len(created),
            "message": f"{len(created)} discovery insight(s) generated.",
            "run_summary": {"run_id": run_id, "completion_state": completion_state, "summary": summary_text},
        }
    finally:
        client.close()


@app.post("/discovery-insights/{insight_id}/generate-assets")
def generate_assets_from_insight(insight_id: str) -> dict:
    """Create placeholder workflow_assets linked to a discovery insight.

    Reads the insight's recommendation to determine asset types (up to 3),
    creates one workflow_asset per type with approval_state='needs_review',
    and links each asset back to the insight via source_discovery_insight_id.
    No content is published — all assets require human review.
    """
    from discovery_engine import asset_docs_from_insight as _asset_docs

    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        insight = _get_discovery_insight_or_404(db, insight_id)
        docs = _asset_docs(insight, now=now)
        created_assets: list[dict] = []
        for doc in docs:
            result = db.workflow_assets.insert_one(doc)
            inserted = db.workflow_assets.find_one({"_id": result.inserted_id})
            if inserted:
                created_assets.append(normalize_workflow_asset(inserted))
        # Link created asset IDs back onto the insight
        asset_ids = [str(a["_id"]) for a in created_assets]
        if asset_ids:
            db.discovery_insights.update_one(
                {"_id": insight["_id"]},
                {"$addToSet": {"linked_workflow_asset_ids": {"$each": asset_ids}}, "$set": {"updated_at": now}},
            )
        return {
            "items": serialize(created_assets),
            "count": len(created_assets),
            "insight_id": insight_id,
            "message": f"{len(created_assets)} workflow asset(s) created from insight.",
        }
    finally:
        client.close()


# ===========================================================================
# Phase 6E — Client Source Registry
# ===========================================================================

VALID_SOURCE_TYPES: list[str] = [
    "website",
    "linkedin",
    "instagram",
    "youtube",
    "tiktok",
    "x",
    "facebook",
    "google_drive",
    "dropbox",
    "rss_feed",
    "podcast",
    "media_library",
]


class ClientSourceCreateRequest(BaseModel):
    workspace_slug: str
    client_profile_slug: str
    source_type: str
    label: str
    uri: str
    platform: str | None = None
    status: str = "active"
    notes: str | None = None


class ClientSourceUpdateRequest(BaseModel):
    label: str | None = None
    uri: str | None = None
    platform: str | None = None
    status: str | None = None
    notes: str | None = None


def normalize_source_uri(uri: str) -> str:
    """Normalize a source URI.

    * Strips leading/trailing whitespace.
    * Adds ``https://`` scheme to bare domain-like strings.
    * Does NOT validate connectivity.
    """
    uri = uri.strip()
    if not uri:
        return uri
    # If it already has a recognised scheme, leave it.
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+\-.]*://", uri):
        return uri
    # Looks like a bare domain / path — prepend https://
    if re.match(r"^[a-zA-Z0-9]", uri):
        return "https://" + uri
    return uri


def _compute_source_health(uri: str, status: str) -> str:
    if status == "inactive":
        return "inactive"
    if not uri:
        return "invalid"
    try:
        from urllib.parse import urlparse
        parsed = urlparse(uri)
        if parsed.scheme in ("http", "https", "ftp", "ftps") and parsed.netloc:
            return "ready"
        return "invalid"
    except Exception:
        return "invalid"


def _get_client_source_or_404(db, source_id: str) -> dict:
    try:
        oid = ObjectId(source_id)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid source id format.")
    doc = db.client_sources.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Client source not found.")
    return doc


def _serialize_source(doc: dict) -> dict:
    out = serialize(doc)
    out["health_status"] = _compute_source_health(
        str(doc.get("uri", "") or ""),
        str(doc.get("status", "active") or "active"),
    )
    return out


@app.post("/admin/client-sources")
def admin_create_client_source(payload: ClientSourceCreateRequest) -> dict:
    workspace_slug = clean_text(payload.workspace_slug)
    client_profile_slug = clean_text(payload.client_profile_slug)
    source_type = clean_text(payload.source_type)
    label = clean_text(payload.label)
    uri = normalize_source_uri(clean_text(payload.uri))

    if not workspace_slug:
        raise HTTPException(status_code=400, detail="workspace_slug is required.")
    if not client_profile_slug:
        raise HTTPException(status_code=400, detail="client_profile_slug is required.")
    if source_type not in VALID_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail=f"source_type must be one of: {', '.join(VALID_SOURCE_TYPES)}")
    if not label:
        raise HTTPException(status_code=400, detail="label is required.")
    if not uri:
        raise HTTPException(status_code=400, detail="uri is required.")

    now = utc_now()
    client = get_client()
    try:
        db = get_database(client)
        doc: dict[str, Any] = {
            "workspace_slug": workspace_slug,
            "client_profile_slug": client_profile_slug,
            "source_type": source_type,
            "label": label,
            "uri": uri,
            "platform": clean_text(payload.platform) or None,
            "status": clean_text(payload.status) or "active",
            "notes": clean_text(payload.notes) or None,
            "created_at": now,
            "updated_at": now,
        }
        result = db.client_sources.insert_one(doc)
        inserted = db.client_sources.find_one({"_id": result.inserted_id})
        return {"item": _serialize_source(inserted)}
    finally:
        client.close()


@app.get("/admin/client-sources")
def admin_list_client_sources(
    workspace_slug: str = Query(""),
    client_profile_slug: str = Query(""),
    source_type: str = Query(""),
    status: str = Query(""),
    limit: int = Query(100),
) -> dict:
    query: dict[str, Any] = {}
    if workspace_slug:
        query["workspace_slug"] = workspace_slug
    if client_profile_slug:
        query["client_profile_slug"] = client_profile_slug
    if source_type:
        query["source_type"] = source_type
    if status:
        query["status"] = status
    client = get_client()
    try:
        db = get_database(client)
        docs = list(db.client_sources.find(query).sort("created_at", -1).limit(max(1, min(limit, 500))))
        return {"items": [_serialize_source(d) for d in docs], "count": len(docs)}
    finally:
        client.close()


@app.get("/admin/client-sources/{source_id}")
def admin_get_client_source(source_id: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        doc = _get_client_source_or_404(db, source_id)
        return {"item": _serialize_source(doc)}
    finally:
        client.close()


@app.patch("/admin/client-sources/{source_id}")
def admin_update_client_source(source_id: str, payload: ClientSourceUpdateRequest) -> dict:
    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        doc = _get_client_source_or_404(db, source_id)
        updates: dict[str, Any] = {"updated_at": now}
        if payload.label is not None:
            val = clean_text(payload.label)
            if not val:
                raise HTTPException(status_code=400, detail="label cannot be empty.")
            updates["label"] = val
        if payload.uri is not None:
            val = normalize_source_uri(clean_text(payload.uri))
            if not val:
                raise HTTPException(status_code=400, detail="uri cannot be empty.")
            updates["uri"] = val
        if payload.platform is not None:
            updates["platform"] = clean_text(payload.platform) or None
        if payload.status is not None:
            updates["status"] = clean_text(payload.status) or "active"
        if payload.notes is not None:
            updates["notes"] = clean_text(payload.notes) or None
        db.client_sources.update_one({"_id": doc["_id"]}, {"$set": updates})
        updated = db.client_sources.find_one({"_id": doc["_id"]})
        return {"item": _serialize_source(updated)}
    finally:
        client.close()


@app.delete("/admin/client-sources/{source_id}")
def admin_delete_client_source(source_id: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        doc = _get_client_source_or_404(db, source_id)
        db.client_sources.delete_one({"_id": doc["_id"]})
        return {"deleted": True, "id": source_id}
    finally:
        client.close()


# ── Phase 6F: Discovery Run Summaries ────────────────────────────────────────

class DiscoveryRunSummaryCreateRequest(BaseModel):
    workspace_slug: str
    run_id: str
    agent_name: str = "content_discovery"
    started_at: datetime
    completed_at: datetime | None = None
    sources_checked: int = 0
    insights_generated: int = 0
    high_confidence_insights: int = 0
    configured_sources_used: list[str] = Field(default_factory=list)
    platforms_checked: list[str] = Field(default_factory=list)
    completion_state: str = "running"
    summary: str | None = None
    next_recommended_action: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiscoveryRunSummaryUpdateRequest(BaseModel):
    completed_at: datetime | None = None
    sources_checked: int | None = None
    insights_generated: int | None = None
    high_confidence_insights: int | None = None
    configured_sources_used: list[str] | None = None
    platforms_checked: list[str] | None = None
    completion_state: str | None = None
    summary: str | None = None
    next_recommended_action: str | None = None
    metadata: dict[str, Any] | None = None


def _serialize_run_summary(doc: dict) -> dict:
    return serialize(doc)


@app.post("/discovery-run-summaries")
def create_discovery_run_summary(payload: DiscoveryRunSummaryCreateRequest) -> dict:
    ws = clean_text(payload.workspace_slug)
    if not ws:
        raise HTTPException(status_code=400, detail="workspace_slug is required.")
    run_id = clean_text(payload.run_id)
    if not run_id:
        raise HTTPException(status_code=400, detail="run_id is required.")
    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        if db.discovery_run_summaries.find_one({"run_id": run_id}):
            raise HTTPException(status_code=409, detail=f"Discovery run summary for run_id '{run_id}' already exists.")
        doc: dict[str, Any] = {
            "workspace_slug": ws,
            "run_id": run_id,
            "agent_name": clean_text(payload.agent_name) or "content_discovery",
            "started_at": payload.started_at,
            "completed_at": payload.completed_at,
            "sources_checked": max(0, payload.sources_checked),
            "insights_generated": max(0, payload.insights_generated),
            "high_confidence_insights": max(0, payload.high_confidence_insights),
            "configured_sources_used": list(payload.configured_sources_used),
            "platforms_checked": list(payload.platforms_checked),
            "completion_state": clean_text(payload.completion_state) or "running",
            "summary": clean_text(payload.summary) if payload.summary else None,
            "next_recommended_action": clean_text(payload.next_recommended_action) if payload.next_recommended_action else None,
            "metadata": payload.metadata or {},
            "created_at": now,
            "updated_at": now,
        }
        result = db.discovery_run_summaries.insert_one(doc)
        doc["_id"] = result.inserted_id
        return {"item": _serialize_run_summary(doc)}
    finally:
        client.close()


@app.get("/discovery-run-summaries")
def list_discovery_run_summaries(
    workspace_slug: str = Query(""),
    run_id: str = Query(""),
    completion_state: str = Query(""),
    limit: int = Query(50),
) -> dict:
    query: dict[str, Any] = {}
    if workspace_slug:
        query["workspace_slug"] = workspace_slug
    if run_id:
        query["run_id"] = run_id
    if completion_state:
        query["completion_state"] = completion_state
    client = get_client()
    try:
        db = get_database(client)
        docs = list(
            db.discovery_run_summaries.find(query)
            .sort("completed_at", -1)
            .limit(max(1, min(limit, 500)))
        )
        return {"items": [_serialize_run_summary(d) for d in docs], "count": len(docs)}
    finally:
        client.close()


@app.get("/discovery-run-summaries/{run_id}")
def get_discovery_run_summary(run_id: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        doc = db.discovery_run_summaries.find_one({"run_id": run_id})
        if not doc:
            raise HTTPException(status_code=404, detail=f"Discovery run summary '{run_id}' not found.")
        return {"item": _serialize_run_summary(doc)}
    finally:
        client.close()


@app.patch("/discovery-run-summaries/{run_id}")
def update_discovery_run_summary(run_id: str, payload: DiscoveryRunSummaryUpdateRequest) -> dict:
    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        doc = db.discovery_run_summaries.find_one({"run_id": run_id})
        if not doc:
            raise HTTPException(status_code=404, detail=f"Discovery run summary '{run_id}' not found.")
        updates: dict[str, Any] = {"updated_at": now}
        if payload.completed_at is not None:
            updates["completed_at"] = payload.completed_at
        if payload.sources_checked is not None:
            updates["sources_checked"] = max(0, payload.sources_checked)
        if payload.insights_generated is not None:
            updates["insights_generated"] = max(0, payload.insights_generated)
        if payload.high_confidence_insights is not None:
            updates["high_confidence_insights"] = max(0, payload.high_confidence_insights)
        if payload.configured_sources_used is not None:
            updates["configured_sources_used"] = list(payload.configured_sources_used)
        if payload.platforms_checked is not None:
            updates["platforms_checked"] = list(payload.platforms_checked)
        if payload.completion_state is not None:
            updates["completion_state"] = clean_text(payload.completion_state) or doc.get("completion_state", "running")
        if payload.summary is not None:
            updates["summary"] = clean_text(payload.summary) or None
        if payload.next_recommended_action is not None:
            updates["next_recommended_action"] = clean_text(payload.next_recommended_action) or None
        if payload.metadata is not None:
            updates["metadata"] = payload.metadata
        db.discovery_run_summaries.update_one({"run_id": run_id}, {"$set": updates})
        updated = db.discovery_run_summaries.find_one({"run_id": run_id})
        return {"item": _serialize_run_summary(updated)}
    finally:
        client.close()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 6H — workflow_runs: structured execution layer
# ─────────────────────────────────────────────────────────────────────────────

WORKFLOW_RUN_TYPES = {"discovery", "content_build", "media_prep", "engagement", "distribution", "crm"}
WORKFLOW_RUN_STATUSES = {"queued", "running", "completed", "failed", "needs_review"}


class WorkflowRunCreateRequest(BaseModel):
    workspace_slug: str
    client_profile_id: Optional[str] = None
    workflow_stage: int = Field(ge=1, le=7)
    run_type: Literal["discovery", "content_build", "media_prep", "engagement", "distribution", "crm"]
    status: Literal["queued", "running", "completed", "failed", "needs_review"] = "queued"
    title: str = ""
    summary: Optional[str] = None
    source_task_id: Optional[str] = None
    source_agent_run_id: Optional[str] = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    # Phase 6N: memory traceability
    client_memory_id: str = ""
    client_memory_version: int = 0
    memory_context_hash: str = ""


class WorkflowRunPatchRequest(BaseModel):
    status: Optional[Literal["queued", "running", "completed", "failed", "needs_review"]] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    outputs: Optional[dict[str, Any]] = None
    completed_at: Optional[datetime] = None


def _serialize_workflow_run(doc: dict) -> dict:
    return serialize(dict(doc))


@app.post("/workflow-runs")
def create_workflow_run(payload: WorkflowRunCreateRequest) -> dict:
    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        doc: dict[str, Any] = {
            "workspace_slug": clean_text(payload.workspace_slug),
            "client_profile_id": clean_text(payload.client_profile_id or ""),
            "workflow_stage": payload.workflow_stage,
            "run_type": payload.run_type,
            "status": payload.status,
            "title": clean_text(payload.title) or f"{payload.run_type.replace('_', ' ').title()} Run",
            "summary": clean_text(payload.summary or "") or None,
            "source_task_id": clean_text(payload.source_task_id or "") or None,
            "source_agent_run_id": clean_text(payload.source_agent_run_id or "") or None,
            "inputs": payload.inputs,
            "outputs": payload.outputs,
            "started_at": payload.started_at or now,
            "completed_at": payload.completed_at,
            "created_at": now,
            "updated_at": now,
        }
        result = db.workflow_runs.insert_one(doc)
        created = db.workflow_runs.find_one({"_id": result.inserted_id})
        return {"item": _serialize_workflow_run(created)}
    finally:
        client.close()


@app.get("/workflow-runs")
def list_workflow_runs(
    workspace_slug: str = Query(""),
    workflow_stage: int = Query(0, ge=0, le=7),
    run_type: str = Query(""),
    status: str = Query(""),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if workflow_stage:
            query["workflow_stage"] = workflow_stage
        if run_type and run_type in WORKFLOW_RUN_TYPES:
            query["run_type"] = run_type
        if status and status in WORKFLOW_RUN_STATUSES:
            query["status"] = status
        items = list(db.workflow_runs.find(query).sort([("created_at", -1)]).limit(limit))
        return {"items": serialize(items), "count": len(items)}
    finally:
        client.close()


@app.get("/workflow-runs/{run_id}")
def get_workflow_run(run_id: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        if is_object_id(run_id):
            doc = db.workflow_runs.find_one({"_id": ObjectId(run_id)})
        else:
            doc = db.workflow_runs.find_one({"source_task_id": run_id})
        if not doc:
            raise HTTPException(status_code=404, detail=f"Workflow run '{run_id}' not found.")
        return {"item": _serialize_workflow_run(doc)}
    finally:
        client.close()


@app.patch("/workflow-runs/{run_id}")
def patch_workflow_run(run_id: str, payload: WorkflowRunPatchRequest) -> dict:
    client = get_client()
    now = utc_now()
    try:
        db = get_database(client)
        if is_object_id(run_id):
            doc = db.workflow_runs.find_one({"_id": ObjectId(run_id)})
        else:
            doc = db.workflow_runs.find_one({"source_task_id": run_id})
        if not doc:
            raise HTTPException(status_code=404, detail=f"Workflow run '{run_id}' not found.")
        updates: dict[str, Any] = {"updated_at": now}
        if payload.status is not None:
            updates["status"] = payload.status
        if payload.title is not None:
            updates["title"] = clean_text(payload.title)
        if payload.summary is not None:
            updates["summary"] = clean_text(payload.summary) or None
        if payload.outputs is not None:
            updates["outputs"] = payload.outputs
        if payload.completed_at is not None:
            updates["completed_at"] = payload.completed_at
        elif payload.status in {"completed", "failed"} and not doc.get("completed_at"):
            updates["completed_at"] = now
        db.workflow_runs.update_one({"_id": doc["_id"]}, {"$set": updates})
        updated = db.workflow_runs.find_one({"_id": doc["_id"]})
        return {"item": _serialize_workflow_run(updated)}
    finally:
        client.close()


@app.get("/workflow-runs/{run_id}/memory-context")
def get_workflow_run_memory_context(run_id: str) -> dict:
    """Phase 6N: Return the memory snapshot frozen at the time of a workflow run."""
    client = get_client()
    try:
        db = get_database(client)
        if is_object_id(run_id):
            run = db.workflow_runs.find_one({"_id": ObjectId(run_id)})
        else:
            run = db.workflow_runs.find_one({"source_task_id": run_id})
        if not run:
            raise HTTPException(status_code=404, detail=f"Workflow run '{run_id}' not found.")
        return {
            "run_id": run_id,
            "run_type": run.get("run_type", ""),
            "has_memory": bool(run.get("client_memory_id")),
            "client_memory_id": run.get("client_memory_id", ""),
            "client_memory_version": run.get("client_memory_version", 0),
            "memory_context_hash": run.get("memory_context_hash", ""),
            "memory_snapshot": run.get("memory_snapshot") or {},
        }
    finally:
        client.close()


# ===========================================================================
# Phase 6M — Adaptive Client Operating Memory & Template Recommendation
# ===========================================================================

# ---------------------------------------------------------------------------
# Foundation Templates — static catalog (8 templates)
# ---------------------------------------------------------------------------

FOUNDATION_TEMPLATES: dict[str, dict] = {
    "media_growth": {
        "slug": "media_growth",
        "name": "Media Growth",
        "description": (
            "For media operators, podcasters, YouTube creators, and content publishers "
            "seeking sponsors, partners, and audience growth opportunities."
        ),
        "category": "content_media",
        "target_client_types": ["podcaster", "youtube_creator", "media_operator", "content_publisher", "blogger", "newsletter_author"],
        "keywords": ["podcast", "media", "content", "youtube", "creator", "audience", "show", "newsletter", "publisher", "streaming", "broadcast"],
        "default_workflow": {
            "discovery_sources": ["podcast_directories", "youtube", "linkedin", "twitter"],
            "content_types": ["social_post", "email", "sponsorship_pitch"],
            "platforms": ["LinkedIn", "YouTube", "Instagram", "TikTok"],
            "approval_required": True,
            "manual_distribution": True,
        },
        "memory_defaults": {
            "voice_tone": {"tone": "engaging", "style": "authentic", "examples": [], "forbidden_phrases": []},
            "workflow_preferences": {"max_assets_per_run": 5, "review_all_assets": True},
            "distribution_preferences": {"channels": ["LinkedIn", "Instagram"], "manual_only": True},
        },
    },
    "artist_growth": {
        "slug": "artist_growth",
        "name": "Artist Growth",
        "description": (
            "For independent artists, musicians, and creatives seeking booking opportunities, "
            "fan engagement, and collaborative partnerships."
        ),
        "category": "content_media",
        "target_client_types": ["musician", "artist", "performer", "band", "dj", "photographer", "visual_artist"],
        "keywords": ["artist", "musician", "music", "band", "tour", "booking", "fan", "creative", "performer", "album", "gig"],
        "default_workflow": {
            "discovery_sources": ["spotify", "instagram", "tiktok", "eventbrite"],
            "content_types": ["social_post", "fan_email", "booking_inquiry"],
            "platforms": ["Instagram", "TikTok", "Facebook", "Spotify"],
            "approval_required": True,
            "manual_distribution": True,
        },
        "memory_defaults": {
            "voice_tone": {"tone": "expressive", "style": "personal", "examples": [], "forbidden_phrases": []},
            "workflow_preferences": {"max_assets_per_run": 3, "review_all_assets": True},
            "distribution_preferences": {"channels": ["Instagram", "TikTok"], "manual_only": True},
        },
    },
    "insurance_growth": {
        "slug": "insurance_growth",
        "name": "Insurance Growth",
        "description": (
            "For independent insurance agents and brokers building referral networks, "
            "generating local leads, and nurturing prospect relationships."
        ),
        "category": "professional_services",
        "target_client_types": ["insurance_agent", "insurance_broker", "financial_advisor", "risk_consultant"],
        "keywords": ["insurance", "broker", "agent", "policy", "coverage", "premium", "referral", "risk", "claims", "underwriting"],
        "default_workflow": {
            "discovery_sources": ["linkedin", "local_directories", "chamber_of_commerce"],
            "content_types": ["social_post", "email", "referral_request"],
            "platforms": ["LinkedIn", "Facebook", "Email"],
            "approval_required": True,
            "manual_distribution": True,
        },
        "memory_defaults": {
            "voice_tone": {"tone": "trustworthy", "style": "consultative", "examples": [], "forbidden_phrases": []},
            "workflow_preferences": {"max_assets_per_run": 5, "review_all_assets": True},
            "distribution_preferences": {"channels": ["LinkedIn", "Email"], "manual_only": True},
        },
    },
    "sales_enablement": {
        "slug": "sales_enablement",
        "name": "Sales Enablement",
        "description": (
            "For B2B sales teams, SDRs, and revenue operators seeking to accelerate pipeline "
            "through targeted prospect research and personalized outreach."
        ),
        "category": "b2b_sales",
        "target_client_types": ["sales_rep", "sdr", "ae", "revenue_operator", "b2b_company", "saas", "startup"],
        "keywords": ["sales", "b2b", "prospect", "pipeline", "outreach", "revenue", "crm", "demo", "close", "lead", "sdr", "quota"],
        "default_workflow": {
            "discovery_sources": ["linkedin", "company_websites", "job_boards", "news"],
            "content_types": ["cold_email", "linkedin_dm", "follow_up"],
            "platforms": ["LinkedIn", "Email", "Phone"],
            "approval_required": True,
            "manual_distribution": True,
        },
        "memory_defaults": {
            "voice_tone": {"tone": "direct", "style": "concise", "examples": [], "forbidden_phrases": []},
            "workflow_preferences": {"max_assets_per_run": 10, "review_all_assets": False},
            "distribution_preferences": {"channels": ["LinkedIn", "Email"], "manual_only": True},
        },
    },
    "founder_thought_leadership": {
        "slug": "founder_thought_leadership",
        "name": "Founder Thought Leadership",
        "description": (
            "For startup founders and executives building public authority through strategic content, "
            "speaking opportunities, and media placements."
        ),
        "category": "executive_brand",
        "target_client_types": ["founder", "ceo", "executive", "startup_leader", "operator"],
        "keywords": ["founder", "startup", "executive", "ceo", "leadership", "thought_leader", "speaking", "authority", "brand", "venture"],
        "default_workflow": {
            "discovery_sources": ["linkedin", "twitter", "substack", "podcast_directories"],
            "content_types": ["linkedin_post", "twitter_thread", "essay", "speaking_pitch"],
            "platforms": ["LinkedIn", "Twitter/X", "Substack"],
            "approval_required": True,
            "manual_distribution": True,
        },
        "memory_defaults": {
            "voice_tone": {"tone": "authoritative", "style": "opinionated", "examples": [], "forbidden_phrases": []},
            "workflow_preferences": {"max_assets_per_run": 5, "review_all_assets": True},
            "distribution_preferences": {"channels": ["LinkedIn", "Twitter/X"], "manual_only": True},
        },
    },
    "investor_outreach": {
        "slug": "investor_outreach",
        "name": "Investor Outreach",
        "description": (
            "For startups and fund managers building LP relationships, managing investor communications, "
            "and accelerating fundraising through targeted research and positioning."
        ),
        "category": "fundraising",
        "target_client_types": ["startup_fundraising", "fund_manager", "gp", "lp_relations"],
        "keywords": ["investor", "fundraising", "venture", "capital", "lp", "fund", "raise", "seed", "series", "valuation", "deck"],
        "default_workflow": {
            "discovery_sources": ["crunchbase", "linkedin", "angel_list", "pitchbook"],
            "content_types": ["investor_update", "cold_email", "deck_teaser"],
            "platforms": ["Email", "LinkedIn"],
            "approval_required": True,
            "manual_distribution": True,
        },
        "memory_defaults": {
            "voice_tone": {"tone": "confident", "style": "data-driven", "examples": [], "forbidden_phrases": []},
            "workflow_preferences": {"max_assets_per_run": 5, "review_all_assets": True},
            "distribution_preferences": {"channels": ["Email", "LinkedIn"], "manual_only": True},
        },
    },
    "local_services": {
        "slug": "local_services",
        "name": "Local Services",
        "description": (
            "For local businesses — contractors, restaurants, clinics, salons — "
            "seeking to grow through community presence, local SEO, and referral generation."
        ),
        "category": "local_business",
        "target_client_types": ["contractor", "restaurant", "clinic", "salon", "local_retailer", "home_services"],
        "keywords": ["local", "contractor", "plumber", "electrician", "restaurant", "clinic", "salon", "service", "community", "neighborhood"],
        "default_workflow": {
            "discovery_sources": ["google_business", "yelp", "nextdoor", "local_directories"],
            "content_types": ["social_post", "google_post", "referral_request"],
            "platforms": ["Facebook", "Instagram", "Google Business", "Nextdoor"],
            "approval_required": True,
            "manual_distribution": True,
        },
        "memory_defaults": {
            "voice_tone": {"tone": "friendly", "style": "local", "examples": [], "forbidden_phrases": []},
            "workflow_preferences": {"max_assets_per_run": 5, "review_all_assets": True},
            "distribution_preferences": {"channels": ["Facebook", "Instagram"], "manual_only": True},
        },
    },
    "recruiting": {
        "slug": "recruiting",
        "name": "Recruiting",
        "description": (
            "For talent acquisition teams and recruiting firms building candidate pipelines, "
            "employer brand, and hiring manager relationships."
        ),
        "category": "talent",
        "target_client_types": ["recruiter", "talent_acquisition", "hr", "hiring_manager", "staffing_agency"],
        "keywords": ["recruiting", "hiring", "talent", "candidate", "recruiter", "hr", "staffing", "placement", "headhunter", "employer_brand"],
        "default_workflow": {
            "discovery_sources": ["linkedin", "indeed", "github", "dribbble"],
            "content_types": ["linkedin_post", "outreach_email", "job_post"],
            "platforms": ["LinkedIn", "Email", "Indeed"],
            "approval_required": True,
            "manual_distribution": True,
        },
        "memory_defaults": {
            "voice_tone": {"tone": "professional", "style": "human", "examples": [], "forbidden_phrases": []},
            "workflow_preferences": {"max_assets_per_run": 5, "review_all_assets": True},
            "distribution_preferences": {"channels": ["LinkedIn", "Email"], "manual_only": True},
        },
    },
}


def _score_template_against_profile(template: dict, profile_text: str) -> float:
    """Score a foundation template against a client profile text blob (0.0–1.0).

    Uses keyword overlap between the profile text and the template's keywords list.
    Returns a normalized score weighted by match density.
    """
    keywords = template.get("keywords", [])
    if not keywords:
        return 0.0
    lowered = profile_text.lower()
    matches = sum(1 for kw in keywords if kw.lower() in lowered)
    # Base score from keyword hits, normalized, with a density bonus
    raw = matches / len(keywords)
    # Boost if many keywords hit (dense match = stronger signal)
    if matches >= 3:
        raw = min(1.0, raw * 1.4)
    return round(raw, 4)


def _build_profile_text(payload_dict: dict) -> str:
    """Concatenate all string fields from a client profile dict into one searchable blob."""
    parts: list[str] = []
    for v in payload_dict.values():
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
        elif isinstance(v, list):
            parts.extend(str(x) for x in v if str(x).strip())
    return " ".join(parts)


def _make_memory_skeleton(template_slug: str) -> dict:
    """Return a fully-formed empty client memory body from the chosen template."""
    tmpl = FOUNDATION_TEMPLATES.get(template_slug, {})
    defaults = tmpl.get("memory_defaults", {})
    return {
        "positioning": {
            "what_they_do": "",
            "who_they_help": "",
            "why_buyers_choose": "",
            "proof_points": [],
            "differentiators": [],
        },
        "icp": {
            "company_type": "",
            "buyer": "",
            "size": "",
            "geography": "",
            "budget_indicators": [],
            "timing_signals": [],
        },
        "voice_tone": defaults.get("voice_tone", {"tone": "", "style": "", "examples": [], "forbidden_phrases": []}),
        "offers": [],
        "approved_claims": [],
        "blocked_claims": [],
        "winning_patterns": [],
        "losing_patterns": [],
        "source_preferences": [],
        "workflow_preferences": defaults.get("workflow_preferences", {"max_assets_per_run": 5, "review_all_assets": True}),
        "distribution_preferences": defaults.get("distribution_preferences", {"channels": [], "manual_only": True}),
        "approval_tendencies": {
            "approval_rate": None,
            "avg_revision_count": None,
            "common_rejection_reasons": [],
        },
        "performance_notes": [],
    }


# ---------------------------------------------------------------------------
# Phase 6N helpers: memory context injection
# ---------------------------------------------------------------------------

def build_memory_context(db, workspace_slug: str) -> dict:
    """Load and condense client memory for a workspace into a workflow-injectable context dict.

    Returns ``{"has_memory": False}`` when no memory is found or on any error.
    """
    import hashlib
    import json as _json

    try:
        memory = db.client_memories.find_one({"workspace_slug": workspace_slug})
        if not memory:
            return {"has_memory": False}

        vt = memory.get("voice_tone") or {}
        winning = [p for p in (memory.get("winning_patterns") or []) if p]
        losing = [p for p in (memory.get("losing_patterns") or []) if p]
        blocked = [c for c in (memory.get("blocked_claims") or []) if c]
        approved = [c for c in (memory.get("approved_claims") or []) if c]
        dist_prefs = memory.get("distribution_preferences") or {}
        src_prefs = memory.get("source_preferences") or []
        wf_prefs = memory.get("workflow_preferences") or {}
        approval_tend = memory.get("approval_tendencies") or {}
        perf_notes = [n for n in (memory.get("performance_notes") or []) if n]

        snapshot = {
            "voice_tone": vt,
            "winning_patterns": winning,
            "losing_patterns": losing,
            "blocked_claims": blocked,
            "approved_claims": approved,
            "distribution_preferences": dist_prefs,
            "source_preferences": src_prefs,
        }

        hash_input = _json.dumps(snapshot, sort_keys=True, default=str)
        memory_context_hash = hashlib.md5(hash_input.encode()).hexdigest()

        return {
            "has_memory": True,
            "memory_id": str(memory["_id"]),
            "memory_version": memory.get("version", 1),
            "memory_context_hash": memory_context_hash,
            "voice_tone": vt,
            "winning_patterns": winning,
            "losing_patterns": losing,
            "blocked_claims": blocked,
            "approved_claims": approved,
            "distribution_preferences": dist_prefs,
            "source_preferences": src_prefs,
            "workflow_preferences": wf_prefs,
            "approval_tendencies": approval_tend,
            "performance_notes": perf_notes,
            "snapshot": snapshot,
            "snapshot_taken_at": utc_now().isoformat(),
        }
    except Exception:
        return {"has_memory": False}


def _enforce_memory_constraints(text: str, memory_ctx: dict) -> dict:
    """Check text against blocked_claims and losing_patterns from client memory.

    Returns ``{"violations": list, "warnings": list, "clean": bool}``
    """
    if not memory_ctx.get("has_memory"):
        return {"violations": [], "warnings": [], "clean": True}

    text_lower = clean_text(text).lower()
    violations: list[str] = []
    warnings_list: list[str] = []

    for claim in memory_ctx.get("blocked_claims") or []:
        needle = clean_text(str(claim)).lower()
        if needle and needle in text_lower:
            violations.append(f"Blocked claim detected: '{claim}'")

    for pattern in memory_ctx.get("losing_patterns") or []:
        needle = clean_text(str(pattern)).lower()
        if len(needle) >= 4 and needle in text_lower:
            warnings_list.append(f"Losing pattern detected: '{pattern}'")

    return {
        "violations": violations,
        "warnings": warnings_list,
        "clean": len(violations) == 0,
    }


def _build_memory_asset_hints(memory_ctx: dict) -> tuple[str, str]:
    """Return (tone_label, signal_block) strings for injecting into asset bodies.

    ``tone_label`` — e.g. "professional · direct"
    ``signal_block`` — multi-line block with winning patterns / channel guidance
    """
    if not memory_ctx.get("has_memory"):
        return "", ""

    vt = memory_ctx.get("voice_tone") or {}
    parts = [p for p in (vt.get("tone", ""), vt.get("style", "")) if p]
    tone_label = " · ".join(parts) if parts else ""

    lines: list[str] = []
    winning = memory_ctx.get("winning_patterns") or []
    if winning:
        lines.append(f"⚡ Apply: {winning[0]}")
    dist = memory_ctx.get("distribution_preferences") or {}
    channels = dist.get("channels") or []
    if isinstance(channels, list) and channels:
        lines.append(f"📢 Preferred channel: {channels[0]}")
    version = memory_ctx.get("memory_version", 0)
    ws = memory_ctx.get("snapshot", {})
    if lines:
        lines.append(f"[Memory v{version} applied]")

    return tone_label, "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 6M Pydantic models
# ---------------------------------------------------------------------------

class TemplateRecommendationRequest(BaseModel):
    client_name: str = ""
    brand_name: str = ""
    industry: str = ""
    business_type: str = ""
    description: str = ""
    primary_offer: str = ""
    target_audience: str = ""
    goals: str = ""
    notes: str = ""


class ClientMemoryInitRequest(BaseModel):
    workspace_slug: str
    client_profile_id: str = ""
    foundation_template_slug: str
    # Optional pre-population
    positioning: dict = Field(default_factory=dict)
    icp: dict = Field(default_factory=dict)
    voice_tone: dict = Field(default_factory=dict)
    offers: list = Field(default_factory=list)
    approved_claims: list[str] = Field(default_factory=list)
    blocked_claims: list[str] = Field(default_factory=list)


class ClientMemoryUpdateRequest(BaseModel):
    positioning: Optional[dict] = None
    icp: Optional[dict] = None
    voice_tone: Optional[dict] = None
    offers: Optional[list] = None
    approved_claims: Optional[list[str]] = None
    blocked_claims: Optional[list[str]] = None
    winning_patterns: Optional[list[str]] = None
    losing_patterns: Optional[list[str]] = None
    source_preferences: Optional[list] = None
    workflow_preferences: Optional[dict] = None
    distribution_preferences: Optional[dict] = None
    approval_tendencies: Optional[dict] = None
    performance_notes: Optional[list[str]] = None


class MemoryUpdateProposalCreateRequest(BaseModel):
    workspace_slug: str
    client_memory_id: str = ""
    client_profile_id: str = ""
    workflow_run_id: str = ""
    source: str = ""  # e.g. "asset_approval", "mark_published", "user_override"
    proposed_change: dict  # {field, change_type: add|update|remove, old_value, new_value}
    evidence: str = ""
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class MemoryUpdateProposalDecisionRequest(BaseModel):
    status: Literal["approved", "rejected"]
    reviewed_by: str = "operator"
    note: str = ""
    override_conflicts: bool = False  # Phase 6O: if True, approve despite high-severity conflicts


class MemoryRollbackRequest(BaseModel):
    target_version: int = Field(ge=1)
    reason: str = ""
    rolled_back_by: str = "operator"


# ---------------------------------------------------------------------------
# Phase 6M helper: auto-propose memory updates from workflow outcomes
# ---------------------------------------------------------------------------

def _try_propose_memory_update(
    db,
    *,
    workspace_slug: str,
    workflow_run_id: str,
    source: str,
    proposed_change: dict,
    evidence: str,
    confidence: float = 0.7,
) -> None:
    """Best-effort insert of a memory update proposal.  Silently swallows errors."""
    try:
        memory = db.client_memories.find_one({"workspace_slug": workspace_slug})
        if not memory:
            return
        now = utc_now()
        db.memory_update_proposals.insert_one({
            "workspace_slug": workspace_slug,
            "client_memory_id": str(memory["_id"]),
            "client_profile_id": memory.get("client_profile_id", ""),
            "workflow_run_id": workflow_run_id,
            "source": source,
            "proposed_change": proposed_change,
            "evidence": evidence,
            "confidence": confidence,
            "status": "pending",
            "reviewed_by": None,
            "reviewed_at": None,
            # Phase 6N: traceability
            "memory_version_used": memory.get("version", 1),
            "reasoning_trace": f"Auto-generated from {source} event. workflow_run_id={workflow_run_id}",
            "created_at": now,
            "updated_at": now,
        })
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 6O: Memory Governance helpers
# ---------------------------------------------------------------------------

_STALE_DAYS = 30
_DUPLICATE_SIMILARITY_THRESHOLD = 0.65
_AUTO_REJECT_CONFIDENCE_MAX = 0.25
_CONFLICT_SIMILARITY_MIN = 0.40

_TONE_OPPOSITES: dict[str, list[str]] = {
    "aggressive":    ["conservative", "gentle", "soft"],
    "conservative":  ["aggressive", "bold", "edgy"],
    "casual":        ["formal", "professional", "corporate"],
    "formal":        ["casual", "conversational", "informal"],
    "edgy":          ["conservative", "professional", "safe"],
    "direct":        ["indirect", "nuanced"],
    "indirect":      ["direct", "blunt"],
    "conversational": ["formal", "corporate"],
    "corporate":     ["casual", "conversational"],
}


def _token_similarity(a: str, b: str) -> float:
    """Jaccard similarity of token sets from two strings."""
    ta = set(clean_text(a).lower().split())
    tb = set(clean_text(b).lower().split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _detect_proposal_conflicts(memory_doc: dict, proposed_change: dict) -> list[dict]:
    """Detect logical conflicts between a proposed change and the current memory state.

    Returns a list of conflict dicts: {conflict_type, description, severity,
    conflicting_field, conflicting_value, similarity}
    """
    conflicts: list[dict] = []
    if not memory_doc or not proposed_change:
        return conflicts

    field = proposed_change.get("field", "")
    change_type = proposed_change.get("change_type", "update")
    new_value = proposed_change.get("new_value")
    if new_value is None:
        return conflicts

    new_items: list[str] = [str(x).strip() for x in (new_value if isinstance(new_value, list) else [new_value]) if x]

    # winning_patterns <-> losing_patterns
    if field == "winning_patterns" and change_type in ("add", "update"):
        losing = memory_doc.get("losing_patterns") or []
        for item in new_items:
            for lp in losing:
                sim = _token_similarity(item, lp)
                if sim >= _CONFLICT_SIMILARITY_MIN:
                    conflicts.append({
                        "conflict_type": "winning_losing_overlap",
                        "description": f"Proposed winning pattern overlaps with existing losing pattern '{lp}'",
                        "severity": "high" if sim >= 0.65 else "medium",
                        "conflicting_field": "losing_patterns",
                        "conflicting_value": lp,
                        "similarity": round(sim, 2),
                    })

    if field == "losing_patterns" and change_type in ("add", "update"):
        winning = memory_doc.get("winning_patterns") or []
        for item in new_items:
            for wp in winning:
                sim = _token_similarity(item, wp)
                if sim >= _CONFLICT_SIMILARITY_MIN:
                    conflicts.append({
                        "conflict_type": "losing_winning_overlap",
                        "description": f"Proposed losing pattern overlaps with existing winning pattern '{wp}'",
                        "severity": "high" if sim >= 0.65 else "medium",
                        "conflicting_field": "winning_patterns",
                        "conflicting_value": wp,
                        "similarity": round(sim, 2),
                    })

    # blocked_claims <-> approved_claims
    if field == "blocked_claims" and change_type in ("add", "update"):
        approved = memory_doc.get("approved_claims") or []
        for item in new_items:
            for ap in approved:
                sim = _token_similarity(item, ap)
                if sim >= 0.50:
                    conflicts.append({
                        "conflict_type": "blocked_approved_overlap",
                        "description": f"Proposed blocked claim overlaps with approved claim '{ap}'",
                        "severity": "high",
                        "conflicting_field": "approved_claims",
                        "conflicting_value": ap,
                        "similarity": round(sim, 2),
                    })

    if field == "approved_claims" and change_type in ("add", "update"):
        blocked = memory_doc.get("blocked_claims") or []
        for item in new_items:
            for bl in blocked:
                sim = _token_similarity(item, bl)
                if sim >= 0.50:
                    conflicts.append({
                        "conflict_type": "approved_blocked_overlap",
                        "description": f"Proposed approved claim overlaps with blocked claim '{bl}'",
                        "severity": "high",
                        "conflicting_field": "blocked_claims",
                        "conflicting_value": bl,
                        "similarity": round(sim, 2),
                    })

    # voice_tone contradiction
    if field == "voice_tone" and isinstance(new_value, dict):
        current_tone = (memory_doc.get("voice_tone") or {}).get("tone", "").lower()
        proposed_tone = new_value.get("tone", "").lower()
        if current_tone and proposed_tone and current_tone != proposed_tone:
            if current_tone in _TONE_OPPOSITES.get(proposed_tone, []):
                conflicts.append({
                    "conflict_type": "tone_contradiction",
                    "description": f"Proposed tone '{proposed_tone}' contradicts existing tone '{current_tone}'",
                    "severity": "medium",
                    "conflicting_field": "voice_tone.tone",
                    "conflicting_value": current_tone,
                    "similarity": 0.0,
                })

    return conflicts


def _detect_proposal_duplicate(db, workspace_slug: str, proposed_change: dict) -> dict:
    """Check if a sufficiently similar pending proposal already exists.

    Returns {"is_duplicate": bool, "duplicate_proposal_id": str, "similarity": float, "reason": str}
    """
    field = proposed_change.get("field", "")
    new_value = proposed_change.get("new_value")
    if not field or new_value is None:
        return {"is_duplicate": False, "duplicate_proposal_id": "", "similarity": 0.0, "reason": ""}
    try:
        candidates = list(db.memory_update_proposals.find({
            "workspace_slug": workspace_slug,
            "status": "pending",
            "proposed_change.field": field,
        }).limit(30))
        new_str = str(new_value).lower()
        for cand in candidates:
            ex_val = (cand.get("proposed_change") or {}).get("new_value")
            if ex_val is None:
                continue
            ex_str = str(ex_val).lower()
            if ex_str == new_str:
                return {
                    "is_duplicate": True,
                    "duplicate_proposal_id": str(cand["_id"]),
                    "similarity": 1.0,
                    "reason": "Identical pending proposal already exists.",
                }
            sim = _token_similarity(new_str, ex_str)
            if sim >= _DUPLICATE_SIMILARITY_THRESHOLD:
                return {
                    "is_duplicate": True,
                    "duplicate_proposal_id": str(cand["_id"]),
                    "similarity": round(sim, 2),
                    "reason": f"Near-identical pending proposal detected (similarity {sim:.0%}).",
                }
    except Exception:
        pass
    return {"is_duplicate": False, "duplicate_proposal_id": "", "similarity": 0.0, "reason": ""}


def _generate_memory_diff(memory_doc: dict, proposed_change: dict) -> dict:
    """Compute a before/after diff for a proposed change without applying it."""
    field = proposed_change.get("field", "")
    change_type = proposed_change.get("change_type", "update")
    new_value = proposed_change.get("new_value")
    current_value = (memory_doc or {}).get(field)

    additions: list = []
    removals: list = []
    result_value = new_value

    if isinstance(current_value, list):
        if change_type == "add":
            add_items = new_value if isinstance(new_value, list) else [new_value]
            additions = [v for v in add_items if v not in current_value]
            result_value = list(current_value) + additions
        elif change_type == "remove":
            rm_items = new_value if isinstance(new_value, list) else [new_value]
            removals = [v for v in rm_items if v in current_value]
            result_value = [v for v in current_value if v not in rm_items]
        else:
            new_list = new_value if isinstance(new_value, list) else [new_value]
            additions = [v for v in new_list if v not in current_value]
            removals = [v for v in current_value if v not in new_list]
            result_value = new_list
    elif isinstance(current_value, dict) and isinstance(new_value, dict):
        for k, v in new_value.items():
            if current_value.get(k) != v:
                additions.append(f"{k}: {v}")
                if k in current_value:
                    removals.append(f"{k}: {current_value[k]}")
    else:
        if current_value != new_value:
            removals = [current_value] if current_value is not None else []
            additions = [new_value] if new_value is not None else []

    return {
        "field": field,
        "change_type": change_type,
        "current_value": current_value,
        "proposed_value": new_value,
        "result_value": result_value,
        "additions": additions,
        "removals": removals,
        "has_changes": current_value != result_value,
    }


def _snapshot_memory_for_history(
    db,
    memory_doc: dict,
    *,
    change_summary: list[str],
    source_proposal_ids: list[str],
    created_by: str = "operator",
) -> None:
    """Write an immutable version snapshot to memory_version_history before a change is applied."""
    try:
        import json as _json
        snap = {k: v for k, v in memory_doc.items() if k != "_id"}
        snap = _json.loads(_json.dumps(snap, default=str))
        db.memory_version_history.insert_one({
            "client_memory_id": str(memory_doc["_id"]),
            "workspace_slug": memory_doc.get("workspace_slug", ""),
            "version": memory_doc.get("version", 1),
            "previous_version": max(0, (memory_doc.get("version", 1) - 1)),
            "snapshot": snap,
            "change_summary": change_summary,
            "source_proposal_ids": source_proposal_ids,
            "created_by": created_by,
            "created_at": utc_now(),
        })
    except Exception:
        pass  # Non-fatal: never block the main approval flow


def _compute_memory_health(db, memory_doc: dict) -> dict:
    """Compute health metrics for a client memory document."""
    if not memory_doc:
        return {"status": "unknown", "memory_health_score": 0.0, "conflict_count": 0}

    from datetime import timezone as _tz

    now = utc_now()
    winning = memory_doc.get("winning_patterns") or []
    losing = memory_doc.get("losing_patterns") or []
    blocked = memory_doc.get("blocked_claims") or []
    approved = memory_doc.get("approved_claims") or []

    # Conflict count: winning/losing overlap + blocked/approved overlap
    conflict_count = 0
    conflict_pairs: list[dict] = []
    for w in winning:
        for ll in losing:
            sim = _token_similarity(w, ll)
            if sim >= _CONFLICT_SIMILARITY_MIN:
                conflict_count += 1
                if len(conflict_pairs) < 5:
                    conflict_pairs.append({"winning": w, "losing": ll, "similarity": round(sim, 2)})
    for bl in blocked:
        for ap in approved:
            sim = _token_similarity(bl, ap)
            if sim >= 0.50:
                conflict_count += 1
                if len(conflict_pairs) < 5:
                    conflict_pairs.append({"blocked": bl, "approved": ap, "similarity": round(sim, 2)})

    # Duplicate patterns in same list
    def _count_dupes(lst: list) -> int:
        count = 0
        for i, a in enumerate(lst):
            for b in lst[i + 1:]:
                if _token_similarity(a, b) >= _DUPLICATE_SIMILARITY_THRESHOLD:
                    count += 1
        return count

    duplicate_count = _count_dupes(winning) + _count_dupes(losing)
    all_patterns = winning + losing
    overgrown = len(all_patterns) > 20

    # Stale detection
    stale_days = 0
    updated_at = memory_doc.get("updated_at")
    if updated_at:
        try:
            if hasattr(updated_at, "tzinfo"):
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=_tz.utc)
            else:
                from datetime import datetime as _dt
                updated_at = _dt.fromisoformat(str(updated_at).replace("Z", "+00:00"))
            stale_days = max(0, (now - updated_at).days)
        except Exception:
            stale_days = 0

    stale = stale_days >= _STALE_DAYS and len(all_patterns) > 0

    # Pending proposal count
    try:
        pending_count = db.memory_update_proposals.count_documents(
            {"workspace_slug": memory_doc.get("workspace_slug", ""), "status": "pending"}
        )
    except Exception:
        pending_count = 0

    # Last approved proposal timestamp
    try:
        last_ap = db.memory_update_proposals.find_one(
            {"workspace_slug": memory_doc.get("workspace_slug", ""), "status": "approved"},
            sort=[("reviewed_at", -1)],
        )
        last_reviewed_at = str(last_ap.get("reviewed_at", "")) if last_ap else None
    except Exception:
        last_reviewed_at = None

    # Health score 0.0-1.0
    score = 1.0
    score -= min(0.40, conflict_count * 0.15)
    score -= min(0.20, duplicate_count * 0.10)
    if stale:
        score -= 0.15
    if overgrown:
        score -= 0.10
    score = round(max(0.0, score), 2)

    if conflict_count > 0:
        status = "conflicted"
    elif stale:
        status = "stale"
    elif overgrown:
        status = "overgrown"
    elif duplicate_count > 0 or pending_count > 3:
        status = "needs_review"
    else:
        status = "healthy"

    return {
        "memory_health_score": score,
        "status": status,
        "conflict_count": conflict_count,
        "conflict_pairs": conflict_pairs,
        "duplicate_pattern_count": duplicate_count,
        "stale": stale,
        "stale_days": stale_days,
        "overgrown": overgrown,
        "total_patterns": len(all_patterns),
        "winning_pattern_count": len(winning),
        "losing_pattern_count": len(losing),
        "blocked_claim_count": len(blocked),
        "approved_claim_count": len(approved),
        "pending_proposal_count": pending_count,
        "last_reviewed_at": last_reviewed_at,
        "version": memory_doc.get("version", 1),
    }


# ---------------------------------------------------------------------------
# Phase 6M Endpoints: Foundation Templates
# ---------------------------------------------------------------------------

@app.get("/foundation-templates")
def list_foundation_templates() -> dict:
    """Return all available foundation templates."""
    items = [
        {k: v for k, v in t.items() if k != "keywords"}
        for t in FOUNDATION_TEMPLATES.values()
    ]
    return {"items": items, "count": len(items)}


@app.get("/foundation-templates/{slug}")
def get_foundation_template(slug: str) -> dict:
    """Return a single foundation template by slug."""
    tmpl = FOUNDATION_TEMPLATES.get(slug)
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"Foundation template '{slug}' not found.")
    return {"item": {k: v for k, v in tmpl.items() if k != "keywords"}}


# ---------------------------------------------------------------------------
# Phase 6M Endpoints: Template Recommendation
# ---------------------------------------------------------------------------

@app.post("/template-recommendation")
def recommend_template(payload: TemplateRecommendationRequest) -> dict:
    """Score all foundation templates against the provided client profile and return a ranked recommendation.

    Uses deterministic keyword scoring (no LLM required).
    Returns: recommended template, confidence, reason, alternates, assumptions, missing_information.
    """
    profile_dict = payload.model_dump()
    profile_text = _build_profile_text(profile_dict)

    if not profile_text.strip():
        raise HTTPException(status_code=400, detail="At least one profile field is required for recommendation.")

    # Score every template
    scored: list[tuple[float, str]] = []
    for slug, tmpl in FOUNDATION_TEMPLATES.items():
        score = _score_template_against_profile(tmpl, profile_text)
        scored.append((score, slug))
    scored.sort(key=lambda x: x[0], reverse=True)

    best_score, best_slug = scored[0]
    best_tmpl = FOUNDATION_TEMPLATES[best_slug]

    # Build alternates (exclude top pick)
    alternates = [
        {
            "slug": s,
            "name": FOUNDATION_TEMPLATES[s]["name"],
            "score": round(sc, 4),
            "reason": f"Partial keyword overlap with {FOUNDATION_TEMPLATES[s]['category']} profile signals.",
        }
        for sc, s in scored[1:4]
        if sc > 0.0
    ]

    # Identify missing information
    missing: list[str] = []
    if not payload.industry.strip():
        missing.append("industry")
    if not payload.primary_offer.strip():
        missing.append("primary_offer")
    if not payload.target_audience.strip():
        missing.append("target_audience")

    # Build assumptions from what we inferred
    assumptions: list[str] = []
    if best_score < 0.3:
        assumptions.append("Low keyword overlap — recommendation is a best-guess based on available profile text.")
        assumptions.append(f"Defaulting to '{best_tmpl['name']}' as the closest match; review alternates before confirming.")
    else:
        assumptions.append(f"Client profile signals align with the '{best_tmpl['category']}' category.")

    # Human-readable reason
    if best_score >= 0.5:
        reason = (
            f"Strong keyword alignment with {best_tmpl['name']} template. "
            f"Profile mentions signals common to {best_tmpl['category']} clients "
            f"({', '.join(best_tmpl.get('keywords', [])[:4])})."
        )
        confidence = min(0.95, 0.6 + best_score * 0.35)
    elif best_score >= 0.2:
        reason = (
            f"Moderate match with {best_tmpl['name']} template based on partial profile signals. "
            "Consider reviewing alternate templates before confirming."
        )
        confidence = min(0.7, 0.3 + best_score * 0.5)
    else:
        reason = (
            f"Weak signal match. '{best_tmpl['name']}' selected as closest option, "
            "but the profile lacks enough specificity for a confident recommendation. "
            "Add industry, primary offer, and target audience for better results."
        )
        confidence = round(max(0.1, best_score * 0.8), 4)

    return {
        "recommended_template": {
            "slug": best_slug,
            "name": best_tmpl["name"],
            "description": best_tmpl["description"],
            "category": best_tmpl["category"],
        },
        "confidence_score": round(confidence, 4),
        "reason": reason,
        "alternate_templates": alternates,
        "assumptions": assumptions,
        "missing_information": missing,
        "raw_scores": {s: sc for sc, s in scored},
    }


# ---------------------------------------------------------------------------
# Phase 6M Endpoints: Client Memory
# ---------------------------------------------------------------------------

@app.get("/client-memory")
def list_client_memories(
    workspace_slug: str = Query(""),
    client_profile_id: str = Query(""),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """List client operating memories, optionally filtered by workspace or client profile."""
    mongo_client = get_client()
    try:
        db = get_database(mongo_client)
        q: dict[str, Any] = {}
        if workspace_slug:
            q["workspace_slug"] = workspace_slug
        if client_profile_id:
            q["client_profile_id"] = client_profile_id
        records = list(db.client_memories.find(q).sort([("created_at", -1)]).limit(limit))
        return {"items": serialize(records), "count": len(records)}
    finally:
        mongo_client.close()


@app.post("/client-memory")
def create_client_memory(payload: ClientMemoryInitRequest) -> dict:
    """Initialize a client operating memory from a foundation template.

    Merges template defaults with any values provided in the request.
    One memory per workspace (idempotent — returns existing if already present).
    """
    if not payload.workspace_slug.strip():
        raise HTTPException(status_code=400, detail="workspace_slug is required.")
    if payload.foundation_template_slug not in FOUNDATION_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown foundation_template_slug '{payload.foundation_template_slug}'. "
                   f"Valid slugs: {sorted(FOUNDATION_TEMPLATES.keys())}",
        )

    mongo_client = get_client()
    try:
        db = get_database(mongo_client)

        # Idempotent: return existing memory if one already exists for this workspace
        existing = db.client_memories.find_one({"workspace_slug": payload.workspace_slug})
        if existing:
            return {
                "item": serialize(existing),
                "message": "Client memory already exists for this workspace.",
                "created": False,
            }

        now = utc_now()
        memory_body = _make_memory_skeleton(payload.foundation_template_slug)

        # Apply caller-supplied overrides
        if payload.positioning:
            memory_body["positioning"].update({k: v for k, v in payload.positioning.items() if v})
        if payload.icp:
            memory_body["icp"].update({k: v for k, v in payload.icp.items() if v})
        if payload.voice_tone:
            memory_body["voice_tone"].update({k: v for k, v in payload.voice_tone.items() if v})
        if payload.offers:
            memory_body["offers"] = payload.offers
        if payload.approved_claims:
            memory_body["approved_claims"] = [clean_text(c) for c in payload.approved_claims if clean_text(c)]
        if payload.blocked_claims:
            memory_body["blocked_claims"] = [clean_text(c) for c in payload.blocked_claims if clean_text(c)]

        record: dict[str, Any] = {
            "workspace_slug": clean_text(payload.workspace_slug),
            "client_profile_id": clean_text(payload.client_profile_id),
            "foundation_template_slug": payload.foundation_template_slug,
            "foundation_template_name": FOUNDATION_TEMPLATES[payload.foundation_template_slug]["name"],
            "version": 1,
            **memory_body,
            "created_at": now,
            "updated_at": now,
        }

        result = db.client_memories.insert_one(record)
        created = db.client_memories.find_one({"_id": result.inserted_id})
        return {
            "item": serialize(created),
            "message": "Client operating memory initialized.",
            "created": True,
        }
    finally:
        mongo_client.close()


@app.patch("/client-memory/{memory_id}")
def update_client_memory(memory_id: str, payload: ClientMemoryUpdateRequest) -> dict:
    """Update fields of a client operating memory. Increments version on each save."""
    if not is_object_id(memory_id):
        raise HTTPException(status_code=400, detail="Invalid memory_id.")
    mongo_client = get_client()
    now = utc_now()
    try:
        db = get_database(mongo_client)
        doc = db.client_memories.find_one({"_id": ObjectId(memory_id)})
        if not doc:
            raise HTTPException(status_code=404, detail=f"Client memory '{memory_id}' not found.")

        updates: dict[str, Any] = {"updated_at": now, "version": (doc.get("version") or 1) + 1}
        if payload.positioning is not None:
            updates["positioning"] = payload.positioning
        if payload.icp is not None:
            updates["icp"] = payload.icp
        if payload.voice_tone is not None:
            updates["voice_tone"] = payload.voice_tone
        if payload.offers is not None:
            updates["offers"] = payload.offers
        if payload.approved_claims is not None:
            updates["approved_claims"] = [clean_text(c) for c in payload.approved_claims if clean_text(c)]
        if payload.blocked_claims is not None:
            updates["blocked_claims"] = [clean_text(c) for c in payload.blocked_claims if clean_text(c)]
        if payload.winning_patterns is not None:
            updates["winning_patterns"] = [clean_text(p) for p in payload.winning_patterns if clean_text(p)]
        if payload.losing_patterns is not None:
            updates["losing_patterns"] = [clean_text(p) for p in payload.losing_patterns if clean_text(p)]
        if payload.source_preferences is not None:
            updates["source_preferences"] = payload.source_preferences
        if payload.workflow_preferences is not None:
            updates["workflow_preferences"] = payload.workflow_preferences
        if payload.distribution_preferences is not None:
            updates["distribution_preferences"] = payload.distribution_preferences
        if payload.approval_tendencies is not None:
            updates["approval_tendencies"] = payload.approval_tendencies
        if payload.performance_notes is not None:
            updates["performance_notes"] = [clean_text(n) for n in payload.performance_notes if clean_text(n)]

        db.client_memories.update_one({"_id": doc["_id"]}, {"$set": updates})
        updated = db.client_memories.find_one({"_id": doc["_id"]})
        return {"item": serialize(updated), "message": "Client memory updated."}
    finally:
        mongo_client.close()


@app.get("/client-memory/{memory_id}/brief")
def get_client_memory_brief(memory_id: str) -> dict:
    """Generate a human-readable markdown brief from the client operating memory."""
    if not is_object_id(memory_id):
        raise HTTPException(status_code=400, detail="Invalid memory_id.")
    mongo_client = get_client()
    try:
        db = get_database(mongo_client)
        doc = db.client_memories.find_one({"_id": ObjectId(memory_id)})
        if not doc:
            raise HTTPException(status_code=404, detail=f"Client memory '{memory_id}' not found.")

        def _list_md(items: list, indent: str = "  ") -> str:
            return "\n".join(f"{indent}- {item}" for item in items) if items else f"{indent}_(none recorded)_"

        pos = doc.get("positioning") or {}
        icp = doc.get("icp") or {}
        vt = doc.get("voice_tone") or {}
        at = doc.get("approval_tendencies") or {}

        brief = f"""# Client Operating Brief
**Workspace:** `{doc.get('workspace_slug', '')}`
**Foundation Template:** {doc.get('foundation_template_name', doc.get('foundation_template_slug', ''))}
**Version:** {doc.get('version', 1)}
**Last Updated:** {(doc.get('updated_at') or doc.get('created_at', '')).isoformat() if hasattr((doc.get('updated_at') or doc.get('created_at', '')), 'isoformat') else str(doc.get('updated_at', ''))}

---

## Positioning
- **What they do:** {pos.get('what_they_do') or '_(not set)_'}
- **Who they help:** {pos.get('who_they_help') or '_(not set)_'}
- **Why buyers choose them:** {pos.get('why_buyers_choose') or '_(not set)_'}

**Proof points:**
{_list_md(pos.get('proof_points', []))}

**Differentiators:**
{_list_md(pos.get('differentiators', []))}

---

## Ideal Customer Profile
- **Company type:** {icp.get('company_type') or '_(not set)_'}
- **Buyer:** {icp.get('buyer') or '_(not set)_'}
- **Size:** {icp.get('size') or '_(not set)_'}
- **Geography:** {icp.get('geography') or '_(not set)_'}

**Budget indicators:**
{_list_md(icp.get('budget_indicators', []))}

**Timing signals:**
{_list_md(icp.get('timing_signals', []))}

---

## Voice & Tone
- **Tone:** {vt.get('tone') or '_(not set)_'}
- **Style:** {vt.get('style') or '_(not set)_'}

**Approved claims:**
{_list_md(doc.get('approved_claims', []))}

**Blocked claims:**
{_list_md(doc.get('blocked_claims', []))}

---

## Offers
{_list_md([str(o) if not isinstance(o, dict) else o.get('name', str(o)) for o in (doc.get('offers') or [])])}

---

## Winning Patterns
{_list_md(doc.get('winning_patterns', []))}

## Losing Patterns
{_list_md(doc.get('losing_patterns', []))}

---

## Approval Tendencies
- **Approval rate:** {f"{int((at.get('approval_rate') or 0) * 100)}%" if at.get('approval_rate') is not None else '_(not enough data)_'}
- **Avg revisions:** {at.get('avg_revision_count') if at.get('avg_revision_count') is not None else '_(not enough data)_'}

**Common rejection reasons:**
{_list_md(at.get('common_rejection_reasons', []))}

---

## Performance Notes
{_list_md(doc.get('performance_notes', []))}
"""

        return {
            "memory_id": memory_id,
            "workspace_slug": doc.get("workspace_slug", ""),
            "brief_markdown": brief,
            "version": doc.get("version", 1),
        }
    finally:
        mongo_client.close()


# ---------------------------------------------------------------------------
# Phase 6M Endpoints: Memory Update Proposals
# ---------------------------------------------------------------------------

@app.get("/memory-update-proposals")
def list_memory_update_proposals(
    workspace_slug: str = Query(""),
    client_memory_id: str = Query(""),
    status: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """List memory update proposals."""
    mongo_client = get_client()
    try:
        db = get_database(mongo_client)
        q: dict[str, Any] = {}
        if workspace_slug:
            q["workspace_slug"] = workspace_slug
        if client_memory_id:
            q["client_memory_id"] = client_memory_id
        if status:
            q["status"] = status
        records = list(db.memory_update_proposals.find(q).sort([("created_at", -1)]).limit(limit))
        return {"items": serialize(records), "count": len(records)}
    finally:
        mongo_client.close()


@app.post("/memory-update-proposals")
def create_memory_update_proposal(payload: MemoryUpdateProposalCreateRequest) -> dict:
    """Manually create a memory update proposal."""
    if not payload.workspace_slug.strip():
        raise HTTPException(status_code=400, detail="workspace_slug is required.")
    if not payload.proposed_change:
        raise HTTPException(status_code=400, detail="proposed_change is required.")

    allowed_fields = {
        "positioning", "icp", "voice_tone", "offers",
        "approved_claims", "blocked_claims", "winning_patterns", "losing_patterns",
        "source_preferences", "workflow_preferences", "distribution_preferences",
        "approval_tendencies", "performance_notes",
    }
    field = payload.proposed_change.get("field", "")
    if field and field not in allowed_fields:
        raise HTTPException(status_code=400, detail=f"Unknown memory field '{field}'. Valid fields: {sorted(allowed_fields)}")

    now = utc_now()
    mongo_client = get_client()
    try:
        db = get_database(mongo_client)

        # Phase 6O: conflict + duplicate detection before insertion
        memory_doc_for_check = db.client_memories.find_one({"workspace_slug": clean_text(payload.workspace_slug)})
        detected_conflicts = _detect_proposal_conflicts(memory_doc_for_check or {}, payload.proposed_change)
        dup_result = _detect_proposal_duplicate(db, clean_text(payload.workspace_slug), payload.proposed_change)

        high_severity = [c for c in detected_conflicts if c.get("severity") == "high"]

        # Confidence governance routing
        if payload.confidence <= _AUTO_REJECT_CONFIDENCE_MAX:
            governance_suggestion = "auto_reject"
        elif payload.confidence >= 0.90 and not high_severity and not dup_result["is_duplicate"]:
            governance_suggestion = "auto_approve"
        else:
            governance_suggestion = "review"

        record: dict[str, Any] = {
            "workspace_slug": clean_text(payload.workspace_slug),
            "client_memory_id": clean_text(payload.client_memory_id),
            "client_profile_id": clean_text(payload.client_profile_id),
            "workflow_run_id": clean_text(payload.workflow_run_id),
            "source": clean_text(payload.source),
            "proposed_change": payload.proposed_change,
            "evidence": clean_text(payload.evidence),
            "confidence": payload.confidence,
            "status": "pending",
            "reviewed_by": None,
            "reviewed_at": None,
            # Phase 6O governance fields
            "conflicts": detected_conflicts,
            "is_duplicate": dup_result["is_duplicate"],
            "duplicate_proposal_id": dup_result["duplicate_proposal_id"],
            "governance_suggestion": governance_suggestion,
            "created_at": now,
            "updated_at": now,
        }
        result = db.memory_update_proposals.insert_one(record)
        created = db.memory_update_proposals.find_one({"_id": result.inserted_id})
        return {"item": serialize(created), "message": "Memory update proposal created."}
    finally:
        mongo_client.close()


@app.patch("/memory-update-proposals/{proposal_id}")
def decide_memory_update_proposal(
    proposal_id: str, payload: MemoryUpdateProposalDecisionRequest
) -> dict:
    """Approve or reject a memory update proposal.

    When approved, the proposed change is automatically applied to the linked client memory.
    """
    if not is_object_id(proposal_id):
        raise HTTPException(status_code=400, detail="Invalid proposal_id.")

    mongo_client = get_client()
    now = utc_now()
    try:
        db = get_database(mongo_client)
        proposal = db.memory_update_proposals.find_one({"_id": ObjectId(proposal_id)})
        if not proposal:
            raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")
        if proposal.get("status") != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Proposal is already '{proposal.get('status')}' and cannot be re-decided.",
            )

        # Update proposal status
        db.memory_update_proposals.update_one(
            {"_id": proposal["_id"]},
            {"$set": {
                "status": payload.status,
                "reviewed_by": clean_text(payload.reviewed_by) or "operator",
                "reviewed_at": now,
                "updated_at": now,
                "note": clean_text(payload.note),
            }},
        )

        applied = False
        memory_updated = None

        if payload.status == "approved":
            # Phase 6O: block approval if high-severity conflicts exist and not overridden
            stored_conflicts = proposal.get("conflicts") or []
            high_conflicts = [c for c in stored_conflicts if c.get("severity") == "high"]
            if high_conflicts and not payload.override_conflicts:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Proposal has high-severity conflicts. Pass override_conflicts=true to approve anyway.",
                        "conflicts": high_conflicts,
                    },
                )

            # Apply the proposed change to the linked client memory
            mem_id = proposal.get("client_memory_id", "")
            change = proposal.get("proposed_change") or {}
            field = change.get("field", "")
            change_type = change.get("change_type", "update")  # add | update | remove
            new_value = change.get("new_value")

            memory_doc = None
            if mem_id and is_object_id(mem_id):
                memory_doc = db.client_memories.find_one({"_id": ObjectId(mem_id)})
            if not memory_doc:
                memory_doc = db.client_memories.find_one({"workspace_slug": proposal.get("workspace_slug", "")})

            if memory_doc and field and new_value is not None:
                # Phase 6O: snapshot current state BEFORE applying the change
                _snapshot_memory_for_history(
                    db,
                    memory_doc,
                    change_summary=[f"{change_type} {field}"],
                    source_proposal_ids=[proposal_id],
                    created_by=payload.reviewed_by or "operator",
                )

                current_val = memory_doc.get(field)
                if change_type == "add" and isinstance(current_val, list):
                    # Append to list without duplicates
                    if isinstance(new_value, list):
                        merged = list(current_val) + [v for v in new_value if v not in current_val]
                    else:
                        merged = list(current_val) + ([new_value] if new_value not in current_val else [])
                    update_val = merged
                elif change_type == "remove" and isinstance(current_val, list):
                    remove_items = new_value if isinstance(new_value, list) else [new_value]
                    update_val = [v for v in current_val if v not in remove_items]
                else:
                    # update: replace
                    update_val = new_value

                db.client_memories.update_one(
                    {"_id": memory_doc["_id"]},
                    {"$set": {field: update_val, "updated_at": now, "version": (memory_doc.get("version") or 1) + 1}},
                )
                memory_updated = str(memory_doc["_id"])
                applied = True

        updated_proposal = db.memory_update_proposals.find_one({"_id": proposal["_id"]})
        return {
            "item": serialize(updated_proposal),
            "applied_to_memory": applied,
            "memory_id": memory_updated,
            "message": (
                f"Proposal {payload.status}."
                + (" Memory updated." if applied else "")
                + (" Memory not found — change not applied." if payload.status == "approved" and not applied else "")
            ),
        }
    finally:
        mongo_client.close()


# ---------------------------------------------------------------------------
# Phase 6O Endpoints: Memory Version History & Health
# ---------------------------------------------------------------------------

@app.get("/client-memory/{memory_id}/history")
def get_client_memory_history(
    memory_id: str,
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """Return the immutable version history for a client operating memory, newest first."""
    if not is_object_id(memory_id):
        raise HTTPException(status_code=400, detail="Invalid memory_id.")
    mongo_client = get_client()
    try:
        db = get_database(mongo_client)
        if not db.client_memories.find_one({"_id": ObjectId(memory_id)}):
            raise HTTPException(status_code=404, detail=f"Client memory '{memory_id}' not found.")
        records = list(
            db.memory_version_history.find({"client_memory_id": memory_id})
            .sort([("version", -1)])
            .limit(limit)
        )
        return {"items": serialize(records), "count": len(records)}
    finally:
        mongo_client.close()


@app.get("/client-memory/{memory_id}/health")
def get_client_memory_health(memory_id: str) -> dict:
    """Compute and return health metrics for a client operating memory."""
    if not is_object_id(memory_id):
        raise HTTPException(status_code=400, detail="Invalid memory_id.")
    mongo_client = get_client()
    try:
        db = get_database(mongo_client)
        doc = db.client_memories.find_one({"_id": ObjectId(memory_id)})
        if not doc:
            raise HTTPException(status_code=404, detail=f"Client memory '{memory_id}' not found.")
        health = _compute_memory_health(db, doc)
        return {"memory_id": memory_id, "workspace_slug": doc.get("workspace_slug", ""), **health}
    finally:
        mongo_client.close()


@app.post("/client-memory/{memory_id}/rollback")
def rollback_client_memory(memory_id: str, payload: MemoryRollbackRequest) -> dict:
    """Restore a client memory to a previous version snapshot.

    The memory is restored to the given target_version snapshot state.
    A new version history entry is created to preserve the audit trail.
    The current version number is incremented (not reset).
    """
    if not is_object_id(memory_id):
        raise HTTPException(status_code=400, detail="Invalid memory_id.")
    mongo_client = get_client()
    now = utc_now()
    try:
        db = get_database(mongo_client)
        current_doc = db.client_memories.find_one({"_id": ObjectId(memory_id)})
        if not current_doc:
            raise HTTPException(status_code=404, detail=f"Client memory '{memory_id}' not found.")

        # Find the target version snapshot
        history_entry = db.memory_version_history.find_one(
            {"client_memory_id": memory_id, "version": payload.target_version}
        )
        if not history_entry:
            raise HTTPException(
                status_code=404,
                detail=f"Version {payload.target_version} not found in history for memory '{memory_id}'.",
            )

        snap = history_entry.get("snapshot") or {}

        # Snapshot the CURRENT state before overwriting
        _snapshot_memory_for_history(
            db,
            current_doc,
            change_summary=[f"rollback to v{payload.target_version}"],
            source_proposal_ids=[],
            created_by=payload.rolled_back_by or "operator",
        )

        # Fields to restore from snapshot (exclude version + timestamps — we manage those)
        restore_fields = {
            k: v for k, v in snap.items()
            if k not in ("version", "created_at", "updated_at", "workspace_slug", "client_profile_id",
                         "foundation_template_slug", "foundation_template_name")
        }
        new_version = (current_doc.get("version") or 1) + 1
        restore_fields["version"] = new_version
        restore_fields["updated_at"] = now

        db.client_memories.update_one({"_id": current_doc["_id"]}, {"$set": restore_fields})
        updated = db.client_memories.find_one({"_id": current_doc["_id"]})

        return {
            "item": serialize(updated),
            "rolled_back_from_version": current_doc.get("version", 1),
            "rolled_back_to_version": payload.target_version,
            "new_version": new_version,
            "message": f"Memory rolled back to v{payload.target_version}. Now at v{new_version}.",
        }
    finally:
        mongo_client.close()


@app.get("/memory-update-proposals/{proposal_id}/diff")
def get_proposal_diff(proposal_id: str) -> dict:
    """Return a before/after diff preview for a memory update proposal."""
    if not is_object_id(proposal_id):
        raise HTTPException(status_code=400, detail="Invalid proposal_id.")
    mongo_client = get_client()
    try:
        db = get_database(mongo_client)
        proposal = db.memory_update_proposals.find_one({"_id": ObjectId(proposal_id)})
        if not proposal:
            raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")

        change = proposal.get("proposed_change") or {}
        mem_id = proposal.get("client_memory_id", "")
        memory_doc = None
        if mem_id and is_object_id(mem_id):
            memory_doc = db.client_memories.find_one({"_id": ObjectId(mem_id)})
        if not memory_doc:
            memory_doc = db.client_memories.find_one({"workspace_slug": proposal.get("workspace_slug", "")})

        diff = _generate_memory_diff(memory_doc or {}, change)
        return {
            "proposal_id": proposal_id,
            "workspace_slug": proposal.get("workspace_slug", ""),
            "status": proposal.get("status", ""),
            "diff": diff,
        }
    finally:
        mongo_client.close()


@app.get("/memory-update-proposals/{proposal_id}/conflicts")
def get_proposal_conflicts(proposal_id: str) -> dict:
    """Detect and return conflicts for a memory update proposal."""
    if not is_object_id(proposal_id):
        raise HTTPException(status_code=400, detail="Invalid proposal_id.")
    mongo_client = get_client()
    try:
        db = get_database(mongo_client)
        proposal = db.memory_update_proposals.find_one({"_id": ObjectId(proposal_id)})
        if not proposal:
            raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")

        change = proposal.get("proposed_change") or {}
        mem_id = proposal.get("client_memory_id", "")
        memory_doc = None
        if mem_id and is_object_id(mem_id):
            memory_doc = db.client_memories.find_one({"_id": ObjectId(mem_id)})
        if not memory_doc:
            memory_doc = db.client_memories.find_one({"workspace_slug": proposal.get("workspace_slug", "")})

        conflicts = _detect_proposal_conflicts(memory_doc or {}, change)
        dup = _detect_proposal_duplicate(db, proposal.get("workspace_slug", ""), change)

        return {
            "proposal_id": proposal_id,
            "workspace_slug": proposal.get("workspace_slug", ""),
            "conflicts": conflicts,
            "conflict_count": len(conflicts),
            "has_high_severity_conflicts": any(c.get("severity") == "high" for c in conflicts),
            "duplicate": dup,
        }
    finally:
        mongo_client.close()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 6P — Operational Analytics & Learning Dashboard
# ─────────────────────────────────────────────────────────────────────────────

_BOTTLENECK_APPROVAL_STALE_HOURS = 24
_BOTTLENECK_WORKFLOW_STALE_HOURS = 48
_BOTTLENECK_QUEUE_OVERLOAD_THRESHOLD = 10


def _analytics_date_filter(days: int) -> dict:
    """Return a MongoDB filter for created_at within the last N days. 0 = all time."""
    if days <= 0:
        return {}
    cutoff = utc_now() - timedelta(days=days)
    return {"created_at": {"$gte": cutoff}}


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _avg_duration_seconds(docs: list[dict]) -> float | None:
    durations = []
    for d in docs:
        s = d.get("started_at")
        e = d.get("completed_at")
        if s and e:
            try:
                delta = (e - s).total_seconds()
                if delta >= 0:
                    durations.append(delta)
            except Exception:
                pass
    return round(sum(durations) / len(durations), 1) if durations else None


def compute_workflow_metrics(db, workspace_slug: str = "", days: int = 30) -> dict:
    """Aggregate workflow performance metrics from workflow_runs."""
    q: dict[str, Any] = {}
    if workspace_slug:
        q["workspace_slug"] = workspace_slug
    q.update(_analytics_date_filter(days))
    try:
        all_runs = list(db.workflow_runs.find(q))
    except Exception:
        all_runs = []

    total = len(all_runs)
    completed = [r for r in all_runs if r.get("status") == "completed"]
    failed = [r for r in all_runs if r.get("status") == "failed"]
    needs_review = [r for r in all_runs if r.get("status") == "needs_review"]

    by_type: dict[str, int] = {}
    for r in all_runs:
        rt = r.get("run_type") or "unknown"
        by_type[rt] = by_type.get(rt, 0) + 1

    avg_dur = _avg_duration_seconds(completed)
    memory_informed = [r for r in all_runs if r.get("client_memory_id")]

    return {
        "total_runs": total,
        "completed_runs": len(completed),
        "failed_runs": len(failed),
        "needs_review_runs": len(needs_review),
        "completion_rate": _safe_rate(len(completed), total),
        "failure_rate": _safe_rate(len(failed), total),
        "avg_duration_seconds": avg_dur,
        "memory_informed_runs": len(memory_informed),
        "memory_informed_rate": _safe_rate(len(memory_informed), total),
        "by_run_type": by_type,
        "period_days": days,
    }


def compute_memory_metrics(db, workspace_slug: str = "", days: int = 30) -> dict:
    """Aggregate memory effectiveness from proposals + client_memories."""
    q: dict[str, Any] = {}
    if workspace_slug:
        q["workspace_slug"] = workspace_slug
    q.update(_analytics_date_filter(days))
    try:
        proposals = list(db.memory_update_proposals.find(q))
    except Exception:
        proposals = []

    total = len(proposals)
    approved = [p for p in proposals if p.get("status") == "approved"]
    rejected = [p for p in proposals if p.get("status") == "rejected"]
    pending = [p for p in proposals if p.get("status") == "pending"]
    decided = len(approved) + len(rejected)

    auto_approve = [p for p in proposals if p.get("governance_suggestion") == "auto_approve"]
    auto_reject = [p for p in proposals if p.get("governance_suggestion") == "auto_reject"]
    review = [p for p in proposals if p.get("governance_suggestion") == "review"]
    duplicates = [p for p in proposals if p.get("is_duplicate")]
    conflicted = [p for p in proposals if p.get("conflicts")]

    confidences = [p.get("confidence", 0.0) for p in proposals if isinstance(p.get("confidence"), (int, float))]
    avg_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.0

    mem_q: dict[str, Any] = {}
    if workspace_slug:
        mem_q["workspace_slug"] = workspace_slug
    try:
        memories = list(db.client_memories.find(mem_q))
    except Exception:
        memories = []
    total_winning = sum(len(m.get("winning_patterns") or []) for m in memories)
    total_losing = sum(len(m.get("losing_patterns") or []) for m in memories)
    total_blocked = sum(len(m.get("blocked_claims") or []) for m in memories)

    return {
        "total_proposals": total,
        "approved_proposals": len(approved),
        "rejected_proposals": len(rejected),
        "pending_proposals": len(pending),
        "approval_rate": _safe_rate(len(approved), decided),
        "rejection_rate": _safe_rate(len(rejected), decided),
        "avg_confidence": avg_confidence,
        "governance_auto_approve_count": len(auto_approve),
        "governance_auto_reject_count": len(auto_reject),
        "governance_review_count": len(review),
        "duplicate_proposals": len(duplicates),
        "conflicted_proposals": len(conflicted),
        "total_winning_patterns": total_winning,
        "total_losing_patterns": total_losing,
        "total_blocked_claims": total_blocked,
        "memory_count": len(memories),
        "period_days": days,
    }


def compute_distribution_metrics(db, workspace_slug: str = "", days: int = 30) -> dict:
    """Distribution funnel metrics from workflow_assets."""
    q: dict[str, Any] = {}
    if workspace_slug:
        q["workspace_slug"] = workspace_slug
    q.update(_analytics_date_filter(days))
    try:
        assets = list(db.workflow_assets.find(q))
    except Exception:
        assets = []

    total = len(assets)
    published = [a for a in assets if a.get("distribution_state") == "published"]
    queued = [a for a in assets if a.get("distribution_state") == "queued"]
    archived = [a for a in assets if a.get("distribution_state") == "archived"]
    not_queued = [a for a in assets if a.get("distribution_state") in ("not_queued", None, "")]

    by_type: dict[str, int] = {}
    for a in assets:
        t = a.get("asset_type") or a.get("content_type") or "unknown"
        by_type[t] = by_type.get(t, 0) + 1

    by_channel: dict[str, int] = {}
    for a in published:
        ch = a.get("distribution_channel") or "unknown"
        by_channel[ch] = by_channel.get(ch, 0) + 1

    return {
        "total_assets": total,
        "published_count": len(published),
        "queued_count": len(queued),
        "archived_count": len(archived),
        "not_queued_count": len(not_queued),
        "publish_rate": _safe_rate(len(published), total),
        "queue_rate": _safe_rate(len(queued), total),
        "by_asset_type": by_type,
        "by_channel": by_channel,
        "period_days": days,
    }


def compute_approval_metrics(db, workspace_slug: str = "", days: int = 30) -> dict:
    """Approval funnel and latency from approval_requests."""
    q: dict[str, Any] = {}
    if workspace_slug:
        q["workspace_slug"] = workspace_slug
    q.update(_analytics_date_filter(days))
    try:
        requests_list = list(db.approval_requests.find(q))
    except Exception:
        requests_list = []

    total = len(requests_list)
    open_reqs = [r for r in requests_list if r.get("status") == "open"]
    approved = [r for r in requests_list if r.get("status") == "approved"]
    rejected = [r for r in requests_list if r.get("status") == "rejected"]
    decided = len(approved) + len(rejected)

    latencies_hours = []
    for r in approved:
        c = r.get("created_at")
        a = r.get("approved_at")
        if c and a:
            try:
                delta_h = (a - c).total_seconds() / 3600
                if delta_h >= 0:
                    latencies_hours.append(delta_h)
            except Exception:
                pass
    avg_latency_hours = round(sum(latencies_hours) / len(latencies_hours), 2) if latencies_hours else None

    by_type: dict[str, int] = {}
    for r in requests_list:
        rt = r.get("request_type") or "unknown"
        by_type[rt] = by_type.get(rt, 0) + 1

    by_module: dict[str, int] = {}
    for r in approved:
        m = r.get("module") or "unknown"
        by_module[m] = by_module.get(m, 0) + 1

    return {
        "total_requests": total,
        "open_count": len(open_reqs),
        "approved_count": len(approved),
        "rejected_count": len(rejected),
        "approval_rate": _safe_rate(len(approved), decided),
        "rejection_rate": _safe_rate(len(rejected), decided),
        "avg_approval_latency_hours": avg_latency_hours,
        "by_request_type": by_type,
        "approved_by_module": by_module,
        "period_days": days,
    }


def compute_template_metrics(db, workspace_slug: str = "", days: int = 30) -> dict:
    """Per-template (module) performance breakdown."""
    q_base: dict[str, Any] = {}
    if workspace_slug:
        q_base["workspace_slug"] = workspace_slug
    date_f = _analytics_date_filter(days)
    try:
        runs = list(db.workflow_runs.find({**q_base, **date_f}))
    except Exception:
        runs = []
    try:
        assets = list(db.workflow_assets.find({**q_base, **date_f}))
    except Exception:
        assets = []
    try:
        approvals = list(db.approval_requests.find({**q_base, **date_f}))
    except Exception:
        approvals = []
    try:
        proposals = list(db.memory_update_proposals.find({**q_base, **date_f}))
    except Exception:
        proposals = []

    modules: set[str] = set()
    for r in runs:
        if (r.get("inputs") or {}).get("module"):
            modules.add(r["inputs"]["module"])
    for a in assets:
        if a.get("module"):
            modules.add(a["module"])
    for ar in approvals:
        if ar.get("module"):
            modules.add(ar["module"])

    leaderboard: list[dict] = []
    for module in sorted(modules):
        mod_runs = [r for r in runs if (r.get("inputs") or {}).get("module") == module]
        mod_assets = [a for a in assets if a.get("module") == module]
        mod_approvals = [ar for ar in approvals if ar.get("module") == module]
        mod_proposals = [p for p in proposals if (p.get("workspace_slug") or "") == (workspace_slug or (p.get("workspace_slug") or ""))]

        completed_runs = [r for r in mod_runs if r.get("status") == "completed"]
        approved_apps = [ar for ar in mod_approvals if ar.get("status") == "approved"]
        rejected_apps = [ar for ar in mod_approvals if ar.get("status") == "rejected"]
        published_assets = [a for a in mod_assets if a.get("distribution_state") == "published"]
        decided_count = len(approved_apps) + len(rejected_apps)

        avg_conf = 0.0
        if mod_proposals:
            confs = [p.get("confidence", 0.7) for p in mod_proposals if isinstance(p.get("confidence"), (int, float))]
            avg_conf = round(sum(confs) / len(confs), 3) if confs else 0.0

        leaderboard.append({
            "module": module,
            "workflow_runs": len(mod_runs),
            "workflow_completion_rate": _safe_rate(len(completed_runs), len(mod_runs)),
            "total_assets": len(mod_assets),
            "total_approvals": len(mod_approvals),
            "approval_rate": _safe_rate(len(approved_apps), decided_count),
            "rejection_rate": _safe_rate(len(rejected_apps), decided_count),
            "distribution_completion_rate": _safe_rate(len(published_assets), len(mod_assets)),
            "avg_memory_proposal_confidence": avg_conf,
        })

    leaderboard.sort(key=lambda x: (x["approval_rate"], x["workflow_completion_rate"]), reverse=True)
    return {
        "templates": leaderboard,
        "total_modules": len(leaderboard),
        "period_days": days,
    }


def compute_client_health_metrics(db, workspace_slug: str = "", days: int = 30) -> dict:
    """Per-workspace operational health scoring."""
    if workspace_slug:
        slugs = [workspace_slug]
    else:
        try:
            ws_docs = list(db.workspaces.find({}, {"slug": 1}))
            slugs = [w.get("slug") for w in ws_docs if w.get("slug")]
        except Exception:
            slugs = []
        if not slugs:
            try:
                runs_sample = list(db.workflow_runs.find({}, {"workspace_slug": 1}).limit(500))
                slugs = list({r.get("workspace_slug") for r in runs_sample if r.get("workspace_slug")})
            except Exception:
                slugs = []

    scores: list[dict] = []
    for ws in slugs:
        wf_metrics = compute_workflow_metrics(db, ws, days)
        mem_metrics = compute_memory_metrics(db, ws, days)
        dist_metrics = compute_distribution_metrics(db, ws, days)
        app_metrics = compute_approval_metrics(db, ws, days)

        mem_health_score = 0.0
        try:
            mem_doc = db.client_memories.find_one({"workspace_slug": ws})
            if mem_doc:
                h = _compute_memory_health(db, mem_doc)
                mem_health_score = h.get("memory_health_score", 0.0)
        except Exception:
            pass

        weekly_velocity = round(wf_metrics["total_runs"] / max(days / 7, 1), 2)
        components = [
            wf_metrics["completion_rate"],
            mem_metrics["approval_rate"],
            dist_metrics["publish_rate"],
            app_metrics["approval_rate"],
            mem_health_score,
        ]
        non_zero = [c for c in components if c > 0]
        overall_score = round(sum(non_zero) / len(non_zero), 3) if non_zero else 0.0
        status = (
            "healthy" if overall_score >= 0.70 else
            "needs_attention" if overall_score >= 0.40 else
            "at_risk"
        )
        scores.append({
            "workspace_slug": ws,
            "overall_health_score": overall_score,
            "status": status,
            "workflow_velocity_per_week": weekly_velocity,
            "workflow_completion_rate": wf_metrics["completion_rate"],
            "memory_health_score": mem_health_score,
            "approval_efficiency": app_metrics["approval_rate"],
            "distribution_efficiency": dist_metrics["publish_rate"],
            "memory_proposal_approval_rate": mem_metrics["approval_rate"],
            "pending_approvals": app_metrics["open_count"],
            "total_workflow_runs": wf_metrics["total_runs"],
        })

    scores.sort(key=lambda x: x["overall_health_score"], reverse=True)
    return {
        "workspaces": scores,
        "total_workspaces": len(scores),
        "period_days": days,
    }


def compute_learning_signals(db, workspace_slug: str = "", days: int = 30) -> dict:
    """Surface top patterns, best-performing channels, tones, and change fields."""
    mem_q: dict[str, Any] = {}
    if workspace_slug:
        mem_q["workspace_slug"] = workspace_slug
    try:
        memories = list(db.client_memories.find(mem_q))
    except Exception:
        memories = []

    pattern_counts: dict[str, int] = {}
    for m in memories:
        for p in (m.get("winning_patterns") or []):
            pattern_counts[p] = pattern_counts.get(p, 0) + 1
    top_winning = sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    rejected_counts: dict[str, int] = {}
    for m in memories:
        for p in (m.get("losing_patterns") or []):
            rejected_counts[p] = rejected_counts.get(p, 0) + 1
    top_rejected = sorted(rejected_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    tone_counts: dict[str, int] = {}
    for m in memories:
        tone = (m.get("voice_tone") or {}).get("tone", "")
        if tone:
            tone_counts[tone] = tone_counts.get(tone, 0) + 1
    top_tones = sorted(tone_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    asset_q: dict[str, Any] = {"distribution_state": "published"}
    if workspace_slug:
        asset_q["workspace_slug"] = workspace_slug
    asset_q.update(_analytics_date_filter(days))
    try:
        published_assets = list(db.workflow_assets.find(asset_q))
    except Exception:
        published_assets = []

    channel_counts: dict[str, int] = {}
    for a in published_assets:
        ch = a.get("distribution_channel") or a.get("platform") or "unknown"
        channel_counts[ch] = channel_counts.get(ch, 0) + 1
    top_channels = sorted(channel_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    prop_q: dict[str, Any] = {"status": "approved"}
    if workspace_slug:
        prop_q["workspace_slug"] = workspace_slug
    prop_q.update(_analytics_date_filter(days))
    try:
        approved_props = list(db.memory_update_proposals.find(prop_q))
    except Exception:
        approved_props = []

    change_field_counts: dict[str, int] = {}
    for p in approved_props:
        f = (p.get("proposed_change") or {}).get("field", "unknown")
        change_field_counts[f] = change_field_counts.get(f, 0) + 1
    top_change_fields = sorted(change_field_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "top_winning_patterns": [{"pattern": p, "frequency": c} for p, c in top_winning],
        "top_rejected_patterns": [{"pattern": p, "frequency": c} for p, c in top_rejected],
        "top_tone_profiles": [{"tone": t, "workspace_count": c} for t, c in top_tones],
        "top_distribution_channels": [{"channel": ch, "published_count": c} for ch, c in top_channels],
        "top_approved_change_fields": [{"field": f, "approval_count": c} for f, c in top_change_fields],
        "total_memories_analyzed": len(memories),
        "period_days": days,
    }


def compute_bottlenecks(db, workspace_slug: str = "", days: int = 30) -> list[dict]:
    """Detect operational bottlenecks: stuck approvals, stale workflows, overloaded queues."""
    now = utc_now()
    bottlenecks: list[dict] = []
    q_base: dict[str, Any] = {}
    if workspace_slug:
        q_base["workspace_slug"] = workspace_slug

    stale_approval_cutoff = now - timedelta(hours=_BOTTLENECK_APPROVAL_STALE_HOURS)
    try:
        stuck_approvals = list(db.approval_requests.find({
            **q_base,
            "status": "open",
            "created_at": {"$lt": stale_approval_cutoff},
        }))
        if stuck_approvals:
            bottlenecks.append({
                "type": "stuck_approvals",
                "severity": "high" if len(stuck_approvals) > 5 else "medium",
                "count": len(stuck_approvals),
                "description": f"{len(stuck_approvals)} approval request(s) open for more than {_BOTTLENECK_APPROVAL_STALE_HOURS}h.",
                "workspace_slug": workspace_slug or "all",
                "item_ids": [str(a["_id"]) for a in stuck_approvals[:5]],
                "status": "Blocked",
            })
    except Exception:
        pass

    stale_wf_cutoff = now - timedelta(hours=_BOTTLENECK_WORKFLOW_STALE_HOURS)
    try:
        stale_wf = list(db.workflow_runs.find({
            **q_base,
            "status": "needs_review",
            "created_at": {"$lt": stale_wf_cutoff},
        }))
        if stale_wf:
            bottlenecks.append({
                "type": "stale_workflow_runs",
                "severity": "medium",
                "count": len(stale_wf),
                "description": f"{len(stale_wf)} workflow run(s) stuck in needs_review for more than {_BOTTLENECK_WORKFLOW_STALE_HOURS}h.",
                "workspace_slug": workspace_slug or "all",
                "item_ids": [str(r["_id"]) for r in stale_wf[:5]],
                "status": "Delayed",
            })
    except Exception:
        pass

    if not workspace_slug:
        try:
            ws_docs = list(db.workflow_runs.find({}, {"workspace_slug": 1}).limit(500))
            ws_set = {r.get("workspace_slug") for r in ws_docs if r.get("workspace_slug")}
            for ws in ws_set:
                open_count = db.approval_requests.count_documents({"workspace_slug": ws, "status": "open"})
                if open_count >= _BOTTLENECK_QUEUE_OVERLOAD_THRESHOLD:
                    bottlenecks.append({
                        "type": "overloaded_queue",
                        "severity": "high",
                        "count": open_count,
                        "description": f"Workspace '{ws}' has {open_count} open approval requests (threshold: {_BOTTLENECK_QUEUE_OVERLOAD_THRESHOLD}).",
                        "workspace_slug": ws,
                        "item_ids": [],
                        "status": "At Risk",
                    })
        except Exception:
            pass
    else:
        try:
            open_count = db.approval_requests.count_documents({"workspace_slug": workspace_slug, "status": "open"})
            if open_count >= _BOTTLENECK_QUEUE_OVERLOAD_THRESHOLD:
                bottlenecks.append({
                    "type": "overloaded_queue",
                    "severity": "high",
                    "count": open_count,
                    "description": f"Workspace '{workspace_slug}' has {open_count} open approval requests.",
                    "workspace_slug": workspace_slug,
                    "item_ids": [],
                    "status": "At Risk",
                })
        except Exception:
            pass

    auto_approve_stale_cutoff = now - timedelta(hours=12)
    try:
        stale_proposals = list(db.memory_update_proposals.find({
            **q_base,
            "status": "pending",
            "governance_suggestion": "auto_approve",
            "created_at": {"$lt": auto_approve_stale_cutoff},
        }))
        if stale_proposals:
            bottlenecks.append({
                "type": "unactioned_auto_approve_proposals",
                "severity": "low",
                "count": len(stale_proposals),
                "description": f"{len(stale_proposals)} memory proposal(s) suggested auto_approve but remain pending.",
                "workspace_slug": workspace_slug or "all",
                "item_ids": [str(p["_id"]) for p in stale_proposals[:5]],
                "status": "Needs Attention",
            })
    except Exception:
        pass

    bottlenecks.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("severity", "low"), 3))
    return bottlenecks


# ── Phase 6P Analytics Endpoints ──────────────────────────────────────────────

@app.get("/analytics/workflows")
def analytics_workflows(
    workspace_slug: str = Query(""),
    days: int = Query(30, ge=0, le=365),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        return compute_workflow_metrics(db, workspace_slug, days)
    finally:
        client.close()


@app.get("/analytics/memory")
def analytics_memory(
    workspace_slug: str = Query(""),
    days: int = Query(30, ge=0, le=365),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        return compute_memory_metrics(db, workspace_slug, days)
    finally:
        client.close()


@app.get("/analytics/distribution")
def analytics_distribution(
    workspace_slug: str = Query(""),
    days: int = Query(30, ge=0, le=365),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        return compute_distribution_metrics(db, workspace_slug, days)
    finally:
        client.close()


@app.get("/analytics/approvals")
def analytics_approvals(
    workspace_slug: str = Query(""),
    days: int = Query(30, ge=0, le=365),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        return compute_approval_metrics(db, workspace_slug, days)
    finally:
        client.close()


@app.get("/analytics/templates")
def analytics_templates(
    workspace_slug: str = Query(""),
    days: int = Query(30, ge=0, le=365),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        return compute_template_metrics(db, workspace_slug, days)
    finally:
        client.close()


@app.get("/analytics/client-health")
def analytics_client_health(
    workspace_slug: str = Query(""),
    days: int = Query(30, ge=0, le=365),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        return compute_client_health_metrics(db, workspace_slug, days)
    finally:
        client.close()


@app.get("/analytics/learning-signals")
def analytics_learning_signals(
    workspace_slug: str = Query(""),
    days: int = Query(30, ge=0, le=365),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        return compute_learning_signals(db, workspace_slug, days)
    finally:
        client.close()


@app.get("/analytics/bottlenecks")
def analytics_bottlenecks(
    workspace_slug: str = Query(""),
    days: int = Query(30, ge=0, le=365),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        items = compute_bottlenecks(db, workspace_slug, days)
        return {"bottlenecks": items, "total": len(items), "period_days": days}
    finally:
        client.close()


# ── Phase 6Q: Autonomous Optimization & Recommendation Engine ────────────────

import hashlib as _hashlib

_REC_WORKFLOW_MIN_COMPLETION_RATE = 0.70
_REC_WORKFLOW_MAX_AVG_DURATION_S = 300.0
_REC_MEMORY_MIN_AUTO_APPROVE_RATE = 0.50
_REC_MEMORY_MAX_PENDING = 10
_REC_TEMPLATE_MIN_APPROVAL_RATE_DIFF = 0.10
_REC_DIST_MIN_PUBLISH_RATE = 0.60
_REC_CLIENT_HEALTH_WARN_THRESHOLD = 0.50
_REC_CONFIDENCE_HIGH = 0.90
_REC_CONFIDENCE_MEDIUM = 0.70
_REC_CONFIDENCE_LOW = 0.50


def _rec_id(rec_type: str, title: str, workspace_slug: str = "") -> str:
    """Deterministic recommendation ID from type + workspace + title."""
    key = f"{rec_type}:{workspace_slug}:{title}"
    return _hashlib.md5(key.encode()).hexdigest()[:16]  # noqa: S324


def _make_recommendation(
    rec_type: str,
    title: str,
    description: str,
    confidence: float,
    impact: str,
    evidence: list,
    affected_workspaces: list,
    workspace_slug: str = "",
) -> dict:
    return {
        "id": _rec_id(rec_type, title, workspace_slug),
        "recommendation_type": rec_type,
        "title": title,
        "description": description,
        "confidence_score": round(confidence, 4),
        "impact_estimate": impact,
        "evidence": evidence,
        "affected_workspaces": affected_workspaces,
        "generated_at": utc_now().isoformat(),
        "status": "active",
    }


def generate_workflow_recommendations(db, workspace_slug: str = "", days: int = 30) -> list:
    """Derive workflow optimization recommendations from telemetry."""
    recs: list[dict] = []
    try:
        metrics = compute_workflow_metrics(db, workspace_slug, days)
    except Exception:
        return recs

    total = metrics.get("total_runs", 0)
    if total == 0:
        return recs

    ws_list = [workspace_slug] if workspace_slug else []
    completion_rate = metrics.get("completion_rate", 1.0)
    avg_dur = metrics.get("avg_duration_seconds")
    memory_rate = metrics.get("memory_informed_rate", 1.0)
    needs_review = metrics.get("needs_review_runs", 0)
    failed = metrics.get("failed_runs", 0)

    if completion_rate < _REC_WORKFLOW_MIN_COMPLETION_RATE:
        recs.append(_make_recommendation(
            rec_type="workflow_optimization",
            title="Improve Workflow Completion Rate",
            description=(
                f"Workflow completion rate is {round(completion_rate * 100, 1)}%, "
                f"below the recommended minimum of {round(_REC_WORKFLOW_MIN_COMPLETION_RATE * 100, 1)}%. "
                "Review failed runs and common failure modes."
            ),
            confidence=_REC_CONFIDENCE_HIGH,
            impact="high",
            evidence=[
                f"Completion rate: {round(completion_rate * 100, 1)}% over last {days or 'all'} days.",
                f"{failed} workflow(s) failed out of {total} total runs.",
            ],
            affected_workspaces=ws_list,
            workspace_slug=workspace_slug,
        ))

    if avg_dur is not None and avg_dur > _REC_WORKFLOW_MAX_AVG_DURATION_S:
        recs.append(_make_recommendation(
            rec_type="workflow_optimization",
            title="Reduce Average Workflow Duration",
            description=(
                f"Average workflow duration is {round(avg_dur, 1)}s, "
                f"exceeding the recommended ceiling of {_REC_WORKFLOW_MAX_AVG_DURATION_S}s. "
                "Consider splitting long-running workflows or parallelizing steps."
            ),
            confidence=_REC_CONFIDENCE_MEDIUM,
            impact="medium",
            evidence=[
                f"Average duration: {round(avg_dur, 1)}s across {total} run(s).",
            ],
            affected_workspaces=ws_list,
            workspace_slug=workspace_slug,
        ))

    if memory_rate < 0.5 and total >= 3:
        recs.append(_make_recommendation(
            rec_type="workflow_optimization",
            title="Increase Memory-Informed Workflow Coverage",
            description=(
                f"Only {round(memory_rate * 100, 1)}% of workflows use client memory context. "
                "Enabling memory-informed execution improves output quality and approval rates."
            ),
            confidence=_REC_CONFIDENCE_MEDIUM,
            impact="medium",
            evidence=[
                f"{round(memory_rate * 100, 1)}% of {total} workflow(s) were memory-informed.",
            ],
            affected_workspaces=ws_list,
            workspace_slug=workspace_slug,
        ))

    if needs_review >= 5:
        recs.append(_make_recommendation(
            rec_type="bottleneck_remediation",
            title="Clear Needs-Review Workflow Backlog",
            description=(
                f"{needs_review} workflow run(s) are in needs_review state. "
                "A growing backlog reduces throughput and blocks downstream distribution."
            ),
            confidence=_REC_CONFIDENCE_HIGH,
            impact="high",
            evidence=[f"{needs_review} run(s) stuck in needs_review state."],
            affected_workspaces=ws_list,
            workspace_slug=workspace_slug,
        ))

    return recs


def generate_memory_recommendations(db, workspace_slug: str = "", days: int = 30) -> list:
    """Derive memory refinement recommendations from proposal and memory metrics."""
    recs: list[dict] = []
    try:
        metrics = compute_memory_metrics(db, workspace_slug, days)
    except Exception:
        return recs

    ws_list = [workspace_slug] if workspace_slug else []
    total_props = metrics.get("total_proposals", 0)
    auto_approve_rate = metrics.get("approval_rate", 1.0)
    pending = metrics.get("pending_proposals", 0)
    rejection_rate = metrics.get("rejection_rate", 0.0)
    total_memories = metrics.get("memory_count", 0)

    if pending >= _REC_MEMORY_MAX_PENDING:
        recs.append(_make_recommendation(
            rec_type="memory_refinement",
            title="Action Pending Memory Update Proposals",
            description=(
                f"{pending} memory update proposal(s) are awaiting review. "
                "Unactioned proposals delay knowledge base improvements."
            ),
            confidence=_REC_CONFIDENCE_HIGH,
            impact="medium",
            evidence=[f"{pending} proposal(s) currently pending review."],
            affected_workspaces=ws_list,
            workspace_slug=workspace_slug,
        ))

    if total_props >= 5 and auto_approve_rate < _REC_MEMORY_MIN_AUTO_APPROVE_RATE:
        recs.append(_make_recommendation(
            rec_type="memory_refinement",
            title="Review Memory Governance Thresholds",
            description=(
                f"Auto-approval rate is {round(auto_approve_rate * 100, 1)}%, "
                "suggesting confidence thresholds may be too conservative. "
                "Consider adjusting to reduce manual review load."
            ),
            confidence=_REC_CONFIDENCE_MEDIUM,
            impact="medium",
            evidence=[
                f"Approval rate: {round(auto_approve_rate * 100, 1)}% across {total_props} proposal(s).",
            ],
            affected_workspaces=ws_list,
            workspace_slug=workspace_slug,
        ))

    if total_props >= 5 and rejection_rate > 0.40:
        recs.append(_make_recommendation(
            rec_type="memory_refinement",
            title="Investigate High Memory Proposal Rejection Rate",
            description=(
                f"{round(rejection_rate * 100, 1)}% of memory proposals are being rejected. "
                "High rejection rates suggest agent extraction quality issues or misaligned scoring rules."
            ),
            confidence=_REC_CONFIDENCE_MEDIUM,
            impact="high",
            evidence=[
                f"Rejection rate: {round(rejection_rate * 100, 1)}% across {total_props} proposal(s).",
            ],
            affected_workspaces=ws_list,
            workspace_slug=workspace_slug,
        ))

    if total_memories == 0 and total_props == 0:
        recs.append(_make_recommendation(
            rec_type="memory_refinement",
            title="Initialize Client Memory Coverage",
            description=(
                "No client memory records or update proposals have been created. "
                "Initializing memory enables personalized, context-aware workflow execution."
            ),
            confidence=_REC_CONFIDENCE_LOW,
            impact="medium",
            evidence=["No client memory entries or proposals found."],
            affected_workspaces=ws_list,
            workspace_slug=workspace_slug,
        ))

    return recs


def generate_template_recommendations(db, workspace_slug: str = "", days: int = 30) -> list:
    """Compare template performance and surface adaptation opportunities."""
    recs: list[dict] = []
    try:
        metrics = compute_template_metrics(db, workspace_slug, days)
    except Exception:
        return recs

    templates = metrics.get("templates", [])
    ws_list = [workspace_slug] if workspace_slug else []

    if len(templates) < 2:
        return recs

    ranked = sorted(templates, key=lambda t: t.get("approval_rate", 0.0), reverse=True)
    best = ranked[0]
    worst = ranked[-1]
    best_rate = best.get("approval_rate", 0.0)
    worst_rate = worst.get("approval_rate", 0.0)
    diff = best_rate - worst_rate

    if diff >= _REC_TEMPLATE_MIN_APPROVAL_RATE_DIFF and worst.get("workflow_runs", 0) >= 2:
        recs.append(_make_recommendation(
            rec_type="template_adaptation",
            title=f"Promote {best['module']} Template Patterns",
            description=(
                f"The '{best['module']}' template achieves a {round(best_rate * 100, 1)}% approval rate, "
                f"{round(diff * 100, 1)}% higher than '{worst['module']}' ({round(worst_rate * 100, 1)}%). "
                "Consider applying patterns from the higher-performing template."
            ),
            confidence=_REC_CONFIDENCE_MEDIUM,
            impact="medium",
            evidence=[
                f"'{best['module']}' approval rate: {round(best_rate * 100, 1)}%.",
                f"'{worst['module']}' approval rate: {round(worst_rate * 100, 1)}%.",
                f"Performance gap: {round(diff * 100, 1)} percentage points.",
            ],
            affected_workspaces=ws_list,
            workspace_slug=workspace_slug,
        ))

    underutilized = [
        t for t in templates
        if t.get("workflow_runs", 0) <= 1 and t.get("approval_rate", 0.0) == 0.0
    ]
    for tmpl in underutilized[:2]:
        recs.append(_make_recommendation(
            rec_type="template_adaptation",
            title=f"Activate or Archive Underutilized Template: {tmpl['module']}",
            description=(
                f"Template '{tmpl['module']}' has {tmpl.get('workflow_runs', 0)} run(s) and 0% approval rate. "
                "Consider activating it for a test run or archiving to reduce noise."
            ),
            confidence=_REC_CONFIDENCE_LOW,
            impact="low",
            evidence=[
                f"'{tmpl['module']}': {tmpl.get('workflow_runs', 0)} run(s), "
                f"{round(tmpl.get('approval_rate', 0.0) * 100, 1)}% approval rate.",
            ],
            affected_workspaces=ws_list,
            workspace_slug=workspace_slug,
        ))

    return recs


def generate_distribution_recommendations(db, workspace_slug: str = "", days: int = 30) -> list:
    """Derive distribution pipeline recommendations from asset funnel metrics."""
    recs: list[dict] = []
    try:
        metrics = compute_distribution_metrics(db, workspace_slug, days)
    except Exception:
        return recs

    ws_list = [workspace_slug] if workspace_slug else []
    total = metrics.get("total_assets", 0)
    publish_rate = metrics.get("publish_rate", 1.0)
    channel_breakdown = metrics.get("by_channel", {})

    if total == 0:
        return recs

    if publish_rate < _REC_DIST_MIN_PUBLISH_RATE:
        recs.append(_make_recommendation(
            rec_type="distribution_timing",
            title="Improve Distribution Pipeline Publish Rate",
            description=(
                f"Distribution publish rate is {round(publish_rate * 100, 1)}%, "
                f"below the recommended minimum of {round(_REC_DIST_MIN_PUBLISH_RATE * 100, 1)}%. "
                "Review blocked or pending assets and resolve downstream blockers."
            ),
            confidence=_REC_CONFIDENCE_HIGH,
            impact="high",
            evidence=[
                f"Publish rate: {round(publish_rate * 100, 1)}% across {total} asset(s).",
            ],
            affected_workspaces=ws_list,
            workspace_slug=workspace_slug,
        ))

    if len(channel_breakdown) >= 2:
        sorted_channels = sorted(channel_breakdown.items(), key=lambda x: x[1], reverse=True)
        top_ch, top_cnt = sorted_channels[0]
        bot_ch, bot_cnt = sorted_channels[-1]
        if bot_cnt > 0:
            ratio = round(top_cnt / bot_cnt, 1)
            if ratio >= 2.0:
                recs.append(_make_recommendation(
                    rec_type="distribution_timing",
                    title=f"Prioritize {top_ch.title()} Distribution Channel",
                    description=(
                        f"'{top_ch}' produces {ratio}x more distributed assets than '{bot_ch}'. "
                        "Consider reallocating production capacity toward the higher-performing channel."
                    ),
                    confidence=_REC_CONFIDENCE_MEDIUM,
                    impact="medium",
                    evidence=[
                        f"'{top_ch}': {top_cnt} asset(s) distributed.",
                        f"'{bot_ch}': {bot_cnt} asset(s) distributed.",
                        f"Performance ratio: {ratio}x.",
                    ],
                    affected_workspaces=ws_list,
                    workspace_slug=workspace_slug,
                ))

    return recs


def generate_operational_recommendations(db, workspace_slug: str = "", days: int = 30) -> list:
    """Generate bottleneck remediation and client health warning recommendations."""
    recs: list[dict] = []
    ws_list = [workspace_slug] if workspace_slug else []

    try:
        bottlenecks = compute_bottlenecks(db, workspace_slug, days)
        for bn in bottlenecks:
            severity = bn.get("severity", "low")
            impact = "high" if severity == "high" else "medium"
            bn_ws = bn.get("workspace_slug") or workspace_slug
            affected = [bn_ws] if bn_ws and bn_ws != "all" else ws_list
            recs.append(_make_recommendation(
                rec_type="bottleneck_remediation",
                title=f"Resolve Bottleneck: {bn.get('type', 'unknown').replace('_', ' ').title()}",
                description=bn.get("description", ""),
                confidence=_REC_CONFIDENCE_HIGH if severity == "high" else _REC_CONFIDENCE_MEDIUM,
                impact=impact,
                evidence=[bn.get("description", "")],
                affected_workspaces=affected,
                workspace_slug=workspace_slug,
            ))
    except Exception:
        pass

    try:
        health_metrics = compute_client_health_metrics(db, workspace_slug, days)
        for ws_data in health_metrics.get("workspaces", []):
            score = ws_data.get("overall_health_score", 1.0)
            if score < _REC_CLIENT_HEALTH_WARN_THRESHOLD:
                ws = ws_data.get("workspace_slug", workspace_slug)
                recs.append(_make_recommendation(
                    rec_type="client_health_warning",
                    title=f"Client Health Alert: {ws}",
                    description=(
                        f"Workspace '{ws}' has a health score of {round(score, 2)}, "
                        f"below the warning threshold of {_REC_CLIENT_HEALTH_WARN_THRESHOLD}. "
                        "Review workflow completion, approval rates, and memory quality."
                    ),
                    confidence=_REC_CONFIDENCE_HIGH,
                    impact="high",
                    evidence=[
                        f"Health score: {round(score, 2)} (threshold: {_REC_CLIENT_HEALTH_WARN_THRESHOLD}).",
                        f"Workflow completion: {round(ws_data.get('workflow_completion_rate', 0.0) * 100, 1)}%.",
                        f"Approval efficiency: {round(ws_data.get('approval_efficiency', 0.0) * 100, 1)}%.",
                    ],
                    affected_workspaces=[ws],
                    workspace_slug=workspace_slug,
                ))
    except Exception:
        pass

    return recs


def generate_cross_client_signals(db, days: int = 30) -> dict:
    """Aggregate anonymized intelligence across all workspaces."""
    date_f = _analytics_date_filter(days)

    try:
        prop_q: dict[str, Any] = {"status": "approved", "extracted_patterns": {"$exists": True}}
        prop_q.update(date_f)
        approved_props = list(db.memory_update_proposals.find(prop_q))
    except Exception:
        approved_props = []

    pattern_counts: dict[str, int] = {}
    for p in approved_props:
        for pat in (p.get("extracted_patterns") or []):
            key = str(pat)
            pattern_counts[key] = pattern_counts.get(key, 0) + 1
    top_patterns = sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    try:
        tmpl_metrics = compute_template_metrics(db, workspace_slug="", days=days)
        global_templates = sorted(
            tmpl_metrics.get("templates", []),
            key=lambda t: t.get("approval_rate", 0.0),
            reverse=True,
        )[:5]
    except Exception:
        global_templates = []

    try:
        dist_metrics = compute_distribution_metrics(db, workspace_slug="", days=days)
        top_channels = sorted(
            dist_metrics.get("by_channel", {}).items(),
            key=lambda x: x[1],
            reverse=True,
        )[:5]
    except Exception:
        top_channels = []

    try:
        run_q: dict[str, Any] = {}
        run_q.update(date_f)
        all_runs = list(db.workflow_runs.find(run_q))
        active_workspaces = len({r.get("workspace_slug") for r in all_runs if r.get("workspace_slug")})
    except Exception:
        active_workspaces = 0

    try:
        all_bottlenecks = compute_bottlenecks(db, workspace_slug="", days=days)
        bn_type_counts: dict[str, int] = {}
        for bn in all_bottlenecks:
            t = bn.get("type", "unknown")
            bn_type_counts[t] = bn_type_counts.get(t, 0) + 1
        common_bottlenecks = sorted(bn_type_counts.items(), key=lambda x: x[1], reverse=True)
    except Exception:
        common_bottlenecks = []

    return {
        "period_days": days,
        "active_workspaces": active_workspaces,
        "top_winning_patterns": [{"pattern": p, "frequency": c} for p, c in top_patterns],
        "best_performing_templates": global_templates,
        "top_channels": [{"channel": ch, "count": c} for ch, c in top_channels],
        "common_bottlenecks": [{"type": t, "count": c} for t, c in common_bottlenecks],
        "generated_at": utc_now().isoformat(),
    }


def _collect_all_recommendations(db, workspace_slug: str = "", days: int = 30) -> list:
    """Collect and deduplicate recommendations from all generators, merging persisted statuses."""
    recs: list[dict] = []
    for generator in [
        generate_workflow_recommendations,
        generate_memory_recommendations,
        generate_template_recommendations,
        generate_distribution_recommendations,
        generate_operational_recommendations,
    ]:
        try:
            recs.extend(generator(db, workspace_slug, days))
        except Exception:
            pass

    seen: dict[str, dict] = {}
    for r in recs:
        seen[r["id"]] = r
    recs = list(seen.values())

    rec_ids = [r["id"] for r in recs]
    try:
        overrides = {
            o["rec_id"]: o
            for o in db.recommendation_statuses.find({"rec_id": {"$in": rec_ids}})
        }
    except Exception:
        overrides = {}

    for r in recs:
        override = overrides.get(r["id"])
        if override:
            r["status"] = override.get("status", r["status"])
            r["updated_at"] = override.get("updated_at", r.get("generated_at"))

    return recs


def _update_recommendation_status(rec_id: str, new_status: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        now = utc_now()
        db.recommendation_statuses.update_one(
            {"rec_id": rec_id},
            {"$set": {"rec_id": rec_id, "status": new_status, "updated_at": now}},
            upsert=True,
        )
        return {"rec_id": rec_id, "status": new_status, "updated_at": now.isoformat()}
    finally:
        client.close()


# ── Phase 6Q Endpoints ────────────────────────────────────────────────────────

@app.get("/recommendations")
def list_recommendations(
    workspace_slug: str = Query(""),
    days: int = Query(30, ge=0, le=365),
    status: str = Query(""),
    rec_type: str = Query(""),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        recs = _collect_all_recommendations(db, workspace_slug, days)
        if status:
            recs = [r for r in recs if r.get("status") == status]
        if rec_type:
            recs = [r for r in recs if r.get("recommendation_type") == rec_type]
        _impact_order = {"high": 0, "medium": 1, "low": 2}
        recs.sort(key=lambda r: (_impact_order.get(r.get("impact_estimate", "low"), 2), -r.get("confidence_score", 0.0)))
        return {"recommendations": recs, "total": len(recs), "period_days": days}
    finally:
        client.close()


@app.get("/recommendations/summary")
def recommendations_summary(
    workspace_slug: str = Query(""),
    days: int = Query(30, ge=0, le=365),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        recs = _collect_all_recommendations(db, workspace_slug, days)
        active = [r for r in recs if r.get("status") == "active"]
        high_impact = [r for r in active if r.get("impact_estimate") == "high"]
        by_type: dict[str, int] = {}
        for r in recs:
            t = r.get("recommendation_type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "total": len(recs),
            "active": len(active),
            "high_impact": len(high_impact),
            "by_type": by_type,
            "period_days": days,
        }
    finally:
        client.close()


@app.get("/recommendations/cross-client-signals")
def recommendations_cross_client_signals(
    days: int = Query(30, ge=0, le=365),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        return generate_cross_client_signals(db, days)
    finally:
        client.close()


@app.get("/recommendations/{rec_id}")
def get_recommendation(
    rec_id: str,
    workspace_slug: str = Query(""),
    days: int = Query(30, ge=0, le=365),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        recs = _collect_all_recommendations(db, workspace_slug, days)
        rec = next((r for r in recs if r["id"] == rec_id), None)
        if rec is None:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        return rec
    finally:
        client.close()


@app.post("/recommendations/{rec_id}/accept")
def accept_recommendation(rec_id: str) -> dict:
    return _update_recommendation_status(rec_id, "accepted")


@app.post("/recommendations/{rec_id}/dismiss")
def dismiss_recommendation(rec_id: str) -> dict:
    return _update_recommendation_status(rec_id, "dismissed")


@app.post("/recommendations/{rec_id}/apply")
def apply_recommendation(rec_id: str) -> dict:
    return _update_recommendation_status(rec_id, "applied")


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 6R — Autonomous Execution Policies & Safe Auto-Optimization
# ─────────────────────────────────────────────────────────────────────────────

import uuid as _uuid_6r

# ── Constants ──────────────────────────────────────────────────────────────────

_RISK_LEVELS: dict[str, int] = {"low": 0, "medium": 1, "high": 2}

_ACTION_META: dict[str, dict] = {
    "auto_archive_stale_workflows":          {"risk_level": "low",    "rollback_supported": True},
    "auto_promote_high_confidence_patterns": {"risk_level": "medium", "rollback_supported": True},
    "auto_merge_duplicate_memory_entries":   {"risk_level": "low",    "rollback_supported": True},
    "auto_adjust_template_priority":         {"risk_level": "low",    "rollback_supported": True},
    "auto_prioritize_distribution_channel":  {"risk_level": "low",    "rollback_supported": True},
    "auto_archive_low_quality_proposals":    {"risk_level": "low",    "rollback_supported": True},
    "auto_escalate_bottlenecks":             {"risk_level": "medium", "rollback_supported": False},
    "auto_recommend_template_switch":        {"risk_level": "medium", "rollback_supported": True},
}

_SAFETY_BLOCKED_ACTIONS: set[str] = {
    "blocked_claim_changes",
    "legal_compliance_memory",
    "delete_workflow_history",
    "mutate_immutable_lineage",
}

_DEFAULT_GLOBAL_POLICY: dict = {
    "workspace_slug": "__global__",
    "autonomy_enabled": True,
    "max_autonomy_risk": "low",
    "auto_apply_threshold": 0.90,
    "require_review_for": ["template_adaptation", "blocked_claim_changes"],
    "auto_archive_days": 30,
}

_AUTO_MIN_CONFIDENCE: float = 0.90
_AUTO_MIN_EVIDENCE: int = 3

# ── Helper Functions ────────────────────────────────────────────────────────────


def _is_autonomy_paused(db) -> bool:
    doc = db.autonomy_state.find_one({"_id": "global"})
    return bool(doc and doc.get("paused", False))


def _get_effective_policy(workspace_slug: str, db) -> dict:
    """Return workspace policy merged on top of global policy defaults."""
    global_doc = db.autonomy_policies.find_one({"workspace_slug": "__global__"}) or {}
    policy: dict = {
        **_DEFAULT_GLOBAL_POLICY,
        **{k: v for k, v in global_doc.items() if k != "_id"},
    }
    if workspace_slug and workspace_slug != "__global__":
        ws_doc = db.autonomy_policies.find_one({"workspace_slug": workspace_slug}) or {}
        policy.update({k: v for k, v in ws_doc.items() if k != "_id"})
    return policy


def evaluate_autonomy_policy(
    action_type: str,
    confidence_score: float,
    evidence_count: int,
    workspace_slug: str,
    db,
) -> dict:
    """Evaluate whether an action is permitted under current policies.

    Returns dict with keys: allowed, requires_review, reason, policy.
    """
    # 1. Global pause check
    if _is_autonomy_paused(db):
        return {
            "allowed": False,
            "requires_review": False,
            "reason": "autonomy_paused",
            "policy": _DEFAULT_GLOBAL_POLICY,
        }

    policy = _get_effective_policy(workspace_slug, db)

    # 2. Autonomy disabled
    if not policy.get("autonomy_enabled", True):
        return {
            "allowed": False,
            "requires_review": False,
            "reason": "autonomy_disabled",
            "policy": policy,
        }

    # 3. Safety guardrails — hard block, no operator override
    if action_type in _SAFETY_BLOCKED_ACTIONS:
        return {
            "allowed": False,
            "requires_review": False,
            "reason": "safety_guardrail",
            "policy": policy,
        }

    requires_review = False
    reason = "auto_apply"

    # 4. Risk level check
    meta = _ACTION_META.get(action_type, {"risk_level": "high", "rollback_supported": False})
    action_risk = _RISK_LEVELS.get(meta["risk_level"], 2)
    max_risk = _RISK_LEVELS.get(policy.get("max_autonomy_risk", "low"), 0)
    if action_risk > max_risk:
        requires_review = True
        reason = "risk_exceeds_policy"

    # 5. Explicitly listed for operator review
    if action_type in policy.get("require_review_for", []):
        requires_review = True
        reason = "policy_requires_review"

    # 6. Confidence threshold
    threshold = float(policy.get("auto_apply_threshold", _AUTO_MIN_CONFIDENCE))
    if confidence_score < threshold:
        requires_review = True
        reason = "confidence_below_threshold"

    # 7. Minimum evidence count
    if evidence_count < _AUTO_MIN_EVIDENCE:
        requires_review = True
        reason = "insufficient_evidence"

    return {
        "allowed": True,
        "requires_review": requires_review,
        "reason": reason,
        "policy": policy,
    }


def simulate_autonomy_action(
    action_type: str,
    workspace_slug: str,
    params: dict,
    db,
) -> dict:
    """Generate a simulation/diff preview before applying an autonomous action."""
    meta = _ACTION_META.get(action_type, {"risk_level": "unknown", "rollback_supported": False})

    _change_map: dict[str, list[str]] = {
        "auto_archive_stale_workflows": [
            f"Archive workflows inactive for >{params.get('days', 30)} days",
        ],
        "auto_promote_high_confidence_patterns": [
            "Promote pattern to approved status",
            "Increase template confidence score",
        ],
        "auto_merge_duplicate_memory_entries": [
            "Merge duplicate memory entries",
            f"Remove {params.get('duplicate_count', 1)} redundant entries",
        ],
        "auto_adjust_template_priority": [
            f"Adjust template priority from {params.get('old_priority', 'medium')} to {params.get('new_priority', 'high')}",
        ],
        "auto_prioritize_distribution_channel": [
            f"Set channel '{params.get('channel', 'unknown')}' as primary",
        ],
        "auto_archive_low_quality_proposals": [
            f"Archive {params.get('proposal_count', 0)} low-quality proposals",
        ],
        "auto_escalate_bottlenecks": [
            "Flag bottleneck for operator review",
            "Create escalation record",
        ],
        "auto_recommend_template_switch": [
            f"Switch template from '{params.get('current_template', '?')}' to '{params.get('target_template', '?')}'",
        ],
    }
    changes = _change_map.get(action_type, ["Apply change"])

    rollback_complexity: str
    if not meta["rollback_supported"]:
        rollback_complexity = "none"
    elif meta["risk_level"] == "low":
        rollback_complexity = "simple"
    else:
        rollback_complexity = "moderate"

    return {
        "action_type": action_type,
        "workspace_slug": workspace_slug,
        "expected_changes": changes,
        "impact_summary": "This change would: " + "; ".join(changes),
        "conflict_detected": False,
        "rollback_complexity": rollback_complexity,
        "rollback_supported": meta["rollback_supported"],
        "risk_level": meta["risk_level"],
        "estimated_confidence_gain": params.get("estimated_confidence_gain", 0.0),
        "params": params,
    }


def _new_action_id() -> str:
    return _uuid_6r.uuid4().hex[:16]


def _now_6r() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_autonomy_analytics(db, workspace_slug: str = "", days: int = 30) -> dict:
    query: dict = {}
    if workspace_slug:
        query["workspace_slug"] = workspace_slug
    if days > 0:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        query["created_at"] = {"$gte": since}

    actions = list(db.autonomy_action_logs.find(query, {"_id": 0}))
    total = len(actions)
    applied = sum(1 for a in actions if a.get("status") in ("applied", "auto_applied"))
    rolled_back = sum(1 for a in actions if a.get("status") == "rolled_back")
    blocked = sum(1 for a in actions if a.get("status") in ("blocked", "auto_blocked"))
    pending = sum(1 for a in actions if a.get("status") == "pending")
    overridden = sum(1 for a in actions if a.get("status") == "operator_overridden")

    auto_apply_success_rate = round(applied / total, 4) if total > 0 else 0.0
    rollback_rate = round(rolled_back / applied, 4) if applied > 0 else 0.0
    operator_override_rate = round(overridden / total, 4) if total > 0 else 0.0

    by_type: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    for a in actions:
        t = a.get("action_type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
        r = a.get("risk_level", "unknown")
        by_risk[r] = by_risk.get(r, 0) + 1

    return {
        "total_actions": total,
        "applied_actions": applied,
        "rolled_back_actions": rolled_back,
        "blocked_actions": blocked,
        "pending_actions": pending,
        "operator_override_count": overridden,
        "auto_apply_success_rate": auto_apply_success_rate,
        "rollback_rate": rollback_rate,
        "operator_override_rate": operator_override_rate,
        "by_action_type": by_type,
        "by_risk_level": by_risk,
        "autonomy_paused": _is_autonomy_paused(db),
        "days": days,
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────


@app.get("/autonomy/policies")
def get_autonomy_policies(workspace_slug: str = Query("")) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        policies: list[dict] = []
        effective_global = _get_effective_policy("", db)
        policies.append(effective_global)
        if workspace_slug:
            ws_policy = _get_effective_policy(workspace_slug, db)
            ws_policy["workspace_slug"] = workspace_slug
            if ws_policy != effective_global:
                policies.append(ws_policy)
        else:
            for doc in db.autonomy_policies.find(
                {"workspace_slug": {"$ne": "__global__"}}, {"_id": 0}
            ):
                policies.append(dict(doc))
        paused = _is_autonomy_paused(db)
        return {"policies": policies, "autonomy_paused": paused}
    finally:
        client.close()


@app.patch("/autonomy/policies/{workspace}")
def update_autonomy_policy(workspace: str, payload: dict) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        update = {k: v for k, v in payload.items() if k not in ("_id", "workspace_slug")}
        update["workspace_slug"] = workspace
        update["updated_at"] = _now_6r()
        db.autonomy_policies.update_one(
            {"workspace_slug": workspace},
            {"$set": update},
            upsert=True,
        )
        effective = _get_effective_policy(
            workspace if workspace != "__global__" else "", db
        )
        return {"policy": effective, "workspace": workspace}
    finally:
        client.close()


@app.get("/autonomy/actions")
def list_autonomy_actions(
    workspace_slug: str = Query(""),
    status: str = Query(""),
    action_type: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict = {}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        if status:
            query["status"] = status
        if action_type:
            query["action_type"] = action_type
        actions = list(
            db.autonomy_action_logs.find(query, {"_id": 0})
            .sort("created_at", -1)
            .limit(limit)
        )
        return {"actions": actions, "total": len(actions)}
    finally:
        client.close()


@app.get("/autonomy/actions/{action_id}")
def get_autonomy_action(action_id: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        doc = db.autonomy_action_logs.find_one({"id": action_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Action not found")
        return dict(doc)
    finally:
        client.close()


@app.post("/autonomy/actions/{action_id}/rollback")
def rollback_autonomy_action(action_id: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        doc = db.autonomy_action_logs.find_one({"id": action_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Action not found")
        if doc.get("status") not in ("applied", "auto_applied"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot rollback action with status '{doc.get('status')}'",
            )
        meta = _ACTION_META.get(doc.get("action_type", ""), {"rollback_supported": False})
        if not meta.get("rollback_supported", False):
            raise HTTPException(
                status_code=400, detail="Action type does not support rollback"
            )
        db.autonomy_action_logs.update_one(
            {"id": action_id},
            {"$set": {"status": "rolled_back", "rolled_back_at": _now_6r()}},
        )
        return {"action_id": action_id, "status": "rolled_back"}
    finally:
        client.close()


@app.post("/autonomy/pause")
def pause_autonomy() -> dict:
    client = get_client()
    try:
        db = get_database(client)
        db.autonomy_state.update_one(
            {"_id": "global"},
            {"$set": {"paused": True, "paused_at": _now_6r()}},
            upsert=True,
        )
        return {"autonomy_paused": True}
    finally:
        client.close()


@app.post("/autonomy/resume")
def resume_autonomy() -> dict:
    client = get_client()
    try:
        db = get_database(client)
        db.autonomy_state.update_one(
            {"_id": "global"},
            {"$set": {"paused": False, "resumed_at": _now_6r()}},
            upsert=True,
        )
        return {"autonomy_paused": False}
    finally:
        client.close()


@app.get("/autonomy/analytics")
def get_autonomy_analytics(
    workspace_slug: str = Query(""),
    days: int = Query(30, ge=0, le=365),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        return _compute_autonomy_analytics(db, workspace_slug, days)
    finally:
        client.close()



# =============================================================================
# PHASE 6T — Multi-Agent Coordination & Autonomous Workflow Orchestration
# =============================================================================

import uuid as _uuid_6t

# ── Constants ─────────────────────────────────────────────────────────────────

_AGENT_NAMES_6T: set[str] = {
    "discovery", "content_build", "approval",
    "distribution", "recommendation", "optimization",
}

_NODE_STATUSES_6T: set[str] = {
    "pending", "ready", "running", "blocked",
    "failed", "retrying", "completed", "escalated",
}

_ORCH_STATUSES_6T: set[str] = {
    "pending", "running", "paused", "completed", "failed", "escalated",
}

_PRIORITY_LEVELS_6T: dict[str, int] = {
    "critical": 3, "high": 2, "normal": 1, "background": 0,
}

_DEFAULT_AGENT_PROFILES_6T: dict[str, dict] = {
    "discovery": {
        "agent_name": "discovery",
        "specializations": ["audience_analysis", "trend_detection", "content_gap_analysis"],
        "success_rate": 0.91,
        "avg_execution_time": 8.5,
        "preferred_templates": ["media_growth", "artist_growth"],
        "max_concurrency": 3,
    },
    "content_build": {
        "agent_name": "content_build",
        "specializations": ["linkedin_posts", "short_form", "founder_content", "visual_scripts"],
        "success_rate": 0.88,
        "avg_execution_time": 14.2,
        "preferred_templates": ["media_growth", "founder_thought_leadership"],
        "max_concurrency": 5,
    },
    "approval": {
        "agent_name": "approval",
        "specializations": ["compliance_review", "brand_voice_validation", "claim_verification"],
        "success_rate": 0.95,
        "avg_execution_time": 3.1,
        "preferred_templates": ["insurance_growth", "investor_outreach"],
        "max_concurrency": 10,
    },
    "distribution": {
        "agent_name": "distribution",
        "specializations": ["multi_channel", "scheduling", "platform_optimization"],
        "success_rate": 0.93,
        "avg_execution_time": 5.7,
        "preferred_templates": ["media_growth", "local_services"],
        "max_concurrency": 8,
    },
    "recommendation": {
        "agent_name": "recommendation",
        "specializations": ["pattern_learning", "template_optimization", "workflow_improvement"],
        "success_rate": 0.87,
        "avg_execution_time": 6.3,
        "preferred_templates": [],
        "max_concurrency": 4,
    },
    "optimization": {
        "agent_name": "optimization",
        "specializations": ["autonomy_tuning", "memory_refinement", "distribution_optimization"],
        "success_rate": 0.84,
        "avg_execution_time": 11.8,
        "preferred_templates": [],
        "max_concurrency": 2,
    },
}

# ── Utility helpers ──────────────────────────────────────────────────────────


def _now_6t() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_orch_id() -> str:
    return _uuid_6t.uuid4().hex[:16]


def _new_node_id() -> str:
    return _uuid_6t.uuid4().hex[:8]


# ── Pydantic Models ───────────────────────────────────────────────────────────


class OrchestrationCreateRequest(BaseModel):
    workspace_slug: str
    workflow_run_id: str = ""
    priority: Literal["critical", "high", "normal", "background"] = "normal"
    agent_chain: list[str]
    config: Optional[dict] = None


class RetryNodeRequest(BaseModel):
    node_id: str
    recovery_strategy: str = ""


class EscalateOrchestrationRequest(BaseModel):
    node_id: str = ""
    reason: str = ""


# ── Core Orchestration Logic ──────────────────────────────────────────────────


def evaluate_agent_dependencies(nodes: list[dict]) -> list[str]:
    """Return node_ids of *pending* nodes whose dependencies are all completed."""
    completed_ids = {n["node_id"] for n in nodes if n.get("status") == "completed"}
    ready: list[str] = []
    for node in nodes:
        if node.get("status") != "pending":
            continue
        deps = node.get("depends_on") or []
        if all(dep in completed_ids for dep in deps):
            ready.append(node["node_id"])
    return ready


def schedule_next_agent_tasks(orch_id: str, db) -> list[str]:
    """Promote pending → ready for nodes whose dependencies are satisfied."""
    orch = db.orchestrations.find_one({"orchestration_id": orch_id})
    if not orch:
        return []
    nodes = orch.get("nodes") or []
    ready_ids = evaluate_agent_dependencies(nodes)
    if not ready_ids:
        return []
    for n in nodes:
        if n["node_id"] in ready_ids:
            n["status"] = "ready"
    db.orchestrations.update_one(
        {"orchestration_id": orch_id},
        {"$set": {"nodes": nodes, "updated_at": _now_6t()}},
    )
    return ready_ids


def create_orchestration_plan(
    workspace_slug: str,
    workflow_run_id: str,
    agent_chain: list[str],
    db,
    priority: str = "normal",
    config: Optional[dict] = None,
) -> dict:
    """Create and persist an orchestration plan from a linear agent chain.

    Builds nodes sequentially — node N+1 depends on node N.
    The first node is immediately set to *ready*; all others are *pending*.
    """
    config = config or {}
    now = _now_6t()
    orch_id = _new_orch_id()
    nodes: list[dict] = []
    edges: list[dict] = []
    prev_node_id: Optional[str] = None

    for i, agent_name in enumerate(agent_chain):
        node_id = _new_node_id()
        node: dict = {
            "node_id": node_id,
            "agent_name": agent_name,
            "label": f"{agent_name.replace('_', ' ').title()} (step {i + 1})",
            "status": "ready" if i == 0 else "pending",
            "depends_on": [prev_node_id] if prev_node_id else [],
            "retry_count": 0,
            "max_retries": int(config.get("max_retries", 3)),
            "failure_reason": None,
            "recovery_strategy": None,
            "execution_metadata": config.get(agent_name) or {},
            "started_at": None,
            "completed_at": None,
        }
        nodes.append(node)
        if prev_node_id:
            edges.append({"from": prev_node_id, "to": node_id})
        prev_node_id = node_id

    doc: dict = {
        "orchestration_id": orch_id,
        "workspace_slug": workspace_slug,
        "workflow_run_id": workflow_run_id,
        "status": "running" if nodes else "completed",
        "priority": priority if priority in _PRIORITY_LEVELS_6T else "normal",
        "nodes": nodes,
        "edges": edges,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "failure_reason": None,
        "escalation_status": None,
        "delegation_count": 0,
        "retry_total": 0,
    }

    result = db.orchestrations.insert_one(doc)
    created = db.orchestrations.find_one({"_id": result.inserted_id})
    return created or doc


def execute_orchestration_graph(orch_id: str, db) -> dict:
    """Advance the graph by transitioning all *ready* nodes to *running*."""
    orch = db.orchestrations.find_one({"orchestration_id": orch_id})
    if not orch:
        return {"error": "not_found"}
    if orch.get("status") in ("paused", "completed", "failed"):
        return {"error": f"cannot_execute: status={orch.get('status')}"}

    nodes = orch.get("nodes") or []
    now = _now_6t()
    started: list[str] = []
    for n in nodes:
        if n.get("status") == "ready":
            n["status"] = "running"
            n["started_at"] = now
            started.append(n["node_id"])

    if started:
        db.orchestrations.update_one(
            {"orchestration_id": orch_id},
            {"$set": {"nodes": nodes, "updated_at": now}},
        )

    return {
        "orchestration_id": orch_id,
        "nodes_started": started,
        "total_started": len(started),
    }


def handle_agent_failure(
    orch_id: str,
    node_id: str,
    failure_reason: str,
    db,
    recovery_strategy: str = "",
) -> dict:
    """Handle a failed node: retry if under max_retries, escalate otherwise."""
    orch = db.orchestrations.find_one({"orchestration_id": orch_id})
    if not orch:
        return {"error": "not_found"}
    nodes = orch.get("nodes") or []
    target = next((n for n in nodes if n["node_id"] == node_id), None)
    if not target:
        return {"error": "node_not_found"}

    retry_count = target.get("retry_count", 0) + 1
    max_retries = target.get("max_retries", 3)

    if retry_count <= max_retries:
        new_status = "retrying"
        recovery = recovery_strategy or "retry_with_defaults"
    else:
        new_status = "escalated"
        recovery = recovery_strategy or "escalate_to_operator"

    for n in nodes:
        if n["node_id"] == node_id:
            n["status"] = new_status
            n["retry_count"] = retry_count
            n["failure_reason"] = failure_reason
            n["recovery_strategy"] = recovery

    orch_status = orch.get("status", "running")
    if new_status == "escalated" and orch_status not in ("paused", "completed"):
        orch_status = "escalated"

    db.orchestrations.update_one(
        {"orchestration_id": orch_id},
        {"$set": {
            "nodes": nodes,
            "status": orch_status,
            "retry_total": orch.get("retry_total", 0) + 1,
            "updated_at": _now_6t(),
        }},
    )
    return {
        "orchestration_id": orch_id,
        "node_id": node_id,
        "new_status": new_status,
        "retry_count": retry_count,
        "recovery_strategy": recovery,
    }


def escalate_orchestration_issue(orch_id: str, node_id: str, reason: str, db) -> dict:
    """Escalate an orchestration issue — optionally scoped to a single node."""
    orch = db.orchestrations.find_one({"orchestration_id": orch_id})
    if not orch:
        return {"error": "not_found"}

    nodes = orch.get("nodes") or []
    now = _now_6t()
    for n in nodes:
        if not node_id or n["node_id"] == node_id:
            n["status"] = "escalated"
            n["failure_reason"] = reason
            n["recovery_strategy"] = "operator_review"
            if node_id:
                break

    db.orchestrations.update_one(
        {"orchestration_id": orch_id},
        {"$set": {
            "nodes": nodes,
            "status": "escalated",
            "escalation_status": "pending_operator_review",
            "failure_reason": reason,
            "updated_at": now,
        }},
    )
    return {
        "orchestration_id": orch_id,
        "node_id": node_id,
        "escalation_status": "pending_operator_review",
        "reason": reason,
    }


def _compute_queue_priority(
    urgency: str,
    deps_ready: bool,
    deadline_hours: float,
    client_health: float,
    confidence: float,
) -> str:
    """Score an orchestration and return a priority bucket."""
    score = _PRIORITY_LEVELS_6T.get(urgency, 1) * 25
    if deps_ready:
        score += 10
    if deadline_hours < 4:
        score += 30
    elif deadline_hours < 24:
        score += 15
    if client_health >= 0.8:
        score += 10
    if confidence >= 0.90:
        score += 5
    if score >= 90:
        return "critical"
    elif score >= 50:
        return "high"
    elif score >= 25:
        return "normal"
    else:
        return "background"


def _compute_orchestration_telemetry(db, workspace_slug: str = "", days: int = 30) -> dict:
    """Aggregate telemetry across all orchestrations in scope."""
    q: dict[str, Any] = {}
    if workspace_slug:
        q["workspace_slug"] = workspace_slug
    q.update(_analytics_date_filter(days))
    try:
        orches = list(db.orchestrations.find(q))
    except Exception:
        orches = []

    total = len(orches)
    completed = [o for o in orches if o.get("status") == "completed"]
    failed = [o for o in orches if o.get("status") == "failed"]
    escalated = [o for o in orches if o.get("status") == "escalated"]
    running = [o for o in orches if o.get("status") == "running"]

    total_retries = sum(o.get("retry_total", 0) for o in orches)
    total_delegations = sum(o.get("delegation_count", 0) for o in orches)

    all_nodes = [n for o in orches for n in (o.get("nodes") or [])]
    by_agent: dict[str, dict] = {}
    for n in all_nodes:
        agent = n.get("agent_name") or "unknown"
        if agent not in by_agent:
            by_agent[agent] = {"total": 0, "completed": 0, "failed": 0, "retries": 0}
        by_agent[agent]["total"] += 1
        if n.get("status") == "completed":
            by_agent[agent]["completed"] += 1
        elif n.get("status") in ("failed", "escalated"):
            by_agent[agent]["failed"] += 1
        by_agent[agent]["retries"] += n.get("retry_count", 0)

    by_priority: dict[str, int] = {}
    for o in orches:
        p = o.get("priority") or "normal"
        by_priority[p] = by_priority.get(p, 0) + 1

    return {
        "total_orchestrations": total,
        "completed": len(completed),
        "failed": len(failed),
        "escalated": len(escalated),
        "running": len(running),
        "completion_rate": round(len(completed) / total, 3) if total else 0.0,
        "total_retries": total_retries,
        "retry_frequency": round(total_retries / total, 2) if total else 0.0,
        "total_delegations": total_delegations,
        "by_agent": by_agent,
        "by_priority": by_priority,
        "days": days,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.post("/orchestrations")
def create_orchestration(payload: OrchestrationCreateRequest) -> dict:
    if not payload.workspace_slug.strip():
        raise HTTPException(status_code=400, detail="workspace_slug is required.")
    if not payload.agent_chain:
        raise HTTPException(status_code=400, detail="agent_chain must not be empty.")
    client = get_client()
    try:
        db = get_database(client)
        doc = create_orchestration_plan(
            workspace_slug=payload.workspace_slug.strip(),
            workflow_run_id=payload.workflow_run_id or "",
            agent_chain=payload.agent_chain,
            db=db,
            priority=payload.priority,
            config=payload.config or {},
        )
        return {"item": serialize([doc])[0], "message": "Orchestration created."}
    finally:
        client.close()


@app.get("/orchestrations")
def list_orchestrations(
    workspace_slug: str = Query(""),
    status: str = Query(""),
    priority: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        q: dict = {}
        if workspace_slug:
            q["workspace_slug"] = workspace_slug
        if status and status in _ORCH_STATUSES_6T:
            q["status"] = status
        if priority and priority in _PRIORITY_LEVELS_6T:
            q["priority"] = priority
        items = list(db.orchestrations.find(q).sort("created_at", -1).limit(limit))
        return {"items": serialize(items), "total": len(items)}
    finally:
        client.close()


@app.get("/orchestrations/telemetry")
def get_orchestration_global_telemetry(
    workspace_slug: str = Query(""),
    days: int = Query(30, ge=0, le=365),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        return _compute_orchestration_telemetry(db, workspace_slug, days)
    finally:
        client.close()


@app.get("/orchestrations/{orch_id}")
def get_orchestration(orch_id: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        doc = db.orchestrations.find_one({"orchestration_id": orch_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Orchestration not found.")
        return {"item": serialize([doc])[0]}
    finally:
        client.close()


@app.get("/orchestrations/{orch_id}/graph")
def get_orchestration_graph(orch_id: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        orch = db.orchestrations.find_one({"orchestration_id": orch_id})
        if not orch:
            raise HTTPException(status_code=404, detail="Orchestration not found.")
        nodes = orch.get("nodes") or []
        edges = orch.get("edges") or []
        return {
            "orchestration_id": orch_id,
            "status": orch.get("status"),
            "nodes": [
                {
                    "node_id": n.get("node_id"),
                    "agent_name": n.get("agent_name"),
                    "label": n.get("label", n.get("agent_name")),
                    "status": n.get("status"),
                    "depends_on": n.get("depends_on") or [],
                    "retry_count": n.get("retry_count", 0),
                }
                for n in nodes
            ],
            "edges": edges,
            "ready_node_count": sum(1 for n in nodes if n.get("status") == "ready"),
            "running_node_count": sum(1 for n in nodes if n.get("status") == "running"),
            "completion_rate": round(
                sum(1 for n in nodes if n.get("status") == "completed") / len(nodes), 3
            ) if nodes else 0.0,
        }
    finally:
        client.close()


@app.get("/orchestrations/{orch_id}/telemetry")
def get_single_orchestration_telemetry(orch_id: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        orch = db.orchestrations.find_one({"orchestration_id": orch_id})
        if not orch:
            raise HTTPException(status_code=404, detail="Orchestration not found.")
        nodes = orch.get("nodes") or []
        total_nodes = len(nodes)
        by_agent: dict[str, int] = {}
        for n in nodes:
            a = n.get("agent_name") or "unknown"
            by_agent[a] = by_agent.get(a, 0) + 1
        total_retries = sum(n.get("retry_count", 0) for n in nodes)
        return {
            "orchestration_id": orch_id,
            "status": orch.get("status"),
            "priority": orch.get("priority"),
            "total_nodes": total_nodes,
            "completed_nodes": sum(1 for n in nodes if n.get("status") == "completed"),
            "failed_nodes": sum(1 for n in nodes if n.get("status") in ("failed", "escalated")),
            "running_nodes": sum(1 for n in nodes if n.get("status") == "running"),
            "pending_nodes": sum(1 for n in nodes if n.get("status") in ("pending", "ready")),
            "retrying_nodes": sum(1 for n in nodes if n.get("status") == "retrying"),
            "total_retries": total_retries,
            "completion_rate": round(
                sum(1 for n in nodes if n.get("status") == "completed") / total_nodes, 3
            ) if total_nodes else 0.0,
            "delegation_count": orch.get("delegation_count", 0),
            "by_agent": by_agent,
            "created_at": orch.get("created_at"),
            "updated_at": orch.get("updated_at"),
        }
    finally:
        client.close()


@app.post("/orchestrations/{orch_id}/pause")
def pause_orchestration(orch_id: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        orch = db.orchestrations.find_one({"orchestration_id": orch_id})
        if not orch:
            raise HTTPException(status_code=404, detail="Orchestration not found.")
        db.orchestrations.update_one(
            {"orchestration_id": orch_id},
            {"$set": {"status": "paused", "updated_at": _now_6t()}},
        )
        return {"orchestration_id": orch_id, "status": "paused"}
    finally:
        client.close()


@app.post("/orchestrations/{orch_id}/resume")
def resume_orchestration(orch_id: str) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        orch = db.orchestrations.find_one({"orchestration_id": orch_id})
        if not orch:
            raise HTTPException(status_code=404, detail="Orchestration not found.")
        db.orchestrations.update_one(
            {"orchestration_id": orch_id},
            {"$set": {"status": "running", "updated_at": _now_6t()}},
        )
        schedule_next_agent_tasks(orch_id, db)
        return {"orchestration_id": orch_id, "status": "running"}
    finally:
        client.close()


@app.post("/orchestrations/{orch_id}/retry-node")
def retry_orchestration_node(orch_id: str, payload: RetryNodeRequest) -> dict:
    if not payload.node_id.strip():
        raise HTTPException(status_code=400, detail="node_id is required.")
    client = get_client()
    try:
        db = get_database(client)
        orch = db.orchestrations.find_one({"orchestration_id": orch_id})
        if not orch:
            raise HTTPException(status_code=404, detail="Orchestration not found.")
        nodes = orch.get("nodes") or []
        target = next((n for n in nodes if n["node_id"] == payload.node_id.strip()), None)
        if not target:
            raise HTTPException(status_code=404, detail="Node not found.")
        if target.get("status") not in ("failed", "escalated", "retrying"):
            raise HTTPException(
                status_code=400,
                detail=f"Node status '{target.get('status')}' is not retryable.",
            )
        for n in nodes:
            if n["node_id"] == payload.node_id.strip():
                n["status"] = "retrying"
                n["retry_count"] = n.get("retry_count", 0) + 1
                if payload.recovery_strategy:
                    n["recovery_strategy"] = payload.recovery_strategy
        db.orchestrations.update_one(
            {"orchestration_id": orch_id},
            {"$set": {
                "nodes": nodes,
                "status": "running",
                "retry_total": orch.get("retry_total", 0) + 1,
                "updated_at": _now_6t(),
            }},
        )
        return {"orchestration_id": orch_id, "node_id": payload.node_id, "status": "retrying"}
    finally:
        client.close()


@app.post("/orchestrations/{orch_id}/escalate")
def escalate_orchestration(orch_id: str, payload: EscalateOrchestrationRequest) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        result = escalate_orchestration_issue(
            orch_id, payload.node_id, payload.reason or "Operator escalation", db
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail="Orchestration not found.")
        return result
    finally:
        client.close()


@app.get("/agents/profiles")
def list_agent_profiles() -> dict:
    client = get_client()
    try:
        db = get_database(client)
        profiles = {k: dict(v) for k, v in _DEFAULT_AGENT_PROFILES_6T.items()}
        for p in db.agent_profiles.find({}):
            name = p.get("agent_name", "")
            if name:
                profiles[name] = {k: v for k, v in p.items() if k != "_id"}
        return {"profiles": list(profiles.values()), "total": len(profiles)}
    finally:
        client.close()


@app.get("/agents/utilization")
def get_agent_utilization(
    workspace_slug: str = Query(""),
    days: int = Query(30, ge=0, le=365),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        profiles = {k: dict(v) for k, v in _DEFAULT_AGENT_PROFILES_6T.items()}
        for p in db.agent_profiles.find({}):
            name = p.get("agent_name", "")
            if name:
                profiles[name] = {k: v for k, v in p.items() if k != "_id"}

        q2: dict[str, Any] = {}
        if workspace_slug:
            q2["workspace_slug"] = workspace_slug
        q2.update(_analytics_date_filter(days))
        try:
            all_orches = list(db.orchestrations.find(q2))
        except Exception:
            all_orches = []

        utilization: dict[str, dict] = {}
        for agent_name, profile in profiles.items():
            running_count = 0
            completed_count = 0
            failed_count = 0
            total_retries = 0
            for orch in all_orches:
                for node in (orch.get("nodes") or []):
                    if node.get("agent_name") == agent_name:
                        s = node.get("status")
                        if s == "running":
                            running_count += 1
                        elif s == "completed":
                            completed_count += 1
                        elif s in ("failed", "escalated"):
                            failed_count += 1
                        total_retries += node.get("retry_count", 0)
            max_concurrency = profile.get("max_concurrency", 5)
            utilization[agent_name] = {
                "agent_name": agent_name,
                "running_nodes": running_count,
                "max_concurrency": max_concurrency,
                "utilization_rate": round(running_count / max_concurrency, 3)
                    if max_concurrency else 0.0,
                "completed_nodes": completed_count,
                "failed_nodes": failed_count,
                "total_retries": total_retries,
                "success_rate": profile.get("success_rate", 0.0),
                "avg_execution_time": profile.get("avg_execution_time", 0.0),
                "specializations": profile.get("specializations", []),
            }
        return {
            "agents": list(utilization.values()),
            "total_running": sum(u["running_nodes"] for u in utilization.values()),
            "period_days": days,
        }
    finally:
        client.close()

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 6U — PRODUCTION HARDENING & DEPLOYMENT READINESS
# ═══════════════════════════════════════════════════════════════════════════════

import logging as _logging_6u
import time as _time_6u
import uuid as _uuid_6u

try:
    import jwt as _pyjwt
    _PYJWT_AVAILABLE = True
except Exception:
    _pyjwt = None  # type: ignore[assignment]
    _PYJWT_AVAILABLE = False

# ── Configuration flags ───────────────────────────────────────────────────────
_AUTH_ENABLED_6U: bool = os.getenv("SIGNALFORGE_AUTH_ENABLED", "false").lower() == "true"
_RATE_LIMIT_ENABLED_6U: bool = os.getenv("SIGNALFORGE_RATE_LIMIT_ENABLED", "false").lower() == "true"
_JWT_SECRET_6U: str = os.getenv("SIGNALFORGE_JWT_SECRET", "signalforge-dev-secret-change-in-production")
_JWT_ALGORITHM_6U: str = "HS256"
_JWT_EXPIRY_HOURS_6U: int = int(os.getenv("SIGNALFORGE_JWT_EXPIRY_HOURS", "24"))

# Default API keys loaded from env (comma-separated key:role pairs, or single key)
_DEFAULT_API_KEYS_6U: dict[str, dict] = {
    os.getenv("SIGNALFORGE_API_KEY", "sf-dev-key-change-me"): {
        "role": "admin",
        "workspace": "*",
    },
}

# ── Structured logging ────────────────────────────────────────────────────────
_sf_logger_6u = _logging_6u.getLogger("signalforge")
if not _sf_logger_6u.handlers:
    _log_handler_6u = _logging_6u.StreamHandler()
    _log_handler_6u.setFormatter(_logging_6u.Formatter(
        '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":%(message)s}'
    ))
    _sf_logger_6u.addHandler(_log_handler_6u)
    _sf_logger_6u.setLevel(_logging_6u.INFO)


def _log_event_6u(level: str, event_type: str, **fields: Any) -> None:
    payload = json.dumps({"event_type": event_type, **fields})
    getattr(_sf_logger_6u, level, _sf_logger_6u.info)(payload)


# ── In-memory runtime state ───────────────────────────────────────────────────
_runtime_state_6u: dict[str, Any] = {
    "total_requests": 0,
    "by_path": {},        # "{METHOD}:{path}" → {count, total_latency_ms, errors, avg_latency_ms}
    "worker_registry": {},  # worker_id → heartbeat record
    "audit_log": [],      # capped at 500 entries
    "rate_buckets": {},   # key → list[float] timestamps
}


def _now_iso_6u() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Request metrics ───────────────────────────────────────────────────────────
def _record_request_6u(path: str, method: str, latency_ms: float, status_code: int) -> None:
    _runtime_state_6u["total_requests"] += 1
    key = f"{method}:{path}"
    bucket = _runtime_state_6u["by_path"].setdefault(key, {
        "count": 0, "total_latency_ms": 0.0, "errors": 0,
        "avg_latency_ms": 0.0, "last_status_code": 200,
    })
    bucket["count"] += 1
    bucket["total_latency_ms"] += latency_ms
    bucket["avg_latency_ms"] = round(bucket["total_latency_ms"] / bucket["count"], 2)
    bucket["last_status_code"] = status_code
    if status_code >= 400:
        bucket["errors"] += 1


def _append_audit_6u(actor: str, action: str, resource: str, **meta: Any) -> None:
    entry = {"ts": _now_iso_6u(), "actor": actor, "action": action, "resource": resource, **meta}
    _runtime_state_6u["audit_log"].append(entry)
    if len(_runtime_state_6u["audit_log"]) > 500:
        _runtime_state_6u["audit_log"] = _runtime_state_6u["audit_log"][-500:]


# ── Rate limiting ─────────────────────────────────────────────────────────────
def _check_rate_limit_6u(key: str, max_requests: int = 60, window_seconds: int = 60) -> bool:
    """Return True if request is allowed, False if rate limited."""
    if not _RATE_LIMIT_ENABLED_6U:
        return True
    now = _time_6u.time()
    bucket: list[float] = _runtime_state_6u["rate_buckets"].get(key, [])
    bucket = [t for t in bucket if now - t < window_seconds]
    if len(bucket) >= max_requests:
        _runtime_state_6u["rate_buckets"][key] = bucket
        return False
    bucket.append(now)
    _runtime_state_6u["rate_buckets"][key] = bucket
    return True


def _rate_key_6u(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return getattr(request.client, "host", "unknown") if request.client else "unknown"


# ── Auth helpers ──────────────────────────────────────────────────────────────
def _create_token_6u(payload: dict, expires_hours: int = _JWT_EXPIRY_HOURS_6U) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    to_encode = {**payload, "exp": exp, "iat": datetime.now(timezone.utc)}
    if _PYJWT_AVAILABLE and _pyjwt is not None:
        return str(_pyjwt.encode(to_encode, _JWT_SECRET_6U, algorithm=_JWT_ALGORITHM_6U))
    # Fallback: opaque token (base64-like stub for environments without PyJWT)
    import base64 as _b64
    return _b64.urlsafe_b64encode(json.dumps(to_encode, default=str).encode()).decode()


def _decode_token_6u(token: str) -> dict:
    if _PYJWT_AVAILABLE and _pyjwt is not None:
        return dict(_pyjwt.decode(token, _JWT_SECRET_6U, algorithms=[_JWT_ALGORITHM_6U]))
    raise HTTPException(
        status_code=401,
        detail={"error": True, "code": "jwt_unavailable", "message": "JWT library not available"},
    )


def _require_auth_6u(request: Request) -> dict:
    """FastAPI dependency: validate Bearer token or API key. Bypassed when auth disabled."""
    if not _AUTH_ENABLED_6U:
        return {"role": "admin", "workspace": "*", "sub": "dev-bypass"}
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if token in _DEFAULT_API_KEYS_6U:
            return _DEFAULT_API_KEYS_6U[token]
        try:
            return _decode_token_6u(token)
        except Exception:
            raise HTTPException(
                status_code=401,
                detail={"error": True, "code": "invalid_token", "message": "Invalid or expired token"},
            )
    raise HTTPException(
        status_code=401,
        detail={"error": True, "code": "missing_auth", "message": "Authorization header required"},
    )


def _require_admin_6u(request: Request) -> dict:
    """FastAPI dependency: require admin role."""
    identity = _require_auth_6u(request)
    if identity.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail={"error": True, "code": "forbidden", "message": "Admin role required"},
        )
    return identity


def _error_response_6u(
    code: str,
    message: str,
    details: dict | None = None,
    trace_id: str | None = None,
    status_code: int = 400,
) -> HTTPException:
    """Build a standardized error HTTPException."""
    return HTTPException(
        status_code=status_code,
        detail={
            "error": True,
            "code": code,
            "message": message,
            "details": details or {},
            "trace_id": trace_id or _uuid_6u.uuid4().hex,
        },
    )


# ── MongoDB index management ──────────────────────────────────────────────────
def ensure_indexes_6u(db: Any) -> dict[str, Any]:
    """Create all production indexes. Idempotent — safe to call on every startup."""
    from pymongo import ASCENDING as _ASC, DESCENDING as _DESC, IndexModel as _IdxModel

    _DIR = {1: _ASC, -1: _DESC}

    index_specs: dict[str, list[list[tuple[str, int]]]] = {
        "workflow_runs": [
            [("workspace_slug", 1), ("created_at", -1)],
            [("status", 1), ("created_at", -1)],
            [("run_id", 1)],
        ],
        "workflow_assets": [
            [("workspace_slug", 1), ("status", 1)],
            [("run_id", 1), ("asset_type", 1)],
            [("created_at", -1)],
        ],
        "approval_requests": [
            [("workspace_slug", 1), ("status", 1)],
            [("created_at", -1)],
            [("asset_id", 1)],
        ],
        "client_memory": [
            [("workspace_slug", 1), ("memory_type", 1)],
            [("workspace_slug", 1), ("updated_at", -1)],
            [("is_active", 1), ("workspace_slug", 1)],
        ],
        "memory_update_proposals": [
            [("workspace_slug", 1), ("status", 1)],
            [("proposed_at", -1)],
            [("governance_level", 1), ("status", 1)],
        ],
        "recommendation_statuses": [
            [("workspace_slug", 1), ("status", 1)],
            [("created_at", -1)],
            [("recommendation_type", 1), ("status", 1)],
        ],
        "orchestrations": [
            [("workspace_slug", 1), ("status", 1)],
            [("created_at", -1)],
            [("orchestration_id", 1)],
        ],
        "autonomy_actions": [
            [("workspace_slug", 1), ("action_type", 1)],
            [("created_at", -1)],
            [("status", 1), ("created_at", -1)],
        ],
        "agent_tasks": [
            [("workspace_slug", 1), ("status", 1)],
            [("assigned_agent", 1), ("status", 1)],
            [("created_at", -1)],
        ],
    }

    results: dict[str, Any] = {}
    for collection_name, specs in index_specs.items():
        try:
            coll = getattr(db, collection_name)
            models = [_IdxModel([(f, _DIR[d]) for f, d in spec]) for spec in specs]
            coll.create_indexes(models)
            results[collection_name] = {"status": "ok", "indexes": len(specs)}
        except Exception as e:
            results[collection_name] = {"status": "error", "error": str(e)}

    return results


# ── Worker heartbeat tracking ─────────────────────────────────────────────────
def _record_worker_heartbeat_6u(
    worker_id: str,
    status: str,
    tasks_processed: int = 0,
    tasks_failed: int = 0,
    queue_depth: int = 0,
    metadata: dict | None = None,
) -> dict:
    record = {
        "worker_id": worker_id,
        "status": status,
        "tasks_processed": tasks_processed,
        "tasks_failed": tasks_failed,
        "queue_depth": queue_depth,
        "last_seen": _now_iso_6u(),
        "metadata": metadata or {},
    }
    _runtime_state_6u["worker_registry"][worker_id] = record
    return record


def _get_worker_health_6u() -> dict:
    registry = _runtime_state_6u["worker_registry"]
    now_ts = _time_6u.time()
    stale_threshold_seconds = 60
    healthy: list[str] = []
    stale: list[str] = []
    for worker_id, record in registry.items():
        try:
            last_seen_dt = datetime.fromisoformat(record["last_seen"])
            age = now_ts - last_seen_dt.timestamp()
            (healthy if age < stale_threshold_seconds else stale).append(worker_id)
        except Exception:
            stale.append(worker_id)
    return {
        "total_workers": len(registry),
        "healthy": len(healthy),
        "stale": len(stale),
        "healthy_worker_ids": healthy,
        "stale_worker_ids": stale,
        "registry": list(registry.values()),
    }


def _detect_stuck_orchestrations_6u(db: Any, threshold_minutes: int = 60) -> list[dict]:
    """Return orchestrations stuck in running state for longer than threshold."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
    try:
        stuck = list(db.orchestrations.find({
            "status": "running",
            "created_at": {"$lt": cutoff.isoformat()},
        }))
        return [
            {
                "orchestration_id": o.get("orchestration_id"),
                "created_at": o.get("created_at"),
                "workspace_slug": o.get("workspace_slug"),
            }
            for o in stuck
        ]
    except Exception:
        return []


def _recover_orphaned_tasks_6u(db: Any) -> dict:
    """Mark tasks assigned to stale workers as failed (orphan recovery)."""
    stale_ids = _get_worker_health_6u()["stale_worker_ids"]
    recovered = 0
    if stale_ids:
        try:
            result = db.agent_tasks.update_many(
                {"status": "running", "assigned_worker": {"$in": stale_ids}},
                {"$set": {
                    "status": "failed",
                    "error": "orphaned_task_worker_stale",
                    "recovered_at": _now_iso_6u(),
                }},
            )
            recovered = result.modified_count
        except Exception:
            pass
    return {"recovered_tasks": recovered, "stale_workers": stale_ids}


# ── Tracing middleware ────────────────────────────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware as _BaseHTTPMiddleware


class _TracingMiddleware6U(_BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Any:
        trace_id = request.headers.get("X-Trace-ID") or _uuid_6u.uuid4().hex
        request.state.trace_id = trace_id
        start = _time_6u.time()
        response = await call_next(request)
        latency_ms = round((_time_6u.time() - start) * 1000, 2)
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Response-Time-Ms"] = str(latency_ms)
        _record_request_6u(request.url.path, request.method, latency_ms, response.status_code)
        return response


app.add_middleware(_TracingMiddleware6U)


# ── Pydantic models ───────────────────────────────────────────────────────────
class TokenRequest6U(BaseModel):
    api_key: str = Field(..., description="API key credential")
    workspace_slug: str = Field("", description="Target workspace scope")


class TokenResponse6U(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_hours: int = _JWT_EXPIRY_HOURS_6U
    role: str = "operator"


class WorkerHeartbeatRequest6U(BaseModel):
    worker_id: str
    status: str = "running"
    tasks_processed: int = 0
    tasks_failed: int = 0
    queue_depth: int = 0
    metadata: dict = Field(default_factory=dict)


# ── Auth endpoints ────────────────────────────────────────────────────────────
@app.post("/auth/token", tags=["auth"])
def auth_get_token(body: TokenRequest6U) -> dict:
    """Issue a JWT access token for a valid API key."""
    key_record = _DEFAULT_API_KEYS_6U.get(body.api_key)
    if not key_record:
        raise _error_response_6u("invalid_api_key", "Invalid API key", status_code=401)
    token = _create_token_6u({
        "sub": body.api_key,
        "role": key_record["role"],
        "workspace": key_record.get("workspace", "*"),
    })
    _append_audit_6u("api_key", "token_issued", "auth", workspace=body.workspace_slug)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_hours": _JWT_EXPIRY_HOURS_6U,
        "role": key_record["role"],
    }


@app.get("/auth/validate", tags=["auth"])
def auth_validate_token(request: Request, identity: dict = Depends(_require_auth_6u)) -> dict:
    """Validate the current Bearer token and return identity claims."""
    return {"valid": True, "identity": identity}


# ── System health & metrics endpoints ────────────────────────────────────────
@app.get("/system/health/detailed", tags=["system"])
def system_health_detailed() -> dict:
    """Comprehensive health check including DB, vault, workers, and feature flags."""
    client = get_client()
    db_ok = False
    db_error: str | None = None
    try:
        db = get_database(client)
        db.command("ping")
        db_ok = True
    except Exception as e:
        db_error = str(e)
    finally:
        client.close()

    worker_h = _get_worker_health_6u()
    return {
        "status": "healthy" if db_ok else "degraded",
        "environment": os.getenv("SIGNALFORGE_ENV", "local"),
        "timestamp": _now_iso_6u(),
        "version": "1.0.0",
        "components": {
            "database": {"status": "ok" if db_ok else "error", "error": db_error},
            "vault": {"status": vault_status()},
            "workers": {
                "status": "ok" if worker_h["stale"] == 0 else "degraded",
                "healthy": worker_h["healthy"],
                "stale": worker_h["stale"],
            },
            "auth": {"enabled": _AUTH_ENABLED_6U},
            "rate_limiting": {"enabled": _RATE_LIMIT_ENABLED_6U},
        },
    }


@app.get("/system/metrics", tags=["system"])
def system_get_metrics(request: Request) -> dict:
    """Return API request metrics, latency statistics, and error rates."""
    if not _check_rate_limit_6u(_rate_key_6u(request), max_requests=30, window_seconds=60):
        raise _error_response_6u("rate_limited", "Too many requests", status_code=429)
    paths = _runtime_state_6u["by_path"]
    total = _runtime_state_6u["total_requests"]
    top_endpoints = sorted(paths.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
    error_endpoints = [(p, d) for p, d in paths.items() if d["errors"] > 0]
    return {
        "total_requests": total,
        "unique_endpoints": len(paths),
        "top_endpoints": [{"endpoint": p, **d} for p, d in top_endpoints],
        "error_endpoints": [{"endpoint": p, **d} for p, d in error_endpoints],
        "timestamp": _now_iso_6u(),
    }


@app.get("/system/indexes", tags=["system"])
def system_index_status() -> dict:
    """Verify and return MongoDB index status for all production collections."""
    client = get_client()
    try:
        db = get_database(client)
        results = ensure_indexes_6u(db)
        all_ok = all(v.get("status") == "ok" for v in results.values())
        return {
            "status": "ok" if all_ok else "partial",
            "collections": results,
            "timestamp": _now_iso_6u(),
        }
    finally:
        client.close()


@app.get("/system/telemetry", tags=["system"])
def system_telemetry() -> dict:
    """Production telemetry aggregation: API metrics, workers, queue, and DB health."""
    client = get_client()
    try:
        db = get_database(client)
        db_ok = True
        try:
            db.command("ping")
        except Exception:
            db_ok = False

        worker_h = _get_worker_health_6u()
        registry = _runtime_state_6u["worker_registry"]
        total_queue = sum(w.get("queue_depth", 0) for w in registry.values())
        total_reqs = _runtime_state_6u["total_requests"]
        paths = _runtime_state_6u["by_path"]
        total_errors = sum(d["errors"] for d in paths.values())
        total_latency = sum(d["total_latency_ms"] for d in paths.values())
        total_count = sum(d["count"] for d in paths.values())
        avg_latency = round(total_latency / total_count, 2) if total_count else 0.0

        return {
            "timestamp": _now_iso_6u(),
            "database": {"healthy": db_ok},
            "api": {
                "total_requests": total_reqs,
                "total_errors": total_errors,
                "error_rate": round(total_errors / total_reqs, 4) if total_reqs else 0.0,
                "avg_latency_ms": avg_latency,
            },
            "workers": {
                "total": worker_h["total_workers"],
                "healthy": worker_h["healthy"],
                "stale": worker_h["stale"],
                "total_queue_depth": total_queue,
            },
        }
    finally:
        client.close()


@app.post("/system/reset-metrics", tags=["system"])
def system_reset_metrics(
    request: Request,
    identity: dict = Depends(_require_admin_6u),
) -> dict:
    """Reset in-memory API metrics (admin only)."""
    _runtime_state_6u["total_requests"] = 0
    _runtime_state_6u["by_path"] = {}
    _append_audit_6u(identity.get("sub", "admin"), "reset_metrics", "system/metrics")
    return {"reset": True, "timestamp": _now_iso_6u()}


@app.get("/system/audit-log", tags=["system"])
def system_audit_log(limit: int = Query(50, ge=1, le=500)) -> dict:
    """Return recent system audit log entries (capped at 500 total)."""
    entries = _runtime_state_6u["audit_log"]
    return {
        "entries": entries[-limit:],
        "total_recorded": len(entries),
        "returned": min(limit, len(entries)),
        "timestamp": _now_iso_6u(),
    }


# ── Worker endpoints ──────────────────────────────────────────────────────────
@app.post("/workers/heartbeat", tags=["workers"])
def worker_heartbeat(body: WorkerHeartbeatRequest6U) -> dict:
    """Register a worker heartbeat to mark the worker as alive."""
    if not _check_rate_limit_6u(f"worker:{body.worker_id}", max_requests=120, window_seconds=60):
        raise _error_response_6u("rate_limited", "Heartbeat rate exceeded", status_code=429)
    record = _record_worker_heartbeat_6u(
        body.worker_id, body.status,
        body.tasks_processed, body.tasks_failed,
        body.queue_depth, body.metadata,
    )
    return {"accepted": True, "worker": record}


@app.get("/workers/health", tags=["workers"])
def workers_health() -> dict:
    """Return worker registry health summary with healthy/stale classification."""
    return _get_worker_health_6u()


@app.get("/workers/queue-depth", tags=["workers"])
def workers_queue_depth() -> dict:
    """Return current queue depth aggregated across all registered workers."""
    registry = _runtime_state_6u["worker_registry"]
    total = sum(w.get("queue_depth", 0) for w in registry.values())
    return {
        "total_queue_depth": total,
        "worker_count": len(registry),
        "per_worker": [
            {"worker_id": wid, "queue_depth": w.get("queue_depth", 0), "status": w.get("status")}
            for wid, w in registry.items()
        ],
        "timestamp": _now_iso_6u(),
    }


@app.post("/workers/recover-orphaned", tags=["workers"])
def workers_recover_orphaned() -> dict:
    """Trigger orphaned task recovery and stuck orchestration detection."""
    client = get_client()
    try:
        db = get_database(client)
        recovery = _recover_orphaned_tasks_6u(db)
        stuck = _detect_stuck_orchestrations_6u(db)
        _append_audit_6u("system", "orphan_recovery", "workers", **recovery)
        return {
            "recovery": recovery,
            "stuck_orchestrations": stuck,
            "stuck_count": len(stuck),
            "timestamp": _now_iso_6u(),
        }
    finally:
        client.close()

# =============================================================================
# PHASE 6V — Production Deployment Drill & Pilot Readiness
# Appended to services/api/main.py
# =============================================================================

import json as _json_6v
import gzip as _gzip_6v
import base64 as _b64_6v
from fastapi.responses import JSONResponse as _JSONResponse_6v

# ── Collections covered by backup / restore ───────────────────────────────────
_PHASE_6V_COLLECTIONS = [
    "workflow_runs",
    "workflow_assets",
    "approval_requests",
    "client_memory",
    "memory_update_proposals",
    "recommendation_statuses",
    "orchestrations",
    "autonomy_actions",
    "agent_tasks",
]

# Score weights (total = 100)
_PILOT_READINESS_WEIGHTS_6V: dict[str, int] = {
    "mongodb_reachable": 20,
    "indexes_created": 10,
    "tracing_active": 10,
    "metrics_operational": 10,
    "audit_log_operational": 10,
    "worker_system_operational": 10,
    "orchestration_recovery_operational": 10,
    "auth_configurable": 10,
    "rate_limit_configurable": 10,
}


# ── Pydantic models ───────────────────────────────────────────────────────────
class BackupRequest6V(BaseModel):
    collections: list[str] | None = None  # None → all Phase 6V collections
    compress: bool = True


class RestoreRequest6V(BaseModel):
    payload: str          # base64(gzip(json)) or base64(json)
    compressed: bool = True
    dry_run: bool = False


# ── Helper: create a backup snapshot ─────────────────────────────────────────
def _do_backup_6v(db: Any, collections: list[str], compress: bool) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "version": "6v",
        "created_at": _now_iso_6u(),
        "collections": {},
    }
    total = 0
    for name in collections:
        docs = list(db[name].find({}, {"_id": 0}))
        snapshot["collections"][name] = docs
        total += len(docs)

    raw = _json_6v.dumps(snapshot, default=str).encode()
    if compress:
        encoded = _b64_6v.b64encode(_gzip_6v.compress(raw)).decode()
    else:
        encoded = _b64_6v.b64encode(raw).decode()

    return {
        "payload": encoded,
        "compressed": compress,
        "total_documents": total,
        "collections": collections,
        "bytes": len(encoded),
        "created_at": snapshot["created_at"],
    }


# ── Helper: restore from a backup snapshot ───────────────────────────────────
def _do_restore_6v(
    db: Any, payload: str, compressed: bool, dry_run: bool
) -> dict[str, Any]:
    raw = _b64_6v.b64decode(payload)
    if compressed:
        raw = _gzip_6v.decompress(raw)
    snapshot = _json_6v.loads(raw)

    if snapshot.get("version") != "6v":
        raise ValueError(f"Unsupported backup version: {snapshot.get('version')!r}")

    results: dict[str, Any] = {}
    for name, docs in snapshot.get("collections", {}).items():
        if dry_run:
            results[name] = {"status": "dry_run", "would_restore": len(docs)}
        else:
            db[name].delete_many({})
            if docs:
                db[name].insert_many(docs)
            results[name] = {"status": "restored", "documents": len(docs)}

    return {
        "dry_run": dry_run,
        "collections": results,
        "restored_at": _now_iso_6u(),
        "source_version": snapshot.get("version"),
    }


# ── Helper: compute pilot readiness score ────────────────────────────────────
def _pilot_readiness_6v(db: Any) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    score = 0
    w = _PILOT_READINESS_WEIGHTS_6V

    # MongoDB connectivity
    try:
        db.command("ping")
        checks["mongodb_reachable"] = True
        score += w["mongodb_reachable"]
    except Exception:
        checks["mongodb_reachable"] = False

    # Index health
    try:
        ensure_indexes_6u(db)  # type: ignore[name-defined]
        checks["indexes_created"] = True
        score += w["indexes_created"]
    except Exception:
        checks["indexes_created"] = False

    # Tracing middleware always active
    checks["tracing_active"] = True
    score += w["tracing_active"]

    # Metrics system
    checks["metrics_operational"] = isinstance(
        _runtime_state_6u.get("total_requests"), int
    )
    if checks["metrics_operational"]:
        score += w["metrics_operational"]

    # Audit log
    checks["audit_log_operational"] = isinstance(
        _runtime_state_6u.get("audit_log"), list
    )
    if checks["audit_log_operational"]:
        score += w["audit_log_operational"]

    # Worker registry
    checks["worker_system_operational"] = isinstance(
        _runtime_state_6u.get("worker_registry"), dict
    )
    if checks["worker_system_operational"]:
        score += w["worker_system_operational"]

    # Orchestration recovery
    try:
        _detect_stuck_orchestrations_6u(db)
        checks["orchestration_recovery_operational"] = True
        score += w["orchestration_recovery_operational"]
    except Exception:
        checks["orchestration_recovery_operational"] = False

    # Auth / rate-limit configurability (env-var based, always configurable)
    checks["auth_configurable"] = True
    score += w["auth_configurable"]
    checks["rate_limit_configurable"] = True
    score += w["rate_limit_configurable"]

    # Informational extras (no score impact)
    checks["active_workers"] = len(_runtime_state_6u.get("worker_registry", {}))
    checks["total_requests_served"] = _runtime_state_6u.get("total_requests", 0)

    return {
        "ready": score >= 80,
        "score": score,
        "max_score": 100,
        "checks": checks,
        "evaluated_at": _now_iso_6u(),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/system/backup", tags=["system"])
def system_backup_6v(req: BackupRequest6V) -> dict:
    """Create a portable backup snapshot of all key collections."""
    collections = req.collections or _PHASE_6V_COLLECTIONS
    c = get_client()
    db = get_database(c)
    try:
        result = _do_backup_6v(db, collections, req.compress)
        _append_audit_6u(
            "system", "backup_created",
            "system/backup",
            collections=len(collections),
            total_documents=result["total_documents"],
            compressed=req.compress,
        )
        return result
    finally:
        c.close()


@app.post("/system/restore", tags=["system"])
def system_restore_6v(req: RestoreRequest6V) -> Any:
    """Restore collections from a backup snapshot (supports dry-run)."""
    c = get_client()
    db = get_database(c)
    try:
        result = _do_restore_6v(db, req.payload, req.compressed, req.dry_run)
        _append_audit_6u(
            "system", "restore_executed",
            "system/restore",
            dry_run=req.dry_run,
            collections=len(result["collections"]),
        )
        return result
    except ValueError as exc:
        return _JSONResponse_6v(status_code=400, content={"error": str(exc)})
    finally:
        c.close()


@app.get("/system/pilot-readiness", tags=["system"])
def system_pilot_readiness_6v() -> dict:
    """Compute a comprehensive pilot-readiness score (0-100)."""
    c = get_client()
    db = get_database(c)
    try:
        return _pilot_readiness_6v(db)
    finally:
        c.close()


@app.get("/system/recovery-status", tags=["system"])
def system_recovery_status_6v() -> dict:
    """Return live recovery status: stuck orchestrations + worker health."""
    c = get_client()
    db = get_database(c)
    try:
        stuck = _detect_stuck_orchestrations_6u(db)
        return {
            "stuck_orchestrations": stuck,
            "stuck_count": len(stuck),
            "orphaned_task_risk": len(stuck) > 0,
            "worker_health": _get_worker_health_6u(),
            "recommendation": (
                "POST /workers/recover-orphaned" if len(stuck) > 0 else "no action needed"
            ),
            "evaluated_at": _now_iso_6u(),
        }
    finally:
        c.close()

# =============================================================================
# PHASE 6W — Pilot UX, Operator Experience & Guided Operations
# Appended to services/api/main.py
# =============================================================================

from datetime import datetime as _datetime_6w, timezone as _tz6w_obj, timedelta as _td_6w
_tz_utc_6w = _tz6w_obj.utc

# ── Role capability map ───────────────────────────────────────────────────────
_ROLE_CAPABILITIES_6W: dict = {
    "admin":    ["analytics", "approvals", "recommendations", "orchestration",
                 "autonomy", "system", "workers", "memory", "onboarding", "demo"],
    "operator": ["analytics", "approvals", "recommendations", "orchestration",
                 "workers", "memory", "onboarding"],
    "reviewer": ["approvals", "recommendations", "analytics"],
    "observer": ["analytics"],
}

# ── Readiness check weights (must sum to 100) ─────────────────────────────────
_READINESS_WEIGHTS_6W: dict = {
    "client_memory_initialized":  20,
    "orchestration_healthy":      20,
    "autonomy_configured":        15,
    "workflows_active":           15,
    "workers_healthy":            15,
    "recommendations_not_blocked": 10,
    "sources_connected":           5,
}

# ── Activity event severity mapping ───────────────────────────────────────────
_ACTIVITY_SEVERITY_6W: dict = {
    "backup_created":           "info",
    "restore_executed":         "warning",
    "worker_recovered":         "warning",
    "orchestration_escalated":  "error",
    "memory_updated":           "info",
    "recommendation_generated": "info",
    "autonomy_action_applied":  "info",
    "rollback_executed":        "warning",
    "retry_triggered":          "info",
    "workflow_completed":       "info",
    "demo_workspace_seeded":    "info",
}

# ── Demo seed document counts ─────────────────────────────────────────────────
_DEMO_SEED_6W: dict = {
    "workflows":        3,
    "orchestrations":   2,
    "recommendations":  5,
    "autonomy_actions": 4,
    "memory_entries":   3,
}

# ── Explainability entity → collection map ────────────────────────────────────
_EXPLAIN_COLLECTION_MAP_6W: dict = {
    "recommendation":  "recommendation_statuses",
    "autonomy_action": "autonomy_actions",
    "orchestration":   "orchestrations",
    "memory_update":   "memory_update_proposals",
    "workflow_run":    "workflow_runs",
}

# ── Remediation guidance per readiness check ─────────────────────────────────
_REMEDIATION_6W: dict = {
    "client_memory_initialized": {
        "severity": "high",
        "message": "Client memory not initialized for this workspace.",
        "action": "POST /client-memory/{slug}",
    },
    "orchestration_healthy": {
        "severity": "high",
        "message": "Stuck orchestrations detected (running > 60 min).",
        "action": "POST /workers/recover-orphaned",
    },
    "autonomy_configured": {
        "severity": "medium",
        "message": "No autonomy actions configured for this workspace.",
        "action": "POST /autonomy/actions",
    },
    "workflows_active": {
        "severity": "medium",
        "message": "No workflow runs found for this workspace.",
        "action": "POST /workflow-runs",
    },
    "workers_healthy": {
        "severity": "high",
        "message": "Stale workers detected — tasks may be orphaned.",
        "action": "POST /workers/recover-orphaned",
    },
    "recommendations_not_blocked": {
        "severity": "medium",
        "message": "High pending recommendation volume — review queue may be blocked.",
        "action": "GET /recommendations/pending",
    },
    "sources_connected": {
        "severity": "low",
        "message": "No source connections detected for this workspace.",
        "action": "POST /approval-requests",
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _workspace_readiness_6w(db, workspace_slug: str) -> dict:
    """Compute a readiness score (0-100) for a workspace with remediation guidance."""
    checks: dict = {}

    # client_memory_initialized
    try:
        n = db.client_memory.count_documents({"workspace_slug": workspace_slug})
        checks["client_memory_initialized"] = int(n) > 0
    except Exception:
        checks["client_memory_initialized"] = False

    # orchestration_healthy — no stuck orchestrations
    try:
        cutoff = (_datetime_6w.now(_tz_utc_6w) - _td_6w(minutes=60)).isoformat()
        n = db.orchestrations.count_documents({
            "workspace_slug": workspace_slug,
            "status": "running",
            "created_at": {"$lt": cutoff},
        })
        checks["orchestration_healthy"] = int(n) == 0
    except Exception:
        checks["orchestration_healthy"] = True

    # autonomy_configured
    try:
        n = db.autonomy_actions.count_documents({"workspace_slug": workspace_slug})
        checks["autonomy_configured"] = int(n) > 0
    except Exception:
        checks["autonomy_configured"] = False

    # workflows_active
    try:
        n = db.workflow_runs.count_documents({"workspace_slug": workspace_slug})
        checks["workflows_active"] = int(n) > 0
    except Exception:
        checks["workflows_active"] = False

    # workers_healthy
    try:
        wh = _get_worker_health_6u()
        checks["workers_healthy"] = wh["total_workers"] == 0 or wh["stale"] == 0
    except Exception:
        checks["workers_healthy"] = True

    # recommendations_not_blocked
    try:
        n = db.recommendation_statuses.count_documents({
            "workspace_slug": workspace_slug,
            "status": "pending",
        })
        checks["recommendations_not_blocked"] = int(n) < 10
    except Exception:
        checks["recommendations_not_blocked"] = True

    # sources_connected (approval_requests used as proxy)
    try:
        n = db.approval_requests.count_documents({"workspace_slug": workspace_slug})
        checks["sources_connected"] = int(n) > 0
    except Exception:
        checks["sources_connected"] = False

    score = sum(_READINESS_WEIGHTS_6W[k] for k, v in checks.items() if v)

    remediation = {
        k: _REMEDIATION_6W[k]
        for k, v in checks.items()
        if not v and k in _REMEDIATION_6W
    }

    return {
        "workspace_slug": workspace_slug,
        "score": score,
        "max_score": 100,
        "ready": score >= 70,
        "checks": checks,
        "remediation": remediation,
        "evaluated_at": _now_iso_6u(),
    }


def _build_activity_feed_6w(
    db, workspace_slug: str | None, limit: int, severity: str | None
) -> list:
    """Unified chronological activity feed from audit log + orchestration events."""
    events: list = []

    # In-memory audit log
    for entry in _runtime_state_6u.get("audit_log", []):
        sev = _ACTIVITY_SEVERITY_6W.get(entry.get("action", ""), "info")
        if severity and sev != severity:
            continue
        events.append({
            "ts": entry.get("ts", ""),
            "type": entry.get("action", "unknown"),
            "severity": sev,
            "entity": entry.get("resource", ""),
            "actor": entry.get("actor", "system"),
            "trace_id": entry.get("trace_id", ""),
            "nav_link": "#" + entry.get("resource", "").split("/")[0],
            "source": "audit_log",
        })

    # Recent orchestration events from DB
    try:
        cutoff = (_datetime_6w.now(_tz_utc_6w) - _td_6w(minutes=120)).isoformat()
        query: dict = {"created_at": {"$gt": cutoff}}
        if workspace_slug:
            query["workspace_slug"] = workspace_slug
        for orch in db.orchestrations.find(query):
            status = orch.get("status", "unknown")
            sev = "error" if status in ("stuck", "failed") else "info"
            if severity and sev != severity:
                continue
            events.append({
                "ts": orch.get("updated_at", orch.get("created_at", "")),
                "type": f"orchestration_{status}",
                "severity": sev,
                "entity": f"orchestrations/{orch.get('orchestration_id', '')}",
                "actor": "system",
                "trace_id": str(orch.get("_id", "")),
                "nav_link": "#orchestration-dashboard",
                "source": "orchestrations",
            })
    except Exception:
        pass

    events.sort(key=lambda e: e.get("ts", ""), reverse=True)
    return events[:limit]


def _explain_entity_6w(db, entity_type: str, entity_id: str) -> dict:
    """Return an explainability payload for a system entity."""
    base: dict = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "found": False,
        "evidence": [],
        "policy_checks": [],
        "confidence": 0.0,
        "triggering_metrics": {},
        "lineage_refs": [],
        "explanation": "",
        "evaluated_at": _now_iso_6u(),
    }

    col_name = _EXPLAIN_COLLECTION_MAP_6W.get(entity_type)
    if not col_name:
        base["explanation"] = f"Unknown entity type: {entity_type}"
        return base

    # Try ObjectId lookup first, fall back to string field lookup
    doc = None
    try:
        import bson as _bson_6w  # type: ignore[import]
        oid = _bson_6w.ObjectId(entity_id)
        doc = db[col_name].find_one({"_id": oid})
    except Exception:
        pass
    if doc is None:
        id_field = f"{entity_type}_id"
        doc = db[col_name].find_one({id_field: entity_id})

    if not doc:
        base["explanation"] = f"Entity not found: {entity_type}/{entity_id}"
        return base

    meta = doc.get("metadata", doc.get("meta", {})) or {}
    base.update({
        "found": True,
        "evidence": meta.get("evidence", [f"Sourced from collection: {col_name}"]),
        "policy_checks": meta.get("policy_checks", []),
        "confidence": float(doc.get("confidence", meta.get("confidence", 0.8))),
        "triggering_metrics": meta.get("triggering_metrics", {}),
        "lineage_refs": meta.get("lineage_refs", []),
        "explanation": doc.get("explanation", meta.get(
            "explanation",
            f"This {entity_type} was generated by the SignalForge autonomous pipeline.",
        )),
        "status": doc.get("status", "unknown"),
        "workspace_slug": doc.get("workspace_slug", ""),
    })
    return base


def _health_summary_6w(db) -> dict:
    """Unified health indicators across all system dimensions."""
    # MongoDB connectivity
    try:
        db.command("ping")
        mongo_ok = True
    except Exception:
        mongo_ok = False

    # Worker health
    wh = _get_worker_health_6u()
    worker_score = 100 if wh["total_workers"] == 0 else max(0, 100 - wh["stale"] * 25)

    # Orchestration health
    try:
        cutoff = (_datetime_6w.now(_tz_utc_6w) - _td_6w(minutes=60)).isoformat()
        stuck = int(db.orchestrations.count_documents({
            "status": "running",
            "created_at": {"$lt": cutoff},
        }))
        orch_score = max(0, 100 - stuck * 20)
    except Exception:
        orch_score = 100
        stuck = 0

    # Memory health (presence of client memory docs)
    try:
        mem_count = int(db.client_memory.count_documents({}))
        mem_score = min(100, mem_count * 20) if mem_count > 0 else 0
    except Exception:
        mem_score = 0

    # Recommendation quality (accepted ratio)
    try:
        total = int(db.recommendation_statuses.count_documents({}))
        approved = int(db.recommendation_statuses.count_documents({"status": "accepted"}))
        rec_quality = int((approved / total) * 100) if total > 0 else 100
    except Exception:
        rec_quality = 100

    # Autonomy confidence based on request volume
    total_req = _runtime_state_6u.get("total_requests", 0)
    autonomy_confidence = min(100, total_req) if total_req > 0 else 50

    system_health = int((
        (100 if mongo_ok else 0) + worker_score + orch_score
    ) / 3)

    # Reuse Phase 6V pilot readiness
    pilot = _pilot_readiness_6v(db)

    return {
        "system_health": system_health,
        "autonomy_confidence": autonomy_confidence,
        "memory_health": mem_score,
        "orchestration_health": orch_score,
        "worker_health": worker_score,
        "recommendation_quality": rec_quality,
        "pilot_readiness": pilot["score"],
        "pilot_ready": pilot["ready"],
        "indicators": {
            "mongodb":         "ok" if mongo_ok else "error",
            "workers":         "ok" if wh["stale"] == 0 else "degraded",
            "orchestrations":  "ok" if stuck == 0 else "degraded",
        },
        "evaluated_at": _now_iso_6u(),
    }


def _seed_demo_workspace_6w(db, workspace_slug: str) -> dict:
    """Insert sample entities for a demo/pilot workspace."""
    created: dict = {k: 0 for k in _DEMO_SEED_6W}
    now = _now_iso_6u()

    # Workflow runs
    wf_docs = [
        {
            "workspace_slug": workspace_slug,
            "workflow_id": f"demo-wf-{i + 1}",
            "status": ["completed", "running", "pending"][i % 3],
            "created_at": now, "updated_at": now,
            "metadata": {"demo": True, "step": i + 1},
        }
        for i in range(_DEMO_SEED_6W["workflows"])
    ]
    try:
        db.workflow_runs.insert_many(wf_docs)
        created["workflows"] = len(wf_docs)
    except Exception:
        pass

    # Orchestrations
    orch_docs = [
        {
            "workspace_slug": workspace_slug,
            "orchestration_id": f"demo-orch-{i + 1}",
            "status": "running",
            "created_at": now, "updated_at": now,
            "metadata": {"demo": True},
        }
        for i in range(_DEMO_SEED_6W["orchestrations"])
    ]
    try:
        db.orchestrations.insert_many(orch_docs)
        created["orchestrations"] = len(orch_docs)
    except Exception:
        pass

    # Recommendations
    rec_docs = [
        {
            "workspace_slug": workspace_slug,
            "recommendation_id": f"demo-rec-{i + 1}",
            "status": ["pending", "accepted", "rejected"][i % 3],
            "confidence": round(0.60 + i * 0.08, 2),
            "explanation": f"Demo recommendation {i + 1}: optimize campaign targeting.",
            "metadata": {"demo": True, "evidence": ["signal_score > 0.7"]},
            "created_at": now,
        }
        for i in range(_DEMO_SEED_6W["recommendations"])
    ]
    try:
        db.recommendation_statuses.insert_many(rec_docs)
        created["recommendations"] = len(rec_docs)
    except Exception:
        pass

    # Autonomy actions
    auto_docs = [
        {
            "workspace_slug": workspace_slug,
            "action_id": f"demo-auto-{i + 1}",
            "action_type": ["outreach_send", "memory_update", "workflow_trigger"][i % 3],
            "status": "applied",
            "confidence": 0.75,
            "created_at": now,
            "metadata": {"demo": True},
        }
        for i in range(_DEMO_SEED_6W["autonomy_actions"])
    ]
    try:
        db.autonomy_actions.insert_many(auto_docs)
        created["autonomy_actions"] = len(auto_docs)
    except Exception:
        pass

    # Client memory
    mem_docs = [
        {
            "workspace_slug": workspace_slug,
            "key": f"demo_signal_{i + 1}",
            "value": {"score": round(0.5 + i * 0.1, 2), "source": "demo"},
            "updated_at": now,
            "metadata": {"demo": True},
        }
        for i in range(_DEMO_SEED_6W["memory_entries"])
    ]
    try:
        db.client_memory.insert_many(mem_docs)
        created["memory_entries"] = len(mem_docs)
    except Exception:
        pass

    _append_audit_6u("system", "demo_workspace_seeded", f"demo/{workspace_slug}",
                     entities=created)

    return {
        "workspace_slug": workspace_slug,
        "created": created,
        "total_entities": sum(created.values()),
        "seeded_at": now,
    }


# ── Pydantic models ───────────────────────────────────────────────────────────

class DemoSeedRequest6W(BaseModel):
    workspace_slug: str = "demo-workspace"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/activity-feed", tags=["operator-ux"])
def activity_feed_6w(
    workspace_slug: str | None = None,
    limit: int = 50,
    severity: str | None = None,
) -> dict:
    """Unified chronological activity feed (audit + orchestration events)."""
    c = get_client()
    db = get_database(c)
    try:
        events = _build_activity_feed_6w(db, workspace_slug, min(limit, 200), severity)
        return {"events": events, "count": len(events), "retrieved_at": _now_iso_6u()}
    finally:
        c.close()


@app.get("/workspace-readiness", tags=["operator-ux"])
def workspace_readiness_6w(workspace_slug: str) -> dict:
    """Compute workspace readiness score with remediation guidance."""
    c = get_client()
    db = get_database(c)
    try:
        return _workspace_readiness_6w(db, workspace_slug)
    finally:
        c.close()


@app.get("/explainability/{entity_type}/{entity_id}", tags=["operator-ux"])
def explainability_6w(entity_type: str, entity_id: str) -> dict:
    """Return explainability payload for any autonomous system entity."""
    c = get_client()
    db = get_database(c)
    try:
        return _explain_entity_6w(db, entity_type, entity_id)
    finally:
        c.close()


@app.get("/health-summary", tags=["operator-ux"])
def health_summary_6w() -> dict:
    """Unified health summary across all system dimensions."""
    c = get_client()
    db = get_database(c)
    try:
        return _health_summary_6w(db)
    finally:
        c.close()


@app.post("/demo-workspace/seed", tags=["operator-ux"])
def demo_workspace_seed_6w(req: DemoSeedRequest6W = DemoSeedRequest6W()) -> dict:
    """Seed a demo workspace with sample entities for pilots, demos, and QA."""
    c = get_client()
    db = get_database(c)
    try:
        return _seed_demo_workspace_6w(db, req.workspace_slug)
    finally:
        c.close()


@app.get("/role-capabilities", tags=["operator-ux"])
def role_capabilities_6w(role: str = "operator") -> dict:
    """Return capability set for a given role."""
    caps = _ROLE_CAPABILITIES_6W.get(role)
    if caps is None:
        from fastapi import HTTPException as _HTTPException_6w
        raise _HTTPException_6w(
            status_code=400,
            detail=f"Unknown role: '{role}'. Valid roles: {list(_ROLE_CAPABILITIES_6W)}",
        )
    return {
        "role": role,
        "capabilities": caps,
        "all_roles": list(_ROLE_CAPABILITIES_6W),
    }

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PHASE 6X — First Live External Workflow Execution (LinkedIn Pilot)         ║
# ║  Appended to main.py                                                         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

import secrets as _secrets_6x

# ── Constants ─────────────────────────────────────────────────────────────────

_DISTRIBUTION_STATES_6X = [
    "pending", "verified", "failed", "retrying", "escalated"
]

_PUBLISH_RETRY_LIMITS_6X = {
    "token_expired":   3,
    "network_failure": 4,
    "rate_limit":      3,
    "rejection":       1,  # no auto-retry on explicit rejection
}

_TELEMETRY_KEYS_6X = [
    "publish_success_rate",
    "publish_latency_ms",
    "retry_frequency",
    "verification_failures",
    "distribution_completion_rate",
    "external_api_latency_ms",
]

_LINKEDIN_SIGNAL_THRESHOLDS_6X = {
    "success_rate_high":  0.90,
    "success_rate_low":   0.70,
    "latency_fast_ms":    3000,
    "latency_slow_ms":    10000,
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_linkedin_integration_6x(db: Any, workspace_slug: str) -> dict | None:
    """Return the stored LinkedIn integration record for a workspace, or None."""
    try:
        rec = db.external_integrations.find_one(
            {"workspace_slug": workspace_slug, "provider": "linkedin"}
        )
        if rec:
            rec.pop("_id", None)
            # Never return raw tokens in API responses
            rec.pop("access_token", None)
            rec.pop("refresh_token", None)
        return rec
    except Exception:
        return None


def _upsert_linkedin_integration_6x(db: Any, workspace_slug: str, update: dict) -> None:
    """Insert or update a LinkedIn integration record."""
    update.setdefault("workspace_slug", workspace_slug)
    update.setdefault("provider", "linkedin")
    update["updated_at"] = _now_iso_6u()
    try:
        db.external_integrations.update_one(
            {"workspace_slug": workspace_slug, "provider": "linkedin"},
            {"$set": update},
            upsert=True,
        )
    except Exception:
        pass


def _create_distribution_attempt_6x(
    db: Any,
    workspace_slug: str,
    workflow_asset_id: str,
    content_text: str,
) -> dict:
    """Create and persist a new distribution_attempts record; returns the full record."""
    attempt_id = f"da_{_secrets_6x.token_hex(8)}"
    now = _now_iso_6u()
    doc = {
        "distribution_attempt_id": attempt_id,
        "workspace_slug":          workspace_slug,
        "workflow_asset_id":       workflow_asset_id,
        "provider":                "linkedin",
        "status":                  "pending",
        "distribution_verification_status": "pending",
        "content_text":            content_text,
        "external_post_id":        None,
        "published_url":           None,
        "request_trace_id":        None,
        "retry_count":             0,
        "verified":                False,
        "escalated":               False,
        "created_at":              now,
        "updated_at":              now,
        "metadata":                {},
    }
    try:
        db.distribution_attempts.insert_one(doc.copy())
    except Exception:
        pass
    doc.pop("_id", None)
    _append_audit_6u("system", "distribution_attempt_created",
                     f"distribution/{attempt_id}",
                     workspace=workspace_slug, provider="linkedin")
    return doc


def _update_distribution_attempt_6x(db: Any, attempt_id: str, update: dict) -> None:
    """Patch an existing distribution_attempts record."""
    update["updated_at"] = _now_iso_6u()
    try:
        db.distribution_attempts.update_one(
            {"distribution_attempt_id": attempt_id},
            {"$set": update},
        )
    except Exception:
        pass


def _get_distribution_attempt_6x(db: Any, attempt_id: str) -> dict | None:
    try:
        rec = db.distribution_attempts.find_one({"distribution_attempt_id": attempt_id})
        if rec:
            rec.pop("_id", None)
        return rec
    except Exception:
        return None


def _check_duplicate_publish_6x(db: Any, workflow_asset_id: str) -> bool:
    """
    Return True if a successful (verified) publish already exists for this asset.
    Prevents accidental duplicate publishing.
    """
    try:
        existing = db.distribution_attempts.count_documents({
            "workflow_asset_id": workflow_asset_id,
            "provider":          "linkedin",
            "verified":          True,
        })
        return int(existing) > 0
    except Exception:
        return False


def _simulate_linkedin_publish_6x(content_text: str, author_urn: str,
                                   idempotency_key: str) -> dict:
    """
    Internal simulation of LinkedIn publish for environments where live
    LinkedIn credentials are not configured.  Returns a deterministic stub
    response that mimics the real client output.
    """
    stub_id = f"urn:li:share:{abs(hash(idempotency_key)) % 10_000_000_000}"
    return {
        "external_post_id": stub_id,
        "published_url":    f"https://www.linkedin.com/feed/update/{stub_id}",
        "request_trace_id": f"sim_{_secrets_6x.token_hex(6)}",
        "published_at":     _now_iso_6u(),
        "raw_response":     {"id": stub_id, "lifecycleState": "PUBLISHED", "_simulated": True},
        "_simulated":       True,
    }


def _execute_linkedin_publish_6x(
    db: Any, workspace_slug: str, attempt: dict
) -> dict:
    """
    Core publish execution — uses live LinkedIn client if token available,
    otherwise falls back to simulation.  Mutates and persists the attempt record.
    """
    attempt_id      = attempt["distribution_attempt_id"]
    asset_id        = attempt["workflow_asset_id"]
    content_text    = attempt["content_text"]
    idempotency_key = f"{workspace_slug}:{asset_id}"

    # Fetch token from DB (not returned to callers)
    access_token: str | None = None
    author_urn: str = "urn:li:person:placeholder"
    try:
        raw = db.external_integrations.find_one(
            {"workspace_slug": workspace_slug, "provider": "linkedin"}
        )
        if raw:
            access_token = raw.get("access_token")
            author_urn   = raw.get("author_urn", author_urn)
    except Exception:
        pass

    simulated = False
    try:
        if access_token:
            # Real execution path
            from linkedin_client import (
                publish_post,
                LinkedInDuplicateError,
                LinkedInTokenExpiredError,
                LinkedInPublishError,
                refresh_access_token,
            )
            try:
                result = publish_post(access_token, author_urn, content_text,
                                      idempotency_key=idempotency_key)
            except LinkedInTokenExpiredError:
                # Attempt token refresh
                try:
                    raw2 = db.external_integrations.find_one(
                        {"workspace_slug": workspace_slug, "provider": "linkedin"}
                    )
                    refresh_token = raw2.get("refresh_token") if raw2 else None
                    if refresh_token:
                        token_data = refresh_access_token(refresh_token)
                        _upsert_linkedin_integration_6x(db, workspace_slug, {
                            "access_token": token_data["access_token"],
                            "refresh_token": token_data.get("refresh_token", refresh_token),
                        })
                        result = publish_post(token_data["access_token"], author_urn,
                                              content_text, idempotency_key=idempotency_key)
                    else:
                        raise
                except Exception as exc2:
                    _update_distribution_attempt_6x(db, attempt_id, {
                        "status": "failed",
                        "distribution_verification_status": "failed",
                        "failure_reason": f"token_refresh_failed: {str(exc2)[:200]}",
                    })
                    _append_audit_6u("system", "distribution_publish_failed",
                                     f"distribution/{attempt_id}",
                                     reason="token_refresh_failed", workspace=workspace_slug)
                    return {**attempt, "status": "failed", "failure_reason": str(exc2)[:200]}
        else:
            # Simulation fallback
            result = _simulate_linkedin_publish_6x(content_text, author_urn, idempotency_key)
            simulated = True
    except Exception as exc:
        retry_count = attempt.get("retry_count", 0)
        new_status  = "retrying" if retry_count < _PUBLISH_RETRY_LIMITS_6X["network_failure"] else "failed"
        _update_distribution_attempt_6x(db, attempt_id, {
            "status":                  new_status,
            "distribution_verification_status": "failed",
            "failure_reason":          str(exc)[:300],
            "retry_count":             retry_count + 1,
        })
        _append_audit_6u("system", "distribution_publish_failed",
                         f"distribution/{attempt_id}",
                         reason=str(exc)[:200], workspace=workspace_slug)
        return {**attempt, "status": new_status, "failure_reason": str(exc)[:200]}

    # Success — persist result
    updates = {
        "status":                  "verified" if result.get("external_post_id") else "failed",
        "distribution_verification_status": "verified" if result.get("external_post_id") else "failed",
        "external_post_id":        result.get("external_post_id"),
        "published_url":           result.get("published_url"),
        "request_trace_id":        result.get("request_trace_id"),
        "verified":                bool(result.get("external_post_id")),
        "published_at":            result.get("published_at"),
        "simulated":               simulated,
        "metadata":                {"raw_response": result.get("raw_response", {})},
    }
    _update_distribution_attempt_6x(db, attempt_id, updates)

    _append_audit_6u("system", "distribution_published",
                     f"distribution/{attempt_id}",
                     provider="linkedin",
                     post_id=result.get("external_post_id"),
                     workspace=workspace_slug,
                     simulated=simulated)

    # Generate recommendation signal on successful publish
    _generate_publish_signal_6x(db, workspace_slug, attempt_id, result)

    return {**attempt, **updates}


def _generate_publish_signal_6x(db: Any, workspace_slug: str,
                                  attempt_id: str, publish_result: dict) -> None:
    """
    On successful publish, insert a recommendation_signal and memory_proposal
    for the learning loop.
    """
    now = _now_iso_6u()
    signal = {
        "workspace_slug": workspace_slug,
        "signal_type":    "distribution_success",
        "provider":       "linkedin",
        "attempt_id":     attempt_id,
        "post_id":        publish_result.get("external_post_id"),
        "created_at":     now,
        "metadata":       {"channel": "linkedin", "source": "6x_publish_loop"},
    }
    proposal = {
        "workspace_slug": workspace_slug,
        "key":            "linkedin_distribution_success_count",
        "proposed_value": {"increment": 1, "last_post_id": publish_result.get("external_post_id")},
        "source":         "6x_publish_signal",
        "created_at":     now,
    }
    try:
        db.recommendation_signals.insert_one(signal)
    except Exception:
        pass
    try:
        db.memory_proposals.insert_one(proposal)
    except Exception:
        pass


def _build_distribution_telemetry_6x(db: Any, workspace_slug: str | None) -> dict:
    """
    Compute delivery telemetry metrics for the telemetry / analytics dashboards.
    """
    q: dict = {}
    if workspace_slug:
        q["workspace_slug"] = workspace_slug
    q_li = {**q, "provider": "linkedin"}
    now  = _now_iso_6u()
    try:
        total        = int(db.distribution_attempts.count_documents(q_li))
        verified     = int(db.distribution_attempts.count_documents({**q_li, "verified": True}))
        failed       = int(db.distribution_attempts.count_documents({**q_li, "status": "failed"}))
        retrying     = int(db.distribution_attempts.count_documents({**q_li, "status": "retrying"}))
        escalated    = int(db.distribution_attempts.count_documents({**q_li, "status": "escalated"}))
        pending      = int(db.distribution_attempts.count_documents({**q_li, "status": "pending"}))

        success_rate = round(verified / total, 3) if total > 0 else 0.0
        channels     = {"linkedin": {"total": total, "verified": verified,
                                     "failed": failed, "retrying": retrying}}
        # Instagram channel appended below; resolved at call time since the whole
        # module is loaded before any request is handled (function defined later
        # in this file, same pattern as every other forward-reference here).
        channels["instagram"] = _build_instagram_distribution_telemetry_ig(db, workspace_slug)
    except Exception:
        total = verified = failed = retrying = escalated = pending = 0
        success_rate = 0.0
        channels     = {}

    return {
        "workspace_slug":       workspace_slug,
        "publish_success_rate": success_rate,
        "publish_latency_ms":   None,         # populated from real execution data
        "retry_frequency":      retrying,
        "verification_failures": failed,
        "distribution_completion_rate": success_rate,
        "external_api_latency_ms": None,      # populated from real execution data
        "totals": {
            "total": total, "verified": verified, "failed": failed,
            "retrying": retrying, "escalated": escalated, "pending": pending,
        },
        "channels":  channels,
        "evaluated_at": now,
    }


def _get_all_external_executions_6x(db: Any, workspace_slug: str | None,
                                     limit: int) -> list[dict]:
    """Return a list of distribution_attempts, newest first."""
    q: dict = {}
    if workspace_slug:
        q["workspace_slug"] = workspace_slug
    results = []
    try:
        cursor = db.distribution_attempts.find(q).sort("created_at", -1).limit(limit)
        for doc in cursor:
            doc.pop("_id", None)
            results.append(doc)
    except Exception:
        pass
    return results


# ── Pydantic Models ────────────────────────────────────────────────────────────

class LinkedInPublishRequest6X(BaseModel):
    workspace_slug:    str
    workflow_asset_id: str
    content_text:      str


class LinkedInRetryRequest6X(BaseModel):
    workspace_slug: str


class LinkedInCallbackRequest6X(BaseModel):
    code:  str
    state: str
    workspace_slug: str = "default"


# ── Endpoints ─────────────────────────────────────────────────────────────────

# OAuth

@app.get("/connect/linkedin/status", tags=["linkedin"])
def linkedin_connection_status_6x(workspace_slug: str = "default") -> dict:
    """Return LinkedIn connection status for a workspace."""
    c = get_client()
    db = get_database(c)
    try:
        integration = _get_linkedin_integration_6x(db, workspace_slug)
        if not integration:
            return {
                "workspace_slug": workspace_slug,
                "provider":       "linkedin",
                "status":         "not_connected",
                "connected":      False,
            }
        return {
            "workspace_slug": workspace_slug,
            "provider":       "linkedin",
            "status":         integration.get("status", "unknown"),
            "connected":      integration.get("status") == "connected",
            "connected_by":   integration.get("connected_by"),
            "expires_at":     integration.get("expires_at"),
            "created_at":     integration.get("created_at"),
        }
    finally:
        c.close()


@app.post("/connect/linkedin/start", tags=["linkedin"])
def linkedin_connect_start_6x(workspace_slug: str = "default") -> dict:
    """Generate a LinkedIn OAuth authorization URL and persist a state token."""
    from linkedin_client import build_authorization_url, LINKEDIN_CLIENT_ID
    state = _secrets_6x.token_hex(16)
    c = get_client()
    db = get_database(c)
    try:
        # Persist state for callback verification
        _upsert_linkedin_integration_6x(db, workspace_slug, {
            "status":       "pending_oauth",
            "oauth_state":  state,
            "connected_by": "operator",
            "created_at":   _now_iso_6u(),
        })
        auth_url = build_authorization_url(state)
        _append_audit_6u("operator", "linkedin_oauth_started",
                         f"connect/{workspace_slug}")
        return {
            "workspace_slug":   workspace_slug,
            "authorization_url": auth_url,
            "state":            state,
            "client_configured": bool(LINKEDIN_CLIENT_ID),
        }
    finally:
        c.close()


@app.get("/connect/linkedin/callback", tags=["linkedin"])
def linkedin_connect_callback_6x(
    code: str,
    state: str,
    workspace_slug: str = "default",
) -> dict:
    """
    Handle LinkedIn OAuth callback — exchange code for token and persist.
    In a real deployment this endpoint is hit by the browser after LinkedIn redirect.
    """
    from linkedin_client import exchange_code_for_token, LINKEDIN_CLIENT_ID
    from datetime import timedelta

    c = get_client()
    db = get_database(c)
    try:
        # Verify state
        rec = db.external_integrations.find_one(
            {"workspace_slug": workspace_slug, "provider": "linkedin"}
        )
        stored_state = rec.get("oauth_state") if rec else None
        if stored_state and stored_state != state:
            from fastapi import HTTPException as _HTTPException_6x
            raise _HTTPException_6x(status_code=400, detail="OAuth state mismatch — possible CSRF")

        if not LINKEDIN_CLIENT_ID:
            # Simulation mode — store a placeholder token
            expires_at = _now_iso_6u()
            _upsert_linkedin_integration_6x(db, workspace_slug, {
                "status":        "connected",
                "access_token":  f"sim_{_secrets_6x.token_hex(16)}",
                "refresh_token": f"sim_rt_{_secrets_6x.token_hex(16)}",
                "expires_at":    expires_at,
                "author_urn":    "urn:li:person:simulated",
                "oauth_state":   None,
                "simulated":     True,
            })
            _append_audit_6u("operator", "linkedin_oauth_completed",
                             f"connect/{workspace_slug}", simulated=True)
            return {"workspace_slug": workspace_slug, "status": "connected",
                    "simulated": True}

        token_data = exchange_code_for_token(code)
        expires_sec = token_data.get("expires_in", 5184000)
        expires_dt  = datetime.now(timezone.utc) + timedelta(seconds=expires_sec)
        _upsert_linkedin_integration_6x(db, workspace_slug, {
            "status":        "connected",
            "access_token":  token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_at":    expires_dt.isoformat(),
            "oauth_state":   None,
            "simulated":     False,
        })
        _append_audit_6u("operator", "linkedin_oauth_completed",
                         f"connect/{workspace_slug}", simulated=False)
        return {"workspace_slug": workspace_slug, "status": "connected", "simulated": False}
    finally:
        c.close()


# Distribution

@app.post("/distribution/linkedin/publish", tags=["linkedin"])
def linkedin_publish_6x(req: LinkedInPublishRequest6X) -> dict:
    """
    Publish a content asset to LinkedIn.
    Performs duplicate-publish check before executing.
    """
    c = get_client()
    db = get_database(c)
    try:
        if _check_duplicate_publish_6x(db, req.workflow_asset_id):
            from fastapi import HTTPException as _HTTPException_6x
            raise _HTTPException_6x(
                status_code=409,
                detail=f"Asset {req.workflow_asset_id!r} has already been verified as published to LinkedIn.",
            )
        attempt = _create_distribution_attempt_6x(
            db, req.workspace_slug, req.workflow_asset_id, req.content_text
        )
        result = _execute_linkedin_publish_6x(db, req.workspace_slug, attempt)
        return result
    finally:
        c.close()


@app.post("/distribution/linkedin/retry", tags=["linkedin"])
def linkedin_retry_6x(attempt_id: str, req: LinkedInRetryRequest6X) -> dict:
    """
    Manually retry a failed or retrying distribution attempt.
    Requires operator acknowledgment (body required).
    """
    c = get_client()
    db = get_database(c)
    try:
        attempt = _get_distribution_attempt_6x(db, attempt_id)
        if not attempt:
            from fastapi import HTTPException as _HTTPException_6x
            raise _HTTPException_6x(status_code=404, detail=f"Attempt {attempt_id!r} not found")
        if attempt.get("status") not in ("failed", "retrying"):
            from fastapi import HTTPException as _HTTPException_6x
            raise _HTTPException_6x(
                status_code=400,
                detail=f"Cannot retry attempt in state: {attempt.get('status')!r}"
            )
        retry_count = attempt.get("retry_count", 0)
        max_retries = _PUBLISH_RETRY_LIMITS_6X["network_failure"]
        if retry_count >= max_retries:
            _update_distribution_attempt_6x(db, attempt_id, {"status": "escalated", "escalated": True})
            _append_audit_6u("operator", "distribution_escalated",
                             f"distribution/{attempt_id}",
                             workspace=req.workspace_slug)
            return {**attempt, "status": "escalated",
                    "message": "Retry limit reached — attempt escalated for operator review"}

        _append_audit_6u("operator", "distribution_retry_requested",
                         f"distribution/{attempt_id}",
                         workspace=req.workspace_slug, retry_count=retry_count + 1)
        result = _execute_linkedin_publish_6x(db, req.workspace_slug, attempt)
        return result
    finally:
        c.close()


@app.get("/distribution/linkedin/{attempt_id}/status", tags=["linkedin"])
def linkedin_attempt_status_6x(attempt_id: str) -> dict:
    """Return the current status of a distribution attempt."""
    c = get_client()
    db = get_database(c)
    try:
        attempt = _get_distribution_attempt_6x(db, attempt_id)
        if not attempt:
            from fastapi import HTTPException as _HTTPException_6x
            raise _HTTPException_6x(status_code=404, detail=f"Attempt {attempt_id!r} not found")
        return attempt
    finally:
        c.close()


# External Executions (audit trail)

@app.get("/external-executions", tags=["linkedin"])
def external_executions_list_6x(
    workspace_slug: str | None = None,
    limit: int = 50,
) -> dict:
    """Return a paginated list of all external distribution execution records."""
    c = get_client()
    db = get_database(c)
    try:
        items = _get_all_external_executions_6x(db, workspace_slug, min(limit, 200))
        return {"executions": items, "count": len(items), "retrieved_at": _now_iso_6u()}
    finally:
        c.close()


@app.get("/external-executions/{attempt_id}", tags=["linkedin"])
def external_execution_detail_6x(attempt_id: str) -> dict:
    """Return full detail for a single external execution record."""
    c = get_client()
    db = get_database(c)
    try:
        attempt = _get_distribution_attempt_6x(db, attempt_id)
        if not attempt:
            from fastapi import HTTPException as _HTTPException_6x
            raise _HTTPException_6x(status_code=404, detail=f"Execution {attempt_id!r} not found")
        return attempt
    finally:
        c.close()


# Telemetry

@app.get("/distribution/telemetry", tags=["linkedin"])
def distribution_telemetry_6x(workspace_slug: str | None = None) -> dict:
    """Delivery telemetry metrics for LinkedIn distribution channel."""
    c = get_client()
    db = get_database(c)
    try:
        return _build_distribution_telemetry_6x(db, workspace_slug)
    finally:
        c.close()

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Pillar 2 — Instagram Publishing                                             ║
# ║  Mirrors the Phase 6X LinkedIn block above. Appended to main.py              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

import secrets as _secrets_ig

# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_instagram_integration_ig(db: Any, workspace_slug: str) -> dict | None:
    """Return the stored Instagram integration record for a workspace, or None."""
    try:
        rec = db.external_integrations.find_one(
            {"workspace_slug": workspace_slug, "provider": "instagram"}
        )
        if rec:
            rec.pop("_id", None)
            # Never return raw tokens in API responses
            rec.pop("access_token", None)
        return rec
    except Exception:
        return None


def _upsert_instagram_integration_ig(db: Any, workspace_slug: str, update: dict) -> None:
    """Insert or update an Instagram integration record."""
    update.setdefault("workspace_slug", workspace_slug)
    update.setdefault("provider", "instagram")
    update["updated_at"] = _now_iso_6u()
    try:
        db.external_integrations.update_one(
            {"workspace_slug": workspace_slug, "provider": "instagram"},
            {"$set": update},
            upsert=True,
        )
    except Exception:
        pass


def _find_asset_render_ig(db: Any, render_id: str) -> dict | None:
    try:
        query: dict = {"_id": render_id}
        if ObjectId.is_valid(render_id):
            query = {"$or": [{"_id": ObjectId(render_id)}, {"_id": render_id}]}
        return db.asset_renders.find_one(query)
    except Exception:
        return None


def _create_distribution_attempt_ig(
    db: Any,
    workspace_slug: str,
    source_asset_render_id: str,
    caption: str,
    media_url: str,
    media_type: str,
) -> dict:
    """Create and persist a new Instagram distribution_attempts record; returns the full record."""
    attempt_id = f"da_{_secrets_ig.token_hex(8)}"
    now = _now_iso_6u()
    doc = {
        "distribution_attempt_id": attempt_id,
        "workspace_slug":          workspace_slug,
        "source_asset_render_id":  source_asset_render_id,
        "provider":                "instagram",
        "status":                  "pending",
        "distribution_verification_status": "pending",
        "caption":                 caption,
        "media_url":               media_url,
        "media_type":              media_type,
        "external_post_id":        None,
        "published_url":           None,
        "retry_count":             0,
        "verified":                False,
        "escalated":               False,
        "created_at":              now,
        "updated_at":              now,
        "metadata":                {},
    }
    try:
        db.distribution_attempts.insert_one(doc.copy())
    except Exception:
        pass
    doc.pop("_id", None)
    _append_audit_6u("system", "distribution_attempt_created",
                     f"distribution/{attempt_id}",
                     workspace=workspace_slug, provider="instagram")
    return doc


def _check_duplicate_publish_ig(db: Any, source_asset_render_id: str) -> bool:
    """Return True if a successful (verified) Instagram publish already exists for this render."""
    try:
        existing = db.distribution_attempts.count_documents({
            "source_asset_render_id": source_asset_render_id,
            "provider":               "instagram",
            "verified":               True,
        })
        return int(existing) > 0
    except Exception:
        return False


def _simulate_instagram_publish_ig(source_asset_render_id: str) -> dict:
    """
    Internal simulation of Instagram publish for environments where live
    Instagram credentials are not configured. Returns a deterministic stub
    response that mimics the real client output.
    """
    stub_id = f"ig_{abs(hash(source_asset_render_id)) % 10_000_000_000}"
    return {
        "external_post_id": stub_id,
        "published_url":    f"https://www.instagram.com/p/{stub_id}/",
        "published_at":     _now_iso_6u(),
        "raw_response":     {"id": stub_id, "_simulated": True},
        "_simulated":       True,
    }


def _execute_instagram_publish_ig(
    db: Any, workspace_slug: str, attempt: dict
) -> dict:
    """
    Core publish execution — uses live Instagram client if token available,
    otherwise falls back to simulation. Mutates and persists the attempt record.
    """
    attempt_id = attempt["distribution_attempt_id"]
    render_id  = attempt["source_asset_render_id"]

    access_token: str | None = None
    ig_user_id: str = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
    try:
        raw = db.external_integrations.find_one(
            {"workspace_slug": workspace_slug, "provider": "instagram"}
        )
        if raw:
            access_token = raw.get("access_token")
            ig_user_id   = raw.get("ig_user_id") or ig_user_id
    except Exception:
        pass

    simulated = False
    try:
        if access_token and ig_user_id:
            from instagram_client import (
                create_media_container,
                publish_container,
                InstagramTokenExpiredError,
                InstagramPublishError,
            )
            try:
                container = create_media_container(
                    access_token, ig_user_id, attempt["media_url"],
                    attempt.get("caption", ""), attempt.get("media_type", "IMAGE"),
                )
                result = publish_container(access_token, ig_user_id, container["creation_id"])
            except InstagramTokenExpiredError as exc:
                _update_distribution_attempt_6x(db, attempt_id, {
                    "status": "failed",
                    "distribution_verification_status": "failed",
                    "failure_reason": f"token_expired: {str(exc)[:200]}",
                })
                _append_audit_6u("system", "distribution_publish_failed",
                                 f"distribution/{attempt_id}",
                                 reason="token_expired", workspace=workspace_slug)
                return {**attempt, "status": "failed", "failure_reason": str(exc)[:200]}
        else:
            # Simulation fallback — INSTAGRAM_ENABLED not true, or no token/ig_user_id configured
            result = _simulate_instagram_publish_ig(render_id)
            simulated = True
    except Exception as exc:
        retry_count = attempt.get("retry_count", 0)
        new_status  = "retrying" if retry_count < _PUBLISH_RETRY_LIMITS_6X["network_failure"] else "failed"
        _update_distribution_attempt_6x(db, attempt_id, {
            "status":                  new_status,
            "distribution_verification_status": "failed",
            "failure_reason":          str(exc)[:300],
            "retry_count":             retry_count + 1,
        })
        _append_audit_6u("system", "distribution_publish_failed",
                         f"distribution/{attempt_id}",
                         reason=str(exc)[:200], workspace=workspace_slug)
        return {**attempt, "status": new_status, "failure_reason": str(exc)[:300]}

    updates = {
        "status":                  "verified" if result.get("external_post_id") else "failed",
        "distribution_verification_status": "verified" if result.get("external_post_id") else "failed",
        "external_post_id":        result.get("external_post_id"),
        "published_url":           result.get("published_url"),
        "verified":                bool(result.get("external_post_id")),
        "published_at":            result.get("published_at"),
        "simulated":               simulated,
        "metadata":                {"raw_response": result.get("raw_response", {})},
    }
    _update_distribution_attempt_6x(db, attempt_id, updates)

    _append_audit_6u("system", "distribution_published",
                     f"distribution/{attempt_id}",
                     provider="instagram",
                     post_id=result.get("external_post_id"),
                     workspace=workspace_slug,
                     simulated=simulated)

    _generate_instagram_publish_signal_ig(db, workspace_slug, attempt_id, result)

    return {**attempt, **updates}


def _generate_instagram_publish_signal_ig(db: Any, workspace_slug: str,
                                            attempt_id: str, publish_result: dict) -> None:
    """
    On successful publish, insert a recommendation_signal and memory_proposal
    for the learning loop — mirrors _generate_publish_signal_6x for LinkedIn.
    """
    now = _now_iso_6u()
    signal = {
        "workspace_slug": workspace_slug,
        "signal_type":    "distribution_success",
        "provider":       "instagram",
        "attempt_id":     attempt_id,
        "post_id":        publish_result.get("external_post_id"),
        "created_at":     now,
        "metadata":       {"channel": "instagram", "source": "instagram_publish_loop"},
    }
    proposal = {
        "workspace_slug": workspace_slug,
        "key":            "instagram_distribution_success_count",
        "proposed_value": {"increment": 1, "last_post_id": publish_result.get("external_post_id")},
        "source":         "instagram_publish_signal",
        "created_at":     now,
    }
    try:
        db.recommendation_signals.insert_one(signal)
    except Exception:
        pass
    try:
        db.memory_proposals.insert_one(proposal)
    except Exception:
        pass


def _build_instagram_distribution_telemetry_ig(db: Any, workspace_slug: str | None) -> dict:
    """Delivery telemetry for the Instagram channel — same shape as LinkedIn's."""
    q: dict = {}
    if workspace_slug:
        q["workspace_slug"] = workspace_slug
    q_ig = {**q, "provider": "instagram"}
    try:
        total     = int(db.distribution_attempts.count_documents(q_ig))
        verified  = int(db.distribution_attempts.count_documents({**q_ig, "verified": True}))
        failed    = int(db.distribution_attempts.count_documents({**q_ig, "status": "failed"}))
        retrying  = int(db.distribution_attempts.count_documents({**q_ig, "status": "retrying"}))
        return {"total": total, "verified": verified, "failed": failed, "retrying": retrying}
    except Exception:
        return {"total": 0, "verified": 0, "failed": 0, "retrying": 0}


# ── Pydantic Models ────────────────────────────────────────────────────────────

class InstagramPublishRequest(BaseModel):
    workspace_slug:          str
    source_asset_render_id:  str
    caption:                 str
    media_url:               str
    media_type:              Literal["IMAGE", "REELS"] = "IMAGE"


class InstagramRetryRequest(BaseModel):
    workspace_slug: str


class InstagramCallbackRequest(BaseModel):
    code:  str
    state: str
    workspace_slug: str = "default"


# ── Endpoints ─────────────────────────────────────────────────────────────────

# OAuth

@app.get("/connect/instagram/status", tags=["instagram"])
def instagram_connection_status(workspace_slug: str = "default") -> dict:
    """Return Instagram connection status for a workspace."""
    c = get_client()
    db = get_database(c)
    try:
        integration = _get_instagram_integration_ig(db, workspace_slug)
        if not integration:
            return {
                "workspace_slug": workspace_slug,
                "provider":       "instagram",
                "status":         "not_connected",
                "connected":      False,
            }
        return {
            "workspace_slug": workspace_slug,
            "provider":       "instagram",
            "status":         integration.get("status", "unknown"),
            "connected":      integration.get("status") == "connected",
            "connected_by":   integration.get("connected_by"),
            "expires_at":     integration.get("expires_at"),
            "created_at":     integration.get("created_at"),
        }
    finally:
        c.close()


@app.post("/connect/instagram/start", tags=["instagram"])
def instagram_connect_start(workspace_slug: str = "default") -> dict:
    """Generate an Instagram (Facebook Login) OAuth authorization URL and persist a state token."""
    from instagram_client import build_authorization_url, INSTAGRAM_CLIENT_ID
    state = _secrets_ig.token_hex(16)
    c = get_client()
    db = get_database(c)
    try:
        _upsert_instagram_integration_ig(db, workspace_slug, {
            "status":       "pending_oauth",
            "oauth_state":  state,
            "connected_by": "operator",
            "created_at":   _now_iso_6u(),
        })
        auth_url = build_authorization_url(state)
        _append_audit_6u("operator", "instagram_oauth_started",
                         f"connect/{workspace_slug}")
        return {
            "workspace_slug":     workspace_slug,
            "authorization_url":  auth_url,
            "state":              state,
            "client_configured":  bool(INSTAGRAM_CLIENT_ID),
        }
    finally:
        c.close()


@app.get("/connect/instagram/callback", tags=["instagram"])
def instagram_connect_callback(
    code: str,
    state: str,
    workspace_slug: str = "default",
) -> dict:
    """
    Handle Instagram OAuth callback — exchange code for a short-lived token,
    then exchange that for a long-lived (~60 day) token and persist it.
    """
    from instagram_client import exchange_code_for_token, get_long_lived_token, INSTAGRAM_CLIENT_ID
    from datetime import timedelta

    c = get_client()
    db = get_database(c)
    try:
        rec = db.external_integrations.find_one(
            {"workspace_slug": workspace_slug, "provider": "instagram"}
        )
        stored_state = rec.get("oauth_state") if rec else None
        if stored_state and stored_state != state:
            from fastapi import HTTPException as _HTTPException_ig
            raise _HTTPException_ig(status_code=400, detail="OAuth state mismatch — possible CSRF")

        if not INSTAGRAM_CLIENT_ID:
            # Simulation mode — store a placeholder token
            expires_at = _now_iso_6u()
            _upsert_instagram_integration_ig(db, workspace_slug, {
                "status":       "connected",
                "access_token": f"sim_{_secrets_ig.token_hex(16)}",
                "ig_user_id":   os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "sim_ig_user"),
                "expires_at":   expires_at,
                "oauth_state":  None,
                "simulated":    True,
            })
            _append_audit_6u("operator", "instagram_oauth_completed",
                             f"connect/{workspace_slug}", simulated=True)
            return {"workspace_slug": workspace_slug, "status": "connected", "simulated": True}

        short_lived = exchange_code_for_token(code)
        long_lived  = get_long_lived_token(short_lived["access_token"])
        expires_sec = long_lived.get("expires_in", 5184000)  # ~60 days
        expires_dt  = datetime.now(timezone.utc) + timedelta(seconds=expires_sec)
        _upsert_instagram_integration_ig(db, workspace_slug, {
            "status":       "connected",
            "access_token": long_lived["access_token"],
            "ig_user_id":   os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", ""),
            "expires_at":   expires_dt.isoformat(),
            "oauth_state":  None,
            "simulated":    False,
        })
        _append_audit_6u("operator", "instagram_oauth_completed",
                         f"connect/{workspace_slug}", simulated=False)
        return {"workspace_slug": workspace_slug, "status": "connected", "simulated": False}
    finally:
        c.close()


# Distribution

@app.post("/distribution/instagram/publish", tags=["instagram"])
def instagram_publish(req: InstagramPublishRequest) -> dict:
    """
    Publish a rendered asset to Instagram.
    The referenced asset_renders record must have status="approved".
    Performs a duplicate-publish check before executing.
    Media is published by URL — Instagram fetches it; the operator supplies a
    publicly-reachable media_url. SignalForge does not auto-host media.
    """
    c = get_client()
    db = get_database(c)
    try:
        render = _find_asset_render_ig(db, req.source_asset_render_id)
        if not render:
            from fastapi import HTTPException as _HTTPException_ig
            raise _HTTPException_ig(status_code=404, detail=f"asset_render {req.source_asset_render_id!r} not found")
        if render.get("status") != "approved":
            from fastapi import HTTPException as _HTTPException_ig
            raise _HTTPException_ig(
                status_code=422,
                detail=f"asset_render {req.source_asset_render_id!r} must be status='approved' before publishing (current: {render.get('status')!r}).",
            )
        if _check_duplicate_publish_ig(db, req.source_asset_render_id):
            from fastapi import HTTPException as _HTTPException_ig
            raise _HTTPException_ig(
                status_code=409,
                detail=f"Render {req.source_asset_render_id!r} has already been verified as published to Instagram.",
            )
        attempt = _create_distribution_attempt_ig(
            db, req.workspace_slug, req.source_asset_render_id,
            req.caption, req.media_url, req.media_type,
        )
        result = _execute_instagram_publish_ig(db, req.workspace_slug, attempt)
        return result
    finally:
        c.close()


@app.post("/distribution/instagram/retry", tags=["instagram"])
def instagram_retry(attempt_id: str, req: InstagramRetryRequest) -> dict:
    """Manually retry a failed or retrying Instagram distribution attempt."""
    c = get_client()
    db = get_database(c)
    try:
        attempt = _get_distribution_attempt_6x(db, attempt_id)
        if not attempt:
            from fastapi import HTTPException as _HTTPException_ig
            raise _HTTPException_ig(status_code=404, detail=f"Attempt {attempt_id!r} not found")
        if attempt.get("status") not in ("failed", "retrying"):
            from fastapi import HTTPException as _HTTPException_ig
            raise _HTTPException_ig(
                status_code=400,
                detail=f"Cannot retry attempt in state: {attempt.get('status')!r}"
            )
        retry_count = attempt.get("retry_count", 0)
        max_retries = _PUBLISH_RETRY_LIMITS_6X["network_failure"]
        if retry_count >= max_retries:
            _update_distribution_attempt_6x(db, attempt_id, {"status": "escalated", "escalated": True})
            _append_audit_6u("operator", "distribution_escalated",
                             f"distribution/{attempt_id}",
                             workspace=req.workspace_slug)
            return {**attempt, "status": "escalated",
                    "message": "Retry limit reached — attempt escalated for operator review"}

        _append_audit_6u("operator", "distribution_retry_requested",
                         f"distribution/{attempt_id}",
                         workspace=req.workspace_slug, retry_count=retry_count + 1)
        result = _execute_instagram_publish_ig(db, req.workspace_slug, attempt)
        return result
    finally:
        c.close()


@app.get("/distribution/instagram/{attempt_id}/status", tags=["instagram"])
def instagram_attempt_status(attempt_id: str) -> dict:
    """Return the current status of an Instagram distribution attempt."""
    c = get_client()
    db = get_database(c)
    try:
        attempt = _get_distribution_attempt_6x(db, attempt_id)
        if not attempt:
            from fastapi import HTTPException as _HTTPException_ig
            raise _HTTPException_ig(status_code=404, detail=f"Attempt {attempt_id!r} not found")
        return attempt
    finally:
        c.close()


@app.get("/distribution/instagram/limit", tags=["instagram"])
def instagram_publishing_limit(workspace_slug: str = "default") -> dict:
    """
    Check the current Instagram publishing-limit usage (100 posts / rolling 24h).
    Returns a simulated zero-usage result when not configured with real credentials.
    """
    c = get_client()
    db = get_database(c)
    try:
        integration = db.external_integrations.find_one(
            {"workspace_slug": workspace_slug, "provider": "instagram"}
        ) or {}
        access_token = integration.get("access_token")
        ig_user_id   = integration.get("ig_user_id") or os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
        if not access_token or not ig_user_id:
            return {"workspace_slug": workspace_slug, "quota_usage": 0, "config": {}, "simulated": True}
        from instagram_client import get_publishing_limit
        result = get_publishing_limit(access_token, ig_user_id)
        return {"workspace_slug": workspace_slug, **result, "simulated": False}
    except Exception as exc:
        return {"workspace_slug": workspace_slug, "quota_usage": 0, "config": {}, "simulated": True, "error": str(exc)[:200]}
    finally:
        c.close()


# Telemetry

@app.get("/distribution/instagram/telemetry", tags=["instagram"])
def instagram_distribution_telemetry(workspace_slug: str | None = None) -> dict:
    """Delivery telemetry metrics for the Instagram distribution channel."""
    c = get_client()
    db = get_database(c)
    try:
        return _build_instagram_distribution_telemetry_ig(db, workspace_slug)
    finally:
        c.close()

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PHASE 6Y — Agent Output Quality & Real Workflow Content Validation         ║
# ║  Appended to main.py                                                         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ── Constants ─────────────────────────────────────────────────────────────────

_QUALITY_DIMENSIONS_6Y: list[str] = [
    "relevance",
    "clarity",
    "client_fit",
    "publish_readiness",
    "strategic_value",
]

_QUALITY_MAX_SCORE_6Y:  int = 5
_QUALITY_MIN_PUBLISH_6Y: float = 3.5  # avg score threshold to mark publish-ready

_CONTENT_PACKAGE_TYPES_6Y: dict[str, int] = {
    "linkedin_post":     5,
    "content_hook":      5,
    "video_concept":     3,
    "outreach_angle":    3,
    "campaign_summary":  1,
}

_MEMORY_IMPROVEMENT_THRESHOLD_6Y: float = 0.15  # 15 % avg score lift = "improved"

_PILOT_WORKSPACE_SLUG_6Y: str = "pilot-john-maxwell"

_PILOT_CLIENT_PROFILE_6Y: dict = {
    "workspace_slug":     _PILOT_WORKSPACE_SLUG_6Y,
    "client_name":        "John Maxwell",
    "offer":              "Leadership coaching, keynote speaking, and bestselling book series",
    "audience":           "Mid-level managers, executives, and emerging leaders aged 30-55",
    "tone":               "Authoritative, warm, story-driven, practical",
    "positioning":        "The world's foremost leadership expert — accessible wisdom for everyday leaders",
    "content_goals":      "Build thought leadership, grow LinkedIn following, drive book sales and speaking inquiries",
    "source_inputs":      "Book excerpts (The 21 Irrefutable Laws of Leadership), podcast transcripts, keynote clips",
    "preferred_channels": ["linkedin", "email", "podcast_repurpose"],
    "blocked_claims":     ["guaranteed results", "overnight success", "get rich quickly"],
    "winning_patterns":   ["story-first hooks", "numbered frameworks", "direct CTAs to book or speaking page"],
    "metadata":           {"pilot": True, "phase": "6Y"},
}

_REVISION_REASONS_6Y: list[str] = [
    "tone_mismatch",
    "off_brand",
    "too_generic",
    "factually_unsafe",
    "weak_cta",
    "off_audience",
    "too_long",
    "too_short",
    "not_original",
    "blocked_claim",
]

_QUALITY_METRIC_KEYS_6Y: list[str] = [
    "approval_rate",
    "revision_rate",
    "publish_ready_rate",
    "avg_quality_score",
    "memory_improvement_delta",
]


# ── Pydantic models ───────────────────────────────────────────────────────────

class QualityReviewCreate6Y(BaseModel):
    workspace_slug:     str
    content_item_id:    str
    content_type:       str  # e.g. linkedin_post, content_hook
    content_text:       str
    scores:             dict[str, int]  # dimension -> 0-5
    approved:           bool = False
    publish_ready:      bool = False
    revision_requested: bool = False
    revision_reason:    str | None = None
    reviewer_notes:     str | None = None
    memory_version:     int = 0  # client memory version used when generating


class QualityReviewUpdate6Y(BaseModel):
    approved:           bool | None = None
    publish_ready:      bool | None = None
    revision_requested: bool | None = None
    revision_reason:    str | None = None
    reviewer_notes:     str | None = None
    scores:             dict[str, int] | None = None


class ContentPackageRequest6Y(BaseModel):
    workspace_slug: str
    client_name:    str = "John Maxwell"
    use_memory:     bool = True


class MemoryComparisonRequest6Y(BaseModel):
    workspace_slug:  str
    content_type:    str = "linkedin_post"
    content_text:    str
    baseline_scores: dict[str, int]
    memory_scores:   dict[str, int]


class PilotWorkspaceSeedRequest6Y(BaseModel):
    workspace_slug: str = _PILOT_WORKSPACE_SLUG_6Y
    force:          bool = False


# ── Helper: generate content text for pilot workspace ─────────────────────────

def _generate_pilot_content_6y(content_type: str, index: int, use_memory: bool) -> dict:
    """
    Return a realistic, client-relevant content item for the John Maxwell pilot.
    Uses embedded templates rather than live LLM calls so tests are deterministic
    while still producing copy that demonstrates quality review mechanics.
    """
    memory_tag = " [memory-informed]" if use_memory else ""

    linkedin_posts = [
        (
            "The best leaders I've worked with all share one trait: they don't manage people — "
            "they multiply them.\n\n"
            "Law #1 of leadership isn't authority. It's influence.\n\n"
            "When you invest in someone's growth, you don't lose — you compound.\n\n"
            "Who are you multiplying today? 👇\n\n"
            "#Leadership #JohnMaxwell #21Laws"
        ),
        (
            "Most managers wait for motivation to arrive.\n\n"
            "Great leaders create the conditions for it.\n\n"
            "3 things I've seen transform team energy:\n"
            "→ Clear vision they believe in\n"
            "→ Progress they can see\n"
            "→ A leader who notices the small wins\n\n"
            "Motivation isn't a mystery. It's a discipline.\n\n"
            "#LeadershipDevelopment #Management"
        ),
        (
            "I've coached Fortune 500 CEOs and front-line supervisors.\n\n"
            "The gap between them isn't intelligence.\n\n"
            "It's this: top leaders ask better questions.\n\n"
            "Not \"why did this fail?\" — but \"what can we learn?\"\n"
            "Not \"who's responsible?\" — but \"how do we move forward?\"\n\n"
            "The question shapes the culture.\n\n"
            "What's one question you could ask your team this week?\n\n"
            "#ExecutiveLeadership #Coaching #GrowthMindset"
        ),
        (
            "Leadership is not a title. It's a choice you make every single day.\n\n"
            "I've seen janitors lead with more influence than VPs.\n\n"
            "Because influence comes from character — not a corner office.\n\n"
            "You don't need permission to start leading.\n\n"
            "→ Share this with someone who needs to hear it today.\n\n"
            "#Leadership #CharacterMatters #MaxwellLeadership"
        ),
        (
            "The 21 Irrefutable Laws of Leadership weren't written from a boardroom.\n\n"
            "They came from 40 years of watching what actually works.\n\n"
            "Law #17: The Law of Magnetism — you attract who you are, not who you want.\n\n"
            "Want better team members? Become a better leader first.\n\n"
            "📖 Link to the book in bio.\n\n"
            "#21Laws #LeadershipBooks #PersonalGrowth"
        ),
    ]

    hooks = [
        f"Most leaders plateau not because they stop working — but because they stop growing.{memory_tag}",
        f"The conversation your team needs you to start — but you keep putting off.{memory_tag}",
        f"5 words that changed how I think about influence: 'People buy into the leader first.'{memory_tag}",
        f"You can have the best strategy in the room. But without trust, it goes nowhere.{memory_tag}",
        f"Leadership pain point no one talks about: the loneliness of the top chair.{memory_tag}",
    ]

    video_concepts = [
        {
            "title":       f"The Law of the Lid — Why Your Team's Growth Is Capped By Yours{memory_tag}",
            "format":      "60-second vertical reel",
            "hook":        "If your team isn't growing, the lid might be you.",
            "structure":   "Hook → Law explanation (15s) → Story example (30s) → CTA to book (15s)",
            "cta":         "Download the free leadership assessment — link in bio.",
        },
        {
            "title":       f"3 Questions Every Great Leader Asks in a 1:1{memory_tag}",
            "format":      "LinkedIn native video, 90 seconds",
            "hook":        "Stop running 1:1s that feel like status updates.",
            "structure":   "Hook (10s) → 3 questions with brief rationale each (60s) → CTA (20s)",
            "cta":         "Reply with your go-to 1:1 question — I'll share the best ones.",
        },
        {
            "title":       f"From Manager to Multiplier: The Shift That Changes Everything{memory_tag}",
            "format":      "LinkedIn carousel repurposed as voiceover reel",
            "hook":        "There's a moment every good manager has — where they realize managing isn't enough.",
            "structure":   "Story hook (20s) → The shift explained (40s) → Practical step (20s) → Book CTA (10s)",
            "cta":         "Grab 'The 21 Irrefutable Laws' — link in comments.",
        },
    ]

    outreach_angles = [
        {
            "angle":   f"Warm intro for speaking inquiry{memory_tag}",
            "subject": "Bringing John Maxwell's leadership framework to your next event",
            "body":    (
                "Hi [Name],\n\n"
                "Your team is doing extraordinary work in [industry]. "
                "I'm reaching out because John Maxwell's Leadership Keynote has been transforming "
                "exactly the kind of culture you're building — with practical, story-driven frameworks "
                "that stick long after the event.\n\n"
                "Would it make sense to explore a 2026 keynote or leadership workshop?\n\n"
                "Best,\nThe Maxwell Leadership Team"
            ),
        },
        {
            "angle":   f"Book launch outreach to HR leaders{memory_tag}",
            "subject": "A leadership resource your team leads have been asking for",
            "body":    (
                "Hi [Name],\n\n"
                "Many HR directors I speak with are looking for one thing: "
                "a leadership development resource their managers will actually use.\n\n"
                "The 21 Irrefutable Laws has been that resource for 3M+ leaders worldwide — "
                "practical, memorable, and directly applicable.\n\n"
                "I'd love to share a complimentary copy for your team. Interested?\n\n"
                "Best,\nJohn Maxwell"
            ),
        },
        {
            "angle":   f"Podcast collab pitch{memory_tag}",
            "subject": "John Maxwell + [Your Podcast] — leadership conversation your audience will love",
            "body":    (
                "Hi [Host],\n\n"
                "Your audience cares deeply about growth — which is exactly what John brings "
                "to every conversation.\n\n"
                "With 40+ years of leadership experience, 100+ books, and frameworks used by "
                "Fortune 500 teams worldwide, he delivers insights your listeners can apply Monday morning.\n\n"
                "Would you be open to a 30-minute exploratory call?\n\n"
                "Best,\nThe Maxwell Leadership Team"
            ),
        },
    ]

    campaign_summary = {
        "campaign_name":    f"John Maxwell Leadership Thought-Leadership Sprint — Q3 2026{memory_tag}",
        "objective":        "Establish dominant LinkedIn presence, drive speaking inquiries, accelerate book sales",
        "target_audience":  "Managers and executives aged 30-55 across mid-large enterprises",
        "core_message":     "Leadership is a choice and a skill — John Maxwell gives you both the why and the how",
        "content_calendar": "5 LinkedIn posts/week (2 original, 2 repurposed, 1 engagement) + 1 video/week",
        "success_kpis":     ["500+ net new LinkedIn followers/month", "15+ speaking inquiry leads/quarter",
                             "10% lift in book referral traffic from LinkedIn"],
        "memory_enabled":   use_memory,
    }

    if content_type == "linkedin_post":
        i = min(index, len(linkedin_posts) - 1)
        text = linkedin_posts[i]
        return {"content_type": content_type, "content_text": text, "index": index}
    elif content_type == "content_hook":
        i = min(index, len(hooks) - 1)
        return {"content_type": content_type, "content_text": hooks[i], "index": index}
    elif content_type == "video_concept":
        i = min(index, len(video_concepts) - 1)
        vc = video_concepts[i]
        return {"content_type": content_type, "content_text": str(vc), "structured": vc, "index": index}
    elif content_type == "outreach_angle":
        i = min(index, len(outreach_angles) - 1)
        oa = outreach_angles[i]
        return {"content_type": content_type, "content_text": oa["body"], "structured": oa, "index": index}
    else:  # campaign_summary
        return {"content_type": content_type, "content_text": str(campaign_summary), "structured": campaign_summary, "index": 0}


# ── Helper: seed pilot workspace ──────────────────────────────────────────────

def _seed_pilot_workspace_6y(db, workspace_slug: str, force: bool = False) -> dict:
    now = _now_iso_6u()
    created: dict[str, int] = {}

    # Workspace record
    existing_ws = db.workspaces.find_one({"slug": workspace_slug})
    if existing_ws and not force:
        return {
            "workspace_slug": workspace_slug,
            "already_exists":  True,
            "created":         {},
            "seeded_at":       now,
        }

    db.workspaces.update_one(
        {"slug": workspace_slug},
        {"$set": {
            "slug":        workspace_slug,
            "name":        "John Maxwell — Leadership Growth",
            "module":      "artist_growth",
            "status":      "active",
            "created_at":  now,
            "metadata":    {"pilot": True, "phase": "6Y"},
        }},
        upsert=True,
    )
    created["workspace"] = 1

    # Client profile
    profile = {**_PILOT_CLIENT_PROFILE_6Y, "created_at": now, "updated_at": now}
    db.client_profiles.update_one(
        {"workspace_slug": workspace_slug},
        {"$set": profile},
        upsert=True,
    )
    created["client_profile"] = 1

    # Client memory v1 (baseline — no winning patterns loaded yet)
    db.client_memory.update_one(
        {"workspace_slug": workspace_slug, "memory_version": 1},
        {"$set": {
            "workspace_slug":  workspace_slug,
            "memory_version":  1,
            "tone":            "Authoritative, warm, story-driven, practical",
            "blocked_claims":  _PILOT_CLIENT_PROFILE_6Y["blocked_claims"],
            "winning_patterns": [],
            "approved_topics": ["leadership", "personal growth", "team development", "book promotion"],
            "created_at":      now,
            "is_baseline":     True,
        }},
        upsert=True,
    )
    created["memory_baseline"] = 1

    # Client memory v2 (memory-informed — winning patterns loaded)
    db.client_memory.update_one(
        {"workspace_slug": workspace_slug, "memory_version": 2},
        {"$set": {
            "workspace_slug":  workspace_slug,
            "memory_version":  2,
            "tone":            "Authoritative, warm, story-driven, practical",
            "blocked_claims":  _PILOT_CLIENT_PROFILE_6Y["blocked_claims"],
            "winning_patterns": _PILOT_CLIENT_PROFILE_6Y["winning_patterns"],
            "approved_topics": ["leadership", "personal growth", "team development", "book promotion",
                                "21 laws", "keynote", "multiplier mindset"],
            "created_at":      now,
            "is_baseline":     False,
            "improvements_applied": ["story-first hooks", "numbered frameworks", "direct CTAs"],
        }},
        upsert=True,
    )
    created["memory_v2"] = 1

    # Pre-seed a content package with quality reviews
    pkg_id = f"pkg_{workspace_slug[:8]}_{_now_iso_6u()[:10].replace('-', '')}"
    db.content_packages_6y.update_one(
        {"package_id": pkg_id},
        {"$setOnInsert": {
            "package_id":     pkg_id,
            "workspace_slug": workspace_slug,
            "client_name":    "John Maxwell",
            "status":         "generated",
            "created_at":     now,
            "item_counts":    _CONTENT_PACKAGE_TYPES_6Y,
        }},
        upsert=True,
    )
    created["content_package"] = 1

    _append_audit_6u("system", "pilot_workspace_seeded", workspace_slug,
                     workspace_slug=workspace_slug, entities=created)
    return {
        "workspace_slug": workspace_slug,
        "already_exists":  False,
        "created":         created,
        "total_entities":  sum(created.values()),
        "seeded_at":       now,
    }


# ── Helper: create quality review ─────────────────────────────────────────────

def _create_quality_review_6y(db, payload_dict: dict) -> dict:
    now   = _now_iso_6u()
    ws    = payload_dict.get("workspace_slug", "default")
    scores: dict = payload_dict.get("scores", {})

    # Clamp all scores 0-5
    clamped = {
        dim: max(0, min(_QUALITY_MAX_SCORE_6Y, int(scores.get(dim, 0))))
        for dim in _QUALITY_DIMENSIONS_6Y
    }
    total_dims = len(_QUALITY_DIMENSIONS_6Y)
    avg_score  = sum(clamped.values()) / total_dims if total_dims else 0.0

    # Auto-detect publish readiness if not explicitly set
    publish_ready = payload_dict.get("publish_ready", False)
    if not publish_ready and avg_score >= _QUALITY_MIN_PUBLISH_6Y:
        publish_ready = True

    review_id = f"qr_{_now_iso_6u()[:10].replace('-','')}_{__import__('secrets').token_hex(4)}"
    doc = {
        "review_id":          review_id,
        "workspace_slug":     ws,
        "content_item_id":    payload_dict.get("content_item_id", ""),
        "content_type":       payload_dict.get("content_type", "unknown"),
        "content_text":       payload_dict.get("content_text", ""),
        "scores":             clamped,
        "avg_score":          round(avg_score, 3),
        "approved":           bool(payload_dict.get("approved", False)),
        "publish_ready":      publish_ready,
        "revision_requested": bool(payload_dict.get("revision_requested", False)),
        "revision_reason":    payload_dict.get("revision_reason"),
        "reviewer_notes":     payload_dict.get("reviewer_notes"),
        "memory_version":     int(payload_dict.get("memory_version", 0)),
        "created_at":         now,
        "updated_at":         now,
    }
    try:
        db.quality_reviews_6y.insert_one(doc)
    except Exception:
        pass

    if bool(payload_dict.get("revision_requested")):
        _append_audit_6u("operator", "quality_review_revision_requested",
                         f"review/{review_id}",
                         workspace_slug=ws,
                         reason=payload_dict.get("revision_reason"))
        # Auto-generate memory proposal on revision
        _propose_quality_memory_update_6y(db, ws, doc)
    else:
        _append_audit_6u("operator", "quality_review_created",
                         f"review/{review_id}",
                         workspace_slug=ws,
                         avg_score=avg_score)

    return doc


# ── Helper: update quality review ─────────────────────────────────────────────

def _update_quality_review_6y(db, review_id: str, update_dict: dict) -> dict | None:
    now = _now_iso_6u()
    existing = db.quality_reviews_6y.find_one({"review_id": review_id})
    if not existing:
        return None

    patch: dict = {"updated_at": now}

    if "scores" in update_dict and update_dict["scores"]:
        new_scores = {
            dim: max(0, min(_QUALITY_MAX_SCORE_6Y, int(update_dict["scores"].get(dim, 0))))
            for dim in _QUALITY_DIMENSIONS_6Y
        }
        patch["scores"]    = new_scores
        patch["avg_score"] = round(sum(new_scores.values()) / len(_QUALITY_DIMENSIONS_6Y), 3)
        # Re-evaluate publish readiness
        patch["publish_ready"] = (
            update_dict.get("publish_ready", False)
            or patch["avg_score"] >= _QUALITY_MIN_PUBLISH_6Y
        )
    for field in ("approved", "publish_ready", "revision_requested",
                  "revision_reason", "reviewer_notes"):
        if update_dict.get(field) is not None:
            patch[field] = update_dict[field]

    try:
        db.quality_reviews_6y.update_one({"review_id": review_id}, {"$set": patch})
        updated = db.quality_reviews_6y.find_one({"review_id": review_id})
        _append_audit_6u("operator", "quality_review_updated",
                         f"review/{review_id}",
                         workspace_slug=existing.get("workspace_slug"))
        return updated
    except Exception:
        return existing


# ── Helper: memory proposal from quality feedback ─────────────────────────────

def _propose_quality_memory_update_6y(db, workspace_slug: str, review: dict) -> None:
    """Insert a memory_proposals doc when a review triggers revision feedback."""
    now = _now_iso_6u()
    try:
        db.memory_proposals.insert_one({
            "workspace_slug":  workspace_slug,
            "source":          "quality_review_6y",
            "review_id":       review.get("review_id"),
            "content_type":    review.get("content_type"),
            "revision_reason": review.get("revision_reason"),
            "avg_score":       review.get("avg_score", 0.0),
            "proposal":        f"Avoid '{review.get('revision_reason','unknown')}' in future {review.get('content_type','content')} outputs",
            "status":          "pending",
            "created_at":      now,
        })
    except Exception:
        pass


# ── Helper: generate content package ─────────────────────────────────────────

def _generate_content_package_6y(db, workspace_slug: str, client_name: str, use_memory: bool) -> dict:
    now  = _now_iso_6u()
    items: list[dict] = []

    for ctype, count in _CONTENT_PACKAGE_TYPES_6Y.items():
        for idx in range(count):
            item = _generate_pilot_content_6y(ctype, idx, use_memory)
            item_id = f"ci_{ctype[:6]}_{idx}_{__import__('secrets').token_hex(3)}"
            doc = {
                "item_id":        item_id,
                "workspace_slug": workspace_slug,
                "client_name":    client_name,
                "content_type":   ctype,
                "content_text":   item.get("content_text", ""),
                "structured":     item.get("structured"),
                "use_memory":     use_memory,
                "status":         "draft",
                "created_at":     now,
            }
            try:
                db.content_items_6y.insert_one(doc)
            except Exception:
                pass
            items.append(doc)

    pkg_id = f"pkg_{__import__('secrets').token_hex(6)}"
    pkg = {
        "package_id":     pkg_id,
        "workspace_slug": workspace_slug,
        "client_name":    client_name,
        "use_memory":     use_memory,
        "item_counts":    {k: sum(1 for i in items if i["content_type"] == k)
                           for k in _CONTENT_PACKAGE_TYPES_6Y},
        "total_items":    len(items),
        "status":         "generated",
        "created_at":     now,
    }
    try:
        db.content_packages_6y.insert_one(pkg)
    except Exception:
        pass

    _append_audit_6u("system", "content_package_generated", pkg_id,
                     workspace_slug=workspace_slug, total=len(items), use_memory=use_memory)
    return {**pkg, "items": items}


# ── Helper: memory comparison ─────────────────────────────────────────────────

def _compare_memory_impact_6y(baseline_scores: dict, memory_scores: dict) -> dict:
    dims = _QUALITY_DIMENSIONS_6Y
    base_avg = sum(baseline_scores.get(d, 0) for d in dims) / len(dims)
    mem_avg  = sum(memory_scores.get(d, 0) for d in dims) / len(dims)
    delta    = mem_avg - base_avg
    improved = delta >= _MEMORY_IMPROVEMENT_THRESHOLD_6Y * _QUALITY_MAX_SCORE_6Y

    dim_deltas = {
        d: round(memory_scores.get(d, 0) - baseline_scores.get(d, 0), 3)
        for d in dims
    }
    return {
        "baseline_avg":      round(base_avg, 3),
        "memory_avg":        round(mem_avg, 3),
        "delta":             round(delta, 3),
        "improved":          improved,
        "dimension_deltas":  dim_deltas,
        "threshold_required": round(_MEMORY_IMPROVEMENT_THRESHOLD_6Y * _QUALITY_MAX_SCORE_6Y, 3),
        "evaluated_at":      _now_iso_6u(),
    }


# ── Helper: quality metrics dashboard ────────────────────────────────────────

def _build_quality_metrics_6y(db, workspace_slug: str | None) -> dict:
    now = _now_iso_6u()
    q: dict = {}
    if workspace_slug:
        q["workspace_slug"] = workspace_slug
    try:
        total      = db.quality_reviews_6y.count_documents(q)
        approved   = db.quality_reviews_6y.count_documents({**q, "approved": True})
        revised    = db.quality_reviews_6y.count_documents({**q, "revision_requested": True})
        pub_ready  = db.quality_reviews_6y.count_documents({**q, "publish_ready": True})

        avg_score  = 0.0
        if total > 0:
            pipeline = [{"$match": q}, {"$group": {"_id": None, "avg": {"$avg": "$avg_score"}}}]
            agg      = list(db.quality_reviews_6y.aggregate(pipeline))
            avg_score = round(agg[0]["avg"], 3) if agg else 0.0

        # Memory delta: compare avg_score of memory_version==0 vs memory_version>=1
        baseline_agg = list(db.quality_reviews_6y.aggregate([
            {"$match": {**q, "memory_version": 0}},
            {"$group": {"_id": None, "avg": {"$avg": "$avg_score"}}},
        ]))
        memory_agg = list(db.quality_reviews_6y.aggregate([
            {"$match": {**q, "memory_version": {"$gte": 1}}},
            {"$group": {"_id": None, "avg": {"$avg": "$avg_score"}}},
        ]))
        baseline_avg  = round(baseline_agg[0]["avg"], 3) if baseline_agg else 0.0
        memory_avg    = round(memory_agg[0]["avg"],   3) if memory_agg   else 0.0
        memory_delta  = round(memory_avg - baseline_avg, 3)

        return {
            "workspace_slug":        workspace_slug,
            "total_reviews":         total,
            "approval_rate":         round(approved / total, 3) if total else 0.0,
            "revision_rate":         round(revised  / total, 3) if total else 0.0,
            "publish_ready_rate":    round(pub_ready / total, 3) if total else 0.0,
            "avg_quality_score":     avg_score,
            "memory_improvement_delta": memory_delta,
            "totals": {
                "approved":          approved,
                "revised":           revised,
                "publish_ready":     pub_ready,
                "total":             total,
            },
            "evaluated_at": now,
        }
    except Exception:
        return {
            "workspace_slug":          workspace_slug,
            "total_reviews":           0,
            "approval_rate":           0.0,
            "revision_rate":           0.0,
            "publish_ready_rate":      0.0,
            "avg_quality_score":       0.0,
            "memory_improvement_delta": 0.0,
            "totals":                  {},
            "evaluated_at":            now,
        }


# ── Helper: filter publish-ready reviews ──────────────────────────────────────

def _get_publish_ready_reviews_6y(db, workspace_slug: str | None, limit: int) -> list[dict]:
    q: dict = {"publish_ready": True}
    if workspace_slug:
        q["workspace_slug"] = workspace_slug
    try:
        return list(
            db.quality_reviews_6y.find(q).sort("created_at", -1).limit(limit)
        )
    except Exception:
        return []


# ── Helper: revision loop — rerun content after feedback ─────────────────────

def _run_revision_loop_6y(db, review_id: str, workspace_slug: str) -> dict:
    now = _now_iso_6u()
    existing = db.quality_reviews_6y.find_one({"review_id": review_id})
    if not existing:
        return {"error": f"review {review_id!r} not found"}

    ctype = existing.get("content_type", "linkedin_post")
    # Generate a fresh content item — use memory (memory_version=2)
    new_item = _generate_pilot_content_6y(ctype, 0, use_memory=True)

    # Build a revised review stub (operator will re-score)
    new_review_id = f"qr_rev_{__import__('secrets').token_hex(5)}"
    revised_doc = {
        "review_id":            new_review_id,
        "workspace_slug":       workspace_slug,
        "content_item_id":      existing.get("content_item_id", ""),
        "content_type":         ctype,
        "content_text":         new_item.get("content_text", ""),
        "scores":               {d: 0 for d in _QUALITY_DIMENSIONS_6Y},
        "avg_score":            0.0,
        "approved":             False,
        "publish_ready":        False,
        "revision_requested":   False,
        "revision_reason":      None,
        "reviewer_notes":       None,
        "memory_version":       2,
        "parent_review_id":     review_id,
        "is_revision":          True,
        "created_at":           now,
        "updated_at":           now,
    }
    try:
        db.quality_reviews_6y.insert_one(revised_doc)
    except Exception:
        pass

    _append_audit_6u("operator", "revision_loop_executed",
                     f"review/{review_id}→{new_review_id}",
                     workspace_slug=workspace_slug)
    return {
        "original_review_id": review_id,
        "new_review_id":      new_review_id,
        "content_type":       ctype,
        "new_content_text":   new_item.get("content_text", ""),
        "memory_version":     2,
        "is_revision":        True,
        "created_at":         now,
    }


# ── Helper: get review by ID ──────────────────────────────────────────────────

def _get_review_6y(db, review_id: str) -> dict | None:
    try:
        return db.quality_reviews_6y.find_one({"review_id": review_id})
    except Exception:
        return None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/quality/pilot-workspace/seed", tags=["quality"])
def seed_pilot_workspace_6y(req: PilotWorkspaceSeedRequest6Y = PilotWorkspaceSeedRequest6Y()) -> dict:
    """Seed the John Maxwell pilot workspace with client profile, memory versions, and content package."""
    c = get_client()
    db = get_database(c)
    try:
        return _seed_pilot_workspace_6y(db, req.workspace_slug, req.force)
    finally:
        c.close()


@app.post("/quality/reviews", tags=["quality"])
def create_quality_review_6y(payload: QualityReviewCreate6Y) -> dict:
    """Create a quality review for a content item with dimension scores."""
    c = get_client()
    db = get_database(c)
    try:
        return _create_quality_review_6y(db, payload.dict())
    finally:
        c.close()


@app.get("/quality/reviews/{review_id}", tags=["quality"])
def get_quality_review_6y(review_id: str) -> dict:
    """Retrieve a single quality review by ID."""
    c = get_client()
    db = get_database(c)
    try:
        review = _get_review_6y(db, review_id)
        if not review:
            from fastapi import HTTPException as _HTTPException_6y
            raise _HTTPException_6y(status_code=404, detail=f"Review {review_id!r} not found")
        return review
    finally:
        c.close()


@app.patch("/quality/reviews/{review_id}", tags=["quality"])
def update_quality_review_6y(review_id: str, payload: QualityReviewUpdate6Y) -> dict:
    """Update scores, approval, publish-readiness, or revision status of a review."""
    c = get_client()
    db = get_database(c)
    try:
        updated = _update_quality_review_6y(db, review_id, payload.dict(exclude_none=True))
        if not updated:
            from fastapi import HTTPException as _HTTPException_6y
            raise _HTTPException_6y(status_code=404, detail=f"Review {review_id!r} not found")
        return updated
    finally:
        c.close()


@app.get("/quality/reviews", tags=["quality"])
def list_quality_reviews_6y(
    workspace_slug: str | None = None,
    publish_ready:  bool | None = None,
    approved:       bool | None = None,
    content_type:   str  | None = None,
    limit:          int  = 50,
) -> dict:
    """List quality reviews with optional filters."""
    c = get_client()
    db = get_database(c)
    try:
        q: dict = {}
        if workspace_slug:   q["workspace_slug"] = workspace_slug
        if publish_ready is not None: q["publish_ready"] = publish_ready
        if approved is not None:      q["approved"] = approved
        if content_type:     q["content_type"] = content_type
        try:
            items = list(db.quality_reviews_6y.find(q).sort("created_at", -1).limit(min(limit, 200)))
        except Exception:
            items = []
        return {"reviews": items, "count": len(items), "retrieved_at": _now_iso_6u()}
    finally:
        c.close()


@app.post("/quality/content-package", tags=["quality"])
def generate_content_package_6y(req: ContentPackageRequest6Y) -> dict:
    """Generate a full content package for a pilot workspace client."""
    c = get_client()
    db = get_database(c)
    try:
        return _generate_content_package_6y(db, req.workspace_slug, req.client_name, req.use_memory)
    finally:
        c.close()


@app.get("/quality/content-package", tags=["quality"])
def list_content_packages_6y(workspace_slug: str | None = None, limit: int = 20) -> dict:
    """List generated content packages."""
    c = get_client()
    db = get_database(c)
    try:
        q: dict = {}
        if workspace_slug:
            q["workspace_slug"] = workspace_slug
        try:
            pkgs = list(db.content_packages_6y.find(q).sort("created_at", -1).limit(min(limit, 100)))
        except Exception:
            pkgs = []
        return {"packages": pkgs, "count": len(pkgs), "retrieved_at": _now_iso_6u()}
    finally:
        c.close()


@app.post("/quality/memory-comparison", tags=["quality"])
def memory_comparison_6y(req: MemoryComparisonRequest6Y) -> dict:
    """Compare baseline vs memory-informed quality scores and compute improvement delta."""
    return _compare_memory_impact_6y(req.baseline_scores, req.memory_scores)


@app.post("/quality/revision-loop/{review_id}", tags=["quality"])
def revision_loop_6y(review_id: str, workspace_slug: str = _PILOT_WORKSPACE_SLUG_6Y) -> dict:
    """Execute a revision loop: generate fresh memory-informed content for a rejected review."""
    c = get_client()
    db = get_database(c)
    try:
        result = _run_revision_loop_6y(db, review_id, workspace_slug)
        if result.get("error"):
            from fastapi import HTTPException as _HTTPException_6y
            raise _HTTPException_6y(status_code=404, detail=result["error"])
        return result
    finally:
        c.close()


@app.get("/quality/publish-ready", tags=["quality"])
def publish_ready_6y(workspace_slug: str | None = None, limit: int = 20) -> dict:
    """Return all publish-ready content reviews."""
    c = get_client()
    db = get_database(c)
    try:
        items = _get_publish_ready_reviews_6y(db, workspace_slug, min(limit, 100))
        return {"publish_ready": items, "count": len(items), "retrieved_at": _now_iso_6u()}
    finally:
        c.close()


@app.get("/quality/metrics", tags=["quality"])
def quality_metrics_6y(workspace_slug: str | None = None) -> dict:
    """Return agent quality metrics dashboard: approval rate, revision rate, avg score, memory delta."""
    c = get_client()
    db = get_database(c)
    try:
        return _build_quality_metrics_6y(db, workspace_slug)
    finally:
        c.close()
