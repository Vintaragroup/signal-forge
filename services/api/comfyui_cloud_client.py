"""
comfyui_cloud_client.py — SignalForge Comfy Cloud renderer adapter (Phase 11)

renderer_type: comfyui_cloud

This module implements the official Comfy Cloud API adapter.
It does NOT replace the local stub or real ComfyUI paths — it is an additional
renderer backend selected when COMFY_CLOUD_ENABLED=true.

Safety guarantees (always enforced)
-------------------------------------
- simulation_only: True on all results
- outbound_actions_taken: 0 always
- No face generation (faceless suffix always appended)
- No voice cloning, no avatar, no publishing
- All outputs land at status=needs_review
- API key is NEVER logged, returned in diagnostics, committed, or shown in UI

Comfy Cloud API style (official)
-----------------------------------
  POST {BASE_URL}/api/prompt          {"prompt": workflow}
  X-API-Key: <key>                    header for all requests
  GET  {BASE_URL}/api/job/{id}/status  poll for completion
  GET  {BASE_URL}/api/jobs/{id}        fetch full job result
  GET  {BASE_URL}/api/view?filename=...  download output image

Environment variables
-----------------------
COMFY_CLOUD_ENABLED          false   — master switch
COMFY_CLOUD_BASE_URL         https://cloud.comfy.org
COMFY_CLOUD_API_KEY          (secret — never log or expose)
COMFY_CLOUD_WORKFLOW_PATH    path to ComfyUI API-format workflow JSON
COMFY_CLOUD_PROVIDER         official
COMFY_CLOUD_TIMEOUT_SECONDS  600     — max seconds to wait for job completion
COMFY_CLOUD_FALLBACK_ALLOWED false   — allow falling back to stub on error

COMFY_MCP_ENABLED            false
COMFY_MCP_URL                https://cloud.comfy.org/mcp
COMFY_MCP_API_KEY            (secret — never log or expose)
COMFY_MCP_VALIDATION_ONLY    true
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

# Reuse the shared faceless safety constants
try:
    from comfyui_client import (  # type: ignore
        _FACELESS_SUFFIX,
        _SAFETY_NEGATIVE,
        _build_positive_text,
        load_real_workflow,
    )
except ImportError:
    _FACELESS_SUFFIX = (
        "no faces, no identifiable people, no avatars, faceless, "
        "cinematic B-roll, symbolic leadership imagery, vertical 9:16"
    )
    _SAFETY_NEGATIVE = (
        "realistic face, recognizable likeness, identifiable person, avatar, "
        "voice cloning, nsfw, explicit, watermark, text overlay, low quality, blurry"
    )

    def _build_positive_text(pg: dict) -> str:
        parts = []
        for field in ("positive_prompt", "visual_style", "lighting", "camera_direction"):
            val = (pg.get(field) or "").strip()
            if val:
                parts.append(val)
        base = ", ".join(parts) or "abstract digital art, cinematic, high contrast"
        if "no faces" not in base:
            return f"{base}, {_FACELESS_SUFFIX}"
        return base

    def load_real_workflow(pg: dict, workflow_path: str, **kwargs) -> dict:  # type: ignore[misc]
        raise ValueError(f"comfyui_client not available — cannot load workflow from {workflow_path!r}")


_DEFAULT_BASE_URL = "https://cloud.comfy.org"
_DEFAULT_TIMEOUT_S = 600
_POLL_INTERVAL_S = 5.0
_CONNECT_TIMEOUT_S = 15
_DOWNLOAD_TIMEOUT_S = 60
_RENDERER_TYPE = "comfyui_cloud"

# ---------------------------------------------------------------------------
# Node type classification
# ---------------------------------------------------------------------------

_VIDEO_OUTPUT_NODE_TYPES: frozenset[str] = frozenset({
    "VHS_VideoCombine",
    "AnimateDiffCombine",
    "ADE_AnimateDiffCombine",
})

_IMAGE_OUTPUT_NODE_TYPES: frozenset[str] = frozenset({
    "SaveImage",
    "SaveImageWebsocket",
    "PreviewImage",
})

_ANIMATEDIFF_LOADER_NODE_TYPES: frozenset[str] = frozenset({
    "ADE_AnimateDiffLoaderWithContext",
    "AnimateDiffLoader",
    "AnimateDiffLoaderWithContext",
    "ADE_AnimateDiffUniformContextOptions",
})

_VIDEO_EXTENSIONS: frozenset[str] = frozenset({".mp4", ".webm", ".mov", ".avi", ".gif"})
_IMAGE_EXTENSIONS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".webp"})


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def _env_bool(key: str, default: bool = False) -> bool:
    return str(os.getenv(key, "true" if default else "false")).strip().lower() in (
        "1", "true", "yes", "on"
    )


def _api_key_configured(key_env: str) -> bool:
    """Return True if the API key env var is set and non-empty. Never return the key itself."""
    val = os.getenv(key_env, "").strip()
    return bool(val)


def _get_base_url() -> str:
    return os.getenv("COMFY_CLOUD_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def _get_timeout() -> int:
    try:
        return int(os.getenv("COMFY_CLOUD_TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT_S)))
    except (ValueError, TypeError):
        return _DEFAULT_TIMEOUT_S


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def cloud_diagnostics() -> dict[str, Any]:
    """
    Return Comfy Cloud configuration status.

    IMPORTANT: Never returns the API key value.
    Only returns configured=True/False.
    """
    enabled = _env_bool("COMFY_CLOUD_ENABLED")
    api_key_configured = _api_key_configured("COMFY_CLOUD_API_KEY")
    workflow_path = os.getenv("COMFY_CLOUD_WORKFLOW_PATH", "").strip()
    base_url = _get_base_url()
    provider = os.getenv("COMFY_CLOUD_PROVIDER", "official")
    timeout = _get_timeout()
    fallback_allowed = _env_bool("COMFY_CLOUD_FALLBACK_ALLOWED")

    workflow_exists = bool(workflow_path and os.path.isfile(workflow_path))

    errors: list[str] = []
    warnings: list[str] = []

    if not enabled:
        errors.append("COMFY_CLOUD_ENABLED is false — Comfy Cloud renderer is disabled.")
    if not api_key_configured:
        errors.append(
            "COMFY_CLOUD_API_KEY is not set. "
            "A Comfy Cloud subscription and API key are required for cloud rendering."
        )
    if not workflow_path:
        errors.append(
            "COMFY_CLOUD_WORKFLOW_PATH is not set. "
            "Provide a ComfyUI API-format workflow JSON file with "
            "{{positive_prompt}} / {{negative_prompt}} markers."
        )
    elif not workflow_exists:
        errors.append(
            f"COMFY_CLOUD_WORKFLOW_PATH={workflow_path!r} does not exist."
        )

    ready = enabled and api_key_configured and workflow_exists and len(errors) == 0

    # MCP status
    mcp_enabled = _env_bool("COMFY_MCP_ENABLED")
    mcp_url = os.getenv("COMFY_MCP_URL", "https://cloud.comfy.org/mcp")
    mcp_key_configured = _api_key_configured("COMFY_MCP_API_KEY")
    mcp_validation_only = _env_bool("COMFY_MCP_VALIDATION_ONLY", default=True)

    return {
        "renderer_type": _RENDERER_TYPE,
        "enabled": enabled,
        "api_key_configured": api_key_configured,   # True/False only — key never returned
        "base_url": base_url,
        "provider": provider,
        "workflow_path": workflow_path,
        "workflow_exists": workflow_exists,
        "timeout_seconds": timeout,
        "fallback_allowed": fallback_allowed,
        "ready": ready,
        "errors": errors,
        "warnings": warnings,
        "mcp": {
            "enabled": mcp_enabled,
            "url": mcp_url,
            "api_key_configured": mcp_key_configured,
            "validation_only": mcp_validation_only,
        },
        "simulation_only": True,
        "outbound_actions_taken": 0,
    }


# ---------------------------------------------------------------------------
# Renderer validation
# ---------------------------------------------------------------------------

def validate_cloud_renderer() -> dict[str, Any]:
    """
    Validate the cloud renderer is fully configured.

    Returns:
        valid           bool
        renderer_type   str
        errors          list[str]
        warnings        list[str]
        blocked_reason  str — human-readable reason if blocked
    """
    diag = cloud_diagnostics()
    blocked_reason = ""

    if not diag["enabled"]:
        blocked_reason = "Comfy Cloud subscription/API key required — COMFY_CLOUD_ENABLED=false"
    elif not diag["api_key_configured"]:
        blocked_reason = "Comfy Cloud subscription/API key required — COMFY_CLOUD_API_KEY not set"
    elif not diag["workflow_path"]:
        blocked_reason = "COMFY_CLOUD_WORKFLOW_PATH not configured"
    elif not diag["workflow_exists"]:
        blocked_reason = f"Workflow file not found: {diag['workflow_path']!r}"

    return {
        "valid": diag["ready"],
        "renderer_type": _RENDERER_TYPE,
        "errors": diag["errors"],
        "warnings": diag["warnings"],
        "blocked_reason": blocked_reason,
    }


# ---------------------------------------------------------------------------
# Workflow output type detection (Phase 12)
# ---------------------------------------------------------------------------

def detect_workflow_output_types(workflow: dict[str, Any]) -> dict[str, Any]:
    """
    Inspect a workflow dict for known output node types and motion loader nodes.

    Returns:
        has_video_nodes     bool
        has_image_nodes     bool
        has_animatediff     bool
        video_node_ids      list[str]
        image_node_ids      list[str]
        motion_model_names  list[str]
        checkpoint_names    list[str]
    """
    video_node_ids: list[str] = []
    image_node_ids: list[str] = []
    motion_model_names: list[str] = []
    checkpoint_names: list[str] = []
    has_animatediff = False

    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")

        if class_type in _VIDEO_OUTPUT_NODE_TYPES:
            video_node_ids.append(str(node_id))
        if class_type in _IMAGE_OUTPUT_NODE_TYPES:
            image_node_ids.append(str(node_id))
        if class_type in _ANIMATEDIFF_LOADER_NODE_TYPES:
            has_animatediff = True
            model_name = (node.get("inputs") or {}).get("model_name", "")
            if model_name:
                motion_model_names.append(str(model_name))
        if class_type == "CheckpointLoaderSimple":
            ckpt = (node.get("inputs") or {}).get("ckpt_name", "")
            if ckpt:
                checkpoint_names.append(str(ckpt))

    return {
        "has_video_nodes": bool(video_node_ids),
        "has_image_nodes": bool(image_node_ids),
        "has_animatediff": has_animatediff,
        "video_node_ids": video_node_ids,
        "image_node_ids": image_node_ids,
        "motion_model_names": motion_model_names,
        "checkpoint_names": checkpoint_names,
    }


def validate_animatediff_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    """
    Validate that a workflow has required AnimateDiff / VHS nodes.

    Fails clearly if video output nodes are missing.
    Does NOT silently substitute alternate paths.

    Returns:
        valid               bool
        has_video_nodes     bool
        has_image_nodes     bool
        has_animatediff     bool
        video_node_ids      list[str]
        image_node_ids      list[str]
        motion_model_names  list[str]
        checkpoint_names    list[str]
        errors              list[str]
        warnings            list[str]
    """
    info = detect_workflow_output_types(workflow)
    errors: list[str] = []
    warnings: list[str] = []

    if not info["has_video_nodes"]:
        node_names = ", ".join(sorted(_VIDEO_OUTPUT_NODE_TYPES))
        errors.append(
            f"Workflow has no video output nodes ({node_names}). "
            "Cannot produce direct video output. "
            "Add a VHS_VideoCombine or AnimateDiffCombine node."
        )
    if not info["has_animatediff"] and info["has_video_nodes"]:
        warnings.append(
            "No AnimateDiff loader node found — video output may lack motion. "
            "Expected: ADE_AnimateDiffLoaderWithContext or AnimateDiffLoader."
        )
    if info["has_animatediff"] and not info["motion_model_names"]:
        warnings.append(
            "AnimateDiff loader node found but no motion model name detected. "
            "Verify model_name input is set correctly."
        )

    return {
        "valid": len(errors) == 0,
        "has_video_nodes": info["has_video_nodes"],
        "has_image_nodes": info["has_image_nodes"],
        "has_animatediff": info["has_animatediff"],
        "video_node_ids": info["video_node_ids"],
        "image_node_ids": info["image_node_ids"],
        "motion_model_names": info["motion_model_names"],
        "checkpoint_names": info["checkpoint_names"],
        "errors": errors,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Workflow helpers
# ---------------------------------------------------------------------------

def load_cloud_workflow(
    pg: dict[str, Any],
    workflow_path: str,
    positive_override: str = "",
    negative_override: str = "",
    force_portrait: bool = True,
) -> dict[str, Any]:
    """
    Load a ComfyUI API-format workflow JSON and inject prompts for cloud submission.

    Delegates to comfyui_client.load_real_workflow for injection logic
    (reuses the same {{positive_prompt}} / {{negative_prompt}} marker system).

    Raises ValueError on load failure.
    """
    return load_real_workflow(
        pg,
        workflow_path,
        positive_override=positive_override,
        negative_override=negative_override,
        force_portrait=force_portrait,
    )


def inject_cloud_workflow_inputs(
    workflow: dict[str, Any],
    positive_prompt: str,
    negative_prompt: str,
    force_portrait: bool = True,
) -> dict[str, Any]:
    """
    Inject prompts directly into an already-loaded workflow dict.
    Useful when the workflow is provided as a dict rather than a file path.

    Applies {{positive_prompt}} / {{negative_prompt}} marker substitution
    and patches EmptyLatentImage to portrait (1080×1920) if force_portrait=True.
    """
    # Enforce safety negatives
    if _SAFETY_NEGATIVE not in negative_prompt:
        negative_prompt = f"{negative_prompt}, {_SAFETY_NEGATIVE}" if negative_prompt else _SAFETY_NEGATIVE

    clip_nodes = [
        (node_id, node)
        for node_id, node in workflow.items()
        if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode"
    ]

    positive_injected = False
    negative_injected = False

    for node_id, node in clip_nodes:
        text = str(node.get("inputs", {}).get("text", ""))
        if "{{positive_prompt}}" in text:
            workflow[node_id]["inputs"]["text"] = positive_prompt
            positive_injected = True
        elif "{{negative_prompt}}" in text:
            workflow[node_id]["inputs"]["text"] = negative_prompt
            negative_injected = True

    if not positive_injected and clip_nodes:
        workflow[clip_nodes[0][0]]["inputs"]["text"] = positive_prompt
    if not negative_injected and len(clip_nodes) > 1:
        workflow[clip_nodes[1][0]]["inputs"]["text"] = negative_prompt

    if force_portrait:
        for node_id, node in workflow.items():
            if isinstance(node, dict) and node.get("class_type") == "EmptyLatentImage":
                workflow[node_id]["inputs"]["width"] = 1080
                workflow[node_id]["inputs"]["height"] = 1920

    return workflow


# ---------------------------------------------------------------------------
# HTTP client for Comfy Cloud
# ---------------------------------------------------------------------------

class ComfyCloudClient:
    """
    HTTP client for the official Comfy Cloud API.

    The API key is read from COMFY_CLOUD_API_KEY at construction time.
    It is stored in memory only and never logged or returned.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or _get_base_url()).rstrip("/")
        # Store key reference but never expose it
        self._api_key = os.getenv("COMFY_CLOUD_API_KEY", "").strip()

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-API-Key": self._api_key,
        }

    def _request(
        self,
        method: str,
        path: str,
        data: bytes | None = None,
        timeout: int = _CONNECT_TIMEOUT_S,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(
            url,
            data=data,
            headers=self._auth_headers(),
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            raise ComfyCloudError(
                f"HTTP {exc.code} {exc.reason} from {path}: {body}"
            ) from exc
        except Exception as exc:
            raise ComfyCloudError(
                f"{type(exc).__name__} calling {method} {path}: {exc}"
            ) from exc

    def health_check(self) -> dict[str, Any]:
        """Check if the Comfy Cloud endpoint is reachable. Does not require valid API key."""
        try:
            req = urllib.request.Request(
                f"{self.base_url}/",
                headers={"Accept": "application/json"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=_CONNECT_TIMEOUT_S) as resp:
                return {"reachable": True, "status_code": resp.status}
        except Exception as exc:
            return {"reachable": False, "error": f"{type(exc).__name__}: {exc}"}

    def submit_workflow(self, workflow: dict[str, Any]) -> dict[str, Any]:
        """
        POST /api/prompt — submit a workflow to Comfy Cloud.

        Returns the response dict containing prompt_id.
        Raises ComfyCloudError on failure.
        """
        payload = json.dumps({"prompt": workflow}).encode()
        return self._request("POST", "/api/prompt", data=payload, timeout=_CONNECT_TIMEOUT_S)

    def poll_job_status(self, prompt_id: str) -> dict[str, Any]:
        """
        GET /api/job/{prompt_id}/status — poll for job completion.

        Returns the status dict. Raises ComfyCloudError on failure.
        """
        return self._request("GET", f"/api/job/{prompt_id}/status", timeout=_CONNECT_TIMEOUT_S)

    def fetch_job_outputs(self, prompt_id: str) -> dict[str, Any]:
        """
        GET /api/jobs/{prompt_id} — fetch full job result including output references.

        Returns the full job dict. Raises ComfyCloudError on failure.
        """
        return self._request("GET", f"/api/jobs/{prompt_id}", timeout=_CONNECT_TIMEOUT_S)

    def download_output(self, filename: str, subfolder: str = "", output_type: str = "output") -> bytes:
        """
        GET /api/view?filename=...&subfolder=...&type=...
        Download raw image bytes. Follows redirects via urllib.

        Raises ComfyCloudError on failure.
        """
        params = urllib.parse.urlencode(
            {"filename": filename, "subfolder": subfolder, "type": output_type}
        )
        url = f"{self.base_url}/api/view?{params}"
        req = urllib.request.Request(
            url,
            headers={k: v for k, v in self._auth_headers().items() if k != "Content-Type"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT_S) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            raise ComfyCloudError(
                f"HTTP {exc.code} downloading {filename}: {exc.reason}"
            ) from exc
        except Exception as exc:
            raise ComfyCloudError(
                f"{type(exc).__name__} downloading {filename}: {exc}"
            ) from exc


class ComfyCloudError(Exception):
    """Raised for Comfy Cloud API errors."""


# ---------------------------------------------------------------------------
# High-level operations
# ---------------------------------------------------------------------------

def submit_cloud_workflow(
    client: ComfyCloudClient,
    workflow: dict[str, Any],
) -> str:
    """
    Submit a workflow to Comfy Cloud and return the prompt_id.

    Raises ComfyCloudError if submission fails or no prompt_id returned.
    """
    resp = client.submit_workflow(workflow)
    prompt_id = resp.get("prompt_id") or resp.get("id") or ""
    if not prompt_id:
        raise ComfyCloudError(
            f"No prompt_id in Comfy Cloud submit response: {resp}"
        )
    return str(prompt_id)


def poll_cloud_job(
    client: ComfyCloudClient,
    prompt_id: str,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """
    Poll GET /api/job/{prompt_id}/status until completed, failed, or timeout.

    Returns the final status dict.
    Raises ComfyCloudError on HTTP failure.
    Raises TimeoutError if the job doesn't complete within timeout_seconds.
    """
    timeout = timeout_seconds if timeout_seconds is not None else _get_timeout()
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        status_resp = client.poll_job_status(prompt_id)

        status = str(status_resp.get("status", "")).lower()
        if status in ("completed", "success", "done", "finished"):
            return status_resp
        if status in ("failed", "error", "cancelled"):
            raise ComfyCloudError(
                f"Comfy Cloud job {prompt_id} failed with status={status!r}: "
                f"{status_resp.get('error', '')}"
            )

        time.sleep(_POLL_INTERVAL_S)

    raise TimeoutError(
        f"Comfy Cloud job {prompt_id} did not complete within {timeout}s"
    )


def fetch_cloud_job_outputs(
    client: ComfyCloudClient,
    prompt_id: str,
) -> list[dict[str, Any]]:
    """
    GET /api/jobs/{prompt_id} and extract output references.

    Returns a list of dicts with at minimum: filename, subfolder, type.
    Each ref also contains output_kind: "image" | "video" based on
    detected node output type or file extension.
    """
    job_data = client.fetch_job_outputs(prompt_id)

    refs: list[dict[str, Any]] = []

    # Standard ComfyUI history format under "outputs"
    outputs = job_data.get("outputs") or {}
    for _node_id, node_data in outputs.items():
        for img in node_data.get("images", []):
            item = dict(img)
            item.setdefault("output_kind", "image")
            refs.append(item)
        # VHS_VideoCombine outputs appear under "videos" or "gifs"
        for vid in (node_data.get("videos") or []) + (node_data.get("gifs") or []):
            item = dict(vid)
            item["output_kind"] = "video"
            refs.append(item)

    # Some cloud providers use top-level "results" or "files"
    if not refs:
        for item in job_data.get("results", []) or []:
            if isinstance(item, dict) and ("filename" in item or "url" in item):
                refs.append(item)

    # Classify any unclassified refs by file extension
    for ref in refs:
        if "output_kind" not in ref:
            filename = ref.get("filename", "").lower()
            ext = os.path.splitext(filename)[1]
            ref["output_kind"] = "video" if ext in _VIDEO_EXTENSIONS else "image"

    return refs


def download_cloud_outputs_typed(
    client: ComfyCloudClient,
    prompt_id: str,
    output_refs: list[dict[str, Any]],
    output_dir: str,
    render_id: str,
    frame_offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Download all output files from a completed cloud job.

    Classifies each output as "image" or "video" and names files accordingly:
      - images: {render_id}_cloud_frame_{N:03d}.png
      - videos: {render_id}_cloud_video_{N:03d}{ext}

    Returns list of dicts: {path, output_kind, filename}
    """
    os.makedirs(output_dir, exist_ok=True)
    results: list[dict[str, Any]] = []
    image_count = 0
    video_count = 0

    for ref in output_refs:
        filename = ref.get("filename", "")
        subfolder = ref.get("subfolder", "")
        output_type = ref.get("type", "output")
        output_kind = ref.get("output_kind", "image")

        if not filename:
            continue

        # Determine extension
        ext = os.path.splitext(filename)[1] or (".mp4" if output_kind == "video" else ".png")

        if output_kind == "video":
            local_path = os.path.join(
                output_dir, f"{render_id}_cloud_video_{video_count:03d}{ext}"
            )
            video_count += 1
        else:
            local_path = os.path.join(
                output_dir, f"{render_id}_cloud_frame_{(frame_offset + image_count):03d}.png"
            )
            image_count += 1

        try:
            data = client.download_output(filename, subfolder, output_type)
            with open(local_path, "wb") as fh:
                fh.write(data)
            results.append({"path": local_path, "output_kind": output_kind, "filename": filename})
        except ComfyCloudError:
            # Non-fatal — try remaining outputs
            continue

    return results


def download_cloud_outputs(
    client: ComfyCloudClient,
    prompt_id: str,
    output_refs: list[dict[str, Any]],
    output_dir: str,
    render_id: str,
    frame_offset: int = 0,
) -> list[str]:
    """
    Download all output images from a completed cloud job (backwards-compat wrapper).

    Returns list of local image paths successfully saved.
    For typed results including video paths, use download_cloud_outputs_typed().
    """
    typed = download_cloud_outputs_typed(
        client, prompt_id, output_refs, output_dir, render_id, frame_offset
    )
    return [r["path"] for r in typed if r["output_kind"] == "image"]


# ---------------------------------------------------------------------------
# Scene-beat cloud rendering
# ---------------------------------------------------------------------------

def run_scene_beats_cloud(
    pg: dict[str, Any],
    render_id: str,
    output_dir: str = "",
    workflow_path: str = "",
    test_mode: bool = False,
) -> dict[str, Any]:
    """
    Submit one Comfy Cloud job per scene beat and download all outputs.

    Supports workflows that output images (SaveImage) and/or direct video
    (VHS_VideoCombine / AnimateDiffCombine).

    Parameters
    ----------
    pg : dict
        Serialized prompt_generation document.
    render_id : str
        Used to name output files.
    output_dir : str
        Where to save downloaded files.
    workflow_path : str
        Override workflow path. Falls back to COMFY_CLOUD_WORKFLOW_PATH.
    test_mode : bool
        If True, returns a diagnostic result without making real API calls.

    Returns
    -------
    dict with keys:
        renderer_type           str — always "comfyui_cloud"
        cloud_provider          str
        workflow_variant        str — "animatediff_t2v" if video workflow, else ""
        comfy_output_type       str — "video" | "image_sequence" | "mixed"
        cloud_job_ids           list[str]
        output_image_paths      list[str]
        output_image_path       str — first image path (compat)
        output_video_paths      list[str]
        comfy_video_path        str — first video path
        downloaded_outputs      list[dict] — {path, output_kind, filename}
        errors                  list[str]
        warnings                list[str]
        fallback_used           bool
        fallback_reason         str
        simulation_only         bool — always True
        outbound_actions_taken  int — always 0
        test_mode               bool
    """
    out_dir = output_dir or os.getenv("FFMPEG_OUTPUT_DIR", "/tmp/signalforge_renders")
    os.makedirs(out_dir, exist_ok=True)

    wf_path = workflow_path or os.getenv("COMFY_CLOUD_WORKFLOW_PATH", "").strip()
    cloud_provider = os.getenv("COMFY_CLOUD_PROVIDER", "official")
    timeout = _get_timeout()
    fallback_allowed = _env_bool("COMFY_CLOUD_FALLBACK_ALLOWED")

    base_result: dict[str, Any] = {
        "renderer_type": _RENDERER_TYPE,
        "cloud_provider": cloud_provider,
        "workflow_variant": "",
        "comfy_output_type": "image_sequence",
        "cloud_job_ids": [],
        "output_image_paths": [],
        "output_image_path": "",
        "output_video_paths": [],
        "comfy_video_path": "",
        "downloaded_outputs": [],
        "errors": [],
        "warnings": [],
        "fallback_used": False,
        "fallback_reason": "",
        "simulation_only": True,
        "outbound_actions_taken": 0,
        "test_mode": test_mode,
    }

    # --- Validate configuration ---
    validation = validate_cloud_renderer()
    if not validation["valid"]:
        base_result["errors"] = validation["errors"]
        base_result["fallback_reason"] = validation["blocked_reason"]
        if not fallback_allowed:
            return base_result
        base_result["fallback_used"] = True
        base_result["warnings"].append(
            f"Comfy Cloud not configured — fallback_allowed=true. "
            f"Reason: {validation['blocked_reason']}"
        )
        return base_result

    # --- Test mode: return diagnostic without real API calls ---
    if test_mode:
        base_result["warnings"].append(
            "test_mode=true — no real Comfy Cloud API calls made. "
            "Configure credentials and workflow, then set test_mode=false."
        )
        return base_result

    client = ComfyCloudClient()
    scene_beats: list[str] = pg.get("scene_beats") or []
    if not scene_beats:
        scene_beats = [_build_positive_text(pg)]

    image_paths: list[str] = []
    video_paths: list[str] = []
    all_downloads: list[dict[str, Any]] = []
    job_ids: list[str] = []
    errors: list[str] = []
    workflow_variant = ""
    comfy_output_type = "image_sequence"

    for idx, beat_text in enumerate(scene_beats):
        base_positive = (
            f"{beat_text.strip()}, "
            f"{pg.get('visual_style', '').strip()}, "
            f"{pg.get('lighting', '').strip()}"
        ).strip(", ")
        positive = f"{base_positive}, {_FACELESS_SUFFIX}"
        negative = pg.get("negative_prompt") or ""
        if _SAFETY_NEGATIVE not in negative:
            negative = f"{negative}, {_SAFETY_NEGATIVE}" if negative else _SAFETY_NEGATIVE

        # Load and inject workflow
        try:
            workflow = load_cloud_workflow(
                pg,
                wf_path,
                positive_override=positive,
                negative_override=negative,
                force_portrait=True,
            )
        except Exception as exc:
            errors.append(f"beat[{idx}] workflow_load_failed: {exc}")
            if not fallback_allowed:
                continue
            base_result["fallback_used"] = True
            base_result["fallback_reason"] = str(exc)
            continue

        # Detect workflow output type (once, on first beat)
        if idx == 0:
            wf_info = detect_workflow_output_types(workflow)
            if wf_info["has_video_nodes"]:
                workflow_variant = "animatediff_t2v"
                comfy_output_type = "video"
                if wf_info["has_image_nodes"]:
                    comfy_output_type = "mixed"
                # Validate AnimateDiff nodes
                ad_validation = validate_animatediff_workflow(workflow)
                if not ad_validation["valid"]:
                    errors.extend(ad_validation["errors"])
                    base_result["errors"] = errors
                    if not fallback_allowed:
                        return base_result
                    base_result["fallback_used"] = True
                    base_result["fallback_reason"] = "; ".join(ad_validation["errors"])
                    return base_result
                base_result["warnings"].extend(ad_validation["warnings"])

        # Submit to cloud
        try:
            prompt_id = submit_cloud_workflow(client, workflow)
        except ComfyCloudError as exc:
            errors.append(f"beat[{idx}] submit_failed: {exc}")
            continue

        job_ids.append(prompt_id)

        # Poll for completion
        try:
            poll_cloud_job(client, prompt_id, timeout_seconds=timeout)
        except (ComfyCloudError, TimeoutError) as exc:
            errors.append(f"beat[{idx}] job_failed: {exc}")
            continue

        # Fetch typed output references
        try:
            output_refs = fetch_cloud_job_outputs(client, prompt_id)
        except ComfyCloudError as exc:
            errors.append(f"beat[{idx}] fetch_outputs_failed: {exc}")
            continue

        # Download all outputs (images + videos)
        typed_results = download_cloud_outputs_typed(
            client, prompt_id, output_refs, out_dir, render_id, frame_offset=idx
        )
        if not typed_results:
            errors.append(f"beat[{idx}] no outputs downloaded for job {prompt_id}")

        for item in typed_results:
            all_downloads.append(item)
            if item["output_kind"] == "video":
                video_paths.append(item["path"])
            else:
                image_paths.append(item["path"])

    base_result["workflow_variant"] = workflow_variant
    base_result["comfy_output_type"] = comfy_output_type
    base_result["cloud_job_ids"] = job_ids
    base_result["output_image_paths"] = image_paths
    base_result["output_image_path"] = image_paths[0] if image_paths else ""
    base_result["output_video_paths"] = video_paths
    base_result["comfy_video_path"] = video_paths[0] if video_paths else ""
    base_result["downloaded_outputs"] = all_downloads
    base_result["errors"] = errors
    return base_result
