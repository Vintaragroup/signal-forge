import { useEffect, useState } from "react";
import { Briefcase, Plus, X } from "lucide-react";
import { api } from "../api.js";

const TYPE_LABELS = {
  internal: "Internal",
  client: "Client",
  demo: "Demo",
  test: "Test",
};

const STATUS_COLORS = {
  active: "bg-green-100 text-green-700",
  paused: "bg-amber-100 text-amber-700",
  archived: "bg-slate-100 text-slate-500",
};

const VALID_MODULES = [
  "",
  "contractor_growth",
  "artist_growth",
  "insurance_growth",
  "media_growth",
];

function WorkspaceCard({ workspace, onStatusChange }) {
  const [loading, setLoading] = useState(false);

  async function handleStatus(newStatus) {
    setLoading(true);
    try {
      await api.updateWorkspaceStatus(workspace.slug, newStatus);
      onStatusChange();
    } catch (err) {
      alert(`Failed to update status: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  const isDefault = workspace.slug === "default";

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Briefcase className="h-4 w-4 text-slate-400" />
          <div>
            <div className="font-semibold text-slate-900">{workspace.name}</div>
            <div className="text-xs text-slate-500">slug: {workspace.slug}</div>
          </div>
        </div>
        <span
          className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[workspace.status] || "bg-slate-100 text-slate-600"}`}
        >
          {workspace.status}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-600">
        <span className="rounded bg-slate-100 px-2 py-0.5">
          type: {TYPE_LABELS[workspace.type] || workspace.type}
        </span>
        {workspace.module && (
          <span className="rounded bg-slate-100 px-2 py-0.5">module: {workspace.module}</span>
        )}
      </div>

      {workspace.notes && (
        <p className="mt-2 text-xs text-slate-500">{workspace.notes}</p>
      )}

      {!isDefault && (
        <div className="mt-4 flex gap-2">
          {workspace.status !== "active" && (
            <button
              type="button"
              onClick={() => handleStatus("active")}
              disabled={loading}
              className="rounded-md border border-green-200 bg-green-50 px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-100 disabled:opacity-50"
            >
              Activate
            </button>
          )}
          {workspace.status === "active" && (
            <button
              type="button"
              onClick={() => handleStatus("paused")}
              disabled={loading}
              className="rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-100 disabled:opacity-50"
            >
              Pause
            </button>
          )}
          {workspace.status !== "archived" && (
            <button
              type="button"
              onClick={() => handleStatus("archived")}
              disabled={loading}
              className="rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-100 disabled:opacity-50"
            >
              Archive
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function CreateWorkspaceForm({ onCreate, onCancel }) {
  const [name, setName] = useState("");
  const [type, setType] = useState("client");
  const [module, setModule] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Workspace name is required.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await api.createWorkspace({ name: name.trim(), type, module, notes });
      onCreate();
    } catch (err) {
      setError(err.message || "Failed to create workspace.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-blue-200 bg-blue-50 p-5 shadow-sm"
    >
      <div className="mb-4 flex items-center justify-between">
        <h3 className="font-semibold text-slate-900">New Workspace</h3>
        <button
          type="button"
          onClick={onCancel}
          className="text-slate-400 hover:text-slate-600"
          aria-label="Cancel"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="space-y-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">
            Name <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Acme Corp, Insurance Test"
            className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-700">Type</label>
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="w-full rounded-md border border-slate-200 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            >
              <option value="client">Client</option>
              <option value="internal">Internal</option>
              <option value="demo">Demo</option>
              <option value="test">Test</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-700">Module</label>
            <select
              value={module}
              onChange={(e) => setModule(e.target.value)}
              className="w-full rounded-md border border-slate-200 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            >
              <option value="">All / none</option>
              {VALID_MODULES.filter(Boolean).map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">Notes</label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            placeholder="Optional context or description"
            className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
        </div>
      </div>

      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}

      <div className="mt-4 flex gap-2">
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Creating…" : "Create Workspace"}
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

export default function WorkspacesPage({ onWorkspacesChange }) {
  const [workspaces, setWorkspaces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  async function load() {
    setLoading(true);
    api
      .workspaces()
      .then((data) => setWorkspaces(data.items || []))
      .catch(() => setWorkspaces([]))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  function handleCreated() {
    setShowCreate(false);
    load();
    if (onWorkspacesChange) onWorkspacesChange();
  }

  function handleStatusChange() {
    load();
    if (onWorkspacesChange) onWorkspacesChange();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Workspaces</h2>
          <p className="mt-0.5 text-sm text-slate-500">
            Separate work by client, campaign, or purpose. Use the workspace selector in the header to filter all pages to a single workspace.
          </p>
        </div>
        {!showCreate && (
          <button
            type="button"
            onClick={() => setShowCreate(true)}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            New Workspace
          </button>
        )}
      </div>

      {showCreate && (
        <CreateWorkspaceForm onCreate={handleCreated} onCancel={() => setShowCreate(false)} />
      )}

      {loading ? (
        <p className="text-sm text-slate-500">Loading workspaces…</p>
      ) : workspaces.length === 0 ? (
        <p className="text-sm text-slate-500">No workspaces found. Create one above.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {workspaces.map((ws) => (
            <WorkspaceCard key={ws.slug} workspace={ws} onStatusChange={handleStatusChange} />
          ))}
        </div>
      )}

      <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-xs text-slate-500">
        <strong className="text-slate-700">How workspaces work:</strong> Records (contacts, leads, messages, deals, candidates) are assigned a <code>workspace_slug</code> when imported or created within a workspace. The header workspace selector filters all pages to show only records for the selected workspace. Selecting <em>All Workspaces</em> shows all records regardless of workspace. Existing records without a workspace_slug are not filtered out when <em>All Workspaces</em> is selected.
      </div>
    </div>
  );
}
