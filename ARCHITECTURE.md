# Architecture

> **Version:** v10 (POC Demo Mode)  
> **Last updated:** May 2026  
> **Status:** Local-first, single-operator, pre-production  
> See [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md) for hardening requirements before multi-user or client-hosted deployment.

## System Overview

SignalForge is a local-first AI-assisted content production and CRM-lite operating system. A FastAPI control plane, a React dashboard, MongoDB, Redis, and an FFmpeg worker together form the core runtime. Operators manage leads, outreach drafts, creative assets, client campaigns, and intelligent pipeline analytics — all locally, all review-gated, with no automated outbound sends.

## Runtime Stack

```text
                       ┌─────────────────────────────────────────┐
                       │           Operator Browser               │
                       │    React 19 + Vite  (localhost:5174)     │
                       │    Real Mode (blue) / Demo Mode (purple) │
                       └───────────────┬─────────────────────────┘
                                       │ HTTP (localhost:8000)
                       ┌───────────────▼─────────────────────────┐
                       │        FastAPI Control Plane             │
                       │   services/api/main.py  (~104 endpoints) │
                       │   Python 3.11  |  signalforge-api        │
                       └────┬───────────────────────┬────────────┘
                            │                       │
              ┌─────────────▼──────┐   ┌────────────▼────────────┐
              │      MongoDB 8     │   │       Redis 7            │
              │  signalforge-mongo │   │  signalforge-redis       │
              │  structured data   │   │  async render job queue  │
              └─────────────┬──────┘   └────────────┬────────────┘
                            │                       │
              ┌─────────────▼──────────────────────▼────────────┐
              │               FFmpeg Worker                       │
              │  signalforge-worker  (same image as api)          │
              │  polls Redis → processes renders → writes volume  │
              └───────────────────────────────────────────────────┘
                            │
              ┌─────────────▼──────┐
              │   /vault markdown  │
              │  Obsidian-readable │
              │  human audit layer │
              └────────────────────┘

  ─ ─ ─ ─ Optional (profile-gated) ─ ─ ─ ─
              ┌────────────────────┐
              │     ComfyUI        │
              │ docker profile:    │
              │   comfyui          │
              │ COMFYUI_ENABLED=   │
              │   false (default)  │
              └────────────────────┘
```

## Service Descriptions

### api — FastAPI Control Plane (core)

The primary runtime service. Implements all 104 HTTP endpoints spanning the full pipeline:
- Lead / contact / CRM management
- Message drafting, review, and approval queue
- Agent task queue and GPT-gated agent runtime
- Creative Studio: client profiles, source channels, content ingestion, transcription, snippet scoring, prompt generation, asset rendering
- Performance feedback loop: publish logs, performance records, summaries
- Campaign packs, reports, and exports
- Client intelligence (v9.5): deterministic ROI/correlation analytics
- Tool layer: read-only mock web search, website scraping, manual CSV import
- Workspace isolation and mode switching
- Full GPT diagnostics

No auth/RBAC layer exists. Single-operator, local-only assumed.

### web — React Dashboard (core)

Vite 6 + React 19 SPA served by Nginx in Docker. Dashboard pages:

| Page | Purpose |
|---|---|
| Overview | System status, pipeline health |
| Pipeline / CRM | Leads, contacts, lifecycle tracking |
| Messages | Draft review and approval |
| Approvals | Approval queue for GPT/agent requests |
| Agent Tasks | Queue, run, and observe agent tasks |
| Agents | Agent console (simulation-only dry runs) |
| Research / Tools | Tool runs, CSV import, candidate review |
| GPT Diagnostics | GPT runtime health without key exposure |
| Deals | Deal outcome tracking |
| Reports | Pipeline and revenue reports |
| Creative Studio | Full social creative pipeline (v2–v10) |
| Demo Mode | POC demo walkthrough entry point |

Operates in **Real Mode** (MongoDB-backed) or **Demo Mode** (browser localStorage only, zero backend writes).

### mongo — MongoDB 8 (core)

Primary structured data store. Collections span the full pipeline. The Obsidian vault at `/vault` provides human-readable markdown mirrors of key records.

### redis — Redis 7 (core)

Job queue for async render handoff. The worker polls Redis for queued render jobs. If Redis is unreachable, the API falls back to synchronous inline rendering.

### worker — FFmpeg Worker (core)

Same Docker image as `api`. Polls Redis, processes render jobs (`queued → running → generated → needs_review | failed`). Writes `.mp4` files to the shared `render-output` volume. `FFMPEG_ENABLED=true` is the default; mock renders are available when disabled.

### comfyui — ComfyUI Image Generator (optional, profile-gated)

Local image/video generation for the Creative Studio asset pipeline. Not started by default.

```bash
docker compose --profile comfyui up -d
```

A pure-Python stub server is included for local development (no GPU required). Set `COMFYUI_ENABLED=true` in `.env` to activate. Communicates only with `host.docker.internal:8188` — no external image APIs.

### lead_scraper — Contractor Lead Engine (one-off / CLI)

Imports structured contractor listings from local JSON into MongoDB. Runs as a one-off CLI process, not a continuously-running service.

```bash
./scripts/run_daily_pipeline.sh --business-type "roofing contractor" --location "Austin, TX"
```

### lead_enricher — Contractor Enrichment Engine (one-off / CLI)

Applies deterministic v3 intelligence scoring to contractor leads. Writes enriched records to MongoDB and markdown notes to `/vault/review_queue`. Runs as a one-off CLI process.

### social_processor — Social Signal Processor (placeholder / scaffold)

Scaffold service only. Entrypoint prints its role and exits with `"Placeholder run complete."`. Real ingestion and signal classification are not implemented.

### post_generator — Content Generation Service (placeholder / scaffold)

Scaffold service only. Entrypoint prints its role and exits with `"Placeholder run complete."`. Real content generation is not implemented. Content drafting is handled through the Creative Studio pipeline in the API.

## Data Flow

### CRM / Outreach Pipeline

```text
Local structured data (JSON/CSV)
  → lead_scraper (CLI)
  → MongoDB (leads, contacts)
  → lead_enricher (CLI)
  → MongoDB (enriched records, review queue)
  → Operator review via dashboard or CLI scripts
  → Message drafts → approval queue → manual send logging
  → Response logging → deal tracking → reports
  → /vault markdown (audit layer)
```

### Creative Studio Pipeline (v2–v10)

```text
Operator adds client profile + source channels
  → Source content ingestion (status-gated)
  → Transcription (Whisper local / stub)
  → Snippet scoring (deterministic, local)
  → Prompt generation (operator review required)
  → Asset rendering: Redis → Worker → FFmpeg → /tmp/renders
  → ComfyUI image generation (optional, local only)
  → Operator review → Campaign packs → Reports → Exports
  → Performance feedback: publish logs → performance records → summaries
  → Client intelligence: ROI/correlation analytics (advisory only)
```

### POC Demo Mode (v10)

```text
Browser localStorage only
  → demoMode.js seed data (8 collections, ~40+ synthetic records)
  → PocDemoTab.jsx 13-step guided walkthrough
  → api.js demo branches (no fetch calls in demo mode)
  → Zero MongoDB writes, zero backend calls for reads
  → Real endpoints always filter is_demo:true records
```

## Environment Variable Gates

| Variable | Default | Effect |
|---|---|---|
| `FFMPEG_ENABLED` | `true` | Real local FFmpeg renders; `false` = mock renders |
| `COMFYUI_ENABLED` | `false` | ComfyUI image generation; `true` requires running ComfyUI |
| `COMFYUI_BASE_URL` | `http://host.docker.internal:8188` | ComfyUI endpoint |
| `GPT_AGENT_ENABLED` | `false` | OpenAI-powered agent planning; requires `OPENAI_API_KEY` |
| `OPENAI_API_KEY` | *(unset)* | Required when `GPT_AGENT_ENABLED=true` |
| `TRANSCRIPT_PROVIDER` | `stub` | `whisper` = local Whisper transcription |
| `TRANSCRIPT_LIVE_ENABLED` | `false` | Double gate for real transcription |
| `SNIPPET_SCORE_THRESHOLD` | `6.0` | Quality gate for snippet → prompt generation |
| `AUTO_SCORE_SNIPPETS` | `false` | Auto-run scoring after snippet generation |

## Design Principles

- **Local-first.** All data lives on the operator's machine. No external APIs are called by default.
- **Review-gated.** Every pipeline stage that produces outbound-relevant content requires explicit operator approval before proceeding.
- **No automated sends.** SignalForge never sends email, SMS, DMs, social posts, or calendar events. Manual send logging exists to track operator-performed sends.
- **Simulation-only agents.** Agent and GPT outputs produce drafts and approval requests only. No agent action results in an outbound event without explicit operator action outside the system.
- **Vault as audit layer.** Key records are mirrored to `/vault` as human-readable markdown accessible in Obsidian.
- **Safety invariants.** All pipeline records carry `simulation_only: true` and `outbound_actions_taken: 0`. Demo records carry `is_demo: true` and are never returned by real-mode endpoints.

## Service Maturity Summary

| Service | Type | Status |
|---|---|---|
| `api` | Core runtime | Production-implemented (local) |
| `web` | Core runtime | Production-implemented (local) |
| `mongo` | Core runtime | Production-implemented (local) |
| `redis` | Core runtime | Production-implemented (local) |
| `worker` | Core runtime | Production-implemented (local) |
| `comfyui` | Optional / profile-gated | Stub included; real GPU optional |
| `lead_scraper` | One-off / CLI | Real (contractor listings only) |
| `lead_enricher` | One-off / CLI | Real (contractor enrichment only) |
| `social_processor` | Placeholder / scaffold | Not implemented |
| `post_generator` | Placeholder / scaffold | Not implemented |

See [docs/SERVICE_BOUNDARIES.md](docs/SERVICE_BOUNDARIES.md) for full inter-service dependency and startup requirements.  
See [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md) for hardening requirements before multi-user deployment.
