from bson import ObjectId

from agents.fan_engagement_agent import FanEngagementAgent


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


def test_fan_engagement_gpt_disabled_keeps_deterministic_fallback(monkeypatch):
    monkeypatch.setenv("GPT_AGENT_ENABLED", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    agent = FanEngagementAgent(module="artist_growth")
    agent.contacts = [
        {
            "name": "Maya Lee",
            "company": "Indie Venue Collective",
            "contact_score": 91,
            "segment": "high_priority",
            "priority_reason": "Venue and audience crossover opportunity.",
        }
    ]

    actions = agent.plan_actions([])

    assert len(actions) == 1
    assert actions[0]["title"] == "Fan engagement idea from Maya Lee"
    assert "Prepare a human-reviewed engagement prompt" in actions[0]["planned_action"]


def test_fan_engagement_high_confidence_creates_artifact_and_note(monkeypatch, tmp_path):
    def fake_generate_agent_response(**kwargs):
        assert kwargs["agent_name"] == "fan_engagement_agent"
        assert kwargs["module"] == "artist_growth"
        assert kwargs["task"] == "generate_fan_engagement_plan"
        assert "artist_module_docs" in kwargs["context"]
        assert kwargs["context"]["safety"]["send_dms"] is False
        assert kwargs["context"]["safety"]["post_comments"] is False
        assert kwargs["context"]["safety"]["scrape_platforms"] is False
        return {
            "enabled": True,
            "used_gpt": True,
            "output": "Invite fans to share the lyric that matches their week, then review replies manually.",
            "confidence": 0.84,
            "reasoning_summary": "Artist personas and release-story strategy support a low-friction engagement prompt.",
            "error": None,
        }

    monkeypatch.setattr("agents.fan_engagement_agent.generate_agent_response", fake_generate_agent_response)

    db = FakeDatabase()
    agent = FanEngagementAgent(module="artist_growth", vault_path=tmp_path)
    agent.db = db
    agent.run_id = "run-artist-1"
    agent.contacts = [{"name": "Maya Lee", "segment": "high_priority", "contact_score": 91}]

    actions = agent.plan_actions([])

    assert len(db.agent_artifacts.documents) == 1
    artifact = db.agent_artifacts.documents[0]
    assert artifact["artifact_type"] == "gpt_fan_engagement_plan"
    assert artifact["path"].startswith("content/agents/")
    assert artifact["content"]["confidence"] == 0.84
    assert artifact["content"]["reasoning_summary"] == "Artist personas and release-story strategy support a low-friction engagement prompt."
    assert artifact["content"]["generated_by_agent"] == "fan_engagement"
    assert artifact["content"]["agent_run_id"] == "run-artist-1"
    assert artifact["content"]["agent_step_name"] == "gpt_fan_engagement_plan_generation"
    assert artifact["content"]["sent_dms"] is False
    assert artifact["content"]["posted_comments"] is False
    assert artifact["content"]["published"] is False
    assert artifact["content"]["scraped_platforms"] is False
    assert artifact["content"]["scheduled"] is False
    assert (tmp_path / artifact["path"]).exists()
    note = (tmp_path / artifact["path"]).read_text(encoding="utf-8")
    assert "status: needs_review" in note
    assert "sent_dms: false" in note
    assert "posted_comments: false" in note
    assert "scraped_platforms: false" in note
    assert "scheduled: false" in note
    assert len(db.approval_requests.documents) == 0
    assert actions[0]["title"] == "GPT fan engagement plan for artist_growth"
    assert "No DMs, comments, posts, scraping, publishing, or scheduling performed" in actions[0]["planned_action"]


def test_fan_engagement_low_confidence_creates_approval_request(monkeypatch, tmp_path):
    def fake_generate_agent_response(**kwargs):
        return {
            "enabled": True,
            "used_gpt": True,
            "output": "Post more often.",
            "confidence": 0.37,
            "reasoning_summary": "Recommendation is too generic for the artist persona context.",
            "error": None,
        }

    monkeypatch.setattr("agents.fan_engagement_agent.generate_agent_response", fake_generate_agent_response)

    db = FakeDatabase()
    agent = FanEngagementAgent(module="artist_growth", vault_path=tmp_path)
    agent.db = db
    agent.run_id = "run-artist-1"

    actions = agent.plan_actions([])

    assert len(db.agent_artifacts.documents) == 0
    assert len(db.approval_requests.documents) == 1
    approval = db.approval_requests.documents[0]
    assert approval["request_type"] == "gpt_fan_engagement_plan_review"
    assert approval["status"] == "open"
    assert approval["gpt_confidence"] == 0.37
    assert approval["generated_by_agent"] == "fan_engagement"
    assert approval["agent_run_id"] == "run-artist-1"
    assert approval["agent_step_name"] == "gpt_fan_engagement_plan_generation"
    assert approval["reason_for_review"] == "Recommendation is too generic for the artist persona context."
    assert len(db.agent_steps.documents) == 1
    assert db.agent_steps.documents[0]["output"]["engagement_plan_created"] is False
    assert db.agent_steps.documents[0]["output"]["sent_dms"] is False
    assert db.agent_steps.documents[0]["output"]["posted_comments"] is False
    assert db.agent_steps.documents[0]["output"]["scraped_platforms"] is False
    assert actions[0]["title"] == "GPT fan engagement plan needs human review for artist_growth"
