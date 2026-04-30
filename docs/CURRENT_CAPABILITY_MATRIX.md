# SignalForge v1 Current Capability Matrix

SignalForge v1 is local-first and human-reviewed. This matrix separates what is browser-supported, CLI-only, simulated, manual, real/local, and not yet implemented before any GPT-powered agent runtime is added.

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
| React web dashboard | Yes | No | No | No | Yes | No | Overview, Pipeline / CRM, Messages, Agent Console, Deals, Reports. |
| Contractor listing import | No | Yes | No | Yes | Yes | No | `scripts/run_daily_pipeline.sh` runs `lead_scraper` against local structured data. |
| Contractor lead enrichment/scoring | No | Yes | No | No | Yes | No | `lead_enricher` adds deterministic v3 intelligence, score breakdown, notes, and review queue items. |
| External/live scraping | No | No | No | No | No | Yes | v1 uses local structured datasets only. |
| External enrichment APIs | No | No | No | No | No | Yes | No external enrichment providers are called. |
| Contact CSV import | No | Yes | No | Yes | Yes | No | `scripts/import_contacts.py` imports local CSVs into MongoDB and writes vault notes. |
| Contact scoring/segmentation | No | Yes | No | No | Yes | No | `scripts/score_contacts.py` applies deterministic local scoring. |
| Message draft generation | No | Yes | No | Yes | Yes | No | `scripts/draft_messages.py` writes Mongo records and editable vault notes. |
| Message review | Yes | Yes | No | Yes | Yes | No | Dashboard Messages page and `scripts/review_message.py` approve, revise, or reject. |
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
| GPT/OpenAI agent runtime | No | No | No | No | Partly | Partly | Phase 1 safe client wrapper exists behind `GPT_AGENT_ENABLED=false`; agents are not wired to use it yet. |
| Social signal processing runtime | No | Partly | Yes | Yes | Partly | Partly | Placeholder service checks vault/Mongo; real ingestion/classification is not implemented. |
| Post/content generation runtime | No | Partly | Yes | Yes | Partly | Partly | Placeholder service checks vault/Mongo; real content generation is not implemented. |
| Backup/export guidance | No | Yes | No | Yes | Yes | No | Documented in `docs/V1_BACKUP_AND_EXPORT.md`; no Makefile wrapper yet. |
| Automated tests | No | Yes | No | No | Yes | No | Basic pytest suite covers constants, scoring, review status rules, and report aggregation. |

## Safety Boundary

SignalForge v1 does not send messages, publish content, create calendar events, issue invoices, call CRM APIs, run GPT-powered agents by default, or use external enrichment/scraping APIs. The Phase 1 GPT client wrapper remains disabled unless `GPT_AGENT_ENABLED=true` and `OPENAI_API_KEY` are both configured. The dashboard and CLI may update local MongoDB records and append local vault logs only.
