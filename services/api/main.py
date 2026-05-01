import os
import re
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from bson import ObjectId
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient

from core.constants import MESSAGE_REVIEW_DECISIONS, OPEN_DEAL_OUTCOMES, VALID_MODULES

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


class MessageReviewRequest(BaseModel):
    decision: Literal["approve", "reject", "revise"]
    note: str = ""


class AgentRunRequest(BaseModel):
    agent: Literal["outreach", "content", "fan_engagement", "followup"]
    module: str
    dry_run: bool = True
    limit: int = 10


class AgentTaskCreateRequest(BaseModel):
    agent_name: Literal["outreach", "followup", "content", "fan_engagement"]
    module: str
    task_type: str = "agent_dry_run"
    priority: int = 5
    input_summary: dict[str, Any] = {}


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "reject", "convert_to_draft", "needs_revision"]
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
    }


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


def agent_task_query(status: str, agent_name: str, module: str) -> dict:
    query: dict[str, Any] = {}
    if status:
        query["status"] = status
    if agent_name:
        query["agent_name"] = agent_name
    if module:
        query["module"] = module
    return query


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


@app.get("/settings/gpt-runtime")
def gpt_runtime_settings() -> dict:
    return gpt_runtime_status()


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
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
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
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
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
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
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
    request_type: str = "",
    agent_name: str = "",
    module: str = "",
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        if request_type:
            query["request_type"] = request_type
        if agent_name:
            query["agent_name"] = agent_name
        if module:
            query["module"] = module
        records = list(db.approval_requests.find(query).sort([("created_at", -1)]).limit(limit))
        records = enrich_approval_requests(records, db)
        return {"items": serialize(records), "simulation_only": True}
    finally:
        client.close()


@app.get("/agent-tasks")
def agent_tasks(
    status: str = "",
    agent_name: str = "",
    module: str = "",
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        records = list(
            db.agent_tasks.find(agent_task_query(status, agent_name, module))
            .sort([("priority", -1), ("created_at", -1)])
            .limit(limit)
        )
        return {"items": serialize(records), "simulation_only": True}
    finally:
        client.close()


@app.post("/agent-tasks")
def create_agent_task(payload: AgentTaskCreateRequest) -> dict:
    validate_agent_task(payload.agent_name, payload.module)
    now = utc_now()
    task = {
        "agent_name": payload.agent_name,
        "module": payload.module,
        "task_type": clean_text(payload.task_type) or "agent_dry_run",
        "status": "queued",
        "priority": payload.priority,
        "input_summary": {
            **(payload.input_summary or {}),
            "dry_run": True,
            "simulation_only": True,
        },
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "linked_run_id": None,
        "outbound_actions_taken": 0,
        "simulation_only": True,
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
        validate_agent_task(agent_name, module)
        db.agent_tasks.update_one(
            {"_id": task["_id"]},
            {"$set": {"status": "running", "started_at": started_at, "updated_at": started_at, "outbound_actions_taken": 0}},
        )

        try:
            agent_cls = AGENT_CLASSES[agent_name]
            limit = int((task.get("input_summary") or {}).get("limit") or 10)
            agent = agent_cls(
                module=module,
                dry_run=True,
                mongo_uri=mongo_uri(),
                vault_path=vault_path(),
                limit=max(1, min(limit, 50)),
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
                "output_summary": {
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
        agent = agent_cls(
            module=payload.module,
            dry_run=True,
            mongo_uri=mongo_uri(),
            vault_path=vault_path(),
            limit=max(1, min(payload.limit, 50)),
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
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if agent_name:
            query["agent_name"] = agent_name
        if module:
            query["module"] = module
        if status:
            query["status"] = status
        runs = list(db.agent_runs.find(query).sort([("started_at", -1)]).limit(limit))
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
    limit: int = Query(200, ge=1, le=500),
) -> dict:
    client = get_client()
    try:
        db = get_database(client)
        query: dict[str, Any] = {}
        if module:
            query["module"] = module
        if outcome:
            query["$or"] = [{"outcome": outcome}, {"deal_status": outcome}]
        records = list(db.deals.find(query).sort([("updated_at", -1), ("deal_value", -1)]).limit(limit))
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
