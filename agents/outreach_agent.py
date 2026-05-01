import re
from datetime import datetime, timezone

from agents.base_agent import BaseAgent
from agents.gpt_client import generate_agent_response


GPT_CONFIDENCE_THRESHOLD = 0.6


class OutreachAgent(BaseAgent):
    agent_name = "outreach"
    agent_role = "Prepare B2B outreach actions for human review"

    def plan_actions(self, leads: list[dict]) -> list[dict[str, str]]:
        gpt_actions = self.plan_gpt_actions(leads)
        if gpt_actions is not None:
            return gpt_actions

        if not leads:
            if self.contacts:
                return [
                    {
                        "title": f"Review imported contact for {contact.get('company') or contact.get('name')}",
                        "target": contact.get("company") or contact.get("name") or self.module,
                        "reason": contact.get("priority_reason") or contact.get("notes", "Imported contact is available for human review."),
                        "planned_action": f"Prepare a human-reviewed outreach angle. Segment: {contact.get('segment', 'unscored')}; score: {contact.get('contact_score', '-')}. Do not send anything automatically.",
                    }
                    for contact in self.contacts
                ]
            return [self.no_data_action()]

        actions = []
        for lead in leads:
            company = lead.get("company_name", "Unknown company")
            status = lead.get("review_status", "not_set")
            outreach = lead.get("outreach_draft", "")
            offer = lead.get("recommended_offer", "review recommended offer")

            if status == "pursue":
                planned = "Review outreach note, confirm offer, and manually prepare a send-ready message."
            elif status == "needs_review":
                planned = "Review lead intelligence before deciding pursue, research_more, or skip."
            else:
                planned = f"No outbound action; current review status is {status}."

            actions.append(
                {
                    "title": f"Outreach plan for {company}",
                    "target": company,
                    "reason": lead.get("priority_reason", "No priority reason available."),
                    "planned_action": f"{planned} Offer angle: {offer}. Draft available: {bool(outreach)}.",
                }
            )
        return actions

    def plan_gpt_actions(self, leads: list[dict]) -> list[dict[str, str]] | None:
        targets = self.gpt_targets(leads)
        if not targets:
            return None

        first_result = generate_agent_response(
            agent_name="outreach_agent",
            module=self.module,
            task="generate_outreach_message",
            context=self.safe_gpt_context(targets[0][1], targets[0][0]),
        )
        if not first_result.get("enabled"):
            return None

        actions = []
        results = [(*targets[0], first_result)]
        for target_type, target in targets[1:]:
            result = generate_agent_response(
                agent_name="outreach_agent",
                module=self.module,
                task="generate_outreach_message",
                context=self.safe_gpt_context(target, target_type),
            )
            results.append((target_type, target, result))

        for index, (target_type, target, result) in enumerate(results, start=1):
            self.record_gpt_step(index, target_type, target, result)
            display = self.target_display(target, target_type)
            confidence = float(result.get("confidence") or 0.0)

            if result.get("used_gpt") and confidence >= GPT_CONFIDENCE_THRESHOLD:
                draft = self.create_gpt_message_draft(target_type, target, result)
                actions.append(
                    {
                        "title": f"GPT draft ready for {display}",
                        "target": display,
                        "reason": result.get("reasoning_summary") or "GPT generated a draft for human review.",
                        "planned_action": (
                            "Review the GPT-generated message draft before any manual send. "
                            f"Draft: {draft.get('draft_key')}. No outbound action taken."
                        ),
                    }
                )
                continue

            approval_id = self.create_gpt_approval_request(target_type, target, result, confidence)
            reason = result.get("reasoning_summary") or result.get("error") or "GPT did not produce a confident draft."
            actions.append(
                {
                    "title": f"GPT draft needs human review for {display}",
                    "target": display,
                    "reason": reason,
                    "planned_action": (
                        "No message draft was created because GPT confidence was too low or no usable GPT output was available. "
                        f"Approval request: {approval_id}."
                    ),
                }
            )

        return actions

    def gpt_targets(self, leads: list[dict]) -> list[tuple[str, dict]]:
        if leads:
            return [("lead", lead) for lead in leads]
        return [("contact", contact) for contact in self.contacts]

    def safe_gpt_context(self, target: dict, target_type: str) -> dict:
        if target_type == "contact":
            return {
                "target_type": "contact",
                "name": target.get("name"),
                "company": target.get("company"),
                "role": target.get("role"),
                "module": target.get("module") or self.module,
                "segment": target.get("segment"),
                "contact_score": target.get("contact_score"),
                "priority_reason": target.get("priority_reason"),
                "recommended_action": target.get("recommended_action"),
                "notes": target.get("notes"),
                "source": target.get("source"),
            }
        return {
            "target_type": "lead",
            "company_name": target.get("company_name"),
            "business_type": target.get("business_type"),
            "location": target.get("location"),
            "review_status": target.get("review_status"),
            "outreach_status": target.get("outreach_status"),
            "lead_score": target.get("lead_score") or target.get("score"),
            "priority_reason": target.get("priority_reason"),
            "recommended_offer": target.get("recommended_offer"),
            "next_action": target.get("next_action"),
            "marketing_gap": target.get("marketing_gap"),
            "source": target.get("source"),
        }

    def record_gpt_step(self, index: int, target_type: str, target: dict, result: dict) -> None:
        if self.db is None or not self.run_id:
            return
        self.record_step(
            self.db,
            self.run_id,
            30 + index,
            "gpt_message_generation",
            {
                "target_type": target_type,
                "target_id": self.record_id(target),
                "task": "generate_outreach_message",
            },
            "Use GPT only for a local draft that still requires human review.",
            {
                "enabled": bool(result.get("enabled")),
                "used_gpt": bool(result.get("used_gpt")),
                "confidence": float(result.get("confidence") or 0.0),
                "reasoning_summary": result.get("reasoning_summary", ""),
                "output_length": len(result.get("output") or ""),
                "error": result.get("error"),
            },
        )

    def create_gpt_message_draft(self, target_type: str, target: dict, result: dict) -> dict:
        if self.db is None:
            return {}

        now = datetime.now(timezone.utc)
        display = self.target_display(target, target_type)
        key = self.gpt_draft_key(target_type, target)
        existing = self.db.message_drafts.find_one({"draft_key": key})
        if existing:
            self.message_drafts.append(existing)
            return existing

        draft = {
            "draft_key": key,
            "module": self.module,
            "target_type": target_type,
            "target_id": self.record_id(target),
            "target_key": self.target_key(target, target_type),
            "recipient_name": display,
            "company": self.target_company(target, target_type),
            "segment": target.get("segment") if target_type == "contact" else "",
            "lead_score": target.get("lead_score") or target.get("score") if target_type == "lead" else None,
            "recommended_action": target.get("recommended_action") or target.get("recommended_offer") or target.get("next_action"),
            "priority_reason": target.get("priority_reason") or target.get("notes") or "GPT-generated outreach draft for human review.",
            "subject_line": f"Human review draft for {display}",
            "message_body": result.get("output") or "",
            "review_status": "needs_review",
            "send_status": "not_sent",
            "source": "gpt",
            "generated_by_agent": self.agent_name,
            "agent_run_id": self.run_id,
            "agent_step_name": "gpt_message_generation",
            "gpt_confidence": float(result.get("confidence") or 0.0),
            "gpt_reasoning_summary": result.get("reasoning_summary", ""),
            "created_at": now,
            "updated_at": now,
        }
        self.db.message_drafts.insert_one(draft)
        self.message_drafts.append(draft)
        return draft

    def create_gpt_approval_request(self, target_type: str, target: dict, result: dict, confidence: float) -> str:
        if self.db is None or not self.run_id:
            return "not_recorded"

        now = datetime.now(timezone.utc)
        display = self.target_display(target, target_type)
        reason = result.get("reasoning_summary") or result.get("error") or "GPT output was not confident enough to create a message draft."
        is_failure = bool(result.get("error")) or not str(result.get("output") or "").strip()
        request_doc = {
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "module": self.module,
            "request_type": "gpt_message_generation_review",
            "status": "open",
            "title": f"Review GPT outreach result for {display}",
            "summary": "GPT could not produce a usable outreach draft." if is_failure else f"GPT drafted a low-confidence outreach idea for {display}.",
            "reason_for_review": reason,
            "request_origin": "system" if is_failure else "gpt",
            "is_test": False,
            "severity": "error" if is_failure else "needs_review",
            "user_facing_summary": "GPT failed before producing a usable outreach draft." if is_failure else f"Review the low-confidence GPT outreach result for {display} before deciding whether to convert it into a draft.",
            "technical_reason": reason,
            "target": self.target_key(target, target_type),
            "target_type": target_type,
            "linked_target_id": self.record_id(target),
            "gpt_confidence": confidence,
            "gpt_used": bool(result.get("used_gpt")),
            "gpt_output_length": len(result.get("output") or ""),
            "created_at": now,
            "resolved_at": None,
            "simulation_only": True,
        }
        insert_result = self.db.approval_requests.insert_one(request_doc)
        return str(insert_result.inserted_id)

    def gpt_draft_key(self, target_type: str, target: dict) -> str:
        return self.slugify(f"{self.module}-gpt-{target_type}-{self.target_key(target, target_type)}")

    def target_key(self, target: dict, target_type: str) -> str:
        if target_type == "contact":
            return str(target.get("contact_key") or target.get("_id") or self.target_display(target, target_type))
        return str(target.get("company_slug") or target.get("_id") or self.target_display(target, target_type))

    def target_display(self, target: dict, target_type: str) -> str:
        if target_type == "contact":
            return target.get("name") or target.get("company") or "Contact"
        return target.get("company_name") or "Lead"

    def target_company(self, target: dict, target_type: str) -> str:
        if target_type == "contact":
            return target.get("company") or ""
        return target.get("company_name") or ""

    @staticmethod
    def slugify(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or "gpt-draft"
