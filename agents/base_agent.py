import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bson import ObjectId
from pymongo import MongoClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_PATH = PROJECT_ROOT / "vault"
DEFAULT_MONGO_URI = "mongodb://localhost:27017/signalforge"

SUPPORTED_MODULES = {
    "contractor_growth": {
        "label": "Contractor Growth",
        "module_path": None,
        "lead_query": {
            "$or": [
                {"engine": {"$regex": "contractor_lead_engine"}},
                {"business_type": {"$regex": "contractor", "$options": "i"}},
            ]
        },
    },
    "insurance_growth": {
        "label": "Insurance Growth",
        "module_path": PROJECT_ROOT / "modules" / "insurance_growth",
        "lead_query": {"module": "insurance_growth"},
    },
    "artist_growth": {
        "label": "Artist Growth",
        "module_path": PROJECT_ROOT / "modules" / "artist_growth",
        "lead_query": {"module": "artist_growth"},
    },
    "media_growth": {
        "label": "Media Growth",
        "module_path": PROJECT_ROOT / "modules" / "media_growth",
        "lead_query": {"module": "media_growth"},
    },
}


class BaseAgent:
    agent_name = "base"
    agent_role = "Base simulation agent"

    def __init__(
        self,
        module: str,
        dry_run: bool = True,
        mongo_uri: str | None = None,
        vault_path: str | Path | None = None,
        limit: int = 10,
    ) -> None:
        if module not in SUPPORTED_MODULES:
            supported = ", ".join(sorted(SUPPORTED_MODULES))
            raise ValueError(f"Unsupported module: {module}. Supported modules: {supported}")

        self.module = module
        self.module_config = SUPPORTED_MODULES[module]
        self.dry_run = dry_run
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI", DEFAULT_MONGO_URI)
        self.vault_path = Path(vault_path or os.getenv("VAULT_PATH", str(DEFAULT_VAULT_PATH)))
        self.limit = limit
        self.started_at = datetime.now(timezone.utc)
        self.contacts: list[dict[str, Any]] = []
        self.message_drafts: list[dict[str, Any]] = []
        self.run_id: str | None = None
        self.db = None

    def run(self) -> dict[str, Any]:
        db = self.get_database()
        self.db = db
        run_id = self.start_observed_run(db)
        self.run_id = run_id
        leads: list[dict[str, Any]] = []
        actions: list[dict[str, str]] = []
        log_path = ""

        try:
            self.record_step(
                db,
                run_id,
                1,
                "load_context",
                {"module": self.module, "limit": self.limit},
                "Use local MongoDB and module docs only.",
                {"module_label": self.module_config["label"], "context": self.module_context_summary()},
            )
            leads = self.fetch_leads(db)
            self.contacts = self.fetch_contacts(db)
            self.message_drafts = self.fetch_message_drafts(db)
            self.record_step(
                db,
                run_id,
                2,
                "read_mongo_records",
                {"lead_query": self.module_config["lead_query"], "module": self.module},
                "Prefer high-priority contacts and recent module records.",
                {
                    "lead_count": len(leads),
                    "contact_count": len(self.contacts),
                    "message_draft_count": len(self.message_drafts),
                    "contacts": self.compact_records(self.contacts, "contact"),
                    "leads": self.compact_records(leads, "lead"),
                    "message_drafts": self.compact_records(self.message_drafts, "message"),
                },
            )
            actions = self.plan_actions(leads)
            self.record_step(
                db,
                run_id,
                3,
                "plan_actions",
                {"lead_count": len(leads), "contact_count": len(self.contacts), "message_draft_count": len(self.message_drafts)},
                "Create dry-run actions for human review; do not send anything.",
                {"planned_actions": actions},
            )
            approval_refs = self.create_approval_requests(db, run_id, actions)
            self.record_step(
                db,
                run_id,
                4,
                "identify_human_approvals",
                {"planned_action_count": len(actions), "message_draft_count": len(self.message_drafts)},
                "Surface review-only approval work for the operator.",
                {"approval_request_count": len(approval_refs), "approval_request_ids": approval_refs},
            )
            log_path = self.write_run_log(leads, self.contacts, self.message_drafts, actions)
            artifact_refs = self.record_artifacts(db, run_id, log_path, actions)
            self.record_step(
                db,
                run_id,
                5,
                "write_outputs",
                {"log_path": log_path},
                "Persist markdown and Mongo observability records.",
                {"log_path": log_path, "artifact_count": len(artifact_refs)},
                artifact_refs=artifact_refs,
            )
            self.complete_observed_run(db, run_id, "completed", leads, actions, log_path)
            self.print_actions(actions, log_path)
            return {
                "run_id": run_id,
                "actions": actions,
                "log_path": log_path,
                "lead_count": len(leads),
                "contact_count": len(self.contacts),
                "message_draft_count": len(self.message_drafts),
            }
        except Exception as exc:
            self.record_step(
                db,
                run_id,
                99,
                "agent_error",
                {"agent": self.agent_name, "module": self.module},
                "Stop the dry run and preserve the error for operator review.",
                {"error": f"{exc.__class__.__name__}: {exc}"},
                status="failed",
            )
            self.complete_observed_run(db, run_id, "failed", leads, actions, log_path, error=str(exc))
            raise

    def get_database(self):
        client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        try:
            return client.get_default_database()
        except Exception:
            return client["signalforge"]

    def fetch_leads(self, db) -> list[dict[str, Any]]:
        query = self.module_config["lead_query"]
        leads = list(db.leads.find(query).sort("updated_at", -1).limit(self.limit))
        return leads

    def fetch_contacts(self, db) -> list[dict[str, Any]]:
        contacts = list(db.contacts.find({"module": self.module}).sort("imported_at", -1).limit(max(self.limit * 5, 25)))
        return self.sort_contacts(contacts)[: self.limit]

    def fetch_message_drafts(self, db) -> list[dict[str, Any]]:
        return list(
            db.message_drafts.find({"module": self.module})
            .sort([("created_at", -1), ("updated_at", -1)])
            .limit(self.limit)
        )

    def start_observed_run(self, db) -> str:
        run_object_id = ObjectId()
        run_id = str(run_object_id)
        input_summary = {
            "agent": self.agent_name,
            "module": self.module,
            "dry_run": self.dry_run,
            "limit": self.limit,
            "simulation_only": True,
        }
        run_doc = {
            "_id": run_object_id,
            "run_id": run_id,
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "module": self.module,
            "status": "running",
            "started_at": self.started_at,
            "completed_at": None,
            "input_summary": input_summary,
            "output_summary": {},
            "related_contacts": [],
            "related_leads": [],
            "related_messages": [],
            "related_deals": [],
            "warnings": ["Simulation-only run. No outbound action taken."],
            "errors": [],
        }
        db.agent_runs.insert_one(run_doc)
        return run_id

    def complete_observed_run(
        self,
        db,
        run_id: str,
        status: str,
        leads: list[dict[str, Any]],
        actions: list[dict[str, str]],
        log_path: str,
        error: str | None = None,
    ) -> None:
        completed_at = datetime.now(timezone.utc)
        related_contacts = [self.record_id(contact) for contact in self.contacts if self.record_id(contact)]
        related_leads = [self.record_id(lead) for lead in leads if self.record_id(lead)]
        related_messages = [self.record_id(message) for message in self.message_drafts if self.record_id(message)]
        output_summary = {
            "planned_action_count": len(actions),
            "lead_count": len(leads),
            "contact_count": len(self.contacts),
            "message_draft_count": len(self.message_drafts),
            "log_path": log_path,
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
        open_approvals = db.approval_requests.count_documents({"run_id": run_id, "status": "open"})
        final_status = "waiting_for_approval" if status == "completed" and open_approvals else status
        update: dict[str, Any] = {
            "status": final_status,
            "completed_at": completed_at,
            "output_summary": output_summary,
            "related_contacts": related_contacts,
            "related_leads": related_leads,
            "related_messages": related_messages,
        }
        if error:
            update["errors"] = [error]
        db.agent_runs.update_one({"run_id": run_id}, {"$set": update})

    def record_step(
        self,
        db,
        run_id: str,
        step_number: int,
        step_name: str,
        input_data: dict[str, Any],
        decision: str,
        output: dict[str, Any],
        status: str = "completed",
        artifact_refs: list[str] | None = None,
    ) -> None:
        db.agent_steps.insert_one(
            {
                "run_id": run_id,
                "agent_name": self.agent_name,
                "module": self.module,
                "step_number": step_number,
                "step_name": step_name,
                "status": status,
                "input": self.mongo_safe(input_data),
                "decision": decision,
                "output": self.mongo_safe(output),
                "artifact_refs": artifact_refs or [],
                "timestamp": datetime.now(timezone.utc),
            }
        )

    def record_artifacts(self, db, run_id: str, log_path: str, actions: list[dict[str, str]]) -> list[str]:
        artifact_docs = [
            {
                "run_id": run_id,
                "agent_name": self.agent_name,
                "module": self.module,
                "artifact_type": "vault_log",
                "label": "Agent run markdown log",
                "path": log_path,
                "created_at": datetime.now(timezone.utc),
            },
            {
                "run_id": run_id,
                "agent_name": self.agent_name,
                "module": self.module,
                "artifact_type": "planned_actions",
                "label": "Dry-run planned actions",
                "content": self.mongo_safe(actions),
                "created_at": datetime.now(timezone.utc),
            },
        ]
        result = db.agent_artifacts.insert_many(artifact_docs)
        return [str(item) for item in result.inserted_ids]

    def create_approval_requests(self, db, run_id: str, actions: list[dict[str, str]]) -> list[str]:
        now = datetime.now(timezone.utc)
        requests = []
        for index, action in enumerate(actions, start=1):
            requests.append(
                {
                    "run_id": run_id,
                    "agent_name": self.agent_name,
                    "module": self.module,
                    "request_type": "planned_action_review",
                    "status": "open",
                    "title": action.get("title", f"Review planned action {index}"),
                    "summary": action.get("planned_action", ""),
                    "target": action.get("target", ""),
                    "created_at": now,
                    "resolved_at": None,
                    "simulation_only": True,
                }
            )
        for draft in self.message_drafts:
            if draft.get("review_status") != "needs_review":
                continue
            requests.append(
                {
                    "run_id": run_id,
                    "agent_name": self.agent_name,
                    "module": self.module,
                    "request_type": "message_review",
                    "status": "open",
                    "title": f"Review message draft for {draft.get('recipient_name') or draft.get('company')}",
                    "summary": draft.get("subject_line", ""),
                    "target": draft.get("draft_key") or self.record_id(draft),
                    "message_draft_id": self.record_id(draft),
                    "created_at": now,
                    "resolved_at": None,
                    "simulation_only": True,
                }
            )
        if not requests:
            return []
        result = db.approval_requests.insert_many(requests)
        return [str(item) for item in result.inserted_ids]

    @staticmethod
    def sort_contacts(contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        segment_rank = {
            "high_priority": 0,
            "nurture": 1,
            "research_more": 2,
            "low_priority": 3,
        }
        return sorted(
            contacts,
            key=lambda contact: (
                segment_rank.get(contact.get("segment"), 99),
                -(contact.get("contact_score") or 0),
                str(contact.get("company") or "").lower(),
                str(contact.get("name") or "").lower(),
            ),
        )

    def plan_actions(self, leads: list[dict[str, Any]]) -> list[dict[str, str]]:
        raise NotImplementedError

    def module_context_summary(self) -> str:
        module_path = self.module_config.get("module_path")
        if module_path and module_path.exists():
            return f"Module docs: {module_path.relative_to(PROJECT_ROOT)}"
        return "Module docs: contractor engine runtime context"

    def no_data_action(self) -> dict[str, str]:
        return {
            "title": "No matching Mongo records found",
            "target": self.module,
            "reason": "The agent queried MongoDB but did not find module-specific records.",
            "planned_action": "Review module strategy docs, add sample source data, then run the relevant pipeline before taking action.",
        }

    def write_run_log(
        self,
        leads: list[dict[str, Any]],
        contacts: list[dict[str, Any]],
        message_drafts: list[dict[str, Any]],
        actions: list[dict[str, str]],
    ) -> str:
        logs_dir = self.vault_path / "logs" / "agents"
        logs_dir.mkdir(parents=True, exist_ok=True)

        timestamp = self.started_at.strftime("%Y%m%dT%H%M%SZ")
        log_path = logs_dir / f"{self.agent_name}_{self.module}_{timestamp}.md"

        action_rows = "\n".join(
            f"| {index} | {self.clean(action.get('title'))} | {self.clean(action.get('target'))} | {self.clean(action.get('planned_action'))} |"
            for index, action in enumerate(actions, start=1)
        )
        if not action_rows:
            action_rows = "| - | No actions planned | - | - |"

        lead_rows = "\n".join(
            f"| {self.clean(lead.get('company_name'))} | {self.clean(lead.get('review_status'))} | {self.clean(lead.get('outreach_status'))} | {self.clean(lead.get('lead_score') or lead.get('score'))} |"
            for lead in leads[:10]
        )
        if not lead_rows:
            lead_rows = "| No matching leads | - | - | - |"

        contact_rows = "\n".join(
            f"| {self.clean(contact.get('name'))} | {self.clean(contact.get('company'))} | {self.clean(contact.get('role'))} | {self.clean(contact.get('contact_score'))} | {self.clean(contact.get('segment'))} | {self.clean(contact.get('contact_status'))} | {self.clean(contact.get('source'))} |"
            for contact in contacts[:10]
        )
        if not contact_rows:
            contact_rows = "| No matching contacts | - | - | - | - | - | - |"

        draft_rows = "\n".join(
            f"| {self.clean(draft.get('recipient_name'))} | {self.clean(draft.get('target_type'))} | {self.clean(draft.get('review_status'))} | {self.clean(draft.get('send_status'))} | {self.clean(draft.get('response_status'))} | {self.clean(draft.get('subject_line'))} | {self.clean(draft.get('message_note_path'))} |"
            for draft in message_drafts[:10]
        )
        if not draft_rows:
            draft_rows = "| No matching message drafts | - | - | - | - | - | - |"

        content = f"""---
type: agent_run
agent: {self.agent_name}
module: {self.module}
dry_run: {str(self.dry_run).lower()}
created: {self.started_at.date().isoformat()}
---

# Agent Run: {self.agent_name}

## Context

- Module: {self.module}
- Module label: {self.module_config["label"]}
- Role: {self.agent_role}
- Dry run: {self.dry_run}
- Simulation only: true
- Started at: {self.started_at.isoformat()}
- {self.module_context_summary()}

## Safety

- No emails sent.
- No SMS sent.
- No DMs sent.
- No social posts published.
- No external APIs called.

## Mongo Leads Read

| Company | Review Status | Outreach Status | Score |
| --- | --- | --- | ---: |
{lead_rows}

## Mongo Contacts Read

| Name | Company | Role | Score | Segment | Status | Source |
| --- | --- | --- | ---: | --- | --- | --- |
{contact_rows}

## Message Drafts Available

| Recipient | Target Type | Review Status | Send Status | Response | Subject | Note |
| --- | --- | --- | --- | --- | --- | --- |
{draft_rows}

## Planned Actions

| # | Title | Target | Planned Action |
| ---: | --- | --- | --- |
{action_rows}
"""
        log_path.write_text(content, encoding="utf-8")
        return str(log_path.relative_to(self.vault_path))

    def print_actions(self, actions: list[dict[str, str]], log_path: str) -> None:
        print(f"Agent: {self.agent_name}")
        print(f"Module: {self.module}")
        print("Mode: simulation-only")
        print(f"Dry run: {self.dry_run}")
        if self.run_id:
            print(f"Agent run ID: {self.run_id}")
        print(f"Planned actions: {len(actions)}")
        for index, action in enumerate(actions, start=1):
            print(f"{index}. {action.get('title')} -> {action.get('planned_action')}")
        print(f"Agent run log: /vault/{log_path}")

    @staticmethod
    def clean(value: Any) -> str:
        if value is None or value == "":
            return "-"
        return str(value).replace("|", "\\|").replace("\n", " ")

    @staticmethod
    def record_id(record: dict[str, Any]) -> str:
        value = record.get("_id") or record.get("contact_key") or record.get("company_slug") or record.get("draft_key")
        return str(value) if value else ""

    def compact_records(self, records: list[dict[str, Any]], record_type: str) -> list[dict[str, Any]]:
        compact = []
        for record in records[:10]:
            compact.append(
                {
                    "id": self.record_id(record),
                    "type": record_type,
                    "name": record.get("name") or record.get("recipient_name") or record.get("company_name"),
                    "company": record.get("company") or record.get("company_name"),
                    "status": record.get("contact_status")
                    or record.get("review_status")
                    or record.get("send_status")
                    or record.get("outreach_status"),
                    "score": record.get("contact_score") or record.get("lead_score") or record.get("score"),
                }
            )
        return compact

    def mongo_safe(self, value: Any) -> Any:
        if isinstance(value, ObjectId):
            return str(value)
        if isinstance(value, datetime):
            return value
        if isinstance(value, list):
            return [self.mongo_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self.mongo_safe(item) for key, item in value.items()}
        return value
