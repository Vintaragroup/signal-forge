import { useEffect, useState, useCallback } from "react";
import {
  AlertTriangle,
  BookOpen,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Clock,
  Diff,
  Heart,
  History,
  Lightbulb,
  Plus,
  RefreshCw,
  RotateCcw,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  XCircle,
} from "lucide-react";
import { api } from "../api.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const CONFIDENCE_COLORS = {
  high: "bg-green-100 text-green-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-slate-100 text-slate-500",
};

function confidenceLabel(score) {
  if (score >= 0.7) return "high";
  if (score >= 0.4) return "medium";
  return "low";
}

const STATUS_COLORS = {
  pending: "bg-amber-100 text-amber-700",
  approved: "bg-green-100 text-green-700",
  rejected: "bg-red-100 text-red-700",
};

function TagList({ items, emptyText = "None recorded" }) {
  if (!items || items.length === 0) {
    return <span className="text-xs text-slate-400 italic">{emptyText}</span>;
  }
  return (
    <div className="flex flex-wrap gap-1.5 mt-1">
      {items.map((item, i) => (
        <span key={i} className="inline-flex rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-700">
          {typeof item === "object" ? JSON.stringify(item) : item}
        </span>
      ))}
    </div>
  );
}

function SectionHeader({ icon: Icon, title, children }) {
  return (
    <div className="flex items-center justify-between gap-2 mb-3">
      <div className="flex items-center gap-2">
        {Icon && <Icon className="h-4 w-4 text-slate-400" />}
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase 6O: Memory Health Badge
// ---------------------------------------------------------------------------

const HEALTH_COLORS = {
  healthy:      "bg-green-100 text-green-700 border-green-200",
  needs_review: "bg-amber-100 text-amber-700 border-amber-200",
  conflicted:   "bg-red-100 text-red-700 border-red-200",
  stale:        "bg-slate-100 text-slate-500 border-slate-200",
  overgrown:    "bg-orange-100 text-orange-700 border-orange-200",
  unknown:      "bg-slate-100 text-slate-400 border-slate-200",
};

function MemoryHealthBadge({ memoryId }) {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!memoryId) return;
    setLoading(true);
    api.clientMemoryHealth(memoryId)
      .then(setHealth)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [memoryId]);

  if (loading) return <span className="text-xs text-slate-400">Checking health…</span>;
  if (!health) return null;

  const cls = HEALTH_COLORS[health.status] || HEALTH_COLORS.unknown;
  const score = Math.round((health.memory_health_score || 0) * 100);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setExpanded((x) => !x)}
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${cls}`}
      >
        <Heart className="h-3 w-3" />
        {health.status} · {score}%
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
      </button>

      {expanded && (
        <div className="absolute right-0 top-7 z-20 w-64 rounded-xl border border-slate-200 bg-white shadow-lg p-3 text-xs text-slate-700 space-y-1.5">
          <div className="font-semibold text-slate-800 mb-2">Memory Health</div>
          <div className="flex justify-between"><span>Score</span><span className="font-medium">{score}%</span></div>
          <div className="flex justify-between"><span>Conflicts</span><span className={health.conflict_count > 0 ? "text-red-600 font-medium" : ""}>{health.conflict_count}</span></div>
          <div className="flex justify-between"><span>Duplicates</span><span>{health.duplicate_pattern_count}</span></div>
          <div className="flex justify-between"><span>Patterns</span><span>{health.total_patterns}</span></div>
          <div className="flex justify-between"><span>Pending proposals</span><span>{health.pending_proposal_count}</span></div>
          {health.stale && <div className="text-amber-600">⚠ Not updated in {health.stale_days}+ days</div>}
          {health.overgrown && <div className="text-orange-600">⚠ Too many patterns ({health.total_patterns})</div>}
          {health.last_reviewed_at && (
            <div className="text-slate-400 text-xs border-t pt-1.5">
              Last approved: {health.last_reviewed_at.slice(0, 10)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase 6O: Version History Panel
// ---------------------------------------------------------------------------

function VersionHistoryPanel({ memoryId, onRollbackComplete }) {
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [rollbackTarget, setRollbackTarget] = useState(null);
  const [rolling, setRolling] = useState(false);

  function load() {
    setLoading(true);
    api.clientMemoryHistory(memoryId, 30)
      .then((d) => setHistory(d.items || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (open && memoryId) load();
  }, [open, memoryId]);

  async function confirmRollback() {
    if (!rollbackTarget) return;
    setRolling(true);
    try {
      await api.rollbackClientMemory(memoryId, { target_version: rollbackTarget });
      setRollbackTarget(null);
      load();
      onRollbackComplete();
    } catch (err) {
      alert(`Rollback failed: ${err.message}`);
    } finally {
      setRolling(false);
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((x) => !x)}
        className="flex w-full items-center justify-between gap-2 px-5 py-4"
      >
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-slate-400" />
          <span className="text-sm font-semibold text-slate-800">Version History</span>
          {history.length > 0 && (
            <span className="text-xs text-slate-400">({history.length} snapshots)</span>
          )}
        </div>
        {open ? <ChevronDown className="h-4 w-4 text-slate-400" /> : <ChevronRight className="h-4 w-4 text-slate-400" />}
      </button>

      {open && (
        <div className="border-t border-slate-100 p-5">
          {loading && <div className="text-sm text-slate-400 py-4 text-center">Loading history…</div>}
          {!loading && history.length === 0 && (
            <div className="text-sm text-slate-400 py-4 text-center">
              No version history yet. History is recorded each time a proposal is approved.
            </div>
          )}
          {!loading && history.length > 0 && (
            <div className="space-y-2">
              {history.map((entry) => (
                <div key={entry._id} className="flex items-start justify-between gap-3 rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="inline-flex rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-700">
                        v{entry.version}
                      </span>
                      <span className="text-xs text-slate-500">
                        {entry.created_at ? String(entry.created_at).slice(0, 16).replace("T", " ") : ""}
                      </span>
                      <span className="text-xs text-slate-400">by {entry.created_by}</span>
                    </div>
                    {entry.change_summary?.length > 0 && (
                      <div className="text-xs text-slate-600 truncate">
                        {entry.change_summary.join(", ")}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => setRollbackTarget(entry.version)}
                    className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-100 whitespace-nowrap"
                  >
                    <RotateCcw className="h-3 w-3" />
                    Restore
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Rollback confirm modal */}
      {rollbackTarget !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-sm rounded-xl bg-white shadow-xl p-6">
            <div className="flex items-center gap-2 mb-3">
              <RotateCcw className="h-4 w-4 text-amber-500" />
              <h3 className="text-base font-semibold text-slate-800">Confirm Rollback</h3>
            </div>
            <p className="text-sm text-slate-600 mb-4">
              Restore memory to <strong>version {rollbackTarget}</strong>? The current state will be
              snapshotted first. A new version will be created with the restored content.
            </p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setRollbackTarget(null)}
                className="rounded-md border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmRollback}
                disabled={rolling}
                className="inline-flex items-center gap-2 rounded-md bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
              >
                {rolling ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
                {rolling ? "Rolling back…" : "Restore"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase 6O: Diff Preview (inline in ProposalCard)
// ---------------------------------------------------------------------------

function DiffPreview({ proposalId }) {
  const [diff, setDiff] = useState(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  async function load() {
    if (diff) { setOpen((x) => !x); return; }
    setLoading(true);
    try {
      const d = await api.proposalDiff(proposalId);
      setDiff(d.diff);
      setOpen(true);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <button
        type="button"
        onClick={load}
        disabled={loading}
        className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-violet-600 disabled:opacity-50"
      >
        {loading ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Diff className="h-3 w-3" />}
        {open ? "Hide diff" : "Preview diff"}
      </button>

      {open && diff && (
        <div className="mt-2 rounded-md border border-slate-100 bg-slate-50 p-3 text-xs space-y-1.5">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-medium text-slate-600">{diff.field}</span>
            <span className="text-slate-400">({diff.change_type})</span>
            {diff.has_changes ? (
              <span className="text-green-600">has changes</span>
            ) : (
              <span className="text-slate-400">no changes</span>
            )}
          </div>
          {diff.removals?.length > 0 && (
            <div>
              <div className="text-xs font-medium text-red-500 mb-0.5">Removed</div>
              {diff.removals.map((r, i) => (
                <div key={i} className="text-red-700 font-mono bg-red-50 px-2 py-0.5 rounded">
                  − {typeof r === "object" ? JSON.stringify(r) : String(r)}
                </div>
              ))}
            </div>
          )}
          {diff.additions?.length > 0 && (
            <div>
              <div className="text-xs font-medium text-green-600 mb-0.5">Added</div>
              {diff.additions.map((a, i) => (
                <div key={i} className="text-green-700 font-mono bg-green-50 px-2 py-0.5 rounded">
                  + {typeof a === "object" ? JSON.stringify(a) : String(a)}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Template Recommendation Panel
// ---------------------------------------------------------------------------

function TemplateRecommendationPanel({ workspaceSlug, onTemplateSelected }) {
  const [form, setForm] = useState({
    client_name: "",
    brand_name: "",
    industry: "",
    business_type: "",
    description: "",
    primary_offer: "",
    target_audience: "",
    goals: "",
    notes: "",
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const data = await api.recommendTemplate(form);
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function field(label, key, placeholder = "") {
    return (
      <div>
        <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
        <input
          type="text"
          value={form[key]}
          onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
          placeholder={placeholder}
          className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder-slate-400 focus:border-violet-400 focus:outline-none"
        />
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center gap-2 border-b border-slate-100 px-5 py-4">
        <Sparkles className="h-4 w-4 text-violet-500" />
        <h2 className="text-sm font-semibold text-slate-800">Template Recommendation</h2>
      </div>

      <form onSubmit={handleSubmit} className="p-5 grid grid-cols-2 gap-4">
        {field("Client Name", "client_name", "Acme Media")}
        {field("Brand / Trade Name", "brand_name", "Acme")}
        {field("Industry", "industry", "podcasting, SaaS, insurance...")}
        {field("Business Type", "business_type", "B2B, local service, creator...")}
        <div className="col-span-2">
          {field("Description", "description", "What does this client do?")}
        </div>
        {field("Primary Offer", "primary_offer", "What do they sell or offer?")}
        {field("Target Audience", "target_audience", "Who are their ideal customers?")}
        <div className="col-span-2">
          {field("Goals", "goals", "What are they trying to achieve with SignalForge?")}
        </div>

        {error && (
          <div className="col-span-2 rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="col-span-2 flex justify-end">
          <button
            type="submit"
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-md bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
          >
            {loading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
            {loading ? "Analyzing..." : "Get Recommendation"}
          </button>
        </div>
      </form>

      {result && (
        <div className="border-t border-slate-100 p-5 space-y-4">
          {/* Top recommendation */}
          <div className="rounded-lg border border-violet-200 bg-violet-50 p-4">
            <div className="flex items-center justify-between gap-3 mb-2">
              <div>
                <div className="text-xs text-violet-500 font-medium uppercase tracking-wide">Recommended Template</div>
                <div className="text-base font-semibold text-slate-900 mt-0.5">
                  {result.recommended_template.name}
                </div>
                <div className="text-xs text-slate-500">{result.recommended_template.description}</div>
              </div>
              <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${CONFIDENCE_COLORS[confidenceLabel(result.confidence_score)]}`}>
                {Math.round(result.confidence_score * 100)}% confidence
              </span>
            </div>
            <p className="text-xs text-slate-700">{result.reason}</p>

            <button
              type="button"
              onClick={() => onTemplateSelected(result.recommended_template.slug, form)}
              className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-700"
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              Apply this template
            </button>
          </div>

          {/* Alternates */}
          {result.alternate_templates?.length > 0 && (
            <div>
              <div className="text-xs font-medium text-slate-600 mb-2">Alternate Templates Considered</div>
              <div className="space-y-2">
                {result.alternate_templates.map((alt) => (
                  <div key={alt.slug} className="flex items-center justify-between rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                    <div>
                      <span className="text-xs font-medium text-slate-700">{alt.name}</span>
                      <span className="text-xs text-slate-400 ml-2">{alt.reason}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-500">{Math.round(alt.score * 100)}%</span>
                      <button
                        type="button"
                        onClick={() => onTemplateSelected(alt.slug, form)}
                        className="text-xs text-violet-600 hover:underline"
                      >
                        Apply
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Assumptions & missing info */}
          {(result.assumptions?.length > 0 || result.missing_information?.length > 0) && (
            <div className="grid grid-cols-2 gap-3">
              {result.assumptions?.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-slate-500 mb-1">Assumptions</div>
                  <ul className="space-y-0.5">
                    {result.assumptions.map((a, i) => (
                      <li key={i} className="text-xs text-slate-600 flex gap-1">
                        <CircleDot className="h-3 w-3 mt-0.5 flex-shrink-0 text-slate-400" />
                        {a}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {result.missing_information?.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-amber-600 mb-1">Missing Information</div>
                  <ul className="space-y-0.5">
                    {result.missing_information.map((m, i) => (
                      <li key={i} className="text-xs text-amber-700 flex gap-1">
                        <XCircle className="h-3 w-3 mt-0.5 flex-shrink-0" />
                        {m}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Client Memory Detail Panel
// ---------------------------------------------------------------------------

function MemoryDetailPanel({ memory, onRefresh }) {
  const [briefOpen, setBriefOpen] = useState(false);
  const [brief, setBrief] = useState(null);
  const [briefLoading, setBriefLoading] = useState(false);
  const [editField, setEditField] = useState(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);

  async function loadBrief() {
    setBriefLoading(true);
    try {
      const data = await api.clientMemoryBrief(memory._id);
      setBrief(data.brief_markdown);
      setBriefOpen(true);
    } catch (err) {
      alert(`Failed to load brief: ${err.message}`);
    } finally {
      setBriefLoading(false);
    }
  }

  async function saveListField(field, rawValue) {
    const items = rawValue.split("\n").map((s) => s.trim()).filter(Boolean);
    setSaving(true);
    try {
      await api.updateClientMemory(memory._id, { [field]: items });
      onRefresh();
      setEditField(null);
    } catch (err) {
      alert(`Failed to save: ${err.message}`);
    } finally {
      setSaving(false);
    }
  }

  function editableList(label, field, items) {
    const isEditing = editField === field;
    return (
      <div className="mb-4">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-medium text-slate-600">{label}</span>
          {!isEditing ? (
            <button
              type="button"
              onClick={() => { setEditField(field); setEditValue((items || []).join("\n")); }}
              className="text-xs text-violet-500 hover:underline"
            >
              Edit
            </button>
          ) : (
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => saveListField(field, editValue)}
                disabled={saving}
                className="text-xs text-green-600 hover:underline disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save"}
              </button>
              <button type="button" onClick={() => setEditField(null)} className="text-xs text-slate-400 hover:underline">
                Cancel
              </button>
            </div>
          )}
        </div>
        {isEditing ? (
          <textarea
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            rows={4}
            className="w-full rounded-md border border-violet-300 px-3 py-2 text-xs text-slate-800 font-mono focus:outline-none focus:border-violet-500"
            placeholder="One item per line"
          />
        ) : (
          <TagList items={items} />
        )}
      </div>
    );
  }

  const pos = memory.positioning || {};
  const icp = memory.icp || {};
  const vt = memory.voice_tone || {};

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-violet-500" />
          <div>
            <div className="text-sm font-semibold text-slate-800">Client Operating Memory</div>
            <div className="text-xs text-slate-400">
              Template: {memory.foundation_template_name || memory.foundation_template_slug} · v{memory.version || 1}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <MemoryHealthBadge memoryId={memory._id} />
          <button
            type="button"
            onClick={briefOpen ? () => setBriefOpen(false) : loadBrief}
            disabled={briefLoading}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            {briefLoading ? <RefreshCw className="h-3 w-3 animate-spin" /> : <BookOpen className="h-3 w-3" />}
            {briefOpen ? "Hide Brief" : "View Brief"}
          </button>
        </div>
      </div>

      {/* Brief markdown */}
      {briefOpen && brief && (
        <div className="border-b border-slate-100 bg-slate-50 px-5 py-4">
          <pre className="text-xs text-slate-700 whitespace-pre-wrap font-mono leading-relaxed">{brief}</pre>
        </div>
      )}

      <div className="p-5 space-y-6">
        {/* Positioning */}
        <div>
          <SectionHeader title="Positioning" />
          <div className="grid grid-cols-2 gap-3 text-xs text-slate-700">
            <div><span className="font-medium">What they do:</span> {pos.what_they_do || <span className="italic text-slate-400">not set</span>}</div>
            <div><span className="font-medium">Who they help:</span> {pos.who_they_help || <span className="italic text-slate-400">not set</span>}</div>
            <div className="col-span-2"><span className="font-medium">Why buyers choose them:</span> {pos.why_buyers_choose || <span className="italic text-slate-400">not set</span>}</div>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-3">
            <div>
              <div className="text-xs font-medium text-slate-500 mb-1">Proof Points</div>
              <TagList items={pos.proof_points} />
            </div>
            <div>
              <div className="text-xs font-medium text-slate-500 mb-1">Differentiators</div>
              <TagList items={pos.differentiators} />
            </div>
          </div>
        </div>

        {/* ICP */}
        <div>
          <SectionHeader title="Ideal Customer Profile" />
          <div className="grid grid-cols-2 gap-3 text-xs text-slate-700 mb-2">
            <div><span className="font-medium">Company type:</span> {icp.company_type || <span className="italic text-slate-400">not set</span>}</div>
            <div><span className="font-medium">Buyer:</span> {icp.buyer || <span className="italic text-slate-400">not set</span>}</div>
            <div><span className="font-medium">Size:</span> {icp.size || <span className="italic text-slate-400">not set</span>}</div>
            <div><span className="font-medium">Geography:</span> {icp.geography || <span className="italic text-slate-400">not set</span>}</div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-xs font-medium text-slate-500 mb-1">Budget Indicators</div>
              <TagList items={icp.budget_indicators} />
            </div>
            <div>
              <div className="text-xs font-medium text-slate-500 mb-1">Timing Signals</div>
              <TagList items={icp.timing_signals} />
            </div>
          </div>
        </div>

        {/* Voice & Tone */}
        <div>
          <SectionHeader title="Voice & Tone" />
          <div className="flex gap-4 text-xs text-slate-700 mb-2">
            <div><span className="font-medium">Tone:</span> {vt.tone || <span className="italic text-slate-400">not set</span>}</div>
            <div><span className="font-medium">Style:</span> {vt.style || <span className="italic text-slate-400">not set</span>}</div>
          </div>
        </div>

        {/* Claims & Patterns — editable */}
        <div className="grid grid-cols-2 gap-x-6">
          {editableList("Approved Claims", "approved_claims", memory.approved_claims)}
          {editableList("Blocked Claims", "blocked_claims", memory.blocked_claims)}
          {editableList("Winning Patterns", "winning_patterns", memory.winning_patterns)}
          {editableList("Losing Patterns", "losing_patterns", memory.losing_patterns)}
          {editableList("Performance Notes", "performance_notes", memory.performance_notes)}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Memory Update Proposals Panel
// ---------------------------------------------------------------------------

function ProposalCard({ proposal, onDecide }) {
  const [deciding, setDeciding] = useState(false);
  const change = proposal.proposed_change || {};
  const conflicts = proposal.conflicts || [];
  const highConflicts = conflicts.filter((c) => c.severity === "high");

  // Confidence tier
  const conf = proposal.confidence || 0;
  const confTier = conf >= 0.90 ? "HIGH" : conf >= 0.50 ? "MED" : "LOW";
  const confTierColors = { HIGH: "bg-green-100 text-green-700", MED: "bg-amber-100 text-amber-700", LOW: "bg-slate-100 text-slate-500" };

  // Governance suggestion badge
  const govColors = {
    auto_approve: "bg-green-50 text-green-700 border-green-200",
    auto_reject:  "bg-red-50 text-red-600 border-red-200",
    review:       "bg-amber-50 text-amber-700 border-amber-200",
  };

  async function decide(status, overrideConflicts = false) {
    setDeciding(true);
    try {
      await onDecide(proposal._id, status, overrideConflicts);
    } finally {
      setDeciding(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[proposal.status] || "bg-slate-100 text-slate-600"}`}>
              {proposal.status}
            </span>
            <span className="text-xs text-slate-500">{proposal.source}</span>
            {/* Confidence tier */}
            <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${confTierColors[confTier]}`}>
              {confTier} · {Math.round(conf * 100)}%
            </span>
            {/* Governance suggestion */}
            {proposal.governance_suggestion && proposal.governance_suggestion !== "review" && (
              <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${govColors[proposal.governance_suggestion] || ""}`}>
                {proposal.governance_suggestion === "auto_approve" ? "✓ suggested: approve" : "✗ suggested: reject"}
              </span>
            )}
            {/* Duplicate warning */}
            {proposal.is_duplicate && (
              <span className="inline-flex items-center gap-0.5 rounded-full bg-orange-100 text-orange-700 border border-orange-200 px-2 py-0.5 text-xs font-medium">
                <AlertTriangle className="h-3 w-3" /> duplicate
              </span>
            )}
          </div>
          <div className="mt-1 text-sm font-medium text-slate-800">
            {change.field ? (
              <span>
                Update <code className="bg-slate-100 px-1 rounded text-xs">{change.field}</code>
                {" "}({change.change_type || "update"})
              </span>
            ) : "Unspecified field change"}
          </div>
        </div>
      </div>

      {/* Conflict warnings */}
      {conflicts.length > 0 && (
        <div className="mb-2 rounded-md border border-red-100 bg-red-50 px-3 py-2">
          <div className="flex items-center gap-1.5 mb-1">
            <AlertTriangle className="h-3.5 w-3.5 text-red-500" />
            <span className="text-xs font-medium text-red-700">{conflicts.length} conflict{conflicts.length > 1 ? "s" : ""} detected</span>
          </div>
          {conflicts.slice(0, 3).map((c, i) => (
            <div key={i} className="text-xs text-red-600">
              <span className={`inline-block rounded px-1 mr-1 ${c.severity === "high" ? "bg-red-200" : "bg-orange-100 text-orange-700"}`}>{c.severity}</span>
              {c.description}
            </div>
          ))}
        </div>
      )}

      {change.new_value !== undefined && (
        <div className="rounded-md bg-slate-50 border border-slate-100 px-3 py-2 mb-2">
          <div className="text-xs text-slate-500 mb-0.5">Proposed value</div>
          <div className="text-xs text-slate-800 font-mono break-all">
            {typeof change.new_value === "object" ? JSON.stringify(change.new_value) : String(change.new_value)}
          </div>
        </div>
      )}

      {proposal.evidence && (
        <p className="text-xs text-slate-500 mb-2">{proposal.evidence}</p>
      )}

      {/* Diff preview */}
      <div className="mb-3">
        <DiffPreview proposalId={proposal._id} />
      </div>

      {proposal.status === "pending" && (
        <div className="flex gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => decide("approved")}
            disabled={deciding}
            className="inline-flex items-center gap-1.5 rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            <ThumbsUp className="h-3 w-3" />
            Approve
          </button>
          {highConflicts.length > 0 && (
            <button
              type="button"
              onClick={() => decide("approved", true)}
              disabled={deciding}
              className="inline-flex items-center gap-1.5 rounded-md border border-red-300 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 disabled:opacity-50"
            >
              <AlertTriangle className="h-3 w-3" />
              Override &amp; Approve
            </button>
          )}
          <button
            type="button"
            onClick={() => decide("rejected")}
            disabled={deciding}
            className="inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 disabled:opacity-50"
          >
            <ThumbsDown className="h-3 w-3" />
            Reject
          </button>
        </div>
      )}

      {proposal.reviewed_by && (
        <div className="mt-2 text-xs text-slate-400">
          {proposal.status} by {proposal.reviewed_by}
        </div>
      )}
    </div>
  );
}

function MemoryUpdateProposalsPanel({ workspaceSlug, memoryId, onMemoryChanged }) {
  const [proposals, setProposals] = useState([]);
  const [filter, setFilter] = useState("pending");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.memoryUpdateProposals({ workspaceSlug, clientMemoryId: memoryId, status: filter, limit: 50 });
      setProposals(data.items || []);
    } catch {
      // non-fatal
    } finally {
      setLoading(false);
    }
  }, [workspaceSlug, memoryId, filter]);

  useEffect(() => { load(); }, [load]);

  async function handleDecide(proposalId, status, overrideConflicts = false) {
    try {
      await api.decideMemoryUpdateProposal(proposalId, { status, override_conflicts: overrideConflicts });
      await load();
      if (status === "approved") onMemoryChanged();
    } catch (err) {
      alert(`Failed to decide proposal: ${err.message}`);
    }
  }

  const pending = proposals.filter((p) => p.status === "pending").length;

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div className="flex items-center gap-2">
          <Lightbulb className="h-4 w-4 text-amber-500" />
          <h2 className="text-sm font-semibold text-slate-800">
            Memory Update Proposals
            {pending > 0 && (
              <span className="ml-2 inline-flex rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                {pending} pending
              </span>
            )}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="rounded-md border border-slate-200 px-2 py-1.5 text-xs text-slate-700 focus:outline-none"
          >
            <option value="">All</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
          <button type="button" onClick={load} className="rounded-md border border-slate-200 p-1.5 text-slate-500 hover:bg-slate-50">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      <div className="p-5">
        {loading && proposals.length === 0 ? (
          <div className="text-sm text-slate-400 text-center py-6">Loading proposals…</div>
        ) : proposals.length === 0 ? (
          <div className="text-sm text-slate-400 text-center py-6">
            {filter === "pending" ? "No pending proposals. Proposals are auto-generated from workflow outcomes." : "No proposals found."}
          </div>
        ) : (
          <div className="space-y-3">
            {proposals.map((p) => (
              <ProposalCard key={p._id} proposal={p} onDecide={handleDecide} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Foundation Template Browser
// ---------------------------------------------------------------------------

function FoundationTemplatesBrowser({ onSelectTemplate }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.foundationTemplates().then((d) => setTemplates(d.items || [])).catch(() => {}).finally(() => setLoading(false));
  }, []);

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setExpanded((x) => !x)}
        className="flex w-full items-center justify-between gap-2 px-5 py-4"
      >
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-slate-400" />
          <span className="text-sm font-semibold text-slate-800">Foundation Template Catalog</span>
          <span className="text-xs text-slate-400">({templates.length} templates)</span>
        </div>
        {expanded ? <ChevronDown className="h-4 w-4 text-slate-400" /> : <ChevronRight className="h-4 w-4 text-slate-400" />}
      </button>

      {expanded && (
        <div className="border-t border-slate-100 p-5 grid grid-cols-2 gap-3">
          {loading && <div className="col-span-2 text-sm text-slate-400">Loading…</div>}
          {templates.map((t) => (
            <div key={t.slug} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-start justify-between gap-2 mb-1">
                <div className="text-sm font-semibold text-slate-800">{t.name}</div>
                <span className="inline-flex rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-600">{t.category}</span>
              </div>
              <p className="text-xs text-slate-500 mb-3">{t.description}</p>
              <div className="flex flex-wrap gap-1 mb-3">
                {(t.target_client_types || []).map((c) => (
                  <span key={c} className="inline-flex rounded-full bg-white border border-slate-200 px-2 py-0.5 text-xs text-slate-600">{c}</span>
                ))}
              </div>
              <button
                type="button"
                onClick={() => onSelectTemplate(t.slug)}
                className="text-xs text-violet-600 hover:underline"
              >
                Apply template →
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Init Memory Modal
// ---------------------------------------------------------------------------

function InitMemoryModal({ workspaceSlug, templateSlug, prefillForm, onClose, onCreated }) {
  const [form, setForm] = useState({
    foundation_template_slug: templateSlug || "",
    client_profile_id: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Sync if template changes from outside
  useEffect(() => {
    if (templateSlug) setForm((f) => ({ ...f, foundation_template_slug: templateSlug }));
  }, [templateSlug]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.foundation_template_slug) {
      setError("Please select a foundation template.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await api.createClientMemory({
        workspace_slug: workspaceSlug,
        foundation_template_slug: form.foundation_template_slug,
        client_profile_id: form.client_profile_id,
      });
      onCreated(data.item);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const TEMPLATE_OPTIONS = [
    "media_growth", "artist_growth", "insurance_growth",
    "sales_enablement", "founder_thought_leadership",
    "investor_outreach", "local_services", "recruiting",
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="w-full max-w-md rounded-xl bg-white shadow-xl p-6">
        <h3 className="text-base font-semibold text-slate-800 mb-4">Initialize Client Memory</h3>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Foundation Template</label>
            <select
              value={form.foundation_template_slug}
              onChange={(e) => setForm((f) => ({ ...f, foundation_template_slug: e.target.value }))}
              className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-800 focus:border-violet-400 focus:outline-none"
            >
              <option value="">Select a template…</option>
              {TEMPLATE_OPTIONS.map((s) => (
                <option key={s} value={s}>{s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Client Profile ID <span className="text-slate-400">(optional)</span></label>
            <input
              type="text"
              value={form.client_profile_id}
              onChange={(e) => setForm((f) => ({ ...f, client_profile_id: e.target.value }))}
              placeholder="Leave blank to skip profile link"
              className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm placeholder-slate-400 focus:border-violet-400 focus:outline-none"
            />
          </div>

          {error && (
            <div className="rounded-md bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">{error}</div>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="rounded-md border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-md bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
            >
              {loading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              {loading ? "Creating…" : "Initialize Memory"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function ClientMemoryPage({ activeWorkspace, refreshTrigger }) {
  const workspaceSlug = activeWorkspace;
  const [memories, setMemories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showInitModal, setShowInitModal] = useState(false);
  const [selectedTemplateSlug, setSelectedTemplateSlug] = useState(null);
  const [prefillForm, setPrefillForm] = useState(null);
  const [activeMemory, setActiveMemory] = useState(null);

  const effectiveWorkspace = workspaceSlug !== "all" ? workspaceSlug : "";

  const loadMemories = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.clientMemories({ workspaceSlug: effectiveWorkspace, limit: 20 });
      const items = data.items || [];
      setMemories(items);
      if (items.length > 0 && !activeMemory) {
        setActiveMemory(items[0]);
      } else if (items.length > 0 && activeMemory) {
        // Refresh active memory from updated list
        const refreshed = items.find((m) => m._id === activeMemory._id);
        if (refreshed) setActiveMemory(refreshed);
      }
    } catch {
      // non-fatal
    } finally {
      setLoading(false);
    }
  }, [effectiveWorkspace, activeMemory?._id]);

  useEffect(() => { loadMemories(); }, [effectiveWorkspace, refreshTrigger]);

  function handleTemplateSelectedFromRecommender(slug, form) {
    setSelectedTemplateSlug(slug);
    setPrefillForm(form);
    setShowInitModal(true);
  }

  function handleTemplateSelectedFromCatalog(slug) {
    setSelectedTemplateSlug(slug);
    setPrefillForm(null);
    setShowInitModal(true);
  }

  function handleMemoryCreated(newMemory) {
    setShowInitModal(false);
    setActiveMemory(newMemory);
    loadMemories();
  }

  const hasMemory = memories.length > 0;

  return (
    <div className="space-y-6 p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-slate-900">Client Operating Memory</h1>
          <p className="text-sm text-slate-500">
            Adaptive intelligence that evolves from every workflow outcome.
          </p>
        </div>
        {!hasMemory && (
          <button
            type="button"
            onClick={() => setShowInitModal(true)}
            className="inline-flex items-center gap-2 rounded-md bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700"
          >
            <Plus className="h-4 w-4" />
            Initialize Memory
          </button>
        )}
        {hasMemory && (
          <button
            type="button"
            onClick={loadMemories}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        )}
      </div>

      {/* No workspace selected warning */}
      {!effectiveWorkspace && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
          Select a workspace in the header to view or create client memory for a specific workspace.
        </div>
      )}

      {/* Template Recommendation */}
      <TemplateRecommendationPanel
        workspaceSlug={effectiveWorkspace}
        onTemplateSelected={handleTemplateSelectedFromRecommender}
      />

      {/* Foundation Template Catalog */}
      <FoundationTemplatesBrowser onSelectTemplate={handleTemplateSelectedFromCatalog} />

      {/* Active Memory */}
      {loading && !hasMemory && (
        <div className="text-sm text-slate-400 text-center py-8">Loading client memory…</div>
      )}

      {!loading && !hasMemory && effectiveWorkspace && (
        <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
          <Brain className="h-8 w-8 text-slate-300 mx-auto mb-2" />
          <p className="text-sm font-medium text-slate-600">No client memory for this workspace</p>
          <p className="text-xs text-slate-400 mt-1 mb-4">Use the Template Recommendation tool above to get started, or browse the catalog.</p>
          <button
            type="button"
            onClick={() => setShowInitModal(true)}
            className="inline-flex items-center gap-2 rounded-md bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700"
          >
            <Plus className="h-4 w-4" />
            Initialize Memory
          </button>
        </div>
      )}

      {activeMemory && (
        <>
          {/* Memory switcher if multiple */}
          {memories.length > 1 && (
            <div className="flex gap-2">
              {memories.map((m) => (
                <button
                  key={m._id}
                  type="button"
                  onClick={() => setActiveMemory(m)}
                  className={`rounded-md border px-3 py-1.5 text-xs font-medium ${
                    activeMemory._id === m._id
                      ? "border-violet-300 bg-violet-50 text-violet-700"
                      : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {m.foundation_template_name || m.foundation_template_slug}
                </button>
              ))}
            </div>
          )}

          <MemoryDetailPanel memory={activeMemory} onRefresh={loadMemories} />

          <VersionHistoryPanel memoryId={activeMemory._id} onRollbackComplete={loadMemories} />

          <MemoryUpdateProposalsPanel
            workspaceSlug={activeMemory.workspace_slug || effectiveWorkspace}
            memoryId={activeMemory._id}
            onMemoryChanged={loadMemories}
          />
        </>
      )}

      {/* Init Modal */}
      {showInitModal && (
        <InitMemoryModal
          workspaceSlug={effectiveWorkspace}
          templateSlug={selectedTemplateSlug}
          prefillForm={prefillForm}
          onClose={() => setShowInitModal(false)}
          onCreated={handleMemoryCreated}
        />
      )}
    </div>
  );
}
