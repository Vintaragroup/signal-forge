from agents.base_agent import BaseAgent


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
