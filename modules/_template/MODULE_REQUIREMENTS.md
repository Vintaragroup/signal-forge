# Module Requirements

## Module Name

- Name:
- Slug:
- Owner:
- Version:
- Last updated:

## Objective

Describe the business outcome this module should produce.

Examples:

- Generate qualified leads for a local service business.
- Identify partnership opportunities for a media company.
- Track fan or venue opportunities for a music artist.
- Create outbound campaigns for professional services.

## Functional Requirements

- Define target audience.
- Define signal sources.
- Normalize leads or opportunities into MongoDB.
- Write human-readable notes into the vault.
- Score leads with explainable rules.
- Create review queue notes.
- Prepare human-approved outreach.
- Track outreach lifecycle.
- Generate operator reports.

## Non-Goals

- No automated outbound without explicit approval.
- No frontend unless specifically scoped.
- No external API integration unless required and documented.
- No hidden lead scoring rules.

## Required Vault Outputs

- Lead or opportunity notes.
- Company, account, or profile notes.
- Review queue notes.
- Outreach notes.
- Follow-up notes.
- Reports.

## Required Mongo Fields

- `module`
- `source`
- `business_type` or `industry`
- `location` or `market`
- `lead_score`
- `priority_reason`
- `recommended_offer`
- `review_status`
- `outreach_status`
- `note_path`

## Acceptance Checklist

- [ ] Module documents are complete.
- [ ] Source data shape is defined.
- [ ] Scoring rules are explainable.
- [ ] Outreach templates are safe for human review.
- [ ] Operator workflow is clear.
- [ ] Report metrics are defined.
