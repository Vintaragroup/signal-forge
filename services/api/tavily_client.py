"""
tavily_client.py — Tavily search client for SignalForge trend discovery.

Read-only web search only. Never posts, publishes, or schedules anything, and
never takes any outbound action — it only returns ranked web results for an
operator/agent to review. Gated behind TAVILY_ENABLED (default false) and
TAVILY_API_KEY; when disabled or unconfigured, search() returns a
deterministic simulated result and makes no network call — same fallback
precedent as approved_url_downloader.py / comfyui_client.py.

This module is intentionally dependency-light (only stdlib + requests).
It is imported by agents/trend_discovery_agent.py; do not import main from here.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import requests

TAVILY_API_BASE = "https://api.tavily.com"

_MAX_RETRIES = 3
_BASE_BACKOFF_S = 1.0
_MAX_BACKOFF_S = 10.0
_TIMEOUT_S = 20
_RATE_LIMIT_CODE = 429


# ── Configuration ─────────────────────────────────────────────────────────────

def _is_enabled() -> bool:
    return os.getenv("TAVILY_ENABLED", "false").strip().lower() == "true"


def _api_key() -> str:
    return os.getenv("TAVILY_API_KEY", "").strip()


def is_configured() -> bool:
    """True when Tavily is enabled AND an API key is present."""
    return _is_enabled() and bool(_api_key())


# ── Utilities ─────────────────────────────────────────────────────────────────

def _redact(key: str | None) -> str:
    """Return last-4 chars with prefix; safe for logs. Never logs the full key."""
    if not key:
        return "<none>"
    return f"...{key[-4:]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _backoff(attempt: int) -> float:
    return min(_MAX_BACKOFF_S, _BASE_BACKOFF_S * (2 ** attempt))


# ── Exceptions ────────────────────────────────────────────────────────────────

class TavilyError(Exception):
    """Base class for all Tavily client errors."""


class TavilyRateLimitError(TavilyError):
    """Rate limit retries exhausted."""


# ── Search ────────────────────────────────────────────────────────────────────

def search(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    topic: str = "general",
    days: int | None = None,
    min_score: float = 0.0,
) -> dict[str, Any]:
    """
    Run a Tavily web search for trend/content discovery.

    Read-only. Returns ranked web results (title, url, content snippet, score,
    published_date) for a human/agent to review — never posts, publishes, or
    takes any outbound action.

    topic: "general" (default) or "news". Tavily only returns published_date
        reliably and only honors `days` under topic="news" — "general" search
        skews toward evergreen content with no date at all.
    days: recency window in days, only applied when topic="news" (defaults
        to 30 in that case).
    min_score: results with a numeric score below this are dropped. Results
        with no score field are kept as-is (not penalized for a field Tavily
        didn't return).

    Returns:
        {
            "query": str,
            "results": [{"title", "url", "content", "score", "published_date"}],
            "simulated": bool,
            "skip_reason": str | None,
            "queried_at": iso timestamp,
        }

    When TAVILY_ENABLED is not "true" or TAVILY_API_KEY is unset, returns a
    deterministic empty result with simulated=True and makes no network call.
    """
    queried_at = _now_iso()
    query = (query or "").strip()

    if not query:
        return {
            "query": query,
            "results": [],
            "simulated": True,
            "skip_reason": "query is empty",
            "queried_at": queried_at,
        }

    if not is_configured():
        return {
            "query": query,
            "results": [],
            "simulated": True,
            "skip_reason": "TAVILY_ENABLED is not true or TAVILY_API_KEY is unset",
            "queried_at": queried_at,
        }

    api_key = _api_key()
    capped_results = max(1, min(int(max_results or 5), 20))
    body = {
        "api_key": api_key,
        "query": query,
        "search_depth": search_depth if search_depth in ("basic", "advanced") else "basic",
        "max_results": capped_results,
        "include_answer": False,
    }
    if topic == "news":
        body["topic"] = "news"
        body["days"] = days if days is not None else 30

    raw = _post_json_retry(f"{TAVILY_API_BASE}/search", body, api_key)

    results: list[dict[str, Any]] = []
    for item in (raw.get("results") or [])[:capped_results]:
        score = item.get("score")
        if isinstance(score, (int, float)) and score < min_score:
            continue
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "score": score,
                "published_date": item.get("published_date"),
            }
        )

    return {
        "query": query,
        "results": results,
        "simulated": False,
        "skip_reason": None,
        "queried_at": queried_at,
    }


# ── Low-level HTTP ────────────────────────────────────────────────────────────

def _post_json_retry(url: str, body: dict, api_key: str) -> dict:
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.post(url, json=body, timeout=_TIMEOUT_S)
            if resp.status_code == 200:
                return resp.json() if resp.text else {}
            if resp.status_code == _RATE_LIMIT_CODE:
                wait = float(resp.headers.get("Retry-After", _backoff(attempt)))
                time.sleep(wait)
                continue
            raise TavilyError(
                f"HTTP {resp.status_code} from Tavily (key={_redact(api_key)}): {resp.text[:200]}"
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == _MAX_RETRIES - 1:
                raise TavilyError(
                    f"Network failure after {_MAX_RETRIES} attempts: {exc}"
                ) from exc
            time.sleep(_backoff(attempt))
    raise TavilyRateLimitError(f"Rate-limit retries exhausted after {_MAX_RETRIES} attempts")
