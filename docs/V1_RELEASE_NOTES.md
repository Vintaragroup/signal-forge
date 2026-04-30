# SignalForge Contractor Lead Engine v1 Release Notes

This release packages the current local-first Contractor Lead Engine as a stable operator workflow. It uses structured local data, MongoDB, the Obsidian vault, and a local React/FastAPI dashboard. It does not include external scraping APIs, email sending, calendar integration, GPT runtime, invoicing, CRM integration, or outbound automation.

## Version Summary

### v1: Mock Contractor Lead Pipeline

- Added a runnable contractor lead pipeline.
- Created mock contractor leads from business type and location inputs.
- Stored leads in MongoDB.
- Wrote lead and company notes into the vault.
- Added basic scoring, outreach drafts, and run logs.

### v2: Structured Source Input

- Replaced pure mock generation with a structured local listing dataset.
- Added `source: google_search_v1`.
- Normalized listing records into the lead schema.
- Preserved Docker pipeline compatibility.

### v3: Lead Intelligence

- Added structured lead intelligence fields.
- Added `insights` with scoring explanation and score breakdown.
- Improved outreach drafts to reference business signals.
- Created review queue notes in `vault/review_queue`.

### v4: Review Actions

- Added `scripts/review_lead.py`.
- Supported `pursue`, `skip`, and `research_more`.
- Updated Mongo review status.
- Appended decision logs to lead and review notes.
- Created outreach-ready notes in `vault/outreach` for pursued leads.

### v5: Outreach Lifecycle Tracking

- Added `scripts/update_outreach_status.py`.
- Supported `drafted`, `sent`, `replied`, `follow_up_needed`, `booked_call`, `closed_won`, and `closed_lost`.
- Appended outreach lifecycle logs.
- Created follow-up notes in `vault/followups`.
- Added meeting prep sections for booked calls.

### v6: Reporting And Dashboard

- Added `scripts/generate_pipeline_report.py`.
- Generated `vault/reports/contractor_pipeline_report.md`.
- Summarized lead counts, review status, outreach status, scores, follow-ups, booked calls, win/loss counts, and latest runs.
- Linked the report from `vault/00_Dashboard.md`.

### v7: Local Web Dashboard And Agent Console

- Added a local React dashboard served through Docker Compose.
- Added FastAPI dashboard endpoints for overview, contacts, leads, messages, agents, deals, and reports.
- Added browser-based message review actions that update MongoDB and append vault logs.
- Added Agent Console observability for dry-run agents using `agent_runs`, `agent_steps`, `agent_artifacts`, and `approval_requests`.
- Kept all dashboard actions local-first and non-sending.

## Stabilization Scope

- Added operator documentation.
- Added system check script.
- Added Makefile commands.
- Kept the system CLI-based and markdown-first.
- Kept all integrations local.

## Known Boundaries

- Source data is a local structured dataset, not live scraping.
- Outreach is prepared for human review only.
- No outbound messages are sent by SignalForge.
- No calendar events are created.
- The local dashboard is available with `make dashboard`; it does not send messages or call external systems.
