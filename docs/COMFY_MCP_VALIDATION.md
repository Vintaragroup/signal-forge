# Comfy MCP Validation

Phase 11 — MCP Validation Helper for Comfy Cloud

---

## Overview

`comfyui_mcp_validation.py` provides a **planning and discovery tool** for the Comfy Cloud MCP (Model Context Protocol) server.

**This is NOT a production rendering path.**

MCP validation is used by operators to:
- Plan and checklist AI-assisted workflow development
- Discover available MCP tools
- Generate step-by-step validation plans before enabling cloud rendering

---

## What MCP Validation Is NOT

- It does NOT submit render jobs
- It does NOT make live calls to MCP (static manifest only)
- It does NOT store or return API keys
- It does NOT post, publish, schedule, or trigger outbound actions

---

## Environment Variables

```bash
# Enable MCP validation (early access — disabled by default)
COMFY_MCP_ENABLED=false

# Comfy Cloud MCP server URL
COMFY_MCP_URL=https://cloud.comfy.org/mcp

# MCP API key — NEVER commit this value
COMFY_MCP_API_KEY=

# Safety: restrict to validation only (do not use MCP for production rendering)
COMFY_MCP_VALIDATION_ONLY=true
```

---

## Available MCP Tools (Static Manifest)

| Tool | Description |
|---|---|
| `search_templates` | Search available ComfyUI workflow templates |
| `search_models` | Search available model checkpoints |
| `submit_workflow` | Submit a workflow to Comfy Cloud |
| `get_job_status` | Poll job status by prompt_id |
| `get_output` | Retrieve output image references |

---

## MCP Validation Plan

The `create_mcp_validation_plan(prompt_generation)` function returns a 10-step operator-guided validation plan:

1. Confirm MCP server is reachable
2. Authenticate with API key (verify 200 response)
3. Call `search_templates` — verify template list returned
4. Call `search_models` — verify model list returned
5. Select workflow template matching content type
6. Inject test prompts using faceless safety suffix
7. Submit via `submit_workflow`
8. Poll via `get_job_status` until completed
9. Download outputs via `get_output`
10. Perform human quality review (faceless, cinematic, matches script)

**Safety checks included:**
- No identifiable person in output
- No watermarks
- No explicit content
- Faceless prompt enforced
- Human review required before marking usable

---

## Cursor MCP Configuration

To use Comfy Cloud MCP with Cursor or Claude Code, add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "comfy-cloud": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://cloud.comfy.org/mcp",
        "--header",
        "X-API-Key: YOUR_KEY_HERE"
      ]
    }
  }
}
```

> ⚠️ **Warning:** Do NOT commit `.cursor/mcp.json` with your API key. Add it to `.gitignore`.

---

## API Endpoint

### `GET /renderer-validation/diagnostics`

Returns MCP configuration status. **API key is never returned.**

```json
{
  "mcp": {
    "mcp_enabled": false,
    "mcp_url": "https://cloud.comfy.org/mcp",
    "api_key_configured": false,
    "validation_only": true,
    "ready": false,
    "errors": ["COMFY_MCP_API_KEY not set"],
    "warnings": []
  }
}
```

---

## Safety

- `COMFY_MCP_API_KEY` is never returned in any API response
- `api_key_configured: true/false` only
- `COMFY_MCP_VALIDATION_ONLY=true` by default — prevents production use of MCP path
- All validation runs are `simulation_only=True`, `outbound_actions_taken=0`
