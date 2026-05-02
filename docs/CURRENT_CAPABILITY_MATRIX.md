# SignalForge v1 Current Capability Matrix

SignalForge v1 is local-first and human-reviewed. This matrix separates what is browser-supported, CLI-only, simulated, manual, real/local, and not yet implemented now that the GPT agent runtime exists behind an explicit operator gate.

Legend:

- `dashboard-supported`: Available through the local React dashboard and FastAPI service.
- `CLI-only`: Available through Python scripts or Makefile commands, not fully through the dashboard.
- `simulated`: Plans or logs actions without taking real-world outbound action.
- `manual`: Requires a human to perform or approve the real-world step outside SignalForge.
- `real/local`: Runs locally against MongoDB, files, Docker, or the vault.
- `not yet implemented`: Documented or planned, but not built as v1 runtime behavior.

| Capability | Dashboard-supported | CLI-only | Simulated | Manual | Real/local | Not yet implemented | Current implementation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Mode Switcher v1 | Yes | No | No | No | Yes | No | Header mode button switches between Real Mode (blue) and Demo Mode (purple) with a confirmation dialog. ModeBanner shows below header. Demo Mode uses browser localStorage only — MongoDB never touched. Reset Demo Data restores seeded records. Overview checklists and Settings/Help section are mode-aware. |
| Docker local stack | No | Yes | No | Yes | Yes | No | `make up`, `make dashboard`, `docker compose` start MongoDB, API, services, and web. |
| FastAPI health/status | Yes | Yes | No | No | Yes | No | `GET /health` plus `curl http://localhost:8000/health`. |
| React web dashboard | Yes | No | No | No | Yes | No | Demo Mode, Workflow, Overview, Pipeline / CRM, Messages, Approvals, Agent Tasks, Agent Console, Research / Tools, GPT Diagnostics, Deals, Reports. |
| Contractor listing import | No | Yes | No | Yes | Yes | No | `scripts/run_daily_pipeline.sh` runs `lead_scraper` against local structured data. |
| Contractor lead enrichment/scoring | No | Yes | No | No | Yes | No | `lead_enricher` adds deterministic v3 intelligence, score breakdown, notes, and review queue items. |
| External/live scraping | Partly | Yes | No | Yes | Partly | Partly | Tool Layer v1 can fetch a public HTML URL and optionally scroll public pages when Playwright is installed. It respects safety gates, avoids protected/gated pages, and remains review-only. |
| External enrichment APIs | No | No | No | No | No | Yes | No external enrichment providers are called. |
| Contact CSV import | No | Yes | No | Yes | Yes | No | `scripts/import_contacts.py` imports local CSVs into MongoDB and writes vault notes. |
| Manual source/candidate CSV import | Yes | Yes | No | Yes | Yes | No | Research / Tools Import CSV panel, `POST /tools/import-candidates`, and `scripts/import_candidates.py` import local/uploaded prospect source lists into `scraped_candidates` with `source=manual_upload`, quality scoring, enrichment, duplicate detection, approval requests, and approval-gated local conversion. |
| Import history and audit | Yes | No | No | No | Yes | No | `GET /tools/import-history` lists every manual CSV import with source label, module, row count, candidate count, duplicate count, error count, status, and timestamp. Dashboard Import History section provides expandable per-import detail. |
| Import detail view | Yes | No | No | No | Yes | No | `GET /tools/import-history/{id}/candidates` returns all candidates for a specific import. Dashboard shows quality score, completeness score, duplicate flag, approval status, and conversion status per candidate. |
| Import row error display | Yes | No | No | No | Yes | No | `GET /tools/import-history/{id}/errors` returns row-level errors from CSV parsing (invalid email, malformed fields, within-import duplicate companies). Errors are stored on the tool_run and visible in the Import History detail panel. |
| Candidate bulk actions | Yes | No | No | Yes | Yes | No | `POST /scraped-candidates/bulk-action` supports approve, reject, and convert_to_contact for multiple candidates in one call. Dashboard bulk action bar appears when candidates are selected. Convert requires prior approval; a confirmation dialog is shown before bulk conversion. |
| Advanced candidate filters | Yes | No | No | No | Yes | No | `GET /scraped-candidates` supports filtering by `source_label`, `module`, `min_quality`, `max_quality`, and `converted`. Dashboard Advanced Filters panel exposes all filter controls. |
| Contact scoring/segmentation | No | Yes | No | No | Yes | No | `scripts/score_contacts.py` applies deterministic local scoring. |
| Message draft generation | No | Yes | No | Yes | Yes | No | `scripts/draft_messages.py` writes Mongo records and editable vault notes. |
| Message review | Yes | Yes | No | Yes | Yes | No | Dashboard Messages page and `scripts/review_message.py` approve, revise, or reject. |
| Approval queue | Yes | No | No | Yes | Yes | No | Dashboard Approval Queue reviews `approval_requests`, stores decisions and notes, and can convert safe local requests into review-only drafts or artifacts. |
| Agent Tool Layer v1 | Yes | Yes | Yes | Yes | Yes | No | Research / Tools plus Agent Console Tool Runs record sanitized `tool_runs`, `scraped_candidates`, tool artifacts, source URLs, extracted fields, linked agent runs, and approval requests. Mock search is deterministic; `SERPAPI_KEY` is future-only. Candidate conversion requires prior approval. |
| Outbound email/SMS/DM/social sending | No | No | No | Yes | No | Yes | SignalForge never sends. Operators may send manually outside the system. |
| Manual send logging | No | Yes | No | Yes | Yes | No | `scripts/log_manual_send.py` records human-performed sends only. |
| Response logging | No | Yes | No | Yes | Yes | No | `scripts/log_response.py` records outcomes and updates linked records. |
| Meeting prep generation | No | Yes | No | Yes | Yes | No | `scripts/generate_meeting_prep.py` writes local meeting prep notes. |
| Calendar integration | No | No | No | Yes | No | Yes | No calendar events are created. |
| Deal outcome tracking | Yes | Yes | No | Yes | Yes | No | Dashboard displays deals; `scripts/log_deal_outcome.py` creates/updates local deal records. |
| Invoicing | No | No | No | Yes | No | Yes | Deal notes explicitly do not create invoices. |
| CRM integration | No | No | No | Yes | No | Yes | MongoDB is the local CRM-lite store; no external CRM APIs are called. |
| Contractor pipeline report | Yes | Yes | No | No | Yes | No | `scripts/generate_pipeline_report.py`, `make report`, and dashboard Reports page. |
| Revenue/performance report | Yes | Yes | No | No | Yes | No | `scripts/generate_revenue_report.py`, `make revenue-report`, and dashboard Reports page. |
| Obsidian vault audit layer | Partly | Yes | No | Yes | Yes | No | Vault notes, logs, drafts, review queue, meetings, deals, and reports remain readable markdown. |
| Simulation-only agents | Yes | Yes | Yes | Yes | Yes | No | CLI and Agent Console run dry-run agents and record observed runs. |
| Agent task queue | Yes | No | Yes | Yes | Yes | No | Agents are now run from the dashboard via Agent Tasks. Dashboard Agent Tasks creates queued `agent_tasks`, runs current dry-run/GPT-safe agents, links to Agent Console runs, and supports internal cancellation. |
| GPT/OpenAI agent runtime | Yes | Yes | Yes | Yes | Yes | No | Implemented for outreach, follow-up, content, and fan engagement planning behind `GPT_AGENT_ENABLED=false` by default. Requires `OPENAI_API_KEY`; all GPT output is review-only and records artifacts, drafts, or approval requests. |
| GPT diagnostics | Yes | Yes | Partly | Yes | Yes | No | Dashboard GPT Diagnostics, `GET /diagnostics/gpt`, and `scripts/gpt_diagnostics.py` report safe runtime status, recent sanitized GPT steps, and GPT-related system approval errors without returning secrets or raw prompts. Optional `--live-test` sends only `Return the word OK.` |
| Social signal processing runtime | No | Partly | Yes | Yes | Partly | Partly | Placeholder service checks vault/Mongo; real ingestion/classification is not implemented. |
| Post/content generation runtime | No | Partly | Yes | Yes | Partly | Partly | Placeholder service checks vault/Mongo; real content generation is not implemented. |
| Backup/export guidance | No | Yes | No | Yes | Yes | No | Documented in `docs/V1_BACKUP_AND_EXPORT.md`; no Makefile wrapper yet. |
| Automated tests | No | Yes | No | No | Yes | No | Basic pytest suite covers constants, scoring, review status rules, and report aggregation. |
| Client Workspace v1 | Yes | No | No | No | Yes | No | Dashboard Workspaces page: create named workspaces (client, internal, demo, test), assign a module, add notes, pause/archive. Workspace selector in header filters all data pages (contacts, leads, messages, deals, approvals, candidates, agent tasks, agent runs, tool runs) to a single workspace. All list endpoints accept `workspace_slug` query param. New records can be tagged with a `workspace_slug` at import/creation time. Existing records without a slug are visible when "All Workspaces" is selected. Selecting a specific workspace shows only records tagged to that slug. |

## Safety Boundary

SignalForge v1 does not send messages, publish content, create calendar events, issue invoices, call CRM APIs, run GPT-powered agents by default, or use external enrichment/search APIs. The GPT runtime is implemented but gated unless `GPT_AGENT_ENABLED=true` and `OPENAI_API_KEY` are configured. Tool Layer v1 is read-only and review-first: it records sanitized `tool_runs`, `scraped_candidates`, artifacts, and approval requests; local contact/lead conversion requires prior approval. Manual source/candidate CSV imports are local only and do not create contacts, leads, messages, or outbound actions automatically. Research Import Management v1 adds import history, per-import candidate detail views, row-level error display, advanced candidate filters, and bulk approve/reject/convert actions — all local, all review-gated; bulk convert still requires prior approval per candidate and shows a confirmation dialog. GPT diagnostics never return API keys or raw prompts; the optional live diagnostics test makes only a minimal OpenAI `OK` request when explicitly invoked. The dashboard and CLI may update local MongoDB records, create review-only GPT artifacts/drafts/approval requests, write sanitized diagnostics steps, and append local vault logs only.

---

## Social Creative Engine v2 — Capability Additions

| Capability | Dashboard-supported | Simulated | Manual | Real/local | Notes |
|---|---|---|---|---|---|
| Client profile management | Yes | No | No | Yes | Per-client brand permissions. Likeness/voice/avatar default `false`. |
| Source channel registry | Yes | No | No | Yes | Per-client, per-platform. Ingestion/reuse gates enforced. |
| Source content ingestion | Yes | No | No | Yes | Discovery score, status gating (`needs_review` → `approved`). |
| Transcript management | Yes | No | No | Yes | Full text stored, status tracked. |
| Snippet scoring & review | Yes | No | Yes | Yes | Score, theme, hook angle, platform fit. Operator review required. |
| Creative asset review | Yes | No | Yes | Yes | All assets start at `needs_review`. No auto-approve path. |
| ComfyUI image/video generation | Yes (opt-in) | No | Yes | Yes | `COMFYUI_ENABLED=true` required. Disabled by default. |
| Creative tool run audit | Yes | No | No | Yes | All runs recorded. Skipped/failed states written safely. |
| Approval queue (snippets + assets) | Yes | No | Yes | Yes | Unified Approval Queue tab in Creative Studio dashboard. |

### v2 Safety Boundary

All Social Creative Engine v2 records carry `simulation_only: true` and `outbound_actions_taken: 0`. Likeness, voice, and avatar permissions are explicitly `false` by default and cannot be set to `true` via the API without operator intent. No asset, snippet, or creative record is published, scheduled, or sent automatically. ComfyUI integration is disabled by default; when enabled, it communicates only with a local ComfyUI instance (`host.docker.internal:8188` by default) and writes all results as internal records only.

---

## Social Creative Engine v4.5 — Prompt Generator Library

| Capability | Dashboard-supported | Simulated | Manual | Real/local | Notes |
|---|---|---|---|---|---|
| Prompt generation from approved snippet | Yes | Yes | Yes | No | Only approved snippets may trigger generation. Draft-status output. |
| 9 visual prompt types | Yes | Yes | Yes | No | faceless_motivational, cinematic_broll, abstract_motion, business_explainer, quote_card_motion, podcast_clip_visual, educational_breakdown, luxury_brand_story, product_service_ad |
| Engine target selection | Yes | Yes | Yes | No | comfyui, seedance, higgsfield, runway, manual. No engine is auto-invoked. |
| Likeness/avatar gate | Yes | N/A | N/A | N/A | use_likeness=True requires explicit avatar_permissions or likeness_permissions on client profile. |
| Prompt review workflow | Yes | Yes | Yes | No | approve / reject / revise. Approved status unlocks prompt for operator use. |
| Workspace isolation | Yes | N/A | N/A | N/A | Prompt generations are scoped to workspace_slug. Demo workspace excluded from real queries. |
| Default faceless guarantee | Yes | N/A | N/A | N/A | Negative prompt always blocks faces, likenesses, and identifiable people. Voice cloning never requested. |
| Source traceability | Yes | N/A | N/A | N/A | source_url, snippet_transcript, snippet_usage_status preserved on every record. |
| Prompt Library tab | Yes | Yes | N/A | N/A | Dedicated tab in Creative Studio dashboard. Generate, filter, and review prompts inline. |

### v4.5 Safety Boundary

All prompt_generations records carry `simulation_only: true` and `outbound_actions_taken: 0`. Default negative prompt blocks all identifiable faces, likenesses, and avatars. Voice cloning instructions are never generated. No ComfyUI, Seedance, Higgsfield, or Runway calls are made by SignalForge; the operator must execute any asset generation externally after review. `use_likeness=True` requires explicit client profile permissions. All prompts enter as `status: draft` and must be reviewed before use.

---

## Social Creative Engine v5 — Asset Rendering

| Capability | Dashboard-supported | Simulated | Manual | Real/local | Notes |
|---|---|---|---|---|---|
| Asset render pipeline | Yes | Yes | No | Opt-in | Requires approved snippet + approved prompt_generation. Both gates enforced at API level. |
| ComfyUI image generation | Yes (opt-in) | Yes (disabled path) | No | Yes (`COMFYUI_ENABLED=true`) | `COMFYUI_ENABLED=false` (default) → mock result, no external calls. |
| FFmpeg video assembly | Yes (opt-in) | Yes (disabled path) | No | Yes (`FFMPEG_ENABLED=true`) | `FFMPEG_ENABLED=false` (default) → mock assembly result, no subprocess spawned. |
| Vertical 9:16 output | Yes | Yes | No | Yes | Default resolution `1080x1920`. Configurable. |
| Caption overlay (basic) | Yes | Yes | No | Yes (`FFMPEG_ENABLED=true`) | Optional `add_captions=true`. Burns caption text via FFmpeg drawtext filter. |
| Status lifecycle | Yes | N/A | N/A | N/A | queued → generated → needs_review. Never auto-advances to approved. |
| Asset render review | Yes | Yes | Yes | No | approve / reject / revise. Operator must explicitly approve each render. |
| Rendered Assets tab | Yes | Yes | N/A | N/A | New "Rendered Assets" tab in Creative Studio dashboard. Preview, filter, and review inline. |
| Demo mode renders | Yes (demo) | Yes | N/A | N/A | 2 demo seed records with mock preview URLs. Review mutations work in demo. |
| Workspace isolation | Yes | N/A | N/A | N/A | asset_renders scoped to workspace_slug. Demo workspace excluded from real queries. |
| Source traceability | Yes | N/A | N/A | N/A | snippet_id and prompt_generation_id stored on every render record. |

### v5 Safety Boundary

All `asset_renders` records carry `simulation_only: true` and `outbound_actions_taken: 0`. No asset is ever published, scheduled, or sent automatically. A render cannot be started unless both the source snippet and prompt_generation have `status: approved`. All rendered assets start as `status: needs_review` and require explicit operator approval before any downstream use. `COMFYUI_ENABLED` and `FFMPEG_ENABLED` are each independently gated and default to `false` — the system makes zero external subprocess or HTTP calls unless explicitly opted in. FFmpeg commands write only to the local filesystem at `FFMPEG_OUTPUT_DIR` (default: `/tmp/signalforge_renders`). No files are uploaded, streamed, or sent to any external service.

---

## Social Creative Engine v5 — Runtime Infrastructure

| Capability | Dashboard-supported | Simulated | Manual | Real/local | Notes |
|---|---|---|---|---|---|
| Redis job queue | No | N/A | N/A | Yes | `redis://redis:6379` by default. `job_queue.py` wraps LPUSH/BRPOP. |
| Async render worker | No | N/A | N/A | Yes | `worker.py` — runs as separate container using same api image. |
| Sync fallback (no Redis) | Yes | Yes | N/A | N/A | When Redis unreachable, render runs inline. Existing behaviour preserved. |
| Status: running | Yes | N/A | N/A | N/A | Worker sets `status: running` before processing. |
| Status: failed | Yes | N/A | N/A | N/A | Worker sets `status: failed` with error on exception. |
| ComfyUI service (profile) | No | N/A | N/A | Yes (opt-in) | `docker compose --profile comfyui up`. Stub server included for local dev. |
| FFmpeg binary | No | N/A | N/A | Yes | Installed in api/worker Docker image. Gate: `FFMPEG_ENABLED=false` (default). |
| Shared render volume | No | N/A | N/A | Yes | `render-output` Docker volume shared between api and worker containers. |
| Dead-letter queue | No | N/A | N/A | Yes | Failed jobs pushed to `signalforge:render_jobs_failed` for inspection. |

### v5 Runtime Safety Boundary

All safety guarantees from v5 Asset Rendering are preserved. The worker process carries the same `simulation_only: true`, `outbound_actions_taken: 0` invariants as the API. Redis is used only for internal job handoff — no job payload is ever sent to an external service. The ComfyUI service definition uses a local stub server and is fully isolated within the Docker network. `COMFYUI_ENABLED=false` (default) means the worker uses the mock render path regardless of whether the ComfyUI container is running.
