from scripts.generate_revenue_report import count_response_events, module_for_lead


def test_count_response_events_prefers_event_history():
    messages = [
        {"response_status": "call_booked", "response_events": [{"outcome": "call_booked"}, {"outcome": "call_booked"}]},
        {"response_status": "call_booked"},
        {"response_status": "interested", "response_events": [{"outcome": "interested"}]},
    ]

    assert count_response_events(messages, "call_booked") == 3
    assert count_response_events(messages, "interested") == 1


def test_module_for_lead_infers_contractor_growth():
    assert module_for_lead({"engine": "contractor_lead_engine_v3"}) == "contractor_growth"
    assert module_for_lead({"business_type": "roofing contractor"}) == "contractor_growth"
    assert module_for_lead({"module": "insurance_growth", "business_type": "roofing contractor"}) == "insurance_growth"