"""
tests/test_stripe_client.py
Pillar 3 — commerce (Stripe Checkout). Pure-unit tests for
services/api/stripe_client.py. No `main` import, no module stubbing —
mirrors tests/test_runway_client.py's pattern, since stripe_client.py is
only imported inline within main.py's route handlers, never at any
module's top level.
"""

import hashlib
import hmac
import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

import stripe_client  # noqa: E402


def _mock_response(status_code=200, json_body=None, text="ok"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    resp.text = text
    resp.json.return_value = json_body if json_body is not None else {}
    return resp


def _sign(payload_bytes: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.".encode() + payload_bytes
    sig = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


class TestUtilities:
    def test_redact_hides_key(self):
        assert stripe_client._redact("sk_test_abcdef1234") == "...1234"

    def test_redact_none_returns_placeholder(self):
        assert stripe_client._redact(None) == "<none>"

    def test_backoff_increases_with_attempts(self):
        assert stripe_client._backoff(0) < stripe_client._backoff(2) <= stripe_client._backoff(4)

    def test_backoff_capped_at_max(self):
        assert stripe_client._backoff(100) == stripe_client._MAX_BACKOFF_S

    def test_headers_use_bearer_auth(self):
        headers = stripe_client._headers("sk_test_123")
        assert headers["Authorization"] == "Bearer sk_test_123"

    def test_exception_hierarchy(self):
        assert issubclass(stripe_client.StripeAuthError, stripe_client.StripeError)
        assert issubclass(stripe_client.StripeRateLimitError, stripe_client.StripeError)
        assert issubclass(stripe_client.StripeWebhookError, stripe_client.StripeError)


class TestCreateCheckoutSession:
    _OFFER = {"_id": "offer1", "title": "Test Asset", "price_cents": 1999, "currency": "usd"}

    def test_disabled_returns_simulated_no_network_call(self):
        with patch.dict(os.environ, {"STRIPE_ENABLED": "false"}), \
             patch("stripe_client.requests.post") as mock_post:
            result = stripe_client.create_checkout_session(
                self._OFFER, "https://x/success", "https://x/cancel", api_key="sk_test_123"
            )
        mock_post.assert_not_called()
        assert result["simulated"] is True
        assert result["checkout_url"].startswith("https://x/success")

    def test_no_key_returns_simulated_no_network_call(self):
        with patch.dict(os.environ, {"STRIPE_ENABLED": "true"}), \
             patch("stripe_client.requests.post") as mock_post:
            result = stripe_client.create_checkout_session(
                self._OFFER, "https://x/success", "https://x/cancel", api_key=""
            )
        mock_post.assert_not_called()
        assert result["simulated"] is True

    def test_enabled_with_key_posts_correct_line_item(self):
        resp = _mock_response(200, {"id": "cs_test_1", "url": "https://checkout.stripe.com/cs_test_1"})
        with patch.dict(os.environ, {"STRIPE_ENABLED": "true"}), \
             patch("stripe_client.requests.post", return_value=resp) as mock_post:
            result = stripe_client.create_checkout_session(
                self._OFFER, "https://x/success", "https://x/cancel", api_key="sk_test_123"
            )
        assert result["simulated"] is False
        assert result["session_id"] == "cs_test_1"
        assert result["checkout_url"] == "https://checkout.stripe.com/cs_test_1"
        sent_body = mock_post.call_args.kwargs["data"]
        assert sent_body["mode"] == "payment"
        assert sent_body["line_items[0][price_data][currency]"] == "usd"
        assert sent_body["line_items[0][price_data][unit_amount]"] == "1999"
        assert sent_body["line_items[0][price_data][product_data][name]"] == "Test Asset"
        assert sent_body["metadata[offer_id]"] == "offer1"
        sent_headers = mock_post.call_args.kwargs["headers"]
        assert sent_headers["Authorization"] == "Bearer sk_test_123"

    def test_401_raises_auth_error(self):
        resp = _mock_response(401, text="unauthorized")
        with patch.dict(os.environ, {"STRIPE_ENABLED": "true"}), \
             patch("stripe_client.requests.post", return_value=resp):
            with pytest.raises(stripe_client.StripeAuthError):
                stripe_client.create_checkout_session(
                    self._OFFER, "https://x/success", "https://x/cancel", api_key="bad-key"
                )

    def test_429_retries_then_succeeds(self):
        rate_limited = _mock_response(429, text="slow down")
        success = _mock_response(200, {"id": "cs_test_2", "url": "https://checkout.stripe.com/cs_test_2"})
        with patch.dict(os.environ, {"STRIPE_ENABLED": "true"}), \
             patch("stripe_client.requests.post", side_effect=[rate_limited, success]), \
             patch("stripe_client.time.sleep"):
            result = stripe_client.create_checkout_session(
                self._OFFER, "https://x/success", "https://x/cancel", api_key="sk_test_123"
            )
        assert result["session_id"] == "cs_test_2"

    def test_key_never_appears_in_error(self):
        resp = _mock_response(500, text="server error")
        with patch.dict(os.environ, {"STRIPE_ENABLED": "true"}), \
             patch("stripe_client.requests.post", return_value=resp):
            with pytest.raises(stripe_client.StripeError) as exc_info:
                stripe_client.create_checkout_session(
                    self._OFFER, "https://x/success", "https://x/cancel", api_key="sk_test_super_secret"
                )
        assert "sk_test_super_secret" not in str(exc_info.value)


class TestRetrieveSession:
    def test_raises_auth_error_without_key(self):
        with pytest.raises(stripe_client.StripeAuthError):
            stripe_client.retrieve_session("cs_test_1", api_key="")

    def test_success_returns_session_dict(self):
        resp = _mock_response(200, {"id": "cs_test_1", "payment_status": "paid"})
        with patch("stripe_client.requests.get", return_value=resp):
            result = stripe_client.retrieve_session("cs_test_1", api_key="sk_test_123")
        assert result["payment_status"] == "paid"


class TestWebhookSignatureVerification:
    SECRET = "whsec_test_secret"

    def test_valid_signature_accepted(self):
        payload = json.dumps({"type": "checkout.session.completed", "data": {"object": {"id": "cs_1"}}}).encode()
        sig = _sign(payload, self.SECRET)
        event = stripe_client.verify_webhook_signature(payload, sig, webhook_secret=self.SECRET)
        assert event["type"] == "checkout.session.completed"

    def test_missing_header_rejected(self):
        payload = b'{"type": "checkout.session.completed"}'
        with pytest.raises(stripe_client.StripeWebhookError):
            stripe_client.verify_webhook_signature(payload, None, webhook_secret=self.SECRET)

    def test_tampered_payload_rejected(self):
        payload = json.dumps({"type": "checkout.session.completed"}).encode()
        sig = _sign(payload, self.SECRET)
        tampered_payload = json.dumps({"type": "checkout.session.completed", "evil": True}).encode()
        with pytest.raises(stripe_client.StripeWebhookError):
            stripe_client.verify_webhook_signature(tampered_payload, sig, webhook_secret=self.SECRET)

    def test_wrong_secret_rejected(self):
        payload = json.dumps({"type": "checkout.session.completed"}).encode()
        sig = _sign(payload, "whsec_wrong_secret")
        with pytest.raises(stripe_client.StripeWebhookError):
            stripe_client.verify_webhook_signature(payload, sig, webhook_secret=self.SECRET)

    def test_expired_timestamp_rejected(self):
        payload = json.dumps({"type": "checkout.session.completed"}).encode()
        old_timestamp = int(time.time()) - 999999
        sig = _sign(payload, self.SECRET, timestamp=old_timestamp)
        with pytest.raises(stripe_client.StripeWebhookError):
            stripe_client.verify_webhook_signature(payload, sig, webhook_secret=self.SECRET)

    def test_no_webhook_secret_configured_rejected(self):
        payload = json.dumps({"type": "checkout.session.completed"}).encode()
        sig = _sign(payload, self.SECRET)
        with pytest.raises(stripe_client.StripeWebhookError):
            stripe_client.verify_webhook_signature(payload, sig, webhook_secret="")


class TestHealthCheck:
    def test_no_key_unreachable(self):
        result = stripe_client.health_check(api_key="")
        assert result["reachable"] is False

    def test_401_unreachable(self):
        resp = _mock_response(401)
        with patch("stripe_client.requests.get", return_value=resp):
            result = stripe_client.health_check(api_key="bad-key")
        assert result["reachable"] is False

    def test_200_is_reachable(self):
        resp = _mock_response(200, {"object": "balance"})
        with patch("stripe_client.requests.get", return_value=resp):
            result = stripe_client.health_check(api_key="sk_test_123")
        assert result["reachable"] is True
