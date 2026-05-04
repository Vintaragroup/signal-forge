import { useEffect, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  FilePlus2,
  PenLine,
  Play,
  RotateCcw,
  Sparkles,
  X,
} from "lucide-react";
import { api, getAppWorkspace } from "../api.js";
import DemoPageBanner from "../components/DemoPageBanner.jsx";
import PocDemoTab from "../components/PocDemoTab.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MODULES = [
  "contractor_growth",
  "insurance_growth",
  "artist_growth",
  "media_growth",
];

const PLATFORMS = ["Instagram", "LinkedIn", "TikTok", "Facebook", "Twitter/X", "Email", "Blog", "YouTube", "Other"];

const CONTENT_TYPES = ["post", "caption", "carousel", "reel_script", "ad_copy"];

const BRIEF_STATUSES = ["draft", "needs_review", "approved", "rejected"];

const DRAFT_STATUSES = ["needs_review", "approved", "rejected"];

const WORKFLOW_STEPS = [
  { id: 1, label: "Create Brief", icon: FilePlus2, description: "Define campaign intent, audience, platform, and offer." },
  { id: 2, label: "Run Content Agent", icon: Play, description: "Agent reads approved briefs and generates draft content." },
  { id: 3, label: "Review Drafts", icon: PenLine, description: "Read, edit, and approve or reject each AI-generated draft." },
  { id: 4, label: "Approve Content", icon: Check, description: "Approved drafts are marked ready for manual use." },
  { id: 5, label: "Mark Ready for Posting", icon: Sparkles, description: "Operator manually posts content outside SignalForge. No automation." },
];

const REVIEW_DECISIONS = [
  { value: "approve", label: "Approve", icon: Check },
  { value: "revise", label: "Mark for Revision", icon: RotateCcw },
  { value: "reject", label: "Reject", icon: X },
];

const emptyBriefFilters = { module: "", platform: "", status: "" };
const emptyDraftFilters = { module: "", platform: "", content_type: "", status: "" };

const emptyBriefForm = {
  campaign_name: "",
  audience: "",
  platform: "",
  goal: "",
  offer: "",
  tone: "",
  notes: "",
  module: "contractor_growth",
  status: "draft",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "—";
}

function SelectFilter({ label, value, onChange, options }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
      >
        <option value="">All</option>
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt.replaceAll("_", " ")}
          </option>
        ))}
      </select>
    </label>
  );
}

function FormField({ label, required, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-700">
        {label}
        {required && <span className="ml-1 text-red-500">*</span>}
      </span>
      {children}
    </label>
  );
}

function inputCls() {
  return "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100";
}

// ---------------------------------------------------------------------------
// Brief form
// ---------------------------------------------------------------------------

function BriefForm({ workspaceSlug, onCreated, onCancel }) {
  const [form, setForm] = useState({ ...emptyBriefForm });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function set(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function submit(e) {
    e.preventDefault();
    if (!form.campaign_name.trim()) {
      setError("Campaign name is required.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const result = await api.createContentBrief({
        ...form,
        workspace_slug: workspaceSlug || "",
      });
      onCreated(result.item);
    } catch (err) {
      setError(err.message || "Failed to create brief.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <FormField label="Campaign Name" required>
          <input
            type="text"
            value={form.campaign_name}
            onChange={(e) => set("campaign_name", e.target.value)}
            placeholder="e.g. Summer Contractor Outreach 2026"
            className={inputCls()}
          />
        </FormField>

        <FormField label="Module">
          <select value={form.module} onChange={(e) => set("module", e.target.value)} className={inputCls()}>
            {MODULES.map((m) => (
              <option key={m} value={m}>{m.replaceAll("_", " ")}</option>
            ))}
          </select>
        </FormField>

        <FormField label="Platform">
          <select value={form.platform} onChange={(e) => set("platform", e.target.value)} className={inputCls()}>
            <option value="">Select platform…</option>
            {PLATFORMS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </FormField>

        <FormField label="Target Audience">
          <input
            type="text"
            value={form.audience}
            onChange={(e) => set("audience", e.target.value)}
            placeholder="e.g. Local roofing contractors in TX"
            className={inputCls()}
          />
        </FormField>

        <FormField label="Campaign Goal">
          <input
            type="text"
            value={form.goal}
            onChange={(e) => set("goal", e.target.value)}
            placeholder="e.g. Generate 5 booked calls this month"
            className={inputCls()}
          />
        </FormField>

        <FormField label="Offer">
          <input
            type="text"
            value={form.offer}
            onChange={(e) => set("offer", e.target.value)}
            placeholder="e.g. Free estimate follow-up audit"
            className={inputCls()}
          />
        </FormField>

        <FormField label="Tone">
          <input
            type="text"
            value={form.tone}
            onChange={(e) => set("tone", e.target.value)}
            placeholder="e.g. friendly, educational, direct"
            className={inputCls()}
          />
        </FormField>

        <FormField label="Status">
          <select value={form.status} onChange={(e) => set("status", e.target.value)} className={inputCls()}>
            {BRIEF_STATUSES.map((s) => (
              <option key={s} value={s}>{s.replaceAll("_", " ")}</option>
            ))}
          </select>
        </FormField>
      </div>

      <FormField label="Notes">
        <textarea
          value={form.notes}
          onChange={(e) => set("notes", e.target.value)}
          rows={3}
          placeholder="Additional context for the agent or operator…"
          className={inputCls()}
        />
      </FormField>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-60"
        >
          <FilePlus2 className="h-4 w-4" />
          {saving ? "Saving…" : "Create Brief"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Draft review inline panel
// ---------------------------------------------------------------------------

function DraftReviewPanel({ draft, onReviewed, onClose }) {
  const [decision, setDecision] = useState("approve");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.reviewContentDraft(draft._id, { decision, note });
      onReviewed();
    } catch (err) {
      setError(err.message || "Review failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-semibold text-blue-800">Review Draft</span>
        <button type="button" onClick={onClose} className="text-blue-500 hover:text-blue-700">
          <X className="h-4 w-4" />
        </button>
      </div>
      <form onSubmit={submit} className="space-y-3">
        <div>
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400">Decision</span>
          <div className="flex flex-wrap gap-2">
            {REVIEW_DECISIONS.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                type="button"
                onClick={() => setDecision(value)}
                className={[
                  "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition",
                  decision === value
                    ? value === "approve"
                      ? "border-green-300 bg-green-50 text-green-700"
                      : value === "reject"
                      ? "border-red-300 bg-red-50 text-red-700"
                      : "border-amber-300 bg-amber-50 text-amber-700"
                    : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50",
                ].join(" ")}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </button>
            ))}
          </div>
        </div>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          placeholder="Optional review note…"
          className={inputCls()}
        />
        {error && <p className="text-xs text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-60"
        >
          {busy ? "Saving…" : "Save Review"}
        </button>
        <p className="mt-1 text-xs text-slate-500">No post will be published or scheduled. Review is for content planning only.</p>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Draft row
// ---------------------------------------------------------------------------

function DraftRow({ draft, onRefresh }) {
  const [expanded, setExpanded] = useState(false);
  const [reviewing, setReviewing] = useState(false);

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-3 p-4 text-left transition hover:bg-slate-50"
      >
        {expanded ? <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" /> : <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-medium text-slate-900">{draft.title || "Untitled draft"}</span>
            <StatusBadge value={draft.status} />
            {draft.generated_by_agent && <StatusBadge value="agent generated" />}
            {draft.platform && <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{draft.platform}</span>}
            {draft.content_type && <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{draft.content_type}</span>}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
            {draft.module && <span>{draft.module.replaceAll("_", " ")}</span>}
            {draft.selected_model && <span>model: {draft.selected_model}</span>}
            <span>{formatDate(draft.created_at)}</span>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-slate-100 px-4 pb-4 pt-3">
          {draft.body && (
            <div className="mb-3">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Draft Body</div>
              <div className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm text-slate-800">{draft.body}</div>
            </div>
          )}
          {draft.call_to_action && (
            <div className="mb-3">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Call to Action</div>
              <p className="text-sm text-slate-700">{draft.call_to_action}</p>
            </div>
          )}
          {draft.hashtags && draft.hashtags.length > 0 && (
            <div className="mb-3">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Hashtags</div>
              <div className="flex flex-wrap gap-1">
                {draft.hashtags.map((tag, i) => (
                  <span key={i} className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700">#{tag}</span>
                ))}
              </div>
            </div>
          )}
          {draft.routing_reason && (
            <div className="mb-3 text-xs text-slate-500">
              <span className="font-medium">Routing: </span>{draft.routing_reason} / complexity: {draft.complexity || "—"}
            </div>
          )}
          {draft.review_note && (
            <div className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
              Review note: {draft.review_note}
            </div>
          )}

          {draft.status === "needs_review" && !reviewing && (
            <button
              type="button"
              onClick={() => setReviewing(true)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-blue-700"
            >
              <PenLine className="h-3.5 w-3.5" /> Review Draft
            </button>
          )}
          {reviewing && (
            <DraftReviewPanel
              draft={draft}
              onReviewed={() => { setReviewing(false); onRefresh(); }}
              onClose={() => setReviewing(false)}
            />
          )}

          {draft.status !== "needs_review" && (
            <p className="text-xs text-slate-500">
              Status: {draft.status} {draft.reviewed_at ? `— reviewed ${formatDate(draft.reviewed_at)}` : ""}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Brief row
// ---------------------------------------------------------------------------

function BriefRow({ brief, relatedDrafts, onRefresh }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-3 p-4 text-left transition hover:bg-slate-50"
      >
        {expanded ? <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" /> : <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-medium text-slate-900">{brief.campaign_name || "Untitled brief"}</span>
            <StatusBadge value={brief.status} />
            {brief.platform && <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{brief.platform}</span>}
            {relatedDrafts.length > 0 && (
              <span className="rounded bg-purple-50 px-2 py-0.5 text-xs text-purple-700">{relatedDrafts.length} draft{relatedDrafts.length !== 1 ? "s" : ""}</span>
            )}
          </div>
          <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-500">
            {brief.module && <span>{brief.module.replaceAll("_", " ")}</span>}
            {brief.audience && <span>audience: {brief.audience}</span>}
            <span>{formatDate(brief.created_at)}</span>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-slate-100 px-4 pb-4 pt-3 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 text-sm text-slate-700">
            {brief.goal && <div><span className="font-medium">Goal:</span> {brief.goal}</div>}
            {brief.offer && <div><span className="font-medium">Offer:</span> {brief.offer}</div>}
            {brief.tone && <div><span className="font-medium">Tone:</span> {brief.tone}</div>}
            {brief.audience && <div><span className="font-medium">Audience:</span> {brief.audience}</div>}
          </div>
          {brief.notes && (
            <div className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700">{brief.notes}</div>
          )}
          {relatedDrafts.length > 0 && (
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Related Drafts</div>
              <div className="space-y-2">
                {relatedDrafts.map((d) => (
                  <DraftRow key={d._id} draft={d} onRefresh={onRefresh} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// v2: Snippet review panel
// ---------------------------------------------------------------------------

function SnippetReviewPanel({ snippet, onReviewed, onClose }) {
  const [decision, setDecision] = useState("approve");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.reviewContentSnippet(snippet._id, { decision, note });
      onReviewed();
    } catch (err) {
      setError(err.message || "Review failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-semibold text-blue-800">Review Snippet</span>
        <button type="button" onClick={onClose} className="text-blue-500 hover:text-blue-700">
          <X className="h-4 w-4" />
        </button>
      </div>
      <form onSubmit={submit} className="space-y-3">
        <div className="flex flex-wrap gap-2">
          {REVIEW_DECISIONS.map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              type="button"
              onClick={() => setDecision(value)}
              className={[
                "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition",
                decision === value
                  ? value === "approve"
                    ? "border-green-300 bg-green-50 text-green-700"
                    : value === "reject"
                    ? "border-red-300 bg-red-50 text-red-700"
                    : "border-amber-300 bg-amber-50 text-amber-700"
                  : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50",
              ].join(" ")}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          placeholder="Optional review note…"
          className={inputCls()}
        />
        {error && <p className="text-xs text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-60"
        >
          {busy ? "Saving…" : "Save Review"}
        </button>
        <p className="mt-1 text-xs text-slate-500">No post will be published or scheduled.</p>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// v6.5: SnippetScorePanel
// ---------------------------------------------------------------------------

function SnippetScorePanel({ snippet, onScored, onClose }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function runScore() {
    setBusy(true);
    setError("");
    try {
      await api.scoreContentSnippet(snippet._id);
      onScored();
    } catch (err) {
      setError(err.message || "Scoring failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-semibold text-emerald-800">Score Snippet (v6.5)</span>
        <button type="button" onClick={onClose} className="text-emerald-500 hover:text-emerald-700">
          <X className="h-4 w-4" />
        </button>
      </div>
      <p className="mb-3 text-xs text-emerald-700">
        Runs deterministic NLP scoring — no external API calls. Scores hook strength, clarity, emotional impact, shareability, and platform fit.
      </p>
      {error && <p className="mb-2 text-xs text-red-600">{error}</p>}
      <button
        type="button"
        disabled={busy}
        onClick={runScore}
        className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:opacity-60"
      >
        {busy ? "Scoring…" : snippet.scored_at ? "Re-score Snippet" : "Run Scoring"}
      </button>
      <p className="mt-2 text-xs text-slate-500">simulation_only: true — no post will be published.</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// v2: SnippetRow
// ---------------------------------------------------------------------------

function SnippetRow({ snippet, onRefresh }) {
  const [expanded, setExpanded] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [scoring, setScoring] = useState(false);

  const hasScore = snippet.overall_score > 0;
  const scoreColor = snippet.overall_score >= 7
    ? "bg-emerald-50 text-emerald-700"
    : snippet.overall_score >= 5
    ? "bg-amber-50 text-amber-700"
    : "bg-red-50 text-red-700";

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-3 p-4 text-left transition hover:bg-slate-50"
      >
        {expanded ? <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" /> : <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-medium text-slate-900">{snippet.theme ? snippet.theme.replaceAll("_", " ") : "Snippet"}</span>
            <StatusBadge value={snippet.status} />
            {hasScore ? (
              <span className={`rounded px-2 py-0.5 text-xs font-medium ${scoreColor}`}>score: {snippet.overall_score.toFixed(1)}</span>
            ) : snippet.score != null && snippet.score > 0 ? (
              <span className="rounded bg-blue-50 px-2 py-0.5 text-xs text-blue-700">score: {snippet.score}</span>
            ) : null}
            {snippet.hook_type && (
              <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs text-sky-700">{snippet.hook_type.replaceAll("_", " ")}</span>
            )}
          </div>
          <div className="mt-1 line-clamp-2 text-xs text-slate-500">{snippet.transcript_text}</div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-slate-100 px-4 pb-4 pt-3 space-y-3">
          <div className="rounded-lg bg-slate-50 p-3 text-sm text-slate-800 italic">"{snippet.transcript_text}"</div>

          {/* v6.5 score breakdown */}
          {hasScore && (
            <div className="rounded-lg border border-emerald-100 bg-emerald-50 p-3 space-y-2">
              <div className="text-xs font-semibold text-emerald-800 mb-1">Score Breakdown (v6.5)</div>
              {[
                { label: "Hook Strength", value: snippet.hook_strength },
                { label: "Clarity", value: snippet.clarity_score },
                { label: "Emotional Impact", value: snippet.emotional_impact },
                { label: "Shareability", value: snippet.shareability_score },
                { label: "Platform Fit", value: snippet.platform_fit_score },
              ].map(({ label, value }) => (
                <div key={label} className="flex items-center gap-2 text-xs">
                  <span className="w-28 shrink-0 text-slate-600">{label}</span>
                  <div className="flex-1 overflow-hidden rounded-full bg-white border border-emerald-100 h-2">
                    <div
                      className="h-full rounded-full bg-emerald-400 transition-all"
                      style={{ width: `${((value || 0) / 10) * 100}%` }}
                    />
                  </div>
                  <span className="w-6 text-right text-emerald-700 font-medium">{(value || 0).toFixed(1)}</span>
                </div>
              ))}
              {snippet.score_reason && (
                <div className="mt-2 text-xs text-slate-500 italic">{snippet.score_reason}</div>
              )}
            </div>
          )}

          {/* v10.3 cleaned hook display (shown when cleanup has been run) */}
          {snippet.display_title && (
            <div className="rounded-lg border border-violet-100 bg-violet-50 p-3 space-y-1">
              <div className="text-xs font-semibold text-violet-800">Display Title</div>
              <div className="text-sm font-semibold text-violet-900">{snippet.display_title}</div>
              {snippet.cleaned_hook_text && snippet.cleaned_hook_text !== snippet.display_title && (
                <>
                  <div className="text-xs font-semibold text-violet-700 mt-1">Clean Hook</div>
                  <div className="text-sm text-violet-800">{snippet.cleaned_hook_text}</div>
                </>
              )}
              {snippet.caption_hook_suggestions && snippet.caption_hook_suggestions.length > 0 && (
                <div className="mt-2 space-y-1">
                  <div className="text-xs font-medium text-violet-700">Caption suggestions:</div>
                  {snippet.caption_hook_suggestions.map((s, i) => (
                    <div key={i} className="text-xs text-slate-600 pl-2 border-l-2 border-violet-200">{s}</div>
                  ))}
                </div>
              )}
              {snippet.hook_cleanup_notes && (
                <div className="text-xs text-violet-500 italic mt-1">{snippet.hook_cleanup_notes}</div>
              )}
            </div>
          )}

          {/* v6.5 hook display */}
          {snippet.hook_text && (
            <div className="rounded-lg border border-sky-100 bg-sky-50 p-3 space-y-1">
              <div className="text-xs font-semibold text-sky-800">{snippet.display_title ? "Raw Extracted Hook" : "Extracted Hook"}</div>
              <div className="text-sm text-sky-900 italic">"{snippet.hook_text}"</div>
              {snippet.hook_type && (
                <span className="inline-block rounded-full bg-sky-100 px-2 py-0.5 text-xs text-sky-700 mt-1">{snippet.hook_type.replaceAll("_", " ")}</span>
              )}
              {snippet.alternative_hooks && snippet.alternative_hooks.length > 0 && (
                <div className="mt-2 space-y-1">
                  <div className="text-xs font-medium text-sky-700">Alternative hooks:</div>
                  {snippet.alternative_hooks.map((h, i) => (
                    <div key={i} className="text-xs text-slate-600 pl-2 border-l-2 border-sky-200">{h}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {snippet.hook_angle && (
            <div className="text-xs text-slate-600"><span className="font-medium">Hook angle:</span> {snippet.hook_angle}</div>
          )}
          {!hasScore && snippet.score_reason && (
            <div className="text-xs text-slate-600"><span className="font-medium">Score reason:</span> {snippet.score_reason}</div>
          )}
          {snippet.platform_fit && snippet.platform_fit.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {snippet.platform_fit.map((p) => (
                <span key={p} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{p}</span>
              ))}
            </div>
          )}
          {snippet.review_note && (
            <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">Note: {snippet.review_note}</div>
          )}

          <div className="flex flex-wrap gap-2">
            {snippet.status === "needs_review" && !reviewing && (
              <button
                type="button"
                onClick={() => setReviewing(true)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-blue-700"
              >
                <PenLine className="h-3.5 w-3.5" /> Review Snippet
              </button>
            )}
            {!scoring && (
              <button
                type="button"
                onClick={() => setScoring(true)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-700 transition hover:bg-emerald-100"
              >
                {snippet.scored_at ? "Re-score" : "Score Snippet"}
              </button>
            )}
          </div>

          {reviewing && (
            <SnippetReviewPanel
              snippet={snippet}
              onReviewed={() => { setReviewing(false); onRefresh(); }}
              onClose={() => setReviewing(false)}
            />
          )}
          {scoring && (
            <SnippetScorePanel
              snippet={snippet}
              onScored={() => { setScoring(false); onRefresh(); }}
              onClose={() => setScoring(false)}
            />
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// v2: ClientProfileRow
// ---------------------------------------------------------------------------

function ClientProfileRow({ profile }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-3 p-4 text-left transition hover:bg-slate-50"
      >
        {expanded ? <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" /> : <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-slate-900">{profile.client_name}</span>
            <StatusBadge value={profile.status} />
            {profile.brand_name && <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{profile.brand_name}</span>}
          </div>
          <div className="mt-1 text-xs text-slate-500">
            Likeness: {profile.likeness_permissions ? "✓" : "✗"} · Voice: {profile.voice_permissions ? "✓" : "✗"} · Avatar: {profile.avatar_permissions ? "✓" : "✗"}
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-slate-100 px-4 pb-4 pt-3 space-y-2 text-sm text-slate-700">
          {profile.compliance_notes && (
            <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">{profile.compliance_notes}</div>
          )}
          {profile.disallowed_topics && profile.disallowed_topics.length > 0 && (
            <div className="text-xs"><span className="font-medium">Disallowed topics:</span> {profile.disallowed_topics.join(", ")}</div>
          )}
          {profile.allowed_content_types && profile.allowed_content_types.length > 0 && (
            <div className="text-xs"><span className="font-medium">Allowed types:</span> {profile.allowed_content_types.join(", ")}</div>
          )}
          <div className="text-xs text-slate-500">Created: {formatDate(profile.created_at)}</div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// v2: SourceChannelRow
// ---------------------------------------------------------------------------

function SourceChannelRow({ channel }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-3 p-4 text-left transition hover:bg-slate-50"
      >
        {expanded ? <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" /> : <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-slate-900">{channel.channel_name}</span>
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{channel.platform}</span>
            {channel.approved_for_ingestion && <StatusBadge value="approved" />}
            {!channel.approved_for_ingestion && <StatusBadge value="not approved" />}
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-slate-100 px-4 pb-4 pt-3 space-y-2 text-sm text-slate-700">
          {channel.channel_url && (
            <div className="text-xs"><span className="font-medium">URL:</span> {channel.channel_url}</div>
          )}
          <div className="text-xs">
            Ingestion: {channel.approved_for_ingestion ? "Approved" : "Not approved"} · Reuse: {channel.approved_for_reuse ? "Approved" : "Not approved"}
          </div>
          {channel.notes && <div className="text-xs text-slate-500">{channel.notes}</div>}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// v2: SourceContentRow
// ---------------------------------------------------------------------------

function SourceContentRow({ content }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-3 p-4 text-left transition hover:bg-slate-50"
      >
        {expanded ? <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" /> : <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-medium text-slate-900">{content.title || "Untitled"}</span>
            <StatusBadge value={content.status} />
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{content.platform}</span>
            {content.discovery_score != null && (
              <span className="rounded bg-blue-50 px-2 py-0.5 text-xs text-blue-700">score: {content.discovery_score}</span>
            )}
          </div>
          <div className="mt-1 text-xs text-slate-500">
            {content.creator && <span>{content.creator} · </span>}
            {content.duration_seconds && <span>{Math.round(content.duration_seconds / 60)}m · </span>}
            <span>{formatDate(content.published_at)}</span>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-slate-100 px-4 pb-4 pt-3 space-y-2 text-sm text-slate-700">
          {content.discovery_reason && (
            <div className="text-xs"><span className="font-medium">Discovery reason:</span> {content.discovery_reason}</div>
          )}
          {content.performance_metadata && (
            <div className="flex flex-wrap gap-3 text-xs text-slate-500">
              {Object.entries(content.performance_metadata).map(([k, v]) => (
                <span key={k}>{k}: {v}</span>
              ))}
            </div>
          )}
          {content.source_url && (
            <div className="text-xs text-slate-500 truncate">{content.source_url}</div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// v2: CreativeAssetRow
// ---------------------------------------------------------------------------

function CreativeAssetRow({ asset, onRefresh }) {
  const [expanded, setExpanded] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [decision, setDecision] = useState("approve");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submitReview(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.reviewCreativeAsset(asset._id, { decision, note });
      onRefresh();
      setReviewing(false);
    } catch (err) {
      setError(err.message || "Review failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-3 p-4 text-left transition hover:bg-slate-50"
      >
        {expanded ? <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" /> : <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-medium text-slate-900">{asset.title || "Untitled asset"}</span>
            <StatusBadge value={asset.status} />
            {asset.asset_type && <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{asset.asset_type}</span>}
          </div>
          {asset.description && <div className="mt-1 line-clamp-1 text-xs text-slate-500">{asset.description}</div>}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-slate-100 px-4 pb-4 pt-3 space-y-3">
          {asset.prompt_used && (
            <div className="text-xs"><span className="font-medium">Prompt:</span> {asset.prompt_used}</div>
          )}
          {asset.review_note && (
            <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">Note: {asset.review_note}</div>
          )}

          {asset.status === "needs_review" && !reviewing && (
            <button
              type="button"
              onClick={() => setReviewing(true)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-blue-700"
            >
              <PenLine className="h-3.5 w-3.5" /> Review Asset
            </button>
          )}
          {reviewing && (
            <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-4">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-sm font-semibold text-blue-800">Review Asset</span>
                <button type="button" onClick={() => setReviewing(false)} className="text-blue-500 hover:text-blue-700">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <form onSubmit={submitReview} className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  {REVIEW_DECISIONS.map(({ value, label, icon: Icon }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setDecision(value)}
                      className={[
                        "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition",
                        decision === value
                          ? value === "approve"
                            ? "border-green-300 bg-green-50 text-green-700"
                            : value === "reject"
                            ? "border-red-300 bg-red-50 text-red-700"
                            : "border-amber-300 bg-amber-50 text-amber-700"
                          : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50",
                      ].join(" ")}
                    >
                      <Icon className="h-3.5 w-3.5" /> {label}
                    </button>
                  ))}
                </div>
                <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder="Optional note…" className={inputCls()} />
                {error && <p className="text-xs text-red-600">{error}</p>}
                <button
                  type="submit"
                  disabled={busy}
                  className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-60"
                >
                  {busy ? "Saving…" : "Save Review"}
                </button>
                <p className="mt-1 text-xs text-slate-500">No post will be published or scheduled.</p>
              </form>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// v3: Ingest Pipeline Section
// ---------------------------------------------------------------------------

function IngestPipelineSection({
  sourceContent,
  audioExtractionRuns,
  transcriptRuns,
  transcriptSegments,
  contentSnippets,
  mediaIntakeRecords,
  wsParam,
  onRefresh,
  showNotice,
  demoMode,
}) {
  const [busy, setBusy] = useState({});

  async function handleApproveContent(contentItem) {
    setBusy((b) => ({ ...b, [contentItem._id]: "approve" }));
    try {
      await api.updateSourceContentStatus(contentItem._id, { status: "approved" });
      showNotice(`"${contentItem.title || contentItem._id}" approved for extraction.`);
      await onRefresh();
    } catch {
      showNotice("Approval failed.");
    } finally {
      setBusy((b) => ({ ...b, [contentItem._id]: null }));
    }
  }

  async function handleRunTranscript(contentItem) {
    setBusy((b) => ({ ...b, [contentItem._id]: "transcript" }));
    try {
      await api.createTranscriptRun({
        source_content_id: contentItem._id,
        ...wsParam(),
      });
      showNotice("Transcript run created. Review results below.");
      await onRefresh();
    } catch {
      showNotice("Transcript run failed.");
    } finally {
      setBusy((b) => ({ ...b, [contentItem._id]: null }));
    }
  }

  async function handleGenerateSnippets(contentItem) {
    setBusy((b) => ({ ...b, [contentItem._id]: "snippets" }));
    try {
      const latestRun = [...transcriptRuns]
        .filter((r) => r.source_content_id === contentItem._id)
        .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0];
      const result = await api.generateSnippets(contentItem._id, {
        transcript_run_id: latestRun?._id || null,
        ...wsParam(),
      });
      const count = result.items?.length ?? 0;
      showNotice(`${count} snippet candidate${count !== 1 ? "s" : ""} added to Snippets for review.`);
      await onRefresh();
    } catch {
      showNotice("Snippet generation failed.");
    } finally {
      setBusy((b) => ({ ...b, [contentItem._id]: null }));
    }
  }

  function statusBadge(status) {
    const colors = {
      approved: "bg-green-100 text-green-700",
      rejected: "bg-red-100 text-red-700",
      needs_review: "bg-amber-100 text-amber-700",
    };
    return (
      <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${colors[status] ?? "bg-slate-100 text-slate-600"}`}>
        {status ?? "unknown"}
      </span>
    );
  }

  return (
    <section className="space-y-6">
      <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        <span className="font-semibold">Safety notice:</span> No audio is downloaded. No content is published or scheduled.
        {demoMode && <span className="ml-2 font-semibold text-indigo-700">[Demo Mode — all actions are simulated]</span>}
      </div>

      {sourceContent.length === 0 ? (
        <p className="text-sm text-slate-500">No source content found. Add a source URL in the Source Content tab first.</p>
      ) : (
        <div className="space-y-3">
          {sourceContent.map((c) => {
            const isApproved = c.status === "approved";
            const runs = transcriptRuns.filter((r) => r.source_content_id === c._id);
            const latestRun = [...runs].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0];
            const segs = transcriptSegments.filter((s) => s.source_content_id === c._id && s.transcript_run_id === latestRun?._id);
            const snippetCount = contentSnippets.filter((s) => s.source_content_id === c._id && s.generation_source === "auto").length;
            const audioRun = audioExtractionRuns.find((r) => r.source_content_id === c._id);
            const intakeRecord = (mediaIntakeRecords || []).find((m) => m.source_content_id === c._id);
            const isApproving = busy[c._id] === "approve";
            const isRunningTranscript = busy[c._id] === "transcript";
            const isRunningSnippets = busy[c._id] === "snippets";
            return (
              <div key={c._id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm space-y-2">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 space-y-1">
                    <p className="text-sm font-semibold text-slate-800 truncate">{c.title || c.source_url || c._id}</p>
                    {c.source_url && (
                      <p className="text-xs text-slate-400 truncate">{c.source_url}</p>
                    )}
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-500">Status:</span>
                      {statusBadge(c.status)}
                      {!isApproved && (
                        <button
                          onClick={() => handleApproveContent(c)}
                          disabled={isApproving}
                          className="rounded bg-green-600 px-2 py-0.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
                        >
                          {isApproving ? "Approving…" : "Approve"}
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <button
                      onClick={() => handleRunTranscript(c)}
                      disabled={isRunningTranscript || isRunningSnippets}
                      className="rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                    >
                      {isRunningTranscript ? "Running…" : "Run Transcript"}
                    </button>
                    <button
                      onClick={() => handleGenerateSnippets(c)}
                      disabled={!latestRun || isRunningTranscript || isRunningSnippets}
                      title={!latestRun ? "Run a transcript first" : "Generate snippet candidates from transcript"}
                      className="rounded bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isRunningSnippets ? "Generating…" : "Generate Snippets"}
                    </button>
                  </div>
                </div>
                {/* v4: media intake record row */}
                {intakeRecord && (
                  <div className="rounded bg-slate-50 border border-slate-100 px-3 py-2 text-xs text-slate-600 space-y-0.5">
                    <p className="font-medium text-slate-700">Media intake</p>
                    <p>
                      <span className="font-medium">Method:</span> {intakeRecord.intake_method}{" "}
                      <span className="font-medium ml-2">Status:</span>{" "}
                      <span className={intakeRecord.status === "registered" ? "text-green-600" : "text-amber-600"}>
                        {intakeRecord.status}
                      </span>
                    </p>
                    {intakeRecord.source_url && (
                      <p className="truncate text-slate-400">{intakeRecord.source_url}</p>
                    )}
                    {intakeRecord.media_path && (
                      <p className="truncate text-slate-400">{intakeRecord.media_path}</p>
                    )}
                    {intakeRecord.skip_reason && (
                      <p className="text-amber-600">Note: {intakeRecord.skip_reason}</p>
                    )}
                  </div>
                )}
                <div className="flex flex-wrap gap-4 text-xs text-slate-500">
                  <span>
                    <span className="font-medium text-slate-600">Audio extraction:</span>{" "}
                    {audioRun ? (
                      <span className={audioRun.status === "skipped" ? "text-amber-600" : "text-green-600"}>
                        {audioRun.status}
                        {audioRun.skip_reason ? ` (${audioRun.skip_reason})` : ""}
                      </span>
                    ) : (
                      <span className="text-slate-400">not run</span>
                    )}
                  </span>
                  <span>
                    <span className="font-medium text-slate-600">Transcript runs:</span>{" "}
                    <span className={runs.length > 0 ? "text-green-600" : "text-slate-400"}>{runs.length}</span>
                  </span>
                  {latestRun && (
                    <span>
                      <span className="font-medium text-slate-600">Provider:</span>{" "}
                      <span className={latestRun.provider === "whisper" ? "text-indigo-600 font-semibold" : "text-slate-500"}>
                        {latestRun.provider ?? "stub"}
                      </span>
                    </span>
                  )}
                  {latestRun && (
                    <span>
                      <span className="font-medium text-slate-600">Status:</span>{" "}
                      <span className={
                        latestRun.status === "complete" ? "text-green-600" :
                        latestRun.status === "failed" ? "text-red-600" :
                        "text-amber-600"
                      }>
                        {latestRun.status ?? "unknown"}
                      </span>
                    </span>
                  )}
                  {latestRun && (
                    <span>
                      <span className="font-medium text-slate-600">Segments:</span>{" "}
                      <span className="text-green-600">{segs.length}</span>
                    </span>
                  )}
                  <span>
                    <span className="font-medium text-slate-600">Auto-snippets:</span>{" "}
                    <span className={snippetCount > 0 ? "text-emerald-600" : "text-slate-400"}>{snippetCount}</span>
                  </span>
                </div>
                {latestRun?.error_message && (
                  <div className="rounded bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
                    <span className="font-semibold">Transcription error:</span> {latestRun.error_message}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// v4.5: Prompt Library Section
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// v9.5: Client Intelligence Section
// ---------------------------------------------------------------------------
function ClientIntelligenceSection({
  clientIntelligenceRecords,
  leadCorrelations,
  clientProfiles,
  assetPerformanceRecords,
  wsParam,
  onRefresh,
  showNotice,
}) {
  const [subTab, setSubTab] = useState("overview");
  const [selectedClientId, setSelectedClientId] = useState("");
  const [generating, setGenerating] = useState(false);
  const [leadId, setLeadId] = useState("");

  const selectedRecord = clientIntelligenceRecords
    .filter((r) => !selectedClientId || r.client_id === selectedClientId)
    .slice(-1)[0] || null;

  const filteredCorrelations = leadCorrelations.filter(
    (c) => !selectedClientId || c.client_id === selectedClientId
  );

  async function handleGenerate() {
    if (!selectedClientId) return showNotice("Select a client first.", "error");
    setGenerating(true);
    try {
      await api.generateClientIntelligence(selectedClientId, {});
      showNotice("Intelligence generated.", "success");
      onRefresh();
    } catch {
      showNotice("Failed to generate intelligence.", "error");
    } finally {
      setGenerating(false);
    }
  }

  async function handleGenerateCorrelations() {
    if (!selectedClientId) return showNotice("Select a client first.", "error");
    setGenerating(true);
    try {
      await api.generateLeadContentCorrelations({
        client_id: selectedClientId,
        lead_id: leadId,
        ...wsParam(),
      });
      showNotice("Correlations generated.", "success");
      onRefresh();
    } catch {
      showNotice("Failed to generate correlations.", "error");
    } finally {
      setGenerating(false);
    }
  }

  const subTabs = [
    { id: "overview", label: "Client Overview" },
    { id: "top-performers", label: "Top Performers" },
    { id: "insights", label: "Insights" },
    { id: "recommendations", label: "Recommendations" },
    { id: "correlations", label: "Correlations" },
  ];

  return (
    <div className="space-y-6">
      {/* Safety badge */}
      <div className="rounded bg-blue-50 border border-blue-200 px-4 py-2 text-xs text-blue-700 font-mono">
        v9.5 Client Intelligence · simulation_only · advisory_only · outbound_actions_taken: 0 · no external calls
      </div>

      {/* Client selector + generate button */}
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-slate-500">Client</label>
          <select
            className="rounded border border-slate-300 px-3 py-1.5 text-sm"
            value={selectedClientId}
            onChange={(e) => setSelectedClientId(e.target.value)}
          >
            <option value="">— All clients —</option>
            {clientProfiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.client_name || p.brand_name || p.id}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          disabled={!selectedClientId || generating}
          onClick={handleGenerate}
          className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {generating ? "Generating…" : "Generate Intelligence"}
        </button>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-slate-500">Lead ID (for correlations)</label>
          <input
            className="rounded border border-slate-300 px-3 py-1.5 text-sm w-48"
            value={leadId}
            onChange={(e) => setLeadId(e.target.value)}
            placeholder="lead id (optional)"
          />
        </div>
        <button
          type="button"
          disabled={!selectedClientId || generating}
          onClick={handleGenerateCorrelations}
          className="rounded bg-slate-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          Generate Correlations
        </button>
      </div>

      {/* Sub-tabs */}
      <div className="flex gap-1 border-b border-slate-200 pb-0">
        {subTabs.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setSubTab(id)}
            className={[
              "rounded-t-lg px-4 py-2 text-sm font-medium transition",
              subTab === id
                ? "border-b-2 border-blue-600 text-blue-700"
                : "text-slate-500 hover:text-slate-800",
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Sub-tab content */}
      {subTab === "overview" && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          {selectedRecord ? (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
              <div><dt className="text-slate-500">Client ID</dt><dd className="font-mono text-xs">{selectedRecord.client_id}</dd></div>
              <div><dt className="text-slate-500">Conversion Status</dt><dd>{selectedRecord.conversion_status || "—"}</dd></div>
              <div><dt className="text-slate-500">Acquisition Score</dt><dd>{selectedRecord.acquisition_score ?? "—"}</dd></div>
              <div><dt className="text-slate-500">Content Performance Score</dt><dd>{selectedRecord.content_performance_score ?? "—"}</dd></div>
              <div><dt className="text-slate-500">Estimated ROI</dt><dd>{selectedRecord.estimated_roi ?? "—"}</dd></div>
              <div><dt className="text-slate-500">Confidence Score</dt><dd>{selectedRecord.confidence_score ?? "—"}</dd></div>
              <div><dt className="text-slate-500">Source Lead ID</dt><dd className="font-mono text-xs">{selectedRecord.source_lead_id || "—"}</dd></div>
              <div><dt className="text-slate-500">Generated At</dt><dd>{selectedRecord.generated_at || selectedRecord.created_at || "—"}</dd></div>
            </dl>
          ) : (
            <p className="text-sm text-slate-500">No intelligence record found. Select a client and click "Generate Intelligence".</p>
          )}
        </div>
      )}

      {subTab === "top-performers" && (
        <div className="space-y-4">
          {selectedRecord ? (
            <>
              {[
                { label: "Top Hook Types", key: "top_hook_types" },
                { label: "Top Prompt Types", key: "top_prompt_types" },
                { label: "Best Platforms", key: "best_platforms" },
                { label: "Top Snippet IDs", key: "top_snippet_ids" },
              ].map(({ label, key }) => (
                <div key={key} className="rounded-lg border border-slate-200 bg-white p-4">
                  <h4 className="text-sm font-semibold text-slate-700 mb-2">{label}</h4>
                  {(selectedRecord[key] || []).length > 0 ? (
                    <ol className="list-decimal list-inside text-sm text-slate-700 space-y-1">
                      {(selectedRecord[key] || []).map((v, i) => (
                        <li key={i}>{v}</li>
                      ))}
                    </ol>
                  ) : (
                    <p className="text-xs text-slate-400">No data.</p>
                  )}
                </div>
              ))}
            </>
          ) : (
            <p className="text-sm text-slate-500">Generate intelligence first.</p>
          )}
        </div>
      )}

      {subTab === "insights" && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          {selectedRecord && (selectedRecord.insights || []).length > 0 ? (
            <ul className="list-disc list-inside space-y-2 text-sm text-slate-700">
              {(selectedRecord.insights || []).map((ins, i) => (
                <li key={i}>{ins}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">No insights available. Generate intelligence first.</p>
          )}
        </div>
      )}

      {subTab === "recommendations" && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          {selectedRecord && (selectedRecord.recommendations || []).length > 0 ? (
            <ul className="list-disc list-inside space-y-2 text-sm text-slate-700">
              {(selectedRecord.recommendations || []).map((rec, i) => (
                <li key={i}>{rec}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">No recommendations available. Generate intelligence first.</p>
          )}
        </div>
      )}

      {subTab === "correlations" && (
        <div className="rounded-lg border border-slate-200 bg-white overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                {["Lead ID", "Client ID", "Content Theme", "Hook Type", "Prompt Type", "Platform", "Score", "Strength"].map((h) => (
                  <th key={h} className="px-3 py-2 text-left text-xs font-semibold text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredCorrelations.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-3 py-4 text-center text-slate-400 text-xs">
                    No correlation records. Generate correlations for a client.
                  </td>
                </tr>
              ) : (
                filteredCorrelations.map((c, i) => (
                  <tr key={c.id || i} className="hover:bg-slate-50">
                    <td className="px-3 py-2 font-mono text-xs">{c.lead_id || "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs">{c.client_id || "—"}</td>
                    <td className="px-3 py-2">{c.content_theme || "—"}</td>
                    <td className="px-3 py-2">{c.hook_type || "—"}</td>
                    <td className="px-3 py-2">{c.prompt_type || "—"}</td>
                    <td className="px-3 py-2">{c.platform || "—"}</td>
                    <td className="px-3 py-2">{c.performance_score ?? "—"}</td>
                    <td className="px-3 py-2">
                      <span className={[
                        "rounded px-2 py-0.5 text-xs font-medium",
                        c.correlation_strength === "strong" ? "bg-green-100 text-green-700" :
                        c.correlation_strength === "moderate" ? "bg-yellow-100 text-yellow-700" :
                        "bg-slate-100 text-slate-600",
                      ].join(" ")}>
                        {c.correlation_strength || "—"}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* All records table */}
      {subTab === "overview" && clientIntelligenceRecords.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white overflow-x-auto mt-4">
          <div className="px-4 py-2 border-b border-slate-100 text-xs font-semibold text-slate-500">
            All Intelligence Records ({clientIntelligenceRecords.length})
          </div>
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                {["Client ID", "Perf Score", "Est. ROI", "Confidence", "Generated At"].map((h) => (
                  <th key={h} className="px-3 py-2 text-left text-xs font-semibold text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {clientIntelligenceRecords.map((r, i) => (
                <tr key={r.id || i} className="hover:bg-slate-50">
                  <td className="px-3 py-2 font-mono text-xs">{r.client_id || "—"}</td>
                  <td className="px-3 py-2">{r.content_performance_score ?? "—"}</td>
                  <td className="px-3 py-2">{r.estimated_roi ?? "—"}</td>
                  <td className="px-3 py-2">{r.confidence_score ?? "—"}</td>
                  <td className="px-3 py-2 text-xs">{r.generated_at || r.created_at || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// v8.5: Campaign Exports Section
// ---------------------------------------------------------------------------
function CampaignExportsSection({ campaignExports, campaignPacks, campaignReports, wsParam, onRefresh, showNotice }) {
  const [subTab, setSubTab] = useState("exports-list");
  const [selectedPackId, setSelectedPackId] = useState("");
  const [selectedReportId, setSelectedReportId] = useState("");
  const [exportName, setExportName] = useState("");
  const [exportFormat, setExportFormat] = useState("markdown");
  const [creating, setCreating] = useState(false);
  const [selectedExport, setSelectedExport] = useState(null);
  const [reviewDecision, setReviewDecision] = useState("approve");
  const [reviewNotes, setReviewNotes] = useState("");
  const [reviewing, setReviewing] = useState(false);

  async function handleCreateExport() {
    if (!selectedPackId) { showNotice("Select a campaign pack."); return; }
    if (!selectedReportId) { showNotice("Select a campaign report."); return; }
    setCreating(true);
    try {
      const res = await api.createCampaignExport({
        campaign_pack_id: selectedPackId,
        campaign_report_id: selectedReportId,
        export_name: exportName || "export",
        export_format: exportFormat,
      });
      showNotice(`Export created — ${res.item?.export_status || "generated"}. Path: ${res.item?.export_path || "n/a"}`);
      setSelectedExport(res.item);
      setSubTab("export-detail");
      onRefresh();
    } catch { showNotice("Failed to create export."); }
    finally { setCreating(false); }
  }

  async function handleReviewExport() {
    if (!selectedExport) return;
    setReviewing(true);
    try {
      const res = await api.reviewCampaignExport(selectedExport._id, { decision: reviewDecision, reviewer_notes: reviewNotes });
      showNotice(`Export ${res.item?.export_status}.`);
      setSelectedExport(res.item);
      onRefresh();
    } catch { showNotice("Review failed."); }
    finally { setReviewing(false); }
  }

  const subTabs = [
    { id: "exports-list", label: `All Exports (${campaignExports.length})` },
    { id: "create-export", label: "Create Export" },
    { id: "export-detail", label: "Export Detail" },
    { id: "review-export", label: "Review Export" },
  ];

  return (
    <div className="space-y-4">
      {/* v8.5 safety badge */}
      <div className="flex flex-wrap gap-2 text-xs">
        {["v8.5 Campaign Exports", "simulation_only", "outbound_actions_taken: 0", "local filesystem only", "no uploads · no email · no DMs"].map((t) => (
          <span key={t} className="rounded bg-emerald-50 px-2 py-0.5 font-mono text-emerald-700 border border-emerald-200">{t}</span>
        ))}
      </div>

      {/* Sub-tabs */}
      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {subTabs.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setSubTab(id)}
            className={["rounded-t-lg px-3 py-1.5 text-xs font-medium transition", subTab === id ? "border-b-2 border-emerald-600 text-emerald-700" : "text-slate-500 hover:text-slate-800"].join(" ")}
          >{label}</button>
        ))}
      </div>

      {/* All Exports */}
      {subTab === "exports-list" && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-800">Campaign Exports</h3>
          {campaignExports.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
              No exports yet. Create one from an approved campaign pack and report.
            </div>
          ) : (
            <div className="space-y-2">
              {campaignExports.map((ex) => (
                <div key={ex._id} className="rounded-lg border border-slate-200 bg-white p-3 flex flex-wrap items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">{ex.export_name}</p>
                    <p className="text-xs text-slate-500">{ex.export_format} · {ex.export_status}</p>
                    <p className="text-xs text-slate-400 font-mono truncate">{ex.export_path}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => { setSelectedExport(ex); setSubTab("export-detail"); }}
                    className="rounded-lg border border-slate-200 px-3 py-1 text-xs text-slate-600 hover:bg-slate-50"
                  >View</button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Create Export */}
      {subTab === "create-export" && (
        <div className="space-y-4 max-w-lg">
          <h3 className="text-sm font-semibold text-slate-800">Create Export Package</h3>
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Campaign Pack</label>
              <select value={selectedPackId} onChange={(e) => setSelectedPackId(e.target.value)} className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm">
                <option value="">— Select a pack —</option>
                {campaignPacks.map((p) => <option key={p._id} value={p._id}>{p.campaign_name} ({p.status})</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Campaign Report</label>
              <select value={selectedReportId} onChange={(e) => setSelectedReportId(e.target.value)} className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm">
                <option value="">— Select a report —</option>
                {campaignReports.map((r) => <option key={r._id} value={r._id}>{r.campaign_pack_id} — {r.status}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Export Name</label>
              <input type="text" value={exportName} onChange={(e) => setExportName(e.target.value)} placeholder="e.g. spring_2025_client_package" className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Export Format</label>
              <select value={exportFormat} onChange={(e) => setExportFormat(e.target.value)} className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm">
                <option value="markdown">Markdown (.md)</option>
                <option value="zip">Zip archive (.zip with manifest + assets)</option>
                <option value="pdf_placeholder">PDF Placeholder (markdown with note)</option>
              </select>
            </div>
            <div className="rounded bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800">
              Export writes to local filesystem only. No uploading, emailing, or outbound actions.
            </div>
            <button
              type="button"
              onClick={handleCreateExport}
              disabled={creating}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            >{creating ? "Generating…" : "Generate Export"}</button>
          </div>
        </div>
      )}

      {/* Export Detail */}
      {subTab === "export-detail" && (
        <div className="space-y-4">
          {!selectedExport ? (
            <p className="text-sm text-slate-500">Select an export from the list to view details.</p>
          ) : (
            <div className="space-y-4">
              <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-2">
                <h3 className="text-sm font-semibold text-slate-800">{selectedExport.export_name}</h3>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <span className="text-slate-500">Format:</span><span className="font-mono">{selectedExport.export_format}</span>
                  <span className="text-slate-500">Status:</span><span className={`font-medium ${selectedExport.export_status === "approved" ? "text-emerald-700" : selectedExport.export_status === "failed" ? "text-red-600" : "text-slate-700"}`}>{selectedExport.export_status}</span>
                  <span className="text-slate-500">Export Path:</span><span className="font-mono text-xs break-all col-span-1">{selectedExport.export_path || "—"}</span>
                </div>
              </div>
              {(selectedExport.safety_notes || []).length > 0 && (
                <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-3 space-y-1">
                  <p className="text-xs font-semibold text-emerald-800">Safety Notes</p>
                  {selectedExport.safety_notes.map((n, i) => <p key={i} className="text-xs text-emerald-700">✓ {n}</p>)}
                </div>
              )}
              {(selectedExport.included_assets || []).length > 0 && (
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs font-semibold text-slate-700 mb-1">Included Assets ({selectedExport.included_assets.length})</p>
                  {selectedExport.included_assets.map((a, i) => <p key={i} className="text-xs font-mono text-slate-600">{a}</p>)}
                </div>
              )}
              <button
                type="button"
                onClick={() => setSubTab("review-export")}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
              >Review this Export →</button>
            </div>
          )}
        </div>
      )}

      {/* Review Export */}
      {subTab === "review-export" && (
        <div className="space-y-4 max-w-md">
          <h3 className="text-sm font-semibold text-slate-800">Review Export</h3>
          {!selectedExport ? (
            <p className="text-sm text-slate-500">Select an export from the list first.</p>
          ) : (
            <div className="space-y-3">
              <p className="text-xs text-slate-600">Reviewing: <span className="font-medium">{selectedExport.export_name}</span> ({selectedExport.export_status})</p>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Decision</label>
                <select value={reviewDecision} onChange={(e) => setReviewDecision(e.target.value)} className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm">
                  <option value="approve">Approve</option>
                  <option value="reject">Reject</option>
                  <option value="revise">Request Revision</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Reviewer Notes (optional)</label>
                <textarea value={reviewNotes} onChange={(e) => setReviewNotes(e.target.value)} rows={3} className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm" placeholder="Notes for client or team…" />
              </div>
              <div className="rounded bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800">
                Approving this export does NOT upload, email, publish, or schedule anything.
              </div>
              <button
                type="button"
                onClick={handleReviewExport}
                disabled={reviewing}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >{reviewing ? "Submitting…" : "Submit Review"}</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// v8: Campaign Packs Section
// ---------------------------------------------------------------------------
function CampaignPacksSection({
  campaignPacks,
  campaignReports,
  sourceContent,
  contentSnippets,
  promptGenerations,
  assetRenders,
  manualPublishLogs,
  assetPerformanceRecords,
  clientProfiles,
  wsParam,
  onRefresh,
  showNotice,
}) {
  const [subTab, setSubTab] = useState("packs-list");

  // Create Pack form
  const [packName, setPackName] = useState("");
  const [packGoal, setPackGoal] = useState("");
  const [packClient, setPackClient] = useState("");
  const [packPlatforms, setPackPlatforms] = useState("");
  const [packAudience, setPackAudience] = useState("");
  const [packThemes, setPackThemes] = useState("");
  const [packCreating, setPackCreating] = useState(false);

  // Selected pack for detail / add items / report
  const [selectedPackId, setSelectedPackId] = useState(null);
  const [packDetail, setPackDetail] = useState(null);
  const [packDetailLoading, setPackDetailLoading] = useState(false);

  // Add Item form
  const [addItemType, setAddItemType] = useState("source_content");
  const [addItemId, setAddItemId] = useState("");
  const [addItemTitle, setAddItemTitle] = useState("");
  const [addItemAdding, setAddItemAdding] = useState(false);

  // Report
  const [packReports, setPackReports] = useState([]);
  const [reportGenerating, setReportGenerating] = useState(false);
  const [reviewingReportId, setReviewingReportId] = useState(null);
  const [reviewDecision, setReviewDecision] = useState("approve");
  const [reviewNotes, setReviewNotes] = useState("");
  const [reviewing, setReviewing] = useState(false);

  const ITEM_TYPE_OPTIONS = [
    { value: "source_content", label: "Source Content" },
    { value: "snippet", label: "Snippet" },
    { value: "prompt_generation", label: "Prompt Generation" },
    { value: "asset_render", label: "Rendered Asset" },
    { value: "publish_log", label: "Publish Log" },
    { value: "performance_record", label: "Performance Record" },
  ];

  function itemTypeLabel(t) {
    return ITEM_TYPE_OPTIONS.find((o) => o.value === t)?.label || t;
  }

  function itemTypeItems(t) {
    switch (t) {
      case "source_content": return sourceContent;
      case "snippet": return contentSnippets;
      case "prompt_generation": return promptGenerations;
      case "asset_render": return assetRenders;
      case "publish_log": return manualPublishLogs;
      case "performance_record": return assetPerformanceRecords;
      default: return [];
    }
  }

  async function loadPackDetail(packId) {
    if (!packId) return;
    setPackDetailLoading(true);
    try {
      const data = await api.getCampaignPack(packId);
      setPackDetail(data);
      // Also load reports for this pack
      const rpData = await api.campaignReports({ ...wsParam(), campaign_pack_id: packId });
      setPackReports(rpData.items || []);
    } catch {
      showNotice("Failed to load pack detail.");
    } finally {
      setPackDetailLoading(false);
    }
  }

  async function handleCreatePack(e) {
    e.preventDefault();
    if (!packName.trim()) { showNotice("Campaign name is required."); return; }
    setPackCreating(true);
    try {
      await api.createCampaignPack({
        campaign_name: packName.trim(),
        campaign_goal: packGoal.trim(),
        client_id: packClient.trim(),
        target_platforms: packPlatforms.split(",").map((p) => p.trim()).filter(Boolean),
        target_audience: packAudience.trim(),
        content_themes: packThemes.split(",").map((t) => t.trim()).filter(Boolean),
      });
      showNotice("Campaign pack created.");
      setPackName(""); setPackGoal(""); setPackClient(""); setPackPlatforms(""); setPackAudience(""); setPackThemes("");
      onRefresh();
      setSubTab("packs-list");
    } catch {
      showNotice("Failed to create campaign pack.");
    } finally {
      setPackCreating(false);
    }
  }

  async function handleAddItem(e) {
    e.preventDefault();
    if (!selectedPackId) { showNotice("Select a pack first."); return; }
    if (!addItemId.trim()) { showNotice("Select an item."); return; }
    setAddItemAdding(true);
    try {
      await api.addCampaignPackItem(selectedPackId, {
        item_type: addItemType,
        item_id: addItemId.trim(),
        title: addItemTitle.trim(),
      });
      showNotice("Item added to pack.");
      setAddItemId(""); setAddItemTitle("");
      await loadPackDetail(selectedPackId);
    } catch (err) {
      const msg = err?.message || "Failed to add item.";
      showNotice(msg.includes("workspace") || msg.includes("client") ? msg : "Failed to add item.");
    } finally {
      setAddItemAdding(false);
    }
  }

  async function handleSelectPack(packId) {
    setSelectedPackId(packId);
    await loadPackDetail(packId);
    setSubTab("pack-detail");
  }

  async function handleGenerateReport() {
    if (!selectedPackId) { showNotice("Select a pack first."); return; }
    setReportGenerating(true);
    try {
      await api.generateCampaignReport(selectedPackId);
      showNotice("Campaign report generated.");
      await loadPackDetail(selectedPackId);
      setSubTab("campaign-report");
    } catch {
      showNotice("Failed to generate report.");
    } finally {
      setReportGenerating(false);
    }
  }

  async function handleReviewReport(e) {
    e.preventDefault();
    if (!reviewingReportId) return;
    setReviewing(true);
    try {
      await api.reviewCampaignReport(reviewingReportId, {
        decision: reviewDecision,
        reviewer_notes: reviewNotes.trim(),
      });
      showNotice(`Report ${reviewDecision}d.`);
      setReviewingReportId(null); setReviewNotes("");
      await loadPackDetail(selectedPackId);
    } catch {
      showNotice("Review failed.");
    } finally {
      setReviewing(false);
    }
  }

  function scoreColor(s) {
    if (s === null || s === undefined) return "text-slate-400";
    if (s >= 7) return "text-green-700 font-semibold";
    if (s >= 4) return "text-amber-600 font-semibold";
    return "text-red-600 font-semibold";
  }

  const subTabs = [
    { id: "packs-list", label: `All Packs (${campaignPacks.length})` },
    { id: "create-pack", label: "Create Pack" },
    { id: "add-items", label: "Add Items" },
    { id: "pack-detail", label: selectedPackId ? "Pack Detail" : "Pack Detail" },
    { id: "campaign-report", label: `Reports (${packReports.length})` },
  ];

  return (
    <div className="mt-4 space-y-4">
      {/* Safety badge */}
      <div className="flex items-center gap-2 rounded border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-700">
        <span className="font-semibold">v8 Campaign Packs</span>
        <span className="rounded bg-blue-100 px-1">simulation_only</span>
        <span className="rounded bg-blue-100 px-1">outbound_actions_taken: 0</span>
        <span className="rounded bg-blue-100 px-1">advisory reports only</span>
        <span className="rounded bg-blue-100 px-1">no auto-publish</span>
      </div>

      {/* Sub-tab bar */}
      <div className="flex gap-1 border-b">
        {subTabs.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setSubTab(id)}
            className={[
              "rounded-t-lg px-3 py-2 text-xs font-medium transition",
              subTab === id ? "border-b-2 border-indigo-600 text-indigo-700" : "text-slate-500 hover:text-slate-800",
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── All Packs ── */}
      {subTab === "packs-list" && (
        <div className="space-y-2">
          <p className="text-xs text-slate-500">Select a pack to view detail, add items, or generate a report.</p>
          {campaignPacks.length === 0 && (
            <p className="text-sm text-slate-400 italic">No campaign packs yet. Use "Create Pack" to get started.</p>
          )}
          {campaignPacks.map((pack) => (
            <div key={pack.id} className="rounded border bg-white p-3 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-medium text-slate-800">{pack.campaign_name}</p>
                  <p className="text-xs text-slate-500">{pack.campaign_goal}</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    <span className={[
                      "rounded px-1 py-0.5 text-xs",
                      pack.status === "approved" ? "bg-green-100 text-green-700" :
                      pack.status === "needs_review" ? "bg-amber-100 text-amber-700" :
                      pack.status === "archived" ? "bg-slate-200 text-slate-500" :
                      "bg-slate-100 text-slate-500",
                    ].join(" ")}>{pack.status}</span>
                    {(pack.target_platforms || []).map((p) => (
                      <span key={p} className="rounded bg-indigo-50 px-1 py-0.5 text-xs text-indigo-600">{p}</span>
                    ))}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleSelectPack(pack.id)}
                  className="rounded bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-700"
                >
                  Open
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Create Pack ── */}
      {subTab === "create-pack" && (
        <form onSubmit={handleCreatePack} className="space-y-3 max-w-lg">
          <h3 className="font-semibold text-slate-700">Create Campaign Pack</h3>
          <div>
            <label className="text-xs text-slate-600">Campaign Name *</label>
            <input className="mt-0.5 w-full rounded border px-2 py-1 text-sm" value={packName} onChange={(e) => setPackName(e.target.value)} required />
          </div>
          <div>
            <label className="text-xs text-slate-600">Campaign Goal</label>
            <input className="mt-0.5 w-full rounded border px-2 py-1 text-sm" value={packGoal} onChange={(e) => setPackGoal(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-slate-600">Client</label>
            <select className="mt-0.5 w-full rounded border px-2 py-1 text-sm" value={packClient} onChange={(e) => setPackClient(e.target.value)}>
              <option value="">— No client —</option>
              {clientProfiles.map((c) => (
                <option key={c._id} value={c._id}>{c.client_name || c._id}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-600">Target Platforms (comma-separated)</label>
            <input className="mt-0.5 w-full rounded border px-2 py-1 text-sm" placeholder="instagram, tiktok, youtube" value={packPlatforms} onChange={(e) => setPackPlatforms(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-slate-600">Target Audience</label>
            <input className="mt-0.5 w-full rounded border px-2 py-1 text-sm" value={packAudience} onChange={(e) => setPackAudience(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-slate-600">Content Themes (comma-separated)</label>
            <input className="mt-0.5 w-full rounded border px-2 py-1 text-sm" placeholder="education, behind-the-scenes" value={packThemes} onChange={(e) => setPackThemes(e.target.value)} />
          </div>
          <button type="submit" disabled={packCreating} className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50">
            {packCreating ? "Creating…" : "Create Campaign Pack"}
          </button>
        </form>
      )}

      {/* ── Add Items ── */}
      {subTab === "add-items" && (
        <div className="space-y-4 max-w-lg">
          <h3 className="font-semibold text-slate-700">Add Items to Pack</h3>
          {!selectedPackId && (
            <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
              Open a pack from "All Packs" first, then return here to add items.
            </p>
          )}
          {selectedPackId && (
            <p className="text-xs text-slate-500">
              Adding to pack: <span className="font-mono">{selectedPackId}</span>
            </p>
          )}
          <form onSubmit={handleAddItem} className="space-y-3">
            <div>
              <label className="text-xs text-slate-600">Item Type</label>
              <select className="mt-0.5 w-full rounded border px-2 py-1 text-sm" value={addItemType} onChange={(e) => { setAddItemType(e.target.value); setAddItemId(""); }}>
                {ITEM_TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-600">Select Item</label>
              <select className="mt-0.5 w-full rounded border px-2 py-1 text-sm" value={addItemId} onChange={(e) => setAddItemId(e.target.value)}>
                <option value="">— Select —</option>
                {itemTypeItems(addItemType).map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title || item.name || item.campaign_name || item.platform || item.id}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-600">Title (optional override)</label>
              <input className="mt-0.5 w-full rounded border px-2 py-1 text-sm" value={addItemTitle} onChange={(e) => setAddItemTitle(e.target.value)} />
            </div>
            <button type="submit" disabled={addItemAdding || !selectedPackId} className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50">
              {addItemAdding ? "Adding…" : "Add to Pack"}
            </button>
          </form>
          {packDetail && packDetail.pack_items && packDetail.pack_items.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-semibold text-slate-600 mb-1">Current Pack Items ({packDetail.pack_items.length})</p>
              <div className="space-y-1">
                {packDetail.pack_items.map((item) => (
                  <div key={item.id} className="flex items-center gap-2 rounded border bg-white px-2 py-1 text-xs">
                    <span className="rounded bg-indigo-50 px-1 text-indigo-600">{itemTypeLabel(item.item_type)}</span>
                    <span className="text-slate-600 truncate">{item.title || item.item_id}</span>
                    <span className={["ml-auto rounded px-1", item.status === "approved" ? "bg-green-100 text-green-700" : "bg-slate-100 text-slate-500"].join(" ")}>{item.status}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Pack Detail ── */}
      {subTab === "pack-detail" && (
        <div className="space-y-4">
          {!selectedPackId && (
            <p className="text-sm text-slate-400 italic">Open a pack from "All Packs" to see its detail.</p>
          )}
          {packDetailLoading && <p className="text-xs text-slate-400">Loading…</p>}
          {packDetail && !packDetailLoading && (
            <div className="space-y-3">
              <div className="rounded border bg-white p-4 shadow-sm">
                <h3 className="font-semibold text-slate-800">{packDetail.item?.campaign_name}</h3>
                <p className="text-xs text-slate-500 mt-1">{packDetail.item?.campaign_goal}</p>
                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                  <span className="rounded bg-blue-50 px-1 text-blue-600">Status: {packDetail.item?.status}</span>
                  {(packDetail.item?.target_platforms || []).map((p) => (
                    <span key={p} className="rounded bg-indigo-50 px-1 text-indigo-600">{p}</span>
                  ))}
                  {(packDetail.item?.content_themes || []).map((t) => (
                    <span key={t} className="rounded bg-emerald-50 px-1 text-emerald-700">{t}</span>
                  ))}
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                  <span className="rounded bg-slate-100 px-1">simulation_only: true</span>
                  <span className="rounded bg-slate-100 px-1">outbound_actions_taken: 0</span>
                  <span className="rounded bg-slate-100 px-1">advisory only</span>
                </div>
              </div>

              {/* Timeline */}
              <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Pipeline Timeline</h4>
              {["source_content", "snippet", "prompt_generation", "asset_render", "publish_log", "performance_record"].map((stage) => {
                const stageItems = (packDetail.pack_items || []).filter((i) => i.item_type === stage);
                return (
                  <div key={stage} className="flex items-start gap-3">
                    <div className="flex-shrink-0 w-28 text-right text-xs text-slate-400 pt-1">{itemTypeLabel(stage)}</div>
                    <div className="flex-1 space-y-1">
                      {stageItems.length === 0 && <p className="text-xs text-slate-300 italic">none</p>}
                      {stageItems.map((item) => (
                        <div key={item.id} className="flex items-center gap-2 rounded border bg-slate-50 px-2 py-1 text-xs">
                          <span className="truncate text-slate-700">{item.title || item.item_id}</span>
                          <span className={["ml-auto rounded px-1 text-xs", item.status === "approved" ? "bg-green-100 text-green-700" : item.status === "needs_review" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-500"].join(" ")}>{item.status}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}

              <button
                type="button"
                onClick={handleGenerateReport}
                disabled={reportGenerating}
                className="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {reportGenerating ? "Generating…" : "Generate Campaign Report"}
              </button>
              <p className="text-xs text-slate-400">Advisory only — no publishing or outbound actions.</p>
            </div>
          )}
        </div>
      )}

      {/* ── Campaign Reports ── */}
      {subTab === "campaign-report" && (
        <div className="space-y-4">
          {packReports.length === 0 && (
            <p className="text-sm text-slate-400 italic">No reports yet for this pack. Use "Generate Campaign Report" from Pack Detail.</p>
          )}
          {packReports.map((report) => (
            <div key={report.id} className="rounded border bg-white p-4 shadow-sm space-y-3">
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-semibold text-slate-800">{report.report_title}</h3>
                <span className={["rounded px-1.5 py-0.5 text-xs", report.status === "approved" ? "bg-green-100 text-green-700" : report.status === "needs_review" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-500"].join(" ")}>
                  {report.status}
                </span>
              </div>

              <p className="text-sm text-slate-600">{report.executive_summary}</p>

              {report.performance_summary && (
                <div className="rounded bg-slate-50 p-2 text-xs space-y-1">
                  <p className="font-semibold text-slate-600">Performance Summary</p>
                  <p>Records: {report.performance_summary.record_count}</p>
                  {report.performance_summary.avg_score !== null && (
                    <p>Avg Score: <span className={scoreColor(report.performance_summary.avg_score)}>{report.performance_summary.avg_score}/10</span></p>
                  )}
                  {report.performance_summary.top_score !== null && (
                    <p>Top Score: <span className={scoreColor(report.performance_summary.top_score)}>{report.performance_summary.top_score}/10</span></p>
                  )}
                </div>
              )}

              {(report.top_hooks || []).length > 0 && (
                <div className="text-xs">
                  <p className="font-semibold text-slate-600 mb-1">Top Hooks</p>
                  {report.top_hooks.map((h) => (
                    <div key={h.value} className="flex gap-2">
                      <span className="text-slate-700">{h.value}</span>
                      <span className={scoreColor(h.avg_score)}>{h.avg_score}/10</span>
                    </div>
                  ))}
                </div>
              )}

              {(report.top_prompt_types || []).length > 0 && (
                <div className="text-xs">
                  <p className="font-semibold text-slate-600 mb-1">Top Prompt Types</p>
                  {report.top_prompt_types.map((p) => (
                    <div key={p.value} className="flex gap-2">
                      <span className="text-slate-700">{p.value}</span>
                      <span className={scoreColor(p.avg_score)}>{p.avg_score}/10</span>
                    </div>
                  ))}
                </div>
              )}

              {(report.top_assets || []).length > 0 && (
                <div className="text-xs">
                  <p className="font-semibold text-slate-600 mb-1">Top Assets</p>
                  {report.top_assets.map((a) => (
                    <div key={a.asset_render_id} className="flex gap-2">
                      <span className="font-mono text-slate-600 truncate">{a.asset_render_id}</span>
                      <span className={scoreColor(a.avg_score)}>{a.avg_score}/10</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="text-xs space-y-1">
                <p className="font-semibold text-slate-600">Lessons Learned</p>
                <p className="text-slate-600">{report.lessons_learned}</p>
              </div>
              <div className="text-xs space-y-1">
                <p className="font-semibold text-slate-600">Next Recommendations</p>
                <p className="text-slate-600">{report.next_recommendations}</p>
              </div>

              <div className="flex flex-wrap gap-1 text-xs">
                <span className="rounded bg-slate-100 px-1">simulation_only: true</span>
                <span className="rounded bg-slate-100 px-1">advisory_only: true</span>
                <span className="rounded bg-slate-100 px-1">outbound_actions_taken: 0</span>
              </div>

              {/* Review controls */}
              {reviewingReportId === report.id ? (
                <form onSubmit={handleReviewReport} className="space-y-2 border-t pt-2">
                  <label className="text-xs text-slate-600">Decision</label>
                  <select className="w-full rounded border px-2 py-1 text-sm" value={reviewDecision} onChange={(e) => setReviewDecision(e.target.value)}>
                    <option value="approve">Approve</option>
                    <option value="reject">Reject</option>
                    <option value="revise">Needs Revision</option>
                  </select>
                  <input className="w-full rounded border px-2 py-1 text-sm" placeholder="Reviewer notes (optional)" value={reviewNotes} onChange={(e) => setReviewNotes(e.target.value)} />
                  <div className="flex gap-2">
                    <button type="submit" disabled={reviewing} className="rounded bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-700 disabled:opacity-50">
                      {reviewing ? "Saving…" : "Submit Review"}
                    </button>
                    <button type="button" onClick={() => setReviewingReportId(null)} className="rounded border px-3 py-1 text-xs text-slate-600 hover:bg-slate-50">
                      Cancel
                    </button>
                  </div>
                  <p className="text-xs text-slate-400">Approving does not trigger any publishing or outbound action.</p>
                </form>
              ) : (
                <button
                  type="button"
                  onClick={() => { setReviewingReportId(report.id); setReviewDecision("approve"); setReviewNotes(""); }}
                  className="rounded border border-indigo-300 px-3 py-1 text-xs text-indigo-700 hover:bg-indigo-50"
                >
                  Review Report
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// v7.5: PerformanceLoopSection
function PerformanceLoopSection({
  assetRenders,
  manualPublishLogs,
  assetPerformanceRecords,
  creativePerformanceSummaries,
  wsParam,
  onRefresh,
  showNotice,
}) {
  const [subTab, setSubTab] = useState("publish-log");

  const [logForm, setLogForm] = useState({
    asset_render_id: "", platform: "", manual_post_url: "", posted_by: "",
    posted_at: "", caption_used: "", hook_used: "", notes: "",
  });
  const [logBusy, setLogBusy] = useState(false);

  const [perfForm, setPerfForm] = useState({
    asset_render_id: "", manual_publish_log_id: "", platform: "",
    views: "", likes: "", comments: "", shares: "", saves: "",
    clicks: "", follows: "", watch_time_seconds: "", average_view_duration: "",
    retention_rate: "", engagement_rate: "", notes: "",
  });
  const [perfBusy, setPerfBusy] = useState(false);
  const [calculatedScore, setCalculatedScore] = useState(null);

  const [csvText, setCsvText] = useState("");
  const [csvBusy, setCsvBusy] = useState(false);
  const [csvResult, setCsvResult] = useState(null);

  const [summaryAssetId, setSummaryAssetId] = useState("");
  const [summaryBusy, setSummaryBusy] = useState(false);
  const [summaryResult, setSummaryResult] = useState(null);
  const [recommendations, setRecommendations] = useState(null);

  const PERF_PLATFORMS = ["instagram", "tiktok", "youtube", "youtube_shorts", "facebook", "twitter", "linkedin", "other"];

  function pn(v, fallback = 0) {
    const n = parseFloat(v);
    return isNaN(n) ? fallback : n;
  }

  function previewScore() {
    const v = pn(perfForm.views);
    const eng = pn(perfForm.engagement_rate, -1);
    const saves = pn(perfForm.saves);
    const shares = pn(perfForm.shares);
    const ret = pn(perfForm.retention_rate, 0);
    const clicks = pn(perfForm.clicks);
    const likes = pn(perfForm.likes);
    const comments = pn(perfForm.comments);
    const clamp = (x) => Math.max(0, Math.min(x, 1));
    const derived_eng = eng < 0 ? (v > 0 ? (likes + comments + shares + saves) / v : 0) : eng;
    const score = (
      0.25 * clamp(v / 10000) +
      0.20 * clamp(derived_eng) +
      0.20 * clamp(saves / 500) +
      0.15 * clamp(shares / 200) +
      0.15 * clamp(ret) +
      0.05 * clamp(clicks / 500)
    ) * 10;
    return Math.round(score * 1000) / 1000;
  }

  async function handleCreateLog(e) {
    e.preventDefault();
    setLogBusy(true);
    try {
      await api.createManualPublishLog({ ...wsParam(), ...logForm });
      showNotice("Publish log recorded. SignalForge did not publish anything.");
      setLogForm({ asset_render_id: "", platform: "", manual_post_url: "", posted_by: "", posted_at: "", caption_used: "", hook_used: "", notes: "" });
      onRefresh();
    } catch {
      showNotice("Failed to save publish log.");
    } finally {
      setLogBusy(false);
    }
  }

  async function handleCreatePerf(e) {
    e.preventDefault();
    setPerfBusy(true);
    try {
      const result = await api.createAssetPerformanceRecord({
        ...wsParam(),
        asset_render_id: perfForm.asset_render_id,
        manual_publish_log_id: perfForm.manual_publish_log_id,
        platform: perfForm.platform,
        views: pn(perfForm.views), likes: pn(perfForm.likes),
        comments: pn(perfForm.comments), shares: pn(perfForm.shares),
        saves: pn(perfForm.saves), clicks: pn(perfForm.clicks),
        follows: pn(perfForm.follows),
        watch_time_seconds: pn(perfForm.watch_time_seconds),
        average_view_duration: pn(perfForm.average_view_duration),
        retention_rate: pn(perfForm.retention_rate, 0),
        engagement_rate: perfForm.engagement_rate === "" ? -1 : pn(perfForm.engagement_rate, -1),
        notes: perfForm.notes,
        imported_from: "manual",
      });
      setCalculatedScore(result.performance_score);
      showNotice(`Performance record saved. Score: ${result.performance_score}`);
      setPerfForm({ asset_render_id: "", manual_publish_log_id: "", platform: "", views: "", likes: "", comments: "", shares: "", saves: "", clicks: "", follows: "", watch_time_seconds: "", average_view_duration: "", retention_rate: "", engagement_rate: "", notes: "" });
      onRefresh();
    } catch {
      showNotice("Failed to save performance record.");
    } finally {
      setPerfBusy(false);
    }
  }

  function parseCSVText(text) {
    const lines = text.trim().split("\n");
    if (lines.length < 2) return [];
    const headers = lines[0].split(",").map((h) => h.trim());
    return lines.slice(1).map((line) => {
      const vals = line.split(",").map((v) => v.trim());
      const obj = {};
      headers.forEach((h, i) => { obj[h] = vals[i] ?? ""; });
      return obj;
    });
  }

  async function handleCSVImport(e) {
    e.preventDefault();
    if (!csvText.trim()) { showNotice("Paste CSV text first."); return; }
    const rows = parseCSVText(csvText);
    if (!rows.length) { showNotice("Could not parse any rows from CSV."); return; }
    setCsvBusy(true);
    try {
      const result = await api.importPerformanceCSV({ ...wsParam(), rows });
      setCsvResult(result);
      showNotice(`Imported ${result.imported_count} record(s). ${result.error_count} error(s).`);
      setCsvText("");
      onRefresh();
    } catch {
      showNotice("CSV import failed.");
    } finally {
      setCsvBusy(false);
    }
  }

  async function handleGenerateSummary() {
    if (!summaryAssetId) { showNotice("Select an asset render to summarise."); return; }
    setSummaryBusy(true);
    setSummaryResult(null);
    setRecommendations(null);
    try {
      const result = await api.generateCreativePerformanceSummary({ ...wsParam(), asset_render_id: summaryAssetId });
      setSummaryResult(result.item);
      setRecommendations(result.recommendations);
      showNotice("Summary generated. Recommendations are advisory only.");
    } catch {
      showNotice("Summary generation failed.");
    } finally {
      setSummaryBusy(false);
    }
  }

  const scorePreview = previewScore();

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-base font-semibold text-slate-950">Performance Loop</h2>
        <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs text-violet-700">v7.5</span>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
          No publishing · No platform API calls · Advisory only
        </span>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-slate-200 pb-1">
        {[
          { id: "publish-log", label: `Publish Log (${(manualPublishLogs || []).length})` },
          { id: "performance-entry", label: `Performance Entry (${(assetPerformanceRecords || []).length})` },
          { id: "csv-import", label: "CSV Import" },
          { id: "summary", label: `Summaries (${(creativePerformanceSummaries || []).length})` },
        ].map(({ id, label }) => (
          <button key={id} type="button" onClick={() => setSubTab(id)}
            className={["rounded-t px-3 py-1.5 text-xs font-medium transition",
              subTab === id ? "border-b-2 border-violet-600 text-violet-700" : "text-slate-500 hover:text-slate-800"].join(" ")}
          >{label}</button>
        ))}
      </div>

      {subTab === "publish-log" && (
        <div className="space-y-6">
          <div className="rounded-lg border border-violet-200 bg-violet-50 p-4">
            <p className="mb-1 text-sm font-semibold text-violet-900">Record a Manual Post</p>
            <p className="mb-3 text-xs text-violet-700">
              Use this after manually posting outside SignalForge. SignalForge does not publish, schedule, or call any social API.
            </p>
            <form onSubmit={handleCreateLog} className="space-y-3">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {[
                  { key: "asset_render_id", label: "Asset Render", type: "select", opts: (assetRenders || []).map((r) => ({ v: r._id, l: `${r._id.slice(-8)} · ${r.generation_engine || "render"} · ${r.status}` })) },
                  { key: "platform", label: "Platform", type: "select", opts: PERF_PLATFORMS.map((p) => ({ v: p, l: p })) },
                  { key: "manual_post_url", label: "Manual Post URL", placeholder: "https://..." },
                  { key: "posted_by", label: "Posted By", placeholder: "operator name" },
                  { key: "posted_at", label: "Posted At", placeholder: "2026-05-03T14:00:00Z" },
                  { key: "hook_used", label: "Hook Used", placeholder: "hook text or type" },
                ].map(({ key, label, type, opts, placeholder }) => (
                  <div key={key}>
                    <label className="mb-1 block text-xs font-medium text-slate-700">{label}</label>
                    {type === "select" ? (
                      <select value={logForm[key]} onChange={(e) => setLogForm((f) => ({ ...f, [key]: e.target.value }))}
                        className="w-full rounded border border-slate-200 px-2 py-1.5 text-xs">
                        <option value="">— select —</option>
                        {(opts || []).map(({ v, l }) => <option key={v} value={v}>{l}</option>)}
                      </select>
                    ) : (
                      <input type="text" value={logForm[key]} placeholder={placeholder}
                        onChange={(e) => setLogForm((f) => ({ ...f, [key]: e.target.value }))}
                        className="w-full rounded border border-slate-200 px-2 py-1.5 text-xs" />
                    )}
                  </div>
                ))}
                <div className="sm:col-span-2">
                  <label className="mb-1 block text-xs font-medium text-slate-700">Caption Used</label>
                  <textarea rows={2} value={logForm.caption_used}
                    onChange={(e) => setLogForm((f) => ({ ...f, caption_used: e.target.value }))}
                    placeholder="Caption as posted…"
                    className="w-full rounded border border-slate-200 px-2 py-1.5 text-xs" />
                </div>
                <div className="sm:col-span-2">
                  <label className="mb-1 block text-xs font-medium text-slate-700">Notes</label>
                  <input type="text" value={logForm.notes}
                    onChange={(e) => setLogForm((f) => ({ ...f, notes: e.target.value }))}
                    className="w-full rounded border border-slate-200 px-2 py-1.5 text-xs" />
                </div>
              </div>
              <button type="submit" disabled={logBusy}
                className="rounded bg-violet-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-violet-700 disabled:opacity-50">
                {logBusy ? "Saving…" : "Save Publish Log"}
              </button>
            </form>
          </div>
          {(manualPublishLogs || []).length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-slate-700">Recorded Publish Logs</p>
              {(manualPublishLogs || []).map((log) => (
                <div key={log._id} className="rounded border border-slate-200 bg-white p-3 text-xs">
                  <div className="flex flex-wrap gap-3">
                    <span className="font-medium text-slate-900">{log.platform || "—"}</span>
                    <span className="text-slate-500">asset: {(log.asset_render_id || "").slice(-8) || "—"}</span>
                    <span className="text-slate-500">by: {log.posted_by || "—"}</span>
                    <span className="text-slate-500">{log.posted_at || ""}</span>
                  </div>
                  {log.manual_post_url && <p className="mt-1 truncate text-blue-600">{log.manual_post_url}</p>}
                  {log.hook_used && <p className="mt-1 text-slate-600">Hook: {log.hook_used}</p>}
                  {log.notes && <p className="mt-1 text-slate-500">{log.notes}</p>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {subTab === "performance-entry" && (
        <div className="space-y-6">
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
            <p className="mb-1 text-sm font-semibold text-emerald-900">Enter Performance Metrics</p>
            <p className="mb-3 text-xs text-emerald-700">
              Manually enter metrics from the platform dashboard. No platform API is called. Score is calculated locally.
            </p>
            <div className="mb-3 flex items-center gap-2">
              <span className="text-xs text-slate-600">Live score preview:</span>
              <span className={`rounded px-2 py-0.5 text-sm font-bold ${scorePreview >= 7 ? "bg-green-100 text-green-800" : scorePreview >= 4 ? "bg-amber-100 text-amber-800" : "bg-red-100 text-red-700"}`}>
                {scorePreview.toFixed(2)} / 10
              </span>
              {calculatedScore !== null && <span className="text-xs text-slate-500">Last saved: {calculatedScore}</span>}
            </div>
            <form onSubmit={handleCreatePerf} className="space-y-3">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-700">Asset Render</label>
                  <select value={perfForm.asset_render_id} onChange={(e) => setPerfForm((f) => ({ ...f, asset_render_id: e.target.value }))}
                    className="w-full rounded border border-slate-200 px-2 py-1.5 text-xs">
                    <option value="">— select —</option>
                    {(assetRenders || []).map((r) => <option key={r._id} value={r._id}>{r._id.slice(-8)} · {r.status}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-700">Publish Log</label>
                  <select value={perfForm.manual_publish_log_id} onChange={(e) => setPerfForm((f) => ({ ...f, manual_publish_log_id: e.target.value }))}
                    className="w-full rounded border border-slate-200 px-2 py-1.5 text-xs">
                    <option value="">— select —</option>
                    {(manualPublishLogs || []).map((l) => <option key={l._id} value={l._id}>{l._id.slice(-8)} · {l.platform}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-700">Platform</label>
                  <select value={perfForm.platform} onChange={(e) => setPerfForm((f) => ({ ...f, platform: e.target.value }))}
                    className="w-full rounded border border-slate-200 px-2 py-1.5 text-xs">
                    <option value="">— select —</option>
                    {PERF_PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
                {[
                  { key: "views", label: "Views" }, { key: "likes", label: "Likes" },
                  { key: "comments", label: "Comments" }, { key: "shares", label: "Shares" },
                  { key: "saves", label: "Saves" }, { key: "clicks", label: "Clicks" },
                  { key: "follows", label: "Follows" }, { key: "watch_time_seconds", label: "Watch Time (s)" },
                  { key: "average_view_duration", label: "Avg View Dur (s)" },
                  { key: "retention_rate", label: "Retention (0–1)" },
                  { key: "engagement_rate", label: "Engagement (0–1 or blank=auto)" },
                ].map(({ key, label }) => (
                  <div key={key}>
                    <label className="mb-1 block text-xs font-medium text-slate-700">{label}</label>
                    <input type="number" step="any" min="0" value={perfForm[key]} placeholder="0"
                      onChange={(e) => setPerfForm((f) => ({ ...f, [key]: e.target.value }))}
                      className="w-full rounded border border-slate-200 px-2 py-1.5 text-xs" />
                  </div>
                ))}
                <div className="col-span-3 sm:col-span-6">
                  <label className="mb-1 block text-xs font-medium text-slate-700">Notes</label>
                  <input type="text" value={perfForm.notes} onChange={(e) => setPerfForm((f) => ({ ...f, notes: e.target.value }))}
                    className="w-full rounded border border-slate-200 px-2 py-1.5 text-xs" />
                </div>
              </div>
              <button type="submit" disabled={perfBusy}
                className="rounded bg-emerald-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
                {perfBusy ? "Saving…" : "Save Performance Record"}
              </button>
            </form>
          </div>
          {(assetPerformanceRecords || []).length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-slate-700">Performance Records</p>
              {(assetPerformanceRecords || []).map((rec) => (
                <div key={rec._id} className="rounded border border-slate-200 bg-white p-3 text-xs">
                  <div className="flex flex-wrap gap-3">
                    <span className={`rounded px-1.5 py-0.5 font-bold ${(rec.performance_score || 0) >= 7 ? "bg-green-100 text-green-800" : (rec.performance_score || 0) >= 4 ? "bg-amber-100 text-amber-800" : "bg-red-100 text-red-700"}`}>
                      {rec.performance_score ?? "—"} / 10
                    </span>
                    <span className="text-slate-600">{rec.platform || "—"}</span>
                    <span className="text-slate-500">views: {rec.views ?? 0}</span>
                    <span className="text-slate-500">saves: {rec.saves ?? 0}</span>
                    <span className="text-slate-500">shares: {rec.shares ?? 0}</span>
                    <span className="text-slate-400 ml-auto">{rec.imported_from || "manual"}</span>
                  </div>
                  {rec.score_reason && <p className="mt-1 text-slate-400 break-all">{rec.score_reason}</p>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {subTab === "csv-import" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="mb-1 text-sm font-semibold text-slate-900">Import Performance Records from CSV</p>
            <p className="mb-3 text-xs text-slate-600">
              Paste CSV text (first row = headers). Columns: asset_render_id, manual_publish_log_id, platform,
              views, likes, comments, shares, saves, clicks, follows, watch_time_seconds,
              average_view_duration, retention_rate, engagement_rate, notes. No platform API called.
            </p>
            <form onSubmit={handleCSVImport} className="space-y-3">
              <textarea rows={8} value={csvText} onChange={(e) => setCsvText(e.target.value)}
                placeholder={"asset_render_id,platform,views,likes,saves\nabc123,instagram,5000,200,50"}
                className="w-full rounded border border-slate-200 px-3 py-2 font-mono text-xs" />
              <button type="submit" disabled={csvBusy}
                className="rounded bg-slate-700 px-4 py-1.5 text-xs font-medium text-white hover:bg-slate-900 disabled:opacity-50">
                {csvBusy ? "Importing…" : "Import CSV"}
              </button>
            </form>
          </div>
          {csvResult && (
            <div className="rounded border border-slate-200 bg-white p-3 text-xs">
              <p className="font-semibold text-slate-900">Imported: {csvResult.imported_count} · Errors: {csvResult.error_count}</p>
              {csvResult.import_errors?.length > 0 && (
                <div className="mt-2 space-y-1">
                  {csvResult.import_errors.map((e, i) => (
                    <div key={i} className="rounded bg-red-50 border border-red-200 p-2">
                      <span className="font-medium text-red-800">Row {e.row_index}: </span>
                      <span className="text-red-700">{(e.errors || []).join("; ")}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {subTab === "summary" && (
        <div className="space-y-6">
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
            <p className="mb-1 text-sm font-semibold text-blue-900">Generate Performance Summary</p>
            <p className="mb-3 text-xs text-blue-700">
              Aggregates performance records and generates advisory learning-loop recommendations.
              No automatic approvals. No outbound actions.
            </p>
            <div className="flex flex-wrap gap-3 items-end">
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-700">Asset Render</label>
                <select value={summaryAssetId} onChange={(e) => setSummaryAssetId(e.target.value)}
                  className="rounded border border-slate-200 px-2 py-1.5 text-xs">
                  <option value="">— select —</option>
                  {(assetRenders || []).map((r) => <option key={r._id} value={r._id}>{r._id.slice(-8)} · {r.status}</option>)}
                </select>
              </div>
              <button type="button" onClick={handleGenerateSummary} disabled={summaryBusy || !summaryAssetId}
                className="rounded bg-blue-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50">
                {summaryBusy ? "Generating…" : "Generate Summary"}
              </button>
            </div>
          </div>

          {summaryResult && (
            <div className="rounded-lg border border-blue-200 bg-white p-4 text-xs space-y-2">
              <p className="font-semibold text-slate-900">Latest Summary</p>
              <div className="flex flex-wrap gap-3">
                <span className={`rounded px-2 py-0.5 font-bold text-sm ${summaryResult.performance_score >= 7 ? "bg-green-100 text-green-800" : summaryResult.performance_score >= 4 ? "bg-amber-100 text-amber-800" : "bg-red-100 text-red-700"}`}>
                  {summaryResult.performance_score ?? "—"} avg
                </span>
                {summaryResult.best_performance_score !== undefined && <span className="text-slate-600">best: {summaryResult.best_performance_score}</span>}
                <span className="text-slate-500">{summaryResult.record_count ?? 0} record(s)</span>
                {summaryResult.platform && <span className="text-slate-500">platform: {summaryResult.platform}</span>}
                {summaryResult.hook_type && <span className="rounded bg-indigo-100 px-1.5 text-indigo-700">hook: {summaryResult.hook_type}</span>}
                {summaryResult.prompt_type && <span className="rounded bg-sky-100 px-1.5 text-sky-700">prompt: {summaryResult.prompt_type}</span>}
              </div>
              {(summaryResult.winning_factors || []).length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {summaryResult.winning_factors.map((f) => (
                    <span key={f} className="rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-800">{f}</span>
                  ))}
                </div>
              )}
              {summaryResult.improvement_notes && <p className="text-slate-600">{summaryResult.improvement_notes}</p>}
            </div>
          )}

          {recommendations && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-xs space-y-3">
              <p className="font-semibold text-amber-900">
                Advisory Recommendations
                <span className="ml-2 rounded bg-amber-200 px-1.5 py-0.5 text-amber-800">
                  {recommendations.based_on_summary_count} summaries · advisory only
                </span>
              </p>
              <p className="text-amber-700">{recommendations.note}</p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {[
                  { key: "top_hook_types", label: "Top Hook Types" },
                  { key: "top_prompt_types", label: "Top Prompt Types" },
                  { key: "top_generation_engines", label: "Top Engines" },
                  { key: "top_platforms", label: "Top Platforms" },
                ].map(({ key, label }) => (
                  <div key={key}>
                    <p className="mb-1 font-medium text-slate-700">{label}</p>
                    {recommendations[key]?.length > 0 ? (
                      <div className="space-y-1">
                        {recommendations[key].map((item, i) => (
                          <div key={i} className="flex items-center gap-2">
                            <span className="w-5 text-center text-slate-400">{i + 1}.</span>
                            <span className="flex-1 text-slate-800">{item.value}</span>
                            <span className="rounded bg-slate-100 px-1.5 text-slate-600">{item.avg_score} avg</span>
                            <span className="text-slate-400">{item.record_count}x</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-slate-400">No data yet.</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {(creativePerformanceSummaries || []).length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-slate-700">All Performance Summaries</p>
              {(creativePerformanceSummaries || []).map((s) => (
                <div key={s._id} className="rounded border border-slate-200 bg-white p-3 text-xs">
                  <div className="flex flex-wrap gap-3">
                    <span className={`rounded px-1.5 py-0.5 font-bold ${(s.performance_score || 0) >= 7 ? "bg-green-100 text-green-800" : (s.performance_score || 0) >= 4 ? "bg-amber-100 text-amber-800" : "bg-red-100 text-red-700"}`}>
                      {s.performance_score ?? "—"}
                    </span>
                    {s.hook_type && <span className="rounded bg-indigo-100 px-1.5 text-indigo-700">{s.hook_type}</span>}
                    {s.prompt_type && <span className="rounded bg-sky-100 px-1.5 text-sky-700">{s.prompt_type}</span>}
                    {s.platform && <span className="text-slate-500">{s.platform}</span>}
                    <span className="text-slate-400 ml-auto">{s.record_count ?? 0} records</span>
                  </div>
                  {(s.winning_factors || []).length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {s.winning_factors.map((f) => <span key={f} className="rounded bg-emerald-100 px-1 text-emerald-700">{f}</span>)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

const PROMPT_TYPE_LABELS = {
  faceless_motivational: "Faceless Motivational",
  cinematic_broll: "Cinematic B-Roll",
  abstract_motion: "Abstract Motion",
  business_explainer: "Business Explainer",
  quote_card_motion: "Quote Card Motion",
  podcast_clip_visual: "Podcast Clip Visual",
  educational_breakdown: "Educational Breakdown",
  luxury_brand_story: "Luxury Brand Story",
  product_service_ad: "Product / Service Ad",
};

const ENGINE_LABELS = {
  comfyui: "ComfyUI",
  seedance: "Seedance",
  higgsfield: "Higgsfield",
  runway: "Runway",
  manual: "Manual",
};

const PROMPT_STATUS_COLORS = {
  draft: "bg-slate-100 text-slate-700",
  approved: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
  needs_revision: "bg-amber-100 text-amber-800",
};

const RENDER_STATUS_COLORS = {
  queued: "bg-blue-100 text-blue-700",
  generated: "bg-indigo-100 text-indigo-700",
  needs_review: "bg-amber-100 text-amber-800",
  approved: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
  needs_revision: "bg-orange-100 text-orange-800",
};

// ---------------------------------------------------------------------------
// v5: AssetRenderSection
// ---------------------------------------------------------------------------

function AssetRenderSection({
  assetRenders,
  promptGenerations,
  contentSnippets,
  wsParam,
  onRefresh,
  showNotice,
  demoMode,
}) {
  const [filterStatus, setFilterStatus] = useState("");
  const [reviewingId, setReviewingId] = useState(null);
  const [reviewNote, setReviewNote] = useState("");
  const [renderingId, setRenderingId] = useState(null);
  const [busy, setBusy] = useState(false);

  const approvedPrompts = (promptGenerations || []).filter((pg) => pg.status === "approved");

  const filtered = (assetRenders || []).filter((r) => {
    if (filterStatus && r.status !== filterStatus) return false;
    return true;
  });

  async function handleRender(promptGen) {
    if (renderingId) return;
    const snippet = (contentSnippets || []).find((s) => s._id === promptGen.snippet_id);
    if (!snippet) {
      showNotice("Cannot render: linked snippet not found.");
      return;
    }
    setBusy(true);
    setRenderingId(promptGen._id);
    try {
      await api.createAssetRender({
        ...wsParam(),
        snippet_id: promptGen.snippet_id,
        prompt_generation_id: promptGen._id,
        client_id: promptGen.client_id || "",
        generation_engine: promptGen.generation_engine_target || "comfyui",
        add_captions: false,
      });
      showNotice("Asset render queued. Awaiting operator review. No content published.");
      onRefresh();
    } catch (err) {
      showNotice(err.message || "Render failed. Check snippet and prompt approval status.");
    } finally {
      setBusy(false);
      setRenderingId(null);
    }
  }

  async function handleReview(id, decision) {
    try {
      await api.reviewAssetRender(id, { decision, note: reviewNote });
      showNotice(`Asset render ${decision}d.`);
      setReviewingId(null);
      setReviewNote("");
      onRefresh();
    } catch {
      showNotice("Review failed. Please try again.");
    }
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-base font-semibold text-slate-950">Rendered Assets</h2>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
          {filtered.length} render{filtered.length !== 1 ? "s" : ""}
        </span>
        {demoMode && (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
            Demo Mode
          </span>
        )}
        <div className="ml-auto">
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="rounded border border-slate-200 px-2 py-1 text-xs"
          >
            <option value="">All Statuses</option>
            <option value="queued">Queued</option>
            <option value="generated">Generated</option>
            <option value="needs_review">Needs Review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="needs_revision">Needs Revision</option>
          </select>
        </div>
      </div>

      {/* Quick render from approved prompt */}
      {approvedPrompts.length > 0 && (
        <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-4">
          <p className="mb-2 text-sm font-medium text-indigo-900">
            Render asset from approved prompt
          </p>
          <div className="flex flex-wrap gap-2">
            {approvedPrompts.slice(0, 5).map((pg) => (
              <button
                key={pg._id}
                type="button"
                disabled={busy}
                onClick={() => handleRender(pg)}
                className="rounded border border-indigo-300 bg-white px-3 py-1 text-xs text-indigo-700 hover:bg-indigo-100 disabled:opacity-50"
              >
                {renderingId === pg._id ? "Queuing…" : (
                  (pg.prompt_type || "prompt").replace(/_/g, " ")
                  + (pg.snippet_id ? ` — snippet …${pg.snippet_id.slice(-4)}` : "")
                )}
              </button>
            ))}
          </div>
          <p className="mt-1 text-xs text-indigo-600">
            ComfyUI and FFmpeg each individually gated by env vars. No external calls in disabled mode.
          </p>
        </div>
      )}

      {filtered.length === 0 && (
        <p className="text-sm text-slate-400">
          No renders yet. Approve a prompt generation above to render an asset.
        </p>
      )}

      <div className="space-y-4">
        {filtered.map((render) => {
          const prompt = (promptGenerations || []).find((p) => p._id === render.prompt_generation_id);
          const snippet = (contentSnippets || []).find((s) => s._id === render.snippet_id);
          const isReviewing = reviewingId === render._id;
          const statusColor = RENDER_STATUS_COLORS[render.status] || "bg-slate-100 text-slate-700";

          return (
            <div key={render._id} className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusColor}`}>
                  {render.status}
                </span>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                  {render.asset_type || "video"}
                </span>
                <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700">
                  {render.generation_engine || "comfyui"}
                </span>
                {render.is_demo && (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">Demo</span>
                )}
                {/* Assembly status badge */}
                {render.assembly_status === "success" && (
                  <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700 font-medium">Real Render</span>
                )}
                {render.assembly_status === "failed" && (
                  <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700 font-medium">Render Failed</span>
                )}
                {(render.assembly_status === "mock" || (!render.assembly_status && render.assembly_result?.mock)) && (
                  <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-500">Mock Render</span>
                )}
                {/* Assembly engine badge */}
                {render.assembly_engine === "ffmpeg" && (
                  <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs text-violet-700">FFmpeg</span>
                )}
                {/* Image source badge */}
                {render.image_source === "comfyui" && (
                  <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs text-sky-700 font-medium">ComfyUI Image</span>
                )}
                {render.image_source === "placeholder" && (
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">Placeholder</span>
                )}
              </div>

              {snippet && (
                <p className="text-xs text-slate-500">
                  <span className="font-medium text-slate-700">Snippet: </span>
                  {(snippet.transcript_text || "").slice(0, 120)}
                  {snippet.transcript_text && snippet.transcript_text.length > 120 ? "…" : ""}
                </p>
              )}

              {prompt && (
                <p className="text-xs text-slate-500">
                  <span className="font-medium text-slate-700">Prompt type: </span>
                  {(prompt.prompt_type || "").replace(/_/g, " ")}
                </p>
              )}

              {/* Preview */}
              {(render.preview_url || render.file_path) && (
                <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  {render.preview_url ? (
                    <img
                      src={render.preview_url}
                      alt="Asset preview"
                      className="mx-auto max-h-48 rounded object-contain"
                    />
                  ) : (
                    <p className="text-xs text-slate-400 italic">
                      {render.assembly_status === "success" ? "Local render — " : "Mock path — "}
                      {render.file_path}
                    </p>
                  )}
                </div>
              )}

              {render.assembly_result?.skip_reason && (
                <p className="text-xs text-slate-400 italic">
                  Assembly skipped: {render.assembly_result.skip_reason}
                </p>
              )}
              {render.comfyui_partial_failure && render.comfyui_result?.fallback_reason && (
                <p className="text-xs text-amber-600 italic">
                  ComfyUI fallback: {render.comfyui_result.fallback_reason}
                </p>
              )}
              {render.assembly_result?.error && (
                <p className="text-xs text-red-400 italic">
                  Error: {render.assembly_result.error}
                </p>
              )}

              <p className="text-xs text-slate-400">
                Duration: {render.duration_seconds || 0}s · {render.resolution || "1080x1920"} ·{" "}
                {render.add_captions ? "Captions ON" : "No captions"}{" "}
                {render.assembly_engine ? `· Engine: ${render.assembly_engine}` : ""}
              </p>

              {/* Safety notice */}
              <p className="rounded bg-green-50 px-2 py-1 text-xs text-green-700">
                simulation_only: true · outbound_actions_taken: 0 · Local render — no external publishing.
              </p>

              {/* Review controls */}
              {render.status === "needs_review" && (
                isReviewing ? (
                  <div className="space-y-2">
                    <textarea
                      className="w-full rounded border border-slate-200 p-2 text-xs"
                      rows={2}
                      placeholder="Review note (optional)"
                      value={reviewNote}
                      onChange={(e) => setReviewNote(e.target.value)}
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => handleReview(render._id, "approve")}
                        className="rounded bg-green-600 px-3 py-1 text-xs text-white hover:bg-green-700"
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        onClick={() => handleReview(render._id, "reject")}
                        className="rounded bg-red-600 px-3 py-1 text-xs text-white hover:bg-red-700"
                      >
                        Reject
                      </button>
                      <button
                        type="button"
                        onClick={() => handleReview(render._id, "revise")}
                        className="rounded bg-amber-500 px-3 py-1 text-xs text-white hover:bg-amber-600"
                      >
                        Needs Revision
                      </button>
                      <button
                        type="button"
                        onClick={() => { setReviewingId(null); setReviewNote(""); }}
                        className="ml-auto rounded border border-slate-200 px-3 py-1 text-xs text-slate-600"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setReviewingId(render._id)}
                    className="rounded border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:bg-slate-50"
                  >
                    Review
                  </button>
                )
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function PromptLibrarySection({
  promptGenerations,
  contentSnippets,
  clientProfiles,
  wsParam,
  onRefresh,
  showNotice,
  demoMode,
}) {
  const [reviewingId, setReviewingId] = useState(null);
  const [reviewNote, setReviewNote] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterType, setFilterType] = useState("");

  const filtered = (promptGenerations || []).filter((pg) => {
    if (filterStatus && pg.status !== filterStatus) return false;
    if (filterType && pg.prompt_type !== filterType) return false;
    return true;
  });

  async function handleReview(id, decision) {
    try {
      await api.reviewPromptGeneration(id, { decision, note: reviewNote });
      showNotice(`Prompt ${decision}d.`);
      setReviewingId(null);
      setReviewNote("");
      onRefresh();
    } catch {
      showNotice("Review failed. Please try again.");
    }
  }

  async function handleGenerate(snippet) {
    try {
      await api.createPromptGeneration({
        ...wsParam(),
        snippet_id: snippet._id,
        client_id: snippet.client_id || "",
        prompt_type: "faceless_motivational",
        generation_engine_target: "comfyui",
      });
      showNotice("Prompt generated and saved as draft.");
      onRefresh();
    } catch {
      showNotice("Generation failed. Snippet must be approved.");
    }
  }

  const approvedSnippets = (contentSnippets || []).filter((s) => s.status === "approved");

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-base font-semibold text-slate-950">Prompt Library</h2>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
          {filtered.length} prompt{filtered.length !== 1 ? "s" : ""}
        </span>
        {demoMode && (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
            Demo Mode
          </span>
        )}
        <div className="ml-auto flex flex-wrap gap-2">
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="rounded border border-slate-200 px-2 py-1 text-xs"
          >
            <option value="">All Statuses</option>
            <option value="draft">Draft</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="needs_revision">Needs Revision</option>
          </select>
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="rounded border border-slate-200 px-2 py-1 text-xs"
          >
            <option value="">All Types</option>
            {Object.entries(PROMPT_TYPE_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Generate prompt from approved snippet */}
      {approvedSnippets.length > 0 && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
          <p className="mb-2 text-sm font-medium text-blue-900">
            Generate prompt from approved snippet
          </p>
          <div className="flex flex-wrap gap-2">
            {approvedSnippets.slice(0, 5).map((s) => (
              <button
                key={s._id}
                type="button"
                onClick={() => handleGenerate(s)}
                className="rounded border border-blue-300 bg-white px-3 py-1 text-xs text-blue-700 hover:bg-blue-100"
              >
                {s.transcript_text ? s.transcript_text.slice(0, 40) + "…" : s._id}
              </button>
            ))}
          </div>
          <p className="mt-1 text-xs text-blue-600">
            Generates a faceless_motivational prompt (ComfyUI target). No external calls made.
          </p>
        </div>
      )}

      {filtered.length === 0 && (
        <p className="text-sm text-slate-400">
          No prompt generations found. Approve a snippet to generate a visual prompt.
        </p>
      )}

      <div className="space-y-4">
        {filtered.map((pg) => {
          const snippet = (contentSnippets || []).find((s) => s._id === pg.snippet_id);
          const isReviewing = reviewingId === pg._id;
          const statusColor = PROMPT_STATUS_COLORS[pg.status] || "bg-slate-100 text-slate-700";

          return (
            <div key={pg._id} className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusColor}`}>
                  {pg.status}
                </span>
                <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs text-indigo-700">
                  {PROMPT_TYPE_LABELS[pg.prompt_type] || pg.prompt_type}
                </span>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                  {ENGINE_LABELS[pg.generation_engine_target] || pg.generation_engine_target}
                </span>
                {pg.is_demo && (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
                    Demo
                  </span>
                )}
              </div>

              {snippet && (
                <p className="text-xs text-slate-500">
                  <span className="font-medium text-slate-700">Snippet: </span>
                  {(snippet.transcript_text || "").slice(0, 120)}
                  {snippet.transcript_text && snippet.transcript_text.length > 120 ? "…" : ""}
                </p>
              )}

              <div className="rounded bg-slate-50 p-3 space-y-1">
                <p className="text-xs font-medium text-slate-700">Positive Prompt</p>
                <p className="text-xs text-slate-600">{pg.positive_prompt}</p>
              </div>

              {pg.scene_beats && pg.scene_beats.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-medium text-slate-700">Scene Beats</p>
                  <ol className="list-decimal pl-4 space-y-0.5">
                    {pg.scene_beats.map((beat, i) => (
                      <li key={i} className="text-xs text-slate-600">{beat}</li>
                    ))}
                  </ol>
                </div>
              )}

              {pg.caption_overlay_suggestion && (
                <p className="text-xs text-slate-500">
                  <span className="font-medium text-slate-700">Caption: </span>
                  {pg.caption_overlay_suggestion}
                </p>
              )}

              <p className="text-xs text-amber-700 bg-amber-50 rounded px-2 py-1">
                {pg.safety_notes}
              </p>

              {/* Review controls */}
              {pg.status === "draft" || pg.status === "needs_revision" ? (
                isReviewing ? (
                  <div className="space-y-2">
                    <textarea
                      className="w-full rounded border border-slate-200 p-2 text-xs"
                      rows={2}
                      placeholder="Review note (optional)"
                      value={reviewNote}
                      onChange={(e) => setReviewNote(e.target.value)}
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => handleReview(pg._id, "approve")}
                        className="rounded bg-green-600 px-3 py-1 text-xs text-white hover:bg-green-700"
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        onClick={() => handleReview(pg._id, "reject")}
                        className="rounded bg-red-600 px-3 py-1 text-xs text-white hover:bg-red-700"
                      >
                        Reject
                      </button>
                      <button
                        type="button"
                        onClick={() => handleReview(pg._id, "revise")}
                        className="rounded bg-amber-500 px-3 py-1 text-xs text-white hover:bg-amber-600"
                      >
                        Needs Revision
                      </button>
                      <button
                        type="button"
                        onClick={() => { setReviewingId(null); setReviewNote(""); }}
                        className="ml-auto rounded border border-slate-200 px-3 py-1 text-xs text-slate-600"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setReviewingId(pg._id)}
                    className="rounded border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:bg-slate-50"
                  >
                    Review
                  </button>
                )
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// v10.4 — Media Ingestion Section
// ---------------------------------------------------------------------------

function MediaIngestionSection({ mediaFolderScans, approvedUrlDownloads, mediaIntakeRecords, clientProfiles, wsParam, onRefresh, showNotice }) {
  const [activeTab, setActiveTab] = useState("folder");
  const [folderPath, setFolderPath] = useState("");
  const [folderClientId, setFolderClientId] = useState("");
  const [folderLabel, setFolderLabel] = useState("");
  const [folderIngestionSource, setFolderIngestionSource] = useState("local_folder");
  const [folderScanning, setFolderScanning] = useState(false);
  const [folderResult, setFolderResult] = useState(null);
  const [folderError, setFolderError] = useState("");

  const [dlUrl, setDlUrl] = useState("");
  const [dlClientId, setDlClientId] = useState("");
  const [dlPermission, setDlPermission] = useState(false);
  const [dlFormat, setDlFormat] = useState("video");
  const [dlNotes, setDlNotes] = useState("");
  const [dlSubmitting, setDlSubmitting] = useState(false);
  const [dlResult, setDlResult] = useState(null);
  const [dlError, setDlError] = useState("");

  // Filter clients to the active workspace and auto-select when there's only one
  const ws = wsParam();
  const filteredClients = ws.workspace_slug
    ? clientProfiles.filter((c) => c.workspace_slug === ws.workspace_slug)
    : clientProfiles;

  useEffect(() => {
    if (filteredClients.length === 1) {
      const id = filteredClients[0]._id;
      setFolderClientId((prev) => prev || id);
      setDlClientId((prev) => prev || id);
    }
  }, [filteredClients.length]);

  const ingestionIntakeRecords = mediaIntakeRecords.filter(
    (r) => r.intake_method === "local_folder_scan" || r.intake_method === "yt_dlp"
  );

  async function handleFolderScan(e) {
    e.preventDefault();
    if (!folderPath.trim()) { setFolderError("Folder path is required"); return; }
    setFolderScanning(true);
    setFolderError("");
    setFolderResult(null);
    try {
      const result = await api.createMediaFolderScan({
        folder_path: folderPath.trim(),
        client_id: folderClientId,
        source_label: folderLabel,
        ingestion_source: folderIngestionSource,
      });
      setFolderResult(result);
      showNotice(`Scan complete: ${result.discovered_count} file(s) discovered.`);
      onRefresh();
    } catch (err) {
      setFolderError(err.message || "Scan failed");
    } finally {
      setFolderScanning(false);
    }
  }

  async function handleUrlDownload(e) {
    e.preventDefault();
    if (!dlUrl.trim()) { setDlError("URL is required"); return; }
    if (!dlPermission) { setDlError("You must confirm you have permission to download this content"); return; }
    setDlSubmitting(true);
    setDlError("");
    setDlResult(null);
    try {
      const result = await api.createApprovedUrlDownload({
        url: dlUrl.trim(),
        client_id: dlClientId,
        permission_confirmed: dlPermission,
        requested_format: dlFormat,
        notes: dlNotes,
      });
      setDlResult(result);
      if (result.status === "skipped") {
        showNotice(`Download skipped: ${result.skip_reason}`);
      } else if (result.status === "completed") {
        showNotice("Download complete. File saved locally.");
        onRefresh();
      } else {
        showNotice(`Download ${result.status}.`);
      }
    } catch (err) {
      setDlError(err.message || "Download request failed");
    } finally {
      setDlSubmitting(false);
    }
  }

  return (
    <section className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-slate-950">Media Ingestion</h2>
        <p className="mt-1 text-xs text-slate-500">
          Ingest approved client media from local synced folders or approved URL downloads. All media is stored locally and requires review before use.
        </p>
      </div>

      {/* Safety notice */}
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        <strong>Permission required:</strong> Only use media you own or have explicit permission to process.
        SignalForge stores files locally and does <strong>not</strong> publish, upload, or transmit media to any third party.
        No likeness, avatar, or voice cloning is performed.
      </div>

      {/* Sub-tabs */}
      <div className="flex gap-2 border-b border-slate-200 pb-1">
        {[
          { id: "folder", label: `Folder Scan (${mediaFolderScans.length})` },
          { id: "url", label: `URL Download (${approvedUrlDownloads.length})` },
          { id: "ingested", label: `Ingested Media (${ingestionIntakeRecords.length})` },
        ].map(({ id, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setActiveTab(id)}
            className={[
              "rounded-t px-3 py-1.5 text-sm font-medium transition",
              activeTab === id ? "border-b-2 border-blue-600 text-blue-700" : "text-slate-500 hover:text-slate-800",
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Folder Scan */}
      {activeTab === "folder" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-white p-5 space-y-4">
            <h3 className="text-sm font-semibold text-slate-800">Shared Folder / Drive Scan</h3>
            <p className="text-xs text-slate-500">
              Scan a local folder, Google Drive synced folder, or Dropbox synced folder for supported media files
              (.mp4, .mov, .m4v, .mp3, .wav, .m4a).
            </p>
            <form onSubmit={handleFolderScan} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Folder Path <span className="text-red-500">*</span></label>
                <input
                  value={folderPath}
                  onChange={(e) => setFolderPath(e.target.value)}
                  placeholder="/Users/you/Google Drive/My Drive/ClientMedia"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Client</label>
                  <select
                    value={folderClientId}
                    onChange={(e) => setFolderClientId(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-2 py-2 text-sm text-slate-700 outline-none focus:border-blue-300"
                  >
                    {filteredClients.length === 0 ? (
                      <option value="" disabled>No clients in this workspace</option>
                    ) : (
                      <>
                        <option value="">— Select client —</option>
                        {filteredClients.map((c) => (
                          <option key={c._id} value={c._id}>{c.client_name || c._id}</option>
                        ))}
                      </>
                    )}
                  </select>
                  {filteredClients.length === 0 && (
                    <p className="mt-1 text-xs text-amber-600">No clients found in this workspace. Create a client profile first.</p>
                  )}
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Ingestion Source</label>
                  <select
                    value={folderIngestionSource}
                    onChange={(e) => setFolderIngestionSource(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-2 py-2 text-sm text-slate-700 outline-none focus:border-blue-300"
                  >
                    <option value="local_folder">Local Folder</option>
                    <option value="google_drive_sync">Google Drive Sync</option>
                    <option value="dropbox_sync">Dropbox Sync</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Source Label (optional)</label>
                <input
                  value={folderLabel}
                  onChange={(e) => setFolderLabel(e.target.value)}
                  placeholder="e.g. John Maxwell – YouTube Recordings"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                />
              </div>
              {folderError && <p className="text-xs text-red-600">{folderError}</p>}
              <button
                type="submit"
                disabled={folderScanning}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {folderScanning ? "Scanning…" : "Scan Folder"}
              </button>
            </form>

            {folderResult && (
              <div className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm space-y-1">
                <div className="font-semibold text-green-800">Scan complete</div>
                <div className="text-xs text-green-700">
                  Discovered: {folderResult.discovered_count} · Registered: {folderResult.registered_count} · Skipped: {folderResult.skipped_count} · Failed: {folderResult.failed_count}
                </div>
                {folderResult.errors?.length > 0 && (
                  <div className="text-xs text-red-600">{folderResult.errors.join("; ")}</div>
                )}
              </div>
            )}
          </div>

          {/* Past scans table */}
          {mediaFolderScans.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
              <div className="px-4 py-2 border-b border-slate-100 bg-slate-50">
                <span className="text-xs font-semibold text-slate-600">Previous Scans</span>
              </div>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-100 text-left text-slate-500">
                    <th className="px-4 py-2">Folder</th>
                    <th className="px-4 py-2">Source</th>
                    <th className="px-4 py-2">Found</th>
                    <th className="px-4 py-2">Registered</th>
                    <th className="px-4 py-2">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {mediaFolderScans.map((scan) => (
                    <tr key={scan._id} className="border-b border-slate-50 hover:bg-slate-50">
                      <td className="px-4 py-2 font-mono text-xs text-slate-700 max-w-xs truncate">{scan.folder_path}</td>
                      <td className="px-4 py-2 text-slate-500">{scan.ingestion_source?.replace("_", " ")}</td>
                      <td className="px-4 py-2">{scan.discovered_count}</td>
                      <td className="px-4 py-2">{scan.registered_count}</td>
                      <td className="px-4 py-2 text-slate-400">{formatDate(scan.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* URL Download */}
      {activeTab === "url" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-white p-5 space-y-4">
            <h3 className="text-sm font-semibold text-slate-800">Approved URL Download</h3>
            <p className="text-xs text-slate-500">
              Download media from an approved URL using yt-dlp. Requires <code className="bg-slate-100 px-1 rounded">YTDLP_ENABLED=true</code> in environment
              and operator permission confirmation. Downloaded files are stored locally only.
            </p>
            <form onSubmit={handleUrlDownload} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">URL <span className="text-red-500">*</span></label>
                <input
                  value={dlUrl}
                  onChange={(e) => setDlUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=..."
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Client</label>
                  <select
                    value={dlClientId}
                    onChange={(e) => setDlClientId(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-2 py-2 text-sm text-slate-700 outline-none focus:border-blue-300"
                  >
                    {filteredClients.length === 0 ? (
                      <option value="" disabled>No clients in this workspace</option>
                    ) : (
                      <>
                        <option value="">— Select client —</option>
                        {filteredClients.map((c) => (
                          <option key={c._id} value={c._id}>{c.client_name || c._id}</option>
                        ))}
                      </>
                    )}
                  </select>
                  {filteredClients.length === 0 && (
                    <p className="mt-1 text-xs text-amber-600">No clients found in this workspace. Create a client profile first.</p>
                  )}
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Format</label>
                  <select
                    value={dlFormat}
                    onChange={(e) => setDlFormat(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-2 py-2 text-sm text-slate-700 outline-none focus:border-blue-300"
                  >
                    <option value="video">Video</option>
                    <option value="audio">Audio only</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Notes</label>
                <input
                  value={dlNotes}
                  onChange={(e) => setDlNotes(e.target.value)}
                  placeholder="e.g. Approved by client on 2026-05-01"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                />
              </div>
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={dlPermission}
                  onChange={(e) => setDlPermission(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-slate-300 accent-blue-600"
                />
                <span className="text-xs text-slate-700">
                  I confirm the operator has permission from the content owner to download and process this media.
                </span>
              </label>
              {dlError && <p className="text-xs text-red-600">{dlError}</p>}
              <button
                type="submit"
                disabled={dlSubmitting}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {dlSubmitting ? "Downloading…" : "Download"}
              </button>
            </form>

            {dlResult && (
              <div className={`rounded-lg border p-3 text-sm space-y-1 ${dlResult.status === "completed" ? "border-green-200 bg-green-50" : dlResult.status === "skipped" ? "border-amber-200 bg-amber-50" : "border-red-200 bg-red-50"}`}>
                <div className={`font-semibold ${dlResult.status === "completed" ? "text-green-800" : dlResult.status === "skipped" ? "text-amber-800" : "text-red-800"}`}>
                  {dlResult.status === "completed" ? "Download complete" : dlResult.status === "skipped" ? "Skipped" : "Failed"}
                </div>
                {dlResult.skip_reason && <div className="text-xs text-amber-700">{dlResult.skip_reason}</div>}
                {dlResult.error_message && <div className="text-xs text-red-700">{dlResult.error_message}</div>}
                {dlResult.item?.output_path && <div className="text-xs text-green-700 font-mono">{dlResult.item.output_path}</div>}
              </div>
            )}
          </div>

          {/* Past downloads table */}
          {approvedUrlDownloads.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
              <div className="px-4 py-2 border-b border-slate-100 bg-slate-50">
                <span className="text-xs font-semibold text-slate-600">Download History</span>
              </div>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-100 text-left text-slate-500">
                    <th className="px-4 py-2">URL</th>
                    <th className="px-4 py-2">Format</th>
                    <th className="px-4 py-2">Status</th>
                    <th className="px-4 py-2">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {approvedUrlDownloads.map((dl) => (
                    <tr key={dl._id} className="border-b border-slate-50 hover:bg-slate-50">
                      <td className="px-4 py-2 max-w-xs truncate font-mono text-slate-600">{dl.url}</td>
                      <td className="px-4 py-2 text-slate-500">{dl.requested_format}</td>
                      <td className="px-4 py-2">
                        <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${dl.status === "completed" ? "bg-green-100 text-green-700" : dl.status === "skipped" ? "bg-amber-100 text-amber-700" : dl.status === "failed" ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-600"}`}>
                          {dl.status}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-slate-400">{formatDate(dl.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Ingested Media */}
      {activeTab === "ingested" && (
        <div className="space-y-3">
          {ingestionIntakeRecords.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
              No ingested media yet. Use Folder Scan or URL Download to ingest approved client media.
            </div>
          ) : (
            ingestionIntakeRecords.map((rec) => (
              <div key={rec._id} className="rounded-lg border border-slate-200 bg-white p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-mono text-slate-600">{rec.extension}</span>
                    <span className={`rounded px-2 py-0.5 text-xs font-medium ${rec.media_type === "video" ? "bg-blue-100 text-blue-700" : "bg-purple-100 text-purple-700"}`}>{rec.media_type}</span>
                    <span className="text-sm font-medium text-slate-800 truncate max-w-xs">{rec.filename || rec.media_path}</span>
                  </div>
                  <span className={`rounded px-2 py-0.5 text-xs font-medium ${rec.ingestion_status === "discovered" ? "bg-amber-100 text-amber-700" : rec.ingestion_status === "registered" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                    {rec.ingestion_status || rec.status}
                  </span>
                </div>
                <div className="text-xs text-slate-400 font-mono truncate">{rec.original_file_path || rec.media_path}</div>
                <div className="flex flex-wrap gap-3 text-xs text-slate-500">
                  {rec.size_bytes > 0 && <span>{(rec.size_bytes / 1024 / 1024).toFixed(1)} MB</span>}
                  {rec.duration_seconds && <span>{Math.round(rec.duration_seconds)}s</span>}
                  <span>{rec.ingestion_source?.replace(/_/g, " ")}</span>
                  {rec.source_label && <span>{rec.source_label}</span>}
                </div>
                {rec.source_content_id && (
                  <div className="text-xs text-slate-400">Linked source content: <code className="bg-slate-100 px-1 rounded">{rec.source_content_id}</code></div>
                )}
                <div className="flex gap-2 mt-1">
                  <span className="text-xs text-slate-400 italic">Next steps: extract audio → transcript → generate snippets</span>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function CreativeStudioPage({ activeWorkspace, refreshTrigger = 0 }) {
  const [briefs, setBriefs] = useState([]);
  const [drafts, setDrafts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showBriefForm, setShowBriefForm] = useState(false);
  const [notice, setNotice] = useState("");
  const [briefFilters, setBriefFilters] = useState({ ...emptyBriefFilters });
  const [draftFilters, setDraftFilters] = useState({ ...emptyDraftFilters });
  const [activeSection, setActiveSection] = useState("briefs");
  const demoMode = api.demoEnabled();

  // v2 state
  const [clientProfiles, setClientProfiles] = useState([]);
  const [sourceChannels, setSourceChannels] = useState([]);
  const [sourceContent, setSourceContent] = useState([]);
  const [contentSnippets, setContentSnippets] = useState([]);
  const [creativeAssets, setCreativeAssets] = useState([]);

  // v6.5 snippet filter
  const [minScore, setMinScore] = useState(0);

  // v3 state
  const [audioExtractionRuns, setAudioExtractionRuns] = useState([]);
  const [transcriptRuns, setTranscriptRuns] = useState([]);
  const [transcriptSegments, setTranscriptSegments] = useState([]);

  // v4 state
  const [mediaIntakeRecords, setMediaIntakeRecords] = useState([]);

  // v4.5 state
  const [promptGenerations, setPromptGenerations] = useState([]);

  // v5 state
  const [assetRenders, setAssetRenders] = useState([]);

  // v7.5 state
  const [manualPublishLogs, setManualPublishLogs] = useState([]);
  const [assetPerformanceRecords, setAssetPerformanceRecords] = useState([]);
  const [creativePerformanceSummaries, setCreativePerformanceSummaries] = useState([]);

  // v8 state
  const [campaignPacks, setCampaignPacks] = useState([]);
  const [campaignReports, setCampaignReports] = useState([]);
  // v8.5 state
  const [campaignExports, setCampaignExports] = useState([]);

  // v9.5: Client Intelligence Layer
  const [clientIntelligenceRecords, setClientIntelligenceRecords] = useState([]);
  const [leadCorrelations, setLeadCorrelations] = useState([]);

  // v10.4: Media Ingestion Layer
  const [mediaFolderScans, setMediaFolderScans] = useState([]);
  const [approvedUrlDownloads, setApprovedUrlDownloads] = useState([]);

  async function load() {
    setLoading(true);
    try {
      const [briefData, draftData, profilesData, channelsData, contentData, snippetsData, assetsData, audioRunsData, transcriptRunsData, segmentsData, intakeData, promptGenData, assetRendersData, publishLogsData, perfRecordsData, perfSummariesData, campaignPacksData, campaignReportsData, campaignExportsData, clientIntelligenceData, leadCorrelationsData, mediaFolderScansData, approvedUrlDownloadsData] = await Promise.all([
        api.contentBriefs({ ...wsParam() }),
        api.contentDrafts({ ...wsParam() }),
        api.clientProfiles({ ...wsParam() }),
        api.sourceChannels({ ...wsParam() }),
        api.sourceContent({ ...wsParam() }),
        api.contentSnippets({ ...wsParam() }),
        api.creativeAssets({ ...wsParam() }),
        api.audioExtractionRuns({ ...wsParam() }),
        api.transcriptRuns({ ...wsParam() }),
        api.transcriptSegments({ ...wsParam() }),
        api.mediaIntakeRecords({ ...wsParam() }),
        api.promptGenerations({ ...wsParam() }),
        api.assetRenders({ ...wsParam() }),
        api.manualPublishLogs({ ...wsParam() }),
        api.assetPerformanceRecords({ ...wsParam() }),
        api.creativePerformanceSummaries({ ...wsParam() }),
        api.campaignPacks({ ...wsParam() }),
        api.campaignReports({ ...wsParam() }),
        api.campaignExports({ ...wsParam() }),
        api.clientIntelligence({ ...wsParam() }),
        api.leadContentCorrelations({ ...wsParam() }),
        api.mediaFolderScans({ ...wsParam() }),
        api.approvedUrlDownloads({ ...wsParam() }),
      ]);
      setBriefs(briefData.items || []);
      setDrafts(draftData.items || []);
      setClientProfiles(profilesData.items || []);
      setSourceChannels(channelsData.items || []);
      setSourceContent(contentData.items || []);
      setContentSnippets(snippetsData.items || []);
      setCreativeAssets(assetsData.items || []);
      setAudioExtractionRuns(audioRunsData.items || []);
      setTranscriptRuns(transcriptRunsData.items || []);
      setTranscriptSegments(segmentsData.items || []);
      setMediaIntakeRecords(intakeData.items || []);
      setPromptGenerations(promptGenData.items || []);
      setAssetRenders(assetRendersData.items || []);
      setManualPublishLogs(publishLogsData.items || []);
      setAssetPerformanceRecords(perfRecordsData.items || []);
      setCreativePerformanceSummaries(perfSummariesData.items || []);
      setCampaignPacks(campaignPacksData.items || []);
      setCampaignReports(campaignReportsData.items || []);
      setCampaignExports(campaignExportsData.items || []);
      setClientIntelligenceRecords(clientIntelligenceData.items || []);
      setLeadCorrelations(leadCorrelationsData.items || []);
      setMediaFolderScans(mediaFolderScansData.items || []);
      setApprovedUrlDownloads(approvedUrlDownloadsData.items || []);
    } catch {
      // fail silently
    } finally {
      setLoading(false);
    }
  }

  function wsParam() {
    const ws = getAppWorkspace();
    return ws && ws !== "all" ? { workspace_slug: ws } : {};
  }

  useEffect(() => {
    load();
  }, [activeWorkspace, refreshTrigger]);

  function showNotice(msg) {
    setNotice(msg);
    setTimeout(() => setNotice(""), 3500);
  }

  function handleBriefCreated(item) {
    setShowBriefForm(false);
    showNotice(`Brief "${item.campaign_name || "Untitled"}" created.`);
    load();
  }

  // Filtered briefs
  const filteredBriefs = briefs.filter((b) => {
    if (briefFilters.module && b.module !== briefFilters.module) return false;
    if (briefFilters.platform && b.platform !== briefFilters.platform) return false;
    if (briefFilters.status && b.status !== briefFilters.status) return false;
    return true;
  });

  // Filtered drafts
  const filteredDrafts = drafts.filter((d) => {
    if (draftFilters.module && d.module !== draftFilters.module) return false;
    if (draftFilters.platform && d.platform !== draftFilters.platform) return false;
    if (draftFilters.content_type && d.content_type !== draftFilters.content_type) return false;
    if (draftFilters.status && d.status !== draftFilters.status) return false;
    return true;
  });

  const needsReviewDrafts = drafts.filter((d) => d.status === "needs_review");
  const approvedDrafts = drafts.filter((d) => d.status === "approved");
  const agentDrafts = drafts.filter((d) => d.generated_by_agent);

  const uniqueModules = [...new Set(briefs.map((b) => b.module).concat(drafts.map((d) => d.module)).filter(Boolean))].sort();
  const uniquePlatforms = [...new Set(briefs.map((b) => b.platform).concat(drafts.map((d) => d.platform)).filter(Boolean))].sort();

  return (
    <div className="space-y-6">
      <DemoPageBanner demoMode={demoMode} />

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-950">Creative Studio</h1>
          <p className="mt-1 text-sm text-slate-500">
            Plan and review content briefs and AI-generated drafts. No publishing or scheduling.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowBriefForm((v) => !v)}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700"
        >
          <FilePlus2 className="h-4 w-4" />
          {showBriefForm ? "Cancel" : "New Brief"}
        </button>
      </div>

      {notice && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-2 text-sm text-green-700">
          {notice}
        </div>
      )}

      {/* Safety notice */}
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
        <strong>Safety:</strong> SignalForge does not publish, schedule, or post content to any platform. All drafts require explicit operator review before use.
      </div>

      {/* Brief form */}
      {showBriefForm && (
        <section className="rounded-lg border border-blue-200 bg-blue-50 p-5">
          <h2 className="mb-4 text-lg font-semibold text-slate-950">Create Content Brief</h2>
          <BriefForm
            workspaceSlug={getAppWorkspace() !== "all" ? getAppWorkspace() : ""}
            onCreated={handleBriefCreated}
            onCancel={() => setShowBriefForm(false)}
          />
        </section>
      )}

      {/* Workflow Steps */}
      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="mb-3 text-base font-semibold text-slate-950">Workflow</h2>
        <div className="flex flex-wrap gap-2">
          {WORKFLOW_STEPS.map((step) => (
            <div key={step.id} className="flex min-w-[160px] flex-1 flex-col gap-1 rounded-lg border border-slate-100 bg-slate-50 p-3">
              <div className="flex items-center gap-2">
                <step.icon className="h-4 w-4 text-blue-500" />
                <span className="text-xs font-semibold text-slate-700">Step {step.id}: {step.label}</span>
              </div>
              <p className="text-xs leading-5 text-slate-500">{step.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* KPI bar */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          { label: "Total Briefs", value: briefs.length },
          { label: "Total Drafts", value: drafts.length },
          { label: "Needs Review", value: needsReviewDrafts.length },
          { label: "Approved", value: approvedDrafts.length },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="text-2xl font-bold text-slate-950">{loading ? "—" : value}</div>
            <div className="mt-1 text-xs font-medium text-slate-500">{label}</div>
          </div>
        ))}
      </div>

      {/* Section tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-1">
        {[
          { id: "briefs", label: `Briefs (${filteredBriefs.length})` },
          { id: "review", label: `Needs Review (${needsReviewDrafts.length})` },
          { id: "approved", label: `Approved (${approvedDrafts.length})` },
          { id: "agent", label: `Agent Generated (${agentDrafts.length})` },
          { id: "all-drafts", label: `All Drafts (${filteredDrafts.length})` },
          { id: "clients", label: `Clients (${clientProfiles.length})` },
          { id: "source-channels", label: `Source Channels (${sourceChannels.length})` },
          { id: "source-content", label: `Source Content (${sourceContent.length})` },
          { id: "snippets", label: `Snippets (${contentSnippets.length})` },
          { id: "assets", label: `Assets (${creativeAssets.length})` },
          { id: "approval-queue", label: `Approval Queue (${[...contentSnippets, ...creativeAssets].filter((i) => i.status === "needs_review").length})` },
          { id: "ingest", label: `Ingest Pipeline (${transcriptRuns.length})` },
          { id: "prompts", label: `Prompt Library (${promptGenerations.length})` },
          { id: "renders", label: `Rendered Assets (${assetRenders.length})` },
          { id: "performance-loop", label: `Performance Loop (${manualPublishLogs.length})` },
          { id: "campaign-packs", label: `Campaign Packs (${campaignPacks.length})` },
          { id: "campaign-exports", label: `Exports (${campaignExports.length})` },
          { id: "client-intelligence", label: `Intelligence (${clientIntelligenceRecords.length})` },
          { id: "media-ingestion", label: `Media Ingestion (${mediaFolderScans.length + approvedUrlDownloads.length})` },
          { id: "poc-demo", label: demoMode ? "POC Demo ✦" : "POC Demo" },
        ].map(({ id, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setActiveSection(id)}
            className={[
              "rounded-t-lg px-4 py-2 text-sm font-medium transition",
              activeSection === id
                ? "border-b-2 border-blue-600 text-blue-700"
                : "text-slate-500 hover:text-slate-800",
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </div>

      {/* BRIEFS section */}
      {activeSection === "briefs" && (
        <section className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <h2 className="text-base font-semibold text-slate-950">Content Briefs</h2>
            <div className="ml-auto flex flex-wrap gap-3">
              <div className="w-36">
                <SelectFilter
                  label="Module"
                  value={briefFilters.module}
                  onChange={(v) => setBriefFilters((f) => ({ ...f, module: v }))}
                  options={uniqueModules.length ? uniqueModules : MODULES}
                />
              </div>
              <div className="w-36">
                <SelectFilter
                  label="Platform"
                  value={briefFilters.platform}
                  onChange={(v) => setBriefFilters((f) => ({ ...f, platform: v }))}
                  options={uniquePlatforms.length ? uniquePlatforms : PLATFORMS}
                />
              </div>
              <div className="w-36">
                <SelectFilter
                  label="Status"
                  value={briefFilters.status}
                  onChange={(v) => setBriefFilters((f) => ({ ...f, status: v }))}
                  options={BRIEF_STATUSES}
                />
              </div>
              {(briefFilters.module || briefFilters.platform || briefFilters.status) && (
                <button
                  type="button"
                  onClick={() => setBriefFilters({ ...emptyBriefFilters })}
                  className="self-end rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-500 hover:bg-slate-50"
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          {loading ? (
            <p className="text-sm text-slate-500">Loading briefs…</p>
          ) : filteredBriefs.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
              {getAppWorkspace() !== "all"
                ? "No briefs for this workspace. Create a brief to get started."
                : "No content briefs yet. Create one above to define a campaign."}
            </div>
          ) : (
            <div className="space-y-2">
              {filteredBriefs.map((brief) => (
                <BriefRow
                  key={brief._id}
                  brief={brief}
                  relatedDrafts={drafts.filter((d) => d.brief_id === brief._id)}
                  onRefresh={load}
                />
              ))}
            </div>
          )}
        </section>
      )}

      {/* NEEDS REVIEW section */}
      {activeSection === "review" && (
        <section className="space-y-4">
          <h2 className="text-base font-semibold text-slate-950">Drafts Needing Review</h2>
          {loading ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : needsReviewDrafts.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
              No drafts awaiting review.
            </div>
          ) : (
            <div className="space-y-2">
              {needsReviewDrafts.map((d) => (
                <DraftRow key={d._id} draft={d} onRefresh={load} />
              ))}
            </div>
          )}
        </section>
      )}

      {/* APPROVED section */}
      {activeSection === "approved" && (
        <section className="space-y-4">
          <div>
            <h2 className="text-base font-semibold text-slate-950">Approved Content</h2>
            <p className="mt-1 text-xs text-slate-500">
              These drafts have been reviewed and approved. Copy content manually for use outside SignalForge.
            </p>
          </div>
          {loading ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : approvedDrafts.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
              No approved content yet. Review drafts to approve them.
            </div>
          ) : (
            <div className="space-y-2">
              {approvedDrafts.map((d) => (
                <DraftRow key={d._id} draft={d} onRefresh={load} />
              ))}
            </div>
          )}
        </section>
      )}

      {/* AGENT GENERATED section */}
      {activeSection === "agent" && (
        <section className="space-y-4">
          <div>
            <h2 className="text-base font-semibold text-slate-950">Agent Generated Content</h2>
            <p className="mt-1 text-xs text-slate-500">
              Drafts created by the content agent from approved briefs. All require human review before use.
            </p>
          </div>
          {loading ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : agentDrafts.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
              No agent-generated drafts yet. Approve a brief and run the content agent.
            </div>
          ) : (
            <div className="space-y-2">
              {agentDrafts.map((d) => (
                <DraftRow key={d._id} draft={d} onRefresh={load} />
              ))}
            </div>
          )}
        </section>
      )}

      {/* ALL DRAFTS section */}
      {activeSection === "all-drafts" && (
        <section className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <h2 className="text-base font-semibold text-slate-950">All Drafts</h2>
            <div className="ml-auto flex flex-wrap gap-3">
              <div className="w-36">
                <SelectFilter
                  label="Module"
                  value={draftFilters.module}
                  onChange={(v) => setDraftFilters((f) => ({ ...f, module: v }))}
                  options={uniqueModules.length ? uniqueModules : MODULES}
                />
              </div>
              <div className="w-36">
                <SelectFilter
                  label="Platform"
                  value={draftFilters.platform}
                  onChange={(v) => setDraftFilters((f) => ({ ...f, platform: v }))}
                  options={uniquePlatforms.length ? uniquePlatforms : PLATFORMS}
                />
              </div>
              <div className="w-36">
                <SelectFilter
                  label="Type"
                  value={draftFilters.content_type}
                  onChange={(v) => setDraftFilters((f) => ({ ...f, content_type: v }))}
                  options={CONTENT_TYPES}
                />
              </div>
              <div className="w-36">
                <SelectFilter
                  label="Status"
                  value={draftFilters.status}
                  onChange={(v) => setDraftFilters((f) => ({ ...f, status: v }))}
                  options={DRAFT_STATUSES}
                />
              </div>
              {(draftFilters.module || draftFilters.platform || draftFilters.content_type || draftFilters.status) && (
                <button
                  type="button"
                  onClick={() => setDraftFilters({ ...emptyDraftFilters })}
                  className="self-end rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-500 hover:bg-slate-50"
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          {loading ? (
            <p className="text-sm text-slate-500">Loading drafts…</p>
          ) : filteredDrafts.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
              No drafts match these filters.
            </div>
          ) : (
            <div className="space-y-2">
              {filteredDrafts.map((d) => (
                <DraftRow key={d._id} draft={d} onRefresh={load} />
              ))}
            </div>
          )}
        </section>
      )}

      {/* v2: CLIENTS section */}
      {activeSection === "clients" && (
        <section className="space-y-4">
          <div>
            <h2 className="text-base font-semibold text-slate-950">Client Profiles</h2>
            <p className="mt-1 text-xs text-slate-500">
              Defines brand permissions and compliance rules per client. Likeness, voice, and avatar rights default to off.
            </p>
          </div>
          {loading ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : clientProfiles.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
              No client profiles. Create one via the API or import workflow.
            </div>
          ) : (
            <div className="space-y-2">
              {clientProfiles.map((p) => (
                <ClientProfileRow key={p._id} profile={p} />
              ))}
            </div>
          )}
        </section>
      )}

      {/* v2: SOURCE CHANNELS section */}
      {activeSection === "source-channels" && (
        <section className="space-y-4">
          <div>
            <h2 className="text-base font-semibold text-slate-950">Source Channels</h2>
            <p className="mt-1 text-xs text-slate-500">
              Channels approved for content ingestion and reuse. Unapproved channels are visible but blocked from processing.
            </p>
          </div>
          {loading ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : sourceChannels.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
              No source channels yet.
            </div>
          ) : (
            <div className="space-y-2">
              {sourceChannels.map((c) => (
                <SourceChannelRow key={c._id} channel={c} />
              ))}
            </div>
          )}
        </section>
      )}

      {/* v2: SOURCE CONTENT section */}
      {activeSection === "source-content" && (
        <section className="space-y-4">
          <div>
            <h2 className="text-base font-semibold text-slate-950">Source Content</h2>
            <p className="mt-1 text-xs text-slate-500">
              Discovered videos and posts. Items must reach "approved" status before snippets are extracted.
            </p>
          </div>
          {loading ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : sourceContent.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
              No source content yet.
            </div>
          ) : (
            <div className="space-y-2">
              {sourceContent.map((c) => (
                <SourceContentRow key={c._id} content={c} />
              ))}
            </div>
          )}
        </section>
      )}

      {/* v2: SNIPPETS section */}
      {activeSection === "snippets" && (
        <section className="space-y-4">
          <div>
            <h2 className="text-base font-semibold text-slate-950">Content Snippets</h2>
            <p className="mt-1 text-xs text-slate-500">
              Scored transcript segments extracted from approved source content. Review each before assets are generated.
            </p>
          </div>
          {/* v6.5 min score filter */}
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-600 font-medium whitespace-nowrap">Min overall score</label>
            <input
              type="range"
              min={0}
              max={10}
              step={0.5}
              value={minScore}
              onChange={(e) => setMinScore(parseFloat(e.target.value))}
              className="w-32 accent-emerald-600"
            />
            <span className="w-8 text-xs font-medium text-emerald-700">{minScore > 0 ? minScore.toFixed(1) : "off"}</span>
            {minScore > 0 && (
              <button type="button" onClick={() => setMinScore(0)} className="text-xs text-slate-400 underline hover:text-slate-600">clear</button>
            )}
          </div>
          {loading ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : contentSnippets.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
              No snippets yet. Approve source content and run transcript extraction.
            </div>
          ) : (
            <div className="space-y-2">
              {contentSnippets
                .filter((s) => minScore <= 0 || (s.overall_score || 0) >= minScore)
                .map((s) => (
                  <SnippetRow key={s._id} snippet={s} onRefresh={load} />
                ))}
              {contentSnippets.filter((s) => minScore <= 0 || (s.overall_score || 0) >= minScore).length === 0 && (
                <p className="text-xs text-slate-500">No snippets match the current score filter.</p>
              )}
            </div>
          )}
        </section>
      )}

      {/* v2: ASSETS section */}
      {activeSection === "assets" && (
        <section className="space-y-4">
          <div>
            <h2 className="text-base font-semibold text-slate-950">Creative Assets</h2>
            <p className="mt-1 text-xs text-slate-500">
              Generated images, reels, and captions. All require operator review. No asset is published automatically.
            </p>
          </div>
          {loading ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : creativeAssets.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
              No creative assets yet.
            </div>
          ) : (
            <div className="space-y-2">
              {creativeAssets.map((a) => (
                <CreativeAssetRow key={a._id} asset={a} onRefresh={load} />
              ))}
            </div>
          )}
        </section>
      )}

      {/* v2: APPROVAL QUEUE section */}
      {activeSection === "approval-queue" && (
        <section className="space-y-6">
          <div>
            <h2 className="text-base font-semibold text-slate-950">Approval Queue</h2>
            <p className="mt-1 text-xs text-slate-500">
              All snippets and assets awaiting operator review. No item is published without explicit approval.
            </p>
          </div>

          {/* Snippets needing review */}
          {(() => {
            const pending = contentSnippets.filter((s) => s.status === "needs_review");
            return (
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-slate-700">Snippets ({pending.length})</h3>
                {pending.length === 0 ? (
                  <p className="text-xs text-slate-500">No snippets awaiting review.</p>
                ) : (
                  <div className="space-y-2">
                    {pending.map((s) => (
                      <SnippetRow key={s._id} snippet={s} onRefresh={load} />
                    ))}
                  </div>
                )}
              </div>
            );
          })()}

          {/* Assets needing review */}
          {(() => {
            const pending = creativeAssets.filter((a) => a.status === "needs_review");
            return (
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-slate-700">Creative Assets ({pending.length})</h3>
                {pending.length === 0 ? (
                  <p className="text-xs text-slate-500">No assets awaiting review.</p>
                ) : (
                  <div className="space-y-2">
                    {pending.map((a) => (
                      <CreativeAssetRow key={a._id} asset={a} onRefresh={load} />
                    ))}
                  </div>
                )}
              </div>
            );
          })()}
        </section>
      )}

      {/* v3: INGEST PIPELINE section */}
      {activeSection === "ingest" && (
        <IngestPipelineSection
          sourceContent={sourceContent}
          audioExtractionRuns={audioExtractionRuns}
          transcriptRuns={transcriptRuns}
          transcriptSegments={transcriptSegments}
          contentSnippets={contentSnippets}
          mediaIntakeRecords={mediaIntakeRecords}
          wsParam={wsParam}
          onRefresh={load}
          showNotice={showNotice}
          demoMode={demoMode}
        />
      )}

      {/* v4.5: PROMPT LIBRARY section */}
      {activeSection === "prompts" && (
        <PromptLibrarySection
          promptGenerations={promptGenerations}
          contentSnippets={contentSnippets}
          clientProfiles={clientProfiles}
          wsParam={wsParam}
          onRefresh={load}
          showNotice={showNotice}
          demoMode={demoMode}
        />
      )}

      {/* v5: RENDERED ASSETS section */}
      {activeSection === "renders" && (
        <AssetRenderSection
          assetRenders={assetRenders}
          promptGenerations={promptGenerations}
          contentSnippets={contentSnippets}
          wsParam={wsParam}
          onRefresh={load}
          showNotice={showNotice}
          demoMode={demoMode}
        />
      )}

      {/* v7.5: PERFORMANCE LOOP section */}
      {activeSection === "performance-loop" && (
        <PerformanceLoopSection
          assetRenders={assetRenders}
          manualPublishLogs={manualPublishLogs}
          assetPerformanceRecords={assetPerformanceRecords}
          creativePerformanceSummaries={creativePerformanceSummaries}
          wsParam={wsParam}
          onRefresh={load}
          showNotice={showNotice}
        />
      )}

      {/* v9.5: CLIENT INTELLIGENCE section */}
      {activeSection === "client-intelligence" && (
        <ClientIntelligenceSection
          clientIntelligenceRecords={clientIntelligenceRecords}
          leadCorrelations={leadCorrelations}
          clientProfiles={clientProfiles}
          assetPerformanceRecords={assetPerformanceRecords}
          wsParam={wsParam}
          onRefresh={load}
          showNotice={showNotice}
        />
      )}

      {/* v8.5: CAMPAIGN EXPORTS section */}
      {activeSection === "campaign-exports" && (
        <CampaignExportsSection
          campaignExports={campaignExports}
          campaignPacks={campaignPacks}
          campaignReports={campaignReports}
          wsParam={wsParam}
          onRefresh={load}
          showNotice={showNotice}
        />
      )}

      {/* v10: POC DEMO section */}
      {activeSection === "poc-demo" && (
        <PocDemoTab
          demoMode={demoMode}
          onNavigate={(section) => setActiveSection(section)}
        />
      )}

      {/* v8: CAMPAIGN PACKS section */}
      {activeSection === "campaign-packs" && (
        <CampaignPacksSection
          campaignPacks={campaignPacks}
          campaignReports={campaignReports}
          sourceContent={sourceContent}
          contentSnippets={contentSnippets}
          promptGenerations={promptGenerations}
          assetRenders={assetRenders}
          manualPublishLogs={manualPublishLogs}
          assetPerformanceRecords={assetPerformanceRecords}
          clientProfiles={clientProfiles}
          wsParam={wsParam}
          onRefresh={load}
          showNotice={showNotice}
        />
      )}

      {/* v10.4: MEDIA INGESTION section */}
      {activeSection === "media-ingestion" && (
        <MediaIngestionSection
          mediaFolderScans={mediaFolderScans}
          approvedUrlDownloads={approvedUrlDownloads}
          mediaIntakeRecords={mediaIntakeRecords}
          clientProfiles={clientProfiles}
          wsParam={wsParam}
          onRefresh={load}
          showNotice={showNotice}
        />
      )}
    </div>
  );
}
