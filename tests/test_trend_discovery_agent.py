"""
tests/test_trend_discovery_agent.py
Phase 6Z — Pure-unit tests for services/api/tavily_client.py and
agents/trend_discovery_agent.py. No `main` import, no module stubbing —
these exercise the real classes directly.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

import tavily_client  # noqa: E402
from agents.trend_discovery_agent import TrendDiscoveryAgent  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# tavily_client
# ══════════════════════════════════════════════════════════════════════════════

class TestTavilyClientDisabled:

    def test_disabled_returns_simulated_no_network_call(self, monkeypatch):
        monkeypatch.delenv("TAVILY_ENABLED", raising=False)
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        with patch("tavily_client.requests.post") as mock_post:
            result = tavily_client.search("landscaping trends")
        mock_post.assert_not_called()
        assert result["simulated"] is True
        assert result["results"] == []
        assert "TAVILY_ENABLED" in result["skip_reason"]

    def test_enabled_without_key_still_simulated(self, monkeypatch):
        monkeypatch.setenv("TAVILY_ENABLED", "true")
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        with patch("tavily_client.requests.post") as mock_post:
            result = tavily_client.search("landscaping trends")
        mock_post.assert_not_called()
        assert result["simulated"] is True

    def test_empty_query_simulated(self, monkeypatch):
        monkeypatch.setenv("TAVILY_ENABLED", "true")
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        with patch("tavily_client.requests.post") as mock_post:
            result = tavily_client.search("   ")
        mock_post.assert_not_called()
        assert result["simulated"] is True

    def test_is_configured_false_by_default(self, monkeypatch):
        monkeypatch.delenv("TAVILY_ENABLED", raising=False)
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        assert tavily_client.is_configured() is False


class TestTavilyClientEnabled:

    def _mock_response(self, results):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "ok"
        resp.json.return_value = {"results": results}
        return resp

    def test_enabled_calls_api_and_shapes_results(self, monkeypatch):
        monkeypatch.setenv("TAVILY_ENABLED", "true")
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        raw_results = [
            {"title": "Landscaping trend 1", "url": "https://example.com/1",
             "content": "snippet", "score": 0.9, "published_date": "2026-08-01"},
        ]
        with patch("tavily_client.requests.post", return_value=self._mock_response(raw_results)) as mock_post:
            result = tavily_client.search("landscaping trends", max_results=3)
        mock_post.assert_called_once()
        assert result["simulated"] is False
        assert len(result["results"]) == 1
        assert result["results"][0]["url"] == "https://example.com/1"

    def test_key_never_appears_in_raised_error(self, monkeypatch):
        monkeypatch.setenv("TAVILY_ENABLED", "true")
        monkeypatch.setenv("TAVILY_API_KEY", "super-secret-key-value")
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "server error"
        with patch("tavily_client.requests.post", return_value=resp):
            with pytest.raises(tavily_client.TavilyError) as exc_info:
                tavily_client.search("landscaping trends")
        assert "super-secret-key-value" not in str(exc_info.value)

    def test_max_results_capped_at_20(self, monkeypatch):
        monkeypatch.setenv("TAVILY_ENABLED", "true")
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        with patch("tavily_client.requests.post", return_value=self._mock_response([])) as mock_post:
            tavily_client.search("query", max_results=999)
        sent_body = mock_post.call_args.kwargs["json"]
        assert sent_body["max_results"] == 20


# ══════════════════════════════════════════════════════════════════════════════
# TrendDiscoveryAgent — query building
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildQuery:

    def _agent(self):
        return TrendDiscoveryAgent(module="artist_growth", workspace_slug="pilot-john-maxwell")

    def test_query_includes_audience(self):
        agent = self._agent()
        query = agent._build_query({"audience": "mid-level managers", "content_goals": ""})
        assert "mid-level managers" in query

    def test_query_includes_content_goals(self):
        agent = self._agent()
        query = agent._build_query({"audience": "", "content_goals": "grow LinkedIn following"})
        assert "grow LinkedIn following" in query

    def test_query_falls_back_when_profile_empty(self):
        agent = self._agent()
        query = agent._build_query({})
        assert "Artist Growth" in query


# ══════════════════════════════════════════════════════════════════════════════
# TrendDiscoveryAgent — creator attribution
# ══════════════════════════════════════════════════════════════════════════════

class TestBestEffortCreatorHandle:

    def test_strips_www(self):
        handle = TrendDiscoveryAgent._best_effort_creator_handle("https://www.example.com/post/1")
        assert handle == "example.com"

    def test_bare_domain(self):
        handle = TrendDiscoveryAgent._best_effort_creator_handle("https://blog.example.com/x")
        assert handle == "blog.example.com"

    def test_invalid_url_returns_empty(self):
        handle = TrendDiscoveryAgent._best_effort_creator_handle("not a url")
        assert handle == ""


# ══════════════════════════════════════════════════════════════════════════════
# TrendDiscoveryAgent — source_content bridge
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateSourceContentCandidates:

    def _agent_with_db(self):
        agent = TrendDiscoveryAgent(module="artist_growth", workspace_slug="pilot-john-maxwell")
        agent.db = MagicMock()
        agent.db.source_content.insert_one.return_value = MagicMock(inserted_id="fake_id")
        agent.run_id = "run_123"
        return agent

    def test_creates_one_doc_per_result(self):
        agent = self._agent_with_db()
        results = [
            {"title": "A", "url": "https://a.example.com", "score": 0.8, "published_date": ""},
            {"title": "B", "url": "https://b.example.com", "score": 0.7, "published_date": ""},
        ]
        created = agent._create_source_content_candidates(results, "test query")
        assert len(created) == 2
        assert agent.db.source_content.insert_one.call_count == 2

    def test_content_rights_is_third_party_curated(self):
        agent = self._agent_with_db()
        results = [{"title": "A", "url": "https://a.example.com", "score": 0.8, "published_date": ""}]
        created = agent._create_source_content_candidates(results, "test query")
        assert created[0]["content_rights"] == "third_party_curated"

    def test_status_needs_review(self):
        agent = self._agent_with_db()
        results = [{"title": "A", "url": "https://a.example.com", "score": 0.8, "published_date": ""}]
        created = agent._create_source_content_candidates(results, "test query")
        assert created[0]["status"] == "needs_review"

    def test_attribution_caption_populated(self):
        agent = self._agent_with_db()
        results = [{"title": "A", "url": "https://a.example.com", "score": 0.8, "published_date": ""}]
        created = agent._create_source_content_candidates(results, "test query")
        assert "a.example.com" in created[0]["attribution_caption"]

    def test_skips_results_without_url(self):
        agent = self._agent_with_db()
        results = [{"title": "No URL", "url": "", "score": 0.5}]
        created = agent._create_source_content_candidates(results, "test query")
        assert created == []
        agent.db.source_content.insert_one.assert_not_called()

    def test_simulation_safety_fields(self):
        agent = self._agent_with_db()
        results = [{"title": "A", "url": "https://a.example.com", "score": 0.8, "published_date": ""}]
        created = agent._create_source_content_candidates(results, "test query")
        assert created[0]["simulation_only"] is True
        assert created[0]["outbound_actions_taken"] == 0

    def test_insert_failure_is_non_fatal(self):
        agent = self._agent_with_db()
        agent.db.source_content.insert_one.side_effect = Exception("db down")
        results = [{"title": "A", "url": "https://a.example.com", "score": 0.8, "published_date": ""}]
        created = agent._create_source_content_candidates(results, "test query")
        assert created == []


# ══════════════════════════════════════════════════════════════════════════════
# TrendDiscoveryAgent — plan_actions (end-to-end within the class, db/tavily mocked)
# ══════════════════════════════════════════════════════════════════════════════

class TestPlanActions:

    def _agent_with_db(self):
        agent = TrendDiscoveryAgent(module="artist_growth", workspace_slug="pilot-john-maxwell")
        agent.db = MagicMock()
        agent.db.client_profiles.find_one.return_value = {"audience": "aspiring artists", "content_goals": ""}
        agent.db.source_content.insert_one.return_value = MagicMock(inserted_id="fake_id")
        agent.run_id = "run_123"
        return agent

    def test_no_results_returns_informational_action(self):
        agent = self._agent_with_db()
        with patch.object(TrendDiscoveryAgent, "_import_tavily_search") as mock_import:
            mock_import.return_value = lambda query, max_results=5: {
                "simulated": True, "results": [], "skip_reason": "TAVILY_ENABLED is not true or TAVILY_API_KEY is unset",
            }
            actions = agent.plan_actions([])
        assert len(actions) == 1
        assert "No source_content candidates" in actions[0]["planned_action"]

    def test_results_produce_review_actions(self):
        agent = self._agent_with_db()
        with patch.object(TrendDiscoveryAgent, "_import_tavily_search") as mock_import:
            mock_import.return_value = lambda query, max_results=5: {
                "simulated": False,
                "results": [{"title": "Trend A", "url": "https://a.example.com", "score": 0.8, "published_date": ""}],
            }
            actions = agent.plan_actions([])
        assert len(actions) == 1
        assert "Review curated content candidate" in actions[0]["title"]
        assert "PATCH /source-content" in actions[0]["planned_action"]
