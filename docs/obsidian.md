# Obsidian

The vault is designed to be useful before automation is complete.

## Recommended Workflow

1. Open `vault/` in Obsidian.
2. Pin `00_Dashboard.md`.
3. Review `02_Workflows.md`.
4. Edit prompts in `prompts/` as your positioning changes.
5. Keep generated notes under their domain folders.

## Note Types

- Leads: `vault/leads`
- Companies: `vault/companies`
- Campaigns: `vault/campaigns`
- Content: `vault/content`
- Logs: `vault/logs`

## Frontmatter

Use frontmatter for status, source, score, and dates. This makes notes easier to query with Obsidian plugins such as Dataview.

Example:

```yaml
---
type: lead
status: new
score: 0
company: Example Inc
created: 2026-04-28
---
```

## Human Review

Generated notes should stay in `draft`, `new`, or `needs_research` until reviewed. Avoid treating generated outreach as approved copy without human review.
