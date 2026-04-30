# Requirements

## Functional Requirements

- Collect lead and company candidates from configured sources.
- Store structured lead, company, social signal, campaign, and content records in MongoDB.
- Enrich company and contact records using AI prompts and external data providers.
- Process social media signals into concise, actionable observations.
- Generate outreach copy, campaign drafts, and content ideas.
- Write useful markdown outputs to the Obsidian vault.
- Maintain a command and execution log that humans can inspect.
- Run services locally with Docker Compose.

## Technical Requirements

- Use Python 3.11 for all services.
- Use Docker Compose for orchestration.
- Mount the Obsidian vault into every service at `/vault`.
- Use MongoDB for structured persistence.
- Use `.env` for secrets and environment configuration.
- Keep each service independently runnable.
- Keep service interfaces simple until real workflow pressure justifies more structure.
- Prefer idempotent scripts and clear logging.

## Data Requirements

Core collections should begin with:

- `leads`
- `companies`
- `contacts`
- `social_signals`
- `campaigns`
- `generated_posts`
- `pipeline_runs`
- `command_log`

Minimum useful fields for records:

- `source`
- `status`
- `created_at`
- `updated_at`
- `raw_payload`
- `notes_path`
- `confidence`

Markdown notes should include:

- YAML frontmatter when useful.
- Human-readable summary.
- Source links or source description.
- AI-generated analysis.
- Next action.
- Last reviewed date.

## Security Considerations

- Never commit `.env`.
- Treat cookies, API keys, and access tokens as secrets.
- Keep LinkedIn cookies and third-party tokens local.
- Avoid storing sensitive raw payloads in the vault unless they are safe for human-readable storage.
- Add rate limits and source-specific compliance checks before production scraping.
- Prefer least-privilege API keys.
- Review generated outreach before sending.
- Keep MongoDB bound to local Docker networking unless remote access is explicitly required.
