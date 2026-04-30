from agents.base_agent import BaseAgent


class ContentAgent(BaseAgent):
    agent_name = "content"
    agent_role = "Prepare content and post ideas from module signals"

    def plan_actions(self, leads: list[dict]) -> list[dict[str, str]]:
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
