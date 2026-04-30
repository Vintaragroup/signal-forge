from scripts.review_message import review_status_for


def test_message_review_decisions_map_to_stored_statuses():
    assert review_status_for("approve") == "approved"
    assert review_status_for("reject") == "rejected"
    assert review_status_for("revise") == "needs_revision"
