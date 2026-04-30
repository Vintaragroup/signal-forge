# Operator Workflow

## Daily Workflow

1. Start Docker services.
2. Run the module pipeline or import.
3. Review generated notes.
4. Decide `pursue`, `skip`, or `research_more`.
5. Prepare outreach for pursued leads.
6. Track outreach lifecycle.
7. Generate report.
8. Log important decisions.

## Commands

Start:

```bash
make up
```

Run pipeline:

```bash
make pipeline
```

Review lead:

```bash
python scripts/review_lead.py <lead-slug-or-id> pursue --note "Reason for decision."
```

Track outreach:

```bash
python scripts/update_outreach_status.py <lead-slug-or-id> sent --note "Sent manually."
```

Generate report:

```bash
make report
```

Check system:

```bash
make check
```

## Human Review Rules

- Do not send outreach without human review.
- Confirm facts before using generated copy.
- Use `research_more` when source data is weak.
- Use `skip` when fit is poor.
- Keep notes concise and decision-oriented.

## Output Folders

- `vault/leads`
- `vault/companies`
- `vault/review_queue`
- `vault/outreach`
- `vault/followups`
- `vault/reports`
