# SignalForge API

The API service is the local FastAPI control plane for SignalForge Web Dashboard v1.

## Local URL

```text
http://localhost:8000
```

## Endpoints

- `GET /health`
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

## Safety

The API reads and updates local MongoDB records and appends review logs to the vault where applicable. It does not send email, SMS, DMs, social posts, calendar events, invoices, or CRM updates.

Agent runs are dry-run only.
