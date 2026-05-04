/**
 * PocDemoTab.jsx — SignalForge v10 POC Demo Mode
 *
 * Guided 13-step proof-of-concept walkthrough. All navigation is local
 * (localStorage) — no backend writes during demo walkthrough.
 *
 * Safety: simulation_only=true, advisory_only=true, outbound_actions_taken=0
 * on every seeded record. This component never calls api write methods.
 */

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  ChevronRight,
  ExternalLink,
  Flag,
  Info,
  List,
  Play,
  RefreshCw,
  Shield,
  Zap,
} from "lucide-react";
import {
  getDemoProgress,
  getDemoState,
  jumpDemoStep,
  nextDemoStep,
  prevDemoStep,
  resetDemoData,
  resetDemoProgress,
} from "../demoMode.js";

// ---------------------------------------------------------------------------
// Step definitions
// ---------------------------------------------------------------------------

const STEPS = [
  {
    id: 1,
    title: "Workspace & Safety",
    subtitle: "Understand the operating environment",
    section: "clients",
    sectionLabel: "Clients tab",
    proves: "SignalForge runs inside a named workspace with a defined client profile. All records in this demo are local-only synthetic data.",
    inspect: "Demo workspace slug, client profile record, compliance notes, permission flags.",
    safety: ["simulation_only=true on every record", "No MongoDB writes from demo navigation", "No external API calls or platform connections"],
    cta: "clients",
    ctaLabel: "View Client Profiles →",
    icon: Shield,
    color: "blue",
  },
  {
    id: 2,
    title: "Client Setup",
    subtitle: "Profile, permissions, content rules",
    section: "clients",
    sectionLabel: "Clients tab",
    proves: "The client profile defines brand permissions: likeness, voice, avatar, allowed content types, disallowed topics, and compliance notes.",
    inspect: "demo-client-1 (Demo Apex Roofing): likeness_permissions=false, voice_permissions=false, avatar_permissions=false.",
    safety: ["No real client data stored", "Permissions are advisory flags — no automation reads them to approve content"],
    cta: "clients",
    ctaLabel: "View Client Profile →",
    icon: Flag,
    color: "blue",
  },
  {
    id: 3,
    title: "Source Approval",
    subtitle: "Approve channels before any ingestion",
    section: "source-channels",
    sectionLabel: "Source Channels tab",
    proves: "Source channels must be explicitly approved for ingestion and reuse before any content is processed. No scraping without operator approval.",
    inspect: "demo-channel-1 (YouTube, approved_for_ingestion=true, approved_for_reuse=true). demo-channel-2 (Instagram, not yet approved).",
    safety: ["No scraping or download occurs from demo URLs", "approved_for_ingestion flag is operator-set, never auto-approved"],
    cta: "source-channels",
    ctaLabel: "View Source Channels →",
    icon: CheckCircle,
    color: "green",
  },
  {
    id: 4,
    title: "Content Intake",
    subtitle: "Discover and approve source content",
    section: "source-content",
    sectionLabel: "Source Content tab",
    proves: "Source content records represent discovered videos/posts. Each must be approved before transcript or snippet generation begins.",
    inspect: "2 demo source content records. demo-source-content-1 (approved, 8.2K views). demo-source-content-2 (approved, 3.9K views).",
    safety: ["No media downloaded — URL metadata only in demo", "source_url points to .invalid domain — no real network call possible"],
    cta: "source-content",
    ctaLabel: "View Source Content →",
    icon: Play,
    color: "purple",
  },
  {
    id: 5,
    title: "Transcript & Snippets",
    subtitle: "Audio → text → scored segments",
    section: "ingest",
    sectionLabel: "Ingest Pipeline tab",
    proves: "Transcript runs segment the audio into timestamped text blocks. Snippet generation scores each segment for hook potential, theme, and platform fit.",
    inspect: "demo-transcript-run-1 (4 segments, simulation_only=true). 4 demo snippets with scores 0.94, 0.88, 0.81, 0.76.",
    safety: ["FFmpeg runs locally — no cloud audio processing", "simulation_only=true on all transcript and segment records"],
    cta: "ingest",
    ctaLabel: "View Ingest Pipeline →",
    icon: Zap,
    color: "amber",
  },
  {
    id: 6,
    title: "Scoring & Hook Selection",
    subtitle: "Rank and approve the best hooks",
    section: "snippets",
    sectionLabel: "Snippets tab",
    proves: "Each snippet has a score (0–1), theme, hook angle, and platform fit. Operators review scores and approve or reject. Only approved snippets proceed.",
    inspect: "demo-snippet-1 score=0.94 (follow_up_system, approved). demo-snippet-4 score=0.88 (positioning, approved). demo-snippet-2/3 pending review.",
    safety: ["Score is advisory — no automatic approvals", "Snippet approval is always operator-gated"],
    cta: "snippets",
    ctaLabel: "View Snippets →",
    icon: Zap,
    color: "amber",
  },
  {
    id: 7,
    title: "Prompt Strategy",
    subtitle: "Design the visual brief for each hook",
    section: "prompts",
    sectionLabel: "Prompt Library tab",
    proves: "Each approved snippet gets a visual prompt: type, positive/negative prompt, camera direction, lighting, scene beats. All require operator review before render.",
    inspect: "3 demo prompt generations. Types: faceless_motivational, podcast_clip_visual, business_explainer. All have use_likeness=false.",
    safety: ["No likeness or voice cloning in any demo prompt", "Prompts cannot trigger renders until status=approved", "negative_prompt always includes 'identifiable person, likeness, voice cloning instructions'"],
    cta: "prompts",
    ctaLabel: "View Prompt Library →",
    icon: List,
    color: "indigo",
  },
  {
    id: 8,
    title: "Rendered Asset",
    subtitle: "Worker assembles the video locally",
    section: "renders",
    sectionLabel: "Rendered Assets tab",
    proves: "The SignalForge worker uses FFmpeg to assemble a local MP4 from prompt + snippet data. No cloud rendering. No content is published. Asset requires review before any use.",
    inspect: "demo-render-1 (approved, ffmpeg assembly, 30s, 1080×1920). demo-render-2 (needs_review). file_path=/tmp/signalforge_renders/.",
    safety: ["File written to local /tmp only", "outbound_actions_taken=0", "No CDN upload, no platform API call, no scheduling"],
    cta: "renders",
    ctaLabel: "View Rendered Assets →",
    icon: Play,
    color: "green",
  },
  {
    id: 9,
    title: "Performance Feedback",
    subtitle: "Record and analyze post-publish metrics",
    section: "performance-loop",
    sectionLabel: "Performance Loop tab",
    proves: "After an operator manually posts content outside SignalForge, they log the performance metrics. SignalForge generates an advisory summary — it does not post or schedule.",
    inspect: "demo-publog-1 (instagram reel, simulation_only=true, outbound=0). 2 performance records. Avg score 7.3. Top recommendation: double down on follow-up hook.",
    safety: ["publish log confirms SignalForge did NOT publish", "outbound_actions_taken=0 on all records", "performance summary is advisory only"],
    cta: "performance-loop",
    ctaLabel: "View Performance Loop →",
    icon: Zap,
    color: "amber",
  },
  {
    id: 10,
    title: "Campaign Pack",
    subtitle: "Bundle the full creative sprint",
    section: "campaign-packs",
    sectionLabel: "Campaign Packs tab",
    proves: "A campaign pack links source content, snippets, prompts, and renders into a named bundle. It's the unit of delivery for a creative sprint.",
    inspect: "demo-pack-1 (Demo: Apex Roofing Summer Growth Pack). Links: 1 source content, 2 snippets, 2 renders, 2 prompts. simulation_only=true.",
    safety: ["Pack creation does not publish anything", "Linking is metadata-only — no external actions"],
    cta: "campaign-packs",
    ctaLabel: "View Campaign Packs →",
    icon: List,
    color: "indigo",
  },
  {
    id: 11,
    title: "Campaign Report",
    subtitle: "Summarize results for the client",
    section: "campaign-packs",
    sectionLabel: "Campaign Packs → Report tab",
    proves: "A campaign report aggregates performance metrics, top performers, and operator recommendations into a structured document for client review.",
    inspect: "demo-report-1 (status=approved). Summary: avg score 7.3, top render demo-render-1 (score 8.4). Total views 6,900. Top hook: follow-up system.",
    safety: ["Report is advisory — no auto-actions triggered", "outbound_actions_taken=0", "Report review is operator-gated"],
    cta: "campaign-packs",
    ctaLabel: "View Campaign Report →",
    icon: CheckCircle,
    color: "green",
  },
  {
    id: 12,
    title: "Client Export",
    subtitle: "Deliver the package locally",
    section: "campaign-exports",
    sectionLabel: "Exports tab",
    proves: "The export package generates a local Markdown file with all campaign data. It is never uploaded, emailed, or sent anywhere by SignalForge.",
    inspect: "demo-export-1. export_path=/tmp/signalforge_exports/demo/. simulation_only=true. outbound=0.",
    safety: ["Export file is written locally to /tmp only", "No email, no upload, no CDN, no sharing API called", "Client must receive file through their own manual channel"],
    cta: "campaign-exports",
    ctaLabel: "View Exports →",
    icon: ExternalLink,
    color: "slate",
  },
  {
    id: 13,
    title: "Client Intelligence",
    subtitle: "Advisory insights from the full pipeline",
    section: "client-intelligence",
    sectionLabel: "Intelligence tab",
    proves: "Client intelligence synthesizes performance data, hook themes, and lead correlations into advisory recommendations. It is never used to auto-send messages or trigger actions.",
    inspect: "demo-intel-1 (advisory_only=true, simulation_only=true, outbound=0). Estimated ROI: 112.5. 2 lead-content correlations. Top recommendation: double down on follow-up hook.",
    safety: ["advisory_only=true — no automation reads this to trigger actions", "outbound_actions_taken=0 enforced on every intelligence record", "Correlations are informational only — no leads are contacted"],
    cta: "client-intelligence",
    ctaLabel: "View Client Intelligence →",
    icon: Info,
    color: "blue",
  },
];

// ---------------------------------------------------------------------------
// Color map
// ---------------------------------------------------------------------------
const COLOR = {
  blue: { bg: "bg-blue-50", border: "border-blue-200", text: "text-blue-700", icon: "text-blue-500", badge: "bg-blue-100 text-blue-700", progress: "bg-blue-500" },
  green: { bg: "bg-emerald-50", border: "border-emerald-200", text: "text-emerald-700", icon: "text-emerald-500", badge: "bg-emerald-100 text-emerald-700", progress: "bg-emerald-500" },
  amber: { bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-700", icon: "text-amber-500", badge: "bg-amber-100 text-amber-700", progress: "bg-amber-500" },
  purple: { bg: "bg-purple-50", border: "border-purple-200", text: "text-purple-700", icon: "text-purple-500", badge: "bg-purple-100 text-purple-700", progress: "bg-purple-500" },
  indigo: { bg: "bg-indigo-50", border: "border-indigo-200", text: "text-indigo-700", icon: "text-indigo-500", badge: "bg-indigo-100 text-indigo-700", progress: "bg-indigo-500" },
  slate: { bg: "bg-slate-50", border: "border-slate-200", text: "text-slate-700", icon: "text-slate-500", badge: "bg-slate-100 text-slate-700", progress: "bg-slate-500" },
};

// ---------------------------------------------------------------------------
// Safety Card
// ---------------------------------------------------------------------------
function SafetyCard({ items }) {
  return (
    <div className="rounded-lg border border-red-100 bg-red-50 p-4">
      <div className="mb-2 flex items-center gap-2">
        <Shield className="h-4 w-4 text-red-500" />
        <span className="text-xs font-semibold uppercase tracking-wide text-red-600">Safety Boundaries Active</span>
      </div>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-xs text-red-700">
            <span className="mt-0.5 text-red-400">•</span>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step indicator dots
// ---------------------------------------------------------------------------
function StepDots({ total, current, onJump }) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-1.5">
      {Array.from({ length: total }, (_, i) => i + 1).map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onJump(n)}
          title={`Jump to Step ${n}`}
          className={[
            "h-2.5 w-2.5 rounded-full transition-all",
            n < current ? "bg-blue-400 hover:bg-blue-500" :
            n === current ? "h-3 w-3 bg-blue-600 ring-2 ring-blue-300" :
            "bg-slate-200 hover:bg-slate-300",
          ].join(" ")}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function PocDemoTab({ demoMode, onNavigate }) {
  const [progress, setProgress] = useState(() => getDemoProgress());
  const [jumpTarget, setJumpTarget] = useState("");
  const [resetConfirm, setResetConfirm] = useState(false);
  const [demoState, setDemoState] = useState(() => getDemoState());

  // Sync on external demo-change events (e.g. Reset Demo from header)
  useEffect(() => {
    function sync() {
      setProgress(getDemoProgress());
      setDemoState(getDemoState());
    }
    window.addEventListener("signalforge-demo-change", sync);
    return () => window.removeEventListener("signalforge-demo-change", sync);
  }, []);

  const currentStep = progress.step || 0;
  const started = currentStep > 0;
  const completed = currentStep >= STEPS.length;
  const step = started && !completed ? STEPS[currentStep - 1] : null;
  const colors = step ? COLOR[step.color] : COLOR.blue;

  function handleStart() {
    const p = jumpDemoStep(1);
    setProgress(p);
  }

  function handleNext() {
    const p = nextDemoStep();
    setProgress(p);
  }

  function handlePrev() {
    const p = prevDemoStep();
    setProgress(p);
  }

  function handleJump(n) {
    const p = jumpDemoStep(n);
    setProgress(p);
    setJumpTarget("");
  }

  function handleReset() {
    resetDemoData();
    resetDemoProgress();
    setProgress({ step: 0, started: false, completed: false });
    setDemoState(getDemoState());
    setResetConfirm(false);
  }

  function handleCta(section) {
    if (onNavigate) onNavigate(section);
  }

  // ---------------------------------------------------------------------------
  // Render: Not in demo mode
  // ---------------------------------------------------------------------------
  if (!demoMode) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
        <AlertTriangle className="h-10 w-10 text-amber-400" />
        <h2 className="text-lg font-semibold text-slate-800">Demo Mode is Off</h2>
        <p className="max-w-sm text-sm text-slate-500">
          Switch to Demo Mode using the toggle in the header to access the POC Demo walkthrough.
          Demo Mode uses only local synthetic data — no MongoDB writes.
        </p>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Welcome / not started
  // ---------------------------------------------------------------------------
  if (!started) {
    return (
      <div className="mx-auto max-w-2xl space-y-6 py-10">
        {/* Header */}
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-100">
            <Play className="h-7 w-7 text-blue-600" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900">SignalForge POC Demo</h1>
          <p className="mt-2 text-sm text-slate-500">
            13-step guided walkthrough of the full social creative pipeline — from client setup through intelligence and export.
          </p>
        </div>

        {/* Safety notice */}
        <div className="rounded-xl border border-red-100 bg-red-50 p-5">
          <div className="mb-3 flex items-center gap-2">
            <Shield className="h-5 w-5 text-red-500" />
            <span className="font-semibold text-red-700">Client-Safe Demo — All Boundaries Enforced</span>
          </div>
          <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2">
            {[
              "No external publishing",
              "No email or DM sending",
              "No platform API calls",
              "No MongoDB writes during demo nav",
              "simulation_only=true on all records",
              "advisory_only=true on all intelligence",
              "outbound_actions_taken=0 everywhere",
              "Demo data stored in localStorage only",
            ].map((item) => (
              <li key={item} className="flex items-center gap-2 text-xs text-red-700">
                <CheckCircle className="h-3 w-3 flex-shrink-0 text-red-400" />
                {item}
              </li>
            ))}
          </ul>
        </div>

        {/* Step overview */}
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <h3 className="mb-3 text-sm font-semibold text-slate-700">13 Demo Steps</h3>
          <ol className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {STEPS.map((s) => (
              <li key={s.id} className="flex items-center gap-2 text-xs text-slate-600">
                <span className={`flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${COLOR[s.color].badge}`}>
                  {s.id}
                </span>
                {s.title}
              </li>
            ))}
          </ol>
        </div>

        {/* Data summary */}
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <h3 className="mb-3 text-sm font-semibold text-slate-700">Seeded Demo Data</h3>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              { label: "Snippets", value: (demoState.content_snippets || []).length },
              { label: "Prompt Gens", value: (demoState.prompt_generations || []).length },
              { label: "Renders", value: (demoState.asset_renders || []).length },
              { label: "Perf Records", value: (demoState.asset_performance_records || []).length },
              { label: "Campaign Packs", value: (demoState.campaign_packs || []).length },
              { label: "Intelligence", value: (demoState.client_intelligence || []).length },
              { label: "Correlations", value: (demoState.lead_content_correlations || []).length },
              { label: "Export Pkgs", value: (demoState.campaign_exports || []).length },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-lg bg-slate-50 p-2 text-center">
                <div className="text-xl font-bold text-slate-800">{value}</div>
                <div className="text-xs text-slate-500">{label}</div>
              </div>
            ))}
          </div>
        </div>

        <button
          type="button"
          onClick={handleStart}
          className="w-full rounded-xl bg-blue-600 px-6 py-4 text-base font-semibold text-white shadow-sm transition hover:bg-blue-700 active:bg-blue-800"
        >
          Start Demo →
        </button>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Completed
  // ---------------------------------------------------------------------------
  if (completed) {
    return (
      <div className="mx-auto max-w-xl space-y-6 py-16 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-100">
          <CheckCircle className="h-8 w-8 text-emerald-600" />
        </div>
        <h2 className="text-2xl font-bold text-slate-900">Demo Complete</h2>
        <p className="text-sm text-slate-500 leading-relaxed">
          You've walked through all 13 steps of the SignalForge pipeline —
          from client setup through intelligence and export.
          Every step used local synthetic data with all safety boundaries enforced.
        </p>
        <div className="rounded-xl border border-emerald-100 bg-emerald-50 p-4 text-left">
          <p className="text-sm font-semibold text-emerald-700 mb-2">What you proved:</p>
          <ul className="space-y-1 text-xs text-emerald-700">
            <li>• Full pipeline from source content → client intelligence</li>
            <li>• Every step is operator-gated — no automation fires without approval</li>
            <li>• No external API calls, uploads, or messages were made</li>
            <li>• All records carry simulation_only=true, outbound_actions_taken=0</li>
            <li>• Intelligence records carry advisory_only=true</li>
          </ul>
        </div>
        <div className="flex gap-3 justify-center">
          <button
            type="button"
            onClick={() => handleJump(1)}
            className="rounded-lg border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Review Steps
          </button>
          {resetConfirm ? (
            <div className="flex gap-2">
              <button type="button" onClick={handleReset} className="rounded-lg bg-red-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-red-700">
                Confirm Reset
              </button>
              <button type="button" onClick={() => setResetConfirm(false)} className="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-600">
                Cancel
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setResetConfirm(true)}
              className="flex items-center gap-2 rounded-lg bg-slate-800 px-5 py-2.5 text-sm font-medium text-white hover:bg-slate-900"
            >
              <RefreshCw className="h-4 w-4" /> Reset Demo
            </button>
          )}
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Active step
  // ---------------------------------------------------------------------------
  const StepIcon = step.icon;
  const pct = Math.round(((currentStep - 1) / STEPS.length) * 100);

  return (
    <div className="mx-auto max-w-2xl space-y-5 py-6">
      {/* Progress bar + controls header */}
      <div className="flex items-center justify-between gap-4">
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide whitespace-nowrap">
          Step {currentStep} / {STEPS.length}
        </span>
        <div className="flex-1 rounded-full bg-slate-100 h-2">
          <div
            className={`h-2 rounded-full transition-all ${colors.progress}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        {/* Jump-to select */}
        <select
          value={jumpTarget}
          onChange={(e) => { setJumpTarget(e.target.value); if (e.target.value) handleJump(Number(e.target.value)); }}
          className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-600 outline-none focus:border-blue-300"
          title="Jump to step"
        >
          <option value="">Jump to…</option>
          {STEPS.map((s) => (
            <option key={s.id} value={s.id}>Step {s.id}: {s.title}</option>
          ))}
        </select>
      </div>

      {/* Step dots */}
      <StepDots total={STEPS.length} current={currentStep} onJump={handleJump} />

      {/* Main step card */}
      <div className={`rounded-2xl border p-6 space-y-5 ${colors.border} ${colors.bg}`}>
        {/* Step header */}
        <div className="flex items-start gap-4">
          <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl ${colors.badge}`}>
            <StepIcon className={`h-5 w-5 ${colors.icon}`} />
          </div>
          <div>
            <div className={`text-xs font-semibold uppercase tracking-wide ${colors.text}`}>Step {step.id}</div>
            <h2 className="text-xl font-bold text-slate-900 leading-tight">{step.title}</h2>
            <p className="text-sm text-slate-600">{step.subtitle}</p>
          </div>
        </div>

        {/* Proves */}
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">What This Proves</div>
          <p className="text-sm leading-relaxed text-slate-700">{step.proves}</p>
        </div>

        {/* Inspect */}
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Data to Inspect</div>
          <p className="font-mono text-xs leading-relaxed text-slate-600 bg-white rounded-lg border border-slate-200 p-3">{step.inspect}</p>
        </div>

        {/* Safety */}
        <SafetyCard items={step.safety} />

        {/* CTA */}
        <button
          type="button"
          onClick={() => handleCta(step.cta)}
          className={`flex w-full items-center justify-between rounded-xl px-4 py-3 text-sm font-semibold transition ${colors.badge} hover:opacity-90`}
        >
          <span>{step.ctaLabel}</span>
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={handlePrev}
          disabled={currentStep <= 1}
          className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 disabled:opacity-40"
        >
          <ArrowLeft className="h-4 w-4" /> Previous
        </button>

        {/* Reset */}
        <div className="flex items-center gap-2">
          {resetConfirm ? (
            <>
              <span className="text-xs text-slate-500">Reset all demo data?</span>
              <button type="button" onClick={handleReset} className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700">
                Yes, Reset
              </button>
              <button type="button" onClick={() => setResetConfirm(false)} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600">
                Cancel
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setResetConfirm(true)}
              className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-50"
            >
              <RefreshCw className="h-3 w-3" /> Reset Demo
            </button>
          )}
        </div>

        <button
          type="button"
          onClick={handleNext}
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white transition hover:bg-blue-700"
        >
          {currentStep >= STEPS.length ? "Finish" : "Next"}
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
