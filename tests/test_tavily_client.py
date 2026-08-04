"""
tests/test_tavily_client.py
Pure-unit tests for services/api/tavily_client.py's recency/relevance
controls (topic, days, min_score). No `main` import, no module stubbing —
mirrors tests/test_runway_client.py's pattern.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

import tavily_client  # noqa: E402


def _mock_response(results):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "ok"
    resp.json.return_value = {"results": results}
    return resp


class TestTopicAndDays:
    def test_default_topic_omits_topic_and_days(self, monkeypatch):
        monkeypatch.setenv("TAVILY_ENABLED", "true")
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        with patch("tavily_client.requests.post", return_value=_mock_response([])) as mock_post:
            tavily_client.search("query")
        sent_body = mock_post.call_args.kwargs["json"]
        assert "topic" not in sent_body
        assert "days" not in sent_body

    def test_news_topic_includes_topic_and_default_days(self, monkeypatch):
        monkeypatch.setenv("TAVILY_ENABLED", "true")
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        with patch("tavily_client.requests.post", return_value=_mock_response([])) as mock_post:
            tavily_client.search("query", topic="news")
        sent_body = mock_post.call_args.kwargs["json"]
        assert sent_body["topic"] == "news"
        assert sent_body["days"] == 30

    def test_news_topic_with_explicit_days(self, monkeypatch):
        monkeypatch.setenv("TAVILY_ENABLED", "true")
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        with patch("tavily_client.requests.post", return_value=_mock_response([])) as mock_post:
            tavily_client.search("query", topic="news", days=7)
        sent_body = mock_post.call_args.kwargs["json"]
        assert sent_body["days"] == 7

    def test_non_news_topic_ignores_days(self, monkeypatch):
        monkeypatch.setenv("TAVILY_ENABLED", "true")
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        with patch("tavily_client.requests.post", return_value=_mock_response([])) as mock_post:
            tavily_client.search("query", topic="general", days=7)
        sent_body = mock_post.call_args.kwargs["json"]
        assert "days" not in sent_body


class TestMinScoreFiltering:
    def _results(self):
        return [
            {"title": "Strong match", "url": "https://a.example.com", "content": "", "score": 0.6, "published_date": "2026-08-01"},
            {"title": "Junk", "url": "https://b.example.com", "content": "", "score": 0.1, "published_date": None},
            {"title": "No score field", "url": "https://c.example.com", "content": "", "published_date": None},
        ]

    def test_default_min_score_keeps_everything(self, monkeypatch):
        monkeypatch.setenv("TAVILY_ENABLED", "true")
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        with patch("tavily_client.requests.post", return_value=_mock_response(self._results())):
            result = tavily_client.search("query")
        assert len(result["results"]) == 3

    def test_min_score_drops_low_score_results(self, monkeypatch):
        monkeypatch.setenv("TAVILY_ENABLED", "true")
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        with patch("tavily_client.requests.post", return_value=_mock_response(self._results())):
            result = tavily_client.search("query", min_score=0.3)
        urls = [r["url"] for r in result["results"]]
        assert "https://a.example.com" in urls
        assert "https://b.example.com" not in urls

    def test_min_score_keeps_scoreless_results(self, monkeypatch):
        monkeypatch.setenv("TAVILY_ENABLED", "true")
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        with patch("tavily_client.requests.post", return_value=_mock_response(self._results())):
            result = tavily_client.search("query", min_score=0.3)
        urls = [r["url"] for r in result["results"]]
        assert "https://c.example.com" in urls
