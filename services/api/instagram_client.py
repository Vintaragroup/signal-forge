"""
instagram_client.py — Retry-safe Instagram Graph API client for SignalForge.

Responsibilities:
  - Facebook Login OAuth (authorization URL, code exchange, long-lived token exchange)
  - Media container creation + publish (Instagram Content Publishing API)
  - Publishing-limit lookup (100 posts / rolling 24h Instagram enforces)
  - Rate-limit handling (429 back-off)
  - Exponential retry with jitter
  - Structured, token-redacted logging

Media is published by URL — Instagram's servers fetch the file themselves.
This client never uploads a file; the caller supplies a publicly-reachable
media_url. See docs/plans note: SignalForge does not auto-host media to the
public internet — the operator supplies the URL.

This module is intentionally dependency-light (only stdlib + requests).
It is imported by main.py; do not import main from here.
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import requests

logger = logging.getLogger("signalforge.instagram")

# ── Configuration ─────────────────────────────────────────────────────────────

INSTAGRAM_CLIENT_ID     = os.getenv("INSTAGRAM_CLIENT_ID", "")
INSTAGRAM_CLIENT_SECRET = os.getenv("INSTAGRAM_CLIENT_SECRET", "")
INSTAGRAM_REDIRECT_URI  = os.getenv("INSTAGRAM_REDIRECT_URI", "http://localhost:8000/connect/instagram/callback")

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE    = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
FACEBOOK_AUTH_BASE = "https://www.facebook.com"
INSTAGRAM_SCOPES   = ["instagram_business_basic", "instagram_business_content_publish"]

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
    """Return the Facebook Login OAuth 2.0 authorization URL for Instagram scopes."""
    params = {
        "response_type": "code",
        "client_id": INSTAGRAM_CLIENT_ID,
        "redirect_uri": INSTAGRAM_REDIRECT_URI,
        "state": state,
        "scope": ",".join(INSTAGRAM_SCOPES),
    }
    return f"{FACEBOOK_AUTH_BASE}/{GRAPH_API_VERSION}/dialog/oauth?{urlencode(params)}"


def exchange_code_for_token(code: str) -> dict[str, Any]:
    """
    Exchange an authorization code for a short-lived access token.
    Returns a dict with: access_token, token_type, expires_in.
    Raises InstagramAuthError on failure.
    """
    params = {
        "client_id":     INSTAGRAM_CLIENT_ID,
        "client_secret": INSTAGRAM_CLIENT_SECRET,
        "redirect_uri":  INSTAGRAM_REDIRECT_URI,
        "code":          code,
    }
    resp = _get_json(f"{GRAPH_API_BASE}/oauth/access_token", params)
    _validate_token_response(resp)
    logger.info("Instagram short-lived token exchanged token=%s", _redact(resp.get("access_token")))
    return resp


def get_long_lived_token(short_lived_token: str) -> dict[str, Any]:
    """
    Exchange a short-lived token for a ~60-day long-lived token.
    Meta's long-lived exchange is a GET with grant_type=fb_exchange_token —
    unlike LinkedIn, there is no POST refresh_token grant; the long-lived
    token is simply used until it expires, then this exchange is repeated.
    Returns a dict with: access_token, token_type, expires_in (seconds).
    """
    params = {
        "grant_type":        "fb_exchange_token",
        "client_id":         INSTAGRAM_CLIENT_ID,
        "client_secret":     INSTAGRAM_CLIENT_SECRET,
        "fb_exchange_token": short_lived_token,
    }
    resp = _get_json(f"{GRAPH_API_BASE}/oauth/access_token", params)
    _validate_token_response(resp)
    logger.info("Instagram long-lived token exchanged token=%s", _redact(resp.get("access_token")))
    return resp


def _validate_token_response(resp: dict) -> None:
    if "access_token" not in resp:
        raise InstagramAuthError(f"Token response missing access_token: {resp}")


# ── Publish ───────────────────────────────────────────────────────────────────

def create_media_container(
    access_token: str,
    ig_user_id: str,
    media_url: str,
    caption: str,
    media_type: str = "IMAGE",
) -> dict[str, Any]:
    """
    Create a media container — the first step of the two-step publish flow.

    media_type: "IMAGE" or "REELS". Instagram's servers fetch media_url
    themselves; it must be publicly reachable (not localhost/Docker-internal).

    Returns {"creation_id": ..., "raw_response": ...}.
    Raises InstagramPublishError on failure.
    """
    params: dict[str, Any] = {
        "access_token": access_token,
        "caption":      caption,
    }
    if media_type == "REELS":
        params["media_type"] = "REELS"
        params["video_url"]  = media_url
    else:
        params["image_url"] = media_url

    resp_data = _post_form_retry(f"{GRAPH_API_BASE}/{ig_user_id}/media", params, access_token)
    creation_id = resp_data.get("id", "")
    if not creation_id:
        raise InstagramPublishError(f"Container creation returned no id: {resp_data}")

    logger.info("Instagram media container created creation_id=%s", creation_id)
    return {"creation_id": creation_id, "raw_response": resp_data}


def publish_container(access_token: str, ig_user_id: str, creation_id: str) -> dict[str, Any]:
    """
    Publish a previously-created media container.

    Returns {
        external_post_id, published_url, published_at, raw_response
    }.
    Raises InstagramPublishError / InstagramRateLimitError on failure.
    """
    params = {
        "access_token": access_token,
        "creation_id":  creation_id,
    }
    resp_data = _post_form_retry(f"{GRAPH_API_BASE}/{ig_user_id}/media_publish", params, access_token)
    post_id = resp_data.get("id", "")
    published_url = f"https://www.instagram.com/p/{post_id}/" if post_id else ""

    result = {
        "external_post_id": post_id,
        "published_url":    published_url,
        "published_at":     _now_iso(),
        "raw_response":      resp_data,
    }
    logger.info("Instagram media published post_id=%s", post_id)
    return result


def get_publishing_limit(access_token: str, ig_user_id: str) -> dict[str, Any]:
    """
    Return the current publishing-limit usage for this IG user.

    Returns {"quota_usage": int, "config": {...}} shaped from Instagram's
    content_publishing_limit endpoint (100 posts / rolling 24h).
    """
    resp = _get_json(
        f"{GRAPH_API_BASE}/{ig_user_id}/content_publishing_limit",
        {"access_token": access_token},
    )
    data = (resp.get("data") or [{}])[0] if isinstance(resp.get("data"), list) else {}
    return {
        "quota_usage": data.get("quota_usage", 0),
        "config":      data.get("config", {}),
        "raw_response": resp,
    }


# ── Low-level HTTP ────────────────────────────────────────────────────────────

def _get_json(url: str, params: dict) -> dict:
    resp = requests.get(url, params=params, timeout=15)
    if not resp.ok:
        raise InstagramAuthError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def _post_form_retry(url: str, params: dict, access_token: str) -> dict:
    """POST (as query params, matching Graph API convention) with exponential retry."""
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.post(url, params=params, timeout=20)
            if resp.status_code == 200:
                return resp.json() if resp.text else {}
            if resp.status_code == _RATE_LIMIT_CODE:
                wait = _backoff(attempt)
                logger.warning("Instagram rate-limited attempt=%d wait=%.1fs token=%s",
                               attempt, wait, _redact(access_token))
                time.sleep(_jitter(wait))
                continue
            if resp.status_code == 401:
                raise InstagramTokenExpiredError(f"Token expired (401): {resp.text[:200]}")
            raise InstagramPublishError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == _MAX_RETRIES - 1:
                raise InstagramPublishError(f"Network failure after {_MAX_RETRIES} retries: {exc}") from exc
            wait = _backoff(attempt)
            logger.warning("Instagram network error attempt=%d retrying in %.1fs err=%s",
                           attempt, wait, exc)
            time.sleep(_jitter(wait))
    raise InstagramRateLimitError(f"Rate-limit retries exhausted after {_MAX_RETRIES} attempts")


def _hash_idempotency_key(key: str) -> str:
    """Produce a safe idempotency-tracking value from a source_asset_render_id."""
    return hashlib.sha256(key.encode()).hexdigest()[:32]


# ── Exceptions ────────────────────────────────────────────────────────────────

class InstagramError(Exception):
    """Base class for all Instagram client errors."""


class InstagramAuthError(InstagramError):
    """OAuth / token errors."""


class InstagramTokenExpiredError(InstagramAuthError):
    """Access token is expired; caller should re-run the long-lived exchange."""


class InstagramPublishError(InstagramError):
    """Container creation / publish failed."""


class InstagramRateLimitError(InstagramPublishError):
    """Rate limit retries exhausted, or the 100/24h publishing limit was hit."""
