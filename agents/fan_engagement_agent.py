from agents.base_agent import BaseAgent


class FanEngagementAgent(BaseAgent):
    agent_name = "fan_engagement"
    agent_role = "Prepare music and entertainment engagement ideas"

    def plan_actions(self, leads: list[dict]) -> list[dict[str, str]]:
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
