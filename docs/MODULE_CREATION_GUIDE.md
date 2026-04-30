# Module Creation Guide

SignalForge modules are reusable strategy packs for a client, industry, or audience. A module should define the operating logic before new code is added.

## Create A New Module

```bash
cp -R modules/_template modules/<module_slug>
```

## Available Modules

- [Insurance Growth](../modules/insurance_growth/README.md)
- [Artist Growth](../modules/artist_growth/README.md)
- [Media Growth](../modules/media_growth/README.md)
- [Template](../modules/_template/README.md)

Then complete each file in the copied module:

- `CLIENT_PROFILE.md`
- `AUDIENCE_PERSONAS.md`
- `SIGNAL_SOURCES.md`
- `SCORING_RULES.md`
- `OUTREACH_TEMPLATES.md`
- `CONTENT_STRATEGY.md`
- `CAMPAIGN_PLAN.md`
- `KPI_TRACKING.md`
- `OPERATOR_WORKFLOW.md`

## Module Design Rules

- Start with documentation and sample data.
- Define scoring before automation.
- Keep outreach human-approved.
- Keep source attribution.
- Avoid external integrations until they are clearly required.
- Preserve MongoDB for structured state and the vault for human-readable output.

## Insurance Module

Typical focus:

- Agencies
- Brokers
- Local businesses needing coverage
- Niche verticals such as contractors, restaurants, or clinics

Signals:

- New business openings
- Hiring growth
- Commercial property changes
- Compliance deadlines
- Industry-specific risk events

Scoring ideas:

- Business category fit
- Policy timing signal
- Company size or location
- Evidence of growth or risk
- Contactability

Outreach angle:

- Risk review
- Coverage gap check
- Renewal readiness
- Industry-specific protection checklist

## Contractors Module

Typical focus:

- Roofing
- Plumbing
- HVAC
- Electrical
- Landscaping
- Specialty trades

Signals:

- Local search listings
- Missing or weak website
- Hiring technicians
- Service area expansion
- Review volume

Scoring ideas:

- Category match
- Local market match
- Website presence
- Marketing gap
- Source visibility

Outreach angle:

- Missed-lead follow-up
- Local search conversion
- Quote request workflow
- Service area campaign

## Media Module

Typical focus:

- Publishers
- Podcasts
- Newsletters
- Creators
- Production companies
- Sponsors and partners

Signals:

- Audience growth
- Sponsorship activity
- New show or series
- Event announcements
- Advertiser categories

Scoring ideas:

- Audience fit
- Partnership relevance
- Sponsorship timing
- Content alignment
- Distribution quality

Outreach angle:

- Partnership idea
- Sponsorship package
- Audience collaboration
- Content distribution support

## Music Artists Module

Typical focus:

- Independent artists
- Managers
- Venues
- Promoters
- Labels
- Playlist and media contacts

Signals:

- New release
- Tour dates
- Venue activity
- Playlist placements
- Social engagement
- Press mentions

Scoring ideas:

- Genre fit
- Audience overlap
- Timing around release or show
- Market relevance
- Contact confidence

Outreach angle:

- Release support
- Show promotion
- Playlist or press pitch
- Fan growth campaign

## Real Estate Module

Typical focus:

- Agents
- Brokerages
- Investors
- Property managers
- Developers
- Local service partners

Signals:

- New listings
- Price changes
- Expired listings
- Market activity
- Hiring or expansion
- Local development news

Scoring ideas:

- Market fit
- Transaction timing
- Asset type
- Urgency signal
- Contactability

Outreach angle:

- Listing marketing audit
- Buyer/seller lead follow-up
- Local market content
- Investor pipeline support

## Professional Services Module

Typical focus:

- Consultants
- Accountants
- Law firms
- Agencies
- IT services
- Fractional executives

Signals:

- Hiring
- Funding
- New office
- Leadership changes
- Technology adoption
- Content activity

Scoring ideas:

- Role fit
- Company stage
- Trigger event
- Budget likelihood
- Problem clarity

Outreach angle:

- Diagnostic call
- Process audit
- Growth system review
- Executive briefing

## When To Add Code

Add code only after the module documents answer:

- What data is needed?
- Where does it come from?
- How is it normalized?
- How is it scored?
- What notes are written?
- How does a human review and act?

## Stabilization Checklist

- [ ] Module folder created.
- [ ] Required docs completed.
- [ ] Sample source data available.
- [ ] Scoring rules are explainable.
- [ ] Outreach templates require human review.
- [ ] KPIs are defined.
- [ ] Operator workflow is clear.
- [ ] System check still passes.
