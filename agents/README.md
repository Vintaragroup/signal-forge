# SignalForge Agent Layer v1

The agent layer is a simulation-first planning layer for SignalForge modules.

Agents can read MongoDB, inspect module context, print planned actions, and write agent run logs into the Obsidian vault. They do not send emails, SMS, DMs, social posts, calendar invites, or any outbound communication.

GPT Agent Runtime v1 is available behind an explicit environment gate. It is disabled by default and remains human-reviewed when enabled.

Agent Tool Layer v1 Phase 1 is available under `tools/`, but it is not integrated into autonomous agent runs. Operators may run the tools manually through `scripts/run_tool.py` and review the resulting `scraped_candidates` in the dashboard Research / Tools page.

Agents read module-matched records from `leads`, `contacts`, and `message_drafts`. Imported contacts come from `scripts/import_contacts.py`; scored contacts come from `scripts/score_contacts.py`; draft notes come from `scripts/draft_messages.py`; review decisions come from `scripts/review_message.py`; manual send logs come from `scripts/log_manual_send.py`; response outcomes come from `scripts/log_response.py`; meeting prep notes come from `scripts/generate_meeting_prep.py`; deal outcomes come from `scripts/log_deal_outcome.py`. When no matching leads exist, agents can create contact-based planning actions for human review and prefer `high_priority` contacts first.

## Supported Modules

- `contractor_growth`
- `insurance_growth`
- `artist_growth`
- `media_growth`

## Agents

- `outreach_agent`: prepares B2B outreach actions.
- `content_agent`: prepares content and post ideas.
- `fan_engagement_agent`: prepares music and entertainment engagement ideas.
- `followup_agent`: identifies leads needing follow-up.

## Usage

```bash
python scripts/run_agent.py outreach --module contractor_growth --dry-run
python scripts/run_agent.py content --module artist_growth --dry-run
python scripts/run_agent.py fan_engagement --module artist_growth --dry-run
python scripts/run_agent.py followup --module insurance_growth --dry-run
```

## GPT Runtime Controls

Enable GPT only in your local `.env`:

```text
GPT_AGENT_ENABLED=true
OPENAI_API_KEY=<your-api-key>
OPENAI_MODEL=gpt-4o-mini
```

`OPENAI_MODEL` is optional; blank values use the runtime default. The dashboard reads `GET /settings/gpt-runtime` to show whether GPT is enabled, whether an API key exists, the configured model, and the safety mode.

When enabled, GPT can:

- draft outreach messages for human review;
- recommend follow-up actions;
- create content planning artifacts and markdown notes;
- create artist fan engagement planning artifacts and markdown notes;
- create approval requests when confidence is low.

GPT cannot send email, SMS, DMs, comments, social posts, publish content, scrape platforms, schedule posts, create calendar events, issue invoices, or call external CRM/platform APIs. Operators must review and approve every GPT output before taking any real-world action outside SignalForge.

Tool Layer Phase 1 is also read-only. It does not submit forms, login, post, message, bypass captcha, scrape protected/private pages, use a real search API, or create contacts/leads without an explicit operator conversion decision.

Import a provided contact list before an agent run:

```bash
python scripts/import_contacts.py data/imports/sample_contacts.csv --module insurance_growth --source "client_provided_list"
python scripts/score_contacts.py --module insurance_growth
python scripts/draft_messages.py --module insurance_growth --limit 5
python scripts/review_message.py <draft-slug-or-id> approve --note "Approved for manual send."
python scripts/log_manual_send.py <draft-slug-or-id> --channel email --note "Sent manually from Gmail."
python scripts/log_response.py <draft-slug-or-id> --outcome interested --note "Asked for pricing details."
python scripts/generate_meeting_prep.py <contact-lead-or-draft-slug>
python scripts/log_deal_outcome.py <contact-lead-draft-or-meeting-slug> --outcome closed_won --deal-value 2500 --note "Client approved starter engagement."
```

## Output

Each run writes a markdown log to:

```text
vault/logs/agents/
```

Agent logs include available message drafts with review, send, and response status so the operator can see what is ready for human review.

## Agent Console Observability

Every agent run also writes structured observability records to MongoDB:

- `agent_runs`: one record per run with agent name, module, status, timing, summaries, and related record ids.
- `agent_steps`: ordered timeline of context loading, Mongo reads, planning, approval identification, output writing, and errors.
- `agent_artifacts`: vault log references and planned-action payloads.
- `approval_requests`: review-only items that need human approval or attention.

The dashboard Agent Console reads these collections to show runs as working processes instead of only markdown summaries. This is still simulation-only. Approval requests are prompts for human review, not permission to send anything automatically.

## Safety Rules

- Simulation only.
- No outbound communication.
- No external platform API calls.
- No social posting.
- No calendar actions.
- Human approval required for any real-world action.
