# signalForge Dashboard

## Today

- Date:
- Primary campaign:
- Pipeline status:
- Review queue:

## Active Views

- Leads: [[leads/lead_template]]
- Companies: [[companies/company_template]]
- Campaigns: [[campaigns/campaign_template]]
- Content: [[content/post_template]]
- Daily log: [[logs/daily_log_template]]
- Contractor pipeline report: [[reports/contractor_pipeline_report]]
- Revenue performance report: [[reports/revenue_performance_report]]

## Operator Report

- Latest report: [[reports/contractor_pipeline_report]]
- Revenue report: [[reports/revenue_performance_report]]
- Regenerate with `python scripts/generate_pipeline_report.py`
- Regenerate revenue report with `python scripts/generate_revenue_report.py`
- Review follow-ups in `followups/`
- Review outreach lifecycle in `outreach/`
- Review deal outcomes in `deals/`

## Pipeline Checklist

- [ ] Collect new leads
- [ ] Enrich new companies
- [ ] Process social signals
- [ ] Generate outreach drafts
- [ ] Generate content drafts
- [ ] Review and approve human-facing copy
- [ ] Update outreach lifecycle statuses
- [ ] Regenerate contractor pipeline report
- [ ] Regenerate revenue performance report
- [ ] Log decisions in [[03_Command_Log]]

## Metrics To Track

| Metric | Current | Notes |
| --- | ---: | --- |
| New leads collected | 0 |  |
| Companies enriched | 0 |  |
| Signals processed | 0 |  |
| Outreach drafts created | 0 |  |
| Posts drafted | 0 |  |

## Review Queue

```dataview
TABLE status, company, score, next_action
FROM "leads"
WHERE status != "approved"
SORT file.mtime DESC
```
