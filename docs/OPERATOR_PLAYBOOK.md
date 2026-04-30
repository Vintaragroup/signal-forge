# Operator Playbook

This playbook describes the daily workflow for the current SignalForge Contractor Lead Engine.

## 1. Start The Stack

```bash
make up
```

This starts MongoDB and the API through Docker Compose.

To use the browser dashboard:

```bash
make dashboard
```

Open `http://localhost:5174`. The dashboard reads MongoDB through the local API and keeps vault behavior unchanged.

## 2. Run The Lead Pipeline

```bash
make pipeline
```

Or pass custom inputs directly:

```bash
./scripts/run_daily_pipeline.sh --business-type "roofing contractor" --location "Austin, TX" --count 5
```

The pipeline imports structured contractor listings, stores leads in MongoDB, enriches them, writes lead and company notes, and creates review queue notes.

## 3. Review Leads

Open the vault in Obsidian and review:

- `vault/review_queue/`
- `vault/leads/`
- `vault/companies/`
- `vault/reports/contractor_pipeline_report.md`

For each review queue note, decide:

- `pursue`
- `skip`
- `research_more`

## 4. Record Review Decision

```bash
python scripts/review_lead.py <lead-slug-or-id> pursue --note "Good fit for contractor follow-up offer."
```

Other decisions:

```bash
python scripts/review_lead.py <lead-slug-or-id> skip --note "Poor fit."
python scripts/review_lead.py <lead-slug-or-id> research_more --note "Verify service area."
```

If the decision is `pursue`, SignalForge creates an outreach-ready note in `vault/outreach/`.

## 5. Update Outreach Status

Use this only for human-driven outreach progress. SignalForge does not send emails.

```bash
python scripts/update_outreach_status.py <lead-slug-or-id> sent --note "Message sent manually."
```

Supported statuses:

- `drafted`
- `sent`
- `replied`
- `follow_up_needed`
- `booked_call`
- `closed_won`
- `closed_lost`

Special behavior:

- `follow_up_needed` creates a note in `vault/followups/`.
- `booked_call` appends meeting prep to the outreach note.

## 6. Generate Report

```bash
make report
```

The report is written to:

```text
vault/reports/contractor_pipeline_report.md
```

Review the report from `vault/00_Dashboard.md`.

## 7. Import Provided Contacts

Use this when a client provides an email, call, or contact list. The import stores contacts in MongoDB and writes a summary note to `vault/contacts/`. It does not send messages or enrich contacts externally.

```bash
python scripts/import_contacts.py data/imports/sample_contacts.csv --module insurance_growth --source "client_provided_list"
```

Expected CSV fields:

```text
name,email,phone,company,role,city,state,notes
```

Imported contacts become available to simulation agents through the `contacts` collection.

## 8. Score And Segment Contacts

After importing contacts, score the module so agents can prioritize who to review first.

```bash
python scripts/score_contacts.py --module insurance_growth
```

The scorer updates MongoDB with `contact_score`, `segment`, `priority_reason`, `recommended_action`, and `scored_at`. It writes a segmentation report to `vault/contacts/`.

Segments:

- `high_priority`
- `nurture`
- `research_more`
- `low_priority`

Scoring is local and deterministic. SignalForge does not send messages or enrich contacts externally.

## 9. Draft Messages For Review

Generate editable drafts after contacts are scored or leads are marked `pursue`.

```bash
python scripts/draft_messages.py --module insurance_growth --limit 5
```

Drafts are written to `vault/messages/` and stored in MongoDB as `message_drafts`. Every draft starts as:

- `review_status=needs_review`
- `send_status=not_sent`

Review and edit drafts in Obsidian. SignalForge does not send email, SMS, DMs, social posts, or call external APIs.

## 10. Review Message Drafts

Record the human review decision after inspecting the draft in `vault/messages/`.

```bash
python scripts/review_message.py <draft-slug-or-id> approve --note "Approved for manual send."
python scripts/review_message.py <draft-slug-or-id> revise --note "Make the tone warmer."
python scripts/review_message.py <draft-slug-or-id> reject --note "Not a fit."
```

Decision behavior:

- `approve` sets `review_status=approved` and keeps `send_status=not_sent`.
- `revise` sets `review_status=needs_revision`.
- `reject` sets `review_status=rejected`.

Every decision appends a review log to the matching message note. SignalForge still does not send anything.

The Web Dashboard v1 can also record message review decisions from the Messages page. Dashboard actions update MongoDB and append vault logs; they still do not send anything.

## 11. Log Manual Sends

Use this only after a human sends an approved draft outside SignalForge. The script records the event; it does not send anything.

```bash
python scripts/log_manual_send.py <draft-slug-or-id> --channel email --note "Sent manually from Gmail."
python scripts/log_manual_send.py <draft-slug-or-id> --channel phone --note "Called and left voicemail."
```

Manual send logging requires `review_status=approved`. It sets `send_status=sent`, writes `sent_at`, appends a send log to the message note, and updates linked records:

- Lead draft: `outreach_status=sent`
- Contact draft: `contact_status=contacted`

## 12. Log Responses

Use this after a manually sent message produces an outcome. The draft must already have `send_status=sent`.

```bash
python scripts/log_response.py <draft-slug-or-id> --outcome interested --note "Asked for pricing details."
python scripts/log_response.py <draft-slug-or-id> --outcome call_booked --note "Discovery call booked manually."
```

Supported outcomes:

- `no_response`
- `interested`
- `not_interested`
- `call_booked`
- `requested_info`
- `wrong_contact`
- `bounced`
- `do_not_contact`

Linked record updates:

- Contact `interested`: `contact_status=interested`
- Contact `not_interested`: `contact_status=not_interested`
- Contact `call_booked`: `contact_status=call_booked`
- Contact `do_not_contact`: `contact_status=do_not_contact`
- Contact `bounced`: `contact_status=invalid`
- Lead `interested`: `outreach_status=replied`
- Lead `call_booked`: `outreach_status=booked_call`
- Lead `not_interested`: `outreach_status=closed_lost`

`call_booked` appends meeting prep to the message note. SignalForge does not create calendar events.

## 13. Generate Meeting Prep

Create a standalone prep note before a booked call. The input can be a contact, lead, or message draft id/slug.

```bash
python scripts/generate_meeting_prep.py <contact-lead-or-draft-slug>
```

The prep note is written to `vault/meetings/` and includes summary context, prioritization reason, original message, response history, likely pain points, recommended offer, discovery questions, call objective, and follow-up checklist.

SignalForge does not create calendar events or send messages.

## 14. Log Deal Outcomes

Track what happened after a meeting. The input can be a contact, lead, message draft, or meeting prep id/slug/path.

```bash
python scripts/log_deal_outcome.py <contact-lead-draft-or-meeting-slug> --outcome closed_won --deal-value 2500 --note "Client approved starter engagement."
python scripts/log_deal_outcome.py <contact-lead-draft-or-meeting-slug> --outcome closed_lost --note "Budget not available this quarter."
```

Supported outcomes:

- `proposal_sent`
- `negotiation`
- `closed_won`
- `closed_lost`
- `nurture`
- `no_show`
- `not_fit`

Deal outcomes update linked contacts, leads, message drafts, and the `deals` collection. Deal notes are written to `vault/deals/`.

`closed_won` notes include source, module, deal value, path to conversion, and next onboarding action. `closed_lost` notes include loss reason and future nurture recommendation.

SignalForge does not send messages, create invoices, or call CRM APIs.

## 15. Generate Revenue Performance Report

Use this after contact, message, meeting, or deal activity to review performance across modules.

```bash
make revenue-report
```

The report is written to:

```text
vault/reports/revenue_performance_report.md
```

Review it from `vault/00_Dashboard.md`. It summarizes contacts, leads, message statuses, response statuses, meeting indicators, deal outcomes, closed-won value, conversion paths, top modules, nurture contacts, and open opportunities from MongoDB only.

## 16. Run System Check

```bash
make check
```

The check verifies MongoDB, vault folders, required scripts, `docker-compose.yml`, contractor pipeline report generation, and revenue performance report generation.

## 17. Run Optional Agent Simulations

Use agents for planning only after MongoDB has current records. Agents write run logs to `vault/logs/agents/`, reference available message drafts, and never send outbound messages or publish content.

```bash
python scripts/run_agent.py outreach --module contractor_growth --dry-run
python scripts/run_agent.py content --module artist_growth --dry-run
python scripts/run_agent.py fan_engagement --module artist_growth --dry-run
python scripts/run_agent.py followup --module insurance_growth --dry-run
```

Review the generated agent logs in Obsidian before taking any manual action.

The dashboard Agent Console can run the same agents in dry-run mode through the local API. Each run creates MongoDB records in `agent_runs`, `agent_steps`, `agent_artifacts`, and `approval_requests`, then displays the selected run as a step-by-step timeline with inputs, outputs, warnings, related records, and approvals needed.

Use the Agent Console to answer:

- What records did the agent read?
- What did it decide at each step?
- What messages or records are related?
- What human approvals are still needed?
- Did the run complete, fail, or produce warnings?

Agent Console actions remain simulation-only. They do not send email, SMS, DMs, social posts, or calendar events.

## 18. Use Dashboard Detail Timelines

The dashboard Messages page supports full message review from the browser:

- message body
- recipient and linked contact/lead/deal
- review/send/response timeline
- response history
- approve/revise/reject actions

The Pipeline / CRM detail drawer shows linked lifecycle activity for contacts and leads, including import, scoring, drafting, approval, manual send logging, response logging, booked-call signals, and deal outcomes.

## 19. Stop The Stack

```bash
make down
```

## Operating Rules

- Keep `.env` local.
- Review outreach before sending anything manually.
- Do not treat generated copy as approved without human review.
- Use notes and status updates to keep MongoDB and the vault aligned.
