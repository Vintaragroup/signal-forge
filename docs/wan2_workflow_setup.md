# Wan2.1 Workflow Setup Guide

## Overview

This guide covers setting up [Wan2.1](https://github.com/Wan-Video/Wan2.1) text-to-video and image-to-video pipelines inside ComfyUI for use with SignalForge's `comfyui_real` renderer backend.

Wan2.1 is a state-of-the-art open-weight video generation model from Alibaba. It supports:
- **T2V** (Text to Video) — generate short clips from a text description
- **I2V** (Image to Video) — animate a still image into a short clip

SignalForge uses the generated frames as cinematic B-roll for leadership content. **No faces, no identifiable people, no avatar or likeness generation.**

---

## GPU / VRAM Requirements

| Model Variant | Recommended VRAM | Notes |
|---|---|---|
| Wan2.1-T2V-1.3B (tiny) | 8 GB | Fast; lower quality |
| Wan2.1-T2V-14B (standard) | 24 GB | Full quality, 720p |
| Wan2.1-I2V-14B | 24 GB | Image-to-video |
| Wan2.1-T2V-14B (fp8 quant) | 16 GB | Quantized, ~720p |

For production SignalForge renders at 1080×1920 (portrait 9:16), **24 GB+ VRAM** is strongly recommended.

If you have less VRAM:
- Use `fp8` or `gguf` quantized checkpoints
- Enable `--lowvram` in your ComfyUI launch command
- Use the 1.3B variant for drafts, 14B for finals

---

## Model Download

### From Hugging Face

```bash
# Standard T2V checkpoint (14B fp16)
huggingface-cli download Wan-AI/Wan2.1-T2V-14B \
  --local-dir ./models/checkpoints/wan2.1-t2v-14b

# Or quantized fp8 (smaller)
huggingface-cli download Wan-AI/Wan2.1-T2V-14B-fp8 \
  --local-dir ./models/checkpoints/wan2.1-t2v-14b-fp8
```

### Model Placement in ComfyUI

Place model files under your ComfyUI `models/` directory:

```
ComfyUI/
  models/
    checkpoints/
      wan2.1-t2v-14b/       ← Wan2.1 checkpoint folder
        ...
    vae/
      wan_2.1_vae.safetensors
    clip/
      umt5-xxl-enc-bf16.safetensors   ← Text encoder
```

> **Note:** The VAE and text encoder (UMT5) are required separately. Download links are on the [Wan2.1 HuggingFace page](https://huggingface.co/Wan-AI).

---

## Required ComfyUI Custom Nodes

Install via [ComfyUI Manager](https://github.com/ltdrdata/ComfyUI-Manager):

| Node Pack | Purpose |
|---|---|
| **ComfyUI-VideoHelperSuite** | Video loading/saving (VHS) |
| **ComfyUI-WanVideoWrapper** | Wan2.1 native model loader |
| **ComfyUI_FizzNodes** | Prompt scheduling (optional) |

Install command (if using git directly):

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite
git clone https://github.com/kijai/ComfyUI-WanVideoWrapper
```

---

## Testing ComfyUI Outside SignalForge

Before connecting SignalForge, verify your ComfyUI setup independently:

1. Start ComfyUI:
   ```bash
   cd ComfyUI
   python main.py --port 8188 --preview-method auto
   ```

2. Open `http://localhost:8188` in your browser.

3. Load the example Wan2.1 workflow (included in ComfyUI examples or the WanVideoWrapper repo).

4. Run a test generation:
   - **Positive prompt:** `golden hour over mountains, cinematic B-roll, no people, symbolic leadership imagery, vertical 9:16`
   - **Negative prompt:** `realistic face, identifiable person, avatar, blurry, low quality`
   - **Resolution:** 1080×1920 (portrait)
   - **Steps:** 25–40

5. Confirm output video appears in `ComfyUI/output/`.

---

## Exporting a Workflow for SignalForge

SignalForge uses ComfyUI's **API-format** workflow JSON (not the UI format).

To export from the ComfyUI browser UI:
1. Open your working workflow in ComfyUI (`http://localhost:8188`)
2. Click **Settings** (gear icon) → Enable **Dev Mode**
3. Click **Save (API format)** — this exports the workflow as `workflow_api.json`
4. Add prompt injection markers to your CLIPTextEncode nodes:
   - Set the positive CLIPTextEncode text to: `{{positive_prompt}}`
   - Set the negative CLIPTextEncode text to: `{{negative_prompt}}`
   - SignalForge will replace these with per-scene-beat prompts at render time

---

## Prompt Injection Markers

SignalForge automatically injects scene-beat prompts into the workflow at render time.

Add these placeholder strings to your workflow's CLIPTextEncode nodes:

```json
{
  "6": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "{{positive_prompt}}",
      "clip": ["4", 1]
    }
  },
  "7": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "{{negative_prompt}}",
      "clip": ["4", 1]
    }
  }
}
```

If markers are **not present**, SignalForge falls back to patching the first two CLIPTextEncode nodes in the workflow (first = positive, second = negative).

---

## Connecting SignalForge

Once your workflow is tested and exported, configure these environment variables in `docker-compose.yml` or your `.env`:

```yaml
environment:
  COMFYUI_ENABLED: "true"
  COMFYUI_BASE_URL: "http://comfyui:8188"   # or http://host.docker.internal:8188 if running locally
  COMFYUI_RENDERER_TYPE: "comfyui_real"
  COMFYUI_WORKFLOW_PATH: "/app/workflows/wan2.1_t2v_signalforge.json"
  COMFYUI_MODEL_CHECKPOINT: "wan2.1-t2v-14b"
  COMFYUI_FORCE_PORTRAIT: "true"            # patch EmptyLatentImage to 1080x1920
  COMFYUI_FALLBACK_ALLOWED: "false"         # fail loudly if workflow not found
```

Mount your workflow JSON into the container:

```yaml
volumes:
  - ./workflows/wan2.1_t2v_signalforge.json:/app/workflows/wan2.1_t2v_signalforge.json:ro
```

---

## Image-to-Video (I2V) Mode

For I2V, the ComfyUI workflow includes a `LoadImage` or `VHS_LoadImageBatch` node as a reference frame. SignalForge can supply the first generated still frame as the input image.

Set `COMFYUI_WORKFLOW_PATH` to an I2V workflow that accepts:
- `{{positive_prompt}}` for motion/scene description
- A `LoadImage` node (you patch `image_path` per scene beat in the workflow)

This mode is optional and requires custom integration beyond the default Phase 10 scope.

---

## Faceless Content Policy

SignalForge enforces strict faceless rendering on every prompt:

- `_FACELESS_SUFFIX` is always appended to positive prompts
- `_SAFETY_NEGATIVE` always included in negative prompts
- Explicitly blocked: `realistic face`, `recognizable likeness`, `identifiable person`, `avatar`, `voice cloning`

**Do not remove these safety terms from your workflow.** SignalForge will re-inject them even if your workflow's CLIPTextEncode nodes include competing text.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `COMFYUI_WORKFLOW_PATH does not exist` | Check path is mounted into Docker and env var matches exactly |
| `No prompt_id in response` | ComfyUI server not running or wrong port |
| Blue placeholder rendered | `COMFYUI_ENABLED=false` or renderer fell back to stub |
| OOM / CUDA out of memory | Use fp8 checkpoint, lower resolution, or reduce batch size |
| 504 timeout polling history | Increase `COMFYUI_POLL_MAX_WAIT_S` env var (default 120s) |

---

## See Also

- [Wan2.1 GitHub](https://github.com/Wan-Video/Wan2.1)
- [ComfyUI-WanVideoWrapper](https://github.com/kijai/ComfyUI-WanVideoWrapper)
- [ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite)
- [SignalForge ARCHITECTURE.md](../ARCHITECTURE.md)
- [SignalForge docs/setup.md](setup.md)
