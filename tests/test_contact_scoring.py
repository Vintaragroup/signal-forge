from datetime import datetime, timezone

from scripts.score_contacts import score_contact


def test_high_information_contact_scores_high_priority():
    contact = {
        "name": "Andre Brooks",
        "email": "andre@example.com",
        "phone": "555-0100",
        "company": "Brooks Benefits Group",
        "role": "Commercial Lines Producer",
        "notes": "Insurance agency focused on commercial lines and risk reviews.",
        "source": "client_provided_list",
    }

    scoring = score_contact(contact, "insurance_growth", datetime.now(timezone.utc))

    assert scoring["contact_score"] == 100
    assert scoring["segment"] == "high_priority"
    assert "has email" in scoring["priority_reason"]
    assert "module keywords matched" in scoring["priority_reason"]


def test_sparse_contact_stays_research_more_or_lower():
    contact = {
        "name": "Unknown Contact",
        "email": "",
        "phone": "",
        "company": "",
        "role": "",
        "notes": "",
        "source": "cold_import",
    }

    scoring = score_contact(contact, "media_growth", datetime.now(timezone.utc))

    assert scoring["contact_score"] < 55
    assert scoring["segment"] in {"research_more", "low_priority"}
