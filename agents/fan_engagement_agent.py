from datetime import datetime, timezone
from typing import Any

from agents.base_agent import BaseAgent
from agents.gpt_client import generate_agent_response


GPT_CONFIDENCE_THRESHOLD = 0.6
GPT_STEP_NAME = "gpt_fan_engagement_plan_generation"


class FanEngagementAgent(BaseAgent):
    agent_name = "fan_engagement"
    agent_role = "Prepare music and entertainment engagement ideas"

    def plan_actions(self, leads: list[dict]) -> list[dict[str, str]]:
        gpt_actions = self.plan_gpt_actions(leads)
        if gpt_actions is not None:
            return gpt_actions

        if self.module != "artist_growth":
            return [
                {
                    "title": "Fan engagement module mismatch",
                    "target": self.module,
                    "reason": "Fan engagement planning is primarily designed for artist_growth.",
                    "planned_action": "Use artist_growth for fan engagement, or adapt this module's personas before taking action.",
                }
            ]

        if not leads:
            if self.contacts:
                return [
                    {
                        "title": f"Fan engagement idea from {contact.get('name') or contact.get('company')}",
                        "target": contact.get("company") or contact.get("name") or "artist_growth",
                        "reason": contact.get("priority_reason") or contact.get("notes", "Imported artist contact context is available."),
                        "planned_action": f"Prepare a human-reviewed engagement prompt or content touchpoint. Segment: {contact.get('segment', 'unscored')}; score: {contact.get('contact_score', '-')}.",
                    }
                    for contact in self.contacts[:8]
                ]
            return [
                {
                    "title": "Plan artist engagement prompts",
                    "target": "artist_growth",
                    "reason": "No artist opportunity records were found in MongoDB.",
                    "planned_action": "Draft release-day fan prompts, behind-the-scenes content ideas, and a community reply plan for human review.",
                },
                {
                    "title": "Plan venue and fan touchpoints",
                    "target": "artist_growth",
                    "reason": "Artist module docs are available but no runtime records exist yet.",
                    "planned_action": "Prepare a non-automated checklist for venue tags, fan comments, and post-show follow-ups.",
                },
            ]

        actions = []
        for lead in leads[:8]:
            target = lead.get("company_name", "Artist opportunity")
            actions.append(
                {
                    "title": f"Fan engagement idea for {target}",
                    "target": target,
                    "reason": lead.get("priority_reason", "Audience opportunity needs review."),
                    "planned_action": "Prepare a human-reviewed engagement prompt tied to the release, show, or audience signal.",
                }
            )
        return actions

    def plan_gpt_actions(self, leads: list[dict]) -> list[dict[str, str]] | None:
        if self.module != "artist_growth":
            return None

        context = self.safe_gpt_context(leads)
        result = generate_agent_response(
            agent_name="fan_engagement_agent",
            module=self.module,
            task="generate_fan_engagement_plan",
            context=context,
        )
        if not result.get("enabled"):
            return None

        confidence = float(result.get("confidence") or 0.0)
        artifact_id = None
        approval_id = None

        if result.get("used_gpt") and confidence >= GPT_CONFIDENCE_THRESHOLD:
            note_path = self.write_gpt_engagement_note(result, context)
            artifact_id = self.create_gpt_engagement_artifact(result, context, note_path)
            actions = [
                {
                    "title": "GPT fan engagement plan for artist_growth",
                    "target": "artist_growth",
                    "reason": result.get("reasoning_summary") or "GPT generated fan engagement ideas for human review.",
                    "planned_action": (
                        "Review the GPT-generated fan engagement note before any manual community action. "
                        f"Artifact: {artifact_id or 'not_recorded'}; note: {note_path or 'not_recorded'}. "
                        "No DMs, comments, posts, scraping, publishing, or scheduling performed."
                    ),
                }
            ]
        else:
            approval_id = self.create_gpt_approval_request(result, confidence)
            actions = [
                {
                    "title": "GPT fan engagement plan needs human review for artist_growth",
                    "target": "artist_growth",
                    "reason": result.get("reasoning_summary") or result.get("error") or "GPT did not produce a confident fan engagement plan.",
                    "planned_action": (
                        "No engagement plan note was created because GPT confidence was too low or no usable GPT output was available. "
                        f"Approval request: {approval_id}. No DMs, comments, posts, scraping, publishing, or scheduling performed."
                    ),
                }
            ]

        self.record_gpt_step(result, artifact_id, approval_id)
        return actions

    def safe_gpt_context(self, leads: list[dict]) -> dict:
        return {
            "module": self.module,
            "artist_module_docs": self.artist_module_docs_context(),
            "campaign_context": self.campaign_context(),
            "contacts": [self.compact_engagement_record(contact, "contact") for contact in self.contacts[:8]],
            "leads": [self.compact_engagement_record(lead, "lead") for lead in leads[:8]],
            "safety": {
                "send_dms": False,
                "post_comments": False,
                "publish_content": False,
                "scrape_platforms": False,
                "schedule_posts": False,
                "requires_human_review": True,
            },
        }

    def artist_module_docs_context(self) -> dict[str, str]:
        module_path = self.module_config.get("module_path")
        docs = {}
        if module_path and module_path.exists():
            for name in ("CLIENT_PROFILE.md", "AUDIENCE_PERSONAS.md", "CONTENT_STRATEGY.md", "CAMPAIGN_PLAN.md", "SIGNAL_SOURCES.md", "OPERATOR_WORKFLOW.md"):
                path = module_path / name
                if path.exists():
                    docs[name] = path.read_text(encoding="utf-8", errors="ignore")[:4000]
        return docs

    def campaign_context(self) -> dict[str, Any]:
        return {
            "module_label": self.module_config["label"],
            "module_context": self.module_context_summary(),
            "engagement_goal": "Generate music and entertainment fan engagement strategies and draft engagement ideas for human review.",
            "approval_required": True,
        }

    def compact_engagement_record(self, record: dict, record_type: str) -> dict:
        return {
            "id": self.record_id(record),
            "type": record_type,
            "name": record.get("name") or record.get("company") or record.get("company_name"),
            "status": record.get("review_status") or record.get("outreach_status") or record.get("contact_status"),
            "score": record.get("contact_score") or record.get("lead_score") or record.get("score"),
            "signal": record.get("signal") or record.get("priority_reason") or record.get("notes") or record.get("marketing_gap"),
            "source": record.get("source"),
        }

    def record_gpt_step(self, result: dict, artifact_id: str | None, approval_id: str | None) -> None:
        if self.db is None or not self.run_id:
            return
        self.record_step(
            self.db,
            self.run_id,
            60,
            GPT_STEP_NAME,
            {"module": self.module, "task": "generate_fan_engagement_plan"},
            "Use GPT only to create human-reviewed fan engagement ideas; never interact with platforms or schedule posts.",
            {
                "enabled": bool(result.get("enabled")),
                "used_gpt": bool(result.get("used_gpt")),
                "confidence": float(result.get("confidence") or 0.0),
                "reasoning_summary": result.get("reasoning_summary", ""),
                "output_length": len(result.get("output") or ""),
                "created_artifact_id": artifact_id,
                "created_approval_request_id": approval_id,
                "engagement_plan_created": bool(artifact_id),
                "sent_dms": False,
                "posted_comments": False,
                "published": False,
                "scraped_platforms": False,
                "scheduled": False,
                "error": result.get("error"),
            },
        )

    def write_gpt_engagement_note(self, result: dict, context: dict) -> str | None:
        if not self.run_id:
            return None
        notes_dir = self.vault_path / "content" / "agents"
        notes_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = notes_dir / f"artist_growth_gpt_fan_engagement_{timestamp}.md"
        content = f"""---
type: fan_engagement_plan
status: needs_review
source: gpt
module: {self.module}
generated_by_agent: {self.agent_name}
agent_run_id: {self.run_id}
agent_step_name: {GPT_STEP_NAME}
gpt_confidence: {float(result.get("confidence") or 0.0)}
created: {datetime.now(timezone.utc).isoformat()}
sent_dms: false
posted_comments: false
published: false
scraped_platforms: false
scheduled: false
---

# GPT Fan Engagement Plan: artist_growth

## Review Status

- Human review required: true
- DMs sent: false
- Comments posted: false
- Published: false
- Platforms scraped: false
- Scheduled: false
- Reasoning summary: {result.get("reasoning_summary") or "No reasoning summary recorded."}

## Draft Engagement Plan

{result.get("output") or ""}

## Source Context

- Contacts considered: {len(context.get("contacts") or [])}
- Leads considered: {len(context.get("leads") or [])}
"""
        path.write_text(content, encoding="utf-8")
        return str(path.relative_to(self.vault_path))

    def create_gpt_engagement_artifact(self, result: dict, context: dict, note_path: str | None) -> str | None:
        if self.db is None or not self.run_id:
            return None
        artifact = {
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "module": self.module,
            "artifact_type": "gpt_fan_engagement_plan",
            "label": "GPT fan engagement plan for artist_growth",
            "path": note_path,
            "content": {
                "engagement_plan": result.get("output") or "",
                "confidence": float(result.get("confidence") or 0.0),
                "reasoning_summary": result.get("reasoning_summary", ""),
                "generated_by_agent": self.agent_name,
                "agent_run_id": self.run_id,
                "agent_step_name": GPT_STEP_NAME,
                "source_context_counts": {
                    "contacts": len(context.get("contacts") or []),
                    "leads": len(context.get("leads") or []),
                },
                "sent_dms": False,
                "posted_comments": False,
                "published": False,
                "scraped_platforms": False,
                "scheduled": False,
            },
            "created_at": datetime.now(timezone.utc),
        }
        insert_result = self.db.agent_artifacts.insert_one(artifact)
        return str(insert_result.inserted_id)

    def create_gpt_approval_request(self, result: dict, confidence: float) -> str:
        if self.db is None or not self.run_id:
            return "not_recorded"
        reason = result.get("reasoning_summary") or result.get("error") or "GPT output was not confident enough to create a fan engagement plan."
        is_failure = bool(result.get("error")) or not str(result.get("output") or "").strip()
        request_doc = {
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "module": self.module,
            "request_type": "gpt_fan_engagement_plan_review",
            "status": "open",
            "title": "Review GPT fan engagement plan for artist_growth",
            "summary": "GPT could not produce a usable fan engagement plan." if is_failure else "GPT produced a low-confidence fan engagement plan for artist_growth.",
            "reason_for_review": reason,
            "request_origin": "system" if is_failure else "gpt",
            "is_test": False,
            "severity": "error" if is_failure else "needs_review",
            "user_facing_summary": "GPT failed before producing a usable fan engagement plan." if is_failure else "Review the low-confidence GPT fan engagement plan before using it.",
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
        }
        insert_result = self.db.approval_requests.insert_one(request_doc)
        return str(insert_result.inserted_id)
