# SignalForge Module Template

Use this folder as the starting point for a new industry, client, or audience module.

A module defines the strategy layer around the SignalForge operating system:

- Who the client serves.
- Which audiences matter.
- Which signals should be collected.
- How leads should be scored.
- What outreach should say.
- What content should be produced.
- How campaigns and KPIs should be tracked.
- How the operator should run the workflow.

This template does not add services or external integrations by itself. Copy it to a new folder, fill in the documents, then decide what code or data changes are actually needed.

## Copy Pattern

```bash
cp -R modules/_template modules/<module_slug>
```

Examples:

- `modules/contractors`
- `modules/insurance`
- `modules/media`
- `modules/music_artists`
- `modules/real_estate`
- `modules/professional_services`

## Required Setup

1. Complete `CLIENT_PROFILE.md`.
2. Define audiences in `AUDIENCE_PERSONAS.md`.
3. Define source strategy in `SIGNAL_SOURCES.md`.
4. Define scoring in `SCORING_RULES.md`.
5. Draft outreach and content patterns.
6. Define campaign and KPI tracking.
7. Write the operating workflow.

## Current Runtime

The stabilized Contractor Lead Engine uses:

- Docker Compose
- MongoDB
- Obsidian vault markdown
- CLI scripts
- Local structured source data

Future modules should preserve this local-first shape unless there is a clear reason to add more.
