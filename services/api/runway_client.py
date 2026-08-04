"""
runway_client.py — Retry-safe Runway Developer API client for SignalForge.

Responsibilities:
  - Text-to-image submission via the Runway Developer API
  - Async task polling (submit -> poll -> download), same shape as this
    codebase's comfyui_client.py against ComfyUI's /prompt + /history + /view
  - run_scene_beats() matching ComfyUIClient.run_scene_beats()'s exact
    signature and return contract, so it is a drop-in alternative image
    source for services/api/worker.py's render pipeline
  - Rate-limit handling, exponential retry with jitter
  - Structured, key-redacted logging

Note: the Runway MCP tools available to a Claude session are scoped to that
session — they are not something this backend/worker process can call. This
client makes real HTTP calls to the Runway Developer API
(https://api.dev.runwayml.com) using RUNWAY_API_KEY, a developer key obtained
separately from https://dev.runwayml.com — a different credential than any
MCP/consumer connection.

This module is intentionally dependency-light (only stdlib + requests).
It is imported by worker.py; do not import worker or main from here.
"""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any

import requests

logger = logging.getLogger("signalforge.runway")

# ── Configuration ─────────────────────────────────────────────────────────────

RUNWAY_API_KEY     = os.getenv("RUNWAY_API_KEY", "")
RUNWAY_IMAGE_MODEL = os.getenv("RUNWAY_IMAGE_MODEL", "gen4_image")
RUNWAY_IMAGE_RATIO = os.getenv("RUNWAY_IMAGE_RATIO", "1080:1920")

RUNWAY_API_BASE     = "https://api.dev.runwayml.com"
RUNWAY_API_VERSION  = "2024-11-06"  # required X-Runway-Version header

# Retry / poll settings
_MAX_RETRIES       = 4
_BASE_BACKOFF_S    = 1.0
_MAX_BACKOFF_S     = 30.0
_RATE_LIMIT_CODE   = 429
_POLL_INTERVAL_S   = 5.0
_DEFAULT_TIMEOUT_S = 180.0

_TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "CANCELED"}


# ── Utilities ─────────────────────────────────────────────────────────────────

def _redact(key: str | None) -> str:
    """Return last-4 chars with prefix; safe for logs."""
    if not key:
        return "<none>"
    return f"...{key[-4:]}"


def _jitter(base: float) -> float:
    return base * (0.75 + random.random() * 0.5)


def _backoff(attempt: int) -> float:
    return min(_MAX_BACKOFF_S, _BASE_BACKOFF_S * (2 ** attempt))


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Runway-Version": RUNWAY_API_VERSION,
    }


# ── Exceptions ────────────────────────────────────────────────────────────────

class RunwayError(Exception):
    """Base class for all Runway client errors."""


class RunwayAuthError(RunwayError):
    """Missing/invalid API key."""


class RunwayGenerationError(RunwayError):
    """Task submission or execution failed."""


class RunwayTimeoutError(RunwayGenerationError):
    """Polling exceeded the configured timeout without reaching a terminal status."""


class RunwayRateLimitError(RunwayGenerationError):
    """Rate limit retries exhausted."""


# ── Low-level API calls ────────────────────────────────────────────────────────

def submit_text_to_image(
    prompt_text: str,
    api_key: str | None = None,
    model: str | None = None,
    ratio: str | None = None,
) -> str:
    """
    Submit a text-to-image generation task.

    Returns the task id. Raises RunwayAuthError if no API key is configured,
    RunwayGenerationError on submission failure.
    """
    key = api_key or RUNWAY_API_KEY
    if not key:
        raise RunwayAuthError("RUNWAY_API_KEY is not configured")

    body = {
        "promptText": prompt_text,
        "model": model or RUNWAY_IMAGE_MODEL,
        "ratio": ratio or RUNWAY_IMAGE_RATIO,
    }
    resp = _post_json_retry(f"{RUNWAY_API_BASE}/v1/text_to_image", body, key)
    task_id = resp.get("id", "")
    if not task_id:
        raise RunwayGenerationError(f"Task submission returned no id: {resp}")
    logger.info("Runway text_to_image submitted task_id=%s key=%s", task_id, _redact(key))
    return task_id


def poll_task(
    task_id: str,
    api_key: str | None = None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    poll_interval_s: float = _POLL_INTERVAL_S,
) -> dict[str, Any]:
    """
    Poll GET /v1/tasks/{id} until a terminal status (SUCCEEDED/FAILED/CANCELED)
    or timeout_s elapses. Returns the raw task dict.

    Raises RunwayTimeoutError past the deadline, RunwayAuthError without a key.
    """
    key = api_key or RUNWAY_API_KEY
    if not key:
        raise RunwayAuthError("RUNWAY_API_KEY is not configured")

    deadline = time.monotonic() + timeout_s
    while True:
        resp = requests.get(
            f"{RUNWAY_API_BASE}/v1/tasks/{task_id}",
            headers=_headers(key),
            timeout=20,
        )
        if resp.status_code == 401:
            raise RunwayAuthError(f"Unauthorized polling task {task_id} (key={_redact(key)})")
        if not resp.ok:
            raise RunwayGenerationError(f"HTTP {resp.status_code} polling task {task_id}: {resp.text[:200]}")

        task = resp.json()
        status = task.get("status", "")
        if status in _TERMINAL_STATUSES:
            return task

        if time.monotonic() >= deadline:
            raise RunwayTimeoutError(
                f"Task {task_id} did not reach a terminal status within {timeout_s}s "
                f"(last status: {status!r})"
            )
        time.sleep(poll_interval_s)


def download_image(url: str, dest_path: str) -> str:
    """
    Stream-download a (signed) Runway output URL to a local file path.
    Returns dest_path on success. Raises RunwayGenerationError on failure.
    """
    try:
        resp = requests.get(url, stream=True, timeout=60)
        if not resp.ok:
            raise RunwayGenerationError(f"HTTP {resp.status_code} downloading output: {url[:100]}")
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    fh.write(chunk)
        return dest_path
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise RunwayGenerationError(f"Network failure downloading output: {exc}") from exc


def health_check(api_key: str | None = None) -> dict[str, Any]:
    """
    Cheap reachability/auth check — same role as ComfyUIClient.health_check()
    at the worker.py call site that decides whether to proceed or fall back.
    """
    key = api_key or RUNWAY_API_KEY
    if not key:
        return {"reachable": False, "error": "RUNWAY_API_KEY is not configured"}
    try:
        # Cheapest authenticated call available: fetch a bogus task id.
        # A well-formed 404 (not 401) confirms the key + host are valid.
        resp = requests.get(
            f"{RUNWAY_API_BASE}/v1/tasks/healthcheck-nonexistent-id",
            headers=_headers(key),
            timeout=10,
        )
        if resp.status_code == 401:
            return {"reachable": False, "error": "Unauthorized — check RUNWAY_API_KEY"}
        return {"reachable": True}
    except (requests.Timeout, requests.ConnectionError) as exc:
        return {"reachable": False, "error": f"{type(exc).__name__}: {exc}"}


def _post_json_retry(url: str, body: dict, api_key: str) -> dict:
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.post(url, json=body, headers=_headers(api_key), timeout=20)
            if resp.status_code in (200, 201):
                return resp.json() if resp.text else {}
            if resp.status_code == _RATE_LIMIT_CODE:
                wait = _backoff(attempt)
                logger.warning("Runway rate-limited attempt=%d wait=%.1fs key=%s",
                               attempt, wait, _redact(api_key))
                time.sleep(_jitter(wait))
                continue
            if resp.status_code == 401:
                raise RunwayAuthError(f"Unauthorized (401): {resp.text[:200]}")
            raise RunwayGenerationError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == _MAX_RETRIES - 1:
                raise RunwayGenerationError(f"Network failure after {_MAX_RETRIES} retries: {exc}") from exc
            wait = _backoff(attempt)
            logger.warning("Runway network error attempt=%d retrying in %.1fs err=%s",
                           attempt, wait, exc)
            time.sleep(_jitter(wait))
    raise RunwayRateLimitError(f"Rate-limit retries exhausted after {_MAX_RETRIES} attempts")


# ── High-level client: drop-in image source for the render worker ─────────────

class RunwayClient:
    """
    Image-generation backend for services/api/worker.py's render pipeline.

    run_scene_beats() mirrors ComfyUIClient.run_scene_beats()'s signature and
    return-dict contract exactly, so worker.py's orchestration code (which
    reads output_image_paths/renderer_type/model_name/etc.) needs no changes
    beyond selecting which client to instantiate.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or RUNWAY_API_KEY

    def health_check(self) -> dict[str, Any]:
        return health_check(self.api_key)

    def run_scene_beats(
        self,
        pg: dict[str, Any],
        render_id: str,
        output_dir: str = "",
        ratio: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate one image per scene beat (or one image from the main prompt
        when scene_beats is absent/empty — same fallback rule as ComfyUI's
        version). Returns the same dict shape as
        ComfyUIClient.run_scene_beats().

        ratio: optional per-call override (e.g. "720:1280" for the cheaper
        720p tier); falls back to RUNWAY_IMAGE_RATIO when None.
        """
        out_dir = output_dir or os.getenv("FFMPEG_OUTPUT_DIR", "/tmp/signalforge_renders")
        os.makedirs(out_dir, exist_ok=True)

        if not self.api_key:
            return {
                "output_image_paths": [],
                "output_image_path": "",
                "prompt_ids": [],
                "errors": ["RUNWAY_API_KEY is not configured"],
                "renderer_type": "runway_real",
                "workflow_path": "",
                "model_name": RUNWAY_IMAGE_MODEL,
                "fallback_used": True,
                "fallback_reason": "missing_api_key",
                "simulation_only": True,
                "outbound_actions_taken": 0,
            }

        # Reuse comfyui_client.py's prompt composition so both engines enforce
        # the same faceless/no-identifiable-likeness safety language from a
        # single source of truth, rather than duplicating that logic here.
        from comfyui_client import _build_positive_text, _FACELESS_SUFFIX  # noqa: PLC0415

        scene_beats: list[str] = pg.get("scene_beats") or []
        if scene_beats:
            prompts = []
            for beat_text in scene_beats:
                base = ", ".join(
                    p for p in (
                        beat_text.strip(),
                        (pg.get("visual_style") or "").strip(),
                        (pg.get("lighting") or "").strip(),
                    ) if p
                )
                prompts.append(f"{base}, {_FACELESS_SUFFIX}")
        else:
            prompts = [_build_positive_text(pg)]

        output_image_paths: list[str] = []
        task_ids: list[str] = []
        errors: list[str] = []

        for idx, prompt_text in enumerate(prompts):
            if not prompt_text:
                errors.append(f"beat {idx}: empty prompt text")
                continue
            try:
                task_id = submit_text_to_image(prompt_text, api_key=self.api_key, ratio=ratio)
                task_ids.append(task_id)
                task = poll_task(task_id, api_key=self.api_key)
                if task.get("status") != "SUCCEEDED":
                    errors.append(f"beat {idx}: task {task_id} ended with status {task.get('status')!r}")
                    continue
                output_urls = task.get("output") or []
                if not output_urls:
                    errors.append(f"beat {idx}: task {task_id} succeeded with no output")
                    continue
                dest_path = os.path.join(out_dir, f"runway_{render_id}_{idx}.png")
                download_image(output_urls[0], dest_path)
                output_image_paths.append(dest_path)
            except RunwayError as exc:
                errors.append(f"beat {idx}: {type(exc).__name__}: {exc}")

        fallback_used = bool(errors) and not output_image_paths
        return {
            "output_image_paths": output_image_paths,
            "output_image_path": output_image_paths[0] if output_image_paths else "",
            "prompt_ids": task_ids,
            "errors": errors,
            "renderer_type": "runway_real",
            "workflow_path": "",
            "model_name": RUNWAY_IMAGE_MODEL,
            "fallback_used": fallback_used,
            "fallback_reason": "; ".join(errors) if fallback_used else "",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
