# Insurance Module Requirements

## Objective

Help an insurance operator find and prioritize commercial prospects that may need a risk review, coverage update, renewal conversation, or industry-specific insurance offer.

## Functional Requirements

- Define target insurance markets and excluded markets.
- Collect or import structured business leads.
- Capture source attribution for every lead.
- Score leads based on business type, timing signal, risk relevance, and data quality.
- Write lead, company, review, outreach, follow-up, and report notes.
- Keep all outreach human-reviewed.

## Technical Requirements

- Use existing SignalForge MongoDB collections.
- Use existing vault folders and markdown note patterns.
- Do not add insurance carrier integrations yet.
- Do not quote premiums, coverage terms, or legal advice automatically.

## Data Requirements

- Company name
- Industry
- Location
- Website
- Source
- Risk or timing signal
- Contact confidence
- Recommended offer

## Acceptance Criteria

- Scoring rules are explainable.
- Outreach templates avoid compliance-sensitive claims.
- Operator workflow is clear enough for daily use.
- KPIs map to review, outreach, replies, calls, and won/lost outcomes.
