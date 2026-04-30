# Terminal Commands

## Setup

```bash
cp .env.example .env
docker compose up --build
```

## Run Health Check

```bash
curl http://localhost:8000/health
```

## Run Contractor Lead Engine v5 Workflow

```bash
./scripts/run_daily_pipeline.sh --business-type "roofing contractor" --location "Austin, TX" --count 5
```

You can also use environment variables:

```bash
BUSINESS_TYPE="plumbing contractor" LOCATION="Denver, CO" LEAD_COUNT=3 ./scripts/run_daily_pipeline.sh
```

This reads structured contractor listings from `data/raw/contractor_listings_seed.json`, stores them in MongoDB, enriches them with v3 lead intelligence, and writes review notes to `vault/review_queue`. v4 and v5 scripts then handle human review, outreach prep, and lifecycle tracking. No email, calendar, authenticated API, or scraping framework is used.

To use a different mounted dataset:

```bash
./scripts/run_daily_pipeline.sh --business-type "hvac contractor" --location "Charlotte, NC" --count 2 --data-file "/data/raw/contractor_listings_seed.json"
```

## Verify Lead Engine Outputs

Keep Mongo running after the pipeline, then inspect recent records:

```bash
docker compose exec mongo mongosh signalforge --quiet --eval "db.leads.find({engine: 'contractor_lead_engine_v3'}, {company_name: 1, source: 1, website_present: 1, marketing_gap: 1, lead_score: 1, review_status: 1, outreach_draft: 1}).sort({updated_at: -1}).limit(5).pretty()"
```

Check generated markdown:

```bash
find vault/leads vault/companies vault/review_queue vault/logs -type f | sort
```

## Review A Lead

Use the review script after the v3 pipeline has created review queue notes. The lead argument can be a Mongo ObjectId, company slug, lead note slug, or review queue note slug.

```bash
python scripts/review_lead.py module-v3-final-20260428-austin-roof-works pursue --note "Good fit for contractor follow-up offer."
```

Supported decisions:

```bash
python scripts/review_lead.py module-v3-final-20260428-austin-roof-works pursue
python scripts/review_lead.py module-v3-final-20260428-austin-roof-works research_more
python scripts/review_lead.py module-v3-final-20260428-austin-roof-works skip
```

When the decision is `pursue`, the script creates an outreach-ready note in `vault/outreach/`. It does not send email or automate outbound.

Verify reviewed leads:

```bash
docker compose exec mongo mongosh signalforge --quiet --eval "db.leads.find({review_status: 'pursue'}, {company_name: 1, lead_score: 1, outreach_note_path: 1}).sort({reviewed_at: -1}).limit(5).pretty()"
```

## Track Outreach Status

Use this after a lead has been marked `pursue`. The lead argument can be a Mongo ObjectId, company slug, lead note slug, review note slug, or outreach note slug.

```bash
python scripts/update_outreach_status.py module-v4-test-20260428-austin-roof-works sent --note "Message sent manually."
```

Supported statuses:

```bash
python scripts/update_outreach_status.py module-v4-test-20260428-austin-roof-works drafted
python scripts/update_outreach_status.py module-v4-test-20260428-austin-roof-works sent
python scripts/update_outreach_status.py module-v4-test-20260428-austin-roof-works replied
python scripts/update_outreach_status.py module-v4-test-20260428-austin-roof-works follow_up_needed --note "No reply after initial message."
python scripts/update_outreach_status.py module-v4-test-20260428-austin-roof-works booked_call --note "Discovery call scheduled by human."
python scripts/update_outreach_status.py module-v4-test-20260428-austin-roof-works closed_won
python scripts/update_outreach_status.py module-v4-test-20260428-austin-roof-works closed_lost
```

`follow_up_needed` creates a note in `vault/followups/`. `booked_call` appends meeting prep to the outreach note when one exists. This does not send email or integrate calendars.

Verify lifecycle state:

```bash
docker compose exec mongo mongosh signalforge --quiet --eval "db.leads.find({outreach_status: {$exists: true}}, {company_name: 1, outreach_status: 1, latest_followup_note_path: 1}).sort({outreach_status_updated_at: -1}).limit(5).pretty()"
```

## Generate Pipeline Report

Generate a markdown dashboard report from MongoDB:

```bash
python scripts/generate_pipeline_report.py
```

The report is written to:

```text
vault/reports/contractor_pipeline_report.md
```

The report includes total leads, review and outreach status counts, average lead score, top leads, follow-ups, booked calls, win/loss counts, and latest pipeline runs.

## Import Contacts

Import a provided CSV contact list into MongoDB:

```bash
python scripts/import_contacts.py data/imports/sample_contacts.csv --module insurance_growth --source "client_provided_list"
```

Expected CSV fields:

```text
name,email,phone,company,role,city,state,notes
```

Imported contacts are stored in the `contacts` collection with `contact_status=imported`. A summary note is written to `vault/contacts/`. This does not send messages or enrich contacts externally.

Verify imported contacts:

```bash
docker compose exec mongo mongosh signalforge --quiet --eval "db.contacts.find({module: 'insurance_growth'}, {_id: 0, name: 1, email: 1, company: 1, module: 1, source: 1, contact_status: 1}).sort({imported_at: -1}).limit(5).pretty()"
```

## Score And Segment Contacts

Score imported contacts for a module:

```bash
python scripts/score_contacts.py --module insurance_growth
```

This updates each matching contact with:

```text
contact_score
segment
priority_reason
recommended_action
scored_at
```

Segments:

```text
high_priority
nurture
research_more
low_priority
```

The segmentation report is written to `vault/contacts/`. This does not send messages or enrich contacts externally.

Verify scored contacts:

```bash
docker compose exec mongo mongosh signalforge --quiet --eval "db.contacts.find({module: 'insurance_growth'}, {_id: 0, name: 1, company: 1, contact_score: 1, segment: 1, priority_reason: 1, recommended_action: 1}).sort({contact_score: -1}).limit(5).pretty()"
```

## Draft Messages

Generate safe, editable message drafts from high-priority contacts and approved leads:

```bash
python scripts/draft_messages.py --module insurance_growth --limit 5
```

Drafts are stored in the `message_drafts` collection and written to:

```text
vault/messages/
```

Each draft starts with:

```text
review_status=needs_review
send_status=not_sent
```

This uses local templates only. It does not send email, SMS, DMs, social posts, or call external APIs.

Verify message drafts:

```bash
docker compose exec mongo mongosh signalforge --quiet --eval "db.message_drafts.find({module: 'insurance_growth'}, {_id: 0, recipient_name: 1, target_type: 1, review_status: 1, send_status: 1, subject_line: 1, message_note_path: 1}).sort({created_at: -1}).limit(5).pretty()"
```

## Review Message Drafts

Approve, revise, or reject a generated message draft before any manual send. The draft argument can be a Mongo ObjectId, `draft_key`, note slug, or message note path.

```bash
python scripts/review_message.py <draft-slug-or-id> approve --note "Approved for manual send."
python scripts/review_message.py <draft-slug-or-id> revise --note "Make the tone warmer."
python scripts/review_message.py <draft-slug-or-id> reject --note "Not a fit."
```

Decision behavior:

```text
approve -> review_status=approved, send_status=not_sent
revise  -> review_status=needs_revision
reject  -> review_status=rejected
```

Each decision updates MongoDB and appends a review log to the matching `vault/messages/` note. This does not send anything.

Verify reviewed drafts:

```bash
docker compose exec mongo mongosh signalforge --quiet --eval "db.message_drafts.find({module: 'insurance_growth'}, {_id: 0, recipient_name: 1, review_status: 1, send_status: 1, review_note: 1}).sort({reviewed_at: -1}).limit(5).pretty()"
```

## Log Manual Sends

Log a message that a human operator sent outside SignalForge. The draft must already have `review_status=approved`.

```bash
python scripts/log_manual_send.py <draft-slug-or-id> --channel email --note "Sent manually from Gmail."
python scripts/log_manual_send.py <draft-slug-or-id> --channel phone --note "Called and left voicemail."
```

Supported channels:

```text
email
phone
sms
dm
social_comment
other
```

This sets `send_status=sent`, records `sent_at`, appends a send event to the `message_drafts` record, and appends a send log to the matching `vault/messages/` note. Linked leads are updated to `outreach_status=sent`; linked contacts are updated to `contact_status=contacted`.

Verify manual send logs:

```bash
docker compose exec mongo mongosh signalforge --quiet --eval "db.message_drafts.find({send_status: 'sent'}, {_id: 0, recipient_name: 1, send_status: 1, send_channel: 1, sent_at: 1, message_note_path: 1}).sort({sent_at: -1}).limit(5).pretty()"
```

## Log Responses

Log what happened after a message was manually sent. The draft must already have `send_status=sent`.

```bash
python scripts/log_response.py <draft-slug-or-id> --outcome interested --note "Asked for pricing details."
python scripts/log_response.py <draft-slug-or-id> --outcome call_booked --note "Discovery call booked manually."
```

Supported outcomes:

```text
no_response
interested
not_interested
call_booked
requested_info
wrong_contact
bounced
do_not_contact
```

Contact outcome mappings:

```text
interested -> interested
not_interested -> not_interested
call_booked -> call_booked
do_not_contact -> do_not_contact
bounced -> invalid
```

Lead outcome mappings:

```text
interested -> replied
call_booked -> booked_call
not_interested -> closed_lost
```

`call_booked` appends a meeting prep section to the message note. This does not send messages or create calendar events.

Verify responses:

```bash
docker compose exec mongo mongosh signalforge --quiet --eval "db.message_drafts.find({response_status: {$exists: true}}, {_id: 0, recipient_name: 1, send_status: 1, response_status: 1, response_note: 1, responded_at: 1}).sort({responded_at: -1}).limit(5).pretty()"
```

## Generate Meeting Prep

Generate a standalone meeting prep note from a contact, lead, or message draft:

```bash
python scripts/generate_meeting_prep.py <contact-lead-or-draft-slug>
```

Examples:

```bash
python scripts/generate_meeting_prep.py insurance-growth-contact-insurance-growth-andre-brooks-example-com
python scripts/generate_meeting_prep.py andre-brooks
python scripts/generate_meeting_prep.py austin-roof-works
```

The note is written to:

```text
vault/meetings/
```

Meeting prep uses only local MongoDB data and markdown context. It does not create calendar events or send messages.

## Log Deal Outcomes

Track what happened after a meeting. The input can be a contact, lead, message draft, or meeting prep id/slug/path.

```bash
python scripts/log_deal_outcome.py <contact-lead-draft-or-meeting-slug> --outcome closed_won --deal-value 2500 --note "Client approved starter engagement."
python scripts/log_deal_outcome.py <contact-lead-draft-or-meeting-slug> --outcome closed_lost --note "Budget not available this quarter."
```

Supported outcomes:

```text
proposal_sent
negotiation
closed_won
closed_lost
nurture
no_show
not_fit
```

Deal notes are written to:

```text
vault/deals/
```

`closed_won` deal notes include source, module, deal value, path to conversion, and next onboarding action. `closed_lost` deal notes include loss reason and future nurture recommendation. This does not send messages, create invoices, or call CRM APIs.

Verify deals:

```bash
docker compose exec mongo mongosh signalforge --quiet --eval "db.deals.find({}, {_id: 0, company: 1, person: 1, outcome: 1, deal_value: 1, module: 1, deal_note_path: 1}).sort({updated_at: -1}).limit(5).pretty()"
```

## Generate Revenue Performance Report

Summarize performance across modules, contacts, leads, messages, responses, meeting indicators, and deals:

```bash
python scripts/generate_revenue_report.py
```

Or use the Makefile shortcut:

```bash
make revenue-report
```

The report is written to:

```text
vault/reports/revenue_performance_report.md
```

The report includes contacts and leads by module, message drafts by review and send status, responses by status, MongoDB-only meeting indicators, deals by outcome, closed-won count and value, conversion paths, top modules, nurture contacts, and open opportunities.

Verify the report file exists:

```bash
ls -la vault/reports/revenue_performance_report.md
```

## Run Web Dashboard

Start the FastAPI backend and React dashboard:

```bash
make dashboard
```

Open:

```text
http://localhost:5174
```

API health:

```bash
curl http://localhost:8000/health
```

Run individual services:

```bash
make api
make web
```

Dashboard message review actions call the local API and update MongoDB/vault logs only. They do not send email, SMS, DMs, social posts, or calendar events.

## Run Simulation Agents

Agents read MongoDB, print planned actions, and write logs to `vault/logs/agents/`. They are simulation-only and do not send emails, SMS, DMs, social posts, calendar events, or external API calls.

```bash
python scripts/run_agent.py outreach --module contractor_growth --dry-run
python scripts/run_agent.py content --module artist_growth --dry-run
python scripts/run_agent.py fan_engagement --module artist_growth --dry-run
python scripts/run_agent.py followup --module insurance_growth --dry-run
```

Supported modules:

```text
contractor_growth
insurance_growth
artist_growth
media_growth
```

Supported agents:

```text
outreach
content
fan_engagement
followup
```

## Run Individual Services

```bash
docker compose run --rm -e BUSINESS_TYPE="roofing contractor" -e LOCATION="Austin, TX" -e LEAD_COUNT=5 -e PIPELINE_RUN_ID="manual-test" lead_scraper
docker compose run --rm -e BUSINESS_TYPE="roofing contractor" -e LOCATION="Austin, TX" -e PIPELINE_RUN_ID="manual-test" lead_enricher
docker compose run --rm social_processor
docker compose run --rm post_generator
```

## Create Notes

```bash
python scripts/create_company_note.py --company "Example Inc" --website "https://example.com"
python scripts/create_lead_note.py --company "Example Inc" --contact "Jane Doe" --role "VP Marketing"
```

## Inspect Compose Config

```bash
docker compose config
```

## Stop The Stack

```bash
docker compose down
```

## Remove Mongo Data Volume

Use this only when you intentionally want to delete local database state:

```bash
docker compose down -v
```
