# SignalForge Agent Layer v1

The agent layer is a simulation-first planning layer for SignalForge modules.

Agents can read MongoDB, inspect module context, print planned actions, and write agent run logs into the Obsidian vault. They do not send emails, SMS, DMs, social posts, calendar invites, or any outbound communication.

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
- No external API calls.
- No social posting.
- No calendar actions.
- Human approval required for any real-world action.
