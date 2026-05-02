# Workspace Data Cleanup Guide

## Overview

SignalForge uses two data modes:

| Mode | Data Source | Storage |
|------|-------------|---------|
| **Real Mode** | MongoDB (live collections) | Server-side, persisted |
| **Demo Mode** | In-memory synthetic data | Browser `localStorage` only |

This guide covers how to manage **Real Mode** data — specifically legacy records (missing `workspace_slug`) and mock/test records (created during development or testing).

> **Note:** Demo Mode uses browser-only synthetic data. The cleanup script does **not** touch `localStorage`. Demo data is reset via the browser UI or `localStorage.clear()`.

---

## Why Records Need Cleanup

During development and early testing, records were created without `workspace_slug`. These "legacy" records appear when no workspace filter is active ("All Workspaces") but are hidden from workspace-scoped views. Additionally, some records carry `source`, `run_id`, or `company` values that identify them as mock/test artifacts (e.g., `mock`, `gpt_runtime_test`, `contractor_test_campaign`).

**In Real Mode, workspace-filtered views now exclude by default:**
- Records missing `workspace_slug`
- Records with `is_demo=true` or `is_test=true`
- Records with `workspace_slug` in `["demo", "synthetic"]`
- Records whose `source`, `run_id`, `name`, `notes`, or `company` match known mock patterns

To restore visibility of these records, pass `include_legacy=true` or `include_test=true` on any list endpoint.

---

## Script: `scripts/workspace_data_cleanup.py`

### Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Print counts by collection — no changes made |
| `--workspace-slug <slug>` | Scope dry-run stats to a specific workspace |
| `--backfill-default` | Assign `workspace_slug="default"` to all records missing it |
| `--archive-legacy` | Archive (then remove) all records missing `workspace_slug` |
| `--archive-mock` | Archive (then remove) all mock/test/demo records |

> `--archive-legacy` and `--backfill-default` are mutually exclusive.

### Safety

- **No permanent deletion.** Records are copied to `<collection>_archive` with `_archived_at` and `_archive_reason` fields before removal from active collections.
- **No Demo Mode changes.** The script only touches MongoDB. Browser `localStorage` is never affected.

---

## Workflows

### 1. Inspect what needs cleanup

```bash
# See all data across all collections
python scripts/workspace_data_cleanup.py --dry-run

# Scope to a specific workspace
python scripts/workspace_data_cleanup.py --dry-run --workspace-slug austin-contractor-test
```

Output columns:
- **Total** — all records in collection
- **Missing WS** — records with no `workspace_slug`
- **Mock/Test** — records identified by mock/test/demo patterns
- **Real** — records with workspace_slug and no mock indicators

### 2. Backfill legacy records into "default" workspace

Use this when you want to keep legacy records visible under the "default" workspace instead of archiving them:

```bash
# Preview
python scripts/workspace_data_cleanup.py --dry-run --backfill-default

# Apply
python scripts/workspace_data_cleanup.py --backfill-default
```

### 3. Archive legacy records

Use this to permanently remove legacy records from active views (safely archived, not deleted):

```bash
# Preview
python scripts/workspace_data_cleanup.py --dry-run --archive-legacy

# Apply
python scripts/workspace_data_cleanup.py --archive-legacy
```

### 4. Archive mock/test data

Use this to clean up records from automated tests and development runs:

```bash
# Preview
python scripts/workspace_data_cleanup.py --dry-run --archive-mock

# Apply
python scripts/workspace_data_cleanup.py --archive-mock
```

### 5. Archive both legacy and mock in one pass

```bash
python scripts/workspace_data_cleanup.py --archive-legacy --archive-mock
```

---

## Mock/Test Detection Patterns

The script identifies mock/test/demo records by checking these fields:
- `source`, `source_label`, `run_id`, `name`, `notes`, `company`, `company_name`

Against these patterns (case-insensitive):
- `mock`, `demo`, `synthetic`, `test`, `sample`
- `contractor_test_campaign`
- `module-v<N>` (e.g., `module-v2-test-*`)
- `module<N>-test-*`
- `gpt_runtime_test`
- `manual_contractor_test_cli`
- `tool_layer_review`

Also flags: `is_demo=true`, `is_test=true` on any record.

---

## API: `include_legacy` and `include_test`

All list endpoints accept these query params when a `workspace_slug` is active:

| Param | Default | Effect |
|-------|---------|--------|
| `include_legacy=true` | `false` | Include records missing `workspace_slug` |
| `include_test=true` | `false` | Include mock/test/demo records |

**Examples:**
```bash
# Default — excludes legacy and test data
GET /contacts?workspace_slug=austin-contractor-test

# Include legacy records in results
GET /contacts?workspace_slug=austin-contractor-test&include_legacy=true

# Include both
GET /messages?workspace_slug=austin-contractor-test&include_legacy=true&include_test=true
```

> When no `workspace_slug` is specified (All Workspaces view), all records are returned — `include_legacy` and `include_test` have no effect.

---

## Collections Managed

The cleanup script inspects and operates on these MongoDB collections:

- `contacts`
- `leads`
- `companies`
- `scraped_candidates`
- `tool_runs`
- `message_drafts`
- `approval_requests`
- `agent_tasks`
- `agent_runs`
- `deals`

Archive targets: `contacts_archive`, `leads_archive`, etc.

---

## Running Inside Docker

```bash
# Connect to the API container where pymongo is available
docker compose exec api python /app/scripts/workspace_data_cleanup.py --dry-run

# Or set MONGO_URI explicitly
MONGO_URI=mongodb://mongo:27017 python scripts/workspace_data_cleanup.py --dry-run
```

---

## Dashboard Empty State

When a specific workspace is selected in Real Mode and that workspace has zero contacts/leads, the Campaign CRM page displays:

> **"This workspace is clean. Import candidates or contacts to begin."**

This confirms workspace isolation is working — no legacy or cross-workspace data is leaking into the view.
