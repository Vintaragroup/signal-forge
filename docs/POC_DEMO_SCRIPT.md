# SignalForge POC: Demo Script

**Document Type:** Operator walkthrough script for client presentations  
**Version:** v10.2  
**Duration:** ~20–30 minutes for full walkthrough; ~10 minutes for highlight tour  
**Prerequisites:** SignalForge running locally (`docker compose up -d`), browser open at `http://localhost:5174`

---

## Before You Start

1. Open `http://localhost:5174` in a browser
2. Click **Demo Mode** in the header → **Enter Demo Mode**
3. The header turns purple with a "DEMO MODE" banner — confirm this is active
4. Navigate to **Creative Studio** in the main nav
5. Click the **"POC Demo ✦"** tab (last tab in the tab bar)
6. You should see the intro screen: "SignalForge POC Demo — 13-step guided walkthrough"
7. Click **Start Demo →** to begin

**Screenshot reference:** `step_00_intro.png`

---

## Intro Screen (Pre-Step)

**What to say:**
> "Before we walk through the pipeline, notice what's on this screen. We see the full 13-step overview, a list of every synthetic data record that's loaded, and a safety boundary summary. Every bullet you see here — no publishing, no email, no platform API calls — is enforced at the data model level, not just as a UI label."

**Key points to highlight:**
- 8 safety bullet points shown before you even start
- Seeded demo data counts: 3 snippets, 2 renders, 1 campaign pack, 1 intelligence record
- "Client-Safe Demo — All Boundaries Enforced" badge

---

## Step 1: Workspace & Safety

**Screenshot:** `step_01_workspace.png`  
**Click:** Start Demo → (takes you here)

**What to say:**
> "Every operation in SignalForge runs inside a named workspace tied to a client profile. This workspace has defined compliance notes and permission flags. The safety boundary is not a setting — it's a record property. `simulation_only=true` is on every single record in this demo."

**Key talking points:**
- Workspace slug ties all records together
- Client profile stores brand permissions at the record level
- No MongoDB writes happen when you navigate through demo steps
- No external API calls at any point

**What to show:**
- Step 1 card with Shield icon (blue border)
- "Safety Boundaries Active" section listing the three guarantees
- "View Client Profiles →" CTA button

---

## Step 2: Client Setup

**Screenshot:** `step_02_client.png`  
**Click:** Next →

**What to say:**
> "The client profile is where brand permissions live. For this demo client — Apex Roofing — likeness, voice, and avatar permissions are all set to false. That flag flows downstream: prompts cannot use likeness, renders cannot clone voice, and the export records these settings as audit data."

**Key talking points:**
- `likeness_permissions: false`, `voice_permissions: false`, `avatar_permissions: false`
- These are advisory flags — they don't block UI, but they're visible at every step
- Compliance notes and allowed/disallowed content types stored here
- No real client data is stored in demo mode

---

## Step 3: Source Approval

**Screenshot:** `step_03_source_approval.png`  
**Click:** Next →

**What to say:**
> "Nothing gets ingested without explicit operator approval. There are two channels here: a YouTube channel that's been approved for ingestion and reuse, and an Instagram channel that's still pending. The system won't pull any content from the Instagram channel until an operator sets that flag. And to be clear — even for the approved YouTube channel, no downloading or scraping happened during this demo."

**Key talking points:**
- `approved_for_ingestion: true` is operator-set, never auto-approved
- Two channels shown: one approved, one pending — realistic scenario
- Source URLs in demo point to `.invalid` domain — no network calls possible
- This gate exists before any transcript or snippet processing begins

---

## Step 4: Content Intake

**Screenshot:** `step_04_content_intake.png`  
**Click:** Next →

**What to say:**
> "Even after a channel is approved, each individual piece of content gets its own approval record before processing begins. These two source content records have been approved — you can see the view counts from the metadata, 8.2K and 3.9K. In a real operation, the operator would review each video and confirm it's suitable before triggering transcript processing."

**Key talking points:**
- Source content approval is separate from channel approval
- URL metadata only in demo — no media files downloaded
- Two records shown with view counts and approval status

---

## Step 5: Transcript & Snippets

**Screenshot:** `step_05_transcript.png`  
**Click:** Next →

**What to say:**
> "Once source content is approved, the transcript run breaks the audio into timestamped segments. This runs locally via FFmpeg — no cloud audio processing, no third-party transcription API. From the transcript, four snippets were generated, each with a score between 0 and 1. `simulation_only=true` is on the transcript run record itself."

**Key talking points:**
- FFmpeg runs locally — audio never leaves the machine
- 4 segments from demo-transcript-run-1
- Snippet scores: 0.94, 0.88, 0.81, 0.76
- Timestamped segments allow precise hook identification

---

## Step 6: Scoring & Hook Selection

**Screenshot:** `step_06_scoring.png`  
**Click:** Next →

**What to say:**
> "Each snippet has a score, a theme, a hook angle, and a platform fit recommendation. The top two snippets — follow-up system at 0.94 and positioning at 0.88 — have been approved by the operator. The other two are still pending review. Scores are advisory: the operator makes the final call on what moves forward."

**Key talking points:**
- Score is 0–1, advisory only
- Operator must explicitly approve each snippet before it can become a prompt
- No automatic approvals at any stage
- Theme labels: follow_up_system, positioning, trust_building

**What to highlight:**
- demo-snippet-1: score 0.94, approved
- demo-snippet-4: score 0.88, approved  
- demo-snippet-2, demo-snippet-3: pending review

---

## Step 7: Prompt Strategy

**Screenshot:** `step_07_prompt.png`  
**Click:** Next →

**What to say:**
> "Each approved snippet becomes a visual prompt brief. The prompt includes a positive description, negative constraints, camera direction, lighting notes, and scene beats. Every prompt in this demo has `use_likeness=false`. And look at the negative prompt — it always includes 'identifiable person, likeness, voice cloning instructions.' That's a hard constraint, not a suggestion."

**Key talking points:**
- 3 demo prompts: faceless_motivational, podcast_clip_visual, business_explainer
- All have `use_likeness: false`
- `negative_prompt` always blocks likeness/voice
- Prompts cannot trigger renders until status=approved (operator-gated)

---

## Step 8: Rendered Asset

**Screenshot:** `step_08_render.png`  
**Click:** Next →

**What to say:**
> "When a prompt is approved, the worker picks it up from the Redis queue and uses FFmpeg to assemble a local MP4. The file goes to `/tmp` on the local machine — not to any CDN, not to S3, not anywhere external. demo-render-1 has been approved; demo-render-2 is still in needs_review. `outbound_actions_taken=0`."

**Key talking points:**
- FFmpeg assembly, local machine only
- 30s, 1080×1920 (vertical format for reels)
- `/tmp/signalforge_renders/` — local filesystem only
- `outbound_actions_taken: 0` on the render record

**What to pause on:**
- The "file_path=/tmp/..." detail — this is the physical boundary of the system
- The needs_review status on render 2 — shows operator review is required before any use

---

## Step 9: Performance Feedback

**Screenshot:** `step_09_performance.png`  
**Click:** Next →

**What to say:**
> "After the operator posts manually — outside of SignalForge, using their own account — they come back here and log the performance data. SignalForge didn't post anything. The publish log record literally says `outbound_actions_taken=0`. The performance data is typed in by the operator. SignalForge then generates an advisory summary: average score 7.3, top recommendation is to double down on the follow-up hook."

**Key talking points:**
- SignalForge never posts — operator posts manually, then logs back
- publish log record confirms 0 outbound actions
- 2 performance records, avg score 7.3
- "Performance summary is advisory only" — no automation reads it to trigger actions

---

## Step 10: Campaign Pack

**Screenshot:** `step_10_campaign_pack.png`  
**Click:** Next →

**What to say:**
> "The campaign pack is the sprint bundle. It links the source content, snippets, prompts, and renders into a named deliverable. For Apex Roofing: 1 source content record, 2 snippets, 2 renders, 2 prompts. `simulation_only=true`. Pack creation doesn't publish anything — it's a metadata grouping."

**Key talking points:**
- Bundle name: "Demo: Apex Roofing Summer Growth Pack"
- Metadata-only linkage — no files are duplicated
- Pack is the unit of delivery and reporting

---

## Step 11: Campaign Report

**Screenshot:** `step_11_report.png`  
**Click:** Next →

**What to say:**
> "The campaign report aggregates everything from the pack into a structured document. You see average score 7.3, top render at 8.4, total views 6,900, and a clear top hook recommendation. This is the client-facing summary. Status is approved — an operator has reviewed and signed off on this report."

**Key talking points:**
- Structured aggregation: avg score, top performers, total views
- Top hook: follow-up system (consistent with snippet scoring)
- `outbound_actions_taken: 0` on the report record
- Status=approved means operator reviewed it

---

## Step 12: Client Export

**Screenshot:** `step_12_export.png`  
**Click:** Next →

**What to say:**
> "The export generates a Markdown file with the full campaign report. It goes to `/tmp` on the local machine. SignalForge never emails it, never uploads it, never sends it anywhere. The operator receives the file and delivers it through their own channel — email, drive share, however they work with the client. The export record says `outbound=0`."

**Key talking points:**
- Export path: `/tmp/signalforge_exports/demo/` (local only)
- Markdown format, human-readable
- `simulation_only: true`, `outbound_actions_taken: 0`
- Manual delivery by operator — system has no outbound capability

**What to show (optional):**
- Open `docs/demo_assets/exports/demo_export_apex_roofing.md` to show what the export looks like

---

## Step 13: Client Intelligence

**Screenshot:** `step_13_intelligence.png`  
**Click:** Next →

**What to say:**
> "The final layer is client intelligence — an advisory synthesis of performance data, hook themes, and lead correlations. Estimated ROI 112.5 based on the performance data. Two lead-content correlations found. `advisory_only=true` is on the record — this output does not trigger any automation. It's a structured recommendation for the operator to act on."

**Key talking points:**
- `advisory_only: true` — no automation reads this to fire actions
- `outbound_actions_taken: 0` enforced
- 2 lead-content correlations: informational only
- Top recommendation: double down on follow-up hook (consistent across the entire pipeline)

---

## Demo Complete Screen

**What to say:**
> "That's the full 13-step pipeline. From source channel approval through client intelligence — all local, all operator-gated, all with `simulation_only=true` and `outbound_actions_taken=0`. What you've seen is not a prototype UI — it's a working local pipeline with 678 backend tests and 88 frontend tests passing."

**Summary of what was proved:**
- Full pipeline from source content to client intelligence
- Every step is operator-gated — no automation fires without approval
- No external API calls, uploads, or messages were made
- All records carry `simulation_only=true`, `outbound_actions_taken=0`
- Intelligence records carry `advisory_only=true`

---

## Highlight Tour (10-minute version)

If time is limited, hit these 5 steps and skip the rest:

| Step | Why It Matters |
|------|---------------|
| **Step 1: Workspace & Safety** | Establishes the operating model and safety boundary |
| **Step 6: Scoring & Hook Selection** | Shows the core value: scored, ranked, operator-approved hooks |
| **Step 8: Rendered Asset** | Proves local FFmpeg render with zero outbound |
| **Step 12: Client Export** | Shows the deliverable format and local-only export |
| **Step 13: Client Intelligence** | Shows the advisory synthesis layer |

---

## Common Questions

**Q: Does SignalForge post to social media?**  
A: No. The system has no outbound capability. Every render goes to `/tmp` locally. The operator posts manually and logs metrics back.

**Q: Is any data sent to OpenAI or other APIs?**  
A: The core pipeline has no external API requirements. The GPT Diagnostics tab uses OpenAI if a key is configured, but it's optional and not part of this demo.

**Q: What happens to client content?**  
A: All content stays on the operator's local machine. No cloud upload, no CDN, no third-party storage.

**Q: Can multiple clients use the same system?**  
A: Currently single-operator/single-workspace. Multi-tenancy would require production auth and workspace isolation — documented in PRODUCTION_READINESS.md.

**Q: How do we get from here to production?**  
A: See [docs/PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) and [docs/POC_TECHNICAL_APPENDIX.md](POC_TECHNICAL_APPENDIX.md) for the full gap analysis.

---

_SignalForge v10.2 — POC Demo Script_
