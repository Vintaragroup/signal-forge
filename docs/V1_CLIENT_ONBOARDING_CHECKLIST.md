# SignalForge v1 Client Onboarding Checklist

Use this checklist when preparing SignalForge for a new client, industry, or module.

## 1. Confirm Fit

- [ ] Define the client type or industry.
- [ ] Confirm the business goal: leads, outreach, content, audience growth, follow-up, or reporting.
- [ ] Confirm what data the client can provide.
- [ ] Confirm outbound rules and approval requirements.
- [ ] Confirm the system will remain local-first and human-reviewed.

## 2. Choose Or Create Module

- [ ] Review existing modules:
  - `modules/insurance_growth`
  - `modules/artist_growth`
  - `modules/media_growth`
- [ ] Copy `modules/_template` if a new module is needed.
- [ ] Fill in:
  - `CLIENT_PROFILE.md`
  - `AUDIENCE_PERSONAS.md`
  - `SIGNAL_SOURCES.md`
  - `SCORING_RULES.md`
  - `OUTREACH_TEMPLATES.md`
  - `CONTENT_STRATEGY.md`
  - `CAMPAIGN_PLAN.md`
  - `KPI_TRACKING.md`
  - `OPERATOR_WORKFLOW.md`
- [ ] Keep the module documentation-first unless automation is explicitly added later.

## 3. Prepare Local Environment

- [ ] Copy `.env.example` to `.env` if needed.
- [ ] Keep `.env` private.
- [ ] Start the stack:

```bash
make up
```

- [ ] Run:

```bash
make check
```

- [ ] Open `vault/` in Obsidian.

## 4. Prepare Client Data

- [ ] Put client contact CSVs in `data/imports/`.
- [ ] Confirm CSV fields:

```text
name,email,phone,company,role,city,state,notes
```

- [ ] Assign a module name, for example `insurance_growth`.
- [ ] Assign a source label, for example `client_provided_list`.
- [ ] Do not include data that should not be stored locally.

## 5. Import Contacts

```bash
python scripts/import_contacts.py data/imports/sample_contacts.csv --module insurance_growth --source "client_provided_list"
```

- [ ] Review the import note in `vault/contacts/`.
- [ ] Confirm contacts exist in MongoDB if needed.

## 6. Score Contacts

```bash
python scripts/score_contacts.py --module insurance_growth
```

- [ ] Review the segmentation report in `vault/contacts/`.
- [ ] Confirm high-priority contacts make sense.
- [ ] Adjust module strategy docs if the scoring rationale is off.

## 7. Draft Messages

```bash
python scripts/draft_messages.py --module insurance_growth --limit 5
```

- [ ] Review drafts in `vault/messages/`.
- [ ] Edit draft text in Obsidian if needed.
- [ ] Do not send any draft until reviewed and approved.

## 8. Review Messages

```bash
python scripts/review_message.py <draft-slug-or-id> approve --note "Approved for manual send."
python scripts/review_message.py <draft-slug-or-id> revise --note "Needs warmer tone."
python scripts/review_message.py <draft-slug-or-id> reject --note "Not a fit."
```

- [ ] Confirm approved drafts still have `send_status=not_sent`.
- [ ] Confirm rejected or revised drafts are not used for manual sending.

## 9. Track Manual Outreach

After a human sends outside SignalForge:

```bash
python scripts/log_manual_send.py <draft-slug-or-id> --channel email --note "Sent manually from Gmail."
```

After a response:

```bash
python scripts/log_response.py <draft-slug-or-id> --outcome interested --note "Asked for more information."
python scripts/log_response.py <draft-slug-or-id> --outcome call_booked --note "Discovery call booked manually."
```

- [ ] Keep all notes factual.
- [ ] Do not log sends that did not happen.
- [ ] Do not use SignalForge as a sending system.

## 10. Prepare Meetings

```bash
python scripts/generate_meeting_prep.py <contact-lead-or-draft-slug>
```

- [ ] Review `vault/meetings/`.
- [ ] Add any human context before the call.
- [ ] Log the outcome after the meeting.

## 11. Track Deal Outcomes

```bash
python scripts/log_deal_outcome.py <contact-lead-draft-or-meeting-slug> --outcome proposal_sent --note "Proposal sent manually."
python scripts/log_deal_outcome.py <contact-lead-draft-or-meeting-slug> --outcome closed_won --deal-value 2500 --note "Client approved starter engagement."
python scripts/log_deal_outcome.py <contact-lead-draft-or-meeting-slug> --outcome closed_lost --note "Not a fit right now."
```

- [ ] Review `vault/deals/`.
- [ ] Confirm deal value is recorded for closed-won outcomes.
- [ ] Capture loss reasons for closed-lost outcomes.

## 12. Generate Reports

```bash
make report
make revenue-report
```

- [ ] Review `vault/reports/contractor_pipeline_report.md`.
- [ ] Review `vault/reports/revenue_performance_report.md`.
- [ ] Review `vault/00_Dashboard.md`.

## 13. Handoff

- [ ] Share the module folder with the operator.
- [ ] Share this checklist.
- [ ] Share `docs/OPERATOR_PLAYBOOK.md`.
- [ ] Share `docs/V1_DEMO_SCRIPT.md`.
- [ ] Confirm backup process in `docs/V1_BACKUP_AND_EXPORT.md`.
- [ ] Confirm the operator understands that SignalForge v1 does not send messages or call external systems.
