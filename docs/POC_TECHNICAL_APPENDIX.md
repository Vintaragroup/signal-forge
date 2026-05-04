# SignalForge POC: Technical Appendix

**Document Type:** Technical Reference for POC Evaluation  
**Version:** v10.2  
**Audience:** Technical evaluators, integration leads, DevOps  
**See also:** [ARCHITECTURE.md](../ARCHITECTURE.md), [docs/PRODUCTION_READINESS.md](PRODUCTION_READINESS.md), [docs/SERVICE_BOUNDARIES.md](SERVICE_BOUNDARIES.md)

---

## Runtime Stack

| Service | Technology | Container | Port | Role |
|---------|------------|-----------|------|------|
| API | FastAPI + Python 3.11 | `signalforge-api` | 8000 | Core business logic, ~104 endpoints |
| Web | React 19 + Vite 6 | `signalforge-web` | 5174 | Operator dashboard |
| Database | MongoDB 8 | `signalforge-mongo` | 27017 | All record persistence |
| Queue | Redis 7 | `signalforge-redis` | 6379 | Async render job queue |
| Worker | Python + FFmpeg | `signalforge-worker` | — | Local video assembly |
| ComfyUI | ComfyUI (optional) | disabled by default | 8188 | AI image generation (not used in POC) |

All services run under `docker compose`. No external dependencies required for local operation.

---

## Service Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    SignalForge Runtime                       │
│                                                              │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  Web UI  │───▶│  FastAPI     │───▶│  MongoDB 8       │  │
│  │  :5174   │    │  :8000       │    │  (local volume)  │  │
│  │ React 19 │    │  ~104 routes │    └──────────────────┘  │
│  └──────────┘    └──────┬───────┘                           │
│                         │                                    │
│                   ┌─────▼──────┐    ┌──────────────────┐   │
│                   │  Redis 7   │───▶│  Worker          │   │
│                   │  job queue │    │  FFmpeg assembly  │   │
│                   └────────────┘    └────────┬─────────┘   │
│                                              │              │
│                                     /tmp/signalforge_renders│
│                                     (local filesystem only) │
│                                                              │
│  Optional (disabled by default):                            │
│  ┌──────────────────────────────────┐                       │
│  │ ComfyUI  :8188  (COMFYUI=false)  │                       │
│  └──────────────────────────────────┘                       │
│                                                              │
│  One-off CLI (run manually, not always-on):                 │
│  lead_scraper · lead_enricher                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Flow: Creative Pipeline

```
Operator approves source channel
          ↓
Source content discovered + approved
          ↓
Transcript run created (FFmpeg local, simulation_only=true in demo)
          ↓
Snippets scored (0–1) + operator approves/rejects
          ↓
Prompt generation created per approved snippet (no likeness)
          ↓
Operator approves prompt → render job queued to Redis
          ↓
Worker picks up job → FFmpeg assembles MP4 → writes to /tmp
          ↓
Operator reviews render → approves/rejects
          ↓
Operator posts manually outside SignalForge
          ↓
Operator logs performance metrics back into system
          ↓
Campaign pack bundles all assets
          ↓
Campaign report aggregates performance + recommendations
          ↓
Export package written to /tmp (Markdown or ZIP)
          ↓
Operator delivers export to client manually
          ↓
Client intelligence synthesizes advisory insights
```

---

## Environment Variable Gates

| Variable | Default | Effect |
|----------|---------|--------|
| `COMFYUI_ENABLED` | `false` | Enables ComfyUI image generation service |
| `COMFYUI_URL` | (unset) | Required if ComfyUI enabled |
| `OPENAI_API_KEY` | (unset) | GPT Diagnostics tab; system runs without it |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Web → API connection |

All core pipeline functionality (transcript, snippet scoring, prompt management, render, performance, export) works without any external API keys.

---

## Service Maturity Summary

| Service | Maturity | POC Ready | Notes |
|---------|----------|-----------|-------|
| FastAPI (api) | Core Runtime | ✅ Yes | ~104 endpoints, all tested |
| React Web (web) | Core Runtime | ✅ Yes | Full UI, POC Demo tab |
| MongoDB (mongo) | Core Runtime | ✅ Yes | All collections stable |
| Redis (redis) | Core Runtime | ✅ Yes | Render queue functional |
| Worker | Core Runtime | ✅ Yes | FFmpeg assembly tested |
| ComfyUI | Optional | ⚠️ Optional | Disabled by default |
| lead_scraper | One-off CLI | ⚠️ Manual | Not in docker compose up |
| lead_enricher | One-off CLI | ⚠️ Manual | Not in docker compose up |
| social_processor | Placeholder | ❌ No | Future sprint |
| post_generator | Placeholder | ❌ No | Future sprint |

---

## POC Demo Mode Architecture

The POC Demo tab (`services/web/src/components/PocDemoTab.jsx`) is entirely client-side:

- **Storage:** `localStorage` only — no MongoDB reads/writes during demo navigation
- **Data:** All 13 step records are synthetic (pre-seeded via `demoMode.js`)
- **Safety enforcement:** Verified via `simulation_only: true`, `outbound_actions_taken: 0` on every synthetic record
- **Render queue:** Not triggered during demo navigation
- **External APIs:** Zero calls during demo mode

This design allows the full 13-step walkthrough to run on any machine with Docker, without requiring live data, API keys, or network access.

---

## Test Coverage

```
Backend (pytest):   678 passed, 44 skipped (0 failures)
Frontend (vitest):   88 passed              (0 failures)
Build (vite):        built in 1.68s         (0 errors)
Docker:              docker compose config → OK
System check:        make check → passed
```

---

## What Would Be Required for Production

See [docs/PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) for the full checklist. Summary:

| Category | Gap | Severity |
|----------|-----|----------|
| Auth | No authentication/sessions | Critical |
| HTTPS | HTTP only in dev | Critical |
| Multi-tenancy | Single workspace model | High |
| Rate limiting | None on API | High |
| Secrets management | .env file only | High |
| Backups | No automated DB backup | Medium |
| Monitoring | No production observability | Medium |
| ComfyUI | GPU server required for production renders | Medium |

**The system is designed and validated for single-operator local use.** It is not currently suitable for multi-user, internet-facing, or multi-client deployment without the above gaps addressed.

---

## Running the System

```bash
# Start all core services
docker compose up -d

# Verify health
make check

# Run tests
pytest services/api/tests/ -q
cd services/web && npm test

# Access UI
open http://localhost:5174

# API docs
open http://localhost:8000/docs
```

---

_SignalForge v10.2 — POC Technical Appendix_
