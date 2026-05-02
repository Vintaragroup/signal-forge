from datetime import datetime, timezone

from agents.base_agent import BaseAgent
from agents.gpt_client import generate_agent_response


GPT_CONFIDENCE_THRESHOLD = 0.6
GPT_STEP_NAME = "gpt_followup_recommendation"


class FollowupAgent(BaseAgent):
    agent_name = "followup"
    agent_role = "Identify leads needing follow-up"

    def fetch_leads(self, db) -> list[dict]:
        module_query = self.module_config["lead_query"]
        followup_query = {
            "$or": [
                {"outreach_status": "follow_up_needed"},
                {"review_status": "research_more"},
                {"outreach_status": "sent"},
                {"outreach_status": "replied"},
            ]
        }
        query = {"$and": [module_query, followup_query]}
        return list(db.leads.find(query).sort("updated_at", -1).limit(self.limit))

    def plan_actions(self, leads: list[dict]) -> list[dict[str, str]]:
        gpt_actions = self.plan_gpt_actions(leads)
        if gpt_actions is not None:
            return gpt_actions

        if not leads:
            if self.contacts:
                return [
                    {
                        "title": f"Review imported contact status for {contact.get('company') or contact.get('name')}",
                        "target": contact.get("company") or contact.get("name") or self.module,
                        "reason": contact.get("priority_reason") or f"contact_status={contact.get('contact_status', 'imported')}; source={contact.get('source', '-')}",
                        "planned_action": f"Decide whether this contact needs research, manual outreach preparation, or no action. Segment: {contact.get('segment', 'unscored')}; score: {contact.get('contact_score', '-')}. Do not send anything automatically.",
                    }
                    for contact in self.contacts
                ]
            return [
                {
                    "title": "No follow-up records found",
                    "target": self.module,
                    "reason": "MongoDB has no matching follow-up, sent, replied, or research_more records for this module.",
                    "planned_action": "Review pipeline report and continue manual outreach tracking before scheduling follow-up work.",
                }
            ]

        actions = []
        for lead in leads:
            company = lead.get("company_name", "Unknown company")
            outreach_status = lead.get("outreach_status", "not_set")
            review_status = lead.get("review_status", "not_set")
            if outreach_status == "follow_up_needed":
                planned = "Open the follow-up note, draft a short human-approved follow-up, and update status after action."
            elif review_status == "research_more":
                planned = "Complete research gap before deciding pursue or skip."
            elif outreach_status == "sent":
                planned = "Check whether enough time has passed and decide if follow_up_needed should be logged."
            else:
                planned = "Review latest reply context and decide next manual action."

            actions.append(
                {
                    "title": f"Follow-up review for {company}",
                    "target": company,
                    "reason": f"review_status={review_status}; outreach_status={outreach_status}",
                    "planned_action": planned,
                }
            )
        return actions

    def plan_gpt_actions(self, leads: list[dict]) -> list[dict[str, str]] | None:
        targets = self.gpt_targets(leads)
        if not targets:
            return None

        first_result = generate_agent_response(
            agent_name="followup_agent",
            module=self.module,
            task="recommend_followup_action",
            context=self.safe_gpt_context(targets[0][1], targets[0][0]),
        )
        if not first_result.get("enabled"):
            return None

        actions = []
        results = [(*targets[0], first_result)]
        for target_type, target in targets[1:]:
            result = generate_agent_response(
                agent_name="followup_agent",
                module=self.module,
                task="recommend_followup_action",
                context=self.safe_gpt_context(target, target_type),
            )
            results.append((target_type, target, result))

        for index, (target_type, target, result) in enumerate(results, start=1):
            display = self.target_display(target, target_type)
            confidence = float(result.get("confidence") or 0.0)
            artifact_id = None
            approval_id = None

            if result.get("used_gpt") and confidence >= GPT_CONFIDENCE_THRESHOLD:
                artifact_id = self.create_gpt_recommendation_artifact(target_type, target, result)
                actions.append(
                    {
                        "title": f"GPT follow-up recommendation for {display}",
                        "target": display,
                        "reason": result.get("reasoning_summary") or "GPT recommended a follow-up action for human review.",
                        "planned_action": (
                            "Review the GPT follow-up recommendation before taking any manual action. "
                            f"Artifact: {artifact_id or 'not_recorded'}. No message sent and send status was not changed."
                        ),
                    }
                )
            else:
                approval_id = self.create_gpt_approval_request(target_type, target, result, confidence)
                actions.append(
                    {
                        "title": f"GPT follow-up needs human review for {display}",
                        "target": display,
                        "reason": result.get("reasoning_summary") or result.get("error") or "GPT did not produce a confident follow-up recommendation.",
                        "planned_action": (
                            "No follow-up recommendation artifact was finalized because GPT confidence was too low or no usable GPT output was available. "
                            f"Approval request: {approval_id}. No message sent and send status was not changed."
                        ),
                    }
                )

            self.record_gpt_step(index, target_type, target, result, artifact_id, approval_id)

        return actions

    def gpt_targets(self, leads: list[dict]) -> list[tuple[str, dict]]:
        message_targets = []
        for message in self.message_drafts:
            response_status = message.get("response_status") or ""
            send_status = message.get("send_status") or ""
            if send_status == "sent" or response_status in {"interested", "requested_info", "call_booked"} or message.get("response_events"):
                message_targets.append(("message", message))
        if message_targets:
            return message_targets
        if leads:
            return [("lead", lead) for lead in leads]
        return [("contact", contact) for contact in self.contacts]

    def safe_gpt_context(self, target: dict, target_type: str) -> dict:
        if target_type == "message":
            return {
                "target_type": "message",
                "module": target.get("module") or self.module,
                "recipient_name": target.get("recipient_name"),
                "company": target.get("company"),
                "subject_line": target.get("subject_line"),
                "review_status": target.get("review_status"),
                "send_status": target.get("send_status"),
                "response_status": target.get("response_status"),
                "sent_at": target.get("sent_at"),
                "last_response_at": target.get("last_response_at"),
                "response_events": target.get("response_events") or [],
                "review_events": target.get("review_events") or [],
                "message_target_type": target.get("target_type") or "message",
                "target_id": self.record_id(target),
            }
        if target_type == "lead":
            return {
                "target_type": "lead",
                "company_name": target.get("company_name"),
                "review_status": target.get("review_status"),
                "outreach_status": target.get("outreach_status"),
                "lead_score": target.get("lead_score") or target.get("score"),
                "priority_reason": target.get("priority_reason"),
                "recommended_offer": target.get("recommended_offer"),
                "next_action": target.get("next_action"),
                "source": target.get("source"),
            }
        return {
            "target_type": "contact",
            "name": target.get("name"),
            "company": target.get("company"),
            "role": target.get("role"),
            "module": target.get("module") or self.module,
            "segment": target.get("segment"),
            "contact_score": target.get("contact_score"),
            "contact_status": target.get("contact_status"),
            "priority_reason": target.get("priority_reason"),
            "notes": target.get("notes"),
            "source": target.get("source"),
        }

    def record_gpt_step(self, index: int, target_type: str, target: dict, result: dict, artifact_id: str | None, approval_id: str | None) -> None:
        if self.db is None or not self.run_id:
            return
        self.record_step(
            self.db,
            self.run_id,
            40 + index,
            GPT_STEP_NAME,
            {
                "target_type": target_type,
                "target_id": self.record_id(target),
                "task": "recommend_followup_action",
            },
            "Use GPT only to recommend a human-reviewed follow-up action; never send or change send status.",
            {
                "enabled": bool(result.get("enabled")),
                "used_gpt": bool(result.get("used_gpt")),
                "confidence": float(result.get("confidence") or 0.0),
                "reasoning_summary": result.get("reasoning_summary", ""),
                "output_length": len(result.get("output") or ""),
                "created_artifact_id": artifact_id,
                "created_approval_request_id": approval_id,
                "recommendation_created": bool(artifact_id),
                "error": result.get("error"),
                "selected_model": result.get("selected_model"),
                "routing_reason": result.get("routing_reason"),
                "complexity": result.get("complexity"),
            },
        )

    def create_gpt_recommendation_artifact(self, target_type: str, target: dict, result: dict) -> str | None:
        if self.db is None or not self.run_id:
            return None
        now = datetime.now(timezone.utc)
        artifact = {
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "module": self.module,
            "artifact_type": "gpt_followup_recommendation",
            "label": f"GPT follow-up recommendation for {self.target_display(target, target_type)}",
            "content": {
                "recommendation": result.get("output") or "",
                "target_type": target_type,
                "target_id": self.record_id(target),
                "target": self.target_key(target, target_type),
                "confidence": float(result.get("confidence") or 0.0),
                "reasoning_summary": result.get("reasoning_summary", ""),
                "generated_by_agent": self.agent_name,
                "agent_run_id": self.run_id,
                "agent_step_name": GPT_STEP_NAME,
                "send_status_changed": False,
                "outbound_actions_taken": 0,
            },
            "created_at": now,
        }
        insert_result = self.db.agent_artifacts.insert_one(artifact)
        return str(insert_result.inserted_id)

    def create_gpt_approval_request(self, target_type: str, target: dict, result: dict, confidence: float) -> str:
        if self.db is None or not self.run_id:
            return "not_recorded"
        reason = result.get("reasoning_summary") or result.get("error") or "GPT output was not confident enough to create a follow-up recommendation."
        is_failure = bool(result.get("error")) or not str(result.get("output") or "").strip()
        request_doc = {
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "module": self.module,
            "request_type": "gpt_followup_recommendation_review",
            "status": "open",
            "title": f"Review GPT follow-up recommendation for {self.target_display(target, target_type)}",
            "summary": "GPT could not produce a usable follow-up recommendation." if is_failure else f"GPT produced a low-confidence follow-up recommendation for {self.target_display(target, target_type)}.",
            "reason_for_review": reason,
            "request_origin": "system" if is_failure else "gpt",
            "is_test": False,
            "severity": "error" if is_failure else "needs_review",
            "user_facing_summary": "GPT failed before producing a usable follow-up recommendation." if is_failure else f"Review the low-confidence GPT follow-up recommendation for {self.target_display(target, target_type)} before using it.",
            "technical_reason": reason,
            "target": self.target_key(target, target_type),
            "target_type": target_type,
            "linked_target_id": self.record_id(target),
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

    def target_key(self, target: dict, target_type: str) -> str:
        if target_type == "message":
            return str(target.get("draft_key") or target.get("_id") or self.target_display(target, target_type))
        if target_type == "lead":
            return str(target.get("company_slug") or target.get("_id") or self.target_display(target, target_type))
        return str(target.get("contact_key") or target.get("_id") or self.target_display(target, target_type))

    def target_display(self, target: dict, target_type: str) -> str:
        if target_type == "message":
            return target.get("recipient_name") or target.get("company") or target.get("subject_line") or "Message"
        if target_type == "lead":
            return target.get("company_name") or "Lead"
        return target.get("company") or target.get("name") or "Contact"
