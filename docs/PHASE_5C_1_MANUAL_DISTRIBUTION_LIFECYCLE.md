# Phase 5C.1 Manual Distribution Lifecycle

## Purpose

Record the implemented manual distribution lifecycle for approved `workflow_assets`.

This is the Phase 5C.1 source-of-truth for:

- backend distribution state behavior
- Step 5 UI grouping semantics
- allowed and blocked state transitions
- manual-only operator rules
- rebuild and validation commands used to deploy the change

## Scope

This lifecycle applies only to approved `workflow_assets`.

It does not add:

- automated posting
- scheduler jobs
- cron execution
- OAuth or external social API calls
- auto-publish behavior of any kind

SignalForge remains a human-reviewed, manual-distribution workflow.

## Data Model

Phase 5C.1 keeps approval and distribution as separate concerns.

Approval state answers:

- is the content approved for operator use?

Distribution state answers:

- where is that approved content in the manual distribution lifecycle?

### Approval State

Existing approval states remain unchanged:

- `needs_review`
- `approved`
- `rejected`

### Distribution State

Phase 5C.1 distribution states are:

- `not_queued`
- `queued`
- `published`
- `archived`

### Distribution Fields

Implemented additive fields on `workflow_assets`:

- `distribution_state`
- `distribution_channel`
- `distribution_notes`
- `published_at`
- `published_url`

Read-path normalization treats missing legacy fields as:

- `distribution_state = "not_queued"`
- `distribution_channel = null`
- `distribution_notes = null`
- `published_at = null`
- `published_url = null`

## Operator Lifecycle

### 1. Review

The content agent emits `workflow_assets` into Step 4 with:

- `approval_state = needs_review`
- no outbound automation

### 2. Approve

The operator approves the asset in Step 4.

That changes only the approval state:

- `approval_state = approved`

The asset then becomes eligible for Step 5 distribution handling.

### 3. Approved / Not Queued

Approved assets first appear in Step 5 under:

- `Approved / Not Queued`

This means:

- content is approved
- no distribution commitment has been recorded yet
- the operator may add manual channel and notes

### 4. Queue for Distribution

When the operator clicks `Queue for Distribution`, the asset moves to:

- `distribution_state = queued`

This means:

- the operator intends to distribute the asset manually
- SignalForge still does not post or schedule it
- channel and notes are operator metadata only

### 5. Mark Published

When the operator manually publishes outside SignalForge and then clicks `Mark Published`, the asset moves to:

- `distribution_state = published`
- `published_at = <utc timestamp>`
- optional `published_url`

This records a human-confirmed publish outcome only.

### 6. Archive

The operator may archive an asset from active queue handling.

Archive moves the asset to:

- `distribution_state = archived`

Archived assets remain visible in history, but they are removed from active Step 5 queue counts.

## Allowed State Transitions

The distribution route supports these transitions:

- `not_queued -> queued`
- `queued -> not_queued`
- `queued -> published`
- `not_queued -> archived`
- `queued -> archived`
- `published -> archived`

## Blocked State Transitions

The route intentionally blocks:

- any distribution action on non-approved assets
- `published -> queued`
- `published -> not_queued`

In Phase 5C.1, `published` is terminal except for archive.

## API Surface

### Read

`GET /workflow-assets`

Supported distribution-related behavior:

- response normalization for missing legacy distribution fields
- optional `distribution_state` filtering
- `distribution_state=not_queued` includes both explicit `not_queued` assets and legacy records with no saved distribution state

### Update

`PATCH /workflow-assets/{asset_id}/distribution`

Supported actions:

- `queue`
- `unqueue`
- `mark_published`
- `archive`

Notes:

- the route enforces `approval_state == approved`
- channel and notes can be persisted with queue or publish actions
- `published_url` is accepted during publish

## Step 5 UI Grouping

Step 5 is intentionally split into four operator-visible sections.

### Approved / Not Queued

Contains only:

- current-run assets
- `approval_state = approved`
- `distribution_state = not_queued` or missing legacy distribution state

### Queued for Distribution

Contains only:

- current-run assets
- `approval_state = approved`
- `distribution_state = queued`

### Published / Archived

Contains only:

- current-run assets
- `approval_state = approved`
- `distribution_state in {published, archived}`

### Ready to Send Message Drafts

This remains the existing message-draft queue and is unchanged by Phase 5C.1.

## Active Queue Counts

Active Step 5 work counts include:

- approved workflow assets in `not_queued`
- approved workflow assets in `queued`
- approved message drafts with `send_status = not_sent`

Active Step 5 work counts exclude:

- `published` workflow assets
- `archived` workflow assets

## Manual-Only Rules

The UI and route are intentionally constrained.

SignalForge does not:

- post to LinkedIn
- post to Instagram
- post to TikTok
- post to YouTube
- schedule future posts
- trigger external publishing tools

The operator must manually publish outside the system, then optionally return to record:

- channel used
- notes
- published URL
- archive status

## Stabilization Coverage

Phase 5C.1 hardening added automated coverage for:

- distribution endpoint behavior
- allowed and blocked transitions
- legacy `not_queued` normalization behavior
- Step 5 grouping logic
- Step 5 active queue counts excluding published and archived assets

Focused tests added:

- `tests/test_workflow_assets_api.py`
- `services/web/src/__tests__/WorkflowPage.test.jsx`

## Rebuild / Redeploy

The runtime images were rebuilt from source with:

```bash
docker compose up -d --build api web
```

This replaced the earlier temporary manual container sync approach.

## Validation Checklist

Validation completed for the stabilized Phase 5C.1 slice:

- backend health endpoint returned `ok`
- rebuilt API served normalized distribution fields
- rebuilt web runtime rendered Step 5 grouping sections
- focused backend tests passed
- focused frontend Step 5 grouping tests passed

## Out Of Scope

Still out of scope after Phase 5C.1 hardening:

- automated scheduler behavior
- recurring queue processing
- outbound publishing integrations
- analytics ingestion from external platforms
- multi-channel publish orchestration
- unpublish or rollback workflows after published state