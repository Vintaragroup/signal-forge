"""
ComfyUI client for SignalForge Social Creative Engine v2.

All generation is simulation-only. ComfyUI must be explicitly enabled via
COMFYUI_ENABLED=true and reachable at COMFYUI_BASE_URL. If unavailable,
fail safely and return a structured error. Never publish or schedule content.
"""

import json
import os
from typing import Any
from urllib import request as urllib_request
from urllib.error import URLError


DEFAULT_COMFYUI_BASE_URL = "http://host.docker.internal:8188"


def _comfyui_base_url() -> str:
    return os.getenv("COMFYUI_BASE_URL", DEFAULT_COMFYUI_BASE_URL).rstrip("/")


def _comfyui_workflow_path() -> str:
    return os.getenv("COMFYUI_WORKFLOW_PATH", "")


class ComfyUIError(Exception):
    pass


class ComfyUIClient:
    """Thin wrapper for the ComfyUI HTTP API. Simulation-only — never publishes."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or _comfyui_base_url()).rstrip("/")

    def _post_json(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except URLError as exc:
            raise ComfyUIError(f"ComfyUI unreachable at {self.base_url}: {exc}") from exc
        except Exception as exc:
            raise ComfyUIError(f"ComfyUI request failed: {exc}") from exc

    def health_check(self) -> bool:
        url = f"{self.base_url}/system_stats"
        req = urllib_request.Request(url, method="GET")
        try:
            with urllib_request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def run_workflow(
        self,
        workflow_path: str = "",
        prompt_inputs: dict | None = None,
    ) -> dict[str, Any]:
        """
        Submit a workflow to ComfyUI. Returns the queue response or raises ComfyUIError.
        All results are simulation-only — no content is published.
        """
        resolved_path = workflow_path or _comfyui_workflow_path()
        workflow: dict[str, Any] = {}

        if resolved_path:
            try:
                with open(resolved_path, encoding="utf-8") as fh:
                    workflow = json.load(fh)
            except FileNotFoundError as exc:
                raise ComfyUIError(f"Workflow file not found: {resolved_path}") from exc
            except json.JSONDecodeError as exc:
                raise ComfyUIError(f"Invalid JSON in workflow file: {exc}") from exc

        if prompt_inputs:
            for node_id, overrides in prompt_inputs.items():
                if node_id in workflow and isinstance(overrides, dict):
                    inputs = workflow[node_id].get("inputs", {})
                    inputs.update(overrides)
                    workflow[node_id]["inputs"] = inputs

        result = self._post_json("/prompt", {"prompt": workflow})
        return {
            "prompt_id": result.get("prompt_id"),
            "number": result.get("number"),
            "node_errors": result.get("node_errors", {}),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }
