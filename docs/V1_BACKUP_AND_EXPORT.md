# SignalForge v1 Backup And Export

SignalForge v1 stores important data in two places:

- MongoDB for structured records.
- `vault/` for human-readable markdown notes.

Back up both. A vault-only backup is readable but incomplete. A Mongo-only backup loses the operator notes.

## What To Back Up

| Item | Why |
| --- | --- |
| MongoDB `signalforge` database | Leads, contacts, message drafts, responses, deals, pipeline runs. |
| `vault/` | Obsidian notes, reports, logs, drafts, review queues, meeting prep, deal notes. |
| `modules/` | Client/module strategy packs. |
| `docs/` | Operator and handoff documentation. |
| `.env.example` | Environment template. |

Do not include `.env` in shared handoff packages unless the recipient is authorized to receive secrets.

## Create Backup Folders

```bash
mkdir -p backups/mongo backups/vault backups/exports
```

## MongoDB Archive Backup

Start the stack first:

```bash
make up
```

Create a compressed MongoDB archive:

```bash
docker compose exec -T mongo mongodump --db signalforge --archive --gzip > backups/mongo/signalforge_$(date +%Y%m%d_%H%M%S).archive.gz
```

Verify the archive exists:

```bash
ls -lh backups/mongo/
```

## MongoDB Restore

Restore only into the intended local environment. This command drops existing records in the restored namespaces.

```bash
docker compose exec -T mongo mongorestore --drop --archive --gzip < backups/mongo/<backup-file>.archive.gz
```

Run checks after restore:

```bash
make check
```

## Vault Backup

Create a compressed vault archive:

```bash
tar -czf backups/vault/signalforge_vault_$(date +%Y%m%d_%H%M%S).tar.gz vault
```

Restore the vault archive into a clean folder before replacing an active vault:

```bash
mkdir -p restore_test
tar -xzf backups/vault/<vault-backup-file>.tar.gz -C restore_test
```

## JSON Collection Exports

Use JSON exports when you need portable snapshots for review or migration. These are not a full replacement for `mongodump`.

```bash
docker compose exec -T mongo mongoexport --db signalforge --collection contacts --jsonArray > backups/exports/contacts.json
docker compose exec -T mongo mongoexport --db signalforge --collection leads --jsonArray > backups/exports/leads.json
docker compose exec -T mongo mongoexport --db signalforge --collection message_drafts --jsonArray > backups/exports/message_drafts.json
docker compose exec -T mongo mongoexport --db signalforge --collection deals --jsonArray > backups/exports/deals.json
docker compose exec -T mongo mongoexport --db signalforge --collection pipeline_runs --jsonArray > backups/exports/pipeline_runs.json
```

If `mongoexport` is unavailable in the local Mongo image, use the archive backup as the source of truth or install MongoDB Database Tools locally.

## Handoff Package

Create a documentation-first handoff package without secrets:

```bash
tar -czf backups/signalforge_v1_handoff_$(date +%Y%m%d_%H%M%S).tar.gz \
  README.md REQUIREMENTS.md ARCHITECTURE.md ROADMAP.md \
  docker-compose.yml .env.example Makefile \
  docs modules agents scripts data/imports vault
```

Before sharing:

- [ ] Confirm `.env` is not included.
- [ ] Confirm private client data is allowed to be included.
- [ ] Confirm the MongoDB archive is stored separately if structured data is required.
- [ ] Confirm the recipient understands SignalForge v1 is local-first and manual-review only.

## Backup Cadence

Recommended cadence:

- Before demos: back up MongoDB and `vault/`.
- Before changing module strategy docs: back up `modules/`.
- Before major operator sessions: run `make check`.
- After closed-won or closed-lost updates: generate `make revenue-report`, then back up.

## Quick Recovery Checklist

1. Clone or unpack the project.
2. Restore `vault/` if needed.
3. Start Docker:

```bash
make up
```

4. Restore MongoDB archive if needed.
5. Run:

```bash
make check
```

6. Open `vault/00_Dashboard.md` in Obsidian.
