# SignalForge API

The API service is the local FastAPI control plane for SignalForge Web Dashboard v1.

## Local URL

```text
http://localhost:8000
```

## Endpoints

- `GET /health`
- `GET /settings/gpt-runtime`
- `GET /diagnostics/gpt`
- `GET /stats/overview`
- `GET /contacts`
- `GET /leads`
- `GET /messages`
- `POST /messages/{id}/review`
- `GET /agents`
- `POST /agents/run`
- `GET /agent-runs`
- `GET /agent-runs/{run_id}`
- `GET /deals`
- `GET /reports`

Agent observability uses MongoDB collections `agent_runs`, `agent_steps`, `agent_artifacts`, and `approval_requests`. `GET /messages` also returns linked contact/lead/deal context and a message timeline for dashboard review.

`GET /diagnostics/gpt` returns safe GPT runtime diagnostics: enabled state, model, API key presence, API key source, client availability, last recorded GPT success/error timestamps, recent sanitized GPT agent steps, and recent GPT-related system approval errors. It never returns `OPENAI_API_KEY`, never exposes raw prompts, and does not call OpenAI.

## Safety

The API reads and updates local MongoDB records and appends review logs to the vault where applicable. It does not send email, SMS, DMs, social posts, calendar events, invoices, or CRM updates.

Agent runs are dry-run only.

Optional live GPT diagnostics are CLI-only and must be explicitly requested:

```bash
docker compose run --rm api python scripts/gpt_diagnostics.py --live-test
```

The live test sends only `Return the word OK.` and records a sanitized diagnostic step.
