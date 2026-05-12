import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Bot,
  ChevronRight,
  CircleDot,
  Film,
  Gauge,
  MessageSquare,
  Network,
  Pause,
  Play,
  RefreshCw,
  Share2,
  Shield,
  Sparkles,
  TrendingUp,
  Workflow,
} from "lucide-react";
import {
  getExecutiveDemoState,
  nextExecutiveDemoPhase,
  prevExecutiveDemoPhase,
  resetDemoData,
  setExecutiveDemoPhase,
} from "../demoMode.js";

const PHASE_ICONS = {
  discovery: Sparkles,
  generation: Film,
  distribution: Share2,
  engagement: MessageSquare,
  funnel: Network,
  conversion: BarChart3,
};

const DISCOVERY_SOURCES = [
  {
    title: "Leadership Sermon Clips",
    detail: "Long-form teaching clips segmented into themes like clarity, influence, discipline, and purpose.",
    meta: "7 topic clusters",
  },
  {
    title: "Quote and Story Library",
    detail: "High-retention moments converted into short quote hooks and executive sound bites.",
    meta: "74 clips extracted",
  },
  {
    title: "Audience Intent Signals",
    detail: "Theme clustering prioritizes what viewers repeatedly respond to across growth accounts.",
    meta: "98% transcript confidence",
  },
];

const DISTRIBUTION_QUEUE = [
  { account: "@LeadWithMaxwell", platform: "Instagram", status: "Queued", eta: "Today 8:30 AM" },
  { account: "@DailyLeadershipFuel", platform: "YouTube Shorts", status: "Optimized", eta: "Today 12:00 PM" },
  { account: "@MaxwellCareerGrowth", platform: "LinkedIn", status: "Scheduled", eta: "Tomorrow 7:15 AM" },
  { account: "@PurposeDrivenGrowth", platform: "Instagram", status: "Ready", eta: "Tomorrow 6:45 PM" },
];

const SECTION_LABELS = {
  ingest: "Ingest Pipeline",
  renders: "Rendered Assets",
  "campaign-packs": "Campaign Packs",
  "performance-loop": "Performance Loop",
  "campaign-exports": "Campaign Exports",
  "client-intelligence": "Client Intelligence",
};

function formatMetric(metric) {
  const prefix = metric?.prefix || "";
  const suffix = metric?.suffix || "";
  const value = Number(metric?.value || 0);
  const formatted = Number.isInteger(value)
    ? value.toLocaleString()
    : value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 });
  return `${prefix}${formatted}${suffix}`;
}

function useAnimatedValue(target) {
  const [value, setValue] = useState(Number(target || 0));

  useEffect(() => {
    const next = Number(target || 0);
    let frame = 0;
    const start = value;
    const diff = next - start;
    const startedAt = performance.now();
    const duration = 650;

    function tick(now) {
      const progress = Math.min(1, (now - startedAt) / duration);
      setValue(start + diff * progress);
      if (progress < 1) frame = window.requestAnimationFrame(tick);
    }

    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [target]);

  return value;
}

function AnimatedMetricCard({ label, value, prefix = "", suffix = "", tone = "blue", helper = "" }) {
  const animated = useAnimatedValue(value);
  const palette = {
    blue: "border-blue-200 bg-blue-50 text-blue-700",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-700",
    amber: "border-amber-200 bg-amber-50 text-amber-700",
    violet: "border-violet-200 bg-violet-50 text-violet-700",
    rose: "border-rose-200 bg-rose-50 text-rose-700",
    slate: "border-slate-200 bg-slate-50 text-slate-700",
  };
  const cardTone = palette[tone] || palette.blue;
  const rounded = Number.isInteger(animated)
    ? Math.round(animated).toLocaleString()
    : animated.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 });

  return (
    <div className={`rounded-2xl border p-4 shadow-sm ${cardTone}`}>
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] opacity-80">{label}</div>
      <div className="mt-3 text-3xl font-semibold">{prefix}{rounded}{suffix}</div>
      {helper ? <p className="mt-2 text-sm opacity-80">{helper}</p> : null}
    </div>
  );
}

function ExecutiveSummaryCard({ card, active }) {
  const cardValue = useAnimatedValue(card.metric_value || 0);
  const formatted = Number.isInteger(cardValue)
    ? Math.round(cardValue).toLocaleString()
    : cardValue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 });

  return (
    <article className={`relative overflow-hidden rounded-[26px] border p-5 shadow-sm transition ${active ? "border-slate-900 bg-slate-950 text-white" : "border-slate-200 bg-white text-slate-900"}`}>
      <div className={`absolute inset-x-0 top-0 h-1 ${active ? "bg-violet-400" : "bg-slate-200"}`} />
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className={`text-[11px] font-semibold uppercase tracking-[0.18em] ${active ? "text-slate-300" : "text-slate-400"}`}>{card.phase}</div>
          <h3 className="mt-2 text-lg font-semibold">{card.title}</h3>
        </div>
        <div className={`rounded-full px-2.5 py-1 text-xs font-semibold ${active ? "bg-violet-400/20 text-violet-100" : "bg-slate-100 text-slate-600"}`}>{card.metric_label}</div>
      </div>
      <div className="mt-5 text-3xl font-semibold tracking-tight">
        {card.metric_prefix || ""}
        {formatted}
        {card.metric_suffix || ""}
      </div>
      <p className={`mt-3 text-sm leading-6 ${active ? "text-slate-200" : "text-slate-600"}`}>{card.description}</p>
    </article>
  );
}

function SectionRail({ timeline, active, onSelect }) {
  return (
    <div className="flex flex-wrap gap-2">
      {timeline.map((phase) => {
        const isActive = phase.id === active?.id;
        const classes = isActive
          ? "border-slate-900 bg-slate-900 text-white shadow-sm"
          : phase.status === "complete"
            ? "border-emerald-200 bg-emerald-50 text-emerald-700"
            : "border-slate-200 bg-white text-slate-600";
        return (
          <button
            key={phase.id}
            type="button"
            onClick={() => onSelect(phase.id)}
            className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition ${classes}`}
          >
            <span>{phase.label}</span>
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        );
      })}
    </div>
  );
}

function NarrativeFlow({ steps, activePhase }) {
  return (
    <div className="overflow-x-auto">
      <div className="flex min-w-[980px] items-center gap-3 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
        {steps.map((step, index) => {
          const active = index + 1 <= activePhase;
          return (
            <div key={step} className="flex min-w-[120px] items-center gap-3">
              <div className={`flex h-11 w-11 items-center justify-center rounded-2xl border text-sm font-semibold ${active ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-slate-50 text-slate-500"}`}>
                {index + 1}
              </div>
              <div className="min-w-0 flex-1">
                <div className={`text-sm font-semibold ${active ? "text-slate-900" : "text-slate-400"}`}>{step}</div>
              </div>
              {index < steps.length - 1 ? <Workflow className={`h-4 w-4 ${active ? "text-slate-700" : "text-slate-300"}`} /> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function formatShortTime(seconds) {
  const totalSeconds = Math.max(0, Math.round(Number(seconds || 0)));
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  return `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
}

function OperationalWorkflowShowcase({ state }) {
  const [selectedClipId, setSelectedClipId] = useState(() => state.audio_clips?.[0]?._id || null);

  useEffect(() => {
    if (!state.audio_clips?.length) {
      setSelectedClipId(null);
      return;
    }
    if (!(state.audio_clips || []).some((clip) => clip._id === selectedClipId)) {
      setSelectedClipId(state.audio_clips[0]._id);
    }
  }, [selectedClipId, state.audio_clips]);

  const selectedClip = (state.audio_clips || []).find((clip) => clip._id === selectedClipId) || state.audio_clips?.[0] || null;
  const sourceById = new Map((state.source_content || []).map((item) => [item._id, item]));
  const snippetById = new Map((state.content_snippets || []).map((item) => [item._id, item]));
  const promptById = new Map((state.prompt_generations || []).map((item) => [item._id, item]));
  const relatedSource = selectedClip ? sourceById.get(selectedClip.source_content_id) : null;
  const relatedSnippet = selectedClip ? snippetById.get(selectedClip.snippet_id) : null;
  const relatedTranscriptSegments = (state.transcript_segments || [])
    .filter((segment) => segment.source_content_id === selectedClip?.source_content_id)
    .slice(0, 4);
  const relatedIdeas = (state.content_ideas || []).filter((idea) => idea.source_clip_id === selectedClip?._id);
  const finishedRenders = (state.asset_renders || []).filter((render) => String(render.preview_url || "").endsWith(".mp4"));
  const campaignPack = state.campaign_packs?.[0] || null;

  return (
    <section className="rounded-[30px] border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Real Workflow Media Demonstration</div>
          <h3 className="mt-2 text-2xl font-semibold text-slate-950">Operational proof: one John Maxwell media source becomes a repeatable short-form growth workflow.</h3>
          <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">
            This layer shows the real workflow continuity end to end: source media, extracted clips, transcript intelligence, AI idea generation, structured script output, faceless video prompts, finished playable media, approved distribution accounts, and the audience-response path into the funnel.
          </p>
        </div>
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700">
          Local media playback enabled
        </div>
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        {[
          "Source Media",
          "Audio Extraction",
          "Transcript Intelligence",
          "AI Content Ideas",
          "Script Generation",
          "Prompt Export",
          "Finished Video Output",
          "Distribution Strategy",
          "Audience Funnel",
        ].map((step) => (
          <span key={step} className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">{step}</span>
        ))}
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
        <div className="space-y-4">
          <article className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Source Media</div>
                <h4 className="mt-2 text-xl font-semibold text-slate-950">{relatedSource?.title || state.source_content?.[0]?.title}</h4>
              </div>
              <div className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-600 shadow-sm">{relatedSource?.platform || "youtube"}</div>
            </div>
            <p className="mt-3 text-sm leading-6 text-slate-600">{relatedSource?.discovery_reason || state.source_content?.[0]?.discovery_reason}</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Duration</div>
                <div className="mt-2 text-lg font-semibold text-slate-950">{formatShortTime(relatedSource?.duration_seconds || state.source_content?.[0]?.duration_seconds)}</div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Discovery score</div>
                <div className="mt-2 text-lg font-semibold text-slate-950">{Math.round(Number((relatedSource?.discovery_score || state.source_content?.[0]?.discovery_score || 0) * 100))}%</div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Snippet candidates</div>
                <div className="mt-2 text-lg font-semibold text-slate-950">{(state.audio_clips || []).length}</div>
              </div>
            </div>
          </article>

          <article className="rounded-3xl border border-slate-200 bg-slate-950 p-5 text-white shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Audio Extraction</div>
                <h4 className="mt-2 text-xl font-semibold">Playable quote clips</h4>
              </div>
              <div className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-semibold text-emerald-100">Real audio files</div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {(state.audio_clips || []).map((clip) => {
                const active = clip._id === selectedClip?._id;
                return (
                  <button
                    key={clip._id}
                    type="button"
                    onClick={() => setSelectedClipId(clip._id)}
                    className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${active ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100" : "border-white/10 bg-white/5 text-slate-300 hover:border-white/20 hover:text-white"}`}
                  >
                    {clip.title}
                  </button>
                );
              })}
            </div>
            {selectedClip ? (
              <div className="mt-5 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
                <div className="rounded-[24px] border border-white/10 bg-white/5 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-white">{selectedClip.title}</div>
                      <div className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-400">{selectedClip.source_reference}</div>
                    </div>
                    <div className="rounded-full bg-white/10 px-2.5 py-1 text-xs font-semibold text-slate-200">{selectedClip.duration_seconds}s</div>
                  </div>
                  <audio className="mt-4 w-full" controls preload="metadata">
                    <source src={selectedClip.audio_url} type="audio/mp4" />
                    Your browser does not support audio playback.
                  </audio>
                  <div className="mt-4 rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-4">
                    <div className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-100">Quote Highlight</div>
                    <p className="mt-2 text-lg font-semibold text-white">{selectedClip.quote_highlight}</p>
                  </div>
                </div>
                <div className="rounded-[24px] border border-white/10 bg-white/5 p-4">
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Why This Clip Matters</div>
                  <p className="mt-3 text-sm leading-6 text-slate-200">{selectedClip.why_this_matters}</p>
                  <div className="mt-4 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">AI labels</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {(selectedClip.ai_labels || []).map((label) => (
                      <span key={label} className="rounded-full border border-white/10 bg-slate-950/60 px-3 py-1 text-xs font-semibold text-slate-200">{label}</span>
                    ))}
                  </div>
                  <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/60 p-4">
                    <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Transcript Snippet</div>
                    <p className="mt-2 text-sm leading-6 text-white">{selectedClip.transcript_snippet}</p>
                  </div>
                </div>
              </div>
            ) : null}
          </article>

          <article className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Transcript Intelligence</div>
            <h4 className="mt-2 text-xl font-semibold text-slate-950">Clip scoring and quote extraction</h4>
            <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_0.95fr]">
              <div className="space-y-3">
                {relatedTranscriptSegments.map((segment) => (
                  <div key={segment._id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{formatShortTime(segment.start_ms / 1000)} - {formatShortTime(segment.end_ms / 1000)}</div>
                      <div className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 shadow-sm">{Math.round(Number(segment.confidence || 0) * 100)}% confidence</div>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-700">{segment.text}</p>
                  </div>
                ))}
              </div>
              <div className="space-y-3">
                {relatedSnippet ? (
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Selected clip score</div>
                    <div className="mt-2 text-2xl font-semibold text-slate-950">{Math.round(Number(relatedSnippet.score || 0) * 100)}%</div>
                    <p className="mt-3 text-sm leading-6 text-slate-600">{relatedSnippet.score_reason}</p>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {(relatedSnippet.platform_fit || []).map((platform) => (
                        <span key={platform} className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-700 shadow-sm">{platform}</span>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className="rounded-2xl border border-slate-200 bg-slate-950 p-4 text-white shadow-sm">
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Theme</div>
                  <div className="mt-2 text-lg font-semibold">{relatedSnippet?.theme?.replaceAll("_", " ") || selectedClip?.engagement_potential}</div>
                  <p className="mt-3 text-sm leading-6 text-slate-300">{relatedSnippet?.hook_angle || selectedClip?.engagement_potential}</p>
                </div>
              </div>
            </div>
          </article>
        </div>

        <div className="space-y-4">
          <article className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">AI Content Ideas</div>
            <h4 className="mt-2 text-xl font-semibold text-slate-950">Audience-aware idea generation from extracted clips</h4>
            <div className="mt-4 space-y-3">
              {(relatedIdeas.length ? relatedIdeas : state.content_ideas || []).slice(0, 3).map((idea) => (
                <div key={idea._id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold text-slate-950">{idea.content_title}</div>
                      <div className="mt-1 text-sm text-slate-500">{idea.target_audience} · {idea.platform_recommendation}</div>
                    </div>
                    <div className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-semibold text-emerald-700">{idea.viral_potential}</div>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-600">{idea.hook}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {(idea.title_variants || []).slice(0, 2).map((variant) => (
                      <span key={variant} className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-700 shadow-sm">{variant}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </article>

          <article className="rounded-3xl border border-slate-200 bg-slate-950 p-5 text-white shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Finished Video Output</div>
            <h4 className="mt-2 text-xl font-semibold">Playable faceless demo renders</h4>
            <div className="mt-4 space-y-4">
              {finishedRenders.map((render) => {
                const prompt = promptById.get(render.prompt_generation_id);
                const snippet = snippetById.get(render.snippet_id);
                return (
                  <div key={render._id} className="rounded-[24px] border border-white/10 bg-white/5 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-white">{snippet?.transcript_text || render._id}</div>
                        <div className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-400">{prompt?.prompt_type?.replaceAll("_", " ") || render.generation_engine}</div>
                      </div>
                      <div className="rounded-full bg-white/10 px-2.5 py-1 text-xs font-semibold text-slate-200">{render.status.replaceAll("_", " ")}</div>
                    </div>
                    <video className="mt-4 aspect-[9/16] w-full rounded-2xl border border-white/10 bg-black" controls preload="metadata">
                      <source src={render.preview_url} type="video/mp4" />
                      Your browser does not support video playback.
                    </video>
                    <p className="mt-3 text-sm leading-6 text-slate-300">{prompt?.caption_overlay_suggestion || render.notes}</p>
                  </div>
                );
              })}
            </div>
          </article>
        </div>
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
        <article className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Structured Script Generation</div>
          <h4 className="mt-2 text-xl font-semibold text-slate-950">Short-form leadership scripts ready for campaign packaging</h4>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {(state.generated_scripts || []).map((script) => (
              <div key={script._id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="font-semibold text-slate-950">{script.title}</div>
                  <div className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-semibold text-violet-700">{script.viral_score}</div>
                </div>
                <div className="mt-3 space-y-2 text-sm leading-6 text-slate-600">
                  <p><span className="font-semibold text-slate-950">Hook:</span> {script.hook}</p>
                  <p><span className="font-semibold text-slate-950">Value:</span> {script.value}</p>
                  <p><span className="font-semibold text-slate-950">Story:</span> {script.story}</p>
                  <p><span className="font-semibold text-slate-950">CTA:</span> {script.cta}</p>
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs font-semibold text-slate-600">
                  <span className="rounded-full bg-white px-3 py-1 shadow-sm">{script.platform_target}</span>
                  <span className="rounded-full bg-white px-3 py-1 shadow-sm">{script.suggested_visual_style}</span>
                </div>
              </div>
            ))}
          </div>
        </article>

        <div className="space-y-4">
          <article className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Faceless Video Prompt Export</div>
            <h4 className="mt-2 text-xl font-semibold text-slate-950">Approved prompt packets for render orchestration</h4>
            <div className="mt-4 space-y-3">
              {(state.prompt_generations || []).map((prompt) => (
                <div key={prompt._id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold text-slate-950">{prompt.prompt_type.replaceAll("_", " ")}</div>
                      <div className="mt-1 text-sm text-slate-500">Engine: {prompt.generation_engine_target}</div>
                    </div>
                    <div className={`rounded-full px-2.5 py-1 text-xs font-semibold ${prompt.status === "approved" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>{prompt.status.replaceAll("_", " ")}</div>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-600">{prompt.caption_overlay_suggestion}</p>
                  <div className="mt-3 rounded-2xl border border-slate-200 bg-white p-3 text-xs leading-5 text-slate-600 shadow-sm">{prompt.positive_prompt}</div>
                </div>
              ))}
            </div>
          </article>

          <article className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Distribution Strategy + Audience Funnel</div>
            <h4 className="mt-2 text-xl font-semibold text-slate-950">From approved growth accounts into demand capture</h4>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {(state.growth_accounts || []).slice(0, 4).map((account) => (
                <div key={account._id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="font-semibold text-slate-950">{account.handle}</div>
                  <div className="mt-1 text-sm text-slate-500">{account.platform.replaceAll("_", " ")} · {account.audience_segment}</div>
                  <div className="mt-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Growth velocity</div>
                  <div className="mt-1 text-sm font-semibold text-slate-950">{account.growth_velocity}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Campaign Pack</div>
              <div className="mt-2 text-lg font-semibold text-slate-950">{campaignPack?.campaign_name}</div>
              <p className="mt-2 text-sm leading-6 text-slate-600">{campaignPack?.description}</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Prompts</div>
                  <div className="mt-1 text-lg font-semibold text-slate-950">{campaignPack?.prompt_generation_ids?.length || 0}</div>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Renders</div>
                  <div className="mt-1 text-lg font-semibold text-slate-950">{campaignPack?.render_ids?.length || 0}</div>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">DM triggers</div>
                  <div className="mt-1 text-lg font-semibold text-slate-950">{(state.dm_queue || []).length}</div>
                </div>
              </div>
              <div className="mt-4 space-y-2">
                {(state.funnel_events || []).slice(0, 3).map((event) => (
                  <div key={event._id} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-700">
                    <span>{event.label}</span>
                    <span className="font-semibold text-slate-950">{Number(event.count || 0).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          </article>
        </div>
      </div>
    </section>
  );
}

function PhaseShowcase({ state }) {
  const active = state.active;
  if (!active) return null;

  if (active.key === "discovery") {
    return (
      <div className="grid gap-4 lg:grid-cols-3">
        {DISCOVERY_SOURCES.map((item) => (
          <article key={item.title} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Discovery Source</div>
            <h4 className="mt-3 text-lg font-semibold text-slate-950">{item.title}</h4>
            <p className="mt-2 text-sm leading-6 text-slate-600">{item.detail}</p>
            <div className="mt-4 inline-flex rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">{item.meta}</div>
          </article>
        ))}
      </div>
    );
  }

  if (active.key === "generation") {
    return (
      <div className="grid gap-4 xl:grid-cols-[1.3fr_0.9fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Generated Scripts</div>
              <h4 className="mt-2 text-lg font-semibold text-slate-950">High-velocity content queue</h4>
            </div>
            <div className="rounded-full bg-violet-100 px-3 py-1 text-xs font-semibold text-violet-700">AnimateDiff ready</div>
          </div>
          <div className="mt-4 space-y-3">
            {state.generated_scripts.map((script) => (
              <article key={script._id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="font-semibold text-slate-950">{script.title}</div>
                  <div className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-semibold text-emerald-700">Viral score {script.viral_score}</div>
                </div>
                <p className="mt-2 text-sm text-slate-600">{script.hook}</p>
                <p className="mt-3 text-xs font-medium uppercase tracking-wide text-slate-400">CTA</p>
                <p className="mt-1 text-sm text-slate-700">{script.cta}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {script.hashtags.map((tag) => <span key={tag} className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 shadow-sm">#{tag}</span>)}
                </div>
              </article>
            ))}
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-950 p-5 text-white shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Render Pipeline</div>
          <h4 className="mt-2 text-lg font-semibold">Faceless short-form assembly</h4>
          <div className="mt-5 space-y-3">
            {[
              ["Prompt orchestration", "Complete"],
              ["Voiceover prompts", "Ready"],
              ["AnimateDiff render", "Streaming"],
              ["Campaign packaging", "Queued"],
            ].map(([label, status], index) => (
              <div key={label} className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                <div className="flex items-center gap-3 text-sm font-medium">
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-white/10 text-xs">{index + 1}</div>
                  {label}
                </div>
                <div className="rounded-full bg-violet-500/20 px-2.5 py-1 text-xs font-semibold text-violet-200">{status}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (active.key === "distribution") {
    return (
      <div className="grid gap-4 xl:grid-cols-[1.15fr_1fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Growth Accounts</div>
          <h4 className="mt-2 text-lg font-semibold text-slate-950">Approved distribution network</h4>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {state.growth_accounts.map((account) => (
              <article key={account._id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-slate-950">{account.handle}</div>
                    <div className="mt-1 text-sm text-slate-500">{account.platform.replaceAll("_", " ")} · {account.theme.replaceAll("_", " ")}</div>
                  </div>
                  <div className="rounded-full bg-blue-100 px-2.5 py-1 text-xs font-semibold text-blue-700">{account.growth_velocity}</div>
                </div>
                <p className="mt-3 text-sm text-slate-600">Audience: {account.audience_segment}</p>
                <p className="mt-1 text-sm text-slate-600">Cadence: {account.posting_frequency}</p>
                <p className="mt-1 text-sm text-slate-600">Estimated reach: {Number(account.estimated_reach).toLocaleString()}</p>
              </article>
            ))}
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Campaign Queue</div>
          <h4 className="mt-2 text-lg font-semibold text-slate-950">Posting coordination at scale</h4>
          <div className="mt-4 space-y-3">
            {DISTRIBUTION_QUEUE.map((item) => (
              <div key={`${item.account}-${item.platform}`} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-slate-950">{item.account}</div>
                    <div className="mt-1 text-sm text-slate-500">{item.platform}</div>
                  </div>
                  <div className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-semibold text-emerald-700">{item.status}</div>
                </div>
                <p className="mt-3 text-sm text-slate-600">{item.eta}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (active.key === "engagement") {
    return (
      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.9fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Live Engagement Feed</div>
          <h4 className="mt-2 text-lg font-semibold text-slate-950">Simulated audience activity</h4>
          <div className="mt-4 space-y-3">
            {state.engagement_events.map((event) => (
              <div key={event._id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="font-semibold text-slate-950">{event.event_type.toUpperCase()} · {event.handle}</div>
                  <div className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-700">{event.sentiment.replaceAll("_", " ")}</div>
                </div>
                <p className="mt-2 text-sm text-slate-600">{event.note}</p>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
                  {event.keyword ? <span className="rounded-full bg-white px-2.5 py-1 shadow-sm">Keyword: {event.keyword}</span> : null}
                  <span className="rounded-full bg-white px-2.5 py-1 shadow-sm">Lead tag: {event.lead_tag.replaceAll("_", " ")}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">DM Queue</div>
            <div className="mt-4 space-y-3">
              {state.dm_queue.map((item) => (
                <div key={item._id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-semibold text-slate-950">{item.target_offer}</div>
                    <div className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-semibold text-violet-700">{item.status}</div>
                  </div>
                  <p className="mt-2 text-sm text-slate-600">Trigger: {item.trigger_keyword}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-950 p-5 text-white shadow-sm">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-200"><Activity className="h-4 w-4" /> Interaction heatmap</div>
            <div className="mt-4 grid grid-cols-4 gap-2">
              {[18, 34, 51, 63, 29, 72, 81, 54, 22, 61, 90, 48].map((value, index) => (
                <div key={index} className="rounded-xl bg-violet-500/20 p-3 text-center text-xs font-semibold text-violet-100" style={{ opacity: 0.35 + value / 140 }}>
                  {value}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (active.key === "funnel") {
    return (
      <div className="grid gap-4 xl:grid-cols-[1fr_1.1fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Micro Program Offers</div>
          <div className="mt-4 space-y-3">
            {state.funnel_offers.map((offer) => (
              <div key={offer._id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-semibold text-slate-950">{offer.name}</div>
                  <div className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-semibold text-emerald-700">${offer.price}</div>
                </div>
                <p className="mt-2 text-sm text-slate-600">Tier: {offer.tier.replaceAll("_", " ")}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Funnel Progression</div>
          <div className="mt-4 space-y-3">
            {state.funnel_events.map((event) => (
              <div key={event._id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="font-semibold text-slate-950">{event.label}</div>
                    <div className="mt-1 text-sm text-slate-500">{event.stage.replaceAll("_", " ")}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-semibold text-slate-950">{Number(event.count).toLocaleString()}</div>
                    <div className="text-xs font-semibold text-slate-500">{Math.round(Number(event.conversion_rate || 0) * 100)}% conversion</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[1.15fr_0.95fr]">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Audience Lifecycle</div>
        <div className="mt-4 flex items-end gap-3">
          {state.audience_growth_snapshots.map((item) => {
            const height = Math.max(56, Math.round((Number(item.projected_revenue || 0) / 74200) * 220));
            const activeBar = Number(item.phase) === Number(state.active_phase);
            return (
              <div key={item._id} className="flex flex-1 flex-col items-center gap-2">
                <div
                  className={`w-full rounded-t-2xl ${activeBar ? "bg-slate-900" : "bg-slate-300"}`}
                  style={{ height }}
                />
                <div className={`text-xs font-semibold ${activeBar ? "text-slate-900" : "text-slate-400"}`}>P{item.phase}</div>
              </div>
            );
          })}
        </div>
      </div>
      <div className="rounded-2xl border border-slate-200 bg-slate-950 p-5 text-white shadow-sm">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Executive Summary</div>
        <div className="mt-4 space-y-3">
          {[
            ["Projected revenue", `$${Number(state.snapshot.projected_revenue || 0).toLocaleString()}`],
            ["Qualified leads", Number(state.snapshot.leads_captured || 0).toLocaleString()],
            ["Audience growth", Number(state.snapshot.followers || 0).toLocaleString()],
            ["Ecosystem conversion", "15.6%"],
          ].map(([label, value]) => (
            <div key={label} className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
              <div className="text-sm text-slate-300">{label}</div>
              <div className="text-lg font-semibold text-white">{value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function CommandSummaryTile({ label, value, helper, accent = "violet" }) {
  const accentClasses = {
    violet: "from-violet-500/20 to-fuchsia-500/10 border-violet-400/20",
    blue: "from-cyan-500/20 to-blue-500/10 border-cyan-400/20",
    emerald: "from-emerald-500/20 to-lime-500/10 border-emerald-400/20",
    amber: "from-amber-500/20 to-orange-500/10 border-amber-400/20",
  };
  return (
    <div className={`rounded-[24px] border bg-gradient-to-br p-5 shadow-[0_18px_50px_rgba(15,23,42,0.35)] ${accentClasses[accent] || accentClasses.violet}`}>
      <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">{label}</div>
      <div className="mt-3 text-3xl font-semibold tracking-tight text-white">{value}</div>
      <p className="mt-2 text-sm leading-6 text-slate-300">{helper}</p>
    </div>
  );
}

function GuardrailBadge({ label }) {
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-amber-400/20 bg-amber-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-100">
      <Shield className="h-3.5 w-3.5" />
      {label}
    </div>
  );
}

function CommandMetricItem({ metric }) {
  const animated = useAnimatedValue(metric.value || 0);
  const formatted = Number.isInteger(animated)
    ? Math.round(animated).toLocaleString()
    : animated.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 });
  const width = Math.max(18, Math.min(100, typeof metric.value === "number" ? Math.round(metric.value) : 42));

  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/60 p-4 shadow-inner shadow-black/20">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-semibold text-white">{metric.label}</div>
        <div className="rounded-full bg-white/10 px-2.5 py-1 text-xs font-semibold text-slate-200">{metric.helper}</div>
      </div>
      <div className="mt-4 text-3xl font-semibold tracking-tight text-white">
        {metric.prefix || ""}
        {formatted}
        {metric.suffix || ""}
      </div>
      <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-violet-500 to-emerald-400 transition-all duration-1000"
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

function CommandMetricGroup({ group }) {
  return (
    <article className="rounded-[28px] border border-white/10 bg-white/5 p-5 backdrop-blur-xl shadow-[0_18px_50px_rgba(15,23,42,0.28)]">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Live KPI Cinematics</div>
          <h3 className="mt-2 text-xl font-semibold text-white">{group.label}</h3>
        </div>
        <div className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-slate-200">
          {group.metrics.length} signals
        </div>
      </div>
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        {group.metrics.map((metric) => <CommandMetricItem key={metric.label} metric={metric} />)}
      </div>
    </article>
  );
}

function CampaignReplayTimeline({ stages, replayIndex, onSelect }) {
  return (
    <section className="rounded-[28px] border border-white/10 bg-white/5 p-5 backdrop-blur-xl shadow-[0_18px_50px_rgba(15,23,42,0.28)]">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Campaign Timeline Replay</div>
          <h3 className="mt-2 text-2xl font-semibold text-white">Synchronized campaign evolution</h3>
        </div>
        <div className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-xs font-semibold text-cyan-100">
          Continuously operating
        </div>
      </div>
      <div className="mt-6 grid gap-3 xl:grid-cols-7">
        {stages.map((stage, index) => {
          const active = index === replayIndex;
          return (
            <button
              key={stage.id}
              type="button"
              onClick={() => onSelect(index)}
              className={`rounded-[22px] border p-4 text-left transition ${active ? "border-violet-400/30 bg-slate-950/90 shadow-[0_0_0_1px_rgba(167,139,250,0.25),0_20px_60px_rgba(76,29,149,0.35)]" : "border-white/10 bg-slate-950/55 hover:border-white/20"}`}
            >
              <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">{stage.timestamp}</div>
              <div className="mt-3 text-sm font-semibold text-white">{stage.title}</div>
              <div className="mt-3 text-sm text-slate-300">{stage.metric}</div>
              <div className={`mt-4 inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${active ? "bg-violet-400/15 text-violet-100" : "bg-white/5 text-slate-300"}`}>{stage.spike_label}</div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function AudienceJourneyVisualization({ journey }) {
  return (
    <section className="rounded-[28px] border border-white/10 bg-white/5 p-5 backdrop-blur-xl shadow-[0_18px_50px_rgba(15,23,42,0.28)]">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Audience Journey Visualization</div>
        <h3 className="mt-2 text-2xl font-semibold text-white">From content discovery to ecosystem conversion</h3>
      </div>
      <div className="mt-6 space-y-3">
        {journey.map((step, index) => {
          const width = Math.max(12, Math.round(step.audience_percent));
          return (
            <div key={step.id} className="rounded-[22px] border border-white/10 bg-slate-950/60 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/5 text-xs font-semibold text-white">{index + 1}</div>
                  <div>
                    <div className="text-sm font-semibold text-white">{step.stage}</div>
                    <div className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-400">{step.lead_quality}</div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-lg font-semibold text-white">{Number(step.people).toLocaleString()}</div>
                  <div className="text-xs font-semibold text-slate-400">{step.audience_percent}% of audience</div>
                </div>
              </div>
              <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-white/10">
                <div className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-violet-500 to-emerald-400 transition-all duration-1000" style={{ width: `${width}%` }} />
              </div>
              <div className="mt-3 text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">{step.velocity_label}</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function OrchestrationVisibility({ events, activeIndex }) {
  return (
    <section className="rounded-[28px] border border-white/10 bg-white/5 p-5 backdrop-blur-xl shadow-[0_18px_50px_rgba(15,23,42,0.28)]">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">AI Orchestration Visibility</div>
        <h3 className="mt-2 text-2xl font-semibold text-white">Strategic actions, not technical logs</h3>
      </div>
      <div className="mt-6 space-y-3">
        {events.map((event, index) => {
          const active = index <= activeIndex % events.length;
          return (
            <div key={event.id} className={`rounded-[22px] border p-4 transition ${active ? "border-emerald-400/25 bg-emerald-400/10" : "border-white/10 bg-slate-950/60"}`}>
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-semibold text-white">{event.title}</div>
                <div className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${active ? "bg-emerald-400/15 text-emerald-100" : "bg-white/5 text-slate-300"}`}>{event.moment}</div>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-200">{event.translation}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function WowMoments({ items }) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {items.map((item) => (
        <article key={item.id} className="rounded-[24px] border border-violet-400/20 bg-gradient-to-br from-violet-500/10 via-slate-950/80 to-cyan-400/10 p-5 shadow-[0_18px_50px_rgba(91,33,182,0.28)]">
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-violet-200">Autonomous system moment</div>
          <h4 className="mt-3 text-lg font-semibold text-white">{item.title}</h4>
          <p className="mt-3 text-sm leading-6 text-slate-300">{item.detail}</p>
          <div className="mt-4 inline-flex rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-xs font-semibold text-cyan-100">{item.metric}</div>
        </article>
      ))}
    </div>
  );
}

function SceneRunbookRail({ scenes, activeSceneId, onSelect }) {
  return (
    <div className="grid gap-3 xl:grid-cols-7">
      {scenes.map((scene) => {
        const active = scene.id === activeSceneId;
        return (
          <button
            key={scene.id}
            type="button"
            onClick={() => onSelect(scene.id)}
            className={`rounded-[20px] border p-4 text-left transition ${active ? "border-cyan-400/30 bg-cyan-400/10 shadow-[0_0_0_1px_rgba(34,211,238,0.18),0_20px_60px_rgba(8,145,178,0.18)]" : "border-white/10 bg-slate-950/50 hover:border-white/20"}`}
          >
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">{scene.label}</div>
            <div className="mt-2 text-sm font-semibold text-white">{scene.title}</div>
            <div className="mt-3 text-xs text-slate-300">{scene.pace}</div>
          </button>
        );
      })}
    </div>
  );
}

function ScreenshotStateRail({ states, activeStateId, onSelect }) {
  return (
    <div className="flex flex-wrap gap-2">
      {states.map((item) => {
        const active = item.id === activeStateId;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onSelect(item.id)}
            className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${active ? "border-violet-400/30 bg-violet-400/15 text-violet-100" : "border-white/10 bg-white/5 text-slate-300 hover:border-white/20 hover:text-white"}`}
          >
            {item.label} · {item.title}
          </button>
        );
      })}
    </div>
  );
}

function PresenterOverlay({ scene, wowMoment, selectedPace, qaItems, activeQuestionId, onSelectQuestion }) {
  const activeQuestion = qaItems.find((item) => item.id === activeQuestionId) || qaItems[0] || null;

  return (
    <aside className="fixed bottom-5 right-5 z-50 hidden w-[360px] rounded-[28px] border border-white/10 bg-slate-950/88 p-5 text-white shadow-[0_30px_80px_rgba(2,6,23,0.55)] backdrop-blur-2xl 2xl:block">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-200">Presenter Mode</div>
          <h3 className="mt-2 text-lg font-semibold text-white">{scene?.title}</h3>
        </div>
        <div className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2.5 py-1 text-[11px] font-semibold text-cyan-100">Hidden from export states</div>
      </div>

      <div className="mt-4 rounded-[22px] border border-white/10 bg-white/5 p-4">
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Presenter Notes</div>
        <p className="mt-2 text-sm leading-6 text-slate-200">{scene?.presenter_notes}</p>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="rounded-[22px] border border-white/10 bg-white/5 p-4">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Pacing</div>
          <div className="mt-2 text-sm font-semibold text-white">{scene?.pace}</div>
          <p className="mt-2 text-xs leading-5 text-slate-300">{selectedPace?.note}</p>
        </div>
        <div className="rounded-[22px] border border-white/10 bg-white/5 p-4">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Wow Moment</div>
          <div className="mt-2 text-sm font-semibold text-white">{wowMoment?.title}</div>
          <p className="mt-2 text-xs leading-5 text-cyan-100">{wowMoment?.metric}</p>
        </div>
      </div>

      <div className="mt-4 rounded-[22px] border border-white/10 bg-white/5 p-4">
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Stakeholder Talking Points</div>
        <div className="mt-3 space-y-2">
          {(scene?.talking_points || []).map((point) => (
            <div key={point} className="flex items-start gap-2 text-sm leading-6 text-slate-200">
              <CircleDot className="mt-1 h-3.5 w-3.5 shrink-0 text-cyan-200" />
              <span>{point}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 rounded-[22px] border border-white/10 bg-white/5 p-4">
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Key KPI Callouts</div>
        <div className="mt-3 flex flex-wrap gap-2">
          {(scene?.kpi_callouts || []).map((item) => (
            <span key={item} className="rounded-full border border-white/10 bg-slate-950/60 px-3 py-1 text-xs font-semibold text-white">{item}</span>
          ))}
        </div>
      </div>

      <div className="mt-4 rounded-[22px] border border-violet-400/20 bg-violet-400/10 p-4">
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-violet-100">Operator Hint</div>
        <p className="mt-2 text-sm leading-6 text-violet-50">{scene?.operator_hint}</p>
      </div>

      <div className="mt-4 rounded-[22px] border border-white/10 bg-white/5 p-4">
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Stakeholder Q&A</div>
        <div className="mt-3 flex flex-wrap gap-2">
          {qaItems.map((item) => {
            const active = item.id === activeQuestionId;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelectQuestion(item.id)}
                className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${active ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100" : "border-white/10 bg-slate-950/60 text-slate-300 hover:border-white/20 hover:text-white"}`}
              >
                {item.question}
              </button>
            );
          })}
        </div>
        {activeQuestion ? (
          <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/60 p-4">
            <div className="text-sm font-semibold text-white">{activeQuestion.question}</div>
            <p className="mt-2 text-sm leading-6 text-slate-200">{activeQuestion.answer}</p>
            <p className="mt-2 text-xs leading-5 text-cyan-100">{activeQuestion.emphasis}</p>
          </div>
        ) : null}
      </div>
    </aside>
  );
}

export default function ExecutiveDemoTab({ demoMode, onNavigate }) {
  const [state, setState] = useState(() => getExecutiveDemoState());
  const [autoPlay, setAutoPlay] = useState(true);
  const [commandMode, setCommandMode] = useState(true);
  const [presentationStateId, setPresentationStateId] = useState(() => getExecutiveDemoState().presentation_states?.[0]?.id || "prelaunch");
  const [sceneId, setSceneId] = useState(() => getExecutiveDemoState().runbook_scenes?.[0]?.id || "scene-1");
  const [paceId, setPaceId] = useState(() => getExecutiveDemoState().pacing_presets?.find((item) => item.id === "medium")?.id || getExecutiveDemoState().pacing_presets?.[0]?.id || "medium");
  const [screenshotStateId, setScreenshotStateId] = useState(() => getExecutiveDemoState().screenshot_states?.[0]?.id || "overview");
  const [exportModeId, setExportModeId] = useState(() => getExecutiveDemoState().export_modes?.[0]?.id || "live");
  const [presenterMode, setPresenterMode] = useState(true);
  const [activeQuestionId, setActiveQuestionId] = useState(() => getExecutiveDemoState().stakeholder_qa?.[0]?.id || null);
  const [replayIndex, setReplayIndex] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(() => Boolean(typeof document !== "undefined" && document.fullscreenElement));

  function syncState() {
    setState(getExecutiveDemoState());
  }

  function needsExecutiveDemoReset(nextState) {
    return !nextState?.executive_summary?.active_campaigns
      || !(nextState?.presentation_states || []).length
      || !(nextState?.kpi_categories || []).length
      || !(nextState?.replay_timeline || []).length
      || !(nextState?.wow_moments || []).length
      || !(nextState?.runbook_scenes || []).length
      || !(nextState?.screenshot_states || []).length
      || !(nextState?.export_modes || []).length
      || !(nextState?.pacing_presets || []).length
      || !(nextState?.stakeholder_qa || []).length
        || !(nextState?.claim_guardrails || []).length
        || !(nextState?.audio_clips || []).length
        || !(nextState?.content_ideas || []).length
        || !(nextState?.prompt_generations || []).length
        || !(nextState?.asset_renders || []).some((item) => String(item.preview_url || "").endsWith(".mp4"))
        || (nextState?.campaign_packs || []).every((item) => Number(item.render_ids?.length || 0) < 3);
  }

  function jumpToPhase(phaseId) {
    setExecutiveDemoPhase(phaseId);
    syncState();
    const nextIndex = (state.replay_timeline || []).findIndex((stage) => Number(stage.phase) === Number(phaseId));
    if (nextIndex >= 0) setReplayIndex(nextIndex);
  }

  function selectPresentationState(nextId) {
    setPresentationStateId(nextId);
    const nextState = (state.presentation_states || []).find((item) => item.id === nextId);
    if (!nextState) return;
    setExecutiveDemoPhase(nextState.phase);
    syncState();
    const nextIndex = (state.replay_timeline || []).findIndex((stage) => Number(stage.phase) >= Number(nextState.phase));
    setReplayIndex(nextIndex >= 0 ? nextIndex : 0);
  }

  function selectScene(nextSceneId) {
    const nextScene = (state.runbook_scenes || []).find((item) => item.id === nextSceneId);
    if (!nextScene) return;
    setSceneId(nextSceneId);
    if (nextScene.presentation_state_id) {
      setPresentationStateId(nextScene.presentation_state_id);
    }
    if (nextScene.screenshot_state_id) {
      setScreenshotStateId(nextScene.screenshot_state_id);
    }
    if (nextScene.phase) {
      setExecutiveDemoPhase(nextScene.phase);
      const nextIndex = (state.replay_timeline || []).findIndex((stage) => Number(stage.phase) >= Number(nextScene.phase));
      if (nextIndex >= 0) setReplayIndex(nextIndex);
    }
    syncState();
  }

  function selectScreenshotState(nextId) {
    const nextState = (state.screenshot_states || []).find((item) => item.id === nextId);
    if (!nextState) return;
    setScreenshotStateId(nextId);
    if (nextState.presentation_state_id) {
      selectPresentationState(nextState.presentation_state_id);
    }
  }

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else {
        await document.documentElement.requestFullscreen?.();
      }
    } catch {
      // Fullscreen is presentation-only sugar; keep Command Mode usable without it.
    }
  }

  function resetExecutiveStory() {
    resetDemoData();
    setReplayIndex(0);
    setPresentationStateId(getExecutiveDemoState().presentation_states?.[0]?.id || "prelaunch");
    setSceneId(getExecutiveDemoState().runbook_scenes?.[0]?.id || "scene-1");
    setPaceId(getExecutiveDemoState().pacing_presets?.find((item) => item.id === "medium")?.id || getExecutiveDemoState().pacing_presets?.[0]?.id || "medium");
    setScreenshotStateId(getExecutiveDemoState().screenshot_states?.[0]?.id || "overview");
    setExportModeId(getExecutiveDemoState().export_modes?.[0]?.id || "live");
    setPresenterMode(true);
    setActiveQuestionId(getExecutiveDemoState().stakeholder_qa?.[0]?.id || null);
    syncState();
    setAutoPlay(true);
  }

  useEffect(() => {
    if (!demoMode) return undefined;
    const sync = () => {
      const nextState = getExecutiveDemoState();
      if (needsExecutiveDemoReset(nextState)) {
        resetDemoData();
        const resetState = getExecutiveDemoState();
        setState(resetState);
        setReplayIndex(0);
        setPresentationStateId(resetState.presentation_states?.[0]?.id || "prelaunch");
        setSceneId(resetState.runbook_scenes?.[0]?.id || "scene-1");
        setScreenshotStateId(resetState.screenshot_states?.[0]?.id || "overview");
        return;
      }
      setState(nextState);
    };
    window.addEventListener("signalforge-demo-change", sync);
    sync();
    return () => window.removeEventListener("signalforge-demo-change", sync);
  }, [demoMode]);

  useEffect(() => {
    if (!commandMode) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [commandMode]);

  useEffect(() => {
    const syncFullscreen = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", syncFullscreen);
    return () => document.removeEventListener("fullscreenchange", syncFullscreen);
  }, []);

  useEffect(() => {
    const exportMode = (state.export_modes || []).find((item) => item.id === exportModeId);
    if (exportMode?.presenter_overlay === false && presenterMode) {
      setPresenterMode(false);
    }
  }, [exportModeId, presenterMode, state.export_modes]);

  useEffect(() => {
    const sceneForPhase = (state.runbook_scenes || []).find((item) => Number(item.phase) === Number(state.active_phase));
    if (sceneForPhase && sceneForPhase.id !== sceneId) {
      setSceneId(sceneForPhase.id);
    }
  }, [sceneId, state.active_phase, state.runbook_scenes]);

  useEffect(() => {
    if (!demoMode || !autoPlay || !commandMode) return undefined;
    if (!(state.replay_timeline || []).length) return undefined;
    const pace = (state.pacing_presets || []).find((item) => item.id === paceId)?.interval_ms || 2300;
    const timer = window.setTimeout(() => {
      const nextIndex = (replayIndex + 1) % state.replay_timeline.length;
      const nextStage = state.replay_timeline[nextIndex];
      setReplayIndex(nextIndex);
      if (nextStage?.phase) {
        setExecutiveDemoPhase(nextStage.phase);
      } else {
        nextExecutiveDemoPhase();
      }
      syncState();
    }, pace);
    return () => window.clearTimeout(timer);
  }, [autoPlay, commandMode, demoMode, paceId, replayIndex, state.pacing_presets, state.replay_timeline]);

  const active = state.active;
  const ActiveIcon = PHASE_ICONS[active?.key] || Sparkles;
  const presentationState = (state.presentation_states || []).find((item) => item.id === presentationStateId) || state.presentation_states?.[0] || null;
  const runbookScenes = state.runbook_scenes || [];
  const currentScene = runbookScenes.find((item) => item.id === sceneId) || runbookScenes.find((item) => Number(item.phase) === Number(state.active_phase)) || runbookScenes[0] || null;
  const sceneIndex = Math.max(0, runbookScenes.findIndex((item) => item.id === currentScene?.id));
  const pacingPresets = state.pacing_presets || [];
  const selectedPace = pacingPresets.find((item) => item.id === paceId) || pacingPresets[0] || null;
  const screenshotStates = state.screenshot_states || [];
  const selectedScreenshotState = screenshotStates.find((item) => item.id === screenshotStateId) || screenshotStates[0] || null;
  const exportModes = state.export_modes || [];
  const selectedExportMode = exportModes.find((item) => item.id === exportModeId) || exportModes[0] || null;
  const stakeholderQa = state.stakeholder_qa || [];
  const currentWowMoment = (state.wow_moments || []).find((item) => item.id === currentScene?.wow_moment_id) || state.wow_moments?.[0] || null;
  const replayStage = state.replay_timeline?.[replayIndex] || null;
  const progressWidth = `${Math.max(12, Math.round(((state.active_phase || 1) / Math.max(1, state.total_phases || 6)) * 100))}%`;
  const activeSectionLabel = SECTION_LABELS[active?.section] || active?.section || "Linked surface";
  const executiveSummary = state.executive_summary || {};
  const audienceGrowthMetrics = (state.kpi_categories || []).find((group) => group.key === "audience_growth")?.metrics || [];
  const revenueMetrics = (state.kpi_categories || []).find((group) => group.key === "revenue_metrics")?.metrics || [];
  const growthAccountsLive = executiveSummary.growth_accounts_live || audienceGrowthMetrics.find((metric) => metric.label === "Account expansion")?.value || state.growth_accounts?.length || 0;
  const projectedMrr = executiveSummary.projected_mrr || revenueMetrics.find((metric) => metric.label === "Projected MRR")?.value || state.snapshot?.projected_revenue || 0;
  const campaignRoi = executiveSummary.campaign_roi || revenueMetrics.find((metric) => metric.label === "Campaign ROI")?.value || 0;
  const activeCampaigns = executiveSummary.active_campaigns || state.campaign_packs?.length || state.presentation_states?.length || 0;
  const activeGuardrails = (state.claim_guardrails || []).filter((item) => item.applies_to.includes(screenshotStateId) || item.applies_to.includes(active?.key) || (currentScene?.phase === 6 && item.applies_to.includes("summary"))).slice(0, 2);
  const presenterVisible = presenterMode && selectedExportMode?.presenter_overlay !== false;
  const heroMetrics = useMemo(() => {
    if (!active) return [];
    return [
      {
        label: "Followers",
        value: Number(state.snapshot.followers || 0),
        tone: "blue",
        helper: "Synthetic audience growth increases as each phase advances.",
      },
      {
        label: "Engagement rate",
        value: Number(state.snapshot.engagement_rate || 0),
        suffix: "%",
        tone: "violet",
        helper: "Signals rise as content routing and DM triggers kick in.",
      },
      {
        label: "Leads captured",
        value: Number(state.snapshot.leads_captured || 0),
        tone: "amber",
        helper: "Lead capture compounds across comments, DMs, and offer delivery.",
      },
      {
        label: "Projected revenue",
        value: Number(state.snapshot.projected_revenue || 0),
        prefix: "$",
        tone: "emerald",
        helper: "Revenue storytelling closes the narrative with ecosystem impact.",
      },
    ];
  }, [active, state.snapshot]);

  const commandSummaryTiles = [
    {
      label: "Active campaigns",
      value: Number(activeCampaigns || 0).toLocaleString(),
      helper: "High-level growth systems currently in motion.",
      accent: "violet",
    },
    {
      label: "Growth accounts live",
      value: Number(growthAccountsLive || 0).toLocaleString(),
      helper: "Distribution network currently carrying the message.",
      accent: "blue",
    },
    {
      label: "Projected MRR",
      value: `$${Number(projectedMrr || 0).toLocaleString()}`,
      helper: "Recurring revenue trajectory from the current funnel state.",
      accent: "emerald",
    },
    {
      label: "Campaign ROI",
      value: `${Number(campaignRoi || 0).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}x`,
      helper: executiveSummary.campaign_health || "Scaling efficiently",
      accent: "amber",
    },
  ];

  if (!demoMode) {
    return (
      <section className="rounded-3xl border border-indigo-200 bg-indigo-50 p-8 shadow-sm">
        <div className="flex items-start gap-3">
          <Shield className="mt-1 h-5 w-5 text-indigo-600" />
          <div>
            <h2 className="text-xl font-semibold text-indigo-950">John Maxwell Executive Demo</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-indigo-900">
              Switch to Demo Mode to open the executive walkthrough. This experience is browser-only, uses synthetic growth data, and never calls posting, DM, CRM, or checkout integrations.
            </p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <div className="space-y-6">
      {commandMode ? (
        <section className={`fixed inset-0 z-40 overflow-y-auto bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.12),_transparent_28%),radial-gradient(circle_at_top_right,_rgba(129,140,248,0.18),_transparent_34%),linear-gradient(180deg,#020617_0%,#0f172a_42%,#111827_100%)] text-white transition-all duration-700 ${selectedExportMode?.id !== "live" ? "[&_button]:transition-colors" : ""}`}>
          <div className="mx-auto min-h-screen max-w-[1600px] px-5 py-6 lg:px-8 lg:py-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="max-w-4xl">
                <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-slate-200">
                  <Bot className="h-3.5 w-3.5" />
                  {state.command_mode_title || "SignalForge Executive Command Mode"}
                </div>
                <h2 className="mt-4 text-5xl font-semibold tracking-tight text-white">{presentationState?.title || state.narrative_title}</h2>
                <p className="mt-3 max-w-3xl text-base leading-8 text-slate-300">{presentationState?.summary || state.command_mode_subtitle}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-xs font-semibold text-cyan-100">
                    <Gauge className="h-3.5 w-3.5" />
                    {currentScene?.label} · {currentScene?.key_message}
                  </div>
                  <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-slate-200">
                    Export: {selectedExportMode?.label}
                  </div>
                  <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-slate-200">
                    Pacing: {selectedPace?.label}
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {(state.presentation_states || []).map((item) => {
                    const selected = item.id === presentationStateId;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => selectPresentationState(item.id)}
                        className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${selected ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100" : "border-white/10 bg-white/5 text-slate-300 hover:border-white/20 hover:text-white"}`}
                      >
                        {item.label} · {item.title}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={() => setPresenterMode((value) => !value)}
                  disabled={selectedExportMode?.presenter_overlay === false}
                  className={`inline-flex h-11 items-center gap-2 rounded-full border px-4 text-sm font-semibold transition ${selectedExportMode?.presenter_overlay === false ? "border-white/10 bg-white/5 text-slate-500" : presenterVisible ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100 hover:bg-cyan-400/20" : "border-white/10 bg-white/5 text-white hover:bg-white/10"}`}
                >
                  <CircleDot className="h-4 w-4" />
                  {presenterVisible ? "Hide Presenter Mode" : "Show Presenter Mode"}
                </button>
                <button type="button" onClick={() => setAutoPlay((value) => !value)} className="inline-flex h-11 items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 text-sm font-semibold text-white transition hover:bg-white/10">
                  {autoPlay ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                  {autoPlay ? "Pause Replay" : "Resume Replay"}
                </button>
                <button type="button" onClick={toggleFullscreen} className="inline-flex h-11 items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 text-sm font-semibold text-white transition hover:bg-white/10">
                  {isFullscreen ? "Exit Fullscreen" : "Enter Fullscreen"}
                </button>
                <button type="button" onClick={() => onNavigate(active?.section || "ingest")} className="inline-flex h-11 items-center gap-2 rounded-full border border-violet-400/20 bg-violet-400/10 px-4 text-sm font-semibold text-violet-100 transition hover:bg-violet-400/20">
                  Open Workflow Layer
                  <ChevronRight className="h-4 w-4" />
                </button>
                <button type="button" onClick={resetExecutiveStory} className="inline-flex h-11 items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 text-sm font-semibold text-white transition hover:bg-white/10">
                  <RefreshCw className="h-4 w-4" />
                  Reset Story
                </button>
                <button type="button" onClick={() => setCommandMode(false)} className="inline-flex h-11 items-center gap-2 rounded-full bg-white px-4 text-sm font-semibold text-slate-950 transition hover:bg-slate-100">
                  Exit Command Mode
                </button>
              </div>
            </div>

            <section className="mt-6 rounded-[30px] border border-white/10 bg-white/5 p-5 backdrop-blur-xl shadow-[0_18px_50px_rgba(15,23,42,0.28)] transition-all duration-700">
              <div className="grid gap-4 xl:grid-cols-[1.35fr_0.65fr]">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Executive Runbook</div>
                  <h3 className="mt-2 text-2xl font-semibold text-white">{currentScene?.title}</h3>
                  <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-300">{currentScene?.goal}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {activeGuardrails.map((item) => (
                      <GuardrailBadge key={item.id} label={item.label} />
                    ))}
                  </div>
                  <div className="mt-5 flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={() => selectScene(runbookScenes[Math.max(0, sceneIndex - 1)]?.id || currentScene?.id)}
                      className="inline-flex h-11 items-center gap-2 rounded-full border border-white/10 bg-slate-950/60 px-4 text-sm font-semibold text-white transition hover:bg-slate-950/80"
                    >
                      <ArrowLeft className="h-4 w-4" />
                      Previous Scene
                    </button>
                    <button
                      type="button"
                      onClick={() => selectScene(runbookScenes[Math.min(runbookScenes.length - 1, sceneIndex + 1)]?.id || currentScene?.id)}
                      className="inline-flex h-11 items-center gap-2 rounded-full border border-white/10 bg-slate-950/60 px-4 text-sm font-semibold text-white transition hover:bg-slate-950/80"
                    >
                      Next Scene
                      <ArrowRight className="h-4 w-4" />
                    </button>
                  </div>
                </div>
                <div className="space-y-4 rounded-[24px] border border-white/10 bg-slate-950/55 p-4">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Presentation Output</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {exportModes.map((mode) => {
                        const activeMode = mode.id === exportModeId;
                        return (
                          <button
                            key={mode.id}
                            type="button"
                            onClick={() => setExportModeId(mode.id)}
                            className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${activeMode ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100" : "border-white/10 bg-white/5 text-slate-300 hover:border-white/20 hover:text-white"}`}
                          >
                            {mode.label}
                          </button>
                        );
                      })}
                    </div>
                    <p className="mt-3 text-sm leading-6 text-slate-300">{selectedExportMode?.summary}</p>
                  </div>
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Presentation Speed</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {pacingPresets.map((preset) => {
                        const activePreset = preset.id === paceId;
                        return (
                          <button
                            key={preset.id}
                            type="button"
                            onClick={() => setPaceId(preset.id)}
                            className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${activePreset ? "border-violet-400/30 bg-violet-400/15 text-violet-100" : "border-white/10 bg-white/5 text-slate-300 hover:border-white/20 hover:text-white"}`}
                          >
                            {preset.label}
                          </button>
                        );
                      })}
                    </div>
                    <p className="mt-3 text-sm leading-6 text-slate-300">{selectedPace?.note}</p>
                  </div>
                </div>
              </div>

              <div className="mt-5">
                <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Guided Scene Flow</div>
                <div className="mt-3">
                  <SceneRunbookRail scenes={runbookScenes} activeSceneId={currentScene?.id} onSelect={selectScene} />
                </div>
              </div>

              <div className="mt-5">
                <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Screenshot Choreography</div>
                <div className="mt-3">
                  <ScreenshotStateRail states={screenshotStates} activeStateId={selectedScreenshotState?.id} onSelect={selectScreenshotState} />
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-300">{selectedScreenshotState?.focus}</p>
              </div>
            </section>

            <div className="mt-6 grid gap-4 lg:grid-cols-4">
              {commandSummaryTiles.map((tile) => (
                <CommandSummaryTile key={tile.label} {...tile} />
              ))}
            </div>

            <div className="mt-6 grid gap-4 xl:grid-cols-[1.45fr_0.95fr]">
              <div className="space-y-4">
                <CampaignReplayTimeline
                  stages={state.replay_timeline || []}
                  replayIndex={replayIndex}
                  onSelect={(index) => {
                    setReplayIndex(index);
                    const stage = state.replay_timeline?.[index];
                    if (stage?.phase) {
                      setExecutiveDemoPhase(stage.phase);
                      syncState();
                    }
                  }}
                />
                <div className="grid gap-4 xl:grid-cols-2">
                  {(state.kpi_categories || []).map((group) => (
                    <CommandMetricGroup key={group.key} group={group} />
                  ))}
                </div>
              </div>
              <div className="space-y-4">
                <section className="rounded-[28px] border border-white/10 bg-white/5 p-5 backdrop-blur-xl shadow-[0_18px_50px_rgba(15,23,42,0.28)]">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Executive Summary Mode</div>
                  <h3 className="mt-2 text-2xl font-semibold text-white">Is the system working?</h3>
                  <div className="mt-5 space-y-3">
                    {[
                      ["Top-performing asset", state.executive_summary?.top_asset],
                      ["Active state", active?.state_label],
                      ["Replay timestamp", replayStage?.timestamp],
                      ["Linked surface", activeSectionLabel],
                    ].map(([label, value]) => (
                      <div key={label} className="flex items-center justify-between rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3">
                        <div className="text-sm text-slate-300">{label}</div>
                        <div className="text-sm font-semibold text-white">{value}</div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-5 rounded-[24px] border border-white/10 bg-slate-950/60 p-4">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Key Message</div>
                    <p className="mt-2 text-sm leading-6 text-white">{currentScene?.key_message}</p>
                  </div>
                  <div className="mt-5 rounded-[24px] border border-cyan-400/20 bg-cyan-400/10 p-4">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-100">Autonomous perception</div>
                    <p className="mt-2 text-sm leading-6 text-cyan-50">SignalForge is autonomously discovering assets, routing demand, activating nurture flows, and surfacing executive growth signals without exposing operational complexity.</p>
                  </div>
                </section>
                <OrchestrationVisibility events={state.orchestration_events || []} activeIndex={replayIndex} />
              </div>
            </div>

            <div className="mt-6 grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
              <AudienceJourneyVisualization journey={state.audience_journey || []} />
              <section className="rounded-[28px] border border-white/10 bg-white/5 p-5 backdrop-blur-xl shadow-[0_18px_50px_rgba(15,23,42,0.28)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Autonomous System Moment</div>
                <h3 className="mt-2 text-2xl font-semibold text-white">{currentWowMoment?.title || replayStage?.spike_label || "Campaign scaling detected"}</h3>
                <p className="mt-3 text-sm leading-6 text-slate-300">The campaign replay, journey engine, and orchestration layer are synchronized so executives feel the system responding as momentum builds.</p>
                <div className="mt-6 rounded-[24px] border border-white/10 bg-slate-950/60 p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Current replay stage</div>
                      <div className="mt-2 text-xl font-semibold text-white">{replayStage?.title}</div>
                    </div>
                    <div className="rounded-full border border-violet-400/20 bg-violet-400/10 px-3 py-1 text-xs font-semibold text-violet-100">{replayStage?.metric}</div>
                  </div>
                  <div className="mt-5 h-2.5 overflow-hidden rounded-full bg-white/10">
                    <div className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-violet-500 to-emerald-400 transition-all duration-1000" style={{ width: `${Math.max(14, ((replayIndex + 1) / Math.max(1, state.replay_timeline?.length || 1)) * 100)}%` }} />
                  </div>
                  <div className="mt-4 flex items-center justify-between text-sm text-slate-300">
                    <span>{presentationState?.status}</span>
                    <span>{replayStage?.timestamp}</span>
                  </div>
                </div>
                <div className="mt-4 rounded-[24px] border border-cyan-400/20 bg-cyan-400/10 p-4 text-sm leading-6 text-cyan-50">
                  {currentWowMoment?.detail}
                </div>
              </section>
            </div>

            <div className="mt-6">
              <WowMoments items={state.wow_moments || []} />
            </div>
          </div>
          {presenterVisible ? (
            <PresenterOverlay
              scene={currentScene}
              wowMoment={currentWowMoment}
              selectedPace={selectedPace}
              qaItems={stakeholderQa}
              activeQuestionId={activeQuestionId}
              onSelectQuestion={setActiveQuestionId}
            />
          ) : null}
        </section>
      ) : null}

      <section className="overflow-hidden rounded-[28px] border border-slate-200 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 p-6 text-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-slate-200">
              <TrendingUp className="h-3.5 w-3.5" />
              Executive Command Mode
            </div>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-white">Mission control for audience growth, nurture, and conversion</h2>
            <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-300">Phase 3 layers a cinematic executive command surface above the walkthrough so the system feels autonomous, synchronized, and boardroom-ready.</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" onClick={() => setCommandMode(true)} className="inline-flex h-11 items-center gap-2 rounded-full bg-white px-4 text-sm font-semibold text-slate-950 transition hover:bg-slate-100">
              Launch Command Mode
            </button>
            <button type="button" onClick={toggleFullscreen} className="inline-flex h-11 items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 text-sm font-semibold text-white transition hover:bg-white/10">
              {isFullscreen ? "Exit Fullscreen" : "Prepare Fullscreen"}
            </button>
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-[30px] border border-slate-200 bg-white shadow-sm">
        <div className="grid gap-0 xl:grid-cols-[1.15fr_0.85fr]">
          <div className="bg-[radial-gradient(circle_at_top_left,_rgba(129,140,248,0.22),_transparent_38%),linear-gradient(135deg,#020617_0%,#111827_42%,#172554_100%)] p-8 text-white">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-200">
              <Bot className="h-3.5 w-3.5" />
              Executive Story Layer
            </div>
            <h2 className="mt-4 text-4xl font-semibold tracking-tight text-white">{state.narrative_title || "John Maxwell Executive Growth Engine"}</h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-300">{state.narrative_subtitle}</p>
            <div className="mt-6 grid gap-4 md:grid-cols-3">
              {[
                ["Demo client", state.client_summary?.identity],
                ["What SignalForge is doing", state.client_summary?.mission],
                ["Environment", state.client_summary?.operator_view],
              ].map(([label, value]) => (
                <div key={label} className="rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">{label}</div>
                  <p className="mt-2 text-sm leading-6 text-slate-100">{value}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-slate-50 p-8">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">What is happening now</div>
                <h3 className="mt-2 text-2xl font-semibold text-slate-950">{active?.title}</h3>
              </div>
              <div className="rounded-2xl bg-slate-950 px-3 py-2 text-right text-white shadow-sm">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Current phase</div>
                <div className="mt-1 text-lg font-semibold">{active?.label}</div>
              </div>
            </div>
            <div className="mt-5 overflow-hidden rounded-full bg-slate-200">
              <div className="h-2 rounded-full bg-gradient-to-r from-slate-900 via-violet-600 to-cyan-400 transition-all duration-700" style={{ width: progressWidth }} />
            </div>
            <div className="mt-5 space-y-3">
              {[
                [active?.input_label, active?.input_detail],
                [active?.action_label, active?.action_detail],
                [active?.output_label, active?.output_detail],
                [active?.business_label, active?.business_detail],
              ].map(([label, value]) => (
                <div key={label} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">{label}</div>
                  <p className="mt-2 text-sm leading-6 text-slate-700">{value}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-5">
        {(state.summary_cards || []).map((card, index) => (
          <ExecutiveSummaryCard
            key={card.key || index}
            card={card}
            active={index + 1 === Number(state.active_phase || 1)}
          />
        ))}
      </section>

      <section className="overflow-hidden rounded-[28px] border border-slate-200 bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 p-8 text-white shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="max-w-4xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-200">
              <Bot className="h-3.5 w-3.5" />
              Executive Demo Layer
            </div>
            <h2 className="mt-4 text-3xl font-semibold tracking-tight text-white">SignalForge turns John Maxwell content operations into an executive growth narrative.</h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-300">
              Each phase shows the same chain of value: discover what the audience already responds to, generate faceless short-form assets, route those assets through approved growth accounts, capture intent, move prospects through leadership offers, and translate that activity into revenue opportunity.
            </p>
          </div>
          <div className="rounded-3xl border border-white/10 bg-white/5 p-4 shadow-lg backdrop-blur">
            <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Active state</div>
            <div className="mt-2 flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/10">
                <ActiveIcon className="h-6 w-6 text-violet-200" />
              </div>
              <div>
                <div className="text-lg font-semibold text-white">{active?.state_label}</div>
                <div className="text-sm text-slate-300">{active?.title}</div>
                <div className="mt-2 inline-flex items-center gap-2 rounded-full border border-violet-400/20 bg-violet-400/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-violet-100">
                  <CircleDot className="h-3.5 w-3.5" />
                  Linked surface: {activeSectionLabel}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <button type="button" onClick={() => { prevExecutiveDemoPhase(); syncState(); }} className="inline-flex h-10 items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 text-sm font-semibold text-white transition hover:bg-white/10">
            <ArrowLeft className="h-4 w-4" />
            Previous
          </button>
          <button type="button" onClick={() => { nextExecutiveDemoPhase(); syncState(); }} className="inline-flex h-10 items-center gap-2 rounded-full bg-white px-4 text-sm font-semibold text-slate-950 transition hover:bg-slate-100">
            Next Phase
            <ArrowRight className="h-4 w-4" />
          </button>
          <button type="button" onClick={() => setAutoPlay((value) => !value)} className="inline-flex h-10 items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 text-sm font-semibold text-white transition hover:bg-white/10">
            {autoPlay ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            {autoPlay ? "Pause Auto Play" : "Resume Auto Play"}
          </button>
          <button type="button" onClick={() => { resetDemoData(); syncState(); setAutoPlay(true); }} className="inline-flex h-10 items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 text-sm font-semibold text-white transition hover:bg-white/10">
            <RefreshCw className="h-4 w-4" />
            Reset Demo Story
          </button>
          <button type="button" onClick={() => onNavigate(active?.section || "ingest")} className="inline-flex h-10 items-center gap-2 rounded-full border border-violet-400/30 bg-violet-400/10 px-4 text-sm font-semibold text-violet-100 transition hover:bg-violet-400/20">
            Open Linked Surface
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </section>

      <NarrativeFlow steps={state.funnel_flow || []} activePhase={state.active_phase || 1} />

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Phase Navigation</div>
            <h3 className="mt-2 text-2xl font-semibold text-slate-950">{active?.title}</h3>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              {active?.proof_points?.[0] || "SignalForge advances a guided growth narrative across discovery, creation, distribution, engagement, funnel movement, and conversion."}
            </p>
          </div>
          <SectionRail timeline={state.timeline || []} active={active} onSelect={jumpToPhase} />
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-4">
          {heroMetrics.map((metric) => (
            <AnimatedMetricCard
              key={metric.label}
              label={metric.label}
              value={metric.value}
              prefix={metric.prefix}
              suffix={metric.suffix}
              tone={metric.tone}
              helper={metric.helper}
            />
          ))}
        </div>

        <div className="mt-6 grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
          <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Phase KPI Story</div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {(active?.kpis || []).map((metric) => (
                <div key={metric.label} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{metric.label}</div>
                  <div className="mt-3 text-2xl font-semibold text-slate-950">{formatMetric(metric)}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Why it matters</div>
            <div className="mt-4 space-y-3">
              {(active?.proof_points || []).map((point) => (
                <div key={point} className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-700">{point}</div>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {(active?.highlights || []).map((item) => (
                <span key={item} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">{item}</span>
              ))}
            </div>
            <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-950 p-4 text-white shadow-sm">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                <Gauge className="h-4 w-4" />
                Executive translation
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-200">{active?.business_detail}</p>
            </div>
          </div>
        </div>
      </section>

      <PhaseShowcase state={state} />

      <OperationalWorkflowShowcase state={state} />

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Presentation Readiness</div>
            <h3 className="mt-2 text-xl font-semibold text-slate-950">Cinematic demo safety boundary</h3>
          </div>
          <div className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
            <Shield className="h-3.5 w-3.5" />
            Browser-only simulation
          </div>
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          {[
            "No social APIs, DM APIs, CRM syncs, or checkout calls run in this experience.",
            "All metrics, engagement events, and funnel outcomes are deterministic synthetic records.",
            "The walkthrough reuses existing Creative Studio and Demo Mode architecture instead of creating a parallel system.",
          ].map((item) => (
            <div key={item} className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-700">{item}</div>
          ))}
        </div>
      </section>
    </div>
  );
}
