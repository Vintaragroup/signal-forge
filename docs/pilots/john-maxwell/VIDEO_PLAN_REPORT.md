# Video Plan Report — John Maxwell Pilot
**Workspace:** `john-maxwell-pilot`
**Client:** John Maxwell
**Phase:** 4 — Render Readiness
**Generated:** 2026-05-04
**Operator status:** Awaiting approved local audio

---

## Audio Availability Audit

| Record Type | Count | Audio Found |
|---|---|---|
| `media_intake_records` (john-maxwell-pilot) | 0 | No |
| `audio_extraction_runs` (john-maxwell-pilot) | 0 | No |
| Prompt `audio_path` / `source_audio_path` | 0 | No |
| Local files in `data/` | Not checked | Not present |

**Conclusion: No approved local audio exists for any snippet.**
No rendering will proceed until the operator provides an approved local audio or video file for each clip.

---

## Approved Prompts — Render Readiness

### Prompt 1

| Field | Value |
|---|---|
| **Prompt ID** | `69f8eeb0672da2fab5965384` |
| **Snippet ID** | `69f8e8c4832da121cfcf714b` |
| **Display Title** | Your Past, but by Your Willingness to Step Forward |
| **Cleaned Hook** | Your Past, but by Your Willingness to Step Forward. |
| **Raw Hook** | `"your past, but by your willingness to step forward."` |
| **Prompt Type** | `inspirational_short_form` |
| **Status** | `approved` |
| **Render Status** | `ready_for_render_pending_audio` |
| **Audio Status** | Missing — no approved local audio file |
| **Preferred Duration** | 75 seconds |
| **Use Likeness** | `false` |
| **Simulation Only** | `true` |

**Visual Direction:**
- **Visual Style:** Cinematic, warm natural tones, authentic, high contrast
- **Camera:** Slow push-in B-roll cuts, handheld drift, rack focus on details
- **Lighting:** Natural golden-hour or window light, authentic ambient
- **Format:** 9:16 vertical, 60–90 seconds
- **Motion Notes:** Original source audio used unchanged — no rewriting or cloning. B-roll cuts every 4–8 seconds to match audio rhythm. Subtle fade in/out at start and end only.

**Scene Beats:**
1. `0–10s:` Establishing environment detail shot — no face shown
2. `10–25s:` Action or process B-roll underscoring the audio hook
3. `25–50s:` Narrative build — environment cuts matching audio pacing
4. `50–70s:` Emotional peak — close detail shot, natural light
5. `70–90s:` Resolution — wide environment, natural fade to end card

---

### Prompt 2

| Field | Value |
|---|---|
| **Prompt ID** | `69f8eebc672da2fab5965386` |
| **Snippet ID** | `69f8e8c4832da121cfcf7166` |
| **Display Title** | Will You Live by Design or by Default? |
| **Cleaned Hook** | Will You Live by Design or by Default? |
| **Raw Hook** | `"choice: will you live by design or by default?"` |
| **Prompt Type** | `inspirational_short_form` |
| **Status** | `approved` |
| **Render Status** | `ready_for_render_pending_audio` |
| **Audio Status** | Missing — no approved local audio file |
| **Preferred Duration** | 75 seconds |
| **Use Likeness** | `false` |
| **Simulation Only** | `true` |

**Visual Direction:**
- **Visual Style:** Cinematic, warm natural tones, authentic, high contrast
- **Camera:** Slow push-in B-roll cuts, handheld drift, rack focus on details
- **Lighting:** Natural golden-hour or window light, authentic ambient
- **Format:** 9:16 vertical, 60–90 seconds
- **Motion Notes:** Original source audio used unchanged — no rewriting or cloning. B-roll cuts every 4–8 seconds to match audio rhythm. Subtle fade in/out at start and end only.

**Scene Beats:**
1. `0–10s:` Establishing environment detail shot — no face shown
2. `10–25s:` Action or process B-roll underscoring the audio hook
3. `25–50s:` Narrative build — environment cuts matching audio pacing
4. `50–70s:` Emotional peak — close detail shot, natural light
5. `70–90s:` Resolution — wide environment, natural fade to end card

---

### Prompt 3

| Field | Value |
|---|---|
| **Prompt ID** | `69f8eebc672da2fab5965388` |
| **Snippet ID** | `69f8e8c4832da121cfcf7157` |
| **Display Title** | Every Failure Is Just Feedback |
| **Cleaned Hook** | Every Failure Is Just Feedback. |
| **Raw Hook** | `"here is what I know: every failure is just feedback."` |
| **Prompt Type** | `inspirational_short_form` |
| **Status** | `approved` |
| **Render Status** | `ready_for_render_pending_audio` |
| **Audio Status** | Missing — no approved local audio file |
| **Preferred Duration** | 75 seconds |
| **Use Likeness** | `false` |
| **Simulation Only** | `true` |

**Visual Direction:**
- **Visual Style:** Cinematic, warm natural tones, authentic, high contrast
- **Camera:** Slow push-in B-roll cuts, handheld drift, rack focus on details
- **Lighting:** Natural golden-hour or window light, authentic ambient
- **Format:** 9:16 vertical, 60–90 seconds
- **Motion Notes:** Original source audio used unchanged — no rewriting or cloning. B-roll cuts every 4–8 seconds to match audio rhythm. Subtle fade in/out at start and end only.

**Scene Beats:**
1. `0–10s:` Establishing environment detail shot — no face shown
2. `10–25s:` Action or process B-roll underscoring the audio hook
3. `25–50s:` Narrative build — environment cuts matching audio pacing
4. `50–70s:` Emotional peak — close detail shot, natural light
5. `70–90s:` Resolution — wide environment, natural fade to end card

---

## Render Configuration (When Audio Is Available)

```yaml
prompt_type: inspirational_short_form
preserve_original_audio: true
preferred_duration_seconds: 75
use_likeness: false
comfyui_enabled: false
ffmpeg_enabled: true
format: 9:16 vertical
audio_rewrite: false
voice_cloning: false
avatar: false
```

---

## Next Operator Action

**Blocker:** No approved local audio file has been provided for any of the 3 clips.

To unblock rendering, for each clip provide one of the following:
- A local `.mp4` or `.mov` file containing the original approved John Maxwell recording
- A local `.mp3` or `.wav` audio-only file extracted from an approved recording

**Intake path:** `data/imports/john-maxwell-pilot/` (create if needed)

Once a file is placed, create a `media_intake_record` pointing to the local path and re-run Phase 4 to trigger render.

**Do NOT:**
- Download YouTube audio or video
- Use a test tone or synthetic audio as final content
- Use voice cloning or AI speech synthesis
- Use John Maxwell's likeness or avatar

---

## Safety Constraints (Confirmed)

| Constraint | Status |
|---|---|
| `simulation_only: true` on all prompts | ✅ Confirmed |
| `outbound_actions_taken: 0` on all prompts | ✅ Confirmed |
| `use_likeness: false` on all prompts | ✅ Confirmed |
| No rendering triggered (audio missing) | ✅ Confirmed |
| No YouTube download | ✅ Confirmed |
| No publishing, scheduling, DM, or email | ✅ Confirmed |
| No avatar / voice cloning | ✅ Confirmed |
