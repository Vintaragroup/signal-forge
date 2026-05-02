from datetime import datetime, timezone
from typing import Any

from agents.base_agent import BaseAgent
from agents.gpt_client import generate_agent_response


GPT_CONFIDENCE_THRESHOLD = 0.6
GPT_STEP_NAME = "gpt_content_plan_generation"


class ContentAgent(BaseAgent):
    agent_name = "content"
    agent_role = "Prepare content and post ideas from module signals"

    def plan_actions(self, leads: list[dict]) -> list[dict[str, str]]:
        gpt_actions = self.plan_gpt_actions(leads)
        if gpt_actions is not None:
            return self.add_tool_research_actions(gpt_actions, "content research signals")

        if not leads:
            if self.contacts:
                return self.add_tool_research_actions([
                    {
                        "title": f"Content idea from {contact.get('company') or contact.get('name')}",
                        "target": contact.get("company") or contact.get("name") or self.module,
                        "reason": contact.get("priority_reason") or contact.get("notes", "Imported contact context is available."),
                        "planned_action": f"Draft one educational post idea for human review. Segment: {contact.get('segment', 'unscored')}; score: {contact.get('contact_score', '-')}.",
                    }
                    for contact in self.contacts[:8]
                ], "content contact research")
            return self.add_tool_research_actions([
                {
                    "title": "Create starter content themes",
                    "target": self.module,
                    "reason": "No module-specific Mongo records were found.",
                    "planned_action": "Use module strategy docs to draft three educational posts, one checklist, and one campaign explainer for human review.",
                }
            ], "content starter research")

        actions = []
        for lead in leads[:8]:
            company = lead.get("company_name", "Unknown company")
            signal = lead.get("signal") or lead.get("marketing_gap") or "No signal available"
            offer = lead.get("recommended_offer", "module-specific offer")
            actions.append(
                {
                    "title": f"Content idea from {company}",
                    "target": company,
                    "reason": signal,
                    "planned_action": f"Draft a short post explaining the problem behind this signal and softly connect it to: {offer}.",
                }
            )
        return self.add_tool_research_actions(actions, "content research signals")

    def plan_gpt_actions(self, leads: list[dict]) -> list[dict[str, str]] | None:
        context = self.safe_gpt_context(leads)
        result = generate_agent_response(
            agent_name="content_agent",
            module=self.module,
            task="generate_content_plan",
            context=context,
        )
        if not result.get("enabled"):
            return None

        confidence = float(result.get("confidence") or 0.0)
        artifact_id = None
        approval_id = None

        if result.get("used_gpt") and confidence >= GPT_CONFIDENCE_THRESHOLD:
            note_path = self.write_gpt_content_note(result, context)
            artifact_id = self.create_gpt_content_artifact(result, context, note_path)
            actions = [
                {
                    "title": f"GPT content plan for {self.module}",
                    "target": self.module,
                    "reason": result.get("reasoning_summary") or "GPT generated module-specific content ideas for human review.",
                    "planned_action": (
                        "Review the GPT-generated content note before editing, scheduling, or publishing anywhere. "
                        f"Artifact: {artifact_id or 'not_recorded'}; note: {note_path or 'not_recorded'}. No post published or scheduled."
                    ),
                }
            ]
        else:
            approval_id = self.create_gpt_approval_request(result, confidence)
            actions = [
                {
                    "title": f"GPT content plan needs human review for {self.module}",
                    "target": self.module,
                    "reason": result.get("reasoning_summary") or result.get("error") or "GPT did not produce a confident content plan.",
                    "planned_action": (
                        "No content draft note was created because GPT confidence was too low or no usable GPT output was available. "
                        f"Approval request: {approval_id}. No post published or scheduled."
                    ),
                }
            ]

        self.record_gpt_step(result, artifact_id, approval_id)
        return actions

    def safe_gpt_context(self, leads: list[dict]) -> dict:
        return {
            "module": self.module,
            "module_docs": self.module_docs_context(),
            "campaign_context": self.campaign_context(),
            "contacts": [self.compact_content_record(contact, "contact") for contact in self.contacts[:8]],
            "leads": [self.compact_content_record(lead, "lead") for lead in leads[:8]],
            "deals": [self.compact_content_record(deal, "deal") for deal in self.fetch_relevant_deals()[:8]],
            "message_drafts": [self.compact_content_record(draft, "message") for draft in self.message_drafts[:8]],
            "safety": {
                "publish_posts": False,
                "schedule_posts": False,
                "requires_human_review": True,
            },
        }

    def module_docs_context(self) -> dict[str, str]:
        module_path = self.module_config.get("module_path")
        docs = {}
        if module_path and module_path.exists():
            for name in ("CLIENT_PROFILE.md", "CAMPAIGN_PLAN.md", "CONTENT_STRATEGY.md", "AUDIENCE_PERSONAS.md", "SIGNAL_SOURCES.md"):
                path = module_path / name
                if path.exists():
                    docs[name] = path.read_text(encoding="utf-8", errors="ignore")[:4000]
        prompt_path = self.vault_path / "prompts" / "content_generation_prompt.md"
        if prompt_path.exists():
            docs["content_generation_prompt.md"] = prompt_path.read_text(encoding="utf-8", errors="ignore")[:3000]
        return docs

    def campaign_context(self) -> dict[str, Any]:
        return {
            "module_label": self.module_config["label"],
            "module_context": self.module_context_summary(),
            "content_goal": "Generate useful module-specific content ideas and draft posts for human review.",
            "approval_required": True,
        }

    def fetch_relevant_deals(self) -> list[dict]:
        if self.db is None:
            return []
        return list(self.db.deals.find({"module": self.module}).sort([("updated_at", -1), ("created_at", -1)]).limit(self.limit))

    def compact_content_record(self, record: dict, record_type: str) -> dict:
        return {
            "id": self.record_id(record),
            "type": record_type,
            "name": record.get("name") or record.get("recipient_name") or record.get("company") or record.get("company_name"),
            "status": record.get("review_status") or record.get("send_status") or record.get("outreach_status") or record.get("contact_status") or record.get("outcome"),
            "score": record.get("contact_score") or record.get("lead_score") or record.get("score"),
            "signal": record.get("signal") or record.get("marketing_gap") or record.get("priority_reason") or record.get("notes"),
            "source": record.get("source"),
        }

    def record_gpt_step(self, result: dict, artifact_id: str | None, approval_id: str | None) -> None:
        if self.db is None or not self.run_id:
            return
        self.record_step(
            self.db,
            self.run_id,
            50,
            GPT_STEP_NAME,
            {"module": self.module, "task": "generate_content_plan"},
            "Use GPT only to create human-reviewed content ideas and draft notes; never publish or schedule posts.",
            {
                "enabled": bool(result.get("enabled")),
                "used_gpt": bool(result.get("used_gpt")),
                "confidence": float(result.get("confidence") or 0.0),
                "reasoning_summary": result.get("reasoning_summary", ""),
                "output_length": len(result.get("output") or ""),
                "created_artifact_id": artifact_id,
                "created_approval_request_id": approval_id,
                "content_draft_created": bool(artifact_id),
                "published": False,
                "scheduled": False,
                "error": result.get("error"),
                "selected_model": result.get("selected_model"),
                "routing_reason": result.get("routing_reason"),
                "complexity": result.get("complexity"),
            },
        )

    def write_gpt_content_note(self, result: dict, context: dict) -> str | None:
        if not self.run_id:
            return None
        notes_dir = self.vault_path / "content" / "agents"
        notes_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = notes_dir / f"{self.module}_gpt_content_{timestamp}.md"
        output = result.get("output") or ""
        content = f"""---
type: content
status: needs_review
source: gpt
module: {self.module}
generated_by_agent: {self.agent_name}
agent_run_id: {self.run_id}
agent_step_name: {GPT_STEP_NAME}
gpt_confidence: {float(result.get("confidence") or 0.0)}
created: {datetime.now(timezone.utc).isoformat()}
published: false
scheduled: false
---

# GPT Content Draft: {self.module}

## Review Status

- Human review required: true
- Published: false
- Scheduled: false
- Reasoning summary: {result.get("reasoning_summary") or "No reasoning summary recorded."}

## Draft

{output}

## Source Context

- Module: {self.module}
- Contacts considered: {len(context.get("contacts") or [])}
- Leads considered: {len(context.get("leads") or [])}
- Deals considered: {len(context.get("deals") or [])}
- Message drafts considered: {len(context.get("message_drafts") or [])}
"""
        path.write_text(content, encoding="utf-8")
        return str(path.relative_to(self.vault_path))

    def create_gpt_content_artifact(self, result: dict, context: dict, note_path: str | None) -> str | None:
        if self.db is None or not self.run_id:
            return None
        artifact = {
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "module": self.module,
            "artifact_type": "gpt_content_plan",
            "label": f"GPT content plan for {self.module}",
            "path": note_path,
            "content": {
                "draft": result.get("output") or "",
                "confidence": float(result.get("confidence") or 0.0),
                "reasoning_summary": result.get("reasoning_summary", ""),
                "generated_by_agent": self.agent_name,
                "agent_run_id": self.run_id,
                "agent_step_name": GPT_STEP_NAME,
                "source_context_counts": {
                    "contacts": len(context.get("contacts") or []),
                    "leads": len(context.get("leads") or []),
                    "deals": len(context.get("deals") or []),
                    "message_drafts": len(context.get("message_drafts") or []),
                },
                "published": False,
                "scheduled": False,
            },
            "created_at": datetime.now(timezone.utc),
        }
        insert_result = self.db.agent_artifacts.insert_one(artifact)
        return str(insert_result.inserted_id)

    def create_gpt_approval_request(self, result: dict, confidence: float) -> str:
        if self.db is None or not self.run_id:
            return "not_recorded"
        reason = result.get("reasoning_summary") or result.get("error") or "GPT output was not confident enough to create a content plan."
        is_failure = bool(result.get("error")) or not str(result.get("output") or "").strip()
        request_doc = {
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "module": self.module,
            "request_type": "gpt_content_plan_review",
            "status": "open",
            "title": f"Review GPT content plan for {self.module}",
            "summary": "GPT could not produce a usable content plan." if is_failure else f"GPT produced a low-confidence content plan for {self.module}.",
            "reason_for_review": reason,
            "request_origin": "system" if is_failure else "gpt",
            "is_test": False,
            "severity": "error" if is_failure else "needs_review",
            "user_facing_summary": "GPT failed before producing a usable content plan." if is_failure else f"Review the low-confidence GPT content plan for {self.module} before using it.",
            "technical_reason": reason,
            "target": self.module,
            "target_type": "module",
            "gpt_confidence": confidence,
            "gpt_used": bool(result.get("used_gpt")),
            "gpt_output_length": len(result.get("output") or ""),
            "generated_by_agent": self.agent_name,
            "agent_run_id": self.run_id,
            "agent_step_name": GPT_STEP_NAME,
            "created_at": datetime.now(timezone.utc),
            "resolved_at": None,
            "simulation_only": True,
            **({"workspace_slug": self.workspace_slug} if self.workspace_slug else {}),
        }
        insert_result = self.db.approval_requests.insert_one(request_doc)
        return str(insert_result.inserted_id)

