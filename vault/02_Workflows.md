# Workflows

## Contractor Lead Engine v6

The contractor lead engine imports structured contractor listings from `data/raw/contractor_listings_seed.json`, enriches each lead with v3 intelligence, uses v4 review actions to prepare human-approved outreach, tracks the v5 outreach lifecycle, generates a v6 operator report from MongoDB, and can be monitored through the local web dashboard. The source is labeled `google_search_v1`, but this version uses a local dataset only. It does not use authentication, paid APIs, scraping frameworks, email sending, calendar integration, outbound automation, GPT runtime, or external CRM/invoicing systems.

1. Run `./scripts/run_daily_pipeline.sh --business-type "roofing contractor" --location "Austin, TX" --count 5`.
2. Confirm new lead notes appear in `leads/`.
3. Confirm company notes appear in `companies/`.
4. Confirm review notes appear in `review_queue/`.
5. Open the run log in `logs/`.
6. Review lead scores, priority reasons, recommended offers, and outreach drafts.
7. Run `python scripts/review_lead.py <lead-slug-or-id> pursue|skip|research_more`.
8. If the decision is `pursue`, review the new outreach note in `outreach/`.
9. Track outreach progress with `python scripts/update_outreach_status.py <lead-slug-or-id> <status>`.
10. Generate the operator report with `python scripts/generate_pipeline_report.py`.
11. Review [[reports/contractor_pipeline_report]] from the dashboard.
12. Add important decisions to [[03_Command_Log]].

## Web Dashboard

Start the local dashboard with:

```bash
make dashboard
```

Open `http://localhost:5174`. The dashboard reads local MongoDB through FastAPI and shows overview metrics, CRM records, message review state, dry-run agent runs, deals, and reports. Dashboard review actions only update MongoDB and append vault logs; they do not send messages or call external systems.

Environment variables are also supported:

```bash
BUSINESS_TYPE="plumbing contractor" LOCATION="Denver, CO" LEAD_COUNT=3 ./scripts/run_daily_pipeline.sh
```

## Daily Pipeline

For now, the daily pipeline is the Contractor Lead Engine structured listing import plus intelligence review loop. Later modules can add live source collection, social signals, content generation, and outbound execution.

## Lead Review

For each lead:

- Confirm the company is real and relevant.
- Check source attribution.
- Review the generated `lead_score` and score breakdown.
- Read the priority reason, marketing gap, and recommended offer.
- Read the outreach draft.
- Assign a next action.
- Mark the review decision as `pursue`, `research_more`, or `skip` with `scripts/review_lead.py`.

## Review Queue

Each enriched lead gets a note in `review_queue/`. Use it to decide:

- Whether to pursue, skip, or research more.
- What offer to lead with.
- What message to send.
- What next action to take.

Review command:

```bash
python scripts/review_lead.py module-v3-final-20260428-austin-roof-works pursue --note "Good fit for contractor follow-up offer."
```

Decision behavior:

- `pursue`: updates Mongo, appends decision logs, and creates an outreach-ready note in `outreach/`.
- `research_more`: updates Mongo and appends decision logs for later research.
- `skip`: updates Mongo and appends decision logs without creating outreach.

## Outreach Preparation

Outreach notes live in `outreach/`. They are ready for human review only and include:

- Company name
- Lead score
- Priority reason
- Recommended offer
- Outreach draft
- Next action
- Follow-up checklist

## Outreach Lifecycle

After a lead is marked `pursue`, track manual outreach progress with:

```bash
python scripts/update_outreach_status.py module-v4-test-20260428-austin-roof-works sent --note "Message sent manually."
```

Supported statuses:

- `drafted`
- `sent`
- `replied`
- `follow_up_needed`
- `booked_call`
- `closed_won`
- `closed_lost`

Lifecycle behavior:

- Every status update writes to Mongo and appends logs to the lead note.
- If an outreach note exists, status updates are appended there too.
- `follow_up_needed` creates a note in `followups/`.
- `booked_call` appends a meeting prep section to the outreach note.
- No emails are sent and no calendars are updated.

## Reporting

Generate the contractor pipeline report with:

```bash
python scripts/generate_pipeline_report.py
```

The report is written to [[reports/contractor_pipeline_report]] and summarizes:

- Total leads
- Leads by review status
- Leads by outreach status
- Average lead score
- Top 10 leads by lead score
- Leads needing follow-up
- Booked calls
- Closed won and closed lost counts
- Latest pipeline runs

## Company Enrichment

Use [[prompts/company_enrichment_prompt]] to turn raw company data into:

- ICP fit summary
- Value hypothesis
- Buying triggers
- Relevant contacts
- Risks or unknowns

## Outreach Generation

Use [[prompts/outreach_prompt]] only after a company has enough context. Outreach should reference real signals, avoid false familiarity, and stay concise.

## Content Generation

Use [[prompts/content_generation_prompt]] to turn repeated market signals into posts. Keep generated content aligned with active campaigns.
