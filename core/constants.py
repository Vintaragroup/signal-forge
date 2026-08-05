"""Shared lifecycle and module constants for SignalForge v1.

These values are intentionally small and explicit. They are the contract shared
by CLI scripts, reports, the local API, and dashboard filters.
"""

VALID_MODULES = (
    "contractor_growth",
    "insurance_growth",
    "artist_growth",
    "media_growth",
)

LEAD_REVIEW_DECISIONS = ("pursue", "skip", "research_more")
LEAD_REVIEW_STATUSES = ("needs_review", *LEAD_REVIEW_DECISIONS)

MESSAGE_REVIEW_DECISIONS = ("approve", "reject", "revise")
MESSAGE_REVIEW_STATUSES = ("needs_review", "approved", "needs_revision", "rejected")

SEND_STATUSES = ("not_sent", "sent")
MANUAL_SEND_CHANNELS = ("email", "phone", "sms", "dm", "social_comment", "other")

RESPONSE_OUTCOMES = (
    "no_response",
    "interested",
    "not_interested",
    "call_booked",
    "requested_info",
    "wrong_contact",
    "bounced",
    "do_not_contact",
)

# Shared between scripts/log_response.py and the API's /messages/{id}/response
# endpoint so a response outcome maps to the same contact/lead status
# regardless of which one logged it.
CONTACT_STATUS_BY_OUTCOME = {
    "interested": "interested",
    "not_interested": "not_interested",
    "call_booked": "call_booked",
    "do_not_contact": "do_not_contact",
    "bounced": "invalid",
}

LEAD_STATUS_BY_OUTCOME = {
    "interested": "replied",
    "call_booked": "booked_call",
    "not_interested": "closed_lost",
}

# Shared between scripts/log_deal_outcome.py and the API's /deals/log-outcome
# endpoint so a deal outcome maps to the same lead outreach_status regardless
# of which one logged it.
LEAD_OUTREACH_STATUS = {
    "proposal_sent": "replied",
    "negotiation": "replied",
    "closed_won": "closed_won",
    "closed_lost": "closed_lost",
    "nurture": "follow_up_needed",
    "no_show": "follow_up_needed",
    "not_fit": "closed_lost",
}

DEAL_OUTCOMES = (
    "proposal_sent",
    "negotiation",
    "closed_won",
    "closed_lost",
    "nurture",
    "no_show",
    "not_fit",
)

CONTACT_STATUSES = (
    "imported",
    "contacted",
    "interested",
    "not_interested",
    "call_booked",
    "do_not_contact",
    "invalid",
    "proposal_sent",
    "negotiation",
    "closed_won",
    "closed_lost",
    "nurture",
    "no_show",
    "not_fit",
)

CONTACT_SEGMENTS = ("high_priority", "nurture", "research_more", "low_priority")

OUTREACH_STATUSES = (
    "drafted",
    "sent",
    "replied",
    "follow_up_needed",
    "booked_call",
    "closed_won",
    "closed_lost",
)

AGENT_RUN_STATUSES = ("running", "completed", "waiting_for_approval", "failed")
APPROVAL_REQUEST_STATUSES = ("open", "closed")

OPEN_DEAL_OUTCOMES = ("proposal_sent", "negotiation")
NURTURE_STATUSES = ("nurture", "not_interested", "no_response")
