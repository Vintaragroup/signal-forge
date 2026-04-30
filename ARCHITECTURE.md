# Architecture

## System Diagram

```text
                         +---------------------+
                         |   External Sources  |
                         | LinkedIn / X / Web  |
                         +----------+----------+
                                    |
                                    v
                         +----------+----------+
                         |    lead_scraper     |
                         +----------+----------+
                                    |
                                    v
+------------------+      +---------+---------+      +----------------------+
| Obsidian Vault   |<---->|       MongoDB      |<---->| lead_enricher        |
| /vault markdown  |      | structured records |      | company/contact AI   |
+--------+---------+      +---------+---------+      +----------------------+
         ^                          ^
         |                          |
         |                +---------+----------+
         |                | social_processor   |
         |                +---------+----------+
         |                          |
         |                +---------+----------+
         +----------------| post_generator     |
                          +---------+----------+
                                    |
                                    v
                          +---------+----------+
                          |        api         |
                          +--------------------+
```

## Service Descriptions

### lead_scraper

Collects lead and company candidates from configured sources. The starter implementation prints its role, checks vault access, and verifies Mongo readiness.

### lead_enricher

Transforms raw company and contact data into richer profiles using prompts from the vault. Future versions should write enrichment summaries back to both MongoDB and markdown notes.

### social_processor

Processes social media events into normalized social signals. Future versions should classify urgency, topic, source credibility, and outreach relevance.

### post_generator

Generates draft posts and campaign content from enriched company data, social signals, and prompt templates.

### api

Exposes a small HTTP interface for health checks and system status. This can later become the control plane for pipeline runs, lead lookup, and vault note creation.

### mongo

Stores structured data. The vault remains the human-readable interface; MongoDB remains the queryable operational store.

## Data Flow

1. Lead scraper collects raw lead or company candidates.
2. Raw records are stored in MongoDB.
3. Enrichment service reads raw records and applies AI enrichment prompts.
4. Social processor turns social events into actionable signals.
5. Post generator creates outreach and content drafts.
6. Services write summaries, templates, and logs into `/vault`.
7. API exposes health and operational status.

## Design Notes

- The vault is shared by bind mount, not copied into images.
- Services do not assume MongoDB is immediately ready; they use short readiness checks.
- AI prompts live in markdown so they can be edited directly in Obsidian.
- The initial architecture avoids queues, schedulers, and workers until pipeline load requires them.
