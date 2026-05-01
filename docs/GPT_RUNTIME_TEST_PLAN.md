# GPT Runtime Test Campaign v1

## Goal

Safely test GPT-enabled agents end to end without outbound automation.

The campaign verifies that GPT runtime settings are visible, outreach dry-runs remain human-reviewed, GPT metadata is recorded, unsafe or low-confidence GPT output creates approval requests, and no message is sent.

## Run Command

```bash
make gpt-agent-test
```

The Makefile target runs inside the Docker API service:

```bash
docker compose run --rm api python scripts/gpt_runtime_test_campaign.py
```

## Environment Gate

GPT is disabled by default. For a live GPT-enabled outreach dry-run, configure the local `.env` file:

```text
GPT_AGENT_ENABLED=true
OPENAI_API_KEY=<your-api-key>
OPENAI_MODEL=gpt-4o-mini
```

`OPENAI_MODEL` is optional. If `OPENAI_API_KEY` is missing, the campaign skips the live GPT call and still runs the local safety-path validation with a mocked low-confidence GPT result.

## What The Campaign Verifies

- `GET /settings/gpt-runtime` returns `enabled`, `model`, `has_api_key`, and `safety_mode`.
- A synthetic local contact exists for the test module.
- `outreach_agent` dry-run uses GPT only when `OPENAI_API_KEY` is present.
- No `message_drafts` record changes to `send_status=sent`.
- Any GPT-created message draft has `review_status=needs_review` and `send_status=not_sent`.
- GPT `agent_steps` include `confidence` and `reasoning_summary`.
- Low-confidence or unsafe GPT output creates an open `gpt_message_generation_review` approval request.

## Safety Boundaries

This campaign does not send messages, publish posts, post comments, scrape platforms, schedule posts, create calendar events, issue invoices, or call external CRM/platform APIs.

The only allowed external call is the optional OpenAI request made by `outreach_agent` when `OPENAI_API_KEY` is present. That call can only create review-only local outputs.

## Expected Output

Successful output ends with:

```text
GPT runtime test campaign passed.
```

If no API key is configured, the live GPT run is skipped and the campaign should still pass the local safety checks.

## Follow-Up Review

After the campaign, inspect the Agent Console and MongoDB records if needed:

- `agent_runs`
- `agent_steps`
- `approval_requests`
- `message_drafts`

All generated work must remain review-only. Any real outreach must be performed manually outside SignalForge and logged separately.