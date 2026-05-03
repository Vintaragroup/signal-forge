# Docker

## Services

```bash
docker compose up --build
```

## API

The API is exposed on port `8000`.

```bash
curl http://localhost:8000/health
```

## Run A Single Worker

```bash
docker compose run --rm lead_scraper
docker compose run --rm lead_enricher
docker compose run --rm social_processor
docker compose run --rm post_generator
```

## MongoDB

MongoDB is exposed locally on port `27017`.

Default internal URI:

```text
mongodb://mongo:27017/signalforge
```

Default host URI:

```text
mongodb://localhost:27017/signalforge
```

Mongo data is stored in the named Docker volume `signalforge_mongo-data`.

## Vault Mount

Every service mounts:

```text
./vault:/vault
```

Services should read prompts from `/vault/prompts` and write human-readable outputs into the appropriate vault folder.

## Redis Service

Redis is used as the render job queue for the Social Creative Engine v5 pipeline.

```bash
# Verify Redis is healthy
docker compose exec redis redis-cli ping
# → PONG

# Check queue depth
docker compose exec redis redis-cli llen signalforge:render_jobs

# Inspect dead-letter queue
docker compose exec redis redis-cli lrange signalforge:render_jobs_failed 0 -1
```

## Worker Service

The worker container (`signalforge-worker`) uses the same Docker image as the API but runs `python worker.py` instead of `uvicorn`. It polls Redis for render jobs and processes them through the ComfyUI → FFmpeg pipeline.

```bash
# View worker logs
docker compose logs -f worker

# Restart worker after code change
docker compose build api && docker compose restart worker

# Run one job then exit (smoke test)
docker compose exec worker python worker.py --once
```

## ComfyUI Service (Optional Profile)

ComfyUI is not started by default. Enable it with the `comfyui` Docker Compose profile:

```bash
# Start with ComfyUI stub (local dev)
docker compose --profile comfyui up -d

# Stop and remove ComfyUI container
docker compose --profile comfyui down
```

`COMFYUI_ENABLED=false` (default) means the worker uses the mock render path even if the container is running. Set `COMFYUI_ENABLED=true` in `.env` to route real ComfyUI calls to the service.

## Render Output Volume

The `render-output` Docker volume is shared between the api and worker containers at `/tmp/signalforge_renders`. With `FFMPEG_ENABLED=true` (default in v5.5), real `.mp4` files, test-tone `.wav` files, and placeholder `.png` files are written here. With `COMFYUI_ENABLED=true` (v6), ComfyUI-generated `.png` images are also saved here before being passed to FFmpeg assembly.

```bash
# Inspect rendered files (from api container)
docker compose exec api ls -lh /tmp/signalforge_renders/

# Verify FFmpeg binary is installed in both containers
docker compose exec api ffmpeg -version
docker compose exec worker ffmpeg -version

# Check FFmpeg health via API
curl http://localhost:8000/health/ffmpeg

# Check ComfyUI health via API (v6)
curl http://localhost:8000/health/comfyui

# Watch worker logs for startup diagnostics
docker compose logs worker | grep -iE "ffmpeg|comfyui"
```

## v5.5 / v6 Rebuild Requirements

When updating Python files (video_assembler.py, worker.py, main.py, comfyui_client.py), **both** api and worker images must be rebuilt:

```bash
docker compose build --no-cache api worker
docker compose up -d
```

> The api and worker containers share the same Dockerfile but produce separate images. Rebuilding `api` does not rebuild `worker`.

## v7 Rebuild Requirements / Whisper Notes

`openai-whisper` is installed from `requirements.txt` during the Docker build — no separate container or service is required. It runs inside the existing `signalforge-api` container. FFmpeg is already present from v5.5.

When updating `transcript_provider.py`, `main.py`, or `requirements.txt`, rebuild both images:

```bash
docker compose build --no-cache api worker
docker compose up -d
```

**Verify Whisper is importable:**
```bash
docker compose exec api python -c "import whisper; print(whisper.__version__)"
```

**First-use model download:** The Whisper `base` model (~140 MB) is downloaded from the internet on first transcription call. Pre-warm it in a running container to avoid latency on first request:
```bash
docker compose exec api python -c "import whisper; whisper.load_model('base')"
```

**Available model sizes** (trade-off: accuracy vs. RAM/speed):

| WHISPER_MODEL | VRAM  | Relative speed |
|---------------|-------|----------------|
| tiny          | ~1 GB | fastest        |
| base          | ~1 GB | fast (default) |
| small         | ~2 GB | moderate       |
| medium        | ~5 GB | slow           |
| large         | ~10 GB| slowest        |

**Enabling live transcription** (both env vars required):
```bash
TRANSCRIPT_PROVIDER=whisper
TRANSCRIPT_LIVE_ENABLED=true
```
If either gate is absent, the provider silently falls back to stub mode. No rebuild is needed to change these env vars — a container restart (`docker compose up -d`) is sufficient.

## ComfyUI Integration (v6)

ComfyUI generates the background image that is fed into FFmpeg assembly. It is **disabled by default** and runs behind a Docker profile.

### Enabling the ComfyUI stub (no GPU required)

The stub is a pure-Python FastAPI server that accepts ComfyUI API calls and returns a minimal dark-purple PNG. Use this to verify the full pipeline without a real ComfyUI installation.

```bash
# Start the full stack including the ComfyUI stub
COMFYUI_ENABLED=true docker compose --profile comfyui up -d

# Verify the stub is healthy
curl http://localhost:8188/system_stats

# Check ComfyUI connectivity from the API
curl http://localhost:8000/health/comfyui
```

The stub supports:
- `GET /system_stats` — health check
- `POST /prompt` — accepts any workflow JSON, returns a `prompt_id`, generates a PNG
- `GET /history/{prompt_id}` — returns immediately completed with image filename
- `GET /view?filename=...&type=output` — returns PNG image bytes

### Using a real ComfyUI instance

To connect a real local ComfyUI running outside Docker (e.g. `http://127.0.0.1:8188`):

```bash
COMFYUI_ENABLED=true \
COMFYUI_BASE_URL=http://host.docker.internal:8188 \
docker compose up -d api worker
```

Required ComfyUI setup:
1. ComfyUI running on port 8188 with the API server enabled
2. A checkpoint model installed (configure via `COMFYUI_MODEL_CHECKPOINT` env var, defaults to `v1-5-pruned-emaonly.safetensors`)
3. The `render-output` volume path accessible (images download to `/tmp/signalforge_renders`)

GPU is recommended but not required. The stub uses CPU.

### Environment variables (v6)

| Variable | Default | Description |
|---|---|---|
| `COMFYUI_ENABLED` | `false` | Enable ComfyUI image generation |
| `COMFYUI_BASE_URL` | `http://comfyui:8188` | ComfyUI endpoint URL |
| `COMFYUI_WORKFLOW_PATH` | _(empty)_ | Path to custom workflow JSON; if empty, auto-built from prompt_generation |
| `COMFYUI_MODEL_CHECKPOINT` | `v1-5-pruned-emaonly.safetensors` | Checkpoint model name |

### Fallback behavior

When `COMFYUI_ENABLED=true` but ComfyUI is unreachable or returns an error:
- The worker falls back to the FFmpeg-generated placeholder image
- `image_source` is set to `"placeholder"` (not `"comfyui"`)
- `comfyui_partial_failure: true` is recorded on the render
- `comfyui_result.fallback_reason` contains the error description
- Assembly still proceeds — the render reaches `needs_review`, **not** `failed`
- `simulation_only: true` and `outbound_actions_taken: 0` are always maintained

## Disabling FFmpeg (revert to mock)

## Disabling FFmpeg (revert to mock)

```bash
FFMPEG_ENABLED=false docker compose up -d
# OR
echo "FFMPEG_ENABLED=false" >> .env && docker compose up -d
```
