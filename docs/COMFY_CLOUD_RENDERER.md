# Comfy Cloud Renderer

Phase 11 — Comfy Cloud + MCP Renderer Validation Layer

---

## Overview

`comfyui_cloud_client.py` provides a **Comfy Cloud** renderer adapter for SignalForge.

This renderer submits ComfyUI workflows to the [official Comfy Cloud API](https://cloud.comfy.org) instead of a local ComfyUI instance.

**Key properties:**
- Requires a Comfy Cloud subscription and API key
- Disabled by default (`COMFY_CLOUD_ENABLED=false`)
- All runs are `simulation_only=True`, `outbound_actions_taken=0`
- API key is **never** logged, returned in responses, shown in UI, or committed to code
- No social publishing, scheduling, or DMs — ever

---

## Renderer Types

| Type | Description |
|---|---|
| `comfyui_stub` | Built-in Pillow test stub — no real generation |
| `comfyui_real` | Local ComfyUI instance (requires `COMFYUI_WORKFLOW_PATH`) |
| `comfyui_cloud` | Comfy Cloud API (requires subscription + API key) |
| `external_manual` | Operator-supplied frames, no HTTP calls |

---

## Resolution Order

1. `COMFYUI_RENDERER_TYPE` env var (explicit override)
2. `COMFY_CLOUD_ENABLED=true` → `comfyui_cloud`
3. `COMFYUI_WORKFLOW_PATH` set + `COMFYUI_ENABLED=true` → `comfyui_real`
4. `COMFYUI_ENABLED=true` but no workflow path → `comfyui_stub` (with warning)
5. `COMFYUI_ENABLED=false` → `comfyui_stub` (mock result)

---

## Environment Variables

```bash
# Enable Comfy Cloud renderer (requires subscription)
COMFY_CLOUD_ENABLED=false

# Comfy Cloud API base URL
COMFY_CLOUD_BASE_URL=https://cloud.comfy.org

# Your Comfy Cloud API key — NEVER commit this value
COMFY_CLOUD_API_KEY=

# Path to cloud ComfyUI workflow JSON file
COMFY_CLOUD_WORKFLOW_PATH=

# Cloud provider name (for logging/diagnostics)
COMFY_CLOUD_PROVIDER=official

# Timeout in seconds for cloud job polling
COMFY_CLOUD_TIMEOUT_SECONDS=600

# Allow fallback to comfyui_stub if cloud config is invalid
COMFY_CLOUD_FALLBACK_ALLOWED=false
```

---

## API Endpoints

### `GET /renderer-validation/diagnostics`
Returns cloud renderer configuration status. **API key is never returned** — only `api_key_configured: true/false`.

### `POST /renderer-validation-runs`
Create a renderer validation run record.

**Request body:**
```json
{
  "workspace_slug": "john-maxwell-pilot",
  "client_id": "...",
  "prompt_generation_id": "...",
  "renderer_type": "comfyui_cloud",
  "workflow_path": "",
  "notes": "Testing cloud renderer",
  "test_mode": true
}
```

### `GET /renderer-validation-runs`
List validation runs. Filters: `workspace_slug`, `renderer_type`, `status`.

### `POST /renderer-validation-runs/{id}/review`
Submit a review decision.

```json
{
  "decision": "approve_as_usable",
  "quality_score": 8.5,
  "quality_notes": "Cinematic, faceless, matches script.",
  "usable_for_final": true
}
```

Valid decisions: `approve_as_usable` | `needs_revision` | `reject`

---

## Security

- `COMFY_CLOUD_API_KEY` is stored in memory only during runtime
- Never logged, never returned in API responses, never shown in UI
- `X-API-Key` header is used for authentication with Comfy Cloud
- All diagnostics return `api_key_configured: true/false` only

---

## Workflow Format

Cloud workflows use the same ComfyUI API-format JSON as local workflows.

Prompt injection uses `{{positive_prompt}}` / `{{negative_prompt}}` markers:

```json
{
  "1": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "{{positive_prompt}}"
    }
  },
  "2": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "{{negative_prompt}}"
    }
  }
}
```

The safety negative prompt (`_FACELESS_SUFFIX`) is **always appended** to the negative prompt regardless of cloud/local renderer.

---

## Job Lifecycle

1. `POST {COMFY_CLOUD_BASE_URL}/api/prompt` — submit workflow
2. `GET /api/job/{id}/status` — poll until `completed/success/done/finished`
3. `GET /api/jobs/{id}` — fetch output references
4. `GET /api/view?filename=...` — download output images

Output files are saved locally as `{render_id}_cloud_frame_{N:03d}.png`.

---

## Quality Gate

All renderer validation runs require human review before being marked usable:

- [ ] Output image is faceless (no identifiable person)
- [ ] Matches scene beat description
- [ ] Cinematic quality
- [ ] Not a stub test image
- [ ] Operator marks `usable_for_final=true`

Human review is required — runs are never auto-approved.
