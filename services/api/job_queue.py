"""
job_queue.py — SignalForge render job queue abstraction

Thin wrapper around Redis LPUSH / BRPOP for render job handoff between
the API process and the worker process.

Graceful degradation
--------------------
If the ``redis`` package is not installed, or if Redis is unreachable,
every function that writes to the queue returns a no-op result and logs
a warning.  The caller (``/assets/render``) checks the return value and
falls back to synchronous processing when Redis is unavailable.

This design means:
- Tests without a live Redis instance silently fall back to sync mode
  (preserving all existing test expectations).
- Production with Redis gets async queued processing.

Environment variables
---------------------
REDIS_URL    Full Redis connection URL (default: redis://redis:6379)
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

RENDER_QUEUE = "signalforge:render_jobs"
FAILED_QUEUE = "signalforge:render_jobs_failed"


# ---------------------------------------------------------------------------
# Internal connection helper
# ---------------------------------------------------------------------------

def _connect(socket_timeout: float = 5.0):
    """
    Return a connected Redis client, or None if unavailable.

    ``socket_timeout`` controls how long a *non-blocking* read can wait.
    For blocking commands (BRPOP) callers should pass a value larger than
    the BRPOP timeout so the socket does not fire before BRPOP can return.

    Catches both ImportError (package missing) and connection errors so
    callers never have to worry about Redis availability.
    """
    try:
        import redis as _redis  # type: ignore
        url = os.getenv("REDIS_URL", "redis://redis:6379")
        client = _redis.from_url(
            url,
            socket_connect_timeout=2,
            socket_timeout=socket_timeout,
            decode_responses=True,
        )
        client.ping()
        return client
    except ImportError:
        logger.debug("redis package not installed — queue unavailable")
        return None
    except Exception as exc:
        logger.debug("Redis unavailable (%s: %s)", type(exc).__name__, exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_available() -> bool:
    """Return True if Redis is reachable right now."""
    return _connect() is not None


def enqueue_render_job(render_id: str, job_payload: dict) -> Optional[str]:
    """
    Push a render job onto the queue.

    Returns the job_id string on success, or None if Redis is unavailable.
    When None is returned the caller should fall back to synchronous rendering.
    """
    r = _connect()
    if r is None:
        logger.warning(
            "Redis unavailable — render_id=%s will not be queued; "
            "falling back to synchronous processing",
            render_id,
        )
        return None

    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "job_type": "asset_render",
        "render_id": render_id,
        **job_payload,
    }
    r.lpush(RENDER_QUEUE, json.dumps(job))
    logger.info("Enqueued render job job_id=%s render_id=%s", job_id, render_id)
    return job_id


def dequeue_render_job(timeout: int = 5) -> Optional[dict]:
    """
    Block-pop the next render job.

    Returns a parsed dict, or None on timeout / Redis unavailable.
    ``timeout=0`` blocks indefinitely (use only in long-lived worker loops).

    Important: the connection socket_timeout must be > brpop timeout to
    prevent the socket read from racing the BRPOP timeout and raising
    redis.exceptions.TimeoutError instead of returning None.
    """
    # Use socket_timeout strictly larger than the BRPOP timeout so Redis
    # can return None cleanly before the socket read deadline fires.
    r = _connect(socket_timeout=float(timeout) + 3.0)
    if r is None:
        return None
    try:
        result = r.brpop(RENDER_QUEUE, timeout=timeout)
    except Exception as exc:
        # TimeoutError from socket or any other transient error — treat as
        # empty poll so the caller loop can continue.
        logger.debug("dequeue_render_job brpop exception (%s: %s)", type(exc).__name__, exc)
        return None
    if result is None:
        return None
    _key, raw = result
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Malformed job payload discarded: %s", exc)
        return None


def move_to_failed(job: dict) -> None:
    """Push a failed job to the dead-letter queue for manual inspection."""
    r = _connect()
    if r is None:
        return
    r.lpush(FAILED_QUEUE, json.dumps(job))


def queue_depth() -> int:
    """Return the number of pending render jobs (0 if Redis unavailable)."""
    r = _connect()
    if r is None:
        return 0
    return r.llen(RENDER_QUEUE)
