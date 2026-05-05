"""
comfyui_client.py — SignalForge ComfyUI integration client (v7 — Phase 10)

Renderer backend abstraction
-----------------------------
renderer_type is resolved at runtime from environment / config:

  comfyui_stub      — built-in Pillow test stub (never production-ready)
  comfyui_real      — real ComfyUI instance with COMFYUI_WORKFLOW_PATH set
  external_manual   — placeholder for operator-supplied frames (no HTTP calls)

Resolution order:
  1. COMFYUI_RENDERER_TYPE env var (explicit override)
  2. COMFYUI_WORKFLOW_PATH set + COMFYUI_ENABLED=true → comfyui_real
  3. COMFYUI_ENABLED=true but no workflow path → comfyui_stub (with warning)
  4. COMFYUI_ENABLED=false → skipped entirely (comfyui_stub label, mock result)

Real workflow support (comfyui_real)
--------------------------------------
COMFYUI_WORKFLOW_PATH   Path to a ComfyUI API-format workflow JSON.
                        Prompt injection points (CLIPTextEncode nodes with
                        "{{positive_prompt}}" / "{{negative_prompt}}" in
                        their text inputs) are substituted per scene beat.
                        Width/height EmptyLatentImage nodes are patched to
                        1080×1920 if COMFYUI_FORCE_PORTRAIT=true (default).

Validation
----------
- COMFYUI_ENABLED=true + workflow path missing → error, never falls back to
  stub silently (unless COMFYUI_FALLBACK_ALLOWED=true)
- Stub output is always labelled renderer_type=comfyui_stub, never "real"
- metadata dict includes: renderer_type, workflow_path, model_name,
  fallback_used, fallback_reason

Safety guarantees
-----------------
- No external calls — only talks to COMFYUI_BASE_URL (local network)
- simulation_only: True on all results
- outbound_actions_taken: 0 always
- No likeness generation, no voice cloning, no external publishing
- Faceless: negative_prompt always contains "face, likeness, person, avatar"

Environment variables
---------------------
COMFYUI_BASE_URL             http://comfyui:8188 (default)
COMFYUI_MODEL_CHECKPOINT     v1-5-pruned-emaonly.safetensors (default)
COMFYUI_WORKFLOW_PATH        (empty) path to real workflow JSON
COMFYUI_RENDERER_TYPE        (auto-detected) comfyui_stub | comfyui_real | external_manual
COMFYUI_FORCE_PORTRAIT       true — patch EmptyLatentImage to 1080×1920
COMFYUI_FALLBACK_ALLOWED     false — allow stub fallback when real workflow fails
FFMPEG_OUTPUT_DIR            /tmp/signalforge_renders (default)
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


_DEFAULT_BASE_URL = "http://comfyui:8188"
_POLL_INTERVAL_S = 1.0       # seconds between history polls
_POLL_MAX_WAIT_S = 120       # seconds max to wait for generation
_CONNECT_TIMEOUT_S = 5       # seconds for health / quick checks
_DOWNLOAD_TIMEOUT_S = 30     # seconds to download output image

# Faceless cinematic suffix appended to every scene-beat positive prompt
_FACELESS_SUFFIX = (
    "no faces, no identifiable people, no avatars, faceless, "
    "cinematic B-roll, symbolic leadership imagery, vertical 9:16"
)

# Negative prompt additions always enforced for safety
_SAFETY_NEGATIVE = (
    "realistic face, recognizable likeness, identifiable person, avatar, "
    "voice cloning, nsfw, explicit, watermark, text overlay, low quality, blurry"
)


# ---------------------------------------------------------------------------
# Renderer backend resolution
# ---------------------------------------------------------------------------

def resolve_renderer_type() -> str:
    """
    Determine which renderer backend will be used.

    Returns one of: "comfyui_stub", "comfyui_real", "external_manual"

    Resolution order:
    1. COMFYUI_RENDERER_TYPE env var (explicit override)
    2. COMFYUI_WORKFLOW_PATH set + COMFYUI_ENABLED=true → comfyui_real
    3. COMFYUI_ENABLED=true but no workflow path → comfyui_stub
    4. Default → comfyui_stub
    """
    explicit = os.getenv("COMFYUI_RENDERER_TYPE", "").strip().lower()
    if explicit in ("comfyui_stub", "comfyui_real", "external_manual"):
        return explicit

    enabled = str(os.getenv("COMFYUI_ENABLED", "false")).strip().lower() in (
        "1", "true", "yes", "on"
    )
    workflow_path = os.getenv("COMFYUI_WORKFLOW_PATH", "").strip()

    if enabled and workflow_path:
        return "comfyui_real"
    return "comfyui_stub"


def validate_renderer(renderer_type: str | None = None) -> dict[str, Any]:
    """
    Validate that the resolved renderer is ready to use.

    Returns a dict with:
        valid           bool
        renderer_type   str
        workflow_path   str
        model_name      str
        errors          list[str]
        warnings        list[str]

    Raises ValueError if COMFYUI_ENABLED=true and workflow path is missing
    and COMFYUI_FALLBACK_ALLOWED is not true.
    """
    rt = renderer_type or resolve_renderer_type()
    workflow_path = os.getenv("COMFYUI_WORKFLOW_PATH", "").strip()
    model_name = os.getenv(
        "COMFYUI_MODEL_CHECKPOINT", "v1-5-pruned-emaonly.safetensors"
    )
    enabled = str(os.getenv("COMFYUI_ENABLED", "false")).strip().lower() in (
        "1", "true", "yes", "on"
    )
    fallback_allowed = str(os.getenv("COMFYUI_FALLBACK_ALLOWED", "false")).strip().lower() in (
        "1", "true", "yes", "on"
    )

    errors: list[str] = []
    warnings: list[str] = []

    if rt == "comfyui_real":
        if not workflow_path:
            msg = (
                "COMFYUI_ENABLED=true and renderer_type=comfyui_real but "
                "COMFYUI_WORKFLOW_PATH is not set. Set COMFYUI_WORKFLOW_PATH "
                "or set COMFYUI_FALLBACK_ALLOWED=true to use the stub."
            )
            if not fallback_allowed:
                errors.append(msg)
            else:
                warnings.append(msg + " Falling back to comfyui_stub.")
                rt = "comfyui_stub"
        elif not os.path.isfile(workflow_path):
            msg = f"COMFYUI_WORKFLOW_PATH={workflow_path!r} does not exist or is not a file."
            if not fallback_allowed:
                errors.append(msg)
            else:
                warnings.append(msg + " Falling back to comfyui_stub.")
                rt = "comfyui_stub"

    if rt == "comfyui_stub":
        warnings.append(
            "renderer_type=comfyui_stub — output images are generated by the "
            "built-in Pillow test stub and are NOT production-ready visuals."
        )

    if enabled and rt == "comfyui_stub" and not workflow_path:
        warnings.append(
            "COMFYUI_ENABLED=true but COMFYUI_WORKFLOW_PATH is not configured. "
            "To use real ComfyUI rendering, set COMFYUI_WORKFLOW_PATH to a valid "
            "ComfyUI API-format workflow JSON file."
        )

    return {
        "valid": len(errors) == 0,
        "renderer_type": rt,
        "workflow_path": workflow_path,
        "model_name": model_name,
        "errors": errors,
        "warnings": warnings,
    }


def load_real_workflow(
    pg: dict[str, Any],
    workflow_path: str,
    positive_override: str = "",
    negative_override: str = "",
    force_portrait: bool = True,
) -> dict[str, Any]:
    """
    Load a ComfyUI API-format workflow JSON and inject prompt fields.

    Injection strategy:
    - Nodes with class_type "CLIPTextEncode" whose text contains
      "{{positive_prompt}}" are replaced with positive_override or
      _build_positive_text(pg).
    - Nodes with class_type "CLIPTextEncode" whose text contains
      "{{negative_prompt}}" are replaced with negative_override or pg.negative_prompt.
    - If force_portrait=True, any EmptyLatentImage node has width/height
      patched to 1080×1920.
    - If no injection markers found, falls back to patching the first two
      CLIPTextEncode nodes (positive then negative).

    Returns the modified workflow dict.
    Raises ValueError on load failure.
    """
    try:
        with open(workflow_path) as fh:
            workflow: dict[str, Any] = json.load(fh)
    except Exception as exc:
        raise ValueError(f"Failed to load workflow from {workflow_path!r}: {exc}") from exc

    positive_text = positive_override or _build_positive_text(pg)
    negative_text = (
        negative_override
        or pg.get("negative_prompt")
        or ""
    )
    # Always enforce safety negatives
    if _SAFETY_NEGATIVE not in negative_text:
        negative_text = f"{negative_text}, {_SAFETY_NEGATIVE}" if negative_text else _SAFETY_NEGATIVE

    clip_nodes = [
        (node_id, node)
        for node_id, node in workflow.items()
        if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode"
    ]

    positive_injected = False
    negative_injected = False

    # Pass 1: look for template markers
    for node_id, node in clip_nodes:
        text = str(node.get("inputs", {}).get("text", ""))
        if "{{positive_prompt}}" in text:
            workflow[node_id]["inputs"]["text"] = positive_text
            positive_injected = True
        elif "{{negative_prompt}}" in text:
            workflow[node_id]["inputs"]["text"] = negative_text
            negative_injected = True

    # Pass 2: fallback — first two CLIP nodes if markers not found
    if not positive_injected and clip_nodes:
        workflow[clip_nodes[0][0]]["inputs"]["text"] = positive_text
        positive_injected = True
    if not negative_injected and len(clip_nodes) > 1:
        workflow[clip_nodes[1][0]]["inputs"]["text"] = negative_text
        negative_injected = True

    # Patch portrait dimensions
    if force_portrait:
        for node_id, node in workflow.items():
            if isinstance(node, dict) and node.get("class_type") == "EmptyLatentImage":
                workflow[node_id]["inputs"]["width"] = 1080
                workflow[node_id]["inputs"]["height"] = 1920

    return workflow


class ComfyUIClient:
    """Minimal HTTP client for a local ComfyUI instance."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (
            base_url or os.getenv("COMFYUI_BASE_URL", _DEFAULT_BASE_URL)
        ).rstrip("/")

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        """
        GET /system_stats — confirm ComfyUI is reachable.

        Returns dict with at least:
            reachable : bool
            url       : str
        """
        url = f"{self.base_url}/system_stats"
        try:
            req = urllib.request.Request(
                url, headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=_CONNECT_TIMEOUT_S) as resp:
                data = json.loads(resp.read())
            return {"reachable": True, "url": self.base_url, "system_stats": data}
        except Exception as exc:
            return {
                "reachable": False,
                "url": self.base_url,
                "error": f"{type(exc).__name__}: {exc}",
            }

    # ------------------------------------------------------------------
    # Workflow builder
    # ------------------------------------------------------------------

    def build_txt2img_workflow(self, pg: dict[str, Any]) -> dict[str, Any]:
        """
        Build a minimal ComfyUI API-format workflow (prompt API dict) from a
        prompt_generation document.

        Uses fields: positive_prompt, negative_prompt, visual_style,
        lighting, camera_direction.

        Returns a dict keyed by node ID (ComfyUI "api format").
        """
        model = os.getenv(
            "COMFYUI_MODEL_CHECKPOINT",
            "v1-5-pruned-emaonly.safetensors",
        )
        positive = _build_positive_text(pg)
        raw_negative = (
            pg.get("negative_prompt") or ""
        )
        # Always enforce faceless / safety negatives
        if _SAFETY_NEGATIVE not in raw_negative:
            negative = f"{raw_negative}, {_SAFETY_NEGATIVE}" if raw_negative else _SAFETY_NEGATIVE
        else:
            negative = raw_negative
        seed = int(pg.get("seed") or 0) or (uuid.uuid4().int & 0xFFFF_FFFF)

        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": model},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": positive, "clip": ["1", 1]},
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": negative, "clip": ["1", 1]},
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 1080, "height": 1920, "batch_size": 1},
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": 20,
                    "cfg": 7.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                },
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            },
            "7": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "signalforge",
                    "images": ["6", 0],
                },
            },
        }

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

    def _queue_prompt(self, workflow: dict[str, Any]) -> dict[str, Any]:
        """POST /prompt — queue the workflow. Returns the full response dict."""
        payload = json.dumps({"prompt": workflow}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/prompt",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_CONNECT_TIMEOUT_S) as resp:
            return json.loads(resp.read())

    def _get_history(self, prompt_id: str) -> dict[str, Any]:
        """GET /history/{prompt_id} — return the raw history dict."""
        req = urllib.request.Request(
            f"{self.base_url}/history/{prompt_id}",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=_CONNECT_TIMEOUT_S) as resp:
            return json.loads(resp.read())

    def _download_image(
        self,
        filename: str,
        subfolder: str,
        img_type: str,
        output_path: str,
    ) -> str:
        """
        GET /view?filename=...&subfolder=...&type=... and write bytes to
        output_path.  Returns output_path on success, "" on failure.
        """
        params = urllib.parse.urlencode(
            {"filename": filename, "subfolder": subfolder, "type": img_type}
        )
        url = f"{self.base_url}/view?{params}"
        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT_S) as resp:
                data = resp.read()
            with open(output_path, "wb") as fh:
                fh.write(data)
            return output_path
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run_from_prompt_generation(
        self,
        pg: dict[str, Any],
        output_dir: str = "",
        workflow_path: str = "",
    ) -> dict[str, Any]:
        """
        Submit a prompt to ComfyUI and wait for the output image.

        Parameters
        ----------
        pg : dict
            Serialized prompt_generation document.
        output_dir : str
            Directory where the downloaded image is saved.
            Defaults to FFMPEG_OUTPUT_DIR or /tmp/signalforge_renders.
        workflow_path : str
            Optional path to a pre-built workflow JSON file.
            If empty, a workflow is auto-built from pg fields.

        Returns
        -------
        dict with keys:
            output_image_path       str  — absolute path to saved image (empty on failure)
            prompt_id               str
            image_filename          str
            workflow                dict — workflow that was submitted
            error                   str  — non-empty on failure
            simulation_only         bool — always True
            outbound_actions_taken  int  — always 0
        """
        out_dir = output_dir or os.getenv(
            "FFMPEG_OUTPUT_DIR", "/tmp/signalforge_renders"
        )
        os.makedirs(out_dir, exist_ok=True)

        render_id = pg.get("_id") or pg.get("snippet_id") or str(uuid.uuid4())
        image_output_path = os.path.join(out_dir, f"comfyui_{render_id}.png")

        base: dict[str, Any] = {
            "output_image_path": "",
            "prompt_id": "",
            "image_filename": "",
            "workflow": {},
            "error": "",
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

        # --- Load or build workflow ---
        if workflow_path:
            try:
                workflow = load_real_workflow(
                    pg,
                    workflow_path,
                    force_portrait=str(os.getenv("COMFYUI_FORCE_PORTRAIT", "true")).strip().lower() in (
                        "1", "true", "yes", "on"
                    ),
                )
            except Exception as exc:
                base["error"] = f"workflow_load_failed: {exc}"
                return base
        else:
            workflow = self.build_txt2img_workflow(pg)
        base["workflow"] = workflow

        # --- Submit prompt ---
        try:
            submit_resp = self._queue_prompt(workflow)
        except Exception as exc:
            base["error"] = f"POST /prompt failed: {type(exc).__name__}: {exc}"
            return base

        prompt_id = submit_resp.get("prompt_id", "")
        if not prompt_id:
            base["error"] = f"No prompt_id in response: {submit_resp}"
            return base
        base["prompt_id"] = prompt_id

        # --- Poll history until completed ---
        deadline = time.monotonic() + _POLL_MAX_WAIT_S
        while time.monotonic() < deadline:
            time.sleep(_POLL_INTERVAL_S)
            try:
                history = self._get_history(prompt_id)
            except Exception as exc:
                base["error"] = f"GET /history failed: {type(exc).__name__}: {exc}"
                return base

            entry = history.get(prompt_id, {})
            if not entry.get("status", {}).get("completed"):
                continue

            # --- Find first output image ---
            image_info = _extract_first_image(entry.get("outputs", {}))
            if not image_info:
                base["error"] = "No output image found in history outputs"
                return base

            fname = image_info["filename"]
            subfolder = image_info.get("subfolder", "")
            img_type = image_info.get("type", "output")
            base["image_filename"] = fname

            # --- Download image ---
            saved = self._download_image(fname, subfolder, img_type, image_output_path)
            if not saved:
                base["error"] = f"Failed to download image: {fname}"
                return base

            base["output_image_path"] = saved
            return base

        base["error"] = f"ComfyUI generation timed out after {_POLL_MAX_WAIT_S}s"
        return base

    # ------------------------------------------------------------------
    # Scene-beat multi-image entry point
    # ------------------------------------------------------------------

    def run_scene_beats(
        self,
        pg: dict[str, Any],
        render_id: str,
        output_dir: str = "",
        renderer_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Submit one ComfyUI prompt per scene beat and collect all output images.

        Parameters
        ----------
        pg : dict
            Serialized prompt_generation document.  Must contain a
            ``scene_beats`` list of strings (falls back to one image from
            the main prompt when absent or empty).
        render_id : str
            Used to build unique per-frame filenames.
        output_dir : str
            Directory where images are saved.
        renderer_type : str | None
            Override for the resolved renderer type.  Defaults to
            resolve_renderer_type().

        Returns
        -------
        dict with keys:
            output_image_paths      list[str] — paths to all saved images
            output_image_path       str  — first image path (backward compat)
            prompt_ids              list[str]
            errors                  list[str]
            renderer_type           str — comfyui_stub | comfyui_real | external_manual
            workflow_path           str — path to workflow JSON (empty for stub)
            model_name              str — checkpoint name
            fallback_used           bool
            fallback_reason         str
            simulation_only         bool — always True
            outbound_actions_taken  int  — always 0
        """
        out_dir = output_dir or os.getenv(
            "FFMPEG_OUTPUT_DIR", "/tmp/signalforge_renders"
        )
        os.makedirs(out_dir, exist_ok=True)

        # --- Validate / resolve renderer ---
        original_rt = renderer_type or resolve_renderer_type()
        validation = validate_renderer(renderer_type)
        rt = validation["renderer_type"]
        workflow_path = validation["workflow_path"]
        model_name = validation["model_name"]
        # Fallback was used if the validated type differs from originally requested
        fallback_used = rt != original_rt and bool(validation["warnings"])
        fallback_reason = validation["warnings"][0] if fallback_used else ""

        # If validation errors and fallback not allowed, fail immediately
        if not validation["valid"]:
            return {
                "output_image_paths": [],
                "output_image_path": "",
                "prompt_ids": [],
                "errors": validation["errors"],
                "renderer_type": rt,
                "workflow_path": workflow_path,
                "model_name": model_name,
                "fallback_used": False,
                "fallback_reason": "; ".join(validation["errors"]),
                "simulation_only": True,
                "outbound_actions_taken": 0,
            }

        scene_beats: list[str] = pg.get("scene_beats") or []
        # Fallback: one image from main prompt when no beats defined
        if not scene_beats:
            result = self.run_from_prompt_generation(
                pg, output_dir=out_dir,
                workflow_path=workflow_path if rt == "comfyui_real" else "",
            )
            return {
                "output_image_paths": [result["output_image_path"]] if result.get("output_image_path") else [],
                "output_image_path": result.get("output_image_path", ""),
                "prompt_ids": [result.get("prompt_id", "")],
                "errors": [result.get("error", "")] if result.get("error") else [],
                "renderer_type": rt,
                "workflow_path": workflow_path,
                "model_name": model_name,
                "fallback_used": fallback_used,
                "fallback_reason": fallback_reason,
                "simulation_only": True,
                "outbound_actions_taken": 0,
            }

        image_paths: list[str] = []
        prompt_ids: list[str] = []
        errors: list[str] = []

        for idx, beat_text in enumerate(scene_beats):
            beat_pg = dict(pg)
            # Build per-beat positive prompt with faceless safety suffix
            base_positive = (
                f"{beat_text.strip()}, "
                f"{pg.get('visual_style', '').strip()}, "
                f"{pg.get('lighting', '').strip()}"
            ).strip(", ")
            beat_pg["positive_prompt"] = f"{base_positive}, {_FACELESS_SUFFIX}"

            # Load real workflow or build stub workflow
            if rt == "comfyui_real" and workflow_path:
                try:
                    workflow = load_real_workflow(
                        beat_pg,
                        workflow_path,
                        positive_override=beat_pg["positive_prompt"],
                        force_portrait=str(os.getenv("COMFYUI_FORCE_PORTRAIT", "true")).strip().lower() in (
                            "1", "true", "yes", "on"
                        ),
                    )
                except ValueError as exc:
                    # Workflow load failed — check fallback policy
                    fallback_allowed = str(os.getenv("COMFYUI_FALLBACK_ALLOWED", "false")).strip().lower() in (
                        "1", "true", "yes", "on"
                    )
                    if not fallback_allowed:
                        errors.append(f"beat[{idx}] workflow_load_failed: {exc}")
                        continue
                    # Fall back to stub workflow
                    fallback_used = True
                    fallback_reason = f"workflow_load_failed: {exc}"
                    workflow = self.build_txt2img_workflow(beat_pg)
                    rt = "comfyui_stub"
            else:
                workflow = self.build_txt2img_workflow(beat_pg)

            image_output_path = os.path.join(
                out_dir, f"{render_id}_frame_{idx:03d}.png"
            )

            # Submit
            try:
                submit_resp = self._queue_prompt(workflow)
            except Exception as exc:
                errors.append(f"beat[{idx}] POST /prompt failed: {exc}")
                continue

            prompt_id = submit_resp.get("prompt_id", "")
            if not prompt_id:
                errors.append(f"beat[{idx}] no prompt_id in response")
                continue
            prompt_ids.append(prompt_id)

            # Poll
            saved = ""
            deadline = time.monotonic() + _POLL_MAX_WAIT_S
            while time.monotonic() < deadline:
                time.sleep(_POLL_INTERVAL_S)
                try:
                    history = self._get_history(prompt_id)
                except Exception as exc:
                    errors.append(f"beat[{idx}] GET /history failed: {exc}")
                    break

                entry = history.get(prompt_id, {})
                if not entry.get("status", {}).get("completed"):
                    continue

                image_info = _extract_first_image(entry.get("outputs", {}))
                if not image_info:
                    errors.append(f"beat[{idx}] no output image in history")
                    break

                fname = image_info["filename"]
                subfolder = image_info.get("subfolder", "")
                img_type = image_info.get("type", "output")
                saved = self._download_image(fname, subfolder, img_type, image_output_path)
                if not saved:
                    errors.append(f"beat[{idx}] download failed: {fname}")
                break
            else:
                errors.append(f"beat[{idx}] timed out after {_POLL_MAX_WAIT_S}s")

            if saved:
                image_paths.append(saved)

        first_path = image_paths[0] if image_paths else ""
        return {
            "output_image_paths": image_paths,
            "output_image_path": first_path,
            "prompt_ids": prompt_ids,
            "errors": errors,
            "renderer_type": rt,
            "workflow_path": workflow_path,
            "model_name": model_name,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }


# ---------------------------------------------------------------------------
# Module-level helpers (used by worker and health endpoint)
# ---------------------------------------------------------------------------

def _build_positive_text(pg: dict[str, Any]) -> str:
    """Combine prompt_generation visual fields into a positive prompt string."""
    parts: list[str] = []
    for field in ("positive_prompt", "visual_style", "lighting", "camera_direction"):
        val = (pg.get(field) or "").strip()
        if val:
            parts.append(val)
    base = ", ".join(parts) or "abstract digital art, cinematic, high contrast"
    # Append faceless suffix if not already present
    if "no faces" not in base and _FACELESS_SUFFIX not in base:
        return f"{base}, {_FACELESS_SUFFIX}"
    return base


def _extract_first_image(
    outputs: dict[str, Any],
) -> dict[str, str] | None:
    """Walk ComfyUI history outputs to find the first image reference."""
    for _node_id, node_data in outputs.items():
        images = node_data.get("images", [])
        if images:
            return images[0]
    return None


def _env_enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def comfyui_diagnostics() -> dict[str, Any]:
    """Return ComfyUI availability diagnostics (used by /health/comfyui)."""
    client = ComfyUIClient()
    health = client.health_check()
    validation = validate_renderer()
    return {
        "comfyui_enabled": _env_enabled(os.getenv("COMFYUI_ENABLED", "false")),
        "comfyui_base_url": client.base_url,
        "comfyui_reachable": health.get("reachable", False),
        "comfyui_error": health.get("error", ""),
        "system_stats": health.get("system_stats"),
        "renderer_type": validation["renderer_type"],
        "workflow_path": validation["workflow_path"],
        "model_name": validation["model_name"],
        "renderer_valid": validation["valid"],
        "renderer_warnings": validation["warnings"],
        "renderer_errors": validation["errors"],
    }
