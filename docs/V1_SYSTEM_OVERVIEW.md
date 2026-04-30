# SignalForge v1 System Overview

SignalForge v1 is a local-first growth operating system for finding, reviewing, contacting, and tracking prospects through a human-approved revenue workflow.

The system is intentionally CLI-based and markdown-first. MongoDB stores structured state. The Obsidian vault stores readable notes, review queues, drafts, meeting prep, deal notes, and reports.

## v1 Scope

SignalForge v1 includes:

- Contractor lead pipeline with structured local source data.
- Contact ingestion from client-provided CSV files.
- Local scoring and segmentation for contacts and leads.
- Human-reviewed message drafting.
- Manual send logging.
- Response logging.
- Meeting prep generation.
- Deal outcome tracking.
- Contractor pipeline reporting.
- Cross-module revenue and performance reporting.
- Simulation-only agents for planning.
- Local React/FastAPI dashboard for overview, CRM, message review, agent observability, deals, and reports.
- Documentation-first module strategy packs.

SignalForge v1 does not include:

- External scraping APIs.
- Email, SMS, DM, or social posting automation.
- Calendar integration.
- CRM integration.
- Invoicing.
- GPT-powered agent runtime.
- Outbound automation from the dashboard.

## Core Surfaces

```text
Operator CLI
  -> Python scripts
  -> MongoDB structured records
  -> Obsidian vault markdown notes
  -> Reports and dashboard

Docker Compose
  -> MongoDB
  -> API health service
  -> Runnable placeholder services

Modules
  -> Strategy docs
  -> Personas, signals, scoring, outreach, content, KPIs
```

## Runtime Components

| Component | Purpose |
| --- | --- |
| `docker-compose.yml` | Starts MongoDB, API, and runnable service containers. |
| `mongo` | Stores leads, contacts, message drafts, deals, and pipeline runs. |
| `services/lead_scraper` | Collects structured contractor listing inputs. |
| `services/lead_enricher` | Scores and enriches contractor leads. |
| `services/api` | Minimal health/status API. |
| `services/web` | Local React dashboard for operating the workflow visually. |
| `vault/` | Obsidian control system and human-readable output layer. |
| `scripts/` | Operator commands for the v1 workflow. |
| `modules/` | Reusable strategy packs for industries and client types. |
| `agents/` | Simulation-only planning agents. |

## MongoDB Collections

| Collection | Role |
| --- | --- |
| `leads` | Contractor and module lead records, scores, statuses, outreach state. |
| `contacts` | Imported client-provided contacts and scoring state. |
| `message_drafts` | Human-reviewed message drafts, send logs, response logs, linked targets. |
| `deals` | Deal outcomes, value, conversion paths, linked records. |
| `pipeline_runs` | Contractor lead pipeline run metadata. |

## Vault Folders

| Folder | Role |
| --- | --- |
| `vault/leads/` | Lead notes. |
| `vault/companies/` | Company notes. |
| `vault/review_queue/` | Human lead review decisions. |
| `vault/outreach/` | Outreach-ready lead notes. |
| `vault/followups/` | Follow-up task notes. |
| `vault/contacts/` | Contact import and segmentation reports. |
| `vault/messages/` | Message drafts and review/send/response logs. |
| `vault/meetings/` | Meeting prep notes. |
| `vault/deals/` | Deal outcome notes. |
| `vault/reports/` | Pipeline and revenue reports. |
| `vault/logs/` | Pipeline and agent run logs. |

## End-To-End Workflow

### 1. Lead Pipeline

The contractor lead engine runs from `scripts/run_daily_pipeline.sh`.

It accepts business type, location, and lead count, then:

1. Reads structured contractor listing data.
2. Stores normalized leads in MongoDB.
3. Enriches and scores each lead.
4. Writes lead and company notes.
5. Writes review queue notes.
6. Logs the pipeline run.

### 2. Human Lead Review

The operator reviews `vault/review_queue/` and records one of:

- `pursue`
- `skip`
- `research_more`

Pursued leads create outreach-ready notes in `vault/outreach/`.

### 3. Contact Ingestion And Scoring

Client-provided CSV lists are imported with `scripts/import_contacts.py`.

Contacts are scored with `scripts/score_contacts.py`, which assigns:

- `contact_score`
- `segment`
- `priority_reason`
- `recommended_action`

### 4. Message Drafting And Review

`scripts/draft_messages.py` creates editable local-template drafts for high-priority contacts and approved leads.

Every draft starts as:

- `review_status=needs_review`
- `send_status=not_sent`

The operator must approve, revise, or reject every draft before any manual send is logged.

### 5. Manual Send And Response Logging

SignalForge never sends messages. It only logs work performed manually outside the system.

The operator can log:

- Manual sends with `scripts/log_manual_send.py`.
- Responses with `scripts/log_response.py`.
- Meeting prep with `scripts/generate_meeting_prep.py`.

### 6. Deal Outcome Tracking

After a meeting or sales conversation, the operator logs the outcome with `scripts/log_deal_outcome.py`.

Supported outcomes:

- `proposal_sent`
- `negotiation`
- `closed_won`
- `closed_lost`
- `nurture`
- `no_show`
- `not_fit`

Deal outcomes update linked contacts, leads, message drafts, and the `deals` collection. Deal notes are written to `vault/deals/`.

### 7. Reporting

Reports are generated into `vault/reports/`.

| Report | Command |
| --- | --- |
| Contractor pipeline report | `make report` |
| Revenue performance report | `make revenue-report` |

The dashboard at `vault/00_Dashboard.md` links to both reports.

## Module Layer

Modules are documentation-first strategy packs. They define client profile, audience personas, signal sources, scoring rules, outreach templates, content strategy, campaign plan, KPIs, and operator workflow.

Current modules:

- `modules/insurance_growth`
- `modules/artist_growth`
- `modules/media_growth`
- `modules/_template`

The contractor engine remains the working automated lead pipeline. Other modules are ready for contact ingestion, scoring, message drafting, reporting, and simulation agents.

## Safety Model

SignalForge v1 is safe by design:

- No outbound message is sent automatically.
- No social post is published automatically.
- No external enrichment or scraping API is called.
- No invoice is created.
- No CRM record is created outside MongoDB.
- Every human-facing message is written as markdown and requires review.

## Primary Operator Commands

```bash
make up
make pipeline
make report
make revenue-report
make check
make down
```

See `docs/OPERATOR_PLAYBOOK.md` and `docs/terminal_commands.md` for detailed command usage.
