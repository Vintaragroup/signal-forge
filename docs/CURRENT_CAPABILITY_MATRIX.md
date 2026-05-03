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

---

## Social Creative Engine v5.5 — Real Local FFmpeg Render

| Capability | Dashboard-supported | Simulated | Manual | Real/local | Notes |
|---|---|---|---|---|---|
| Real local MP4 generation | Yes | No | No | Yes | `FFMPEG_ENABLED=true` (now default). Worker calls FFmpeg subprocess to produce actual `.mp4` file. |
| Test tone fallback | No | N/A | N/A | Yes | `generate_test_tone()` creates a 440 Hz sine-wave WAV via FFmpeg lavfi when no `source_audio_path` is provided. No external downloads. |
| Placeholder visual | No | N/A | N/A | Yes | `_placeholder_image()` generates a 1080×1920 dark-background PNG with SignalForge label via FFmpeg lavfi when no `image_path` provided. |
| assembly_status field | Yes | N/A | N/A | N/A | `success` / `failed` / `mock` / `skipped`. Stored on every render record and shown in dashboard. |
| assembly_engine badge | Yes | N/A | N/A | N/A | `ffmpeg` or `mock`. Dashboard badge in Rendered Assets tab. |
| duration_seconds from snippet | No | N/A | N/A | Yes | Worker derives `duration_seconds = end_time − start_time` from snippet when both fields are set. |
| GET /health/ffmpeg | No | N/A | N/A | Yes | Returns `ffmpeg_available`, `ffmpeg_path`, `ffmpeg_version`, `ffmpeg_enabled`. |
| FFmpeg diagnostics at worker startup | No | N/A | N/A | Yes | Worker logs FFmpeg availability, path, and version line on startup. |
| Real Render badge | Yes | N/A | N/A | N/A | Dashboard shows green "Real Render" badge when `assembly_status=success`, violet "FFmpeg" engine badge when `assembly_engine=ffmpeg`. |
| Local render file path display | Yes | N/A | N/A | N/A | Dashboard Rendered Assets tab shows "Local render — /tmp/signalforge_renders/..." for real renders vs "Mock path —" for mock. |
| Assembly error display | Yes | N/A | N/A | N/A | `assembly_result.error` shown in dashboard on failed renders. |

### v5.5 Safety Boundary

All v5 and v5 Runtime safety guarantees are preserved. `FFMPEG_ENABLED=true` is now the default — FFmpeg is invoked **locally** via subprocess only, writing `.mp4` files to the `render-output` Docker volume (`/tmp/signalforge_renders`). No file is uploaded, streamed, or sent to any external service. The test tone generator uses FFmpeg lavfi (a built-in source) — it never downloads audio from any URL. The placeholder image generator uses FFmpeg lavfi color source — no network calls. All renders remain `simulation_only: true`, `outbound_actions_taken: 0`. ComfyUI remains disabled by default (`COMFYUI_ENABLED=false`). Approved renders still require explicit operator action before any downstream use.

---

## Social Creative Engine v6 — ComfyUI Image Generation

| Capability | Dashboard-supported | Simulated | Manual | Real/local | Notes |
|---|---|---|---|---|---|
| ComfyUI image generation | Partial | No | No | Yes | `COMFYUI_ENABLED=true` required. Worker submits workflow to ComfyUI, polls until done, downloads PNG to shared volume. |
| ComfyUI stub (no GPU) | Yes | N/A | N/A | Yes | `docker compose --profile comfyui up -d` starts a pure-Python FastAPI stub that accepts ComfyUI API calls and returns a real PNG. |
| Workflow auto-build from prompt_generation | No | N/A | N/A | Yes | `build_txt2img_workflow()` constructs 7-node KSampler workflow from `positive_prompt`, `negative_prompt`, `visual_style`, `lighting`, `camera_direction`. |
| Custom workflow file | No | N/A | N/A | Yes | Set `COMFYUI_WORKFLOW_PATH` to a JSON file path; loaded in preference over auto-built workflow. |
| image_source field | Yes | N/A | N/A | N/A | `"comfyui"` or `"placeholder"`. Set on every render record. Dashboard shows sky "ComfyUI Image" or slate "Placeholder" badge. |
| comfyui_partial_failure | Yes | N/A | N/A | N/A | `true` when ComfyUI was enabled but failed; render still completes via fallback. |
| Graceful fallback on ComfyUI failure | No | N/A | N/A | Yes | Unreachable ComfyUI → placeholder image used; render reaches `needs_review` not `failed`. `fallback_reason` stored. |
| GET /health/comfyui | No | N/A | N/A | Yes | Returns `comfyui_enabled`, `comfyui_base_url`, `comfyui_reachable`, `comfyui_error`, `system_stats`. |
| ComfyUI image badge | Yes | N/A | N/A | N/A | Sky "ComfyUI Image" badge when `image_source=comfyui`. Amber fallback notice when partial failure. |
| os.path.isfile guard | No | N/A | N/A | Yes | If ComfyUI returns a path that doesn't exist on disk, worker falls back to placeholder. Never passes a non-existent path to FFmpeg. |

### v6 Safety Boundary

All v5.5 guarantees are preserved. ComfyUI calls are made only to the local endpoint specified by `COMFYUI_BASE_URL` — no external image generation APIs. The worker never posts generated images externally. `simulation_only: true` and `outbound_actions_taken: 0` are maintained on every path, including ComfyUI success, ComfyUI failure, and fallback. GPU is not required — the built-in stub runs on CPU. `COMFYUI_ENABLED=false` is the default; the ComfyUI service requires the `comfyui` Docker profile to start.

---

## Social Creative Engine v6.5 — Snippet Scoring and Hook Optimization

| Capability | Dashboard-supported | Simulated | Manual | Real/local | Notes |
|---|---|---|---|---|---|
| Snippet scoring (deterministic) | Yes | No | No | Yes | `snippet_scorer.py` scores any transcript text. Dimensions: hook_strength, clarity_score, emotional_impact, shareability_score, platform_fit_score. All stdlib — no external APIs. |
| Overall score (weighted) | Yes | N/A | N/A | N/A | Weighted: hook×0.30 + clarity×0.20 + emotional×0.20 + shareability×0.20 + platform×0.10. Range 0.0–10.0. |
| Hook extraction | Yes | N/A | N/A | N/A | Extracts hook_text (first strong sentence), hook_type (curiosity/bold_statement/contrarian/emotional/educational/story), 3 alternative_hooks per snippet. |
| Score gate for prompt generation | No | N/A | N/A | Yes | If snippet has been scored (`scored_at` set) and `overall_score < SNIPPET_SCORE_THRESHOLD` (default 6.0), POST /prompt-generations returns 422. Unscored snippets pass through unchanged. |
| POST /content-snippets/{id}/score | No | N/A | N/A | Yes | Scores a snippet on demand. Stores all score fields + `scored_at` timestamp. |
| GET /content-snippets?min_score= | Yes | N/A | N/A | N/A | Filters snippets by overall_score. `min_score=0` (default) returns all. |
| Hook-enhanced prompt generation | No | N/A | N/A | Yes | hook_text prepended to scene_beats and used as caption_overlay_suggestion in `generate_prompt()`. |
| Score breakdown UI | Yes | N/A | N/A | N/A | Per-dimension progress bars in SnippetRow expanded view. Color: emerald ≥7, amber ≥5, red <5. |
| Score Snippet / Re-score button | Yes | N/A | N/A | N/A | Triggers POST /content-snippets/{id}/score. Shows SnippetScorePanel on click. |
| Min score filter slider | Yes | N/A | N/A | N/A | Range slider on Snippets tab. Filters visible snippets client-side; default "off" (0). |

### v6.5 Safety Boundary

All v6 guarantees are preserved. `snippet_scorer.py` uses only Python stdlib (`re`, `dataclasses`) — no network calls, no external APIs, no LLM calls. Scoring is fully deterministic and local. `simulation_only: true` and `outbound_actions_taken: 0` are maintained on all new code paths (score endpoint, score gate, prompt hook injection). The score gate is opt-in — it only fires once a snippet has been explicitly scored; existing unscored snippets are unaffected.

---

## Social Creative Engine v7 — Real Local Transcription Provider

| Capability | Dashboard-supported | Simulated | Manual | Real/local | Notes |
|---|---|---|---|---|---|
| WhisperTranscriptProvider | No | N/A | N/A | Yes | Fully on-device using `openai-whisper`. No audio sent to external services. Requires `TRANSCRIPT_PROVIDER=whisper` AND `TRANSCRIPT_LIVE_ENABLED=true`. Falls back to stub if either gate missing. |
| StubTranscriptProvider (default) | Yes | Yes | N/A | N/A | Always enabled; produces deterministic synthetic segments. Default when no gates are set. |
| Double gate safety | N/A | N/A | N/A | Yes | Two independent env vars required to activate Whisper: `TRANSCRIPT_PROVIDER=whisper` + `TRANSCRIPT_LIVE_ENABLED=true`. Any misconfiguration silently falls back to stub. |
| Audio file validation | N/A | N/A | N/A | Yes | `os.path.isfile()` checked before transcription. Missing file → `status=failed`, `error_message` stored. No crash. |
| Transcript run error handling | Yes | N/A | N/A | Yes | All provider exceptions caught. Failed runs stored with `status=failed`, `error_message`, `segment_count=0`. |
| `input_path` field on run | No | N/A | N/A | Yes | Path to audio file used for transcription stored on `transcript_run` record. |
| `error_message` field on run | Yes | N/A | N/A | Yes | Populated on failure; empty string on success. Displayed in frontend Ingest Pipeline tab. |
| AUTO_SCORE_SNIPPETS | No | N/A | N/A | Yes | When `AUTO_SCORE_SNIPPETS=true`, each snippet from `/generate-snippets/v4` is auto-scored immediately. Scoring failure is non-fatal. |
| Ingest Pipeline transcript status | Yes | N/A | N/A | N/A | Shows provider badge, status badge, segment count, and error message panel per content item. |
| WHISPER_MODEL env var | N/A | N/A | N/A | Yes | Controls model size: tiny/base/small/medium/large. Default: base. |

### v7 Safety Boundary

All v6.5 guarantees are preserved. `openai-whisper` is a local Python library — no audio data leaves the machine. No external API keys, no network calls during transcription. The double gate (`TRANSCRIPT_PROVIDER=whisper` AND `TRANSCRIPT_LIVE_ENABLED=true`) ensures stub mode is the safe default for any misconfiguration. `simulation_only: true` and `outbound_actions_taken: 0` on all transcript runs, segments, and auto-scored snippets. No social API calls, no posting, no scheduling, no avatar/voice cloning.

---

## v7.5 Capability Matrix — Performance Feedback & Learning Loop

| Capability | v7 | v7.5 | Notes |
|---|---|---|---|
| Manual publish log | No | Yes | Operator records where/when they manually posted. No publishing, no scheduling. |
| Asset performance records | No | Yes | Operator enters metrics from platform dashboard. No platform API called. |
| Deterministic performance score | No | Yes | 0.0–10.0 weighted formula. Same inputs → same output always. |
| Auto-derived engagement rate | No | Yes | When `engagement_rate < 0`, auto-calculated from likes+comments+shares+saves / views. |
| Performance CSV import | No | Yes | Paste CSV locally; invalid rows stored in `import_errors`, valid rows imported. Max 1000 rows. |
| Creative performance summary | No | Yes | Per-asset aggregate summary with best/avg score, winning factors, improvement notes. |
| Learning-loop recommendations | No | Yes | Top hook types, prompt types, engines, platforms ranked by avg score. Advisory only. |
| Advisory-only guarantee | N/A | Yes | `advisory_only: true` on all recommendations. No auto-approvals, no auto-publishing. |
| CSV import error safety | N/A | Yes | Invalid rows never crash the import; stored separately in `import_errors`. |
| Frontend Performance Loop tab | No | Yes | 4 sub-tabs: Publish Log, Performance Entry, CSV Import, Summaries & Recommendations. |
| Live score preview | No | Yes | Frontend mirrors backend formula in JS for instant preview as operator types metrics. |
| Score color coding | N/A | Yes | ≥7 green, ≥4 amber, <4 red across all score displays. |
| Workspace isolation | Yes | Yes | All queries filtered by `workspace_slug`. Cross-workspace records never returned. |
| Client isolation | Yes | Yes | `client_id` filter supported on all new endpoints. |
| simulation_only | Yes | Yes | All new record types carry `simulation_only: true` — always. |
| outbound_actions_taken | Yes | Yes | Always `0` on all new record types — no outbound actions possible. |
| Platform API calls | None | None | v7.5 makes zero calls to any social platform API. |
| Auto-approve on high score | N/A | Never | Performance data never triggers snippet or asset approval changes. |

### v7.5 Safety Boundary

All v7 guarantees are preserved. No social platform API is called at any point in the v7.5 pipeline. Performance metrics are entered by the operator from external platform dashboards. Scores are calculated entirely locally using a deterministic formula. Recommendations are advisory and surfaced for human review only — no code path acts on them automatically. CSV import is fully local with row-level validation. All new collections carry `simulation_only: true` and `outbound_actions_taken: 0`.

---

## v8 — Client Campaign Packs

| Capability | Status | Notes |
|---|---|---|
| Create campaign pack | ✅ | POST /campaign-packs; status_code=201 |
| List campaign packs | ✅ | Filterable by workspace, client, status |
| Campaign pack detail | ✅ | Returns pack + all pack_items |
| Add item to pack | ✅ | 6 item types; workspace/client validated |
| Generate campaign report | ✅ | Advisory only; no outbound actions |
| List campaign reports | ✅ | Filterable by workspace, client, pack, status |
| Review campaign report | ✅ | approve/reject/revise; no auto-publish |
| Workspace isolation | ✅ | Cross-workspace items rejected at API layer |
| Client isolation | ✅ | Cross-client items rejected at API layer |
| Frontend Campaign Packs tab | ✅ | 5 sub-tabs in Creative Studio |
| simulation_only on all records | ✅ | campaign_packs, campaign_pack_items, campaign_reports |
| outbound_actions_taken: 0 always | ✅ | All v8 record types |
| advisory_only on all reports | ✅ | Reports never trigger publishing |
| No social API calls | ✅ | All data local-only |

### v8 Safety Boundary

Approving a `campaign_report` does not publish content, schedule posts, change the status of snippets or assets, or call any external API. Campaign packs and reports are packaging and advisory artifacts only. All v8 collections carry `simulation_only: true` and `outbound_actions_taken: 0`. Pack items are cross-validated at insert time — a workspace or client mismatch is a hard 422 rejection. SignalForge never sends, schedules, or triggers any outbound message or post at any step of the v8 flow.
