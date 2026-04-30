from agents.base_agent import BaseAgent


class OutreachAgent(BaseAgent):
    agent_name = "outreach"
    agent_role = "Prepare B2B outreach actions for human review"

    def plan_actions(self, leads: list[dict]) -> list[dict[str, str]]:
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
