from core.constants import (
    AGENT_RUN_STATUSES,
    CONTACT_STATUSES,
    DEAL_OUTCOMES,
    LEAD_REVIEW_STATUSES,
    MESSAGE_REVIEW_DECISIONS,
    MESSAGE_REVIEW_STATUSES,
    RESPONSE_OUTCOMES,
    SEND_STATUSES,
    VALID_MODULES,
)


def test_core_lifecycle_contracts_include_current_v1_values():
    assert VALID_MODULES == ("contractor_growth", "insurance_growth", "artist_growth", "media_growth")
    assert "needs_review" in LEAD_REVIEW_STATUSES
    assert {"approve", "reject", "revise"}.issubset(MESSAGE_REVIEW_DECISIONS)
    assert {"needs_review", "approved", "needs_revision", "rejected"}.issubset(MESSAGE_REVIEW_STATUSES)
    assert SEND_STATUSES == ("not_sent", "sent")
    assert {"call_booked", "do_not_contact", "bounced"}.issubset(RESPONSE_OUTCOMES)
    assert {"proposal_sent", "closed_won", "closed_lost"}.issubset(DEAL_OUTCOMES)
    assert {"imported", "contacted", "call_booked"}.issubset(CONTACT_STATUSES)
    assert {"running", "completed", "waiting_for_approval", "failed"}.issubset(AGENT_RUN_STATUSES)
