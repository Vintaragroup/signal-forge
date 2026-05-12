import { useEffect, useState } from "react";
import { Plus, X, ChevronDown, ChevronUp, Link, Trash2 } from "lucide-react";
import { api } from "../api.js";
import { SYSTEM_PROFILES } from "../navigation/systemProfiles.js";

// ── Constants ────────────────────────────────────────────────────────────────

const MODULES = [
  { value: "", label: "— none —" },
  { value: "contractor_growth", label: "contractor_growth" },
  { value: "artist_growth", label: "artist_growth" },
  { value: "insurance_growth", label: "insurance_growth" },
  { value: "media_growth", label: "media_growth" },
];

const TIERS = ["", "starter", "growth", "enterprise"];
const TONES = ["", "authoritative", "warm", "technical", "conversational"];
const STATUS_COLORS = {
  active: "bg-green-100 text-green-700",
  paused: "bg-amber-100 text-amber-700",
  archived: "bg-slate-100 text-slate-500",
};

function slugifyLocal(value) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

// ── WorkflowDefinitionSubForm ─────────────────────────────────────────────────

function WorkflowDefinitionSubForm({ onCreated, onCancel }) {
  const [defSlug, setDefSlug] = useState("");
  const [defName, setDefName] = useState("");
  const [defSystemProfileId, setDefSystemProfileId] = useState("");
  const [defModule, setDefModule] = useState("");
  const [defNotes, setDefNotes] = useState("");
  const [stages, setStages] = useState(
    Array.from({ length: 7 }, (_, i) => ({
      stage_number: i + 1,
      label: `Step ${i + 1}`,
      agent_key: "",
      run_card_type: "",
      chips: [],
      required: true,
      notes: "",
    }))
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function updateStage(index, field, value) {
    setStages((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      return next;
    });
  }

  async function handleCreate() {
    if (!defSlug.trim() || !defName.trim()) {
      setError("Slug and display name are required.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const payload = {
        slug: defSlug.trim(),
        display_name: defName.trim(),
        system_profile_id: defSystemProfileId,
        module: defModule,
        stages: stages.map((s) => ({
          ...s,
          chips: s.chips.filter(Boolean),
        })),
        notes: defNotes.trim(),
        status: "active",
      };
      const result = await api.createWorkflowDefinition(payload);
      onCreated(result.item);
    } catch (err) {
      setError(err.message || "Failed to create workflow definition.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="font-semibold text-slate-800 text-sm">New Workflow Definition</h4>
        <button type="button" onClick={onCancel} className="text-slate-400 hover:text-slate-600">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">Display Name *</label>
          <input
            type="text"
            value={defName}
            onChange={(e) => {
              setDefName(e.target.value);
              if (!defSlug) setDefSlug(slugifyLocal(e.target.value));
            }}
            placeholder="Executive Growth — Standard"
            className="w-full rounded border border-slate-200 bg-white px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">Slug *</label>
          <input
            type="text"
            value={defSlug}
            onChange={(e) => setDefSlug(slugifyLocal(e.target.value))}
            placeholder="executive-growth-v1"
            className="w-full rounded border border-slate-200 bg-white px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">System Profile</label>
          <select
            value={defSystemProfileId}
            onChange={(e) => setDefSystemProfileId(e.target.value)}
            className="w-full rounded border border-slate-200 bg-white px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          >
            <option value="">— none —</option>
            {SYSTEM_PROFILES.map((p) => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">Module</label>
          <select
            value={defModule}
            onChange={(e) => setDefModule(e.target.value)}
            className="w-full rounded border border-slate-200 bg-white px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          >
            {MODULES.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-slate-700">Notes</label>
        <textarea
          value={defNotes}
          onChange={(e) => setDefNotes(e.target.value)}
          rows={2}
          className="w-full rounded border border-slate-200 bg-white px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
      </div>

      <div>
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Stages (1–7)</div>
        <div className="space-y-1.5">
          {stages.map((stage, i) => (
            <div key={stage.stage_number} className="grid grid-cols-[2rem_1fr_1fr_1fr] gap-2 items-center">
              <span className="text-xs font-bold text-slate-500 text-center">{stage.stage_number}</span>
              <input
                type="text"
                value={stage.label}
                onChange={(e) => updateStage(i, "label", e.target.value)}
                placeholder="Stage label"
                className="rounded border border-slate-200 bg-white px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-300"
              />
              <input
                type="text"
                value={stage.agent_key}
                onChange={(e) => updateStage(i, "agent_key", e.target.value)}
                placeholder="agent_key"
                className="rounded border border-slate-200 bg-white px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-300"
              />
              <input
                type="text"
                value={stage.run_card_type}
                onChange={(e) => updateStage(i, "run_card_type", e.target.value)}
                placeholder="run_card_type"
                className="rounded border border-slate-200 bg-white px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-300"
              />
            </div>
          ))}
        </div>
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleCreate}
          disabled={loading}
          className="rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {loading ? "Saving…" : "Save Workflow Definition"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ── ClientProfileForm ─────────────────────────────────────────────────────────

function ClientProfileForm({ workspaces, workflowDefinitions, onCreated, onCancel }) {
  const [displayName, setDisplayName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugManual, setSlugManual] = useState(false);
  const [systemProfileId, setSystemProfileId] = useState("");
  const [module, setModule] = useState("");
  const [industry, setIndustry] = useState("");
  const [tier, setTier] = useState("");
  const [primaryGoal, setPrimaryGoal] = useState("");
  const [targetAudience, setTargetAudience] = useState("");
  const [tonePreference, setTonePreference] = useState("");
  const [contentCadence, setContentCadence] = useState("");
  const [workspaceSlug, setWorkspaceSlug] = useState("");
  const [workflowDefinitionId, setWorkflowDefinitionId] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showDefForm, setShowDefForm] = useState(false);
  const [localDefs, setLocalDefs] = useState(workflowDefinitions);

  useEffect(() => {
    setLocalDefs(workflowDefinitions);
  }, [workflowDefinitions]);

  function handleNameChange(value) {
    setDisplayName(value);
    if (!slugManual) {
      setSlug(slugifyLocal(value));
    }
  }

  function handleDefCreated(def) {
    setLocalDefs((prev) => [...prev, def]);
    setWorkflowDefinitionId(def.slug);
    setShowDefForm(false);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!displayName.trim()) {
      setError("Display name is required.");
      return;
    }
    if (!slug.trim()) {
      setError("Slug is required.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await api.createClientProfile({
        slug: slug.trim(),
        display_name: displayName.trim(),
        workspace_slug: workspaceSlug,
        system_profile_id: systemProfileId,
        module,
        industry: industry.trim(),
        tier,
        primary_goal: primaryGoal.trim(),
        target_audience: targetAudience.trim(),
        tone_preference: tonePreference,
        content_cadence: contentCadence.trim(),
        workflow_definition_id: workflowDefinitionId,
        notes: notes.trim(),
        status: "active",
      });
      onCreated();
    } catch (err) {
      setError(err.message || "Failed to create client profile.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-xl border border-blue-200 bg-blue-50 p-5 space-y-4 shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-slate-900">New Client Profile</h3>
        <button type="button" onClick={onCancel} className="text-slate-400 hover:text-slate-600">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Identity */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">
            Display Name <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => handleNameChange(e.target.value)}
            placeholder="John Maxwell"
            className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">
            Slug <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={slug}
            onChange={(e) => {
              setSlugManual(true);
              setSlug(slugifyLocal(e.target.value));
            }}
            placeholder="john-maxwell"
            className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
        </div>
      </div>

      {/* Classification */}
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">System Profile</label>
          <select
            value={systemProfileId}
            onChange={(e) => setSystemProfileId(e.target.value)}
            className="w-full rounded-md border border-slate-200 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          >
            <option value="">— none —</option>
            {SYSTEM_PROFILES.map((p) => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">Module</label>
          <select
            value={module}
            onChange={(e) => setModule(e.target.value)}
            className="w-full rounded-md border border-slate-200 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          >
            {MODULES.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">Tier</label>
          <select
            value={tier}
            onChange={(e) => setTier(e.target.value)}
            className="w-full rounded-md border border-slate-200 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          >
            {TIERS.map((t) => (
              <option key={t} value={t}>{t || "— none —"}</option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-slate-700">Industry</label>
        <input
          type="text"
          value={industry}
          onChange={(e) => setIndustry(e.target.value)}
          placeholder="Leadership Development"
          className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
      </div>

      {/* Goals & Context */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">Primary Goal</label>
          <textarea
            value={primaryGoal}
            onChange={(e) => setPrimaryGoal(e.target.value)}
            rows={2}
            placeholder="Book 3 keynotes per quarter"
            className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">Target Audience</label>
          <textarea
            value={targetAudience}
            onChange={(e) => setTargetAudience(e.target.value)}
            rows={2}
            placeholder="HR directors, Fortune 500"
            className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">Tone Preference</label>
          <select
            value={tonePreference}
            onChange={(e) => setTonePreference(e.target.value)}
            className="w-full rounded-md border border-slate-200 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          >
            {TONES.map((t) => (
              <option key={t} value={t}>{t || "— none —"}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">Content Cadence</label>
          <input
            type="text"
            value={contentCadence}
            onChange={(e) => setContentCadence(e.target.value)}
            placeholder="2x/week"
            className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
        </div>
      </div>

      {/* Links */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">Link Workspace</label>
          <select
            value={workspaceSlug}
            onChange={(e) => setWorkspaceSlug(e.target.value)}
            className="w-full rounded-md border border-slate-200 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          >
            <option value="">— none —</option>
            {workspaces.map((ws) => (
              <option key={ws.slug} value={ws.slug}>{ws.name} ({ws.slug})</option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">
            Workflow Definition
            <button
              type="button"
              onClick={() => setShowDefForm((v) => !v)}
              className="ml-2 text-indigo-600 hover:text-indigo-800 text-[10px] underline"
            >
              + new
            </button>
          </label>
          <select
            value={workflowDefinitionId}
            onChange={(e) => setWorkflowDefinitionId(e.target.value)}
            className="w-full rounded-md border border-slate-200 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          >
            <option value="">— none —</option>
            {localDefs.map((d) => (
              <option key={d.slug} value={d.slug}>{d.display_name} ({d.slug})</option>
            ))}
          </select>
        </div>
      </div>

      {showDefForm && (
        <WorkflowDefinitionSubForm
          onCreated={handleDefCreated}
          onCancel={() => setShowDefForm(false)}
        />
      )}

      <div>
        <label className="mb-1 block text-xs font-medium text-slate-700">Notes</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Creating…" : "Create Client Profile"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

// ── ProfileRow ────────────────────────────────────────────────────────────────

function ProfileRow({ profile, onArchive }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex items-center gap-3">
          <span className="font-medium text-slate-900 text-sm">{profile.display_name}</span>
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-mono text-slate-500">{profile.slug}</span>
          {profile.module && (
            <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] text-blue-600">{profile.module}</span>
          )}
          {profile.tier && (
            <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-600">{profile.tier}</span>
          )}
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${STATUS_COLORS[profile.status] || "bg-slate-100 text-slate-600"}`}>
            {profile.status}
          </span>
        </div>
        {open ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
      </button>

      {open && (
        <div className="border-t border-slate-100 px-4 py-3 space-y-2 text-xs text-slate-600">
          {profile.system_profile_id && <div><span className="font-medium">System Profile:</span> {profile.system_profile_id}</div>}
          {profile.industry && <div><span className="font-medium">Industry:</span> {profile.industry}</div>}
          {profile.primary_goal && <div><span className="font-medium">Goal:</span> {profile.primary_goal}</div>}
          {profile.target_audience && <div><span className="font-medium">Audience:</span> {profile.target_audience}</div>}
          {profile.tone_preference && <div><span className="font-medium">Tone:</span> {profile.tone_preference}</div>}
          {profile.content_cadence && <div><span className="font-medium">Cadence:</span> {profile.content_cadence}</div>}
          {profile.workspace_slug && <div><span className="font-medium">Workspace:</span> {profile.workspace_slug}</div>}
          {profile.workflow_definition_id && <div><span className="font-medium">Workflow Def:</span> {profile.workflow_definition_id}</div>}
          {profile.notes && <div><span className="font-medium">Notes:</span> {profile.notes}</div>}

          {profile.status !== "archived" && (
            <button
              type="button"
              onClick={() => onArchive(profile.slug)}
              className="mt-2 rounded border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] text-slate-500 hover:bg-slate-100"
            >
              Archive
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Source Registry constants ─────────────────────────────────────────────────

const SOURCE_TYPES = [
  { value: "website", label: "Website" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "instagram", label: "Instagram" },
  { value: "youtube", label: "YouTube" },
  { value: "tiktok", label: "TikTok" },
  { value: "x", label: "X (Twitter)" },
  { value: "facebook", label: "Facebook" },
  { value: "google_drive", label: "Google Drive" },
  { value: "dropbox", label: "Dropbox" },
  { value: "rss_feed", label: "RSS Feed" },
  { value: "podcast", label: "Podcast" },
  { value: "media_library", label: "Media Library" },
];

const HEALTH_COLORS = {
  ready: "bg-green-100 text-green-700",
  inactive: "bg-slate-100 text-slate-500",
  invalid: "bg-red-100 text-red-700",
};

// ── ClientSourceForm ──────────────────────────────────────────────────────────

function ClientSourceForm({ profiles, onCreated, onCancel }) {
  const [sourceType, setSourceType] = useState("website");
  const [label, setLabel] = useState("");
  const [uri, setUri] = useState("");
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState("active");
  const [profileSlug, setProfileSlug] = useState(profiles[0]?.slug || "");
  const [workspaceSlug, setWorkspaceSlug] = useState(profiles[0]?.workspace_slug || "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function handleProfileChange(slug) {
    setProfileSlug(slug);
    const p = profiles.find((pr) => pr.slug === slug);
    setWorkspaceSlug(p?.workspace_slug || "");
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!label.trim() || !uri.trim()) {
      setError("Label and URI are required.");
      return;
    }
    if (!profileSlug) {
      setError("Select a client profile.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result = await api.createClientSource({
        workspace_slug: workspaceSlug,
        client_profile_slug: profileSlug,
        source_type: sourceType,
        label: label.trim(),
        uri: uri.trim(),
        notes: notes.trim() || null,
        status,
      });
      onCreated(result.item);
    } catch (err) {
      setError(err.message || "Failed to add source.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-lg border border-teal-200 bg-teal-50 p-4 space-y-3"
    >
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-slate-800">Add Source</h4>
        <button type="button" onClick={onCancel} className="text-slate-400 hover:text-slate-600">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">Client Profile *</label>
          <select
            value={profileSlug}
            onChange={(e) => handleProfileChange(e.target.value)}
            className="w-full rounded border border-slate-200 bg-white px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-300"
          >
            {profiles.map((p) => (
              <option key={p.slug} value={p.slug}>{p.display_name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">Source Type *</label>
          <select
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value)}
            className="w-full rounded border border-slate-200 bg-white px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-300"
          >
            {SOURCE_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">Label *</label>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="John's LinkedIn"
            className="w-full rounded border border-slate-200 bg-white px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-300"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">URI *</label>
          <input
            type="text"
            value={uri}
            onChange={(e) => setUri(e.target.value)}
            placeholder="https://linkedin.com/in/..."
            className="w-full rounded border border-slate-200 bg-white px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-300"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">Notes</label>
          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Optional context"
            className="w-full rounded border border-slate-200 bg-white px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-300"
          />
        </div>
        <div className="flex items-end gap-3">
          <label className="flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={status === "active"}
              onChange={(e) => setStatus(e.target.checked ? "active" : "inactive")}
              className="h-3.5 w-3.5 rounded"
            />
            Active
          </label>
        </div>
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={loading}
          className="rounded bg-teal-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-teal-700 disabled:opacity-50"
        >
          {loading ? "Adding…" : "Add Source"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

// ── SourceRow ─────────────────────────────────────────────────────────────────

function SourceRow({ source, onDelete, onToggleStatus }) {
  const [deleting, setDeleting] = useState(false);
  const [toggling, setToggling] = useState(false);

  const typeLabel = SOURCE_TYPES.find((t) => t.value === source.source_type)?.label || source.source_type;
  const healthClass = HEALTH_COLORS[source.health_status] || "bg-slate-100 text-slate-500";

  async function handleDelete() {
    if (!window.confirm(`Remove source "${source.label}"?`)) return;
    setDeleting(true);
    try {
      await onDelete(source._id);
    } finally {
      setDeleting(false);
    }
  }

  async function handleToggle() {
    setToggling(true);
    try {
      await onToggleStatus(source._id, source.status === "active" ? "inactive" : "active");
    } finally {
      setToggling(false);
    }
  }

  return (
    <tr className="border-t border-slate-100 text-xs">
      <td className="py-2 px-3">
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">{typeLabel}</span>
      </td>
      <td className="py-2 px-3 font-medium text-slate-800">{source.label}</td>
      <td className="py-2 px-3 max-w-[200px] truncate text-slate-500">
        <a href={source.uri} target="_blank" rel="noreferrer" className="hover:text-teal-600 hover:underline flex items-center gap-1">
          <Link className="h-3 w-3 shrink-0" />
          <span className="truncate">{source.uri}</span>
        </a>
      </td>
      <td className="py-2 px-3">
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${STATUS_COLORS[source.status] || "bg-slate-100 text-slate-500"}`}>
          {source.status}
        </span>
      </td>
      <td className="py-2 px-3">
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${healthClass}`}>
          {source.health_status}
        </span>
      </td>
      <td className="py-2 px-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleToggle}
            disabled={toggling}
            className="text-[10px] text-slate-500 hover:text-slate-800 disabled:opacity-40"
          >
            {source.status === "active" ? "Deactivate" : "Activate"}
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={deleting}
            className="text-red-400 hover:text-red-600 disabled:opacity-40"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </td>
    </tr>
  );
}

// ── ClientSourceSection ───────────────────────────────────────────────────────

function ClientSourceSection({ profiles }) {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState("");

  async function loadSources() {
    setLoading(true);
    setError("");
    try {
      const data = await api.clientSources();
      setSources(data.items || []);
    } catch (err) {
      setError(err.message || "Failed to load sources.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSources();
  }, []);

  async function handleDelete(id) {
    try {
      await api.deleteClientSource(id);
      setSources((prev) => prev.filter((s) => s._id !== id));
    } catch (err) {
      alert(`Delete failed: ${err.message}`);
    }
  }

  async function handleToggleStatus(id, newStatus) {
    try {
      const result = await api.updateClientSource(id, { status: newStatus });
      setSources((prev) => prev.map((s) => (s._id === id ? result.item : s)));
    } catch (err) {
      alert(`Update failed: ${err.message}`);
    }
  }

  function handleCreated(newSource) {
    setSources((prev) => [newSource, ...prev]);
    setShowAdd(false);
  }

  const activeSources = sources.filter((s) => s.status === "active");
  const connectedTypes = [...new Set(activeSources.map((s) => s.source_type))];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Client Sources</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Configure websites, social profiles, and content sources for each client.
            Used to make discovery recommendations client-aware.
          </p>
        </div>
        {!showAdd && (
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className="inline-flex items-center gap-1.5 rounded bg-teal-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-teal-700"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Source
          </button>
        )}
      </div>

      {activeSources.length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 rounded-lg border border-teal-100 bg-teal-50 px-3 py-2 text-xs text-teal-800">
          <span><strong>{activeSources.length}</strong> active source{activeSources.length !== 1 ? "s" : ""}</span>
          {connectedTypes.length > 0 && (
            <span>Connected: {connectedTypes.map((t) => SOURCE_TYPES.find((st) => st.value === t)?.label || t).join(", ")}</span>
          )}
        </div>
      )}

      {showAdd && profiles.length > 0 && (
        <ClientSourceForm
          profiles={profiles}
          onCreated={handleCreated}
          onCancel={() => setShowAdd(false)}
        />
      )}
      {showAdd && profiles.length === 0 && (
        <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
          Create a client profile first before adding sources.
        </p>
      )}

      {error && <p className="text-xs text-red-600">{error}</p>}

      {loading ? (
        <p className="text-xs text-slate-500">Loading sources…</p>
      ) : sources.length === 0 ? (
        <p className="text-xs text-slate-500">No sources configured yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full min-w-[600px]">
            <thead>
              <tr className="text-left text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Label</th>
                <th className="px-3 py-2">URI</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Health</th>
                <th className="px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <SourceRow
                  key={s._id}
                  source={s}
                  onDelete={handleDelete}
                  onToggleStatus={handleToggleStatus}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── AdminOnboardingPage ───────────────────────────────────────────────────────

export default function AdminOnboardingPage() {
  const [profiles, setProfiles] = useState([]);
  const [workspaces, setWorkspaces] = useState([]);
  const [workflowDefs, setWorkflowDefs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [profileData, wsData, wdefData] = await Promise.all([
        api.clientProfiles(),
        api.workspaces(),
        api.workflowDefinitions(),
      ]);
      setProfiles(profileData.items || []);
      setWorkspaces(wsData.items || []);
      setWorkflowDefs(wdefData.items || []);
    } catch (err) {
      setError(err.message || "Failed to load data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleArchive(slug) {
    try {
      await api.updateClientProfileStatus(slug, "archived");
      await load();
    } catch (err) {
      alert(`Archive failed: ${err.message}`);
    }
  }

  function handleCreated() {
    setShowCreate(false);
    load();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Admin — Client Onboarding</h2>
          <p className="mt-0.5 text-sm text-slate-500">
            Create and manage client profiles and workflow definitions. No client-facing access.
          </p>
        </div>
        {!showCreate && (
          <button
            type="button"
            onClick={() => setShowCreate(true)}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            New Client Profile
          </button>
        )}
      </div>

      {showCreate && (
        <ClientProfileForm
          workspaces={workspaces}
          workflowDefinitions={workflowDefs}
          onCreated={handleCreated}
          onCancel={() => setShowCreate(false)}
        />
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      {loading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : profiles.length === 0 ? (
        <p className="text-sm text-slate-500">No client profiles yet. Create one above.</p>
      ) : (
        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            {profiles.length} Profile{profiles.length !== 1 ? "s" : ""}
          </div>
          {profiles.map((p) => (
            <ProfileRow key={p.slug} profile={p} onArchive={handleArchive} />
          ))}
        </div>
      )}

      <div className="mt-8 border-t border-slate-200 pt-6">
        <ClientSourceSection profiles={profiles} />
      </div>
    </div>
  );
}
