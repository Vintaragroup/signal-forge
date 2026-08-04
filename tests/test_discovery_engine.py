"""
Phase 6D — Backend tests for discovery_engine module and new endpoints.

Note: generate_discovery_insights() now sources trends from real Tavily
search via get_real_social_trends() (services/api/discovery_engine.py).
Tests that exercise generate_discovery_insights()/the /discovery-insights
endpoints monkeypatch get_real_social_trends() with deterministic fixture
data so they stay pure-unit — no real network calls.
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
        self.client_profiles = FakeCollection([])


class FakeClient:
    def __init__(self, db: FakeDatabase):
        self._db = db

    def close(self):
        pass


# ── Fixture trend data (stand-in for real Tavily-derived trends) ───────────────


def _fake_trend(idx=0, **overrides):
    trend = {
        "id": f"fake_trend_{idx}",
        "keyword": "media growth — trending audience content this week",
        "title": f"Fake discovered article {idx}",
        "summary": "A short content snippet from a real search result.",
        "insight_type": "content_opportunity",
        "platforms": ["TikTok"],
        "asset_types": ["content_brief"],
        "next_stage": "generate_content",
        "rationale": "Discovered via Tavily search for 'media growth'.",
        "base_score": 0.6,
        "signal_type": "search_trend",
        "source_url": f"https://example.com/article-{idx}",
    }
    trend.update(overrides)
    return trend


def _fake_trends(count=3):
    return [_fake_trend(i) for i in range(count)]


# ── Discovery engine unit tests ─────────────────────────────────────────────────


def _make_db():
    return FakeDatabase()


def test_score_opportunity_bounds():
    for trend in [_fake_trend(0, base_score=0.9), _fake_trend(1, base_score=0.1), _fake_trend(2, platforms=["A", "B", "C"])]:
        score = engine.score_opportunity(trend, [], set())
        assert 0.0 <= score <= 1.0, f"score {score} out of bounds for {trend['id']}"


def test_score_opportunity_high_with_prior_match():
    trend = _fake_trend(0)
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
    trend = _fake_trend(0)
    rec = engine.build_recommendation(trend, "media_growth")
    assert "recommended_asset_types" in rec
    assert "recommended_platforms" in rec
    assert "recommended_next_stage" in rec
    assert "rationale" in rec
    assert isinstance(rec["recommended_asset_types"], list)
    assert isinstance(rec["recommended_platforms"], list)


def test_build_evidence_structure():
    trend = _fake_trend(0)
    evidence = engine.build_evidence(trend)
    assert isinstance(evidence, list)
    assert len(evidence) >= 1
    for ev in evidence:
        assert "signal_type" in ev
        assert "keyword" in ev


def test_build_evidence_includes_source_url():
    trend = _fake_trend(0, source_url="https://example.com/real-article")
    evidence = engine.build_evidence(trend)
    assert evidence[0]["source_url"] == "https://example.com/real-article"


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


# ── _clean_search_snippet() ─────────────────────────────────────────────────────


def test_clean_search_snippet_empty_input():
    assert engine._clean_search_snippet("") == ""


def test_clean_search_snippet_drops_nav_chrome():
    # Realistic case: nav chrome mixed with real content (never 100% chrome).
    messy = (
        "TikTok\n\nLog in\n\nSearch\n\nFor You\n\nExplore\n\nFollowing\n\nLIVE\n\nUpload\n\nProfile\n\nMore\n\n"
        "This creator's growth tips video is getting strong engagement this week."
    )
    cleaned = engine._clean_search_snippet(messy)
    assert "Log in" not in cleaned
    assert "For You" not in cleaned
    assert "This creator's growth tips video is getting strong engagement this week." in cleaned


def test_clean_search_snippet_drops_pure_digit_lines():
    messy = "A real sentence about growth trends worth keeping.\n\n207\n\n11\n\n69"
    cleaned = engine._clean_search_snippet(messy)
    assert "207" not in cleaned
    assert "A real sentence about growth trends worth keeping." in cleaned


def test_clean_search_snippet_dedupes_exact_repeated_lines():
    messy = "This is a repeated content line worth keeping.\n\nThis is a repeated content line worth keeping."
    cleaned = engine._clean_search_snippet(messy)
    assert cleaned.count("This is a repeated content line worth keeping.") == 1


def test_clean_search_snippet_keeps_real_sentences():
    messy = "Log in\n\nThis longer sentence describes a real content trend and should be kept intact."
    cleaned = engine._clean_search_snippet(messy)
    assert "This longer sentence describes a real content trend and should be kept intact." in cleaned


def test_clean_search_snippet_truncates_at_word_boundary():
    long_text = "This is a real sentence. " * 40
    cleaned = engine._clean_search_snippet(long_text, max_len=100)
    assert len(cleaned) <= 101  # allow for the trailing ellipsis character
    assert cleaned.endswith("…")
    assert not cleaned[:-1].endswith(" ")


def test_clean_search_snippet_falls_back_to_raw_when_everything_filtered():
    # All-short/all-digit input has nothing left after filtering -- fall back
    # to the (whitespace-collapsed) original rather than returning "".
    messy = "1\n\n2\n\n3"
    cleaned = engine._clean_search_snippet(messy)
    assert cleaned == "1 2 3"


# ── get_real_social_trends() ────────────────────────────────────────────────────


def test_get_real_social_trends_no_results_returns_empty(monkeypatch):
    import tavily_client

    monkeypatch.setattr(tavily_client, "search", lambda *a, **kw: {"simulated": True, "results": []})
    db = _make_db()
    trends = engine.get_real_social_trends("media_growth", "ws-test", None, db)
    assert trends == []


def test_get_real_social_trends_maps_real_results(monkeypatch):
    import tavily_client

    def fake_search(query, **kwargs):
        assert kwargs.get("topic") == "news"
        assert kwargs.get("days") == 30
        assert kwargs.get("min_score") == 0.3
        return {
            "simulated": False,
            "results": [
                {"title": "Real Article", "url": "https://tiktok.com/@user/video/1", "content": "snippet", "score": 0.55, "published_date": "2026-08-01"},
            ],
        }

    monkeypatch.setattr(tavily_client, "search", fake_search)
    db = _make_db()
    db.client_profiles = FakeCollection([{"workspace_slug": "ws-test", "audience": "artists", "content_goals": "grow"}])
    trends = engine.get_real_social_trends("media_growth", "ws-test", None, db)
    assert len(trends) == 1
    assert trends[0]["title"] == "Real Article"
    assert trends[0]["source_url"] == "https://tiktok.com/@user/video/1"
    assert trends[0]["platforms"] == ["TikTok"]
    assert trends[0]["base_score"] == 0.55
    assert "Warning:" not in trends[0]["rationale"]


def test_get_real_social_trends_cleans_summary(monkeypatch):
    import tavily_client

    messy_content = "TikTok\n\nLog in\n\nSearch\n\nFor You\n\nA real sentence describing the actual content trend worth keeping."

    monkeypatch.setattr(
        tavily_client,
        "search",
        lambda *a, **kw: {
            "simulated": False,
            "results": [{"title": "T", "url": "https://tiktok.com/@user/video/1", "content": messy_content, "score": 0.5, "published_date": None}],
        },
    )
    db = _make_db()
    trends = engine.get_real_social_trends("media_growth", "ws-test", None, db)
    assert "Log in" not in trends[0]["summary"]
    assert "A real sentence describing the actual content trend worth keeping." in trends[0]["summary"]


def test_get_real_social_trends_flags_generic_fallback(monkeypatch):
    import tavily_client

    monkeypatch.setattr(
        tavily_client,
        "search",
        lambda *a, **kw: {
            "simulated": False,
            "results": [{"title": "T", "url": "https://example.com/1", "content": "", "score": 0.5, "published_date": None}],
        },
    )
    db = _make_db()  # no client_profiles seeded -> generic fallback
    trends = engine.get_real_social_trends("media_growth", "ws-test", None, db)
    assert len(trends) == 1
    assert "Warning:" in trends[0]["rationale"]
    assert "generic fallback query" in trends[0]["rationale"]


# ── generate_discovery_insights() (get_real_social_trends monkeypatched) ───────


def _patch_real_trends(monkeypatch, trends=None):
    monkeypatch.setattr(engine, "get_real_social_trends", lambda *a, **kw: trends if trends is not None else _fake_trends())


def test_generate_discovery_insights_creates_records(monkeypatch):
    _patch_real_trends(monkeypatch)
    db = _make_db()
    results = engine.generate_discovery_insights(db, "ws-test", None, "media_growth", source_run_id="run-abc")
    assert len(results) > 0
    # Records should be persisted to the fake collection
    assert len(db.discovery_insights.documents) == len(results)


def test_generate_discovery_insights_returns_list(monkeypatch):
    _patch_real_trends(monkeypatch)
    db = _make_db()
    results = engine.generate_discovery_insights(db, "ws-test", None, "media_growth")
    assert isinstance(results, list)


def test_generate_discovery_insights_empty_when_no_trends(monkeypatch):
    _patch_real_trends(monkeypatch, trends=[])
    db = _make_db()
    results = engine.generate_discovery_insights(db, "ws-test", None, "media_growth")
    assert results == []


def test_generate_discovery_insights_has_evidence(monkeypatch):
    _patch_real_trends(monkeypatch)
    db = _make_db()
    results = engine.generate_discovery_insights(db, "ws-test", None, "media_growth")
    for insight in results:
        assert isinstance(insight.get("evidence"), list)
        assert len(insight["evidence"]) > 0


def test_generate_discovery_insights_has_recommendation(monkeypatch):
    _patch_real_trends(monkeypatch)
    db = _make_db()
    results = engine.generate_discovery_insights(db, "ws-test", None, "media_growth")
    for insight in results:
        rec = insight.get("recommendation")
        assert isinstance(rec, dict)
        assert "recommended_asset_types" in rec
        assert "recommended_platforms" in rec


def test_generate_discovery_insights_confidence_in_range(monkeypatch):
    _patch_real_trends(monkeypatch)
    db = _make_db()
    results = engine.generate_discovery_insights(db, "ws-test", None, "media_growth")
    for insight in results:
        score = insight.get("confidence_score", -1)
        assert 0.0 <= score <= 1.0, f"confidence_score {score} out of bounds"


def test_generate_discovery_insights_links_source_run(monkeypatch):
    _patch_real_trends(monkeypatch)
    db = _make_db()
    results = engine.generate_discovery_insights(db, "ws-test", None, "media_growth", source_run_id="run-xyz-123")
    for insight in results:
        assert insight.get("source_run_id") == "run-xyz-123"


def test_generate_discovery_insights_has_quality_tags(monkeypatch):
    _patch_real_trends(monkeypatch)
    db = _make_db()
    results = engine.generate_discovery_insights(db, "ws-test", None, "media_growth")
    for insight in results:
        tags = insight.get("quality_tags")
        assert isinstance(tags, list)
        assert len(tags) > 0


def test_generate_discovery_insights_max_insights(monkeypatch):
    _patch_real_trends(monkeypatch, trends=_fake_trends(5))
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
    _patch_real_trends(monkeypatch)
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
