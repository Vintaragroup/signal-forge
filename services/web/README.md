# SignalForge Web Dashboard v1

The web dashboard is a local-first React interface for operating SignalForge from the browser.

## Run

```bash
make dashboard
```

Open:

```text
http://localhost:5174
```

The dashboard talks to the FastAPI service at `http://localhost:8000`.

## Pages

- Overview
- Pipeline / CRM
- Messages
- Agent Console
- Deals
- Reports

## Agent Console v1

The Agent Console shows simulation-only agents as observed processes:

- run list and status badges
- selected run timeline
- inputs and final outputs
- approval requests
- vault/Mongo artifacts
- linked contacts, leads, messages, and deals

Messages and CRM records also expose richer detail timelines for draft review, manual send logging, responses, meeting prep signals, and deal outcomes.

## Safety

- No email sending.
- No SMS sending.
- No DMs.
- No social posting.
- No calendar integration.
- Agent runs are dry-run only.

MongoDB remains the source of truth. The Obsidian vault remains the audit and knowledge layer.
