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
| Docker local stack | No | Yes | No | Yes | Yes | No | `make up`, `make dashboard`, `docker compose` start MongoDB, API, services, and web. |
| FastAPI health/status | Yes | Yes | No | No | Yes | No | `GET /health` plus `curl http://localhost:8000/health`. |
| React web dashboard | Yes | No | No | No | Yes | No | Demo Mode, Workflow, Overview, Pipeline / CRM, Messages, Approvals, Agent Tasks, Agent Console, Research / Tools, GPT Diagnostics, Deals, Reports. |
| Contractor listing import | No | Yes | No | Yes | Yes | No | `scripts/run_daily_pipeline.sh` runs `lead_scraper` against local structured data. |
| Contractor lead enrichment/scoring | No | Yes | No | No | Yes | No | `lead_enricher` adds deterministic v3 intelligence, score breakdown, notes, and review queue items. |
| External/live scraping | Partly | Yes | No | Yes | Partly | Partly | Tool Layer v1 can fetch a public HTML URL and optionally scroll public pages when Playwright is installed. It respects safety gates, avoids protected/gated pages, and remains review-only. |
| External enrichment APIs | No | No | No | No | No | Yes | No external enrichment providers are called. |
| Contact CSV import | No | Yes | No | Yes | Yes | No | `scripts/import_contacts.py` imports local CSVs into MongoDB and writes vault notes. |
| Manual source/candidate CSV import | Yes | Yes | No | Yes | Yes | No | Research / Tools Import CSV panel, `POST /tools/import-candidates`, and `scripts/import_candidates.py` import local/uploaded prospect source lists into `scraped_candidates` with `source=manual_upload`, quality scoring, enrichment, duplicate detection, approval requests, and approval-gated local conversion. |
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

## Safety Boundary

SignalForge v1 does not send messages, publish content, create calendar events, issue invoices, call CRM APIs, run GPT-powered agents by default, or use external enrichment/search APIs. The GPT runtime is implemented but gated unless `GPT_AGENT_ENABLED=true` and `OPENAI_API_KEY` are configured. Tool Layer v1 is read-only and review-first: it records sanitized `tool_runs`, `scraped_candidates`, artifacts, and approval requests; local contact/lead conversion requires prior approval. Manual source/candidate CSV imports are local only and do not create contacts, leads, messages, or outbound actions automatically. GPT diagnostics never return API keys or raw prompts; the optional live diagnostics test makes only a minimal OpenAI `OK` request when explicitly invoked. The dashboard and CLI may update local MongoDB records, create review-only GPT artifacts/drafts/approval requests, write sanitized diagnostics steps, and append local vault logs only.
