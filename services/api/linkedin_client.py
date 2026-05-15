"""
linkedin_client.py — Retry-safe LinkedIn API client for SignalForge.

Responsibilities:
  - OAuth token exchange & refresh
  - Post publishing (UGC Posts API)
  - Post status / verification retrieval
  - Rate-limit handling (429 back-off)
  - Exponential retry with jitter
  - Structured, token-redacted logging

This module is intentionally dependency-light (only stdlib + requests).
It is imported by main.py; do not import main from here.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import requests

logger = logging.getLogger("signalforge.linkedin")

# ── Configuration ─────────────────────────────────────────────────────────────

LINKEDIN_CLIENT_ID     = os.getenv("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")
LINKEDIN_REDIRECT_URI  = os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:8000/connect/linkedin/callback")
LINKEDIN_API_BASE      = "https://api.linkedin.com/v2"
LINKEDIN_AUTH_BASE     = "https://www.linkedin.com/oauth/v2"
LINKEDIN_SCOPES        = ["w_member_social", "r_liteprofile"]

# Retry settings
_MAX_RETRIES     = 4
_BASE_BACKOFF_S  = 1.0
_MAX_BACKOFF_S   = 30.0
_RATE_LIMIT_CODE = 429

# ── Utilities ─────────────────────────────────────────────────────────────────

def _redact(token: str | None) -> str:
    """Return last-4 chars with prefix; safe for logs."""
    if not token:
        return "<none>"
    return f"...{token[-4:]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jitter(base: float) -> float:
    return base * (0.75 + random.random() * 0.5)


def _backoff(attempt: int) -> float:
    return min(_MAX_BACKOFF_S, _BASE_BACKOFF_S * (2 ** attempt))


# ── OAuth Helpers ─────────────────────────────────────────────────────────────

def build_authorization_url(state: str) -> str:
    """Return the LinkedIn OAuth 2.0 authorization URL."""
    params = {
        "response_type": "code",
        "client_id": LINKEDIN_CLIENT_ID,
        "redirect_uri": LINKEDIN_REDIRECT_URI,
        "state": state,
        "scope": " ".join(LINKEDIN_SCOPES),
    }
    return f"{LINKEDIN_AUTH_BASE}/authorization?{urlencode(params)}"


def exchange_code_for_token(code: str) -> dict[str, Any]:
    """
    Exchange an authorization code for an access + refresh token.
    Returns a dict with: access_token, refresh_token, expires_in, token_type.
    Raises LinkedInAuthError on failure.
    """
    payload = {
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  LINKEDIN_REDIRECT_URI,
        "client_id":     LINKEDIN_CLIENT_ID,
        "client_secret": LINKEDIN_CLIENT_SECRET,
    }
    resp = _post_form(f"{LINKEDIN_AUTH_BASE}/accessToken", payload)
    _validate_token_response(resp)
    logger.info("LinkedIn token exchanged token=%s", _redact(resp.get("access_token")))
    return resp


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    """
    Use a refresh_token to obtain a new access_token.
    Returns same shape as exchange_code_for_token.
    """
    payload = {
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
        "client_id":     LINKEDIN_CLIENT_ID,
        "client_secret": LINKEDIN_CLIENT_SECRET,
    }
    resp = _post_form(f"{LINKEDIN_AUTH_BASE}/accessToken", payload)
    _validate_token_response(resp)
    logger.info("LinkedIn token refreshed token=%s", _redact(resp.get("access_token")))
    return resp


def _validate_token_response(resp: dict) -> None:
    if "access_token" not in resp:
        raise LinkedInAuthError(f"Token response missing access_token: {resp}")


# ── Publish ───────────────────────────────────────────────────────────────────

def publish_post(access_token: str, author_urn: str, text: str,
                 idempotency_key: str | None = None) -> dict[str, Any]:
    """
    Publish a text post to LinkedIn via UGC Posts API.

    Returns {
        external_post_id, published_url, request_trace_id,
        published_at, raw_response
    }

    Raises:
      LinkedInDuplicateError  — if idempotency key already used
      LinkedInRateLimitError  — if rate-limited and retries exhausted
      LinkedInPublishError    — on other failures
    """
    body = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    headers: dict[str, str] = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    if idempotency_key:
        headers["X-RestLi-Method"] = "CREATE"
        headers["X-Idempotency-Token"] = _hash_idempotency_key(idempotency_key)

    resp_data, trace_id = _post_json_retry(
        f"{LINKEDIN_API_BASE}/ugcPosts", body, headers, access_token
    )

    post_id = resp_data.get("id", "")
    published_url = f"https://www.linkedin.com/feed/update/{post_id}" if post_id else ""
    result = {
        "external_post_id":  post_id,
        "published_url":     published_url,
        "request_trace_id":  trace_id,
        "published_at":      _now_iso(),
        "raw_response":      resp_data,
    }
    logger.info("LinkedIn post published post_id=%s trace=%s", post_id, trace_id)
    return result


def get_post_status(access_token: str, post_id: str) -> dict[str, Any]:
    """
    Retrieve a post's current status from LinkedIn.
    Returns {found, lifecycleState, author, created, raw_response}.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    try:
        resp = _get_retry(
            f"{LINKEDIN_API_BASE}/ugcPosts/{requests.utils.quote(post_id, safe='')}",
            headers, access_token
        )
        return {
            "found":          True,
            "lifecycleState": resp.get("lifecycleState"),
            "author":         resp.get("author"),
            "created":        resp.get("created"),
            "raw_response":   resp,
        }
    except LinkedInNotFoundError:
        return {"found": False, "lifecycleState": None, "author": None,
                "created": None, "raw_response": {}}


# ── Low-level HTTP ────────────────────────────────────────────────────────────

def _post_form(url: str, data: dict) -> dict:
    resp = requests.post(url, data=data, timeout=15)
    if not resp.ok:
        raise LinkedInAuthError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def _post_json_retry(url: str, body: dict, headers: dict,
                     access_token: str) -> tuple[dict, str]:
    """POST with exponential retry; returns (response_dict, trace_id)."""
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=20)
            trace_id = resp.headers.get("x-restli-id", "") or resp.headers.get("x-li-fabric", "")
            if resp.status_code == 201:
                return resp.json() if resp.text else {}, trace_id
            if resp.status_code == 409:
                raise LinkedInDuplicateError(f"Duplicate post (409): {resp.text[:200]}")
            if resp.status_code == _RATE_LIMIT_CODE:
                wait = float(resp.headers.get("Retry-After", _backoff(attempt)))
                logger.warning("LinkedIn rate-limited attempt=%d wait=%.1fs token=%s",
                               attempt, wait, _redact(access_token))
                time.sleep(_jitter(wait))
                continue
            if resp.status_code == 401:
                raise LinkedInTokenExpiredError(f"Token expired (401): {resp.text[:200]}")
            raise LinkedInPublishError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == _MAX_RETRIES - 1:
                raise LinkedInPublishError(f"Network failure after {_MAX_RETRIES} retries: {exc}") from exc
            wait = _backoff(attempt)
            logger.warning("LinkedIn network error attempt=%d retrying in %.1fs err=%s",
                           attempt, wait, exc)
            time.sleep(_jitter(wait))
    raise LinkedInPublishError(f"Rate-limit retries exhausted after {_MAX_RETRIES} attempts")


def _get_retry(url: str, headers: dict, access_token: str) -> dict:
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                raise LinkedInNotFoundError(f"Post not found: {url}")
            if resp.status_code == _RATE_LIMIT_CODE:
                wait = float(resp.headers.get("Retry-After", _backoff(attempt)))
                time.sleep(_jitter(wait))
                continue
            if resp.status_code == 401:
                raise LinkedInTokenExpiredError("Token expired")
            raise LinkedInPublishError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == _MAX_RETRIES - 1:
                raise LinkedInPublishError(f"Network failure: {exc}") from exc
            time.sleep(_jitter(_backoff(attempt)))
    raise LinkedInPublishError("GET retries exhausted")


def _hash_idempotency_key(key: str) -> str:
    """Produce a safe idempotency header value from a workflow asset ID."""
    return hashlib.sha256(key.encode()).hexdigest()[:32]


# ── Exceptions ────────────────────────────────────────────────────────────────

class LinkedInError(Exception):
    """Base class for all LinkedIn client errors."""


class LinkedInAuthError(LinkedInError):
    """OAuth / token errors."""


class LinkedInTokenExpiredError(LinkedInAuthError):
    """Access token is expired; caller should refresh."""


class LinkedInPublishError(LinkedInError):
    """Post creation/retrieval failed."""


class LinkedInDuplicateError(LinkedInPublishError):
    """Duplicate publish attempt detected via idempotency key."""


class LinkedInRateLimitError(LinkedInPublishError):
    """Rate limit retries exhausted."""


class LinkedInNotFoundError(LinkedInPublishError):
    """Requested resource not found (404)."""
