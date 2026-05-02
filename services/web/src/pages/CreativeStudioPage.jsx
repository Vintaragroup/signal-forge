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
// v2: SnippetRow
// ---------------------------------------------------------------------------

function SnippetRow({ snippet, onRefresh }) {
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
            <span className="truncate text-sm font-medium text-slate-900">{snippet.theme ? snippet.theme.replaceAll("_", " ") : "Snippet"}</span>
            <StatusBadge value={snippet.status} />
            {snippet.score != null && (
              <span className="rounded bg-blue-50 px-2 py-0.5 text-xs text-blue-700">score: {snippet.score}</span>
            )}
          </div>
          <div className="mt-1 line-clamp-2 text-xs text-slate-500">{snippet.transcript_text}</div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-slate-100 px-4 pb-4 pt-3 space-y-3">
          <div className="rounded-lg bg-slate-50 p-3 text-sm text-slate-800 italic">"{snippet.transcript_text}"</div>

          {snippet.hook_angle && (
            <div className="text-xs text-slate-600"><span className="font-medium">Hook angle:</span> {snippet.hook_angle}</div>
          )}
          {snippet.score_reason && (
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

          {snippet.status === "needs_review" && !reviewing && (
            <button
              type="button"
              onClick={() => setReviewing(true)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-blue-700"
            >
              <PenLine className="h-3.5 w-3.5" /> Review Snippet
            </button>
          )}
          {reviewing && (
            <SnippetReviewPanel
              snippet={snippet}
              onReviewed={() => { setReviewing(false); onRefresh(); }}
              onClose={() => setReviewing(false)}
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

  async function load() {
    setLoading(true);
    try {
      const [briefData, draftData, profilesData, channelsData, contentData, snippetsData, assetsData] = await Promise.all([
        api.contentBriefs({ ...wsParam() }),
        api.contentDrafts({ ...wsParam() }),
        api.clientProfiles({ ...wsParam() }),
        api.sourceChannels({ ...wsParam() }),
        api.sourceContent({ ...wsParam() }),
        api.contentSnippets({ ...wsParam() }),
        api.creativeAssets({ ...wsParam() }),
      ]);
      setBriefs(briefData.items || []);
      setDrafts(draftData.items || []);
      setClientProfiles(profilesData.items || []);
      setSourceChannels(channelsData.items || []);
      setSourceContent(contentData.items || []);
      setContentSnippets(snippetsData.items || []);
      setCreativeAssets(assetsData.items || []);
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
          {loading ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : contentSnippets.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
              No snippets yet. Approve source content and run transcript extraction.
            </div>
          ) : (
            <div className="space-y-2">
              {contentSnippets.map((s) => (
                <SnippetRow key={s._id} snippet={s} onRefresh={load} />
              ))}
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
    </div>
  );
}
