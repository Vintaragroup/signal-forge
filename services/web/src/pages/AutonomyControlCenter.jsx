import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Clock,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Shield,
  ShieldOff,
  Sliders,
  Zap,
} from "lucide-react";
import { api } from "../api";

// ── Risk / status style maps ───────────────────────────────────────────────────
const RISK_STYLES = {
  low:     "bg-green-100 text-green-800",
  medium:  "bg-yellow-100 text-yellow-800",
  high:    "bg-red-100 text-red-800",
  unknown: "bg-gray-100 text-gray-600",
};

const STATUS_STYLES = {
  pending:           "bg-blue-100 text-blue-700",
  applied:           "bg-green-100 text-green-800",
  auto_applied:      "bg-emerald-100 text-emerald-800",
  rolled_back:       "bg-orange-100 text-orange-700",
  blocked:           "bg-red-100 text-red-700",
  auto_blocked:      "bg-red-100 text-red-700",
  operator_overridden: "bg-purple-100 text-purple-700",
};

function RiskBadge({ level }) {
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${RISK_STYLES[level] || RISK_STYLES.unknown}`}>
      {level || "unknown"}
    </span>
  );
}

function StatusBadge({ status }) {
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_STYLES[status] || "bg-gray-100 text-gray-600"}`}>
      {(status || "unknown").replace(/_/g, " ")}
    </span>
  );
}

function MetricCard({ label, value, sub, accent }) {
  const accentMap = {
    blue:   "border-blue-400",
    green:  "border-green-400",
    yellow: "border-yellow-400",
    red:    "border-red-400",
    gray:   "border-gray-300",
  };
  return (
    <div className={`bg-white rounded-lg border-l-4 ${accentMap[accent] || accentMap.gray} shadow-sm p-4`}>
      <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{label}</p>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}

function SectionHeader({ icon: Icon, title, count }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <Icon className="w-4 h-4 text-gray-500" />
      <h3 className="font-semibold text-gray-800 text-sm">{title}</h3>
      {count !== undefined && (
        <span className="ml-auto text-xs bg-gray-100 text-gray-600 rounded-full px-2 py-0.5">
          {count}
        </span>
      )}
    </div>
  );
}

function PolicyCard({ policy, onEdit }) {
  const [expanded, setExpanded] = useState(false);
  const isGlobal = policy.workspace_slug === "__global__";

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Sliders className="w-4 h-4 text-gray-400" />
          <span className="font-medium text-sm text-gray-800">
            {isGlobal ? "Global Policy" : policy.workspace_slug}
          </span>
          {isGlobal && (
            <span className="text-xs bg-blue-100 text-blue-700 rounded-full px-2 py-0.5">global</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`text-xs font-medium px-2 py-0.5 rounded-full ${
              policy.autonomy_enabled
                ? "bg-green-100 text-green-700"
                : "bg-gray-100 text-gray-500"
            }`}
          >
            {policy.autonomy_enabled ? "enabled" : "disabled"}
          </span>
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-gray-400 hover:text-gray-600"
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      <div className="flex items-center gap-4 text-xs text-gray-500">
        <span>Max risk: <strong className="text-gray-700">{policy.max_autonomy_risk}</strong></span>
        <span>Threshold: <strong className="text-gray-700">{((policy.auto_apply_threshold || 0.9) * 100).toFixed(0)}%</strong></span>
        <span>Archive after: <strong className="text-gray-700">{policy.auto_archive_days}d</strong></span>
      </div>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-gray-100 space-y-2">
          <div>
            <p className="text-xs text-gray-500 mb-1">Require review for:</p>
            <div className="flex flex-wrap gap-1">
              {(policy.require_review_for || []).length === 0 ? (
                <span className="text-xs text-gray-400">none</span>
              ) : (
                (policy.require_review_for || []).map((t) => (
                  <span key={t} className="text-xs bg-yellow-50 text-yellow-700 border border-yellow-200 rounded px-1.5 py-0.5">
                    {t}
                  </span>
                ))
              )}
            </div>
          </div>
          {onEdit && (
            <button
              onClick={() => onEdit(policy)}
              className="text-xs text-blue-600 hover:underline"
            >
              Edit policy
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function ActionRow({ action, onRollback }) {
  const canRollback =
    ["applied", "auto_applied"].includes(action.status) &&
    action.rollback_supported !== false;

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3 flex items-start justify-between gap-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap mb-1">
          <span className="text-sm font-medium text-gray-800 truncate">
            {(action.action_type || "unknown").replace(/_/g, " ")}
          </span>
          <RiskBadge level={action.risk_level} />
          <StatusBadge status={action.status} />
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          {action.workspace_slug && (
            <span className="font-mono truncate">{action.workspace_slug}</span>
          )}
          {action.confidence_score !== undefined && (
            <span>conf: {(action.confidence_score * 100).toFixed(0)}%</span>
          )}
          {action.created_at && (
            <span>{new Date(action.created_at).toLocaleDateString()}</span>
          )}
        </div>
      </div>
      {canRollback && (
        <button
          onClick={() => onRollback(action.id)}
          className="flex items-center gap-1 text-xs text-orange-600 border border-orange-200 rounded px-2 py-1 hover:bg-orange-50 whitespace-nowrap"
        >
          <RotateCcw className="w-3 h-3" /> Rollback
        </button>
      )}
    </div>
  );
}

// ── Edit Policy Modal ──────────────────────────────────────────────────────────
function EditPolicyModal({ policy, onSave, onClose }) {
  const [form, setForm] = useState({
    autonomy_enabled: policy.autonomy_enabled ?? true,
    max_autonomy_risk: policy.max_autonomy_risk ?? "low",
    auto_apply_threshold: policy.auto_apply_threshold ?? 0.90,
    auto_archive_days: policy.auto_archive_days ?? 30,
  });
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(policy.workspace_slug, form);
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
        <h3 className="text-base font-semibold text-gray-900 mb-4">
          Edit Policy — {policy.workspace_slug === "__global__" ? "Global" : policy.workspace_slug}
        </h3>
        <div className="space-y-4">
          <label className="flex items-center justify-between">
            <span className="text-sm text-gray-700">Autonomy Enabled</span>
            <input
              type="checkbox"
              checked={form.autonomy_enabled}
              onChange={(e) => setForm((f) => ({ ...f, autonomy_enabled: e.target.checked }))}
              className="w-4 h-4"
            />
          </label>
          <div>
            <label className="block text-sm text-gray-700 mb-1">Max Risk Level</label>
            <select
              value={form.max_autonomy_risk}
              onChange={(e) => setForm((f) => ({ ...f, max_autonomy_risk: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-700 mb-1">
              Auto-Apply Threshold ({Math.round(form.auto_apply_threshold * 100)}%)
            </label>
            <input
              type="range"
              min="0.5"
              max="1.0"
              step="0.05"
              value={form.auto_apply_threshold}
              onChange={(e) => setForm((f) => ({ ...f, auto_apply_threshold: parseFloat(e.target.value) }))}
              className="w-full"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-700 mb-1">Archive After (days)</label>
            <input
              type="number"
              min="1"
              max="365"
              value={form.auto_archive_days}
              onChange={(e) => setForm((f) => ({ ...f, auto_archive_days: parseInt(e.target.value) || 30 }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-60"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────────
const DAYS_OPTIONS = [
  { label: "7d", value: 7 },
  { label: "30d", value: 30 },
  { label: "90d", value: 90 },
];

const ACTION_TABS = [
  { label: "All", value: "" },
  { label: "Pending", value: "pending" },
  { label: "Applied", value: "applied" },
  { label: "Auto-Applied", value: "auto_applied" },
  { label: "Rolled Back", value: "rolled_back" },
  { label: "Blocked", value: "blocked" },
];

export default function AutonomyControlCenter({ activeWorkspace }) {
  const [days, setDays] = useState(30);
  const [actionTab, setActionTab] = useState("");
  const [policies, setPolicies] = useState([]);
  const [actions, setActions] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [paused, setPaused] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editingPolicy, setEditingPolicy] = useState(null);
  const [pauseLoading, setPauseLoading] = useState(false);

  const wsSlug = activeWorkspace?.slug || "";

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [polRes, actRes, analyticsRes] = await Promise.all([
        api.getAutonomyPolicies(wsSlug),
        api.listAutonomyActions(wsSlug, actionTab, "", 100),
        api.getAutonomyAnalytics(wsSlug, days),
      ]);
      setPolicies(polRes.policies || []);
      setPaused(polRes.autonomy_paused ?? false);
      setActions(actRes.actions || []);
      setAnalytics(analyticsRes);
    } catch (e) {
      setError(e.message || "Failed to load autonomy data");
    } finally {
      setLoading(false);
    }
  }, [wsSlug, days, actionTab]);

  useEffect(() => { load(); }, [load]);

  const handlePauseResume = async () => {
    setPauseLoading(true);
    try {
      const res = paused ? await api.resumeAutonomy() : await api.pauseAutonomy();
      setPaused(res.autonomy_paused);
    } finally {
      setPauseLoading(false);
    }
  };

  const handleRollback = async (actionId) => {
    try {
      await api.rollbackAutonomyAction(actionId);
      load();
    } catch (e) {
      alert(`Rollback failed: ${e.message}`);
    }
  };

  const handleSavePolicy = async (workspace, updates) => {
    await api.updateAutonomyPolicy(workspace, updates);
    load();
  };

  // Derived subsets
  const pendingActions = actions.filter((a) => a.status === "pending");
  const blockedActions = actions.filter((a) => ["blocked", "auto_blocked"].includes(a.status));
  const rollbackQueue = actions.filter((a) =>
    ["applied", "auto_applied"].includes(a.status) && a.rollback_supported !== false
  );

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Shield className="w-6 h-6 text-blue-600" />
          <div>
            <h1 className="text-xl font-bold text-gray-900">Autonomy Control Center</h1>
            <p className="text-sm text-gray-500">
              {wsSlug ? `Workspace: ${wsSlug}` : "All workspaces"}
              {" · "}Bounded autonomous operational governance
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Days selector */}
          <div className="flex border border-gray-200 rounded-lg overflow-hidden">
            {DAYS_OPTIONS.map(({ label, value }) => (
              <button
                key={value}
                onClick={() => setDays(value)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  days === value
                    ? "bg-blue-600 text-white"
                    : "text-gray-600 hover:bg-gray-50"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {/* Pause / Resume */}
          <button
            onClick={handlePauseResume}
            disabled={pauseLoading}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              paused
                ? "bg-green-600 text-white hover:bg-green-700"
                : "bg-red-600 text-white hover:bg-red-700"
            } disabled:opacity-60`}
          >
            {paused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
            {paused ? "Resume Autonomy" : "Pause Autonomy"}
          </button>
          <button
            onClick={load}
            className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Paused Banner */}
      {paused && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          <ShieldOff className="w-4 h-4 flex-shrink-0" />
          <strong>Autonomy is globally paused.</strong> No autonomous actions will execute until resumed.
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Analytics Metrics */}
      {analytics && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
          <MetricCard label="Total Actions" value={analytics.total_actions} accent="gray" />
          <MetricCard
            label="Applied"
            value={analytics.applied_actions}
            sub={`${(analytics.auto_apply_success_rate * 100).toFixed(0)}% success rate`}
            accent="green"
          />
          <MetricCard
            label="Pending"
            value={analytics.pending_actions}
            accent="blue"
          />
          <MetricCard
            label="Rolled Back"
            value={analytics.rolled_back_actions}
            sub={`${(analytics.rollback_rate * 100).toFixed(0)}% of applied`}
            accent="yellow"
          />
          <MetricCard
            label="Blocked"
            value={analytics.blocked_actions}
            accent="red"
          />
          <MetricCard
            label="Op. Overrides"
            value={analytics.operator_override_count}
            accent="gray"
          />
        </div>
      )}

      {loading && (
        <div className="text-center py-12 text-gray-400">Loading autonomy data…</div>
      )}

      {!loading && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Policies + Analytics breakdown */}
          <div className="space-y-6">
            {/* Active Policies */}
            <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
              <SectionHeader icon={Sliders} title="Active Policies" count={policies.length} />
              <div className="space-y-3">
                {policies.length === 0 ? (
                  <p className="text-xs text-gray-400">No policies configured. Using defaults.</p>
                ) : (
                  policies.map((p) => (
                    <PolicyCard
                      key={p.workspace_slug}
                      policy={p}
                      onEdit={(pol) => setEditingPolicy(pol)}
                    />
                  ))
                )}
              </div>
            </div>

            {/* By Action Type */}
            {analytics && Object.keys(analytics.by_action_type).length > 0 && (
              <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
                <SectionHeader icon={Activity} title="By Action Type" />
                <div className="space-y-1.5">
                  {Object.entries(analytics.by_action_type)
                    .sort((a, b) => b[1] - a[1])
                    .map(([type, count]) => (
                      <div key={type} className="flex items-center justify-between text-xs">
                        <span className="text-gray-600 truncate">
                          {type.replace(/_/g, " ")}
                        </span>
                        <span className="font-medium text-gray-800 ml-2">{count}</span>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* By Risk Level */}
            {analytics && Object.keys(analytics.by_risk_level).length > 0 && (
              <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
                <SectionHeader icon={AlertTriangle} title="By Risk Level" />
                <div className="space-y-1.5">
                  {Object.entries(analytics.by_risk_level).map(([level, count]) => (
                    <div key={level} className="flex items-center justify-between text-xs">
                      <RiskBadge level={level} />
                      <span className="font-medium text-gray-800">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right: Action log */}
          <div className="lg:col-span-2 space-y-6">
            {/* Safety Alerts */}
            {blockedActions.length > 0 && (
              <div className="bg-red-50 rounded-xl p-4 border border-red-200">
                <SectionHeader icon={AlertTriangle} title="Safety Alerts" count={blockedActions.length} />
                <div className="space-y-2">
                  {blockedActions.map((a) => (
                    <ActionRow key={a.id} action={a} onRollback={handleRollback} />
                  ))}
                </div>
              </div>
            )}

            {/* Pending High-Risk Actions */}
            {pendingActions.filter((a) => a.risk_level !== "low").length > 0 && (
              <div className="bg-yellow-50 rounded-xl p-4 border border-yellow-200">
                <SectionHeader
                  icon={Clock}
                  title="Pending High-Risk Actions"
                  count={pendingActions.filter((a) => a.risk_level !== "low").length}
                />
                <div className="space-y-2">
                  {pendingActions
                    .filter((a) => a.risk_level !== "low")
                    .map((a) => (
                      <ActionRow key={a.id} action={a} onRollback={handleRollback} />
                    ))}
                </div>
              </div>
            )}

            {/* Rollback Queue */}
            {rollbackQueue.length > 0 && (
              <div className="bg-orange-50 rounded-xl p-4 border border-orange-200">
                <SectionHeader icon={RotateCcw} title="Rollback Queue" count={rollbackQueue.length} />
                <div className="space-y-2">
                  {rollbackQueue.map((a) => (
                    <ActionRow key={a.id} action={a} onRollback={handleRollback} />
                  ))}
                </div>
              </div>
            )}

            {/* All Autonomous Actions with tab filter */}
            <div className="bg-white rounded-xl border border-gray-200">
              <div className="px-4 pt-4 pb-2">
                <SectionHeader icon={Zap} title="Autonomous Actions" count={actions.length} />
                <div className="flex gap-1 flex-wrap">
                  {ACTION_TABS.map(({ label, value }) => (
                    <button
                      key={value}
                      onClick={() => setActionTab(value)}
                      className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
                        actionTab === value
                          ? "bg-blue-600 text-white"
                          : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="p-4 pt-2 space-y-2 max-h-96 overflow-y-auto">
                {actions.length === 0 ? (
                  <p className="text-xs text-gray-400 py-4 text-center">
                    No autonomous actions recorded yet.
                  </p>
                ) : (
                  actions.map((a) => (
                    <ActionRow key={a.id} action={a} onRollback={handleRollback} />
                  ))
                )}
              </div>
            </div>

            {/* Auto-Applied Changes */}
            {actions.filter((a) => a.status === "auto_applied").length > 0 && (
              <div className="bg-emerald-50 rounded-xl p-4 border border-emerald-200">
                <SectionHeader
                  icon={CheckCircle}
                  title="Auto-Applied Changes"
                  count={actions.filter((a) => a.status === "auto_applied").length}
                />
                <div className="space-y-2">
                  {actions
                    .filter((a) => a.status === "auto_applied")
                    .map((a) => (
                      <ActionRow key={a.id} action={a} onRollback={handleRollback} />
                    ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Edit Policy Modal */}
      {editingPolicy && (
        <EditPolicyModal
          policy={editingPolicy}
          onSave={handleSavePolicy}
          onClose={() => setEditingPolicy(null)}
        />
      )}
    </div>
  );
}
