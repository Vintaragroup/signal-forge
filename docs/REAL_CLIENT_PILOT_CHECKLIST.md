# Real Client Pilot Checklist — SignalForge v10.3

> **Purpose:** Step-by-step checklist for onboarding the first real client pilot.
> Complete every item in order before running a live content session.
> No content is published or scheduled by SignalForge — all posting is manual.

---

## 0. Pre-Flight: System Readiness

- [ ] Docker stack is running: `docker compose ps` shows all containers healthy
- [ ] API is reachable: `curl http://localhost:8000/health` returns `{"status": "ok"}`
- [ ] Frontend is reachable: `http://localhost:5174` loads SignalForge UI
- [ ] MongoDB is reachable: `docker compose exec mongo mongosh --eval "db.runCommand({ping:1})"`
- [ ] Redis is reachable: `docker compose exec redis redis-cli ping` returns `PONG`
- [ ] `FFMPEG_ENABLED` is confirmed `false` (default) unless intentional: check `.env`
- [ ] `DEMO_MODE` is confirmed `false` in environment / `.env`
- [ ] No `is_demo=True` records exist for the pilot workspace slug (run smoke query)
- [ ] Run test suite: `docker compose exec api sh -c "PYTHONPATH=/app pytest tests/ -q"` — all green
- [ ] Run frontend build: `docker compose exec web sh -c "npm run build"` — no errors

---

## 1. Create Client Workspace

- [ ] Choose a unique `workspace_slug` for the pilot client (e.g. `maxwell-pilot-2025`)
  - Must not be `demo`, `test`, `synthetic`, or `legacy`
- [ ] Create a workspace record via API or UI:
  ```
  POST /workspaces
  { "workspace_slug": "maxwell-pilot-2025", "name": "John Maxwell Pilot" }
  ```
- [ ] Confirm workspace appears in workspace list: `GET /workspaces`
- [ ] Note workspace slug for all subsequent steps

---

## 2. Create Client Profile (Company Record)

- [ ] Create the client company profile:
  ```
  POST /companies
  {
    "workspace_slug": "<slug>",
    "name": "Client Full Name or Brand",
    "industry": "<industry>",
    "avatar_permissions": false,
    "likeness_permissions": false
  }
  ```
  - **Keep `avatar_permissions` and `likeness_permissions` both `false` for pilot**
- [ ] Note the returned `_id` as `CLIENT_ID`
- [ ] Verify profile via `GET /companies?workspace_slug=<slug>`

---

## 3. Create Source Channel(s)

- [ ] For each platform where the client publishes long-form content (YouTube, podcast, etc.):
  ```
  POST /source-channels
  {
    "workspace_slug": "<slug>",
    "client_id": "<CLIENT_ID>",
    "channel_name": "Client YouTube Channel",
    "platform": "youtube",
    "channel_url": "https://www.youtube.com/@clienthandle"
  }
  ```
- [ ] Note each returned `_id` as `CHANNEL_ID`
- [ ] Verify channels: `GET /source-channels?workspace_slug=<slug>`

---

## 4. Add Source Content

- [ ] For each long-form video or podcast episode to process:
  ```
  POST /source-content
  {
    "workspace_slug": "<slug>",
    "client_id": "<CLIENT_ID>",
    "channel_id": "<CHANNEL_ID>",
    "title": "Episode Title",
    "source_url": "https://www.youtube.com/watch?v=...",
    "content_type": "youtube_video",
    "status": "pending"
  }
  ```
- [ ] Confirm at least 1 source content item is in `pending` status
- [ ] **Operator review gate:** confirm the source content URL is authentic client content — not third-party, not licensed music, not copyrighted without rights

---

## 5. Run Transcript Extraction

- [ ] Initiate transcript run for each source content item:
  ```
  POST /transcript-runs
  {
    "workspace_slug": "<slug>",
    "source_content_id": "<CONTENT_ID>"
  }
  ```
- [ ] Monitor transcript status: `GET /transcript-runs?source_content_id=<id>`
- [ ] Confirm transcript status reaches `completed`
- [ ] Review transcript text for accuracy — flag any errors before proceeding

---

## 6. Create and Score Content Snippets

- [ ] Review auto-detected or manually create snippets from the transcript:
  ```
  POST /content-snippets
  {
    "workspace_slug": "<slug>",
    "client_id": "<CLIENT_ID>",
    "source_content_id": "<CONTENT_ID>",
    "transcript_text": "<clip text>",
    "start_time": 120.5,
    "end_time": 195.0
  }
  ```
- [ ] Score each snippet:
  ```
  POST /content-snippets/<id>/score
  ```
- [ ] Review scores — minimum `overall_score >= 6.0` required to proceed
- [ ] **Operator review gate:** read each snippet aloud to confirm it represents the client's voice and intent accurately

---

## 7. Approve Snippets

- [ ] For each high-scoring snippet to proceed:
  ```
  POST /content-snippets/<id>/review
  { "decision": "approve", "note": "Strong hook, authentic voice, on-brand" }
  ```
- [ ] Confirm snippet status is `approved` before generating prompts
- [ ] Reject any snippets with unclear context, missing consent, or off-brand content

---

## 8. Generate Visual Prompts

- [ ] For each approved snippet, select a prompt type:
  - **Recommended for pilot:** `inspirational_short_form` (60–90s, cinematic B-roll, original audio)
  - Alternatives: `cinematic_broll`, `faceless_motivational`, `quote_card_motion`
  ```
  POST /prompt-generations
  {
    "workspace_slug": "<slug>",
    "client_id": "<CLIENT_ID>",
    "snippet_id": "<SNIPPET_ID>",
    "prompt_type": "inspirational_short_form",
    "generation_engine_target": "manual",
    "use_likeness": false
  }
  ```
- [ ] Confirm `use_likeness: false` — **never enable likeness for pilot**
- [ ] Review `positive_prompt` text for brand safety and accuracy
- [ ] Review `negative_prompt` — confirm likeness, avatar, and voice cloning are blocked

---

## 9. Approve Prompts

- [ ] Review each generated prompt with the client or team:
  ```
  POST /prompt-generations/<id>/review
  { "decision": "approve", "note": "Visual direction approved by operator" }
  ```
- [ ] Request revision if prompt direction doesn't match client's aesthetic
- [ ] Confirm status is `approved` before initiating any asset render

---

## 10. Render Video Assets

- [ ] Initiate render for each approved snippet + prompt pair:
  ```
  POST /assets/render
  {
    "workspace_slug": "<slug>",
    "client_id": "<CLIENT_ID>",
    "snippet_id": "<SNIPPET_ID>",
    "prompt_generation_id": "<PROMPT_GEN_ID>",
    "source_audio_path": "/path/to/client_original_audio.wav",
    "preserve_original_audio": true,
    "generation_engine": "manual"
  }
  ```
- [ ] **Audio rule:** always provide `source_audio_path` pointing to the client's original recording
  - If `source_audio_path` is empty, only a test-tone fallback is used (demo/test only)
  - Never use AI-generated, cloned, or synthetic audio for real client content
- [ ] Confirm render record is created with `preserve_original_audio: true`
- [ ] Review assembled video output for accuracy and brand alignment

---

## 11. Approve Rendered Assets

- [ ] Review each rendered asset in the SignalForge UI or via API:
  ```
  POST /assets/<id>/review
  { "decision": "approve", "note": "Asset approved for export" }
  ```
- [ ] Reject any asset with visual artifacts, incorrect audio sync, or off-brand direction
- [ ] **Operator review gate:** play full video before approving — do not batch-approve

---

## 12. Export Campaign Pack

- [ ] Create a campaign pack from approved assets:
  ```
  POST /campaign-packs
  {
    "workspace_slug": "<slug>",
    "client_id": "<CLIENT_ID>",
    "name": "Pilot Campaign Pack — Week 1"
  }
  ```
- [ ] Add approved assets to the pack
- [ ] Generate a campaign report: `POST /campaign-reports`
- [ ] Export the pack for delivery: `POST /campaign-exports`
- [ ] Confirm export contains:
  - Visual prompt details
  - Source attribution (source URL, clip timestamps)
  - Video plan report (see `VIDEO_PLAN_REPORT_TEMPLATE.md`)
  - Posting guidelines (platform, cadence, caption copy)

---

## 13. Manual Posting Only

- [ ] **SignalForge does NOT post content** — all posting is manual by the operator or client
- [ ] Review platform-specific posting requirements before delivery:
  - Instagram Reels: 60s max (use 60s cut), vertical 9:16, captions recommended
  - TikTok: 60–90s supported, original audio preserved for sync
  - YouTube Shorts: up to 60s for Shorts feed, 90s acceptable as standard upload
  - LinkedIn: 10 min max, but 60–90s performs best for thought leadership
- [ ] Provide the client with the exported pack and posting schedule
- [ ] Log the delivery: `POST /manual-publish-logs`

---

## 14. Post-Pilot Review

- [ ] Log any response or engagement data: `POST /asset-performance-records`
- [ ] Review KPIs from `KPI_TRACKING.md` in the client module
- [ ] Document what worked and what to adjust for the next cycle
- [ ] Schedule follow-up review meeting with client within 5–7 days of first post

---

## Safety Guardrails — Never Override

| Rule | Enforcement |
|------|-------------|
| No avatar or likeness rendering | `avatar_permissions=false`, `likeness_permissions=false`, `use_likeness=false` |
| No voice cloning or audio rewriting | `preserve_original_audio=true` always; source audio unchanged |
| No AI-generated voice substitution | `inspirational_short_form` preset explicitly blocks this |
| No outbound posting by SignalForge | `simulation_only=true`, `outbound_actions_taken=0` always |
| No demo data in real workspace | Real workspace slug filters out demo/test/synthetic records |
| All renders require operator review | Asset review step is mandatory before export |

---

*SignalForge v10.3 — Real Client Pilot Readiness*
