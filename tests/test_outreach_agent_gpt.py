from bson import ObjectId

from agents.outreach_agent import OutreachAgent


class InsertResult:
    def __init__(self):
        self.inserted_id = ObjectId()


class FakeCollection:
    def __init__(self):
        self.documents = []

    def find_one(self, query):
        for document in self.documents:
            if all(document.get(key) == value for key, value in query.items()):
                return document
        return None

    def insert_one(self, document):
        self.documents.append(document)
        return InsertResult()


class FakeDatabase:
    def __init__(self):
        self.message_drafts = FakeCollection()
        self.approval_requests = FakeCollection()
        self.agent_steps = FakeCollection()


def test_outreach_agent_gpt_disabled_keeps_contact_fallback(monkeypatch):
    monkeypatch.setenv("GPT_AGENT_ENABLED", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    agent = OutreachAgent(module="insurance_growth")
    agent.contacts = [
        {
            "name": "Andre Brooks",
            "company": "Brooks Benefits Group",
            "role": "Commercial Lines Producer",
            "contact_score": 94,
            "segment": "high_priority",
        }
    ]

    actions = agent.plan_actions([])

    assert len(actions) == 1
    assert actions[0]["title"] == "Review imported contact for Brooks Benefits Group"
    assert actions[0]["target"] == "Brooks Benefits Group"
    assert "Do not send anything automatically" in actions[0]["planned_action"]


def test_outreach_agent_gpt_enabled_creates_message_draft(monkeypatch):
    def fake_generate_agent_response(**kwargs):
        assert kwargs["agent_name"] == "outreach_agent"
        assert kwargs["module"] == "insurance_growth"
        assert kwargs["task"] == "generate_outreach_message"
        assert kwargs["context"]["target_type"] == "contact"
        return {
            "enabled": True,
            "used_gpt": True,
            "output": "Hi Andre, noticed your agency focuses on commercial lines...",
            "confidence": 0.82,
            "reasoning_summary": "Strong contact fit.",
            "error": None,
        }

    monkeypatch.setattr("agents.outreach_agent.generate_agent_response", fake_generate_agent_response)

    db = FakeDatabase()
    agent = OutreachAgent(module="insurance_growth")
    agent.db = db
    agent.run_id = "run-123"
    agent.contacts = [
        {
            "_id": ObjectId(),
            "contact_key": "andre-brooks",
            "name": "Andre Brooks",
            "company": "Brooks Benefits Group",
            "role": "Commercial Lines Producer",
            "contact_score": 94,
            "segment": "high_priority",
            "priority_reason": "High-fit insurance contact.",
            "recommended_action": "Draft commercial-lines outreach.",
        }
    ]

    actions = agent.plan_actions([])

    assert len(db.message_drafts.documents) == 1
    draft = db.message_drafts.documents[0]
    assert draft["review_status"] == "needs_review"
    assert draft["send_status"] == "not_sent"
    assert draft["source"] == "gpt"
    assert draft["generated_by_agent"] == "outreach"
    assert draft["agent_run_id"] == "run-123"
    assert draft["agent_step_name"] == "gpt_message_generation"
    assert draft["message_body"].startswith("Hi Andre")
    assert draft in agent.message_drafts
    assert len(db.approval_requests.documents) == 0
    assert actions[0]["title"] == "GPT draft ready for Andre Brooks"


def test_outreach_agent_low_confidence_creates_approval_request(monkeypatch):
    def fake_generate_agent_response(**kwargs):
        return {
            "enabled": True,
            "used_gpt": True,
            "output": "Draft may be off-target.",
            "confidence": 0.41,
            "reasoning_summary": "Insufficient context for confident outreach.",
            "error": None,
        }

    monkeypatch.setattr("agents.outreach_agent.generate_agent_response", fake_generate_agent_response)

    db = FakeDatabase()
    agent = OutreachAgent(module="insurance_growth")
    agent.db = db
    agent.run_id = "run-123"
    agent.contacts = [
        {
            "contact_key": "andre-brooks",
            "name": "Andre Brooks",
            "company": "Brooks Benefits Group",
            "contact_score": 94,
            "segment": "high_priority",
        }
    ]

    actions = agent.plan_actions([])

    assert len(db.message_drafts.documents) == 0
    assert len(db.approval_requests.documents) == 1
    approval = db.approval_requests.documents[0]
    assert approval["request_type"] == "gpt_message_generation_review"
    assert approval["status"] == "open"
    assert approval["simulation_only"] is True
    assert approval["request_origin"] == "gpt"
    assert approval["is_test"] is False
    assert approval["severity"] == "needs_review"
    assert approval["user_facing_summary"] == "Review the low-confidence GPT outreach result for Andre Brooks before deciding whether to convert it into a draft."
    assert approval["technical_reason"] == "Insufficient context for confident outreach."
    assert approval["gpt_confidence"] == 0.41
    assert approval["reason_for_review"] == "Insufficient context for confident outreach."
    assert approval["linked_target_id"] == "andre-brooks"
    assert actions[0]["title"] == "GPT draft needs human review for Andre Brooks"