# Setup

## Prerequisites

- Docker Desktop or Docker Engine with Docker Compose.
- Python 3.11 if you want to run scripts outside Docker.
- Obsidian if you want the vault UI.

## First Run

From the project root:

```bash
cp .env.example .env
docker compose up --build
```

The stack starts MongoDB, the API, and the worker service containers. Worker services are currently placeholder jobs, so they run, print status, and exit when invoked directly.

## Environment

Edit `.env` with real secrets when integrations are added:

- `OPENAI_API_KEY`
- `LINKEDIN_COOKIE`
- `X_API_KEY`
- `APIFY_TOKEN`
- `SERPAPI_KEY`

Keep `.env` local. It is ignored by git.

## Obsidian

Open the `vault/` folder as an Obsidian vault. Start with `00_Dashboard.md`.

## Local Note Scripts

Create a company note:

```bash
python scripts/create_company_note.py --company "Example Inc" --website "https://example.com"
```

Create a lead note:

```bash
python scripts/create_lead_note.py --company "Example Inc" --contact "Jane Doe" --role "VP Marketing"
```
