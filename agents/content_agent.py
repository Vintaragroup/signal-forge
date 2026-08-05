from datetime import datetime, timezone
from typing import Any

from agents.base_agent import BaseAgent
from agents.gpt_client import generate_agent_response


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


GPT_CONFIDENCE_THRESHOLD = 0.6
GPT_STEP_NAME = "gpt_content_plan_generation"


class ContentAgent(BaseAgent):
    agent_name = "content"
    agent_role = "Prepare content and post ideas from module signals"

    def plan_actions(self, leads: list[dict]) -> list[dict[str, str]]:
        """Wrapper: runs core plan logic then emits workflow_assets for media_growth."""
        actions = self._plan_actions_core(leads)
        if self.module == "media_growth" and self.db is not None and self.run_id:
            self._emit_workflow_assets(actions)
        return actions

    def _plan_actions_core(self, leads: list[dict]) -> list[dict[str, str]]:
        gpt_actions = self.plan_gpt_actions(leads)
        if gpt_actions is not None:
            return gpt_actions

        if not leads:
            if self.contacts:
                return [
                    {
                        "title": f"Content idea from {contact.get('company') or contact.get('name')}",
                        "target": contact.get("company") or contact.get("name") or self.module,
                        "reason": contact.get("priority_reason") or contact.get("notes", "Imported contact context is available."),
                        "planned_action": f"Draft one educational post idea for human review. Segment: {contact.get('segment', 'unscored')}; score: {contact.get('contact_score', '-')}.",
                    }
                    for contact in self.contacts[:8]
                ]
            return [
                {
                    "title": "Create starter content themes",
                    "target": self.module,
                    "reason": "No module-specific Mongo records were found.",
                    "planned_action": "Use module strategy docs to draft three educational posts, one checklist, and one campaign explainer for human review.",
                }
            ]

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
        return actions

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
        self._gpt_result = result  # stored for _emit_workflow_assets
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

    # ------------------------------------------------------------------
    # Phase 5A — Structured workflow_assets (media_growth only, additive)
    # ------------------------------------------------------------------

    def _emit_workflow_assets(self, actions: list[dict[str, str]]) -> None:
        """Create workflow_asset records for media_growth content runs.

        Additive only — does not remove or replace approval_request creation.
        Synthetic demo assets are created when no GPT content is available so
        Step 4 always renders meaningful asset cards during Phase 5A validation.
        """
        if self.db is None or not self.run_id:
            return
        now = datetime.now(timezone.utc)
        run_short = self.run_id[:8]

        gpt_result = getattr(self, "_gpt_result", None)
        gpt_success = (
            gpt_result is not None
            and gpt_result.get("used_gpt")
            and float(gpt_result.get("confidence") or 0.0) >= GPT_CONFIDENCE_THRESHOLD
            and str(gpt_result.get("output") or "").strip()
        )

        asset_docs: list[dict] = []

        if gpt_success:
            asset_docs.append(self._gpt_to_workflow_asset(gpt_result, run_short, now, index=1))

        # Always append synthetic demo assets to ensure Step 4 renders cards
        # during Phase 5A validation. Clearly marked metadata.synthetic_demo = True.
        asset_docs.extend(self._synthetic_demo_assets(run_short, now, start_index=len(asset_docs) + 1))

        self.create_workflow_assets(self.db, self.run_id, asset_docs)

    def _gpt_to_workflow_asset(self, result: dict, run_short: str, now: Any, index: int) -> dict:
        return {
            "asset_id": f"{run_short}-content_idea-{index}",
            "run_id": self.run_id,
            "task_id": self.task_id or None,
            "module": self.module,
            "workspace_slug": self.workspace_slug or None,
            "profile_id": "executive_growth",
            "asset_type": "content_idea",
            "output_category": "content",
            "platform": None,
            "title": f"GPT Content Plan — {self.module.replace('_', ' ').title()}",
            "summary": result.get("reasoning_summary") or "GPT-generated content plan ready for operator review.",
            "body": result.get("output") or "",
            "sections": None,
            "metadata": {
                "hook_type": "gpt_generated",
                "synthetic_demo": False,
                "gpt_confidence": float(result.get("confidence") or 0.0),
                "source": "gpt_content_plan",
            },
            "approval_state": "needs_review",
            "source_agent": self.agent_name,
            "simulation_only": True,
            "is_test": False,
            "created_at": now,
            "updated_at": now,
        }

    def _synthetic_demo_assets(self, run_short: str, now: Any, start_index: int = 1) -> list[dict]:
        """Return 5 synthetic demo assets for media_growth Phase 5A validation.

        These are clearly marked metadata.synthetic_demo = True so operators
        understand they are placeholder content, not real GPT outputs.
        """
        templates = [
            {
                "asset_type": "content_idea",
                "title": "Why consistency beats motivation in content creation",
                "summary": "Most creators wait for inspiration. The ones who build audiences show up on a schedule. This post explores why systems outperform willpower for long-term content output.",
                "body": (
                    "Motivation is unreliable. It spikes after a conference, a good book, or a viral post — "
                    "then fades within 72 hours. Consistency, on the other hand, is a system.\n\n"
                    "The creators with the largest audiences aren't the most talented — they're the most reliable. "
                    "They post when they don't feel like it. They ship imperfect content. They trust the compound effect.\n\n"
                    "Hook idea: 'The most underrated skill in content isn't creativity — it's showing up.'\n\n"
                    "CTA: Ask followers how they stay consistent when motivation drops."
                ),
                "metadata": {"hook_type": "bold_statement", "platform": "LinkedIn", "estimated_length": "short", "synthetic_demo": True},
            },
            {
                "asset_type": "content_idea",
                "title": "The hidden leadership tax of unclear communication",
                "summary": "Vague direction from leadership costs teams hours of rework weekly. This post frames unclear communication as a measurable cost, not just a soft skill gap.",
                "body": (
                    "Every time a leader sends an unclear directive, someone on their team spends 30–90 minutes "
                    "figuring out what it actually means. Multiply that by 10 team members, 3× per week.\n\n"
                    "That's the leadership communication tax — invisible on the P&L, massive in lost output.\n\n"
                    "The fix isn't softer language. It's sharper structure: one decision, one owner, one deadline per message.\n\n"
                    "Hook idea: 'Your team isn't slow. Your communication is expensive.'\n\n"
                    "CTA: Share the most confusing message you ever received from a manager (anonymized)."
                ),
                "metadata": {"hook_type": "bold_statement", "platform": "LinkedIn", "estimated_length": "short", "synthetic_demo": True},
            },
            {
                "asset_type": "script_draft",
                "title": "60-second video script: The 5-minute rule for executive content",
                "summary": "A short-form script (60 seconds) for LinkedIn or YouTube Shorts on building a sustainable content habit with 5 minutes of intentional output daily.",
                "body": (
                    "[HOOK — 0:00–0:08]\n"
                    "You don't need an hour to build a content presence. You need 5 minutes and a decision.\n\n"
                    "[BODY — 0:08–0:45]\n"
                    "Here's the system: Every morning, write one sentence about something you noticed yesterday "
                    "that your audience would find useful. Don't edit. Don't overthink.\n\n"
                    "That sentence becomes your post. Sometimes it becomes a thread. Occasionally it becomes a talk.\n\n"
                    "I've watched executives add 40k followers in a year using nothing but that habit. "
                    "The secret isn't the content — it's the commitment to show up before you feel ready.\n\n"
                    "[CTA — 0:45–0:60]\n"
                    "What's one thing you noticed this week that your audience should know? "
                    "Drop it in the comments — I'll respond to every one."
                ),
                "metadata": {"platform": "LinkedIn / YouTube Shorts", "estimated_runtime": 60, "tone": "direct-authoritative", "synthetic_demo": True},
            },
            {
                "asset_type": "video_prompt",
                "title": "Faceless short-form prompt: Decision fatigue in modern leadership",
                "summary": "A visual direction brief for a faceless short-form video on how decision fatigue silently reduces executive output — suitable for B-roll + text overlay format.",
                "body": (
                    "VISUAL DIRECTION:\n"
                    "Open on a desk covered in sticky notes, open laptop tabs, a coffee going cold. "
                    "Time-lapse of a clock. No faces shown.\n\n"
                    "TEXT OVERLAY (timed to scroll):\n"
                    "Line 1: 'The average executive makes 35,000 decisions per day'\n"
                    "Line 2: 'By 3pm, most are running on cognitive fumes'\n"
                    "Line 3: 'Decision fatigue isn't weakness — it's physics'\n"
                    "Line 4: 'The fix: batch, delegate, and protect your first 90 minutes'\n\n"
                    "B-ROLL SUGGESTIONS:\n"
                    "- Calendar app being scrolled rapidly\n"
                    "- Empty inbox vs overflowing inbox contrast\n"
                    "- Person closing laptop and stepping away\n\n"
                    "MUSIC TONE: Low, ambient, slightly tense. Resolves to calm at end.\n\n"
                    "DURATION TARGET: 30–45 seconds."
                ),
                "metadata": {"platform": "Instagram Reels / TikTok / YouTube Shorts", "format": "faceless", "duration_target": 40, "synthetic_demo": True},
            },
            {
                "asset_type": "content_idea",
                "title": "The audience-first content mistake most executives make",
                "summary": "Most executives start content creation by talking about what they know. The audience-first approach flips this: start with what your audience fears, then teach backward from there.",
                "body": (
                    "The most common mistake in executive content: leading with expertise instead of empathy.\n\n"
                    "Expertise says: 'Here's what I know about supply chain optimization.'\n"
                    "Empathy says: 'Here's the supply chain decision that kept you up last night — and how to solve it.'\n\n"
                    "The second version gets 10× the engagement. Same knowledge. Different angle.\n\n"
                    "The framework: Before writing anything, ask 'What does my audience fear losing?' "
                    "Then write a post that addresses that fear and leads them toward a better outcome.\n\n"
                    "Hook idea: 'Your audience doesn't want your expertise. They want their problem solved.'\n\n"
                    "Format suggestion: 3-point framework post with a fear-based hook."
                ),
                "metadata": {"hook_type": "contrarian", "platform": "LinkedIn", "estimated_length": "medium", "synthetic_demo": True},
            },
        ]

        run_short_str = run_short
        assets = []
        for i, template in enumerate(templates, start=start_index):
            asset_type = template["asset_type"]
            assets.append({
                "asset_id": f"{run_short_str}-{asset_type}-{i}",
                "run_id": self.run_id,
                "task_id": self.task_id or None,
                "module": self.module,
                "workspace_slug": self.workspace_slug or None,
                "profile_id": "executive_growth",
                "asset_type": asset_type,
                "output_category": "content",
                "platform": template["metadata"].get("platform"),
                "title": template["title"],
                "summary": template["summary"],
                "body": template["body"],
                "sections": None,
                "metadata": template["metadata"],
                "approval_state": "needs_review",
                "source_agent": self.agent_name,
                "simulation_only": True,
                "is_test": False,
                "created_at": now,
                "updated_at": now,
            })
        return assets

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

    # ------------------------------------------------------------------
    # Creative Studio: process approved content briefs
    # ------------------------------------------------------------------

    def fetch_approved_briefs(self) -> list[dict]:
        """Return approved content briefs for the current module/workspace."""
        if self.db is None:
            return []
        query: dict[str, Any] = {"status": "approved"}
        if self.module:
            query["module"] = self.module
        if self.workspace_slug:
            query["workspace_slug"] = self.workspace_slug
        return list(self.db.content_briefs.find(query).sort([("created_at", -1)]).limit(self.limit))

    def generate_content_drafts(self) -> list[dict]:
        """For each approved brief, create a content_draft with needs_review status.

        Uses the model router:
        - planning step  → agent/review model (generate_agent_response)
        - writing step   → draft model (generate_draft_response)

        Returns list of created draft documents.
        """
        if self.db is None or not self.run_id:
            return []

        briefs = self.fetch_approved_briefs()
        if not briefs:
            return []

        from agents.gpt_client import generate_agent_response, generate_draft_response  # noqa: PLC0415

        created_drafts: list[dict] = []

        for brief in briefs:
            brief_id = str(brief.get("_id", ""))

            # --- Step A: plan (review/agent model) ---
            plan_context = {
                "module": self.module,
                "brief": {
                    "campaign_name": brief.get("campaign_name"),
                    "audience": brief.get("audience"),
                    "platform": brief.get("platform"),
                    "goal": brief.get("goal"),
                    "offer": brief.get("offer"),
                    "tone": brief.get("tone"),
                    "notes": brief.get("notes"),
                },
                "safety": {
                    "publish_posts": False,
                    "schedule_posts": False,
                    "requires_human_review": True,
                },
            }
            plan_result = generate_agent_response(
                agent_name="content_agent",
                module=self.module,
                task="plan_content_from_brief",
                context=plan_context,
            )
            plan_enabled = plan_result.get("enabled")
            plan_confidence = float(plan_result.get("confidence") or 0.0)

            # --- Step B: write (draft model) ---
            draft_result: dict[str, Any] = {"enabled": False}
            if plan_enabled and plan_confidence >= GPT_CONFIDENCE_THRESHOLD:
                draft_context = {**plan_context, "plan_output": plan_result.get("output") or ""}
                draft_result = generate_draft_response(
                    agent_name="content_agent",
                    module=self.module,
                    task="write_content_draft",
                    context=draft_context,
                )

            # --- Determine body and status ---
            use_draft = draft_result.get("enabled") and draft_result.get("used_gpt")
            body = (draft_result.get("output") or plan_result.get("output") or "").strip()
            selected_model = clean_text(draft_result.get("selected_model") or plan_result.get("selected_model"))
            routing_reason = clean_text(draft_result.get("routing_reason") or plan_result.get("routing_reason"))
            complexity = clean_text(draft_result.get("complexity") or plan_result.get("complexity"))

            draft_status: str
            approval_id: str | None = None
            if body and (plan_confidence >= GPT_CONFIDENCE_THRESHOLD or use_draft):
                draft_status = "needs_review"
            else:
                draft_status = "needs_review"
                approval_id = self._create_brief_approval_request(brief, plan_result, plan_confidence)

            now = datetime.now(timezone.utc)
            draft_doc: dict[str, Any] = {
                "workspace_slug": self.workspace_slug or brief.get("workspace_slug", ""),
                "module": self.module,
                "brief_id": brief_id,
                "platform": brief.get("platform", ""),
                "content_type": "post",
                "title": brief.get("campaign_name") or f"Draft for {self.module}",
                "body": body or "(No output generated — operator must write or revise.)",
                "hashtags": [],
                "call_to_action": brief.get("offer", ""),
                "status": draft_status,
                "generated_by_agent": self.agent_name,
                "agent_run_id": self.run_id,
                "selected_model": selected_model,
                "routing_reason": routing_reason,
                "complexity": complexity,
                "gpt_confidence": plan_confidence,
                "review_events": [],
                "outbound_actions_taken": 0,
                "simulation_only": True,
                "created_at": now,
                "updated_at": now,
            }
            insert_result = self.db.content_drafts.insert_one(draft_doc)
            draft_doc["_id"] = insert_result.inserted_id
            created_drafts.append(draft_doc)

            # Update brief so it isn't re-processed on the next run
            self.db.content_briefs.update_one(
                {"_id": brief["_id"]},
                {"$set": {"status": "needs_review", "last_draft_id": str(insert_result.inserted_id), "updated_at": now}},
            )

        return created_drafts

    def _create_brief_approval_request(self, brief: dict, result: dict, confidence: float) -> str:
        if self.db is None or not self.run_id:
            return "not_recorded"
        reason = result.get("reasoning_summary") or result.get("error") or "GPT did not produce confident output for this brief."
        request_doc: dict[str, Any] = {
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "module": self.module,
            "request_type": "gpt_content_draft_review",
            "status": "open",
            "title": f"Review content draft for brief: {brief.get('campaign_name') or brief.get('_id')}",
            "summary": f"GPT draft for brief '{brief.get('campaign_name')}' needs human review.",
            "reason_for_review": reason,
            "request_origin": "gpt",
            "is_test": False,
            "severity": "needs_review",
            "user_facing_summary": f"Review the AI-generated draft for brief '{brief.get('campaign_name')}' before using it anywhere.",
            "technical_reason": reason,
            "target": str(brief.get("_id", "")),
            "target_type": "content_brief",
            "gpt_confidence": confidence,
            "generated_by_agent": self.agent_name,
            "agent_run_id": self.run_id,
            "created_at": datetime.now(timezone.utc),
            "resolved_at": None,
            "simulation_only": True,
            **({"workspace_slug": self.workspace_slug} if self.workspace_slug else {}),
        }
        insert_result = self.db.approval_requests.insert_one(request_doc)
        return str(insert_result.inserted_id)

