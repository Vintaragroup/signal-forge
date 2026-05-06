"""
comfyui_mcp_validation.py — SignalForge Comfy MCP validation helper (Phase 11)

Purpose
-------
Use the Comfy Cloud MCP server as a discovery/planning/validation helper,
NOT as the primary production rendering path.

The MCP server is an early-access research preview.
SignalForge does NOT require live MCP calls for tests.
All validation plan steps are verifiable manually or via future adapters.

MCP Server details
------------------
URL:    https://cloud.comfy.org/mcp
Auth:   X-API-Key header (COMFY_MCP_API_KEY env var)
Mode:   COMFY_MCP_VALIDATION_ONLY=true (default) — no production submissions

Cursor / Claude Code setup
---------------------------
Add to .cursor/mcp.json or claude_desktop_config.json:

  {
    "mcpServers": {
      "comfy-cloud": {
        "command": "npx",
        "args": ["mcp-remote", "https://cloud.comfy.org/mcp"],
        "headers": {
          "X-API-Key": "<your-comfy-cloud-api-key>"
        }
      }
    }
  }

MCP tools available (expected — verify with summarize_available_mcp_tools)
---------------------------------------------------------------------------
  search_templates    — find workflow templates matching a query
  search_models       — find models by name/type
  submit_workflow     — submit a workflow JSON for execution
  get_job_status      — get status of a queued job
  get_output          — retrieve job output references

Validation checklist
---------------------
For each tool, confirm:
1. Tool is listed in the MCP tool manifest
2. Tool accepts expected parameters
3. Tool returns expected response structure
4. Output files are accessible via get_output
5. No PII/face generation occurs
"""

from __future__ import annotations

import os
from typing import Any


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def mcp_diagnostics() -> dict[str, Any]:
    """
    Return MCP configuration status.

    IMPORTANT: Never returns the API key value.
    Only returns api_key_configured=True/False.
    """
    enabled = str(os.getenv("COMFY_MCP_ENABLED", "false")).strip().lower() in (
        "1", "true", "yes", "on"
    )
    mcp_url = os.getenv("COMFY_MCP_URL", "https://cloud.comfy.org/mcp")
    api_key_val = os.getenv("COMFY_MCP_API_KEY", "").strip()
    api_key_configured = bool(api_key_val)
    validation_only = str(os.getenv("COMFY_MCP_VALIDATION_ONLY", "true")).strip().lower() in (
        "1", "true", "yes", "on"
    )

    errors: list[str] = []
    warnings: list[str] = []

    if not enabled:
        errors.append("COMFY_MCP_ENABLED=false — MCP is not active.")
    if not api_key_configured:
        errors.append(
            "COMFY_MCP_API_KEY is not set. "
            "A Comfy Cloud API key is required to connect to the MCP server."
        )
    if not validation_only:
        warnings.append(
            "COMFY_MCP_VALIDATION_ONLY=false — MCP may submit production jobs. "
            "Set COMFY_MCP_VALIDATION_ONLY=true unless intentionally in production mode."
        )

    return {
        "mcp_enabled": enabled,
        "mcp_url": mcp_url,
        "api_key_configured": api_key_configured,  # True/False only — key never returned
        "validation_only": validation_only,
        "ready": enabled and api_key_configured,
        "errors": errors,
        "warnings": warnings,
        "note": (
            "MCP is an early-access research preview. "
            "Do not use for production rendering until fully validated."
        ),
        "simulation_only": True,
        "outbound_actions_taken": 0,
    }


# ---------------------------------------------------------------------------
# Setup instructions
# ---------------------------------------------------------------------------

def build_mcp_connection_instructions() -> dict[str, Any]:
    """
    Return exact setup instructions for connecting Cursor or Claude Code
    to the Comfy Cloud MCP server.

    These instructions are safe to display to operators.
    They do NOT include the actual API key value.
    """
    mcp_url = os.getenv("COMFY_MCP_URL", "https://cloud.comfy.org/mcp")
    key_env = "COMFY_MCP_API_KEY"
    api_key_configured = bool(os.getenv(key_env, "").strip())

    cursor_config = {
        "mcpServers": {
            "comfy-cloud": {
                "command": "npx",
                "args": ["mcp-remote", mcp_url],
                "headers": {
                    "X-API-Key": f"<value of {key_env} env var>"
                }
            }
        }
    }

    claude_code_config = {
        "mcpServers": {
            "comfy-cloud": {
                "command": "npx",
                "args": ["-y", "mcp-remote", mcp_url],
                "env": {
                    "X_API_KEY": f"<value of {key_env} env var>"
                }
            }
        }
    }

    return {
        "mcp_url": mcp_url,
        "api_key_env_var": key_env,
        "api_key_configured": api_key_configured,
        "cursor_mcp_json": cursor_config,
        "claude_code_mcp_json": claude_code_config,
        "setup_steps": [
            "1. Get your Comfy Cloud API key from https://cloud.comfy.org",
            f"2. Set {key_env}=<your-key> in your .env file",
            "3. Set COMFY_MCP_ENABLED=true in your .env file",
            "4. Add the MCP server config to .cursor/mcp.json or claude_desktop_config.json",
            "5. Restart Cursor / Claude Code to load the MCP server",
            "6. Run summarize_available_mcp_tools() to verify tool list",
            "7. Run create_mcp_validation_plan() to get a structured validation checklist",
        ],
        "warning": (
            "Comfy Cloud MCP is early access. API shape may change. "
            "Do not use COMFY_MCP_VALIDATION_ONLY=false in production."
        ),
        "simulation_only": True,
        "outbound_actions_taken": 0,
    }


# ---------------------------------------------------------------------------
# Tool manifest
# ---------------------------------------------------------------------------

def summarize_available_mcp_tools() -> dict[str, Any]:
    """
    Return the expected MCP tools available on the Comfy Cloud MCP server.

    This is a static manifest based on official Comfy Cloud MCP documentation.
    Actual tool availability depends on your subscription tier.

    NOTE: This does NOT make a live call to the MCP server.
    To verify live tool availability, use the Cursor MCP panel or Claude Code.
    """
    expected_tools = [
        {
            "name": "search_templates",
            "description": "Search workflow templates by keyword, style, or category.",
            "expected_params": ["query", "category", "limit"],
            "validation_status": "not_verified",
        },
        {
            "name": "search_models",
            "description": "Search available models by name, type (checkpoint, lora, etc.), or tag.",
            "expected_params": ["query", "model_type", "limit"],
            "validation_status": "not_verified",
        },
        {
            "name": "submit_workflow",
            "description": "Submit a ComfyUI API-format workflow JSON for cloud execution.",
            "expected_params": ["workflow", "priority"],
            "validation_status": "not_verified",
        },
        {
            "name": "get_job_status",
            "description": "Get the current status of a queued or running job.",
            "expected_params": ["job_id"],
            "validation_status": "not_verified",
        },
        {
            "name": "get_output",
            "description": "Retrieve output file references for a completed job.",
            "expected_params": ["job_id"],
            "validation_status": "not_verified",
        },
    ]

    return {
        "source": "static_manifest_phase11",
        "live_verified": False,
        "note": (
            "This manifest is based on official Comfy Cloud MCP documentation. "
            "Verify live tool availability in Cursor MCP panel after connecting."
        ),
        "tools": expected_tools,
        "validation_checklist": _build_tool_validation_checklist(expected_tools),
        "simulation_only": True,
        "outbound_actions_taken": 0,
    }


def _build_tool_validation_checklist(tools: list[dict]) -> list[dict]:
    return [
        {
            "tool": t["name"],
            "check_listed_in_manifest": False,
            "check_accepts_expected_params": False,
            "check_returns_expected_structure": False,
            "check_outputs_accessible": False,
            "check_no_face_generation": False,
            "verified_at": None,
            "notes": "",
        }
        for t in tools
    ]


# ---------------------------------------------------------------------------
# Validation plan
# ---------------------------------------------------------------------------

def create_mcp_validation_plan(prompt_generation: dict[str, Any]) -> dict[str, Any]:
    """
    Create a structured validation plan for MCP-assisted rendering.

    Parameters
    ----------
    prompt_generation : dict
        A prompt_generation document from SignalForge.
        Used to build the test prompt summary.

    Returns
    -------
    dict with:
        plan_steps          list of validation steps to execute manually
        prompt_summary      summary of the test prompt (no raw key data)
        safety_checks       list of safety requirements to verify
        quality_gates       list of quality gates before production use
        mcp_tools_needed    list of MCP tools required for this plan
    """
    pg_id = str(prompt_generation.get("_id", "unknown"))
    workspace_slug = prompt_generation.get("workspace_slug", "unknown")
    positive_preview = (prompt_generation.get("positive_prompt") or "")[:100]
    negative_preview = (prompt_generation.get("negative_prompt") or "")[:100]
    scene_beat_count = len(prompt_generation.get("scene_beats") or [])

    plan_steps = [
        {
            "step": 1,
            "action": "Verify MCP connection",
            "tool": None,
            "instruction": "Open Cursor MCP panel. Confirm 'comfy-cloud' server is connected and green.",
            "expected_result": "Server shows as connected",
            "completed": False,
        },
        {
            "step": 2,
            "action": "List available tools",
            "tool": None,
            "instruction": "In Cursor, ask: 'List all available MCP tools from comfy-cloud'",
            "expected_result": "Tools list matches: search_templates, search_models, submit_workflow, get_job_status, get_output",
            "completed": False,
        },
        {
            "step": 3,
            "action": "Search for SDXL templates",
            "tool": "search_templates",
            "instruction": "Call search_templates(query='faceless cinematic portrait 9:16 SDXL')",
            "expected_result": "Returns at least one template with workflow JSON",
            "completed": False,
        },
        {
            "step": 4,
            "action": "Search for available models",
            "tool": "search_models",
            "instruction": "Call search_models(query='stable diffusion xl', model_type='checkpoint')",
            "expected_result": "Returns model list including SDXL or similar",
            "completed": False,
        },
        {
            "step": 5,
            "action": "Submit test workflow",
            "tool": "submit_workflow",
            "instruction": (
                f"Submit a minimal test workflow for prompt_generation_id={pg_id}. "
                "Use positive_prompt: 'cinematic B-roll shot, mountain sunrise, no faces, vertical 9:16'. "
                "Use negative_prompt: 'face, person, avatar, nsfw, text'."
            ),
            "expected_result": "Returns job_id",
            "completed": False,
        },
        {
            "step": 6,
            "action": "Poll job status",
            "tool": "get_job_status",
            "instruction": "Call get_job_status(job_id=<id from step 5>). Repeat until status=completed.",
            "expected_result": "status=completed within timeout",
            "completed": False,
        },
        {
            "step": 7,
            "action": "Retrieve outputs",
            "tool": "get_output",
            "instruction": "Call get_output(job_id=<id from step 5>)",
            "expected_result": "Returns list of output file references",
            "completed": False,
        },
        {
            "step": 8,
            "action": "Download and review output image",
            "tool": None,
            "instruction": (
                "Download the output image. Confirm:\n"
                "- No faces or identifiable people\n"
                "- Vertical 9:16 format (1080x1920)\n"
                "- Cinematically usable for leadership inspirational content\n"
                "- Not generic blue/grey gradient stub output"
            ),
            "expected_result": "Image passes quality checklist",
            "completed": False,
        },
        {
            "step": 9,
            "action": "Create renderer_validation_run in SignalForge",
            "tool": None,
            "instruction": (
                f"POST /renderer-validation-runs with "
                f"prompt_generation_id={pg_id}, renderer_type=comfyui_cloud, "
                "test_mode=true, workspace_slug=" + workspace_slug
            ),
            "expected_result": "Validation run created, status=pending",
            "completed": False,
        },
        {
            "step": 10,
            "action": "Review validation run",
            "tool": None,
            "instruction": (
                "After downloading and reviewing images, call "
                "POST /renderer-validation-runs/{id}/review with "
                "decision=approve_as_usable or needs_revision."
            ),
            "expected_result": "Human review decision stored, usable_for_final set",
            "completed": False,
        },
    ]

    safety_checks = [
        {"check": "No faces or identifiable people in output", "required": True},
        {"check": "No avatar or digital likeness", "required": True},
        {"check": "No voice cloning or lip sync", "required": True},
        {"check": "Original audio preserved (not generated)", "required": True},
        {"check": "Output stays at needs_review — not auto-approved", "required": True},
        {"check": "No publishing, scheduling, or social API calls", "required": True},
        {"check": "simulation_only=true on all records", "required": True},
        {"check": "outbound_actions_taken=0 on all records", "required": True},
        {"check": "API key not logged or returned in UI", "required": True},
    ]

    quality_gates = [
        {"gate": "Image is faceless (no person visible)", "pass": False},
        {"gate": "Image is vertical 9:16 (1080x1920)", "pass": False},
        {"gate": "Image is not a generic gradient/stub", "pass": False},
        {"gate": "Image matches the scene beat prompt", "pass": False},
        {"gate": "Image is cinematically usable for leadership content", "pass": False},
        {"gate": "All 6 scene beats produce distinct visuals", "pass": False},
        {"gate": "Generated images assemble into a usable MP4 with original audio", "pass": False},
        {"gate": "Human reviewer marks usable_for_final=true", "pass": False},
    ]

    return {
        "prompt_generation_id": pg_id,
        "workspace_slug": workspace_slug,
        "positive_prompt_preview": positive_preview + ("..." if len(positive_preview) == 100 else ""),
        "negative_prompt_preview": negative_preview + ("..." if len(negative_preview) == 100 else ""),
        "scene_beat_count": scene_beat_count,
        "plan_steps": plan_steps,
        "safety_checks": safety_checks,
        "quality_gates": quality_gates,
        "mcp_tools_needed": ["search_templates", "search_models", "submit_workflow", "get_job_status", "get_output"],
        "note": (
            "This plan is for operator-guided MCP validation. "
            "Complete all steps before approving Comfy Cloud for final production use."
        ),
        "simulation_only": True,
        "outbound_actions_taken": 0,
    }
