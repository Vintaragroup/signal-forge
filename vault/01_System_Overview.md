# System Overview

signalForge connects structured automation with a markdown operating system.

## Core Idea

MongoDB stores queryable records. The vault stores context that humans can read, edit, and trust. Services bridge the two by reading prompts from the vault, processing records, and writing summaries back as markdown.

## Current Services

| Service | Purpose | Writes To |
| --- | --- | --- |
| lead_scraper | Finds lead and company candidates | MongoDB, `vault/leads` |
| lead_enricher | Enriches companies and contacts | MongoDB, `vault/companies` |
| social_processor | Converts social events into signals | MongoDB, `vault/logs` |
| post_generator | Drafts content and outreach | MongoDB, `vault/content` |
| api | Exposes health and status endpoints | HTTP |

## Source Of Truth

- Structured state: MongoDB
- Human review state: Obsidian vault
- Secrets: `.env`
- Service runtime: Docker Compose

## Operating Principle

Automation should create drafts, summaries, and recommendations. Humans approve positioning, outreach, and publishing decisions.
