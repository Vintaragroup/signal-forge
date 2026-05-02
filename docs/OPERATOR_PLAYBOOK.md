# Operator Playbook

This playbook describes the daily workflow for the current SignalForge Contractor Lead Engine.

## 0. Choose Your Mode

Before doing any work, confirm you are in the correct mode. The mode button is in the top-right header.

| Mode | Use When | Data |
|------|----------|------|
| **Real Mode** (blue) | Running an actual test campaign | Local MongoDB |
| **Demo Mode** (purple) | Showing clients / onboarding operators | Browser localStorage only |

**To switch modes:** Click the header mode button — a confirmation dialog appears. MongoDB is never touched in Demo Mode.

**To reset Demo data:** Click "Reset Demo Data" on any page with the purple banner or on the Demo Mode page. This restores seeded records without affecting MongoDB.

See [docs/MODES_AND_DEMO_GUIDE.md](MODES_AND_DEMO_GUIDE.md) for full mode documentation.

---

## 1. Start The Stack

```bash
make up
```

This starts MongoDB and the API through Docker Compose.

To use the browser dashboard:

```bash
make dashboard
```

Open `http://localhost:5174`. The dashboard reads MongoDB through the local API and keeps vault behavior unchanged.

The dashboard header shows GPT runtime status from `GET /settings/gpt-runtime`: enabled or disabled, plus the configured model when enabled.

## 1A. Optional GPT Runtime Gate

GPT Agent Runtime v1 is disabled by default. To enable review-only GPT planning, edit the local `.env` file:

```text
GPT_AGENT_ENABLED=true
OPENAI_API_KEY=<your-api-key>
OPENAI_MODEL=gpt-4o-mini
```

`OPENAI_MODEL` is optional; blank values use the runtime default. Keep `.env` local and do not commit real API keys.

When enabled, GPT can create human-reviewed outreach drafts, follow-up recommendations, content plans, fan engagement plans, agent artifacts, local markdown notes, and approval requests. GPT output is not approval to take action.

GPT cannot send emails, SMS, DMs, comments, social posts, publish content, scrape platforms, schedule posts, create calendar events, issue invoices, or call external CRM/platform APIs. Operators must review GPT outputs in the Agent Console, Messages page, approval requests, and vault notes before doing anything manually outside SignalForge.

## 1B. Optional Research / Tools Review

Agent Tool Layer v1 is available for safe local research review. It can be run manually from Docker or optionally from outreach/content agent dry-runs. It does not run real search APIs in v1; `SERPAPI_KEY` is reserved for future support.

Mock search example:

```bash
docker compose run --rm api python scripts/run_tool.py web_search --query "roofing contractor" --module contractor_growth --location "Austin, TX" --limit 3
```

Manual candidate CSV import example:

```bash
docker compose run --rm api python scripts/import_candidates.py data/imports/contractor_sources.csv --module contractor_growth --source-label "manual_contractor_test"
```

Manual candidate imports are also available in the dashboard Research / Tools page from the Import CSV panel. Use this for real prospect/source lists supplied by an operator or client. Expected CSV fields are:

```text
company,website,phone,email,city,state,service_category,notes,source_url
```

Imported rows are stored as `scraped_candidates` with `source=manual_upload`, `status=needs_review`, and the provided `source_label`. They use the same quality scoring, enrichment, source validation, duplicate detection, approval request creation, and conversion rules as other Research / Tools candidates. Importing does not create contacts or leads automatically.

Public website scrape example:

```bash
docker compose run --rm api python scripts/run_tool.py website_scraper --url https://example.com
```

Public browser-scroll example, when Playwright is installed in the API environment:

```bash
docker compose run --rm api python scripts/run_tool.py browser_scroll --url https://example.com
```

Review the resulting records in the dashboard Research / Tools page. Tool output lands in `scraped_candidates` with `status=needs_review` and creates an approval request. Approve the candidate first; only approved candidates can be converted into local contacts or leads.

Tool Layer v1 is read-only: no form submission, login, posting, messaging, captcha bypass, protected/private scraping, external CRM update, or outbound action. Agent tool usage creates research artifacts and approval requests only.

## 1C. Research Import Management Workflow

After importing a CSV of candidates, use the **Import History** section of the Research / Tools page to audit and act on the batch.

**Review Import History**

The Import History table lists every manual CSV import with:
- Source label and module
- Row count, candidate count, duplicate count, error count
- Status and timestamp

Click any row to expand the import detail view.

**Review Import Detail**

The expanded detail view shows:
- All candidates from that import with quality score, completeness score, duplicate flag, approval status, and conversion status.
- A row errors panel listing any invalid email addresses, malformed fields, or within-import duplicate companies collected during parsing.

**Apply Advanced Filters**

Use the Advanced Filters panel above the candidate table to narrow results by:
- Source label (exact match)
- Module
- Quality score range (min/max)
- Converted / not converted

Click **Apply Filters** to refresh the table.

**Bulk-Approve Candidates**

1. Select one or more candidate rows using the checkboxes.
2. The bulk action bar appears at the top of the table.
3. Choose **Approve Selected** and confirm.
4. Only approved candidates may later be converted.

**Bulk-Reject Candidates**

Select candidates and choose **Reject Selected** from the bulk action bar.

**Bulk-Convert Candidates**

Select already-approved candidates and choose **Convert Selected to Contact** from the bulk action bar. A confirmation dialog appears before any conversion is executed. Candidates that are not yet approved will fail conversion and be reported in the result summary.

**Review Row Errors**

Open the Import History detail view for any import and scroll to the Row Errors panel. Each error shows the row number, field name, error description, and the raw value that failed validation. Use this to identify rows that need correction in the source CSV before re-importing.

## 2. Run The Lead Pipeline

```bash
make pipeline
```

Or pass custom inputs directly:

```bash
./scripts/run_daily_pipeline.sh --business-type "roofing contractor" --location "Austin, TX" --count 5
```

The pipeline imports structured contractor listings, stores leads in MongoDB, enriches them, writes lead and company notes, and creates review queue notes.

## 3. Review Leads

Open the vault in Obsidian and review:

- `vault/review_queue/`
- `vault/leads/`
- `vault/companies/`
- `vault/reports/contractor_pipeline_report.md`

For each review queue note, decide:

- `pursue`
- `skip`
- `research_more`

## 4. Record Review Decision

```bash
python scripts/review_lead.py <lead-slug-or-id> pursue --note "Good fit for contractor follow-up offer."
```

Other decisions:

```bash
python scripts/review_lead.py <lead-slug-or-id> skip --note "Poor fit."
python scripts/review_lead.py <lead-slug-or-id> research_more --note "Verify service area."
```

If the decision is `pursue`, SignalForge creates an outreach-ready note in `vault/outreach/`.

## 5. Update Outreach Status

Use this only for human-driven outreach progress. SignalForge does not send emails.

```bash
python scripts/update_outreach_status.py <lead-slug-or-id> sent --note "Message sent manually."
```

Supported statuses:

- `drafted`
- `sent`
- `replied`
- `follow_up_needed`
- `booked_call`
- `closed_won`
- `closed_lost`

Special behavior:

- `follow_up_needed` creates a note in `vault/followups/`.
- `booked_call` appends meeting prep to the outreach note.

## 6. Generate Report

```bash
make report
```

The report is written to:

```text
vault/reports/contractor_pipeline_report.md
```

Review the report from `vault/00_Dashboard.md`.

## 7. Import Provided Contacts

Use this when a client provides an email, call, or contact list. The import stores contacts in MongoDB and writes a summary note to `vault/contacts/`. It does not send messages or enrich contacts externally.

```bash
python scripts/import_contacts.py data/imports/sample_contacts.csv --module insurance_growth --source "client_provided_list"
```

Expected CSV fields:

```text
name,email,phone,company,role,city,state,notes
```

Imported contacts become available to simulation agents through the `contacts` collection.

## 8. Score And Segment Contacts

After importing contacts, score the module so agents can prioritize who to review first.

```bash
python scripts/score_contacts.py --module insurance_growth
```

The scorer updates MongoDB with `contact_score`, `segment`, `priority_reason`, `recommended_action`, and `scored_at`. It writes a segmentation report to `vault/contacts/`.

Segments:

- `high_priority`
- `nurture`
- `research_more`
- `low_priority`

Scoring is local and deterministic. SignalForge does not send messages or enrich contacts externally.

## 9. Draft Messages For Review

Generate editable drafts after contacts are scored or leads are marked `pursue`.

```bash
python scripts/draft_messages.py --module insurance_growth --limit 5
```

Drafts are written to `vault/messages/` and stored in MongoDB as `message_drafts`. Every draft starts as:

- `review_status=needs_review`
- `send_status=not_sent`

Review and edit drafts in Obsidian. SignalForge does not send email, SMS, DMs, social posts, or call external APIs.

## 10. Review Message Drafts

Record the human review decision after inspecting the draft in `vault/messages/`.

```bash
python scripts/review_message.py <draft-slug-or-id> approve --note "Approved for manual send."
python scripts/review_message.py <draft-slug-or-id> revise --note "Make the tone warmer."
python scripts/review_message.py <draft-slug-or-id> reject --note "Not a fit."
```

Decision behavior:

- `approve` sets `review_status=approved` and keeps `send_status=not_sent`.
- `revise` sets `review_status=needs_revision`.
- `reject` sets `review_status=rejected`.

Every decision appends a review log to the matching message note. SignalForge still does not send anything.

The Web Dashboard v1 can also record message review decisions from the Messages page. Dashboard actions update MongoDB and append vault logs; they still do not send anything.

## 11. Log Manual Sends

Use this only after a human sends an approved draft outside SignalForge. The script records the event; it does not send anything.

```bash
python scripts/log_manual_send.py <draft-slug-or-id> --channel email --note "Sent manually from Gmail."
python scripts/log_manual_send.py <draft-slug-or-id> --channel phone --note "Called and left voicemail."
```

Manual send logging requires `review_status=approved`. It sets `send_status=sent`, writes `sent_at`, appends a send log to the message note, and updates linked records:

- Lead draft: `outreach_status=sent`
- Contact draft: `contact_status=contacted`

## 12. Log Responses

Use this after a manually sent message produces an outcome. The draft must already have `send_status=sent`.

```bash
python scripts/log_response.py <draft-slug-or-id> --outcome interested --note "Asked for pricing details."
python scripts/log_response.py <draft-slug-or-id> --outcome call_booked --note "Discovery call booked manually."
```

Supported outcomes:

- `no_response`
- `interested`
- `not_interested`
- `call_booked`
- `requested_info`
- `wrong_contact`
- `bounced`
- `do_not_contact`

Linked record updates:

- Contact `interested`: `contact_status=interested`
- Contact `not_interested`: `contact_status=not_interested`
- Contact `call_booked`: `contact_status=call_booked`
- Contact `do_not_contact`: `contact_status=do_not_contact`
- Contact `bounced`: `contact_status=invalid`
- Lead `interested`: `outreach_status=replied`
- Lead `call_booked`: `outreach_status=booked_call`
- Lead `not_interested`: `outreach_status=closed_lost`

`call_booked` appends meeting prep to the message note. SignalForge does not create calendar events.

## 13. Generate Meeting Prep

Create a standalone prep note before a booked call. The input can be a contact, lead, or message draft id/slug.

```bash
python scripts/generate_meeting_prep.py <contact-lead-or-draft-slug>
```

The prep note is written to `vault/meetings/` and includes summary context, prioritization reason, original message, response history, likely pain points, recommended offer, discovery questions, call objective, and follow-up checklist.

SignalForge does not create calendar events or send messages.

## 14. Log Deal Outcomes

Track what happened after a meeting. The input can be a contact, lead, message draft, or meeting prep id/slug/path.

```bash
python scripts/log_deal_outcome.py <contact-lead-draft-or-meeting-slug> --outcome closed_won --deal-value 2500 --note "Client approved starter engagement."
python scripts/log_deal_outcome.py <contact-lead-draft-or-meeting-slug> --outcome closed_lost --note "Budget not available this quarter."
```

Supported outcomes:

- `proposal_sent`
- `negotiation`
- `closed_won`
- `closed_lost`
- `nurture`
- `no_show`
- `not_fit`

Deal outcomes update linked contacts, leads, message drafts, and the `deals` collection. Deal notes are written to `vault/deals/`.

`closed_won` notes include source, module, deal value, path to conversion, and next onboarding action. `closed_lost` notes include loss reason and future nurture recommendation.

SignalForge does not send messages, create invoices, or call CRM APIs.

## 15. Generate Revenue Performance Report

Use this after contact, message, meeting, or deal activity to review performance across modules.

```bash
make revenue-report
```

The report is written to:

```text
vault/reports/revenue_performance_report.md
```

Review it from `vault/00_Dashboard.md`. It summarizes contacts, leads, message statuses, response statuses, meeting indicators, deal outcomes, closed-won value, conversion paths, top modules, nurture contacts, and open opportunities from MongoDB only.

## 16. Run System Check

```bash
make check
```

The check verifies MongoDB, vault folders, required scripts, `docker-compose.yml`, contractor pipeline report generation, and revenue performance report generation.

## 17. Run Optional Agent Simulations

Use agents for planning only after MongoDB has current records. Agents write run logs to `vault/logs/agents/`, reference available message drafts, and never send outbound messages or publish content.

```bash
python scripts/run_agent.py outreach --module contractor_growth --dry-run
python scripts/run_agent.py content --module artist_growth --dry-run
python scripts/run_agent.py fan_engagement --module artist_growth --dry-run
python scripts/run_agent.py followup --module insurance_growth --dry-run
```

Review the generated agent logs in Obsidian before taking any manual action.

The dashboard Agent Console can run the same agents in dry-run mode through the local API. Each run creates MongoDB records in `agent_runs`, `agent_steps`, `agent_artifacts`, and `approval_requests`, then displays the selected run as a step-by-step timeline with inputs, outputs, warnings, related records, and approvals needed.

Use the Agent Console to answer:

- What records did the agent read?
- What did it decide at each step?
- What messages or records are related?
- What human approvals are still needed?
- Did the run complete, fail, or produce warnings?

Agent Console actions remain simulation-only. They do not send email, SMS, DMs, social posts, or calendar events.

If GPT is enabled, supported agents may add GPT steps, artifacts, drafts, and approval requests to the same run timeline. Low-confidence GPT output creates an approval request instead of being treated as ready. All GPT-generated drafts remain `send_status=not_sent` until a human sends outside SignalForge and logs that manual action.

### GPT Diagnostics

Use the dashboard GPT Diagnostics page or the CLI to verify GPT runtime configuration without exposing secrets:

```bash
docker compose run --rm api python scripts/gpt_diagnostics.py
```

Diagnostics report whether GPT is enabled, the configured model, whether an API key is present, whether the local GPT client module is available, recent GPT agent steps, recent GPT-related system approval errors, the last recorded GPT success, and the last recorded GPT error. The API endpoint is `GET /diagnostics/gpt`.

The diagnostics view never returns `OPENAI_API_KEY`, does not expose raw prompts, does not send messages, and does not change agent behavior. To run the optional live connectivity check, use:

```bash
docker compose run --rm api python scripts/gpt_diagnostics.py --live-test
```

The live test sends only `Return the word OK.` to OpenAI and stores a sanitized `gpt_diagnostic_live_test` step. Do not use `--live-test` unless you intentionally want to make that single OpenAI request.

### Approval Queue Classification

Approval requests include classification fields so the dashboard can separate real operator work from diagnostics:

- `request_origin`: `operator`, `agent`, `gpt`, `test`, or `system`
- `is_test`: marks synthetic validation records
- `severity`: `info`, `needs_review`, `warning`, or `error`
- `user_facing_summary`: short plain-English operator summary
- `technical_reason`: detailed diagnostic context

The Approval Queue defaults to actionable human work and hides synthetic test records and system/GPT failures from the main list. Use the queue filters to inspect `All`, `GPT`, `System Issues`, or `Test / Synthetic` records when troubleshooting.

Synthetic approvals exist because GPT runtime tests intentionally create review-only safety records to prove that low-confidence or mocked GPT output does not send anything. These are useful for verification, but they are not real operator tasks.

Clean up synthetic approval requests with:

```bash
python scripts/cleanup_test_approvals.py --dry-run
python scripts/cleanup_test_approvals.py --archive
```

`--dry-run` only lists matching records. `--archive` copies matching records to `approval_requests_archive` before deleting them from `approval_requests`. The script only matches `is_test=true` or `request_origin=test`; it does not delete real approvals by default.

## 18. Queue Agent Tasks

Agents are now run from the dashboard via Agent Tasks. Use the dashboard Agent Tasks page to create and run agent work from the browser instead of only using CLI dry-runs. Each task is stored in the `agent_tasks` collection with `agent_name`, `module`, `task_type`, `status`, `priority`, `input_config`, timestamps, `linked_run_id`, and `result_summary`.

Supported agents:

- `outreach`
- `followup`
- `content`
- `fan_engagement`

Task types:

- `run_outreach`
- `run_followup`
- `generate_content`
- `engage_fans`

Priorities:

- `low`
- `normal`
- `high`

Task statuses:

- `queued`
- `running`
- `waiting_for_approval`
- `completed`
- `failed`
- `cancelled`

Run only starts the current dry-run/GPT-safe agent behavior. Cancel only changes internal queue state before the task is completed. Agent Tasks do not send email, SMS, DMs, comments, or social posts. They do not scrape platforms, schedule posts, create calendar events, issue invoices, or call external CRM/platform APIs.

When a task links to an Agent Console run, use that run to inspect steps, artifacts, related records, warnings, and approvals. If the task is `waiting_for_approval`, use the Approval Queue to resolve the internal review items.

## 19. Review The Approval Queue

Use the dashboard Approval Queue to review GPT-created approval requests and agent review items from a single view. The queue shows request type, agent, module, confidence, reasoning summary, linked contact/lead/message, created time, decision buttons, and operator notes.

Supported decisions:

- `approve`: marks the approval request approved.
- `reject`: marks the request rejected.
- `needs_revision`: marks the request `needs_revision` and stores the operator note.
- `convert_to_draft`: creates a review-only `message_draft` or `approval_queue_draft` artifact when the request has enough local context.

Approval Queue decisions are internal workflow state only. They do not send email, SMS, DMs, comments, or social posts. They do not scrape platforms, schedule posts, create calendar events, issue invoices, or call external CRM/platform APIs.

## 20. Use Dashboard Detail Timelines

The dashboard Messages page supports full message review from the browser:

- message body
- recipient and linked contact/lead/deal
- review/send/response timeline
- response history
- approve/revise/reject actions

The Pipeline / CRM detail drawer shows linked lifecycle activity for contacts and leads, including import, scoring, drafting, approval, manual send logging, response logging, booked-call signals, and deal outcomes.

## 21. Stop The Stack

```bash
make down
```

## Operating Rules

- Keep `.env` local.
- Review outreach before sending anything manually.
- Do not treat generated copy as approved without human review.
- Treat every GPT output as a draft, recommendation, or approval request only.
- Use notes and status updates to keep MongoDB and the vault aligned.


## 22. Social Creative Engine v2

The Creative Studio now includes a full social content pipeline. All steps are review-only. Nothing is published.

### Client Profiles
Create one profile per client to define brand permissions:
- `likeness_permissions`, `voice_permissions`, `avatar_permissions` — all default `false`
- `disallowed_topics` — topics the agent must avoid
- `allowed_content_types` — e.g. `post`, `caption`, `reel_script`
- `compliance_notes` — freeform compliance reminders

### Source Channels
Add channels (YouTube, Instagram, etc.) per client. Set `approved_for_ingestion` and `approved_for_reuse` explicitly. Unapproved channels are visible but blocked from processing.

### Source Content
Log discovered videos and posts. Each item is scored at ingestion with `discovery_score` and `discovery_reason`. Items start at `needs_review` — approve them before transcripts are extracted.

### Content Transcripts & Snippets
Once source content is approved, add transcripts and let the snippet scorer extract the best segments. Each snippet shows:
- `score` and `score_reason`
- `theme`, `hook_angle`, `platform_fit`
- starts at `needs_review` — approve or reject before asset generation

### Creative Assets
Assets (images, reels, captions) are linked to approved snippets. Review each asset in the Assets tab or the Approval Queue.

### ComfyUI (optional)
To enable local generative image/video support:
```bash
# .env
COMFYUI_ENABLED=true
COMFYUI_BASE_URL=http://host.docker.internal:8188
COMFYUI_WORKFLOW_PATH=/path/to/workflow.json
```
If disabled (default) or unavailable, `creative_tool_runs` record the skipped/failed state safely. No asset is ever published.

### Operating Rules (v2)
- Never approve a snippet from a channel that is `approved_for_reuse: false`
- Never set `likeness_permissions: true` without written client authorization
- Every creative asset requires explicit operator review before external use
- `simulation_only: true` and `outbound_actions_taken: 0` on all records — always

---

## 23. Social Creative Engine v3 — Audio, Transcripts, Snippets

### Overview
v3 adds an ingest pipeline: extract audio metadata from source content, generate synthetic transcripts, and score transcript segments into snippet candidates.

### Ingest Pipeline Flow
1. Add source content (URL + title) in the Source Content tab
2. Navigate to **Ingest Pipeline** tab in Creative Studio
3. Click **Run Transcript** on any content item — generates stub transcript segments
4. Click **Generate Snippets** — scores segments, creates snippet candidates
5. Review candidates in the Snippets tab; approve/reject each one

### Env Vars
| Variable | Default | Description |
|---|---|---|
| `FFMPEG_ENABLED` | `false` | Enable real FFmpeg audio extraction |
| `FFMPEG_OUTPUT_DIR` | `/tmp/signalforge_audio` | Output directory for extracted audio |
| `TRANSCRIPT_PROVIDER` | `stub` | Transcript provider (`stub` only in v3) |

### Safety (v3)
- All audio extraction runs record `simulation_only: true`, `outbound_actions_taken: 0`
- FFmpeg disabled by default — set `FFMPEG_ENABLED=true` only for local file processing
- No audio sent externally; no content posted or scheduled

---

## 24. Social Creative Engine v4 — Media Intake, Approval Gates, Real FFmpeg

### Overview
v4 adds formal approval gates before each pipeline stage and real FFmpeg support for local media files.

### Approval Chain
```
Source Content (status=approved)
  → Media Intake Registration (POST /media-intake-records)
    → Audio Extraction (POST /audio-extraction-runs/v4)
      → Transcript Run (POST /transcript-runs/v4)
        → Snippet Generation (POST /source-content/{id}/generate-snippets/v4)
```

### Source Content Approval
Before any extraction, the source content item must be approved:
```bash
curl -X PATCH http://localhost:8000/source-content/{id}/status \
  -H "Content-Type: application/json" \
  -d '{"status": "approved"}'
```
Status values: `needs_review` (default) | `approved` | `rejected`

### Media Intake
Register a local file or URL metadata (no download):
```bash
# Local file
curl -X POST http://localhost:8000/media-intake-records \
  -H "Content-Type: application/json" \
  -d '{"source_content_id": "{id}", "media_path": "/path/to/video.mp4", "workspace_slug": "default"}'

# URL metadata only (no download)
curl -X POST http://localhost:8000/media-intake-records \
  -H "Content-Type: application/json" \
  -d '{"source_content_id": "{id}", "source_url": "https://youtube.com/...", "workspace_slug": "default"}'
```
Allowed extensions: `.mp4 .mov .mkv .avi .webm .mp3 .wav .m4a .aac .flac`

### Audio Extraction (v4)
Uses registered intake record's `media_path` when FFmpeg is enabled:
```bash
curl -X POST http://localhost:8000/audio-extraction-runs/v4 \
  -H "Content-Type: application/json" \
  -d '{"source_content_id": "{id}", "workspace_slug": "default"}'
```

### Transcript Runs (v4)
Stub provider works without prior audio extraction (manual text_hint flow):
```bash
curl -X POST http://localhost:8000/transcript-runs/v4 \
  -H "Content-Type: application/json" \
  -d '{"source_content_id": "{id}", "text_hint": "Paste transcript text here.", "workspace_slug": "default"}'
```

### Env Vars (v4)
| Variable | Default | Description |
|---|---|---|
| `FFMPEG_ENABLED` | `false` | Enable real FFmpeg extraction |
| `FFMPEG_OUTPUT_DIR` | `/tmp/signalforge_audio` | Audio output directory |
| `MEDIA_DOWNLOAD_ENABLED` | `false` | (Reserved) URL download — not yet enabled |
| `TRANSCRIPT_PROVIDER` | `stub` | `stub` or `whisper` (whisper not yet live) |
| `TRANSCRIPT_LIVE_ENABLED` | `false` | Second gate for live transcript providers |

### Operating Rules (v4)
- Never approve source content without verifying the creator owns/has licensed the material
- `approved_for_download: false` on all intake records by default — URL download is never enabled automatically
- `WhisperTranscriptProvider` is a placeholder — set `TRANSCRIPT_PROVIDER=stub` until fully implemented
- All records carry `simulation_only: true`, `outbound_actions_taken: 0`
- No audio is sent to any external API unless `TRANSCRIPT_LIVE_ENABLED=true` AND `TRANSCRIPT_PROVIDER=whisper` (both required)

---

## Section 25: Social Creative Engine v4.5 — Prompt Generator Library

### Overview

v4.5 adds a structured visual prompt generation layer on top of the v4 approval pipeline. Approved content snippets feed into the Prompt Generator to produce structured visual prompts for faceless short-form creative content. All prompts are operator-reviewed before any asset generation begins.

**Architecture**: `prompt_generator.py` module → `POST /prompt-generations` endpoint → `prompt_generations` MongoDB collection → Prompt Library tab in Creative Studio.

### Key Rules

1. **Approved snippets only** — only snippets with `status='approved'` may generate a prompt. Attempting to generate from a `needs_review` or `rejected` snippet returns 422.
2. **Likeness gate** — `use_likeness=True` requires `avatar_permissions=True` or `likeness_permissions=True` on the client profile. Default: both `false`.
3. **Default faceless** — every generated prompt includes "no faces, no identifiable people" in the positive prompt and blocks `realistic human face, identifiable person, likeness` in the negative prompt.
4. **No voice cloning** — no voice clone instructions are ever generated by the module.
5. **No auto-execution** — SignalForge never calls ComfyUI, Seedance, Higgsfield, or Runway automatically. The operator runs asset generation externally after approval.
6. **Review gate** — all prompts start as `draft`. They must be approved before operator use.
7. **Safety invariants** — every record carries `simulation_only: true`, `outbound_actions_taken: 0`.

### Supported Prompt Types

| Type | Description |
|---|---|
| `faceless_motivational` | Abstract energy, bold typography, motivational theme |
| `cinematic_broll` | Professional B-roll, no faces, shallow depth of field |
| `abstract_motion` | Pure abstract motion design, no people |
| `business_explainer` | Flat design infographic animation |
| `quote_card_motion` | Animated quote card with text reveal |
| `podcast_clip_visual` | Waveform animation with branded background |
| `educational_breakdown` | Numbered steps, educational infographic style |
| `luxury_brand_story` | High-end product/lifestyle detail shots |
| `product_service_ad` | Direct commercial with product hero shot |

### Supported Engine Targets

| Engine | Status | Notes |
|---|---|---|
| `comfyui` | Local (operator must run separately) | Default. Communicates only with local ComfyUI instance. |
| `seedance` | Not yet integrated | Export prompt and use manually. |
| `higgsfield` | Not yet integrated | Export prompt and use manually. |
| `runway` | Not yet integrated | Export prompt and use manually. |
| `manual` | Always available | Operator uses prompt with any external tool. |

### Operator Workflow

```
1. Approve a snippet via the Snippets tab or Approval Queue.
2. Open the Prompt Library tab in Creative Studio.
3. Click an approved snippet button to generate a prompt (defaults to faceless_motivational / comfyui).
4. Review the generated prompt: check positive_prompt, negative_prompt, scene_beats, caption_overlay.
5. Approve, reject, or request revision.
6. For approved prompts: export/copy the prompt and run ComfyUI (or chosen engine) externally.
7. Import the result back into SignalForge as a creative asset (manual workflow for now).
```

### API Quick Reference

```bash
# Generate a prompt from an approved snippet
curl -X POST http://localhost:8000/prompt-generations \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_slug": "default",
    "snippet_id": "<approved_snippet_id>",
    "prompt_type": "faceless_motivational",
    "generation_engine_target": "comfyui",
    "use_likeness": false
  }'

# List all prompt generations
curl "http://localhost:8000/prompt-generations?workspace_slug=default"

# Review a prompt generation
curl -X POST "http://localhost:8000/prompt-generations/<gen_id>/review" \
  -H "Content-Type: application/json" \
  -d '{"decision": "approve", "note": "Ready for ComfyUI run."}'
```

### Operating Rules (v4.5)

- Never enable `use_likeness=True` without verifying the client has signed appropriate permissions
- Prompt approval does not automatically trigger any asset generation — operator action required
- All records carry `simulation_only: true`, `outbound_actions_taken: 0`
- The `prompt_generator.py` module makes zero external API calls
- Default engine target is `comfyui` — local only, no remote API

---

## Section 26: Social Creative Engine v5 — Asset Rendering

### Overview

v5 adds a rendering pipeline on top of the v4.5 prompt approval layer. Approved prompt generations can be submitted to a render job that (optionally) calls ComfyUI for image generation and FFmpeg for video assembly. All rendering is gated: both `COMFYUI_ENABLED` and `FFMPEG_ENABLED` default to `false`. Every rendered asset is created as `status: needs_review` and requires operator approval before any downstream use.

### Prerequisites

1. Snippet must be `status: approved` (v2 snippet review workflow)
2. Prompt generation must be `status: approved` (v4.5 prompt review workflow)
3. No content is rendered, generated, or assembled without both approvals

### Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `COMFYUI_ENABLED` | `false` | Enable real ComfyUI image generation |
| `COMFYUI_BASE_URL` | `http://host.docker.internal:8188` | ComfyUI API address (local only) |
| `COMFYUI_WORKFLOW_PATH` | `` | Path to ComfyUI workflow JSON |
| `FFMPEG_ENABLED` | `false` | Enable real FFmpeg video assembly |
| `FFMPEG_OUTPUT_DIR` | `/tmp/signalforge_renders` | Output directory for assembled mp4 files |

### API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/assets/render` | Trigger asset render from approved snippet + prompt generation |
| GET | `/assets` | List render records with workspace/status/engine filters |
| POST | `/assets/{id}/review` | Operator review: approve / reject / revise |

### Render Workflow

```
Approved snippet + Approved prompt_generation
    ↓
POST /assets/render
    ↓ (status: queued)
ComfyUI step (if COMFYUI_ENABLED=true → image; else mock path)
    ↓ (status: generated)
FFmpeg step (if FFMPEG_ENABLED=true → mp4; else mock path)
    ↓ (status: needs_review)
Operator review via POST /assets/{id}/review
    ↓
status: approved | rejected | needs_revision
```

### Quick Reference: cURL Commands

```bash
# Trigger a render (both gates disabled — safe mock mode)
curl -X POST "http://localhost:8000/assets/render" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_slug": "default",
    "snippet_id": "<approved_snippet_id>",
    "prompt_generation_id": "<approved_prompt_gen_id>",
    "asset_type": "video",
    "generation_engine": "comfyui",
    "add_captions": false
  }'

# List renders for workspace
curl "http://localhost:8000/assets?workspace_slug=default"

# List renders awaiting review
curl "http://localhost:8000/assets?workspace_slug=default&status=needs_review"

# Approve a render
curl -X POST "http://localhost:8000/assets/<render_id>/review" \
  -H "Content-Type: application/json" \
  -d '{"decision": "approve", "note": "Approved for use."}'

# Reject a render
curl -X POST "http://localhost:8000/assets/<render_id>/review" \
  -H "Content-Type: application/json" \
  -d '{"decision": "reject", "note": "Does not meet brand guidelines."}'
```

### Operating Rules (v5)

- Never enable `COMFYUI_ENABLED=true` or `FFMPEG_ENABLED=true` in production without confirming local service availability
- Both the snippet and the prompt_generation must be operator-approved before any render can be triggered
- All render records carry `simulation_only: true`, `outbound_actions_taken: 0`
- Rendered assets go to `needs_review` — they are never auto-approved
- `video_assembler.py` makes zero external API calls; FFmpeg writes only to the local filesystem
- The "Rendered Assets" tab in Creative Studio shows all renders with inline review controls

---

## Section 27: Social Creative Engine v5 — Runtime Infrastructure

### Overview

v5 Runtime Infrastructure adds an async render pipeline backed by Redis and a dedicated worker container. The API enqueues render jobs when Redis is available; the worker processes them independently. When Redis is unavailable, the API falls back to synchronous inline processing (preserving existing behaviour).

### New Services

| Service | Container | Start condition |
|---|---|---|
| `redis` | `signalforge-redis` | Default (always started) |
| `worker` | `signalforge-worker` | Default (always started) |
| `comfyui` | `signalforge-comfyui` | Profile `comfyui` only |

### Status Lifecycle

```
queued     API created render record, job enqueued to Redis
   ↓
running    Worker has dequeued job and started processing
   ↓
generated  ComfyUI step complete (or mock), before video assembly
   ↓
needs_review  Assembly complete — awaiting operator review
   or
failed     Unhandled exception in worker — check logs
```

### Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://redis:6379` | Redis connection URL |
| `COMFYUI_ENABLED` | `false` | Enable real ComfyUI calls from worker |
| `FFMPEG_ENABLED` | `false` | Enable real FFmpeg assembly in worker |
| `FFMPEG_OUTPUT_DIR` | `/tmp/signalforge_renders` | Output path for rendered mp4 files |

### Starting with ComfyUI profile

```bash
# Start full stack including ComfyUI stub
docker compose --profile comfyui up -d

# Start full stack (default — no ComfyUI)
docker compose up -d
```

### Worker logs

```bash
docker compose logs -f worker
```

### Check queue depth

```bash
docker compose exec redis redis-cli llen signalforge:render_jobs
```

### Inspect failed jobs

```bash
docker compose exec redis redis-cli lrange signalforge:render_jobs_failed 0 -1
```

### Quick Reference: render status query

```bash
# List renders in running state
curl "http://localhost:8000/assets?workspace_slug=default&status=running"

# List failed renders
curl "http://localhost:8000/assets?workspace_slug=default&status=failed"
```

### Operating Rules (v5 Runtime)

- The worker is a long-running process; use `docker compose restart worker` to pick up code changes after `docker compose build api`
- `COMFYUI_ENABLED=true` requires the ComfyUI service to be running AND reachable at `COMFYUI_BASE_URL`
- `FFMPEG_ENABLED=true` requires FFmpeg binary to be present (pre-installed in the Docker image)
- If Redis is down and a render request comes in, the API falls back to synchronous execution with `queued: false` in the response
- The dead-letter queue (`signalforge:render_jobs_failed`) is for operator inspection only — no automatic retry
- All records produced by the worker carry `simulation_only: true` and `outbound_actions_taken: 0`

---

## Section 28: Social Creative Engine v5.5 — Real Local FFmpeg Render

### Overview

v5.5 activates the real local FFmpeg render path. `FFMPEG_ENABLED` defaults to `true`. The worker produces actual `.mp4` files written to `/tmp/signalforge_renders` (shared `render-output` Docker volume). If no audio is available, a 440 Hz sine-wave test tone is auto-generated locally using FFmpeg lavfi — no external downloads occur.

### Environment Variables Changed in v5.5

| Variable | v5 default | v5.5 default | Notes |
|---|---|---|---|
| `FFMPEG_ENABLED` | `false` | `true` | Real FFmpeg subprocess now runs by default |

### Verify FFmpeg is installed in containers

```bash
# API container
docker compose exec api ffmpeg -version

# Worker container
docker compose exec worker ffmpeg -version
```

### Check FFmpeg health endpoint

```bash
curl http://localhost:8000/health/ffmpeg
# Expected response:
# {"ffmpeg_available": true, "ffmpeg_path": "/usr/bin/ffmpeg", "ffmpeg_version": "ffmpeg version ...", "ffmpeg_enabled": true}
```

### Confirm renders are creating real MP4 files

```bash
# After triggering a render via the dashboard or API:
docker compose exec api ls -lh /tmp/signalforge_renders/

# Example expected output:
# -rw-r--r-- 1 root root 2.3M Jun 1 12:00 6843a1b2f00c4d001234abcd.mp4
# -rw-r--r-- 1 root root  48K Jun 1 12:00 placeholder_6843....png
# -rw-r--r-- 1 root root 176K Jun 1 12:00 testtone_6843....wav
```

### Worker startup log (v5.5)

When the worker container starts, look for FFmpeg diagnostics in the startup log:

```bash
docker compose logs worker | grep -i ffmpeg
# Expected output includes:
# FFmpeg diagnostics: available=True path=/usr/bin/ffmpeg version=ffmpeg version 6.1... enabled=True
```

### Trigger a full render and verify

```bash
# 1. Queue a render from the dashboard (Creative Studio → Rendered Assets tab)
# OR via API:
curl -X POST http://localhost:8000/assets/render \
  -H "Content-Type: application/json" \
  -d '{"snippet_id": "<approved-snippet-id>", "prompt_generation_id": "<approved-pg-id>", "workspace_slug": "default"}'

# 2. Watch worker log
docker compose logs -f worker | grep render_id

# 3. Verify the MP4 was created
docker compose exec api ls /tmp/signalforge_renders/

# 4. Query the render record
curl "http://localhost:8000/assets?workspace_slug=default&status=needs_review"
# Look for: assembly_status=success, assembly_engine=ffmpeg, file_path set
```

### Disable FFmpeg (revert to mock)

```bash
# Stop containers, set env var, restart
FFMPEG_ENABLED=false docker compose up -d
# OR add to a .env file:
echo "FFMPEG_ENABLED=false" >> .env
docker compose up -d
```

### Operating Rules (v5.5)

- `FFMPEG_ENABLED=true` is now the default — rebuild both `api` and `worker` images if changing Python files: `docker compose build --no-cache api worker`
- Test tone generation uses FFmpeg lavfi — it never downloads external audio
- Placeholder image uses FFmpeg lavfi color source — no network calls
- All renders continue to carry `simulation_only: true` and `outbound_actions_taken: 0`
- `assembly_status` and `assembly_engine` are stored on every render record and visible in the dashboard
- Dashboard shows green "Real Render" badge when `assembly_status=success`, violet "FFmpeg" badge when `assembly_engine=ffmpeg`
- `COMFYUI_ENABLED` remains `false` by default — ComfyUI is not required for v5.5 renders
