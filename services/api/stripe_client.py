"""
stripe_client.py — Stripe Checkout client for SignalForge digital-asset sales.

Hosted checkout only: card data never touches this server (no PCI scope).
This module only creates/reads Checkout Sessions and verifies webhook
signatures — it never stores card data, never auto-refunds, and takes no
action beyond what an operator-approved offer explicitly authorizes.

Gated behind STRIPE_ENABLED (default false) and STRIPE_SECRET_KEY; when
disabled or unconfigured, create_checkout_session() returns a deterministic
simulated response and makes no network call — same fallback precedent as
every other real-integration client in this codebase (tavily_client.py,
instagram_client.py, runway_client.py).

This module is intentionally dependency-light (only stdlib + requests).
It is imported by main.py; do not import main from here.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import time
from datetime import datetime, timezone
from typing import Any

import requests

STRIPE_API_BASE = "https://api.stripe.com/v1"

_MAX_RETRIES = 4
_BASE_BACKOFF_S = 1.0
_MAX_BACKOFF_S = 30.0
_TIMEOUT_S = 20
_RATE_LIMIT_CODE = 429
# Stripe's documented replay-protection tolerance for webhook timestamps.
_WEBHOOK_TOLERANCE_S = 300


# ── Configuration ─────────────────────────────────────────────────────────────

def _is_enabled() -> bool:
    return os.getenv("STRIPE_ENABLED", "false").strip().lower() == "true"


def _api_key() -> str:
    return os.getenv("STRIPE_SECRET_KEY", "").strip()


def _webhook_secret() -> str:
    return os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()


def is_configured() -> bool:
    """True when Stripe is enabled AND a secret key is present."""
    return _is_enabled() and bool(_api_key())


# ── Utilities ─────────────────────────────────────────────────────────────────

def _redact(key: str | None) -> str:
    """Return last-4 chars with prefix; safe for logs. Never logs the full key."""
    if not key:
        return "<none>"
    return f"...{key[-4:]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jitter(base: float) -> float:
    return base * (0.75 + random.random() * 0.5)


def _backoff(attempt: int) -> float:
    return min(_MAX_BACKOFF_S, _BASE_BACKOFF_S * (2 ** attempt))


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


# ── Exceptions ────────────────────────────────────────────────────────────────

class StripeError(Exception):
    """Base class for all Stripe client errors."""


class StripeAuthError(StripeError):
    """Missing/invalid secret key."""


class StripeRateLimitError(StripeError):
    """Rate limit retries exhausted."""


class StripeWebhookError(StripeError):
    """Webhook signature missing, malformed, expired, or mismatched."""


# ── Checkout Sessions ─────────────────────────────────────────────────────────

def create_checkout_session(
    offer: dict[str, Any],
    success_url: str,
    cancel_url: str,
    api_key: str | None = None,
) -> dict[str, Any]:
    """
    Create a one-time-payment hosted Checkout Session for a single offer.

    offer: {"_id" or "offer_id", "title", "price_cents", "currency"}

    Returns {"session_id", "checkout_url", "simulated", "skip_reason"}.
    When Stripe is disabled/unconfigured, returns a deterministic simulated
    checkout URL and makes no network call.
    """
    offer_id = str(offer.get("offer_id") or offer.get("_id") or "")
    key = api_key or _api_key()

    if not _is_enabled() or not key:
        session_id = f"sim_session_{offer_id}"
        # success_url is expected to already contain Stripe's documented
        # {CHECKOUT_SESSION_ID} placeholder (real Checkout Sessions require
        # it); substitute it directly rather than blindly appending a second
        # "?session_id=..." onto a URL that may already have one.
        checkout_url = success_url.replace("{CHECKOUT_SESSION_ID}", session_id)
        sep = "&" if "?" in checkout_url else "?"
        checkout_url = f"{checkout_url}{sep}simulated=true"
        return {
            "session_id": session_id,
            "checkout_url": checkout_url,
            "simulated": True,
            "skip_reason": "STRIPE_ENABLED is not true or STRIPE_SECRET_KEY is unset",
        }

    currency = (offer.get("currency") or "usd").lower()
    price_cents = int(offer.get("price_cents") or 0)
    title = (offer.get("title") or "SignalForge digital asset")[:250]

    body = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": currency,
        "line_items[0][price_data][unit_amount]": str(price_cents),
        "line_items[0][price_data][product_data][name]": title,
        "metadata[offer_id]": offer_id,
    }

    raw = _post_form_retry(f"{STRIPE_API_BASE}/checkout/sessions", body, key)
    return {
        "session_id": raw.get("id", ""),
        "checkout_url": raw.get("url", ""),
        "simulated": False,
        "skip_reason": None,
    }


def retrieve_session(session_id: str, api_key: str | None = None) -> dict[str, Any]:
    """
    Look up a Checkout Session by id — used as a fallback when the success
    page loads before the webhook has landed. Raises StripeAuthError without
    a key.
    """
    key = api_key or _api_key()
    if not key:
        raise StripeAuthError("STRIPE_SECRET_KEY is not configured")

    resp = requests.get(
        f"{STRIPE_API_BASE}/checkout/sessions/{session_id}",
        headers=_headers(key),
        timeout=_TIMEOUT_S,
    )
    if resp.status_code == 401:
        raise StripeAuthError(f"Unauthorized retrieving session {session_id} (key={_redact(key)})")
    if not resp.ok:
        raise StripeError(f"HTTP {resp.status_code} retrieving session {session_id}: {resp.text[:200]}")
    return resp.json()


# ── Webhook signature verification ───────────────────────────────────────────

def verify_webhook_signature(
    payload_bytes: bytes,
    sig_header: str | None,
    webhook_secret: str | None = None,
) -> dict[str, Any]:
    """
    Verify Stripe's Stripe-Signature header per Stripe's documented HMAC-SHA256
    scheme, with replay-protection on the timestamp. Returns the parsed event
    dict on success; raises StripeWebhookError on any failure (missing header,
    unparseable header, expired timestamp, or signature mismatch).
    """
    secret = webhook_secret or _webhook_secret()
    if not secret:
        raise StripeWebhookError("STRIPE_WEBHOOK_SECRET is not configured")
    if not sig_header:
        raise StripeWebhookError("Missing Stripe-Signature header")

    parts: dict[str, list[str]] = {}
    for item in sig_header.split(","):
        if "=" not in item:
            continue
        k, _, v = item.partition("=")
        parts.setdefault(k.strip(), []).append(v.strip())

    timestamps = parts.get("t")
    signatures = parts.get("v1")
    if not timestamps or not signatures:
        raise StripeWebhookError("Malformed Stripe-Signature header")

    timestamp = timestamps[0]
    try:
        ts_int = int(timestamp)
    except ValueError as exc:
        raise StripeWebhookError("Malformed timestamp in Stripe-Signature header") from exc

    if abs(time.time() - ts_int) > _WEBHOOK_TOLERANCE_S:
        raise StripeWebhookError("Webhook timestamp outside tolerance window (possible replay)")

    signed_payload = f"{timestamp}.".encode() + payload_bytes
    expected_sig = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()

    if not any(hmac.compare_digest(expected_sig, sig) for sig in signatures):
        raise StripeWebhookError("Signature mismatch")

    try:
        return json.loads(payload_bytes)
    except ValueError as exc:
        raise StripeWebhookError(f"Signature valid but payload is not valid JSON: {exc}") from exc


def health_check(api_key: str | None = None) -> dict[str, Any]:
    """Cheap reachability/auth check for a connection-status panel."""
    key = api_key or _api_key()
    if not key:
        return {"reachable": False, "error": "STRIPE_SECRET_KEY is not configured"}
    try:
        resp = requests.get(f"{STRIPE_API_BASE}/balance", headers=_headers(key), timeout=10)
        if resp.status_code == 401:
            return {"reachable": False, "error": "Unauthorized — check STRIPE_SECRET_KEY"}
        return {"reachable": True}
    except (requests.Timeout, requests.ConnectionError) as exc:
        return {"reachable": False, "error": f"{type(exc).__name__}: {exc}"}


# ── Low-level HTTP ────────────────────────────────────────────────────────────

def _post_form_retry(url: str, body: dict, api_key: str) -> dict:
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.post(url, data=body, headers=_headers(api_key), timeout=_TIMEOUT_S)
            if resp.status_code in (200, 201):
                return resp.json() if resp.text else {}
            if resp.status_code == _RATE_LIMIT_CODE:
                wait = _backoff(attempt)
                time.sleep(_jitter(wait))
                continue
            if resp.status_code == 401:
                raise StripeAuthError(f"Unauthorized (401): {resp.text[:200]}")
            raise StripeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == _MAX_RETRIES - 1:
                raise StripeError(f"Network failure after {_MAX_RETRIES} retries: {exc}") from exc
            time.sleep(_jitter(_backoff(attempt)))
    raise StripeRateLimitError(f"Rate-limit retries exhausted after {_MAX_RETRIES} attempts")
