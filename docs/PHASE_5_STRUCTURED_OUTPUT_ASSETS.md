# Phase 5 — Structured Output Assets
## Architecture Discovery & Implementation Plan

**Status:** Discovery — Do Not Implement  
**Date:** May 2026  
**Scope:** Backend schema · Collection design · Agent refactor strategy · Frontend component architecture · Migration plan  

---

## Table of Contents

1. [Current Architecture Audit](#1-current-architecture-audit)
2. [Gap Analysis](#2-gap-analysis)
3. [Proposed Output Asset Architecture](#3-proposed-output-asset-architecture)
4. [Collection Strategy](#4-collection-strategy)
5. [Asset Lifecycle Design](#5-asset-lifecycle-design)
6. [Step Mapping Redesign](#6-step-mapping-redesign)
7. [UI Component Architecture](#7-ui-component-architecture)
8. [Migration Strategy](#8-migration-strategy)
9. [Agent Refactor Strategy](#9-agent-refactor-strategy)
10. [Safe Initial Scope](#10-safe-initial-scope)
11. [Risks](#11-risks)
12. [Validation Plan](#12-validation-plan)
13. [Rollback Plan](#13-rollback-plan)

---

## 1. Current Architecture Audit

### 1.1 How Approval Requests Are Generated

The flow is exclusively rooted in `BaseAgent.run()` (agents/base_agent.py):

```
BaseAgent.run()
  → step 1: load_context
  → step 2: read_mongo_records (fetch_leads, fetch_contacts, fetch_message_drafts)
  → step 3: plan_actions()        ← agent subclass implements this
  → step 4: create_approval_requests()  ← every action → approval_request doc
  → step 5: write_outputs (vault log + agent_artifacts)
```

`create_approval_requests()` (base_agent.py ~line 357) iterates every planned action and inserts one `approval_request` document per action with schema:

```python
{
  "run_id":              str,   # links back to agent_run
  "agent_name":          str,
  "module":              str,
  "request_type":        "planned_action_review" | "message_review" | "gpt_*",
  "status":              "open",
  "title":               str,
  "summary":             str,
  "request_origin":      "agent" | "gpt" | "system" | "test",
  "is_test":             bool,
  "severity":            "needs_review" | "error",
  "user_facing_summary": str,
  "technical_reason":    str,
  "target":              str,   # company name or module name — loose string
  "created_at":          datetime,
  "resolved_at":         None,
  "simulation_only":     True,
  "workspace_slug":      str | None,
}
```

**Critical observation:** There is no `asset_type`, no `body`, no `content`, no structured payload. The entire business deliverable — whether a content idea, script draft, engagement plan, or outreach message — is collapsed into `title` + `summary` strings.

### 1.2 Which Agents Create Approval Requests

| Agent | Class | Module | What It Produces |
|-------|-------|--------|-----------------|
| `outreach` | `OutreachAgent` | contractor_growth, media_growth, etc. | `planned_action_review` per lead; GPT: `message_drafts` records (if confidence ≥ 0.6) or `gpt_message_generation_review` approval |
| `content` | `ContentAgent` | media_growth, artist_growth, etc. | `planned_action_review` per content idea; GPT: vault markdown + `agent_artifacts` + approval if confidence < 0.6 |
| `fan_engagement` | `FanEngagementAgent` | artist_growth (only) | `planned_action_review` fan engagement idea; GPT: vault markdown + artifact |
| `followup` | `FollowupAgent` | all | `planned_action_review` follow-up action per contact |

### 1.3 Existing Schemas / Collections

Complete inventory of all MongoDB collections (from main.py grep):

**Core business records:**
- `contacts` — CRM contacts
- `leads` — prospecting leads
- `deals` — deal/opportunity CRM
- `message_drafts` — outreach message drafts

**Agent observability:**
- `agent_tasks` — queued task specs
- `agent_runs` — run-level telemetry
- `agent_steps` — step-by-step execution log
- `agent_artifacts` — lightweight run outputs (vault_log, planned_actions, gpt content plans)
- `approval_requests` — human review queue (generic)
- `scraped_candidates` — tool-layer research candidates
- `tool_runs` — web search / tool execution logs

**Creative Studio (Social Engine):**
- `content_briefs` — campaign briefs with audience/platform/goal
- `content_drafts` — typed posts: post/caption/carousel/reel_script/ad_copy
- `content_snippets` — scored video/transcript snippet candidates
- `creative_assets` — rendered visual assets (ComfyUI output)
- `creative_tool_runs` — creative pipeline run records
- `transcript_runs` / `transcript_segments` / `content_transcripts` — audio pipeline
- `source_content` / `source_channels` — ingestion pipeline
- `client_profiles` — client identity records for creative engine
- `prompt_generations` / `asset_renders` / `asset_performance_records` — generation telemetry

**Campaign:**
- `campaign_packs` / `campaign_pack_items` / `campaign_exports` / `campaign_reports`

**Other:**
- `workspaces` / `companies` / `manual_publish_logs` / `media_intake_records` / `media_folder_scans` / etc.

### 1.4 Existing Run Linkage

All of these fields link records back to runs:
- `approval_requests.run_id` → `agent_runs.run_id`
- `agent_steps.run_id` → `agent_runs.run_id`
- `agent_artifacts.run_id` → `agent_runs.run_id`
- `agent_tasks.linked_run_id` → `agent_runs.run_id`
- `message_drafts.agent_run_id` → `agent_runs.run_id`
- `content_drafts.agent_run_id` → `agent_runs.run_id`
- `scraped_candidates.linked_agent_run_id` → `agent_runs.run_id`

### 1.5 Existing Review Workflow

**approval_requests:** 4 decisions via `POST /approval-requests/{id}/decision`:
- `approve` → status = "approved"
- `reject` → status = "rejected"
- `needs_revision` → status = "needs_revision"
- `convert_to_draft` → creates `message_drafts` or `agent_artifacts` record

**message_drafts:** 3 decisions via `POST /messages/{id}/review`:
- `approve` → review_status = "approved", send_status = "not_sent"
- `reject` → review_status = "rejected"
- `revise` → review_status = "needs_revision"

**content_drafts:** 3 decisions via `POST /content-drafts/{id}/review`:
- `approve` / `reject` / `revise`

**content_snippets:** Scored + reviewed via `POST /content-snippets/{id}/review`

### 1.6 Existing Message/Draft Flow

`OutreachAgent.create_gpt_message_draft()` creates a `message_drafts` record when GPT confidence ≥ 0.6. The draft has `review_status: needs_review`, `send_status: not_sent`. This is the closest thing to a structured output asset today — but it only covers outreach messages.

### 1.7 Convert-to-Draft Behavior

`convert_approval_to_draft()` in main.py (line ~855) checks request_type and target_type:
- If it's a GPT message review or contact/lead/message target → creates a `message_drafts` record
- Otherwise → creates an `agent_artifacts` record with `artifact_type: "approval_queue_draft"`

This is the escape valve for turning generic approval records into something usable. Phase 5 inverts this: assets come first, approval records reference them.

---

## 2. Gap Analysis

### 2.1 Why "No Matching Mongo Records Found" Appears

`BaseAgent.no_data_action()` (line ~410) returns this string when `fetch_leads()` returns an empty list. For media_growth specifically:

- `fetch_leads()` queries `leads` collection with `{"module": "media_growth"}`
- No such leads exist in the production database
- The ContentAgent falls through to `ContentAgent.plan_actions()` fallback branch:
  - If no leads AND no contacts → returns `"Create starter content themes"` action
  - That becomes one generic `planned_action_review` approval_request
  - Title: "Create starter content themes", summary: "Use module strategy docs to draft..."

**Result:** Step 4 renders one generic approval card with no real content deliverable. The operator sees an instruction to do something manually, not an artifact to review.

### 2.2 Why Content Discovery Produces Infrastructure/System Reviews

When `ContentAgent.plan_gpt_actions()` runs with low GPT confidence (or GPT disabled), it calls `create_gpt_approval_request()` which inserts a record with `request_origin: "gpt"` and `severity: "error"`. In the approval queue view filter, these match `view = "system"` or `view = "gpt"` and visually render like error/diagnostic records rather than content deliverables.

Even when GPT succeeds, the output is written to a vault markdown file and an `agent_artifacts` record — but the artifact schema only has: `run_id`, `agent_name`, `module`, `artifact_type: "planned_actions"`, `content: {reasoning_summary: str}`. The actual GPT-generated content plan is buried in the vault markdown, never surfaced as a structured record.

### 2.3 Where Business Deliverables Are Missing

| What Should Exist | What Exists Today |
|---|---|
| Content idea card with title, hook, platform, audience target | Generic approval_request with title + summary strings |
| Script draft card with body text, sections, revision history | vault markdown only (not queryable) |
| Video prompt with visual direction, tone, shot list | Not created at all |
| Carousel outline with slides, CTAs | Not created at all |
| Engagement signal with platform, signal type, response recommendation | Generic approval_request |
| Distribution-ready asset with channels, schedule recommendation | Not created at all |
| Production note with instructions, dependencies | agent_artifacts.content (untyped dict) |

The `content_snippets` and `content_drafts` collections from the Social Creative Engine (v2/v3) are the closest existing precedent. They have typed records with review workflows. But they are scoped to the social media pipeline, not the agent workflow pipeline.

**The system has the scaffolding of a creative OS. It just needs a canonical asset layer connecting agents to it.**

---

## 3. Proposed Output Asset Architecture

### 3.1 Canonical Asset Model

**Collection name:** `workflow_assets`

```python
{
  # Identity
  "_id":            ObjectId,
  "asset_id":       str,           # human-readable: "{run_id_short}-{asset_type}-{n}"

  # Context
  "run_id":         str,           # required — links to agent_runs
  "task_id":        str | None,    # optional — links to agent_tasks
  "module":         str,           # "media_growth" | "contractor_growth" | etc.
  "workspace_slug": str | None,
  "profile_id":     str | None,    # e.g. "executive_growth"

  # Classification
  "asset_type":     AssetType,     # see enum below
  "output_category": str,          # "content" | "outreach" | "engagement" | "distribution" | "crm"
  "platform":       str | None,    # "linkedin" | "podcast" | "youtube" | "email" | None
  "format":         str | None,    # "short_form" | "long_form" | "carousel" | "video" | None

  # Content
  "title":          str,           # required
  "summary":        str,           # 1–2 sentence operator-facing summary
  "body":           str | None,    # full text: script body, post copy, engagement script
  "sections":       list[dict] | None,  # structured sections for carousel/script
  "metadata":       dict,          # type-specific payload (see below)

  # Provenance
  "created_by_agent": str,         # "content" | "fan_engagement" | "outreach" | "followup"
  "source_context": dict | None,   # compact snapshot of what triggered this asset

  # Review state
  "approval_state": ApprovalState, # see lifecycle below
  "approval_request_id": str | None,  # backward compat link to approval_requests

  # Flags
  "simulation_only": bool,         # always True in Phase 5A/5B
  "is_test":        bool,
  "is_demo":        bool,

  # Timestamps
  "created_at":     datetime,
  "updated_at":     datetime,
  "reviewed_at":    datetime | None,
  "published_at":   datetime | None,

  # History
  "review_events":  list[ReviewEvent],
  "revision_notes": list[str],
}
```

### 3.2 Asset Type Enum

```python
AssetType = Literal[
  # Content / Media
  "content_idea",         # high-level topic + hook + angle
  "script_draft",         # full narration or interview script
  "carousel_outline",     # slide-by-slide breakdown
  "video_prompt",         # visual direction + shot structure
  "post_copy",            # short-form caption / LinkedIn post / tweet
  "email_draft",          # email outreach or newsletter draft
  "production_note",      # operator instructions, dependencies, checklist

  # Engagement
  "engagement_signal",    # fan/audience signal that warrants a response
  "reply_recommendation", # recommended reply or comment text

  # Distribution
  "distribution_package", # approved + scheduled asset bundle
  "content_calendar_slot", # a specific calendar entry

  # CRM / Growth
  "lead_opportunity",     # enriched prospect or opportunity record
  "investor_target",      # investor-specific prospect
  "candidate_profile",    # recruiting candidate record
  "deal_signal",          # deal advancement trigger

  # Meta
  "agent_research_note",  # raw GPT research output not yet classified
]
```

### 3.3 Metadata by Asset Type

Each asset_type carries a typed `metadata` dict. Examples:

**content_idea:**
```python
{
  "hook_type":       "question" | "bold_statement" | "story" | "stat",
  "estimated_length": "short" | "medium" | "long",
  "target_audience": str,
  "signal_source":   str,    # what data triggered this idea
  "related_lead_id": str | None,
  "related_contact_id": str | None,
}
```

**script_draft:**
```python
{
  "sections":        [{"label": "Intro", "body": str, "duration_seconds": int}],
  "estimated_runtime": int,   # seconds
  "tone":            str,
  "cta":             str,
  "platform":        str,
}
```

**carousel_outline:**
```python
{
  "slide_count":     int,
  "slides":          [{"slide_n": int, "headline": str, "body": str, "visual_note": str}],
  "cta_slide":       str,
}
```

**video_prompt:**
```python
{
  "visual_direction": str,
  "b_roll_suggestions": list[str],
  "on_screen_text":   list[str],
  "music_tone":       str | None,
  "duration_target":  int,    # seconds
}
```

**engagement_signal:**
```python
{
  "signal_type":     "comment" | "dm" | "story_reply" | "tag" | "mention",
  "platform":        str,
  "signal_text":     str | None,
  "recommended_action": str,
  "urgency":         "high" | "normal" | "low",
}
```

**distribution_package:**
```python
{
  "asset_refs":      list[str],     # workflow_asset _ids
  "channels":        list[str],
  "schedule_window": str | None,
  "operator_checklist": list[str],
}
```

### 3.4 ReviewEvent Schema

```python
{
  "decision":     str,         # "approve" | "reject" | "revise" | "queue"
  "note":         str,
  "decided_at":   datetime,
  "source":       "web_dashboard" | "api" | "operator_cli",
}
```

---

## 4. Collection Strategy

### 4.1 Decision: Single `workflow_assets` Collection

**Recommendation: single collection with `asset_type` discriminator.**

**Rationale:**

| Concern | Single Collection | Multiple Collections |
|---|---|---|
| Cross-asset queries (e.g. all assets for a run) | Simple — one query | Requires fan-out across N collections |
| Type-specific queries | Filtered by asset_type index | Natural (per-collection) |
| Schema divergence | Managed via metadata subdoc | Enforced by schema |
| Frontend simplicity | One API endpoint | N endpoints or complex routing |
| Indexing flexibility | Compound indexes on type+state | Per-collection |
| Migration cost | Low — add fields incrementally | High — create/backfill N collections |

**The `metadata` subdocument absorbs type-specific payload without polluting the root schema.** MongoDB's flexible document model makes this idiomatic.

### 4.2 Indexing Strategy

```python
# Primary lookup — all queries start here
{ "run_id": 1, "asset_type": 1, "approval_state": 1 }

# Workflow step 4 rendering
{ "module": 1, "approval_state": 1, "created_at": -1 }

# Profile/workspace scoped views
{ "profile_id": 1, "module": 1, "approval_state": 1 }
{ "workspace_slug": 1, "module": 1, "approval_state": 1 }

# Task linkage
{ "task_id": 1 }

# Agent attribution
{ "created_by_agent": 1, "module": 1 }

# TTL for archived assets (optional, future)
{ "archived_at": 1 }, expireAfterSeconds = 7776000  # 90 days
```

### 4.3 Query Patterns

```python
# Step 4: from this run
db.workflow_assets.find({
  "run_id": current_run_id,
  "approval_state": {"$in": ["needs_review", "generated"]}
})

# Step 4: same profile, other runs
db.workflow_assets.find({
  "module": active_module,
  "run_id": {"$ne": current_run_id},
  "approval_state": {"$in": ["needs_review", "generated"]}
})

# Step 5: approved/publish-ready
db.workflow_assets.find({
  "module": active_module,
  "approval_state": "approved",
  "output_category": {"$in": ["content", "distribution"]}
})

# Step 6: engagement signals
db.workflow_assets.find({
  "module": active_module,
  "asset_type": {"$in": ["engagement_signal", "reply_recommendation"]},
  "approval_state": {"$ne": "archived"}
})
```

### 4.4 Scalability Considerations

- Each agent run produces 5–20 assets. At 10 runs/day per workspace, that's ~100–200 docs/day — trivially small.
- The `metadata` subdoc is unindexed by default. If type-specific queries on metadata become hot, consider sparse indexes on specific metadata paths.
- `body` text can be large (scripts, full drafts). Consider MongoDB's 16MB document limit only for extreme cases. For very long scripts, store body separately in vault markdown and reference the path in `body_path`.
- Cross-workspace queries are gated by `workspace_slug` index — no cross-tenant data leak risk.

---

## 5. Asset Lifecycle Design

### 5.1 State Enum

```
queued
generated
needs_review
approved
rejected
needs_revision
queued_for_distribution
published
archived
```

### 5.2 State Transition Diagram

```
                    ┌─────────┐
         agent task │ queued  │  (optional pre-generation state)
         submitted  └────┬────┘
                         │ agent runs
                         ▼
                   ┌───────────┐
                   │ generated │  agent wrote asset to DB, no human seen it yet
                   └─────┬─────┘
                         │ auto-promote on write (or after run completes)
                         ▼
                  ┌─────────────┐
           ┌──────┤ needs_review ├──────┐
           │      └─────────────┘       │
           │ approve                     │ reject
           ▼                             ▼
       ┌──────────┐               ┌──────────┐
       │ approved │               │ rejected │──── archived (after N days)
       └────┬─────┘               └──────────┘
            │
     ┌──────┴───────┐
     │ revise       │ needs_revision
     │ decision     ├───────────────────► needs_review (re-enters queue)
     └──────┬───────┘
            │ queue for send/publish
            ▼
  ┌──────────────────────────┐
  │ queued_for_distribution  │  operator-confirmed, awaiting manual send
  └──────────┬───────────────┘
             │ operator logs manual send
             ▼
         ┌───────────┐
         │ published │──────────────────► archived (after N days)
         └───────────┘
```

### 5.3 Transition Rules

| From | To | Trigger | Who |
|---|---|---|---|
| queued | generated | agent writes asset record | system |
| generated | needs_review | run completes | system auto |
| needs_review | approved | operator approves | operator |
| needs_review | rejected | operator rejects | operator |
| needs_review | needs_revision | operator requests revision | operator |
| needs_revision | needs_review | operator re-submits or agent revises | operator / agent |
| approved | queued_for_distribution | operator queues for send | operator |
| queued_for_distribution | published | operator logs manual send | operator |
| approved / published | archived | TTL or explicit operator action | system / operator |
| any | archived | operator explicit archive | operator |

### 5.4 Backward Compatibility with approval_requests

During Phase 5A and 5B:
- Every asset written also creates (or updates) a linked `approval_request`
- `approval_requests.status` maps: `needs_review` ↔ `open`, `approved` ↔ `approved`
- `workflow_assets.approval_request_id` stores the backward link
- Frontend reads from `workflow_assets` for asset-native views
- Frontend falls back to `approval_requests` for all legacy + non-asset records

---

## 6. Step Mapping Redesign

### Current Step Purpose Map

| Step | Current Content | Problem |
|---|---|---|
| 1 | System/profile selection | ✓ Working |
| 2 | Run card selection (8 profiles × N cards) | ✓ Working |
| 3 | Live execution telemetry | Shows "waiting_for_approval" state only |
| 4 | Generic approval queue (approval_requests) | No structured assets |
| 5 | Approved messages (message_drafts) | Only outreach messages |
| 6 | Audience signals (deals as signals) | No engagement assets |
| 7 | Deals/CRM | ✓ Working but thin |

### Phase 5 Step Mapping

**Step 2 — Run Selection (unchanged)**
- Same as today: profile-specific run cards
- Each card maps to a specific agent + task_type that will produce typed assets
- The card description should hint at what assets the run produces: "Produces: content_idea, script_draft"

**Step 3 — Live Execution Telemetry**
```
Renders:
- Active agent run progress (agent_steps)
- "Assets generated so far: N" counter
- Run status: running / waiting_for_review / completed
- Any errors surfaced as system alerts
- Does NOT render asset content yet (that's Step 4)
```

**Step 4 — Structured Asset Review**
```
Renders (replacing approval_requests):
- workflow_assets WHERE approval_state IN [generated, needs_review, needs_revision]
- Grouped by asset_type: ContentIdeaCard, ScriptDraftCard, VideoPromptCard, etc.
- Current run first
- Same-profile other runs (collapsed)
- All backlog (collapsed, cross-module)

Actions:
- Approve → approval_state = "approved"
- Reject → approval_state = "rejected"
- Request revision → approval_state = "needs_revision" + note
- Queue for distribution → approval_state = "queued_for_distribution"
```

**Step 5 — Approved / Publish-Ready Assets**
```
Renders:
- workflow_assets WHERE approval_state IN [approved, queued_for_distribution]
- Sorted by output_category then asset_type
- Shows "Queue for distribution" action on approved items
- Shows operator checklist for distribution_package assets
```

**Step 6 — Audience Signals & Engagement Outcomes**
```
Renders:
- workflow_assets WHERE asset_type IN [engagement_signal, reply_recommendation]
- Any inbound signal records (future: real platform signals)
- Response recommendations ready for operator action
```

**Step 7 — Monetization / CRM**
```
Renders:
- deals (unchanged)
- workflow_assets WHERE asset_type IN [lead_opportunity, investor_target, candidate_profile, deal_signal]
- Conversion actions: convert to CRM contact, convert to lead
```

---

## 7. UI Component Architecture

### 7.1 Base Card Props Interface

All asset cards share a base props interface:

```typescript
interface WorkflowAssetCardProps {
  asset: WorkflowAsset;
  onApprove: (id: string, note: string) => Promise<void>;
  onReject: (id: string, note: string) => Promise<void>;
  onRevise: (id: string, note: string) => Promise<void>;
  onQueue?: (id: string) => Promise<void>;
  busyId: string | null;
  notes: Record<string, string>;
  onNoteChange: (id: string, value: string) => void;
}
```

### 7.2 Component Inventory

---

**`ContentIdeaCard`**
- Layout: title (large), hook type badge, summary, platform badge, signal source line
- Body: collapsible full content if present
- Actions: Approve · Revise · Reject · Queue for Distribution
- Extra: "Generate script from this idea" action (future Phase 5C)
- Color: slate/blue border

---

**`ScriptDraftCard`**
- Layout: title, estimated runtime badge, platform badge, tone chip
- Body: sections accordion (Intro / Body / CTA), each section expandable
- Actions: Approve · Request Revision · Reject
- Extra: character count, copy-to-clipboard button
- Color: slate/violet border

---

**`CarouselOutlineCard`**
- Layout: title, slide count badge, platform chip
- Body: numbered slide list — headline + body + visual note per slide
- Actions: Approve · Request Revision · Reject
- Extra: "Export as brief" action (future)
- Color: slate/indigo border

---

**`VideoPromptCard`**
- Layout: title, duration_target badge, tone chip
- Body: visual_direction block, b_roll list, on_screen_text list, music_tone line
- Actions: Approve · Request Revision · Reject
- Extra: "Send to Creative Engine" (future)
- Color: slate/purple border

---

**`EngagementSignalCard`**
- Layout: platform badge, signal_type badge, urgency badge (red/amber/green)
- Body: signal_text quote block, recommended_action text
- Actions: Approve (mark handled) · Dismiss · Create reply draft
- Color: amber/orange border

---

**`ReplyRecommendationCard`**
- Layout: target context line, platform badge
- Body: recommended reply text (editable inline)
- Actions: Approve · Revise · Dismiss
- Color: amber/yellow border

---

**`ProductionNoteCard`**
- Layout: title, checklist items
- Body: full note text
- Actions: Acknowledge · Archive
- Color: slate/gray border — de-emphasized

---

**`DistributionAssetCard`**
- Layout: title, channel badges, schedule_window chip
- Body: operator_checklist with checkboxes
- Actions: Mark as sent · Archive
- Color: green border (publish-ready state)

---

**`LeadOpportunityCard`** / **`InvestorTargetCard`** / **`CandidateProfileCard`**
- Layout: name/company, confidence score badge, source line
- Body: summary
- Actions: Convert to Contact · Convert to Lead · Reject
- Color: blue/teal border

---

### 7.3 AssetReviewSection (Aggregate Component)

Replaces the current `<div>` + articles pattern in WorkflowPage Step 4.

```
<AssetReviewSection
  assets={currentRunAssets}
  sectionTitle="From this run"
  groupByType={true}
  onDecision={handleAssetDecision}
/>
```

Internally groups assets by `output_category`, then renders the appropriate typed card for each `asset_type`.

**Grouping order:**
1. needs_revision (flagged — highest priority)
2. generated / needs_review grouped by output_category:
   - "content" → ContentIdeaCard, ScriptDraftCard, CarouselOutlineCard, VideoPromptCard
   - "engagement" → EngagementSignalCard, ReplyRecommendationCard
   - "distribution" → DistributionAssetCard
   - "crm" → LeadOpportunityCard, InvestorTargetCard, CandidateProfileCard
   - "meta" → ProductionNoteCard (collapsed by default)

### 7.4 Fallback Behavior (Phase 5A/5B)

When `workflow_assets` returns 0 records for a run, the section falls back to rendering `approval_requests` using the existing approval card (current Step 4 behavior). This is a simple conditional:

```jsx
{assets.length > 0
  ? <AssetReviewSection assets={assets} ... />
  : <ApprovalRequestSection approvals={currentRunApprovals} ... />
}
```

---

## 8. Migration Strategy

### 8.1 Phase 5A — Coexistence (Zero Breaking Changes)

**What changes:**
- Add `workflow_assets` collection to MongoDB (no migration, just a new collection)
- Add `POST /workflow-assets` and `GET /workflow-assets` endpoints to main.py
- Add `PATCH /workflow-assets/{id}/decision` endpoint
- Add `api.workflowAssets()` and `api.decideWorkflowAsset()` to api.js
- Add `workflow_assets` field to `agentRunDetail` response
- ContentAgent (media_growth only) writes `content_idea` assets alongside its existing approval_request output
- Frontend Step 4: if `workflow_assets` exist for current run, show AssetReviewSection; otherwise show existing approval cards

**What does NOT change:**
- `create_approval_requests()` in base_agent.py — untouched
- All existing approval_request endpoints — untouched
- WorkflowPage.jsx sections for Same-profile other runs / All backlog — still use approval_requests
- All existing data — no backfill, no migration

**Backward compatibility guarantee:** Removing or disabling the workflow_assets endpoints returns Step 4 to exactly its current behavior.

---

### 8.2 Phase 5B — Approval Requests Wrap Asset References

**What changes:**
- `create_approval_requests()` gains an optional `asset_id` field
- When an agent creates an asset AND an approval_request, the AR stores `workflow_asset_id: str`
- `enrich_approval_requests()` in main.py optionally fetches and embeds the linked asset
- Frontend approval card shows "View asset" link when `workflow_asset_id` is present
- `convert_to_draft` decision on an approval_request that has a linked asset: promotes the asset to `queued_for_distribution` instead of creating a new `agent_artifacts` record

**Invariant:** All existing records with no `workflow_asset_id` continue to render identically.

---

### 8.3 Phase 5C — Step 4 Fully Asset-Native

**What changes:**
- All agents write workflow_assets as primary output
- `approval_requests` are generated as a derived/notification record from assets (not the source of truth)
- Step 4 frontend always uses `AssetReviewSection`
- `approval_requests` collection kept but treated as audit log only
- Same-profile other runs and All backlog sections also read from `workflow_assets` (with `module` filter) instead of `approval_requests`

**This is the end state of the migration. Phase 5C is a complete paradigm shift and should only be executed once Phase 5B has been validated across all five profiles.**

---

## 9. Agent Refactor Strategy

### 9.1 Where Asset Creation Occurs

Assets are created **directly by agent subclasses**, not by a pipeline transformer layer. This keeps the existing `BaseAgent.run()` orchestration intact and avoids introducing a new middleware layer.

The refactor path:

```python
# Today (base_agent.py)
def create_approval_requests(self, db, run_id, actions) → list[str]:
    # inserts approval_request per action

# Phase 5A addition (base_agent.py)
def create_workflow_assets(self, db, run_id, assets_data) → list[str]:
    # inserts workflow_asset per structured output
    # optionally creates linked approval_request
```

Subclasses call `create_workflow_assets()` in addition to (5A) or instead of (5C) `create_approval_requests()`.

### 9.2 Agent → Asset Type Mapping

**Executive Growth Engine (profile: `executive_growth`, module: `media_growth`)**

| Run Card | Agent | Asset Types Produced |
|---|---|---|
| Content Discovery Run | `content` | `content_idea` (×N), `agent_research_note` |
| Content Asset Creation Run | `content` | `script_draft`, `carousel_outline`, `video_prompt` |
| Fan/Audience Engagement Run | `fan_engagement` | `engagement_signal`, `reply_recommendation` |
| Outreach / Partnership Run | `outreach` | `lead_opportunity`, `email_draft` |

---

**Contractor Growth (profile: `contractor_growth`, module: `contractor_growth`)**

| Run Card | Agent | Asset Types Produced |
|---|---|---|
| Lead Research Run | `outreach` | `lead_opportunity` (×N) |
| Outreach Draft Run | `outreach` | `email_draft` (×N) |
| Follow-up Run | `followup` | `email_draft` (follow-up variant) |
| Content Run | `content` | `post_copy`, `content_idea` |

---

**Creator Monetization (profile: `creator_monetization`, module: `artist_growth`)**

| Run Card | Agent | Asset Types Produced |
|---|---|---|
| Fan Engagement Run | `fan_engagement` | `engagement_signal`, `reply_recommendation`, `content_idea` |
| Content Run | `content` | `script_draft`, `video_prompt`, `carousel_outline` |
| Monetization Signal Run | `outreach` | `lead_opportunity`, `deal_signal` |

---

**Investor Outreach (profile: `investor_outreach`, module: `insurance_growth`)**

| Run Card | Agent | Asset Types Produced |
|---|---|---|
| Prospect Research Run | `outreach` | `investor_target` (×N) |
| Outreach Draft Run | `outreach` | `email_draft` (investor variant) |
| Content Run | `content` | `post_copy`, `content_idea` |

---

**Recruiting Pipeline (profile: `recruiting_pipeline`, module: `contractor_growth`)**

| Run Card | Agent | Asset Types Produced |
|---|---|---|
| Candidate Research Run | `outreach` | `candidate_profile` (×N) |
| Outreach Draft Run | `outreach` | `email_draft` (recruiting variant) |
| Follow-up Run | `followup` | `email_draft` (follow-up) |

---

### 9.3 Asset vs. Approval Request Decision Logic

```python
def should_emit_asset(self, action: dict, context: dict) -> bool:
    """
    Emit a workflow_asset when:
    - GPT produced structured content (confidence >= threshold)
    - The output has a clear business type (content idea, script, etc.)
    - The action is a deliverable, not an infrastructure decision

    Emit an approval_request when:
    - GPT confidence below threshold (error/review needed)
    - Infrastructure/system decisions (module mismatch, no data, config issue)
    - The action has no structured body (just a recommendation string)
    """
    if action.get("is_infrastructure") or action.get("is_system_error"):
        return False  # → approval_request only
    if action.get("asset_type") and action.get("body"):
        return True   # → workflow_asset (+ optional linked approval_request)
    return False      # → approval_request (fallback, current behavior)
```

### 9.4 BaseAgent Extension Points

```python
class BaseAgent:
    # NEW: subclasses override to declare what asset types they produce
    def asset_types_for_module(self) -> list[str]:
        return []

    # NEW: called after plan_actions(), before create_approval_requests()
    def create_workflow_assets(self, db, run_id, actions) -> list[str]:
        return []  # default: no assets (backward compatible)
```

---

## 10. Safe Initial Scope

### 10.1 Recommendation: Executive Growth + Content Discovery Run Only

**Phase 5A-slice-1:** A single agent × single module × two asset types.

```
Target:
  profile:    executive_growth
  module:     media_growth
  agent:      content
  task card:  "Content Discovery Run"
  assets:     content_idea, agent_research_note

Scope:
  1. Add workflow_assets collection (no schema enforcement in Mongo — flexible)
  2. Add GET /workflow-assets endpoint (query by run_id, module, approval_state)
  3. Add PATCH /workflow-assets/{id}/decision endpoint
  4. Modify ContentAgent.plan_actions() for media_growth:
     - After planning actions, call create_workflow_assets() with content_idea records
     - Existing approval_request creation unchanged
  5. Add api.workflowAssets() to api.js
  6. WorkflowPage.jsx Step 4:
     - Load workflow_assets for current run alongside approval_requests
     - If assets exist: render ContentIdeaCard components
     - If no assets: render existing approval cards (unchanged)
```

**Why this slice:**
- **Lowest risk:** ContentAgent already has GPT content plan logic. Converting its output to a structured asset is a narrow change.
- **Most visible:** The content_idea is the most obviously "wrong" deliverable today — operators see "Create starter content themes" instead of actual ideas.
- **No outreach side effects:** Content assets have no send/outreach pathway. Approving a content_idea does nothing downstream except set approval_state. Zero risk of unintended outreach.
- **Validates the full asset lifecycle:** queued → generated → needs_review → approved → queued_for_distribution — all without touching outreach, deals, or CRM.
- **Isolated profile:** media_growth data is isolated. Regression impact is limited to EGE view only.
- **Existing fallback:** If the asset write fails, the existing approval_request is still created. Step 4 degrades gracefully.

**Validating success:**
- Run Content Discovery Run from EGE profile
- Step 3 shows run telemetry
- Step 4 renders ≥1 ContentIdeaCard with title, hook, body
- Approve button → `approval_state = "approved"` → card leaves Step 4
- Card appears in Step 5 (approved assets)
- Existing approval_requests still visible as fallback if assets = 0

---

## 11. Risks

### 11.1 Schema Sprawl
**Risk:** 14 asset types × 5 profiles = 70 potential type×profile combinations. Each adds metadata variations.  
**Mitigation:** The `metadata` subdoc absorbs variation without polluting root schema. Enforce `asset_type` enum server-side. Audit new types at design time (require new entry in AssetType enum).

### 11.2 Over-Generic Abstraction
**Risk:** `workflow_assets` becomes a dumping ground for anything, losing meaning. "content_idea" and "infrastructure_note" both become assets.  
**Mitigation:** Keep the `is_infrastructure` / `is_system_error` routing rule (section 9.3). Infrastructure decisions stay in `approval_requests`. Assets must have a `body` or `sections` — no empty-body assets.

### 11.3 Frontend Complexity
**Risk:** 14 card types × review actions × state management = large component surface area.  
**Mitigation:** All cards share the same `WorkflowAssetCardProps` interface. The `AssetReviewSection` handles routing to the correct card component. Only 4–5 card types are needed for Phase 5A/5B.

### 11.4 Migration Complexity
**Risk:** Phase 5C requires every agent to emit assets. A partial rollout leaves the queue inconsistent.  
**Mitigation:** Strict phase gating. 5A → 5B → 5C. Each phase is independently deployable and independently revertible. No agent is fully migrated until the phase is validated.

### 11.5 Review-State Duplication
**Risk:** `approval_requests.status` and `workflow_assets.approval_state` can diverge. Approving an asset doesn't automatically resolve the linked approval_request.  
**Mitigation:** In Phase 5B, the `PATCH /workflow-assets/{id}/decision` endpoint always updates both records atomically. In Phase 5C, approval_requests become derived (written from assets) — no duplication.

### 11.6 Asset Approval Drift
**Risk:** An operator approves a content_idea but never returns to queue it for distribution. Assets stagnate in "approved" state.  
**Mitigation:** Step 5 renders all approved assets with a clear "Queue for distribution" CTA. Future: staleness indicator on assets approved >7 days ago.

### 11.7 Queue Consistency
**Risk:** Step 5 (queued_for_distribution) reads from two sources during transition: `workflow_assets` and `message_drafts`.  
**Mitigation:** During Phase 5A/5B, Step 5 continues to read only `message_drafts`. Workflow assets in `queued_for_distribution` state are shown as a separate sub-section, clearly labeled. No merge until Phase 5C.

### 11.8 Scaling Concerns
**Risk:** `workflow_assets` grows unboundedly. Old runs accumulate hundreds of asset records.  
**Mitigation:** TTL index on `archived_at` (90 days). `approval_state = "archived"` is set automatically on rejected/published records after a configurable window. Operator can also manually archive. Query patterns always filter by `approval_state` first (indexed).

### 11.9 GPT Content Quality
**Risk:** If GPT confidence is low (as it often is with `gpt-4o-mini`), the asset body will be generic or empty — worse than no asset.  
**Mitigation:** Only create a `workflow_asset` when GPT returns `used_gpt: True AND confidence >= 0.6`. Below threshold: emit approval_request only (current behavior). The threshold is already implemented in all three agent subclasses.

### 11.10 Demo Mode
**Risk:** `isDemoModeEnabled()` routes many api calls to `demoMode.js` synthetic data. New `api.workflowAssets()` calls will return 404 in demo mode if not handled.  
**Mitigation:** Add demo data stubs to demoMode.js for `workflow_assets`. These are already established patterns in the codebase for every other collection.

---

## 12. Validation Plan

### 12.1 Phase 5A Validation Checklist

**Backend:**
- [ ] `GET /workflow-assets?run_id=X` returns correctly shaped documents
- [ ] `GET /workflow-assets?module=media_growth&approval_state=needs_review` returns module-scoped results
- [ ] `PATCH /workflow-assets/{id}/decision` with `approve` sets `approval_state = approved`
- [ ] `PATCH /workflow-assets/{id}/decision` with `reject` sets `approval_state = rejected`
- [ ] `PATCH /workflow-assets/{id}/decision` with `revise` sets `approval_state = needs_revision` and appends note
- [ ] Decision endpoint is idempotent (repeated approve → no error)
- [ ] ContentAgent for media_growth creates ≥1 `content_idea` asset per run when GPT enabled
- [ ] ContentAgent still creates approval_requests (Phase 5A coexistence confirmed)
- [ ] workflow_asset has correct `run_id`, `module`, `created_by_agent`, `title`, `body`
- [ ] No `workflow_asset` created when GPT confidence < 0.6
- [ ] `agent_run_detail` response includes `workflow_assets` array

**Frontend:**
- [ ] EGE profile, run Content Discovery Run → Step 4 renders ContentIdeaCard(s)
- [ ] ContentIdeaCard shows: title, summary, hook_type badge, signal_source
- [ ] Approve button → card leaves Step 4 → appears in Step 5
- [ ] Reject button → card leaves Step 4 → does not appear in Step 5
- [ ] Revise button → `approval_state = needs_revision` → card stays in Step 4 with revision badge
- [ ] If workflow_assets = 0, Step 4 renders approval_requests (fallback)
- [ ] No console errors with either assets or approval_requests rendering
- [ ] Same-profile other runs / All backlog sections (approval_requests tier) unchanged
- [ ] Contractor Growth profile: no workflow_assets changes, Step 4 unchanged
- [ ] Demo mode: no crashes, demo data stubs return gracefully

### 12.2 End-to-End Scenario Test

1. Reset to fresh EGE state (Step 1 active)
2. Open Step 2 → select "Content Discovery Run" → run agent task
3. Step 3 → confirm run completes with `waiting_for_approval` status
4. Step 4 → confirm ContentIdeaCard appears with populated title + body
5. Approve one asset → confirm Step 5 shows it
6. Reject one asset → confirm it disappears from both Step 4 and Step 5
7. Request revision on one → confirm it stays in Step 4 with badge
8. Open same page in Contractor Growth profile → confirm Step 4 unchanged (approval_requests)

---

## 13. Rollback Plan

### 13.1 Phase 5A Rollback

The following can be reverted without data loss:

**Backend rollback:**
1. Remove `POST /workflow-assets`, `GET /workflow-assets`, `PATCH /workflow-assets/{id}/decision` from main.py
2. Revert ContentAgent change: remove `create_workflow_assets()` call
3. Deploy to container: `docker cp main.py signalforge-api:/app/main.py`

`workflow_assets` collection data is not deleted — it accumulates but is never read.

**Frontend rollback:**
1. Remove `api.workflowAssets()` from api.js
2. Remove conditional `{assets.length > 0 ? <AssetReviewSection> : <ApprovalRequestSection>}` in WorkflowPage.jsx
3. Step 4 returns exactly to Phase 4E state
4. Deploy: `docker cp WorkflowPage.jsx signalforge-web:/app/src/pages/WorkflowPage.jsx`

**Data impact:** Zero. No existing records are modified. `workflow_assets` documents created during testing remain in DB but are never displayed.

### 13.2 Phase 5B Rollback

More involved because approval_requests now have `workflow_asset_id` fields.

1. Revert `enrich_approval_requests()` change (remove asset lookup)
2. Revert frontend "View asset" link in approval cards
3. The `workflow_asset_id` field on approval_requests is ignored by old code — no null pointer risk

**Data impact:** Zero. Old approval_requests have no `workflow_asset_id`. New ones with the field are read by old code without it — the field is simply ignored.

### 13.3 Phase 5C Rollback

**This phase cannot be rolled back without data impact.** Phase 5C should only be executed once 5A and 5B are fully validated across all five profiles.

If Phase 5C rollback is required:
- Re-enable `create_approval_requests()` in all agents
- Re-generate approval_requests for recent assets via a one-time backfill script
- Switch frontend back to approval_requests as primary source for Step 4

**This is why Phase 5C is the last phase and requires explicit sign-off.**

---

## Appendix A — Payload Examples

### content_idea Asset

```json
{
  "_id": "682bdc3f1234567890abcdef",
  "asset_id": "d185a4ae-content_idea-1",
  "run_id": "d185a4ae-3f2c-4a8b-b1d2-abc123def456",
  "task_id": "682bdc001234567890abcde0",
  "module": "media_growth",
  "workspace_slug": null,
  "profile_id": "executive_growth",
  "asset_type": "content_idea",
  "output_category": "content",
  "platform": "linkedin",
  "format": "short_form",
  "title": "Why Most Media Campaigns Fail Before They Start",
  "summary": "A pattern-based post idea targeting media executives who overfocus on distribution before building audience trust.",
  "body": "Most media campaigns allocate 80% of budget to distribution and 20% to content quality. This is backwards. Here is why the audience-first model consistently outperforms...",
  "sections": null,
  "metadata": {
    "hook_type": "bold_statement",
    "estimated_length": "medium",
    "target_audience": "Media executives, podcast producers, brand strategists",
    "signal_source": "GPT content analysis of media_growth module docs",
    "related_lead_id": null,
    "related_contact_id": null
  },
  "created_by_agent": "content",
  "source_context": {
    "gpt_confidence": 0.82,
    "module_docs_used": ["CONTENT_STRATEGY.md", "AUDIENCE_PERSONAS.md"],
    "leads_analyzed": 0,
    "contacts_analyzed": 3
  },
  "approval_state": "needs_review",
  "approval_request_id": "682bdc0012345678abcdef01",
  "simulation_only": true,
  "is_test": false,
  "is_demo": false,
  "created_at": "2026-05-11T18:26:00Z",
  "updated_at": "2026-05-11T18:26:00Z",
  "reviewed_at": null,
  "published_at": null,
  "review_events": [],
  "revision_notes": []
}
```

### script_draft Asset

```json
{
  "asset_id": "d185a4ae-script_draft-1",
  "run_id": "d185a4ae-3f2c-4a8b-b1d2-abc123def456",
  "module": "media_growth",
  "asset_type": "script_draft",
  "output_category": "content",
  "platform": "podcast",
  "title": "The Audience Trust Framework — Podcast Script Draft",
  "summary": "A 4-minute segment on why media brands lose audience confidence and how to rebuild it.",
  "body": "Full narration text here...",
  "sections": [
    {"label": "Hook", "body": "You have 11 seconds...", "duration_seconds": 30},
    {"label": "Problem", "body": "Most brands distribute before...", "duration_seconds": 60},
    {"label": "Framework", "body": "The three pillars of...", "duration_seconds": 90},
    {"label": "CTA", "body": "If this resonated...", "duration_seconds": 20}
  ],
  "metadata": {
    "estimated_runtime": 200,
    "tone": "authoritative-conversational",
    "cta": "Subscribe for the full framework PDF",
    "platform": "podcast"
  },
  "approval_state": "needs_review"
}
```

### carousel_outline Asset

```json
{
  "asset_id": "d185a4ae-carousel_outline-1",
  "asset_type": "carousel_outline",
  "title": "5 Signs Your Media Strategy Is Broken",
  "metadata": {
    "slide_count": 6,
    "slides": [
      {"slide_n": 1, "headline": "Your metrics look good but revenue is flat", "body": "Vanity metrics trap.", "visual_note": "Red/green split graphic"},
      {"slide_n": 2, "headline": "You're chasing reach, not depth", "body": "Depth-first audiences convert 3× better.", "visual_note": "Funnel illustration"},
      {"slide_n": 6, "headline": "The fix starts with a single question", "body": "What does my audience actually fear?", "visual_note": "Text-only, bold font"}
    ],
    "cta_slide": "DM me 'framework' for the full breakdown"
  },
  "approval_state": "needs_review"
}
```

---

## Appendix B — API Endpoint Design

```
GET    /workflow-assets
       ?run_id=             (filter by run)
       ?module=             (filter by module)
       ?profile_id=         (filter by profile)
       ?workspace_slug=     (filter by workspace)
       ?asset_type=         (filter by type)
       ?approval_state=     (filter by state)
       ?output_category=    (filter by category)
       ?limit=100

GET    /workflow-assets/{asset_id}

PATCH  /workflow-assets/{asset_id}/decision
       Body: { decision: "approve"|"reject"|"revise"|"queue", note: str }

GET    /agent-runs/{run_id}
       Response now includes: workflow_assets: []   (added in Phase 5A)

POST   /workflow-assets           (internal — called by agents, not directly by frontend)
```

---

## Appendix C — Agent Code Sketch (Phase 5A)

```python
# base_agent.py — new method, added alongside existing create_approval_requests()

def create_workflow_assets(
    self,
    db,
    run_id: str,
    asset_data_list: list[dict],
) -> list[str]:
    """
    Insert workflow_asset documents and return their IDs.
    Called by subclasses that produce structured deliverables.
    Does NOT replace create_approval_requests() in Phase 5A.
    """
    if not asset_data_list:
        return []
    now = datetime.now(timezone.utc)
    docs = []
    for index, data in enumerate(asset_data_list, start=1):
        run_short = run_id[:8] if run_id else "unknown"
        asset_type = data.get("asset_type", "agent_research_note")
        docs.append({
            "asset_id":          f"{run_short}-{asset_type}-{index}",
            "run_id":            run_id,
            "task_id":           data.get("task_id"),
            "module":            self.module,
            "workspace_slug":    self.workspace_slug or None,
            "profile_id":        data.get("profile_id"),
            "asset_type":        asset_type,
            "output_category":   data.get("output_category", "content"),
            "platform":          data.get("platform"),
            "format":            data.get("format"),
            "title":             data.get("title", "Untitled asset"),
            "summary":           data.get("summary", ""),
            "body":              data.get("body"),
            "sections":          data.get("sections"),
            "metadata":          data.get("metadata", {}),
            "created_by_agent":  self.agent_name,
            "source_context":    data.get("source_context"),
            "approval_state":    "needs_review",
            "approval_request_id": data.get("approval_request_id"),
            "simulation_only":   True,
            "is_test":           bool(data.get("is_test")),
            "is_demo":           False,
            "created_at":        now,
            "updated_at":        now,
            "reviewed_at":       None,
            "published_at":      None,
            "review_events":     [],
            "revision_notes":    [],
        })
    result = db.workflow_assets.insert_many(docs)
    return [str(inserted_id) for inserted_id in result.inserted_ids]
```

---

*End of Phase 5 Architecture Discovery Document*  
*Next action: Operator reviews and approves Phase 5A-slice-1 scope before implementation begins.*
