from bson import ObjectId

from agents.content_agent import ContentAgent


class InsertResult:
    def __init__(self):
        self.inserted_id = ObjectId()


class FakeCursor:
    def __init__(self, documents=None):
        self.documents = documents or []

    def sort(self, *args, **kwargs):
        return self

    def limit(self, limit):
        return self.documents[:limit]


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = documents or []

    def find(self, query=None):
        return FakeCursor(self.documents)

    def insert_one(self, document):
        self.documents.append(document)
        return InsertResult()


class FakeDatabase:
    def __init__(self):
        self.agent_artifacts = FakeCollection()
        self.agent_steps = FakeCollection()
        self.approval_requests = FakeCollection()
        self.deals = FakeCollection([
            {
                "_id": ObjectId(),
                "module": "insurance_growth",
                "outcome": "proposal_sent",
                "note": "Prospect asked about renewal readiness.",
            }
        ])


def test_content_agent_gpt_disabled_keeps_deterministic_fallback(monkeypatch):
    monkeypatch.setenv("GPT_AGENT_ENABLED", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    agent = ContentAgent(module="insurance_growth")
    agent.contacts = [
        {
            "name": "Andre Brooks",
            "company": "Brooks Benefits Group",
            "contact_score": 94,
            "segment": "high_priority",
            "priority_reason": "Commercial-lines agency with renewal education opportunity.",
        }
    ]

    actions = agent.plan_actions([])

    assert len(actions) == 1
    assert actions[0]["title"] == "Content idea from Brooks Benefits Group"
    assert "Draft one educational post idea for human review" in actions[0]["planned_action"]


def test_content_agent_high_confidence_creates_artifact_and_note(monkeypatch, tmp_path):
    def fake_generate_agent_response(**kwargs):
        assert kwargs["agent_name"] == "content_agent"
        assert kwargs["module"] == "insurance_growth"
        assert kwargs["task"] == "generate_content_plan"
        assert "module_docs" in kwargs["context"]
        assert kwargs["context"]["safety"]["publish_posts"] is False
        return {
            "enabled": True,
            "used_gpt": True,
            "output": "## Draft\nRenewal readiness starts before the renewal notice arrives.",
            "confidence": 0.88,
            "reasoning_summary": "Module strategy and recent deal context support renewal-readiness content.",
            "error": None,
        }

    monkeypatch.setattr("agents.content_agent.generate_agent_response", fake_generate_agent_response)

    db = FakeDatabase()
    agent = ContentAgent(module="insurance_growth", vault_path=tmp_path)
    agent.db = db
    agent.run_id = "run-789"
    agent.contacts = [{"company": "Brooks Benefits Group", "segment": "high_priority", "contact_score": 94}]

    actions = agent.plan_actions([])

    assert len(db.agent_artifacts.documents) == 1
    artifact = db.agent_artifacts.documents[0]
    assert artifact["artifact_type"] == "gpt_content_plan"
    assert artifact["path"].startswith("content/agents/")
    assert artifact["content"]["confidence"] == 0.88
    assert artifact["content"]["reasoning_summary"] == "Module strategy and recent deal context support renewal-readiness content."
    assert artifact["content"]["generated_by_agent"] == "content"
    assert artifact["content"]["agent_run_id"] == "run-789"
    assert artifact["content"]["agent_step_name"] == "gpt_content_plan_generation"
    assert artifact["content"]["published"] is False
    assert artifact["content"]["scheduled"] is False
    assert (tmp_path / artifact["path"]).exists()
    note = (tmp_path / artifact["path"]).read_text(encoding="utf-8")
    assert "status: needs_review" in note
    assert "published: false" in note
    assert "scheduled: false" in note
    assert len(db.approval_requests.documents) == 0
    assert actions[0]["title"] == "GPT content plan for insurance_growth"
    assert "No post published or scheduled" in actions[0]["planned_action"]


def test_content_agent_low_confidence_creates_approval_request(monkeypatch, tmp_path):
    def fake_generate_agent_response(**kwargs):
        return {
            "enabled": True,
            "used_gpt": True,
            "output": "Generic draft idea.",
            "confidence": 0.42,
            "reasoning_summary": "Content idea is too generic for the module context.",
            "error": None,
        }

    monkeypatch.setattr("agents.content_agent.generate_agent_response", fake_generate_agent_response)

    db = FakeDatabase()
    agent = ContentAgent(module="insurance_growth", vault_path=tmp_path)
    agent.db = db
    agent.run_id = "run-789"

    actions = agent.plan_actions([])

    assert len(db.agent_artifacts.documents) == 0
    assert len(db.approval_requests.documents) == 1
    approval = db.approval_requests.documents[0]
    assert approval["request_type"] == "gpt_content_plan_review"
    assert approval["status"] == "open"
    assert approval["gpt_confidence"] == 0.42
    assert approval["generated_by_agent"] == "content"
    assert approval["agent_run_id"] == "run-789"
    assert approval["agent_step_name"] == "gpt_content_plan_generation"
    assert approval["reason_for_review"] == "Content idea is too generic for the module context."
    assert len(db.agent_steps.documents) == 1
    assert db.agent_steps.documents[0]["output"]["content_draft_created"] is False
    assert actions[0]["title"] == "GPT content plan needs human review for insurance_growth"
