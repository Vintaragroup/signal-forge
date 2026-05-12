"""
Phase 6D — Backend tests for discovery_engine module and new endpoints.
"""
from datetime import datetime, timezone

from bson import ObjectId
from fastapi.testclient import TestClient

import main
from main import app
import discovery_engine as engine

# ── Shared fakes ──────────────────────────────────────────────────────────────


class InsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, _spec):
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(self.documents)


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = list(documents or [])

    def find(self, query=None):
        query = query or {}
        return FakeCursor([doc for doc in self.documents if self._matches(doc, query)])

    def find_one(self, query):
        docs = list(self.find(query))
        return docs[0] if docs else None

    def insert_one(self, document):
        if "_id" not in document:
            document["_id"] = ObjectId()
        self.documents.append(document)
        return InsertResult(document["_id"])

    def update_one(self, query, update, upsert=False):
        doc = self.find_one(query)
        if not doc:
            return None
        for key, value in (update.get("$set") or {}).items():
            doc[key] = value
        if "$addToSet" in update:
            for key, value in update["$addToSet"].items():
                if isinstance(value, dict) and "$each" in value:
                    existing = doc.get(key, [])
                    for item in value["$each"]:
                        if item not in existing:
                            existing.append(item)
                    doc[key] = existing
        return None

    def _matches(self, document, query):
        for key, value in query.items():
            if key == "$or":
                if not any(self._matches(document, cond) for cond in value):
                    return False
                continue
            if document.get(key) != value:
                return False
        return True


class FakeDatabase:
    def __init__(self, seed_assets=None):
        self.discovery_insights = FakeCollection([])
        self.workflow_assets = FakeCollection(seed_assets or [])
        self.agent_tasks = FakeCollection([])
        self.agent_runs = FakeCollection([])


class FakeClient:
    def __init__(self, db: FakeDatabase):
        self._db = db

    def close(self):
        pass


# ── Discovery engine unit tests ───────────────────────────────────────────────


def _make_db():
    return FakeDatabase()


def test_get_mock_social_trends_media_growth():
    trends = engine.get_mock_social_trends("media_growth")
    assert isinstance(trends, list)
    assert len(trends) > 0
    for t in trends:
        assert "keyword" in t
        assert "platforms" in t
        assert "title" in t


def test_get_mock_social_trends_artist_growth():
    trends = engine.get_mock_social_trends("artist_growth")
    assert isinstance(trends, list)
    assert len(trends) > 0


def test_get_mock_social_trends_contractor_growth():
    trends = engine.get_mock_social_trends("contractor_growth")
    assert isinstance(trends, list)
    assert len(trends) > 0


def test_get_mock_social_trends_unknown_module():
    # Unknown module falls back to _default (non-empty)
    trends = engine.get_mock_social_trends("unknown_xyz_module")
    assert isinstance(trends, list)
    assert len(trends) > 0


def test_score_opportunity_bounds():
    for module in ("media_growth", "artist_growth", "contractor_growth"):
        for trend in engine.get_mock_social_trends(module):
            score = engine.score_opportunity(trend, [], set())
            assert 0.0 <= score <= 1.0, f"score {score} out of bounds for {trend['id']}"


def test_score_opportunity_high_with_prior_match():
    trend = engine.get_mock_social_trends("media_growth")[0]
    keyword = trend["keyword"]
    approved = [{"title": f"Test asset with {keyword}", "summary": "Prior content", "approval_state": "approved"}]
    base_score = engine.score_opportunity(trend, [], set())
    boosted_score = engine.score_opportunity(trend, approved, set())
    assert boosted_score >= base_score


def test_score_opportunity_low_no_signals():
    minimal_trend = {
        "id": "test_minimal",
        "keyword": "xyzabc",
        "title": "Minimal trend",
        "platforms": ["LinkedIn"],
        "asset_types": ["linkedin_post"],
        "base_score": 0.3,
    }
    score = engine.score_opportunity(minimal_trend, [], set())
    assert score == 0.3


def test_score_opportunity_multi_platform_bonus():
    trend_2p = {"id": "t1", "keyword": "kw", "title": "T", "platforms": ["A", "B"], "base_score": 0.7}
    trend_3p = {"id": "t2", "keyword": "kw", "title": "T", "platforms": ["A", "B", "C"], "base_score": 0.7}
    score_2 = engine.score_opportunity(trend_2p, [], set())
    score_3 = engine.score_opportunity(trend_3p, [], set())
    assert score_3 > score_2


def test_build_recommendation_structure():
    trend = engine.get_mock_social_trends("media_growth")[0]
    rec = engine.build_recommendation(trend, "media_growth")
    assert "recommended_asset_types" in rec
    assert "recommended_platforms" in rec
    assert "recommended_next_stage" in rec
    assert "rationale" in rec
    assert isinstance(rec["recommended_asset_types"], list)
    assert isinstance(rec["recommended_platforms"], list)


def test_build_evidence_structure():
    trend = engine.get_mock_social_trends("media_growth")[0]
    evidence = engine.build_evidence(trend)
    assert isinstance(evidence, list)
    assert len(evidence) >= 1
    for ev in evidence:
        assert "signal_type" in ev
        assert "keyword" in ev


def test_derive_quality_tags_high_confidence():
    trend = {"id": "t", "keyword": "kw", "title": "T", "platforms": ["A", "B"], "base_score": 0.9}
    tags = engine.derive_quality_tags(trend, 0.9, [], set())
    assert "High Confidence" in tags


def test_derive_quality_tags_multi_platform():
    trend = {"id": "t", "keyword": "kw", "title": "T", "platforms": ["A", "B"], "base_score": 0.7}
    tags = engine.derive_quality_tags(trend, 0.7, [], set())
    assert "Multi-Platform Signal" in tags


def test_derive_quality_tags_fresh_signal():
    trend = {"id": "t", "keyword": "unique keyword xyz", "title": "T", "platforms": ["A"], "base_score": 0.6}
    tags = engine.derive_quality_tags(trend, 0.6, [], set())
    assert "Fresh Signal" in tags


def test_derive_quality_tags_recurring_trend():
    trend = {"id": "t", "keyword": "existing keyword", "title": "T", "platforms": ["A"], "base_score": 0.6}
    existing_kws = {"existing keyword"}
    tags = engine.derive_quality_tags(trend, 0.6, [], existing_kws)
    assert "Recurring Trend" in tags
    assert "Fresh Signal" not in tags


def test_derive_quality_tags_based_on_prior_success():
    trend = {"id": "t", "keyword": "leadership burnout", "title": "T", "platforms": ["LinkedIn"], "base_score": 0.7}
    approved = [{"title": "Post about leadership and burnout recovery", "summary": "", "approval_state": "approved"}]
    tags = engine.derive_quality_tags(trend, 0.7, approved, set())
    assert "Based on Prior Success" in tags


def test_generate_discovery_insights_creates_records():
    db = _make_db()
    results = engine.generate_discovery_insights(db, "ws-test", None, "media_growth", source_run_id="run-abc")
    assert len(results) > 0
    # Records should be persisted to the fake collection
    assert len(db.discovery_insights.documents) == len(results)


def test_generate_discovery_insights_returns_list():
    db = _make_db()
    results = engine.generate_discovery_insights(db, "ws-test", None, "media_growth")
    assert isinstance(results, list)


def test_generate_discovery_insights_has_evidence():
    db = _make_db()
    results = engine.generate_discovery_insights(db, "ws-test", None, "media_growth")
    for insight in results:
        assert isinstance(insight.get("evidence"), list)
        assert len(insight["evidence"]) > 0


def test_generate_discovery_insights_has_recommendation():
    db = _make_db()
    results = engine.generate_discovery_insights(db, "ws-test", None, "media_growth")
    for insight in results:
        rec = insight.get("recommendation")
        assert isinstance(rec, dict)
        assert "recommended_asset_types" in rec
        assert "recommended_platforms" in rec


def test_generate_discovery_insights_confidence_in_range():
    db = _make_db()
    results = engine.generate_discovery_insights(db, "ws-test", None, "media_growth")
    for insight in results:
        score = insight.get("confidence_score", -1)
        assert 0.0 <= score <= 1.0, f"confidence_score {score} out of bounds"


def test_generate_discovery_insights_links_source_run():
    db = _make_db()
    results = engine.generate_discovery_insights(db, "ws-test", None, "media_growth", source_run_id="run-xyz-123")
    for insight in results:
        assert insight.get("source_run_id") == "run-xyz-123"


def test_generate_discovery_insights_has_quality_tags():
    db = _make_db()
    results = engine.generate_discovery_insights(db, "ws-test", None, "media_growth")
    for insight in results:
        tags = insight.get("quality_tags")
        assert isinstance(tags, list)
        assert len(tags) > 0


def test_generate_discovery_insights_max_insights():
    db = _make_db()
    results = engine.generate_discovery_insights(db, "ws-test", None, "media_growth", max_insights=2)
    assert len(results) <= 2


def test_asset_docs_from_insight():
    insight = {
        "_id": ObjectId(),
        "title": "Test Insight",
        "summary": "A test insight summary",
        "workspace_slug": "ws-test",
        "recommendation": {
            "recommended_asset_types": ["script_draft", "linkedin_post", "video_prompt"],
        },
    }
    docs = engine.asset_docs_from_insight(insight)
    assert isinstance(docs, list)
    assert len(docs) > 0
    assert len(docs) <= 3
    for doc in docs:
        assert doc["workspace_slug"] == "ws-test"
        assert str(insight["_id"]) in doc["source_discovery_insight_id"]
        assert doc["approval_state"] == "needs_review"
        assert doc["asset_type"] in ["script_draft", "linkedin_post", "video_prompt"]


# ── API endpoint tests ────────────────────────────────────────────────────────


def _seed_insight():
    return {
        "_id": ObjectId("cccccccccccccccccccccccc"),
        "workspace_slug": "ws-api-test",
        "insight_type": "content_opportunity",
        "title": "API Test Insight",
        "summary": "Summary for API test",
        "confidence_score": 0.85,
        "evidence": [{"platform": "LinkedIn", "signal_type": "search_trend", "keyword": "test kw"}],
        "recommendation": {
            "recommended_asset_types": ["script_draft", "linkedin_post"],
            "recommended_platforms": ["LinkedIn"],
            "recommended_next_stage": "generate_content",
            "rationale": "Test rationale",
        },
        "quality_tags": ["High Confidence", "Fresh Signal"],
        "source_agent": "discovery_engine",
        "source_run_id": None,
        "linked_workflow_asset_ids": [],
        "status": "approved",
        "approved_by": None,
        "approved_at": None,
        "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }


def test_trigger_discovery_insight_generation(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient(db)
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post(
        "/discovery-insights/generate",
        json={"workspace_slug": "ws-api-test", "module": "media_growth"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert data["count"] == len(data["items"])
    assert data["count"] > 0


def test_trigger_discovery_insight_generation_missing_workspace(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient(db)
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post(
        "/discovery-insights/generate",
        json={"workspace_slug": "", "module": "media_growth"},
    )
    assert response.status_code == 400


def test_generate_assets_from_insight(monkeypatch):
    insight = _seed_insight()
    db = FakeDatabase()
    db.discovery_insights = FakeCollection([insight])
    fake_client = FakeClient(db)
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post(f"/discovery-insights/cccccccccccccccccccccccc/generate-assets")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["count"] > 0
    # Each asset should be linked to the insight
    for asset in data["items"]:
        assert asset["source_discovery_insight_id"] == "cccccccccccccccccccccccc"
        assert asset["approval_state"] == "needs_review"


def test_generate_assets_from_insight_not_found(monkeypatch):
    db = FakeDatabase()
    fake_client = FakeClient(db)
    monkeypatch.setattr(main, "get_client", lambda: fake_client)
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    response = client.post("/discovery-insights/dddddddddddddddddddddddd/generate-assets")
    assert response.status_code == 404
