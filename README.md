# signalForge

signalForge is a local-first AI-powered growth operating system for collecting leads, enriching company and contact data, processing social signals, generating outreach and content, and writing human-readable outputs into an Obsidian vault.

The project is intentionally small at the foundation layer. Each service is runnable, Dockerized, and wired for MongoDB and the shared vault, but the initial implementation favors clear placeholders over premature platform complexity.

## SignalForge v1 Status

SignalForge v1 is packaged for local handoff and repeatable operator use. The working system includes the contractor lead engine, contact ingestion, contact scoring, message drafting and review, manual send logging, response logging, meeting prep, deal outcome tracking, reports, documentation-first modules, and simulation-only agents.

Current package docs:

- [Current Capability Matrix](docs/CURRENT_CAPABILITY_MATRIX.md)
- [v1 System Overview](docs/V1_SYSTEM_OVERVIEW.md)
- [v1 Demo Script](docs/V1_DEMO_SCRIPT.md)
- [v1 Client Onboarding Checklist](docs/V1_CLIENT_ONBOARDING_CHECKLIST.md)
- [v1 Backup And Export](docs/V1_BACKUP_AND_EXPORT.md)
- [v1 Release Notes](docs/V1_RELEASE_NOTES.md)
- [Operator Playbook](docs/OPERATOR_PLAYBOOK.md)

v1 remains local-first and human-reviewed. It does not send messages, publish content, create calendar events, issue invoices, call CRM APIs, or use external enrichment/scraping APIs.

## GPT Agent Runtime

GPT Agent Runtime v1 is implemented but gated off by default. It can help the existing agents draft or recommend review-only outputs:

- `outreach_agent`: draft outreach messages into `message_drafts` with `review_status=needs_review` and `send_status=not_sent`.
- `followup_agent`: create follow-up recommendations as agent artifacts or approval requests.
- `content_agent`: create content plan artifacts and local markdown notes under `vault/content/agents/`.
- `fan_engagement_agent`: create artist-growth engagement plan artifacts and local markdown notes under `vault/content/agents/`.

To enable GPT locally, copy `.env.example` to `.env`, then set:

```text
GPT_AGENT_ENABLED=true
OPENAI_API_KEY=<your-api-key>
OPENAI_MODEL=gpt-4o-mini
```

`OPENAI_MODEL` is optional; blank values use the built-in default. The dashboard shows GPT enabled/disabled status from `GET /settings/gpt-runtime` and displays the active model name.

GPT cannot send emails, SMS, DMs, comments, social posts, calendar invites, invoices, CRM updates, enrichment calls, scraping jobs, or publishing/scheduling actions. Every GPT output requires human review before any real-world action happens outside SignalForge.

## GPT Diagnostics v1

Operators can inspect safe GPT runtime diagnostics from the dashboard GPT Diagnostics page or from the CLI:

```bash
docker compose run --rm api python scripts/gpt_diagnostics.py
```

Diagnostics show whether GPT is enabled, the configured model, whether an API key is present, whether the local GPT client module is available, the last recorded GPT success/error, recent GPT agent steps, and recent GPT-related system approval errors. The API endpoint is `GET /diagnostics/gpt`.

The diagnostics endpoint and CLI never print or return `OPENAI_API_KEY`, never expose raw prompts, and never send messages or modify agent behavior. A live OpenAI connectivity check only runs when explicitly requested:

```bash
docker compose run --rm api python scripts/gpt_diagnostics.py --live-test
```

The live test sends only `Return the word OK.` and records a sanitized `gpt_diagnostic_live_test` step in MongoDB.

## Web Dashboard v1

SignalForge now includes a local React dashboard for operating the system visually.

```bash
make dashboard
```

Open:

```text
http://localhost:5174
```

The dashboard uses the FastAPI service at `http://localhost:8000`, reads existing MongoDB collections, and keeps the Obsidian vault as the audit and knowledge layer.

Dashboard pages:

- Demo Mode
- Workflow
- Overview
- Pipeline / CRM
- Messages
- Approvals
- Agent Tasks
- Agents
- Research / Tools
- GPT Diagnostics
- Deals
- Reports

Message review and approval queue actions in the dashboard update MongoDB and append local records only. They do not send messages, publish content, post comments, schedule work, or call external platforms. Agent actions are dry-run only.

## Mode Switcher v1

SignalForge operates in **Real Mode** (blue) or **Demo Mode** (purple). The current mode is always visible in the top-right header button and in the persistent banner below the header.

**Switching modes:** Click the header mode button. A confirmation dialog appears before any switch takes effect. This prevents accidental mode changes.

**Real Mode:** Reads and writes local MongoDB only. No automated outbound sends ever occur. All agent actions are dry-run or review-only.

**Demo Mode:** Browser localStorage only. MongoDB is never touched. All records are synthetic and labeled DEMO. Used for client demos, onboarding, and walkthroughs. Click "Reset Demo Data" at any time to restore seeded records without affecting MongoDB.

See [docs/MODES_AND_DEMO_GUIDE.md](docs/MODES_AND_DEMO_GUIDE.md) for the full guide.

## Demo Mode v1

Demo Mode provides a clean browser-only walkthrough for first-time operators. Start it from the Overview page or the Demo Mode navigation item.

Demo Mode preloads synthetic contacts, leads, drafts, responses, and deals in browser storage. It labels records as Demo Mode, shows the banner `Demo Mode - No real messages will be sent`, and walks through Run Outreach, Review Drafts, Approve Message, Simulate Response, and Show Deal Outcome.

Demo Mode does not write to MongoDB, does not run agents, does not call GPT, and does not send or schedule anything. Exit Demo returns the dashboard to live local data.

## Approval Queue v1

The dashboard Approval Queue gives operators one place to review GPT-created approval requests and other agent review items. Operators can approve, reject, mark needs revision, or convert an approval request into a review-only draft.

Approval decisions only control internal workflow state:

- `approve` marks the request approved.
- `reject` marks the request rejected.
- `needs_revision` stores the operator note and marks the request for revision.
- `convert_to_draft` creates either a `message_draft` or an `approval_queue_draft` artifact with `review_status=needs_review` when applicable.

No approval queue decision sends messages, posts content, scrapes data, schedules posts, creates calendar events, or calls external CRM/platform APIs.

Approval requests are classified by origin and severity so the dashboard can keep real operator work separate from diagnostics. The default Approval Queue shows actionable approvals only; use the queue filters for GPT, system issues, or test/synthetic records. GPT runtime tests may create synthetic approval requests to verify safety behavior. Review them with `python scripts/cleanup_test_approvals.py --dry-run`, or archive and remove them with `python scripts/cleanup_test_approvals.py --archive`.

## Agent Tool Layer v1

SignalForge now includes a read-only research tool layer under `tools/`. It includes deterministic mock web search, public website scraping, optional Playwright browser scrolling for public pages, contact-field extraction, and source validation. Tool runs record sanitized `tool_runs`, review-only `scraped_candidates`, `agent_artifacts`, and approval requests for operator inspection.

Run tools from Docker with:

```bash
docker compose run --rm api python scripts/run_tool.py web_search --query "roofing contractor" --module contractor_growth --location "Austin, TX" --limit 3
docker compose run --rm api python scripts/run_tool.py website_scraper --url https://example.com
docker compose run --rm api python scripts/run_tool.py browser_scroll --url https://example.com
docker compose run --rm api python scripts/import_candidates.py data/imports/contractor_sources.csv --module contractor_growth --source-label "manual_contractor_test"
```

The dashboard Research / Tools page shows tool history, inputs, source URLs, extracted fields, linked agent runs, approval links, and scraped candidates. Operators can run deterministic mock research or import a local/uploaded CSV through the Import CSV panel. Manual candidate imports expect `company,website,phone,email,city,state,service_category,notes,source_url`, run the same source validation, quality scoring, enrichment, duplicate detection, approval request creation, and review workflow as tool-generated candidates, and store rows with `source=manual_upload` plus the operator-provided `source_label`. Operators can approve or reject candidates. Local conversion to contact or lead is blocked until the candidate has first been approved.

Outreach and content agents can optionally run the tool layer from the Agent Console. Tool-enabled agent runs create research artifacts and approval requests only. They do not convert candidates, send messages, submit forms, post content, bypass captcha, scrape protected/private areas, or take any outbound action. `SERPAPI_KEY` is reserved for future support; v1 remains deterministic unless explicitly extended later.

## Research Import Management v1

The Research / Tools dashboard now provides full import audit and management capabilities for manual CSV imports:

**Import History** — every CSV import is listed with source label, module, imported row count, candidate count, duplicate count, error count, timestamp, and status. Click any import row to expand its detail view.

**Import Detail View** — per-import view of all imported candidates with quality scores, completeness scores, duplicate status, approval status, and conversion status. Row-level errors (invalid email, malformed fields, within-import duplicates) are shown in a separate error panel.

**Candidate Bulk Actions** — operators can approve, reject, or convert multiple candidates at once from the candidate table. Bulk convert requires candidates to already be approved; a confirmation dialog is shown before any bulk conversion. Candidate selection is per-page; the action bar appears automatically when one or more candidates are selected.

**Advanced Filters** — the candidate table supports filtering by source label, module, quality score range, and conversion status. Use the Advanced Filters panel above the table to apply compound filters.

**Import Error Display** — row-level errors collected during CSV parsing (invalid email format, blank rows, within-import duplicate companies) are stored on the tool_run record and displayed in the Import History detail view. Invalid email rows are flagged but still enter the review pipeline so operators can correct or reject them manually.

API endpoints added: `GET /tools/import-history`, `GET /tools/import-history/{id}/candidates`, `GET /tools/import-history/{id}/errors`, `POST /scraped-candidates/bulk-action`.

## Agent Task Queue v1

Agents are now run from the dashboard via Agent Tasks. The dashboard Agent Tasks page lets operators create, queue, run, and cancel agent tasks without using CLI dry-runs directly. Agents now run in a live panel with visible step execution and outputs. Tasks are stored in MongoDB in the `agent_tasks` collection and link to the resulting Agent Console run when executed.

Supported agents:

- `outreach`
- `followup`
- `content`
- `fan_engagement`

Task runs use the same dry-run/GPT-safe agent behavior as the Agent Console. A task can become `waiting_for_approval` when the linked agent run creates open approval requests. The task page links to the Agent Console run and to the Approval Queue for follow-up review.

Task records store `agent_name`, `module`, `task_type`, `status`, `priority`, `input_config`, lifecycle timestamps, `linked_run_id`, and `result_summary`.

Running a task does not send messages, publish content, post comments, scrape platforms, schedule posts, create calendar events, or call external CRM/platform APIs.

## System Overview

signalForge combines three working surfaces:

- **Automation services** in `services/` for scraping, enrichment, signal processing, post generation, and API access.
- **Structured storage** in MongoDB for leads, companies, campaigns, signals, generated content, and pipeline events.
- **Human-readable knowledge** in `vault/`, mounted into every service at `/vault`, so generated outputs can become Obsidian notes.

```text
External Sources
  -> lead_scraper
  -> MongoDB
  -> lead_enricher
  -> social_processor
  -> post_generator
  -> /vault markdown outputs
  -> api
```

## Creative Studio v2 — Social Creative Engine

Creative Studio v2 extends the content planning workflow with a full social creative pipeline: client profiles, source channel management, content ingestion, transcript-based snippet scoring, and creative asset review. No content is published or scheduled.

**New collections (v2):**

| Collection | Purpose |
|---|---|
| `client_profiles` | Brand permissions, compliance rules, allowed content types. Likeness/voice/avatar default off. |
| `source_channels` | Channels approved for ingestion and content reuse. |
| `source_content` | Discovered videos and posts. Must reach `approved` before snippets are extracted. |
| `content_transcripts` | Full transcripts from source content. |
| `content_snippets` | Scored transcript segments. Each requires operator review before asset generation. |
| `creative_assets` | Generated images, reels, and captions. Require review before any external use. |
| `creative_tool_runs` | Records of ComfyUI or manual tool invocations. |

**Safety:** All v2 records are `simulation_only: true` and `outbound_actions_taken: 0`. Likeness, voice, and avatar permissions default to `false`. No asset is published or scheduled automatically.

**ComfyUI integration (optional):** Set `COMFYUI_ENABLED=true` in `.env` to enable local image/video generation via ComfyUI. If disabled (default), tool runs are recorded with `status=skipped`. If enabled but unavailable, runs fail safely with a `creative_tool_run` error record.

```bash
COMFYUI_ENABLED=true
COMFYUI_BASE_URL=http://host.docker.internal:8188
COMFYUI_WORKFLOW_PATH=/path/to/workflow.json
```

**Dashboard:** The Creative Studio page now includes Clients, Source Channels, Source Content, Snippets, Assets, Approval Queue, Ingest Pipeline, and **Prompt Library** tabs.

## Social Creative Engine v4.5 — Prompt Generator Library

v4.5 adds a structured visual prompt generation layer on top of the v4 approval pipeline. Approved content snippets feed into the Prompt Generator to produce structured visual prompts for faceless short-form creative content.

**Supported prompt types:** `faceless_motivational`, `cinematic_broll`, `abstract_motion`, `business_explainer`, `quote_card_motion`, `podcast_clip_visual`, `educational_breakdown`, `luxury_brand_story`, `product_service_ad`.

**Supported engine targets:** `comfyui` (default, local only), `seedance`, `higgsfield`, `runway`, `manual`. No engine is auto-invoked — operator runs generation externally after prompt approval.

**Safety:**
- Snippets must be `status='approved'` before a prompt can be generated.
- `use_likeness=True` requires explicit `avatar_permissions` or `likeness_permissions` on the client profile.
- Default negative prompt always blocks identifiable faces, likenesses, and voice cloning.
- All records carry `simulation_only: true`, `outbound_actions_taken: 0`.
- Prompts start as `draft` and require operator review before use.

## Social Creative Engine v5 — Asset Rendering

v5 adds a rendering pipeline on top of the v4.5 prompt approval layer. An approved prompt generation can be rendered into a short-form vertical video (9:16 mp4) by combining a ComfyUI-generated image with snippet audio via FFmpeg.

**Key features:**
- `POST /assets/render` — triggers render from approved snippet + approved prompt_generation.
- `GET /assets` — lists rendered assets with workspace/status/engine filters.
- `POST /assets/{id}/review` — operator review: approve / reject / revise.
- **Rendered Assets tab** in Creative Studio dashboard: filter, preview, and review renders inline.
- Mock render support: `COMFYUI_ENABLED=false` and `FFMPEG_ENABLED=false` (both default) produce safe mock records with no subprocess calls.
- Caption overlay: optional `add_captions=true` burns caption text via FFmpeg drawtext filter.

**v5 Runtime Infrastructure:**
- **Redis** service (`signalforge-redis`) — job queue for async render handoff.
- **Worker** service (`signalforge-worker`) — polls Redis, processes renders (queued → running → generated → needs_review or failed).
- **ComfyUI** service — available via `docker compose --profile comfyui up` (stub server included for local dev; disabled by default).
- FFmpeg installed in the API/worker Docker image; gated by `FFMPEG_ENABLED`.
- Shared `render-output` Docker volume between api and worker containers.
- **Graceful fallback**: if Redis is unreachable, render runs synchronously inline.

**v5.5 — Real Local FFmpeg Render:**
- `FFMPEG_ENABLED=true` is now the default — the worker produces actual `.mp4` files locally.
- `generate_test_tone()` auto-generates a 440 Hz sine-wave WAV via FFmpeg lavfi when no audio is provided (no external downloads).
- `_placeholder_image()` generates a 1080×1920 placeholder PNG via FFmpeg lavfi when no image is provided.
- `assembly_status` (`success` / `failed` / `mock`) and `assembly_engine` (`ffmpeg` / `mock`) stored on every render record.
- `GET /health/ffmpeg` endpoint returns `ffmpeg_available`, `ffmpeg_path`, `ffmpeg_version`, `ffmpeg_enabled`.
- Duration derived from `snippet.end_time - snippet.start_time` when both fields are set.
- Dashboard shows green "Real Render" badge and violet "FFmpeg" engine badge for real renders.

**v6 — ComfyUI Image Generation:**
- `COMFYUI_ENABLED=true` activates real image generation via a local ComfyUI instance. Defaults to `false`.
- `comfyui_client.py`: submits a KSampler workflow built from `prompt_generation` fields → polls until done → downloads image to shared volume.
- ComfyUI stub included: `docker compose --profile comfyui up -d` starts a pure-Python stub that accepts ComfyUI API calls and returns a real PNG (no GPU required).
- `image_source: "comfyui"` or `"placeholder"` stored on every render. Dashboard shows sky "ComfyUI Image" badge or slate "Placeholder" badge.
- Graceful fallback: if ComfyUI is unreachable or returns no image, the worker uses the FFmpeg placeholder — render reaches `needs_review`, not `failed`.
- `comfyui_partial_failure: true` and `fallback_reason` recorded when fallback occurs.
- `GET /health/comfyui` endpoint returns `comfyui_enabled`, `comfyui_base_url`, `comfyui_reachable`.
- `COMFYUI_MODEL_CHECKPOINT` env var selects the checkpoint (defaults to `v1-5-pruned-emaonly.safetensors`).

**v6.5 — Snippet Scoring and Hook Optimization:**
- `snippet_scorer.py`: deterministic, local scoring of transcript snippets. Uses only Python stdlib — no external APIs.
- 5 quality dimensions: `hook_strength` (30%), `clarity_score` (20%), `emotional_impact` (20%), `shareability_score` (20%), `platform_fit_score` (10%).
- `POST /content-snippets/{id}/score` scores a snippet and stores all fields + `scored_at` timestamp.
- Score gate: if a snippet has been scored and `overall_score < SNIPPET_SCORE_THRESHOLD` (default 6.0), prompt generation is blocked with a 422.
- Hook extraction: `hook_text`, `hook_type` (curiosity/bold_statement/contrarian/emotional/educational/story), and 3 `alternative_hooks` per snippet.
- Hook-enhanced prompts: `hook_text` is injected into `scene_beats[0]` and `caption_overlay_suggestion` in `generate_prompt()`.
- Dashboard: score breakdown bars, hook display, Score Snippet button, min-score filter slider on Snippets tab.
- Unscored snippets bypass the gate — fully backwards compatible with v6 and earlier.
- `SNIPPET_SCORE_THRESHOLD` env var (default `6.0`) controls the quality gate.

**v7 — Real Local Transcription:**
- `transcript_provider.py`: opt-in real transcription via `openai-whisper` (fully on-device, no external calls).
- Double gate: `TRANSCRIPT_PROVIDER=whisper` AND `TRANSCRIPT_LIVE_ENABLED=true` both required; defaults silently to stub.
- `WhisperTranscriptProvider` validates the audio file path, loads the configured model (`WHISPER_MODEL`, default `base`), and returns typed segments with `start_ms`, `end_ms`, `text`, `speaker`, `confidence`, `index`, `provider`.
- `POST /transcript-runs/v4` records `input_path`, `status` (`complete`/`failed`), `error_message`, and all segments in MongoDB.
- `AUTO_SCORE_SNIPPETS=true` automatically runs v6.5 snippet scoring after snippet generation — no extra API call needed.
- Frontend Ingest Pipeline tab: provider badge (whisper/stub), run status badge, segment count, inline error message panel.
- FFmpeg is already installed in the Docker image from v5.5; `openai-whisper` is installed from `requirements.txt` — no new container needed.

**Safety:**
- Both snippet AND prompt_generation must be `status='approved'` before any render can start.
- All renders start as `status: needs_review` — no auto-publish path exists.
- `COMFYUI_ENABLED` defaults to `false`. `FFMPEG_ENABLED` defaults to `true` (local subprocess only).
- All records carry `simulation_only: true`, `outbound_actions_taken: 0`.
- ComfyUI calls are made only to the local `COMFYUI_BASE_URL` — no external image APIs.
- FFmpeg writes only to local filesystem (`FFMPEG_OUTPUT_DIR`, default `/tmp/signalforge_renders`) — no uploads to external services.

**v7.5 — Performance Feedback & Learning Loop:**
- Three new collections: `manual_publish_logs`, `asset_performance_records`, `creative_performance_summaries`.
- `manual_publish_logs`: record when and where an operator manually posted an asset outside SignalForge. No publishing, no scheduling, no social API calls.
- `asset_performance_records`: store platform metrics (views, likes, saves, shares, etc.) entered by the operator from the platform dashboard. A deterministic performance score (0.0–10.0) is calculated locally: `0.25×reach + 0.20×engagement + 0.20×saves + 0.15×shares + 0.15×retention + 0.05×clicks`. Same inputs always produce the same score.
- `creative_performance_summaries`: aggregated per-asset summary with `advisory_only` learning-loop recommendations (top hook types, prompt types, engines, platforms ranked by average score). No automatic approvals, no outbound actions.
- CSV import: paste performance data locally, validated row-by-row; invalid rows stored in `import_errors` without crashing the import.
- Frontend: "Performance Loop" tab in Creative Studio with 4 sub-tabs: Publish Log, Performance Entry (with live score preview), CSV Import, Summaries & Recommendations.
- All records carry `simulation_only: true`, `outbound_actions_taken: 0`. No platform API calls at any step.

**v8 — Client Campaign Packs:**
- Three new collections: `campaign_packs`, `campaign_pack_items`, `campaign_reports`.
- `campaign_packs`: top-level record for a named client campaign — stores goals, platforms, audience, themes, and lists of all referenced pipeline item IDs (source content, snippets, prompts, renders, publish logs, performance records).
- `campaign_pack_items`: individual pipeline items attached to a pack, typed by stage (`source_content`, `snippet`, `prompt_generation`, `asset_render`, `publish_log`, `performance_record`). Items are workspace- and client-isolated at insert time.
- `campaign_reports`: advisory report generated from a pack — includes executive summary, top snippets, best hooks, best prompt types, top assets, performance summary, lessons learned, and next-batch recommendations. Status lifecycle: draft → needs_review → approved. Approving does not trigger any publishing or outbound action.
- Pack reports are generated locally from existing performance data — no social API calls.
- All records carry `simulation_only: true`, `outbound_actions_taken: 0`. Reports are `advisory_only: true`.
- Frontend: "Campaign Packs" tab in Creative Studio with 5 sub-tabs: All Packs, Create Pack, Add Items, Pack Detail (pipeline timeline with safety badges), Reports (review/approve workflow).

**v8.5 — Client Export Package:**
- New collection: `campaign_exports`. Each record links a campaign pack + report into a deliverable export file on the local filesystem.
- Supported formats: `markdown` (single `.md`), `zip` (report.md + referenced local assets + manifest.json), `pdf_placeholder` (markdown with PDF conversion note).
- Export path lives under `SIGNALFORGE_EXPORT_DIR` (default: `/tmp/signalforge_exports/{workspace}/{pack_id}/`). No uploading, emailing, scheduling, or outbound action occurs at any step — including after review approval.
- Review workflow: `approve` → `approved`, `reject` → `rejected`, `revise` → `needs_review`. Approving does NOT publish or distribute anything.
- All exports carry `simulation_only: true`, `outbound_actions_taken: 0`. Safety notes embedded in every export file and every API response.
- Frontend: "Exports" tab in Creative Studio — Create Export (select pack + report + format), All Exports list, Export Detail with safety notes + included assets, Review Export form (approve/reject/revise).

## Local Setup

1. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add any API keys you want to use. Keep `GPT_AGENT_ENABLED=false` unless you want review-only GPT planning.

3. Start the stack:

   ```bash
   docker compose up --build
   ```

4. Open the API health endpoint:

   ```bash
   curl http://localhost:8000/health
   ```

5. Open `vault/` as an Obsidian vault.

## Services

- `lead_scraper`: placeholder lead collection service.
- `lead_enricher`: placeholder AI enrichment service.
- `social_processor`: placeholder social signal processor.
- `post_generator`: placeholder content generation service.
- `api`: minimal FastAPI service for health checks and basic system status.
- `mongo`: MongoDB backing store.

## Daily Pipeline

Run the contractor lead engine locally with:

```bash
./scripts/run_daily_pipeline.sh --business-type "roofing contractor" --location "Austin, TX" --count 5
```

The pipeline imports structured contractor listings, stores them in MongoDB, enriches each lead with v3 intelligence, writes lead and company notes, and creates human review notes in `vault/review_queue`. Reviewed leads can be prepared for outreach with `scripts/review_lead.py`, then tracked through a CRM-lite lifecycle with `scripts/update_outreach_status.py`.

## Current v1 Workflow

Use the Makefile for the stabilized local workflow:

```bash
make up
make dashboard
make pipeline
make report
make revenue-report
make check
```

Daily operator loop:

1. Run the pipeline with `make pipeline`.
2. Review leads in `vault/review_queue`.
3. Mark each lead with `scripts/review_lead.py` as `pursue`, `skip`, or `research_more`.
4. For pursued leads, use `scripts/update_outreach_status.py` to track `drafted`, `sent`, `replied`, `follow_up_needed`, `booked_call`, `closed_won`, or `closed_lost`.
5. Generate the dashboard reports with `make report` and `make revenue-report`.
6. Open `vault/00_Dashboard.md`, `vault/reports/contractor_pipeline_report.md`, and `vault/reports/revenue_performance_report.md` in Obsidian.

Run a full system check with:

```bash
make check
```

## Contact Ingestion

SignalForge can import client-provided contact lists into MongoDB for module-aware agent planning. Imports are local, CSV-based, and do not send messages or enrich contacts externally.

```bash
python scripts/import_contacts.py data/imports/sample_contacts.csv --module insurance_growth --source "client_provided_list"
```

Imported contacts are stored in the `contacts` collection with `contact_status=imported`, and a summary note is written to `vault/contacts/`.

Score and segment imported contacts with:

```bash
python scripts/score_contacts.py --module insurance_growth
```

Scored contacts receive `contact_score`, `segment`, `priority_reason`, and `recommended_action` fields in MongoDB. A segmentation report is written to `vault/contacts/`, and simulation agents prefer `high_priority` contacts first.

Generate editable message drafts for high-priority contacts and approved leads with:

```bash
python scripts/draft_messages.py --module insurance_growth --limit 5
```

Drafts are stored in the `message_drafts` collection and written to `vault/messages/` with `review_status=needs_review` and `send_status=not_sent`. SignalForge does not send messages.

Review drafts before any manual send:

```bash
python scripts/review_message.py <draft-slug-or-id> approve --note "Approved for manual send."
python scripts/review_message.py <draft-slug-or-id> revise --note "Make the tone warmer."
python scripts/review_message.py <draft-slug-or-id> reject --note "Not a fit."
```

Approvals keep `send_status=not_sent`; this system still does not send messages.

After an operator manually sends an approved draft outside SignalForge, log the event with:

```bash
python scripts/log_manual_send.py <draft-slug-or-id> --channel email --note "Sent manually from Gmail."
python scripts/log_manual_send.py <draft-slug-or-id> --channel phone --note "Called and left voicemail."
```

Manual send logging requires `review_status=approved`, sets `send_status=sent`, and updates the linked lead or contact lifecycle. SignalForge still does not send anything.

Log responses after a manual send with:

```bash
python scripts/log_response.py <draft-slug-or-id> --outcome interested --note "Asked for pricing details."
python scripts/log_response.py <draft-slug-or-id> --outcome call_booked --note "Discovery call booked manually."
```

Response logging requires `send_status=sent`, updates the linked lead or contact status, and appends to the message note. `call_booked` also adds meeting prep. SignalForge does not create calendar events.

Generate a standalone call prep note from a contact, lead, or message draft:

```bash
python scripts/generate_meeting_prep.py <contact-lead-or-draft-slug>
```

Meeting prep notes are written to `vault/meetings/` using only local MongoDB and markdown context.

Track deal outcomes after meetings with:

```bash
python scripts/log_deal_outcome.py <contact-lead-draft-or-meeting-slug> --outcome closed_won --deal-value 2500 --note "Client approved starter engagement."
python scripts/log_deal_outcome.py <contact-lead-draft-or-meeting-slug> --outcome closed_lost --note "Budget not available this quarter."
```

Deal notes are written to `vault/deals/`, linked Mongo records are updated, and no invoice or CRM integration is created.

Generate a cross-module revenue and performance report with:

```bash
python scripts/generate_revenue_report.py
```

The report is written to `vault/reports/revenue_performance_report.md` and summarizes contacts, leads, messages, responses, meeting indicators, deals, closed-won value, conversion paths, top modules, nurture contacts, and open opportunities using MongoDB data only.

## SignalForge Modules

Modules are reusable strategy packs for a specific client, industry, or audience. They define the client profile, personas, signal sources, scoring rules, outreach templates, content strategy, campaign plan, KPIs, and operator workflow before new services or integrations are added.

Start a new module from:

```bash
modules/_template
```

See [docs/MODULE_CREATION_GUIDE.md](docs/MODULE_CREATION_GUIDE.md) for examples covering insurance, contractors, media, music artists, real estate, and professional services.

Available documentation-first modules:

- [Insurance Growth](modules/insurance_growth/README.md)
- [Artist Growth](modules/artist_growth/README.md)
- [Media Growth](modules/media_growth/README.md)
- [Module Template](modules/_template/README.md)

## Agent Layer

SignalForge includes a simulation-only agent layer for planning work across modules. Agents read MongoDB, use module context, print planned actions, and write run logs to `vault/logs/agents/`. When GPT is enabled, supported agents may call OpenAI to create review-only drafts, recommendations, artifacts, or approval requests. They do not send email, SMS, DMs, social posts, publish content, or call external platform APIs.

Example dry runs:

```bash
python scripts/run_agent.py outreach --module contractor_growth --dry-run
python scripts/run_agent.py content --module artist_growth --dry-run
python scripts/run_agent.py fan_engagement --module artist_growth --dry-run
python scripts/run_agent.py followup --module insurance_growth --dry-run
```

See [agents/README.md](agents/README.md) for the supported agent roles.

## Agent Console v1

The Web Dashboard now includes an Agent Console that records every dry-run agent process in MongoDB:

- `agent_runs`
- `agent_steps`
- `agent_artifacts`
- `approval_requests`

Each run stores status, inputs, outputs, related contacts/leads/messages/deals, step-by-step decisions, artifacts, and human approval requests. The console is observability only: agents remain simulation-only and never send outbound messages or publish content.

The Messages page now supports full draft review with message body, recipient details, linked records, response history, and approval/send/response timeline. The CRM detail drawer shows linked lifecycle activity across import, scoring, draft review, send logging, response logging, meeting prep signals, and deal outcomes.

## Project Principles

- Local-first by default.
- Markdown outputs stay readable and portable.
- Structured data lives in MongoDB.
- Services remain independently runnable.
- AI behavior is prompt-driven and observable through the vault.
# signal-forge

---

### v9.5 — Client Intelligence Layer

v9.5 introduces a structured **client intelligence layer** that links acquisition data (leads, deals) to content performance (performance records, campaign reports) and generates deterministic, advisory-only insights per client.

**New capabilities:**
- **`client_intelligence_records`** collection: aggregates acquisition score, content performance score, estimated ROI, top performers (hook types, prompt types, platforms), insights, and recommendations — all deterministic, no ML.
- **`lead_content_correlations`** collection: groups performance records by (content theme, hook type, prompt type, platform) and classifies each group as `strong` / `moderate` / `weak`.
- **`client_intelligence.py`** module: pure-Python, rule-based, no external calls, fully unit-testable in isolation.
- **PATCH extensions** for `client_profiles`, `campaign_packs`, and `asset_performance_records` to link acquisition and funnel data.
- **Frontend "Intelligence" tab** in Creative Studio with 5 sub-sections: Client Overview, Top Performers, Insights, Recommendations, Correlations.

**v9.5 Safety guarantees:**
- All intelligence and correlation records permanently carry `simulation_only: true`, `outbound_actions_taken: 0`, `advisory_only: true`.
- Generating intelligence never modifies existing records.
- No external API calls, no posting, no scheduling, no DMs at any step.
- Workspace and client isolation enforced at every endpoint.

---

### v10 — POC Demo Mode (13-Step Guided Walkthrough)

v10 adds a fully self-contained **POC Demo Mode** for client demos, investor presentations, and operator onboarding. The entire pipeline is walkable without a backend connection, without MongoDB, and with zero outbound actions.

**New capabilities:**
- **`PocDemoTab.jsx`** — a 13-step guided walkthrough component inside Creative Studio with progress tracking, step-dot navigation, CTA buttons that open the relevant section, and a full safety card per step.
- **Progress system** — `getDemoProgress`, `setDemoProgress`, `nextDemoStep`, `prevDemoStep`, `jumpDemoStep`, `resetDemoProgress` — all localStorage-only, no backend calls.
- **8 new v10 seed collections** in `demoMode.js`: `manual_publish_logs`, `asset_performance_records`, `creative_performance_summaries`, `campaign_packs`, `campaign_reports`, `campaign_exports`, `client_intelligence`, `lead_content_correlations`.
- **Full api.js demo branches** for all v10 collections — demo mode returns localStorage data, real mode calls the backend. Generate methods return synthetic success responses in demo mode without calling fetch.

**The 13 walkthrough steps prove:**

| Steps | Pipeline stage |
|-------|---------------|
| 1–2 | Client workspace setup |
| 3 | Source channel ingestion |
| 4 | Approved source content |
| 5 | Transcript ingest pipeline |
| 6 | Snippet scoring + approval |
| 7 | GPT prompt generation review |
| 8 | Asset render pipeline |
| 9 | Publish log → performance record loop |
| 10–11 | Campaign pack assembly + report approval |
| 12 | Local-only export delivery |
| 13 | AI-advisory client intelligence |

**v10 Safety guarantees:**
- The POC Demo walkthrough makes **zero backend calls** — all data from localStorage only.
- All demo records carry `simulation_only: true`, `outbound_actions_taken: 0`, `is_demo: true`.
- Intelligence and correlation records additionally carry `advisory_only: true`.
- Real API endpoints never return `is_demo: true` records.
- No content is published, scheduled, emailed, or distributed at any step.
- Switching to Real Mode instantly hides all demo data — real MongoDB is never touched.
