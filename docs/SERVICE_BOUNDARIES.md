# Service Boundaries

> **SignalForge v10**  
> Last updated: May 2026  
> See [ARCHITECTURE.md](../ARCHITECTURE.md) for the full system diagram and data flow.

This document describes which services are core, optional, one-off, or placeholder, what each service requires to run, and which services must be running for full pipeline operation and E2E validation.

---

## Service Categories

### Core Runtime Services

These services must be running for normal dashboard and API operation. Start them all with:

```bash
docker compose up -d
# or
make up
```

| Service | Container | Port | Purpose |
|---|---|---|---|
| `api` | `signalforge-api` | `8000` | FastAPI control plane — all 104 endpoints |
| `web` | `signalforge-web` | `5174` | React 19 + Vite 6 dashboard |
| `mongo` | `signalforge-mongo` | `27017` | MongoDB 8 — primary data store |
| `redis` | `signalforge-redis` | `6379` | Redis 7 — async render job queue |
| `worker` | `signalforge-worker` | *(internal)* | FFmpeg render worker |

**Startup order dependency:**
- `mongo` must be healthy before `api` and `worker` start (health check in compose file)
- `redis` must be reachable before render jobs can be queued (graceful inline fallback if unavailable)
- `api` must be running for `web` to serve meaningful data

---

### Optional / Profile-Gated Services

These services are not started by default. They extend core functionality when enabled.

#### comfyui — Local Image Generation

```bash
# Start with the comfyui profile
docker compose --profile comfyui up -d

# Enable in .env
COMFYUI_ENABLED=true
COMFYUI_BASE_URL=http://host.docker.internal:8188
COMFYUI_MODEL_CHECKPOINT=v1-5-pruned-emaonly.safetensors
```

| Detail | Value |
|---|---|
| Container | `signalforge-comfyui` |
| Profile | `comfyui` |
| Default state | Off (`COMFYUI_ENABLED=false`) |
| Stub included | Yes — pure-Python stub accepts ComfyUI API calls without GPU |
| Fallback behavior | If unreachable, worker uses FFmpeg placeholder image; render reaches `needs_review`, not `failed` |

When `COMFYUI_ENABLED=false` (default), all ComfyUI calls are skipped and renders complete with a placeholder image. The stub server (`docker compose --profile comfyui up`) accepts API calls and returns a real PNG without GPU hardware.

---

### One-Off / CLI Services

These services run as on-demand processes, not continuously-running containers. They execute a job and exit.

#### lead_scraper — Contractor Lead Importer

Imports structured contractor listings from local JSON files into MongoDB. Writes to `leads` and `companies` collections.

```bash
# Run via daily pipeline script
./scripts/run_daily_pipeline.sh --business-type "roofing contractor" --location "Austin, TX" --count 5

# Run directly
docker compose run --rm lead_scraper
```

| Detail | Value |
|---|---|
| Type | One-off / CLI |
| Runs continuously | No |
| Real data | Yes (contractor listings from local JSON seed) |
| Output | MongoDB `leads`, `companies`; `/vault/review_queue` markdown notes |

#### lead_enricher — Contractor Enrichment Engine

Applies deterministic v3 scoring and intelligence to contractor leads. Requires `lead_scraper` output to be present in MongoDB.

```bash
docker compose run --rm lead_enricher
```

| Detail | Value |
|---|---|
| Type | One-off / CLI |
| Runs continuously | No |
| Real data | Yes (deterministic scoring, no external API calls) |
| Output | Enriched MongoDB records; `/vault/review_queue` review notes |
| Depends on | `lead_scraper` having run first |

---

### Placeholder / Scaffold Services

These services exist in `docker-compose.yml` and `services/` but are **not functionally implemented**. Their entrypoints print a status message and exit. They do not process real data.

> **Do not rely on these services for any production workflow.** The capabilities they represent are either handled through the API (content drafting, prompt generation) or are planned for future implementation.

#### social_processor

```bash
# Entrypoint behavior:
print("Placeholder run complete. Next step: ingest social events and classify signal relevance.")
```

| Detail | Value |
|---|---|
| Type | Placeholder / scaffold |
| Functional | No |
| Real data | No |
| Replaces | Nothing — social ingestion and signal classification are not implemented |
| Dashboard equivalent | None |

#### post_generator

```bash
# Entrypoint behavior:
print("Placeholder run complete. Next step: generate drafts and write markdown content notes.")
```

| Detail | Value |
|---|---|
| Type | Placeholder / scaffold |
| Functional | No |
| Real data | No |
| Replaces | Nothing — autonomous post generation is not implemented |
| Dashboard equivalent | Creative Studio pipeline handles content generation manually |

---

## Inter-Service Dependencies

```text
                  ┌──────────────────────────────────────────────┐
                  │  CORE RUNTIME (must all be running)           │
                  │                                               │
                  │  mongo ──► api ──► web                        │
                  │     └──────► worker                           │
                  │  redis ──────► api (queue writes)             │
                  │          └──► worker (queue reads)            │
                  └──────────────────────────────────────────────┘
                                    │ optional
                  ┌─────────────────▼────────────────────────────┐
                  │  OPTIONAL (profile-gated)                     │
                  │                                               │
                  │  comfyui ◄── worker (when COMFYUI_ENABLED)    │
                  └──────────────────────────────────────────────┘

  ONE-OFF (CLI, run manually, not continuously running):
    lead_scraper → mongo
    lead_enricher ← mongo (reads leads) → mongo (writes enriched)

  PLACEHOLDER (no real dependencies, exits immediately):
    social_processor
    post_generator
```

---

## Environment Variable Gates

These variables control which optional capabilities are active at runtime:

| Variable | Default | Controls |
|---|---|---|
| `FFMPEG_ENABLED` | `true` | Real local FFmpeg renders in worker |
| `COMFYUI_ENABLED` | `false` | ComfyUI image generation; requires running ComfyUI |
| `GPT_AGENT_ENABLED` | `false` | OpenAI-powered agent planning; requires `OPENAI_API_KEY` |
| `OPENAI_API_KEY` | *(unset)* | Required when `GPT_AGENT_ENABLED=true` |
| `TRANSCRIPT_PROVIDER` | `stub` | `whisper` = local Whisper; `stub` = no-op |
| `TRANSCRIPT_LIVE_ENABLED` | `false` | Second gate required for real transcription |
| `SNIPPET_SCORE_THRESHOLD` | `6.0` | Quality gate for snippet → prompt generation |
| `AUTO_SCORE_SNIPPETS` | `false` | Auto-run snippet scoring after generation |
| `COMFYUI_BASE_URL` | `http://host.docker.internal:8188` | ComfyUI endpoint |
| `COMFYUI_MODEL_CHECKPOINT` | `v1-5-pruned-emaonly.safetensors` | ComfyUI model selection |
| `SIGNALFORGE_EXPORT_DIR` | `/tmp/signalforge_exports` | Campaign export output directory |
| `FFMPEG_OUTPUT_DIR` | `/tmp/signalforge_renders` | FFmpeg render output directory |

---

## E2E Validation Requirements

### Minimum services for full backend test suite

```bash
# All backend tests (678 passing)
docker compose run --rm --no-deps api python -m pytest tests/ -q
```

Required: `api` container with access to `mongo` and `redis`.  
The `--no-deps` flag is used in CI; in practice `make up` must be running for integration tests that hit MongoDB.

### Minimum services for full frontend build

```bash
cd services/web && npm run build
# or
docker compose run --rm web npm run build
```

Required: Node.js environment (inside or outside Docker).  
No backend connection needed for build; frontend tests (vitest) run in isolation.

### Full pipeline E2E (manual walkthrough)

Requires all core runtime services: `api`, `web`, `mongo`, `redis`, `worker`.

```bash
make up        # Start all core services
make dashboard # Open http://localhost:5174
```

ComfyUI is not required for E2E — renders fall back to FFmpeg placeholder images when `COMFYUI_ENABLED=false`.

### POC Demo Mode E2E (no backend required)

The POC Demo Mode 13-step walkthrough requires only the web dashboard (`signalforge-web`). All data is served from browser localStorage. The API container is not required for any demo step read operations.

---

## Quick Reference: Which Services Do I Need?

| Goal | Services needed |
|---|---|
| Run backend tests | `api` + `mongo` + `redis` |
| Run frontend tests / build | Node.js only (no Docker containers) |
| Use the dashboard (real mode) | All core: `api`, `web`, `mongo`, `redis`, `worker` |
| Run the POC demo walkthrough | `web` only (or just a browser + `npm run dev`) |
| Import contractor leads | `mongo` + `lead_scraper` (CLI) + `lead_enricher` (CLI) |
| Render video assets | `api` + `mongo` + `redis` + `worker` |
| Generate ComfyUI images | All core + `comfyui` (profile) + `COMFYUI_ENABLED=true` |
| Use GPT agent planning | All core + `OPENAI_API_KEY` + `GPT_AGENT_ENABLED=true` |
| Use real transcription | All core + `TRANSCRIPT_PROVIDER=whisper` + `TRANSCRIPT_LIVE_ENABLED=true` |
