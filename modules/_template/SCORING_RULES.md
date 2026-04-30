# Scoring Rules

## Scoring Goal

Explain what a high-scoring lead or opportunity means for this module.

## Score Fields

- `lead_score`
- `priority_reason`
- `score_breakdown`
- `review_status`

## Baseline Dimensions

| Dimension | Points | Rationale |
| --- | ---: | --- |
| Audience fit |  |  |
| Location or market fit |  |  |
| Data quality |  |  |
| Timing signal |  |  |
| Marketing or sales opportunity |  |  |
| Source confidence |  |  |

## Review Status Rules

- `needs_review`: default after enrichment.
- `pursue`: human approved for outreach prep.
- `research_more`: needs more validation.
- `skip`: not worth pursuing now.

## Score Interpretation

- 90-100: high priority.
- 75-89: good fit, review before outreach.
- 60-74: research before outreach.
- Below 60: low priority unless strategically important.

## Required Explanation

Every score should explain:

- Why the lead matters.
- What signal supports it.
- What risk or unknown remains.
- What next action is recommended.
