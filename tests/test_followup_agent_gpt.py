from bson import ObjectId

from agents.followup_agent import FollowupAgent


class InsertResult:
    def __init__(self):
        self.inserted_id = ObjectId()


class FakeCollection:
    def __init__(self):
        self.documents = []

    def insert_one(self, document):
        self.documents.append(document)
        return InsertResult()


class FakeDatabase:
    def __init__(self):
        self.agent_artifacts = FakeCollection()
        self.agent_steps = FakeCollection()
        self.approval_requests = FakeCollection()


def sent_message():
    return {
        "_id": ObjectId(),
        "draft_key": "brooks-followup",
        "module": "insurance_growth",
        "recipient_name": "Andre Brooks",
        "company": "Brooks Benefits Group",
        "subject_line": "Checking in",
        "review_status": "approved",
        "send_status": "sent",
        "response_status": "interested",
        "response_events": [
            {
                "outcome": "interested",
                "note": "Asked for more detail about commercial-lines workflows.",
                "responded_at": "2026-04-29T12:00:00+00:00",
            }
        ],
    }


def test_followup_agent_gpt_disabled_keeps_deterministic_fallback(monkeypatch):
    monkeypatch.setenv("GPT_AGENT_ENABLED", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    agent = FollowupAgent(module="insurance_growth")
    leads = [
        {
            "company_name": "Brooks Benefits Group",
            "review_status": "pursue",
            "outreach_status": "sent",
        }
    ]

    actions = agent.plan_actions(leads)

    assert len(actions) == 1
    assert actions[0]["title"] == "Follow-up review for Brooks Benefits Group"
    assert "decide if follow_up_needed should be logged" in actions[0]["planned_action"]


def test_followup_agent_high_confidence_creates_recommendation_artifact(monkeypatch):
    def fake_generate_agent_response(**kwargs):
        assert kwargs["agent_name"] == "followup_agent"
        assert kwargs["module"] == "insurance_growth"
        assert kwargs["task"] == "recommend_followup_action"
        assert kwargs["context"]["target_type"] == "message"
        assert kwargs["context"]["send_status"] == "sent"
        return {
            "enabled": True,
            "used_gpt": True,
            "output": "Recommend a short manual follow-up with the requested workflow details.",
            "confidence": 0.86,
            "reasoning_summary": "Recent interested response with a clear information request.",
            "error": None,
        }

    monkeypatch.setattr("agents.followup_agent.generate_agent_response", fake_generate_agent_response)

    db = FakeDatabase()
    message = sent_message()
    agent = FollowupAgent(module="insurance_growth")
    agent.db = db
    agent.run_id = "run-456"
    agent.message_drafts = [message]

    actions = agent.plan_actions([])

    assert len(db.agent_artifacts.documents) == 1
    artifact = db.agent_artifacts.documents[0]
    assert artifact["artifact_type"] == "gpt_followup_recommendation"
    assert artifact["content"]["confidence"] == 0.86
    assert artifact["content"]["reasoning_summary"] == "Recent interested response with a clear information request."
    assert artifact["content"]["generated_by_agent"] == "followup"
    assert artifact["content"]["agent_run_id"] == "run-456"
    assert artifact["content"]["agent_step_name"] == "gpt_followup_recommendation"
    assert artifact["content"]["send_status_changed"] is False
    assert len(db.approval_requests.documents) == 0
    assert actions[0]["title"] == "GPT follow-up recommendation for Andre Brooks"
    assert "No message sent" in actions[0]["planned_action"]


def test_followup_agent_low_confidence_creates_approval_request(monkeypatch):
    def fake_generate_agent_response(**kwargs):
        return {
            "enabled": True,
            "used_gpt": True,
            "output": "Maybe follow up.",
            "confidence": 0.39,
            "reasoning_summary": "Response history is too thin to recommend a specific next action.",
            "error": None,
        }

    monkeypatch.setattr("agents.followup_agent.generate_agent_response", fake_generate_agent_response)

    db = FakeDatabase()
    agent = FollowupAgent(module="insurance_growth")
    agent.db = db
    agent.run_id = "run-456"
    agent.message_drafts = [sent_message()]

    actions = agent.plan_actions([])

    assert len(db.agent_artifacts.documents) == 0
    assert len(db.approval_requests.documents) == 1
    approval = db.approval_requests.documents[0]
    assert approval["request_type"] == "gpt_followup_recommendation_review"
    assert approval["status"] == "open"
    assert approval["gpt_confidence"] == 0.39
    assert approval["generated_by_agent"] == "followup"
    assert approval["agent_run_id"] == "run-456"
    assert approval["agent_step_name"] == "gpt_followup_recommendation"
    assert approval["reason_for_review"] == "Response history is too thin to recommend a specific next action."
    assert len(db.agent_steps.documents) == 1
    assert db.agent_steps.documents[0]["output"]["recommendation_created"] is False
    assert actions[0]["title"] == "GPT follow-up needs human review for Andre Brooks"
