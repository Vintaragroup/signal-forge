# Roadmap

## Phase 0: Foundation

- Create project structure.
- Add Docker Compose orchestration.
- Add Python 3.11 service skeletons.
- Add shared Obsidian vault.
- Add basic scripts and documentation.

## Phase 1: Local Data Model

- Define MongoDB document shapes for leads, companies, signals, content, and campaigns.
- Add basic repository helpers for Mongo access.
- Add note creation utilities that keep Mongo records linked to vault paths.
- Add pipeline run logging.

## Phase 2: Lead Collection

- Add source-specific collectors.
- Add deduplication by domain, company name, and contact profile URL.
- Add source attribution.
- Add rate limiting and source compliance notes.

## Phase 3: AI Enrichment

- Load prompts from `vault/prompts`.
- Add company and contact enrichment workers.
- Add confidence scoring.
- Add markdown summary generation.
- Add human review status.

## Phase 4: Social Signals

- Normalize social events.
- Classify signal type, urgency, and buying intent.
- Link signals to leads and companies.
- Generate recommended next actions.

## Phase 5: Outreach And Content

- Generate outreach drafts from enriched records.
- Generate posts from campaign themes and social signals.
- Add approval states.
- Export content drafts from MongoDB to vault notes.

## Phase 6: Operating Layer

- Expand API control plane.
- Add scheduled daily pipeline runs.
- Add dashboard views.
- Add integration tests.
- Add backup and restore guidance.
