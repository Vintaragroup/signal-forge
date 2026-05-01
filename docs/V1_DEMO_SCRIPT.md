# SignalForge v1 Demo Script

This demo shows SignalForge from contact import to closed-won revenue reporting. It uses local MongoDB data, the sample CSV, and the Obsidian vault. It does not send messages, create calendar events, create invoices, or call external APIs.

Estimated time: 10-15 minutes.

## Fast Dashboard Demo Mode

For a clean no-prep walkthrough, open the dashboard and click `Start Demo` on Overview, or open the Demo Mode page.

Demo Mode uses browser-seeded synthetic contacts, leads, drafts, responses, and deals. Every record is labeled Demo Mode and the dashboard shows `Demo Mode - No real messages will be sent`.

Guided flow:

1. Run Outreach
2. Review Drafts
3. Approve Message
4. Simulate Response
5. Show Deal Outcome

Demo Mode does not write to MongoDB, run agents, call GPT, send messages, create calendar events, issue invoices, or call CRM/platform APIs. Use the steps below when you want to demo the full local data pipeline.

## 1. Start The Stack

```bash
make up
docker compose ps
```

Narration:

SignalForge runs locally. Docker Compose starts MongoDB and the minimal API service. The vault remains a normal local folder that can be opened in Obsidian.

## 2. Run The System Check

```bash
make check
```

Narration:

The check confirms required scripts and vault folders exist, MongoDB is reachable, and reports can be generated.

## 3. Run The Contractor Lead Pipeline

```bash
make pipeline
```

Optional custom demo input:

```bash
BUSINESS_TYPE="roofing contractor" LOCATION="Austin, TX" LEAD_COUNT=5 make pipeline
```

Show:

- `vault/review_queue/`
- `vault/leads/`
- `vault/companies/`
- `vault/reports/contractor_pipeline_report.md`

Narration:

The contractor engine creates structured leads, enriches them, scores them, and writes human-readable review notes.

## 4. Import A Client Contact List

```bash
python scripts/import_contacts.py data/imports/sample_contacts.csv --module insurance_growth --source "client_provided_list"
```

Show:

- `vault/contacts/`
- The latest contact import summary note.

Narration:

Client-provided lists enter MongoDB as contacts and become available to module-aware workflows.

## 5. Score And Segment Contacts

```bash
python scripts/score_contacts.py --module insurance_growth
```

Show:

- Latest `vault/contacts/contact_segmentation_insurance_growth_*.md`

Narration:

Contacts are scored locally. The system identifies high-priority contacts without external enrichment.

## 6. Draft Messages

```bash
python scripts/draft_messages.py --module insurance_growth --limit 3
```

Show:

- `vault/messages/`
- A generated message draft.

Narration:

SignalForge drafts editable messages using local templates only. Drafts start as `needs_review` and `not_sent`.

## 7. Review A Draft

Use a generated draft slug. With the sample CSV, this slug is usually available:

```bash
python scripts/review_message.py insurance-growth-contact-insurance-growth-andre-brooks-example-com approve --note "Approved for manual demo send."
```

Show:

- The matching note in `vault/messages/`.
- The appended review log.

Narration:

Human review is mandatory. Approval does not send the message.

## 8. Log A Manual Send

```bash
python scripts/log_manual_send.py insurance-growth-contact-insurance-growth-andre-brooks-example-com --channel email --note "Sent manually from Gmail during demo."
```

Narration:

This records that the operator sent a message outside SignalForge. SignalForge itself still sends nothing.

## 9. Log A Positive Response

```bash
python scripts/log_response.py insurance-growth-contact-insurance-growth-andre-brooks-example-com --outcome call_booked --note "Discovery call booked manually during demo."
```

Show:

- The message note response log.
- The meeting prep section appended to the message note.

Narration:

Response logging connects the draft to contact status and meeting preparation.

## 10. Generate Meeting Prep

```bash
python scripts/generate_meeting_prep.py insurance-growth-contact-insurance-growth-andre-brooks-example-com
```

Show:

- The generated note in `vault/meetings/`.

Narration:

The meeting note pulls together contact context, original message, response history, likely pain points, discovery questions, and follow-up checklist.

## 11. Log A Closed-Won Outcome

Use the generated meeting note path from the previous command, or use the message draft slug:

```bash
python scripts/log_deal_outcome.py insurance-growth-contact-insurance-growth-andre-brooks-example-com --outcome closed_won --deal-value 2500 --note "Client approved starter engagement during demo."
```

Show:

- `vault/deals/`
- The generated or updated deal note.

Narration:

Deal tracking updates linked MongoDB records and writes a deal note. It does not create an invoice or push to a CRM.

## 12. Generate Reports

```bash
make report
make revenue-report
```

Show:

- `vault/reports/contractor_pipeline_report.md`
- `vault/reports/revenue_performance_report.md`
- `vault/00_Dashboard.md`

Narration:

The contractor report summarizes lead pipeline health. The revenue report summarizes contacts, messages, responses, meeting indicators, deals, closed-won value, conversion paths, top modules, nurture contacts, and open opportunities.

## 13. Close The Demo

```bash
make check
```

Closing points:

- SignalForge v1 is local-first.
- MongoDB is the structured system of record.
- The Obsidian vault is the operator control layer.
- Agents are simulation-only.
- All outbound work remains human-approved and manual.
- The system is ready to copy for additional modules without adding integrations.
