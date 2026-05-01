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

- Overview
- Pipeline / CRM
- Messages
- Approvals
- Agent Tasks
- Agents
- Deals
- Reports

Message review and approval queue actions in the dashboard update MongoDB and append local records only. They do not send messages, publish content, post comments, schedule work, or call external platforms. Agent actions are dry-run only.

## Approval Queue v1

The dashboard Approval Queue gives operators one place to review GPT-created approval requests and other agent review items. Operators can approve, reject, mark needs revision, or convert an approval request into a review-only draft.

Approval decisions only control internal workflow state:

- `approve` marks the request approved.
- `reject` marks the request rejected.
- `needs_revision` stores the operator note and marks the request for revision.
- `convert_to_draft` creates either a `message_draft` or an `approval_queue_draft` artifact with `review_status=needs_review` when applicable.

No approval queue decision sends messages, posts content, scrapes data, schedules posts, creates calendar events, or calls external CRM/platform APIs.

## Agent Task Queue v1

The dashboard Agent Tasks page lets operators create, queue, run, and cancel agent tasks without using CLI dry-runs directly. Tasks are stored in MongoDB in the `agent_tasks` collection and link to the resulting Agent Console run when executed.

Supported agents:

- `outreach`
- `followup`
- `content`
- `fan_engagement`

Task runs use the same dry-run/GPT-safe agent behavior as the Agent Console. A task can become `waiting_for_approval` when the linked agent run creates open approval requests. The task page links to the Agent Console run and to the Approval Queue for follow-up review.

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
