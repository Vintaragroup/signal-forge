"""
comfyui_client.py — SignalForge ComfyUI integration client (v6)

Connects to a local ComfyUI instance:
  1. Builds a minimal KSampler workflow from prompt_generation fields
  2. Submits via POST /prompt
  3. Polls GET /history/{prompt_id} until completed
  4. Downloads the output image via GET /view?filename=...&type=output
  5. Saves to shared render-output volume

Safety guarantees
-----------------
- No external calls — only talks to COMFYUI_BASE_URL (local network)
- Graceful failure: always returns a dict (never raises to caller)
- simulation_only: True on all results
- outbound_actions_taken: 0 always
- No likeness generation, no voice cloning, no external publishing

Environment variables
---------------------
COMFYUI_BASE_URL             http://comfyui:8188 (default)
COMFYUI_MODEL_CHECKPOINT     v1-5-pruned-emaonly.safetensors (default)
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
        negative = (
            pg.get("negative_prompt")
            or "nsfw, explicit, realistic face, recognizable likeness, "
               "watermark, text overlay, low quality, blurry, distorted"
        )
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
                "inputs": {"width": 576, "height": 1024, "batch_size": 1},
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
        if workflow_path and os.path.isfile(workflow_path):
            try:
                with open(workflow_path) as fh:
                    workflow = json.load(fh)
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

        Returns
        -------
        dict with keys:
            output_image_paths      list[str] — paths to all saved images
            output_image_path       str  — first image path (backward compat)
            prompt_ids              list[str]
            errors                  list[str]
            simulation_only         bool — always True
            outbound_actions_taken  int  — always 0
        """
        out_dir = output_dir or os.getenv(
            "FFMPEG_OUTPUT_DIR", "/tmp/signalforge_renders"
        )
        os.makedirs(out_dir, exist_ok=True)

        scene_beats: list[str] = pg.get("scene_beats") or []
        # Fallback: one image from main prompt when no beats defined
        if not scene_beats:
            result = self.run_from_prompt_generation(pg, output_dir=out_dir)
            return {
                "output_image_paths": [result["output_image_path"]] if result.get("output_image_path") else [],
                "output_image_path": result.get("output_image_path", ""),
                "prompt_ids": [result.get("prompt_id", "")],
                "errors": [result.get("error", "")] if result.get("error") else [],
                "simulation_only": True,
                "outbound_actions_taken": 0,
            }

        image_paths: list[str] = []
        prompt_ids: list[str] = []
        errors: list[str] = []

        for idx, beat_text in enumerate(scene_beats):
            beat_pg = dict(pg)
            beat_pg["positive_prompt"] = (
                f"{beat_text.strip()}, "
                f"{pg.get('visual_style', '').strip()}, "
                f"{pg.get('lighting', '').strip()}, "
                f"no faces, no identifiable people, cinematic B-roll"
            )
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
    return ", ".join(parts) or "abstract digital art, cinematic, high contrast"


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
    return {
        "comfyui_enabled": _env_enabled(os.getenv("COMFYUI_ENABLED", "false")),
        "comfyui_base_url": client.base_url,
        "comfyui_reachable": health.get("reachable", False),
        "comfyui_error": health.get("error", ""),
        "system_stats": health.get("system_stats"),
    }
