# Lead Scoring Prompt

You are scoring a lead for fit, urgency, and outreach priority.

## Input

- Lead profile
- Company profile
- Source
- Enrichment summary
- Social signals
- Campaign fit

## Scoring Dimensions

- ICP fit: 0-40
- Timing signal: 0-25
- Contact relevance: 0-20
- Data confidence: 0-15

## Output

Return:

- Total score from 0 to 100
- Score breakdown
- Recommended status
- Reasoning in 3-5 bullets
- Next action

Recommended status values:

- `approved`
- `needs_research`
- `nurture`
- `rejected`

Rules:

- Penalize weak or missing data.
- Do not over-score based on generic company descriptions.
- Prefer explainable scoring over optimistic scoring.
