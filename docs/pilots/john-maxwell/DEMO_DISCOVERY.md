# John Maxwell Demo Discovery

Date: 2026-05-08
Workspace context: `john-maxwell-pilot`
Status: Discovery complete against current SignalForge repo/runtime surfaces

## Executive Summary

SignalForge can already demonstrate a substantial portion of the John Maxwell story today, but only as a hybrid of:

1. existing Creative Studio and Demo Mode flows
2. the real `john-maxwell-pilot` workspace for proof of the faceless video pipeline
3. new demo-only data and UI layers for distribution, audience engagement, and funnel conversion

The strongest current proof points are:
- source content ingestion and approval
- transcript and snippet generation
- prompt generation and render review
- faceless video rendering, including AnimateDiff text-to-video support
- campaign packs, reports, exports, and advisory intelligence
- browser-only guided demo mode with seeded synthetic data and zero backend writes

The biggest current gaps for the requested John Maxwell executive demo are:
- no real social posting or scheduling system
- no real DM/comment automation engine
- no funnel/onboarding automation layer
- no follower growth or customer journey visualization purpose-built for creator brands
- no auth, account roles, or sandbox tenancy beyond workspace scoping and demo/localStorage isolation

The right MVP is not a new product area. It is a John Maxwell-specific executive tour layered onto the existing Creative Studio + POC Demo architecture, with new demo collections for approved growth accounts, distribution state, engagement triggers, nurture steps, funnel offers, and revenue outcomes.

## 1. Current SignalForge Capabilities

### Dashboard modules that already exist

Current top-level dashboard modules:
- Demo Mode
- Workflow
- Overview
- Pipeline
- Messages
- Approvals
- Agent Tasks
- Agent Console
- Research / Tools
- GPT Diagnostics
- Deals
- Creative Studio
- Reports
- Workspaces

Current Creative Studio sub-areas already visible in-product:
- Clients
- Source Channels
- Source Content
- Snippets
- Assets
- Approval Queue
- Ingest Pipeline
- Prompt Library
- Rendered Assets
- Performance Loop
- Campaign Packs
- Exports
- Intelligence
- Media Ingestion
- Renderer Validation
- POC Demo

### Workflow engine that exists today

Operational workflow/orchestration surfaces already present:
- Agent task queue with statuses like `queued`, `running`, `waiting_for_approval`, `completed`, `failed`
- Agent run timeline and live run panel
- Approval queue for human gating
- Redis-backed render queue with worker processing
- Workspace-scoped record loading across the dashboard
- Guided workflow page for operator-driven runs and approvals

What this means for the demo:
- the system already shows progression and review gates well
- the existing flow is operator-centric, not executive-story-centric
- it can be repackaged into a guided executive walkthrough without inventing a new orchestration layer

### AI content generation systems that are operational

Operational today:
- GPT-gated prompt generation and draft generation
- transcript generation with stub/local provider paths
- deterministic snippet scoring and hook selection
- ComfyUI stub/local rendering
- Comfy Cloud rendering path
- FFmpeg-based video assembly
- Phase 12 AnimateDiff faceless text-to-video workflow support
- renderer validation diagnostics

Important constraint:
- SignalForge does not auto-publish generated content
- all outputs remain review-only and `simulation_only=true`

### Scraping/content ingestion systems that exist

Operational or partially operational today:
- source channel registration and approval
- source content registration and approval
- transcript ingestion pipeline
- media intake records for local file and URL metadata
- media folder scanning for local synced folders
- approved URL download flow via `yt-dlp`
- manual CSV candidate import via Research / Tools
- contractor lead scraper/enricher CLI flows

Current limitation for John Maxwell:
- there is no live creator-platform ingestion/orchestration engine that pulls directly from social platform APIs
- the repo is better positioned for approved-source tracking and local media intake than for live creator growth ingestion

### Automation/orchestration systems that exist

Operational today:
- agent task queue
- approval queue
- worker queue for renders
- manual publish log and performance feedback loop
- campaign pack/report/export packaging
- advisory-only intelligence generation

Not operational today:
- social posting automation
- comment automation
- DM automation
- booking automation
- CRM sync automation
- email/SMS automation

### Analytics and reporting systems that exist

Operational today:
- overview KPIs
- pipeline and revenue reports
- performance loop in Creative Studio
- asset performance records
- creative performance summaries
- campaign reports
- campaign exports
- client intelligence and lead-content correlation analytics

Current limitation:
- analytics are stronger for internal pipeline proof than for a creator-brand audience growth story
- follower, reach, comment-trigger, DM funnel, and customer journey metrics are not first-class entities yet

### Social posting systems that exist

Current state:
- manual publish logs exist
- campaign exports exist
- performance can be logged after manual posting
- SignalForge does not schedule or publish content to social platforms

Conclusion:
- the John Maxwell demo can show distribution planning and distribution outcomes
- it cannot truthfully show live autoposting because that system does not exist

### DM or engagement automation that exists

Current state:
- message drafts, review, manual send logging, and response logging exist for outreach/CRM workflows
- no platform-native comment trigger system exists
- no DM automation engine exists
- no keyword-triggered creator engagement system exists

Conclusion:
- the requested engagement section must be demo-simulated, not presented as an operational production system

### Onboarding/funnel systems that exist

Current state:
- deals pipeline exists
- manual outcomes and reports exist
- campaign exports and intelligence exist
- no dedicated onboarding funnel engine exists
- no offer delivery engine exists
- no booking flow engine exists
- no micro-program enrollment workflow exists

Conclusion:
- funnel conversion must be added as demo-only entities or a lightweight extension of existing data structures

### Database structures that already exist

Confirmed collection families already represented in the UI/API include:
- workspaces
- contacts
- leads
- messages
- deals
- approval_requests
- tool_runs
- scraped_candidates
- agent_tasks
- agent_runs
- content_briefs
- content_drafts
- client_profiles
- source_channels
- source_content
- content_transcripts
- transcript_runs
- transcript_segments
- content_snippets
- creative_assets
- media_intake_records
- audio_extraction_runs
- prompt_generations
- asset_renders
- manual_publish_logs
- asset_performance_records
- creative_performance_summaries
- campaign_packs
- campaign_reports
- campaign_exports
- client_intelligence
- lead_content_correlations
- media_folder_scans
- approved_url_downloads
- renderer_validation_runs

This is enough structure to support the first half of the John Maxwell story without adding a new storage architecture.

### User roles/account systems that exist

Current state:
- no auth
- no RBAC
- no multi-user account model
- no tenant isolation beyond workspace scoping
- single-operator local-first architecture

Conclusion:
- demo accounts can be sandboxed through Demo Mode and workspace-specific seed data
- they cannot be presented as true secure multi-user account environments

## 2. Demo Mode Architecture

### What already exists

Existing demo architecture is already strong:
- Real Mode vs Demo Mode switcher in the header
- Demo Mode runs from browser `localStorage` only
- demo records are seeded in `services/web/src/demoMode.js`
- POC Demo tab provides a guided 13-step walkthrough inside Creative Studio
- progress state is replayable via `getDemoProgress`, `setDemoProgress`, `nextDemoStep`, `prevDemoStep`, `jumpDemoStep`, and `resetDemoProgress`
- demo reads do not call backend fetch APIs
- demo records are isolated from real-mode backend endpoints

### What Demo Mode can support today

Already possible:
- simulated data
- safe sandboxed records
- step-by-step guided progression
- visual replay through CTA buttons into actual dashboard sections
- seeded synthetic analytics
- synthetic performance outcomes
- isolated resettable walkthrough state

### What Demo Mode does not yet support directly

Not yet purpose-built:
- a creator-brand-specific executive story
- a distribution calendar with social account abstractions
- comment/DM trigger visualizations
- funnel enrollment and upsell progression
- follower cohort or audience journey visualizations
- executive KPI landing page for creator growth

### Recommended Demo Architecture

Use a two-layer John Maxwell demo architecture.

Layer A: Executive demo mode
- extend the existing browser-only POC Demo architecture
- add a John Maxwell-specific guided tour with creator-growth language
- keep all engagement, funnel, and revenue outcomes synthetic and sandboxed

Layer B: Technical proof mode
- use the real `john-maxwell-pilot` workspace to show actual approved prompts, renders, and Phase 12 AnimateDiff output
- treat this as proof that the render pipeline is real, while the broader growth engine is still demo-simulated

This is the cleanest way to answer the executive question without overstating current production capability.

## 3. Dashboard Walkthrough Design

## Recommended Executive Narrative

The demo should answer:

> SignalForge discovers content opportunities, turns them into faceless short-form growth assets, routes them through approved brand-safe distribution, simulates scalable engagement and nurture logic, and visualizes how those actions convert into long-term customer and community growth.

### Step 1 — Content Ingestion

Map to existing UI:
- Creative Studio: Clients
- Source Channels
- Source Content
- Ingest Pipeline
- Snippets

What can already be shown:
- approved source channels
- approved source content
- transcript runs and transcript segments
- leadership topic or hook clustering via snippets/themes
- quote/hook extraction via scored snippets
- content categorization through snippet theme and platform-fit fields

What should be added for the John Maxwell demo:
- John Maxwell-specific source channels and source content seed set
- leadership category tags such as `discipline`, `growth`, `leadership`, `purpose`, `communication`, `consistency`
- visual cluster summary card at the top of the Ingest area

### Step 2 — AI Content Creation

Map to existing UI:
- Prompt Library
- Rendered Assets
- Renderer Validation

What can already be shown:
- script/prompt generation review
- negative-prompt safety boundaries
- faceless prompt strategy
- AnimateDiff text-to-video workflow variant
- render status and output type
- content scoring inputs from snippet and performance layers

What should be added:
- explicit short-form script card
- caption/CTA/hashtag cards
- voiceover policy panel showing that cloned voice is disabled and real approved audio is preserved when present
- “why this asset should perform” score explanation widget

### Step 3 — Distribution

Map to existing UI today:
- Campaign Packs
- Exports
- Performance Loop

What can honestly be shown today:
- approved growth account concepts as demo records
- distribution plan by platform/account
- manual publish logging after posting outside SignalForge
- prioritization by performance score

What is missing and should be added as demo-only support:
- distribution queue
- posting calendar
- account roster by theme
- per-account content assignment
- “ready to post” queue state

### Step 4 — Audience Engagement

Current gap:
- this is not an operational system today

Recommended demo-only additions:
- comments inbox demo records
- keyword triggers such as `ACTION`, `GROWTH`, `LEADER`
- DM trigger rules
- automated response preview cards
- lead tagging states
- nurture sequence stage cards

These should be clearly labeled as demo simulation or future automation preview.

### Step 5 — Funnel Conversion

Current gap:
- no operational funnel engine today

Recommended demo-only additions:
- digital package delivery records
- low-ticket offer catalog
- funnel event records
- micro-program enrollment state
- upsell path cards
- booking/conversion milestones

This should be presented as “how SignalForge operationalizes the funnel,” not “this is already connected to a live checkout stack.”

### Step 6 — Analytics & Outcomes

Map to existing UI today:
- Overview
- Reports
- Performance Loop
- Campaign Reports
- Client Intelligence

What can already be shown:
- performance records
- summary recommendations
- campaign reports
- advisory intelligence

What should be added for executive impact:
- follower growth KPI cards
- engagement-rate widgets
- conversion funnel cards
- projected revenue card
- customer journey visualization
- account-level leaderboard
- top-performing leadership theme clusters

## 4. John Maxwell Demo Configuration

## Approved Growth Account Concepts

Recommended demo-only account roster:

Leadership / Motivation
- `@MaxwellDailyGrowth`
- `@LeadWithMaxwell`
- `@DailyLeadershipFuel`
- `@MaxwellMindset`

Career / Professional Growth
- `@MaxwellCareerGrowth`
- `@NextLevelLeadershipDaily`
- `@WinningLeaderDaily`

Personal Growth / Purpose
- `@PurposeDrivenGrowth`
- `@DailyGrowthPrinciples`

## Recommended data model additions for these accounts

Add a demo-only collection such as `growth_accounts` with fields:
- `workspace_slug`
- `handle`
- `theme`
- `platform`
- `status`
- `audience_persona`
- `content_pillars`
- `posting_frequency`
- `simulation_only`
- `outbound_actions_taken`
- `is_demo`

## John Maxwell client configuration

Create or extend the John Maxwell client profile with:
- `workspace_slug: john-maxwell-demo`
- `brand_name: John Maxwell`
- `use_likeness: false`
- `use_voice_clone: false`
- `faceless_only: true`
- `approved_content_types: short_form_video, quote_graphic, carousel, email_teaser`
- `disallowed_content: synthetic voice, talking-head avatar, likeness recreation`
- `primary_offer_ladder`
- `community_goal`

## 5. Demo Funnel Design

## Funnel Journey

### Top of Funnel
- faceless motivational clips
- leadership quote clips
- productivity and growth principle clips
- career advancement clips

### Mid Funnel trigger events
- comment `ACTION`
- comment `GROWTH`
- message `LEADER`

### Offer Layer
- 5-Day Leadership Challenge
- Leadership Momentum Pack
- Confidence Accelerator
- Career Growth Blueprint

### High Ticket Conversion
- coaching
- masterminds
- certifications
- leadership communities
- enterprise/team programs

## Recommended demo-only collections for the funnel

Add:
- `engagement_events`
- `dm_trigger_rules`
- `nurture_sequences`
- `funnel_offers`
- `funnel_contacts`
- `funnel_events`
- `conversion_outcomes`

This is the minimal data model needed to show the requested end-to-end lifecycle without claiming live automation.

## 6. Technical Discovery

### Backend

Already present:
- FastAPI control plane
- MongoDB for structured records
- Redis render queue
- worker-based media processing
- GPT runtime gate and diagnostics
- ComfyUI local/cloud validation and render plumbing
- media intake, transcript, prompt, render, pack, export, intelligence endpoints

Not present:
- vector database
- true workflow engine with branching automation rules for social engagement/funnels
- social platform API integrations
- DM provider integrations
- checkout/enrollment integrations
- calendar/booking integrations

### Frontend

Already present:
- multi-page dashboard shell
- mode switching and banners
- Creative Studio with many pipeline sections
- POC Demo guided walkthrough
- live run panel for agent-step timelines
- KPI cards, tables, filters, status badges

Not present:
- dedicated creator growth landing view
- social distribution calendar
- follower journey map
- funnel stage board
- cohort visualization
- demo replay timeline across all six executive phases

### Data / tenancy

Already present:
- workspace scoping in API/UI
- demo seed system in browser localStorage
- demo reset system
- `is_demo` isolation strategy for synthetic records

Not present:
- secure multi-tenant backend tenancy
- role-based demo sandboxes
- backend-managed seeded demo datasets

## 7. UX Discovery

## What the landing dashboard should show first

For the John Maxwell executive demo, the first screen should not be the current operator workflow tabs. It should be an executive summary panel showing:
- total growth accounts
- active content themes
- clips generated this week
- engagement events captured
- micro-program enrollments
- projected downstream ecosystem revenue

Below that, show a six-phase horizontal progression:
- Discover
- Create
- Distribute
- Engage
- Nurture
- Convert

## KPIs that matter most to executives

Recommended top-row KPI set:
- new followers influenced
- engagement rate
- DM trigger rate
- digital package opt-ins
- micro-program enrollments
- leadership ecosystem conversions
- projected revenue influenced
- cost per acquired engaged lead

## What creates the wow factor

Most important visual moments:
- a content opportunity board that shows themes emerging from ingested leadership content
- a faceless video asset card with AnimateDiff badge and direct video output proof
- a growth account distribution board showing one idea adapted across multiple branded accounts
- a comment-to-DM-to-offer journey animation
- a funnel card that shows top-of-funnel attention becoming low-ticket enrollment and then higher-value ecosystem conversion
- a customer journey view that links source clip → engagement trigger → nurture path → offer conversion

## What should be interactive vs automated

Interactive:
- jumping phase to phase
- opening a real asset render
- viewing synthetic engagement and conversion journeys
- switching between account concepts and audience segments

Automated/simulated:
- progression of counts through the funnel
- account-level growth stats
- comment trigger examples
- nurture sequence progression

## 8. Demo Narrative

## Recommended six-phase story

### Phase 1 — Discover
SignalForge ingests approved leadership content, extracts transcripts, scores key hooks, and identifies which growth themes are most likely to perform.

### Phase 2 — Create
SignalForge turns top hooks into faceless short-form assets, complete with prompts, captions, CTAs, hashtags, and brand-safe render outputs.

### Phase 3 — Distribute
SignalForge routes each asset to the right approved growth account concept, building a managed distribution queue instead of a one-size-fits-all posting stream.

### Phase 4 — Engage
Audience responses trigger comment and DM workflows that tag intent and move users into the right nurture path.

### Phase 5 — Nurture
SignalForge delivers the right lead magnet or micro-program offer based on expressed intent and tracks progression toward deeper brand engagement.

### Phase 6 — Convert
SignalForge visualizes how top-of-funnel engagement turns into paid participation in the broader John Maxwell ecosystem.

## 9. Success Criteria

The demo is successful if an executive can clearly say:
- SignalForge can find and organize growth content opportunities
- SignalForge can scale faceless short-form content creation safely
- SignalForge can coordinate distribution across approved brand growth accounts
- SignalForge can model scalable audience engagement flows
- SignalForge can show how attention becomes enrollment and long-term ecosystem value
- SignalForge is an operating system for audience growth, not just a content generator

## 10. Final Deliverables

## 10.1 Demo workflow architecture

Recommended architecture:
- extend existing Demo Mode seed system
- add John Maxwell-specific demo seed collections
- add a new John Maxwell executive walkthrough component, ideally inside Creative Studio
- reuse existing section tabs as CTA destinations
- use the real `john-maxwell-pilot` workspace only for proof artifacts such as the Phase 12 render

## 10.2 Dashboard wireframe flow

Recommended sequence:
1. Executive Summary
2. Discover Opportunities
3. Create Assets
4. Plan Distribution
5. Simulate Engagement
6. Show Funnel Progression
7. Show Revenue/Community Outcomes
8. Close with real proof artifact and safety boundary

## 10.3 Required backend systems list

Needed for the MVP demo layer:
- demo seed additions for growth accounts
- distribution queue records
- engagement event records
- trigger rule records
- nurture sequence records
- funnel offer records
- funnel outcome records
- aggregated executive KPI endpoint or frontend selector over demo state

## 10.4 Mock/demo data requirements

Need seeded demo data for:
- 9 growth accounts
- 12 to 18 source content records
- 20 to 30 scored snippets
- 8 to 12 prompt generations
- 6 to 10 rendered assets
- 30 to 50 synthetic engagement events
- 12 to 20 funnel contacts
- 4 low-ticket offers
- 3 to 5 high-ticket conversion outcomes
- 6-phase KPI snapshots

## 10.5 UI component requirements

Recommended new components:
- `JohnMaxwellExecutiveDemo.jsx`
- `GrowthAccountsBoard.jsx`
- `DistributionQueueBoard.jsx`
- `EngagementTriggerPanel.jsx`
- `FunnelJourneyBoard.jsx`
- `ExecutiveKpiStrip.jsx`
- `JourneyMapPanel.jsx`

## 10.6 Automation requirements

For MVP demo:
- synthetic only
- localStorage-backed in Demo Mode
- no backend writes required for navigation
- optional synthetic “advance phase” actions

For later real productization:
- social account connectors
- comment event ingestion
- DM automation integrations
- offer delivery integrations
- booking/check-out integrations

## 10.7 Funnel architecture

Recommended stages:
- content view
- engagement signal
- keyword/DM trigger
- digital package delivered
- micro-program accepted
- high-ticket qualified
- ecosystem conversion

## 10.8 Analytics requirements

Required demo analytics:
- by growth account
- by content pillar
- by hook/theme cluster
- by engagement trigger keyword
- by low-ticket offer
- by final ecosystem outcome

## 10.9 Demo script / walkthrough

Recommended operator script:
1. Start on Executive Summary and state the problem
2. Show how opportunities are discovered from approved leadership content
3. Open snippets and prompt strategy
4. Open rendered asset and show faceless video proof
5. Move to distribution board and explain account strategy
6. Show synthetic comment and DM trigger panel
7. Walk the funnel from keyword to micro-program to ecosystem offer
8. End on revenue/community outcome view and safety boundaries

## 10.10 MVP implementation plan

### Phase A — Repackage existing capability
- create John Maxwell demo workspace/config
- seed John Maxwell source channels/content/snippets/prompts/renders
- build executive summary view
- reuse existing Creative Studio tabs as evidence destinations

### Phase B — Add demo-only growth/funnel layers
- add growth account, distribution, engagement, nurture, and conversion demo collections
- add UI boards for each stage
- add synthetic KPI rollups

### Phase C — Polish the executive walkthrough
- create one-click guided tour
- add “proof” links into the real `john-maxwell-pilot` render artifacts
- tighten visual narrative and operator script

## Recommendation

Build the John Maxwell demo as a browser-only executive layer first, not as a real automation engine.

That approach is truthful to the repo’s current state, fastest to implement, safe by default, and still visually powerful. The current system already proves ingestion, AI-assisted creative generation, review-gated rendering, reporting, and advisory intelligence. Distribution, engagement automation, and conversion funneling should be added as clearly labeled demo-simulated layers until the corresponding live systems exist.

## Evidence Used

Primary repo surfaces reviewed for this discovery:
- `README.md`
- `ARCHITECTURE.md`
- `docs/MODES_AND_DEMO_GUIDE.md`
- `docs/CURRENT_CAPABILITY_MATRIX.md`
- `docs/POC_DEMO_SCRIPT.md`
- `docs/pilots/john-maxwell/VIDEO_PLAN_REPORT.md`
- `services/web/src/App.jsx`
- `services/web/src/pages/CreativeStudioPage.jsx`
- `services/web/src/components/PocDemoTab.jsx`
- `services/web/src/demoMode.js`
- `services/web/src/api.js`
- `services/api/main.py`
- `services/api/worker.py`
- `services/api/comfyui_client.py`
- `workflows/comfyui/signalforge_animatediff_faceless_t2v_v1_api.json`
