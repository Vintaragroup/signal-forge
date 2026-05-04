# Production Readiness

> **SignalForge v10 — Local-First, Single-Operator**  
> Last updated: May 2026  
> See [ARCHITECTURE.md](../ARCHITECTURE.md) and [docs/SERVICE_BOUNDARIES.md](SERVICE_BOUNDARIES.md) for system context.

This document describes what SignalForge is ready to do today, what gaps exist before multi-user or client-hosted deployment, and what must be addressed before treating this as a production SaaS.

---

## Current Strengths

### Local-first by design
All data stays on the operator's machine. MongoDB, Redis, and file outputs live in Docker volumes. No data leaves the host by default.

### Review-gated execution
Every pipeline stage that produces outbound-relevant content requires explicit operator approval. No automated sends, posts, or calendar events exist at any point in the pipeline.

### Comprehensive test coverage
- 678 backend tests passing (pytest)
- 88 frontend tests passing (vitest)
- Safety invariant tests confirm real endpoints never return `is_demo: true` records
- Test suite covers all pipeline stages, agent behavior, tool layer, Creative Studio, and demo isolation

### Safety invariants on all records
Every pipeline record carries `simulation_only: true` and `outbound_actions_taken: 0`. Demo records carry `is_demo: true`. These fields are enforced at insertion time and tested parametrically.

### POC Demo Mode (v10)
A 13-step browser-localStorage-only walkthrough for client demos and operator onboarding. Zero MongoDB writes, zero API calls for reads. Fully isolated from real-mode data.

### Deterministic local processing
Snippet scoring, client intelligence, lead scoring, performance analytics, and correlation analysis are all deterministic, local Python — no ML inference, no external API calls, no randomness.

### Graceful fallbacks
Redis unavailable → synchronous inline render. ComfyUI unavailable → FFmpeg placeholder image. Transcript provider unset → stub mode. The system degrades gracefully without crashing.

### Workspace isolation
All pipeline collections support `workspace_slug` filtering. Demo workspace is permanently excluded from real-mode queries.

---

## Current Limitations

### Single-operator only
There is no user model. No login, no session management, no roles, no per-user data isolation. The system assumes one operator with full local access to Docker and MongoDB.

### No authentication or RBAC
Any process that can reach `localhost:8000` has full read/write access to all data. This is acceptable for a single operator on a private machine and unacceptable for any networked or shared deployment.

### Local-only deployment
The Docker Compose stack is designed for a single machine. No load balancing, no horizontal scaling, no HA configuration, no off-machine backups are provided.

### Mock-only web search
The tool layer's web search returns 5 hardcoded `MOCK_BUSINESSES`. `SERPAPI_KEY` is reserved in `.env.example` but not wired to any API call. Live web search requires implementation work before it functions.

### No external integrations
None of the following are implemented:
- Email / SMS / DM sending
- Social media APIs (read or write)
- CRM systems (Salesforce, HubSpot, etc.)
- Calendar / scheduling APIs
- External enrichment providers (Clearbit, Apollo, etc.)
- Payment / invoicing systems
- Webhook delivery to external systems

### social_processor and post_generator are scaffolds
Both services exist as Docker containers but print a placeholder message and exit. Real social signal processing and autonomous content generation are not implemented.

### No persistent secret management
API keys and configuration are stored in `.env` files on disk. No vault integration (HashiCorp Vault, AWS Secrets Manager, etc.) exists.

---

## Security Gaps

> These are pre-production gaps, not active vulnerabilities, given the local-only single-operator deployment. They become blocking issues before any networked or multi-user deployment.

| Gap | Severity for multi-user | Notes |
|---|---|---|
| No user authentication | **Critical** | Any process reaching port 8000 has full API access |
| No RBAC / authorization layer | **Critical** | No role or permission model exists |
| No API key / token enforcement | **Critical** | All endpoints are unauthenticated |
| No CORS policy enforced | High | Default FastAPI CORS is permissive |
| No rate limiting | High | No request throttling on any endpoint |
| `.env` file key storage | High | Keys stored in plaintext on disk |
| No HTTPS / TLS | High | API served over plain HTTP |
| No audit log of admin actions | Medium | MongoDB records pipeline events; no separate admin audit trail |
| No input sanitization layer | Medium | FastAPI Pydantic models validate types; no XSS/injection audit beyond that |
| No secrets scanning in CI | Medium | No automated detection of committed secrets |
| MongoDB has no auth configured | Medium | Mongo container uses no username/password by default |

---

## Local-First Deployment Assumptions

The current system assumes:

1. **Single machine.** All containers run on one host via Docker Compose.
2. **Single operator.** One trusted user operates the system locally.
3. **Private network.** API and dashboard ports are bound to `localhost`, not exposed to the internet.
4. **Operator-managed `.env`.** Secrets are managed manually in a local `.env` file not committed to source control.
5. **Obsidian vault is local.** `/vault` is a bind-mounted local directory. No cloud sync is configured by SignalForge.
6. **No backups.** MongoDB data and render outputs live in Docker volumes. The operator is responsible for backups (see `docs/V1_BACKUP_AND_EXPORT.md`).

---

## External Integrations Not Implemented

The following capabilities are documented or reserved but not built:

| Integration | Status | Notes |
|---|---|---|
| SERPAPI live web search | Reserved | `SERPAPI_KEY` in `.env.example`; mock-only today |
| OpenAI / GPT agent | Gated | Implemented; requires `GPT_AGENT_ENABLED=true` + `OPENAI_API_KEY` |
| Whisper transcription | Gated | Implemented; requires `TRANSCRIPT_PROVIDER=whisper` + `TRANSCRIPT_LIVE_ENABLED=true` |
| ComfyUI image generation | Gated | Implemented; requires `COMFYUI_ENABLED=true` + running ComfyUI instance |
| Email sending | Not implemented | — |
| SMS sending | Not implemented | — |
| Social DM / comment posting | Not implemented | — |
| Social media read APIs | Not implemented | — |
| CRM sync (Salesforce / HubSpot) | Not implemented | — |
| Calendar API (Google / Outlook) | Not implemented | — |
| External enrichment APIs | Not implemented | — |
| Webhook delivery | Not implemented | — |
| Payment / invoicing | Not implemented | — |

---

## Pre-Production Checklist

Before deploying SignalForge for any networked, shared, or client-hosted use:

### Authentication & Authorization
- [ ] Add a user model with hashed passwords (e.g., bcrypt)
- [ ] Implement session tokens or JWT-based auth
- [ ] Add role-based access control (operator / viewer / admin)
- [ ] Gate all API endpoints behind authentication middleware
- [ ] Add per-workspace permission checks

### Transport Security
- [ ] Configure HTTPS / TLS (reverse proxy: nginx, Caddy, or cloud LB)
- [ ] Set strict CORS policy (allowed origins whitelist)
- [ ] Add rate limiting (e.g., slowapi or nginx `limit_req`)
- [ ] Set `Secure`, `HttpOnly`, `SameSite` on session cookies

### Secret Management
- [ ] Move API keys out of `.env` files into a secrets manager
- [ ] Enable MongoDB authentication (username + password)
- [ ] Add secrets scanning to CI pipeline
- [ ] Rotate any keys committed to version history

### Data Isolation
- [ ] Enforce workspace-level data isolation with server-side checks
- [ ] Add user-scoped data ownership model
- [ ] Audit all endpoints for cross-tenant data leakage

### Infrastructure
- [ ] Configure persistent volume backups (MongoDB dumps + render outputs)
- [ ] Add health-check alerting
- [ ] Set resource limits on Docker containers
- [ ] Configure log aggregation (not just Docker stdout)
- [ ] Add a deployment environment strategy (staging vs. production)

### Code Quality
- [ ] Integrate SERPAPI or a real web search provider (replace mock)
- [ ] Implement or stub-out `social_processor` and `post_generator` clearly
- [ ] Run OWASP dependency scan on Python and Node packages
- [ ] Add CI pipeline (lint, test, security scan on every commit)

### Operational
- [ ] Write operator runbook for incident response
- [ ] Document data retention / deletion policy
- [ ] Add privacy policy if handling client data
- [ ] Review all third-party AI outputs for compliance requirements

---

## What Is Production-Ready Today (Locally)

| Capability | Local production status |
|---|---|
| FastAPI control plane (104 endpoints) | ✅ Stable, tested |
| React dashboard (all pages) | ✅ Stable, tested |
| MongoDB data layer | ✅ Stable (no auth) |
| Redis + worker render pipeline | ✅ Stable |
| FFmpeg local rendering | ✅ Real renders, `FFMPEG_ENABLED=true` default |
| Creative Studio pipeline (v2–v10) | ✅ Full pipeline, all stages |
| Client intelligence & correlations (v9.5) | ✅ Deterministic, advisory-only |
| POC Demo Mode (v10) | ✅ Fully isolated, fully tested |
| GPT agent runtime | ✅ Implemented, gated off by default |
| Whisper transcription | ✅ Implemented, gated off by default |
| ComfyUI image generation | ✅ Implemented (stub included), gated off by default |
| Tool layer (mock web search, scraper) | ✅ Functional (web search is mock-only) |
| Workspace isolation | ✅ All endpoints support `workspace_slug` |
| Campaign packs, reports, exports | ✅ Stable |
| Automated test suite | ✅ 678 backend + 88 frontend passing |

---

## Summary

SignalForge v10 is **ready for local single-operator use**. The pipeline is complete, tested, and review-gated. It is **not ready for networked, multi-user, or client-hosted deployment** without addressing the authentication, authorization, transport security, and secret management gaps listed above.
