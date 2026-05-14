import { useEffect, useState, useCallback } from "react";
import { api } from "../api";

// ── Status / priority badge helpers ──────────────────────────────────────────

const STATUS_COLORS = {
  running: "bg-blue-100 text-blue-800",
  paused: "bg-yellow-100 text-yellow-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  escalated: "bg-orange-100 text-orange-800",
  pending: "bg-gray-100 text-gray-700",
};

const PRIORITY_COLORS = {
  critical: "bg-red-100 text-red-800",
  high: "bg-orange-100 text-orange-800",
  normal: "bg-blue-100 text-blue-700",
  background: "bg-gray-100 text-gray-600",
};

const NODE_STATUS_COLORS = {
  running: "text-blue-600",
  completed: "text-green-600",
  failed: "text-red-600",
  escalated: "text-orange-600",
  retrying: "text-yellow-600",
  pending: "text-gray-500",
  ready: "text-indigo-600",
  blocked: "text-gray-400",
};

function Badge({ label, colorClass }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${colorClass}`}>
      {label}
    </span>
  );
}

function MetricCard({ title, value, sub }) {
  return (
    <div className="bg-white rounded-lg shadow p-4 flex flex-col gap-1">
      <p className="text-xs text-gray-500 uppercase tracking-wide">{title}</p>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-400">{sub}</p>}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function OrchestrationDashboardPage({ activeWorkspace }) {
  const ws = activeWorkspace || "";

  const [orchestrations, setOrchestrations] = useState([]);
  const [telemetry, setTelemetry] = useState(null);
  const [agentProfiles, setAgentProfiles] = useState([]);
  const [agentUtilization, setAgentUtilization] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionStatus, setActionStatus] = useState({});
  const [expandedProfiles, setExpandedProfiles] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [orchRes, telRes, profilesRes, utilRes] = await Promise.all([
        api.listOrchestrations(ws, "", "", 100),
        api.getOrchestrationGlobalTelemetry(ws, 30),
        api.listAgentProfiles(),
        api.getAgentUtilization(ws, 30),
      ]);
      setOrchestrations(orchRes.items || []);
      setTelemetry(telRes);
      setAgentProfiles(profilesRes.profiles || []);
      setAgentUtilization(utilRes.agents || []);
    } catch (e) {
      setError("Failed to load orchestration data. Is the API reachable?");
    } finally {
      setLoading(false);
    }
  }, [ws]);

  useEffect(() => { load(); }, [load]);

  // ── Actions ────────────────────────────────────────────────────────────────

  async function handlePause(orchId) {
    setActionStatus((p) => ({ ...p, [orchId]: "pausing..." }));
    try {
      await api.pauseOrchestration(orchId);
      setActionStatus((p) => ({ ...p, [orchId]: "paused" }));
      load();
    } catch {
      setActionStatus((p) => ({ ...p, [orchId]: "error" }));
    }
  }

  async function handleResume(orchId) {
    setActionStatus((p) => ({ ...p, [orchId]: "resuming..." }));
    try {
      await api.resumeOrchestration(orchId);
      setActionStatus((p) => ({ ...p, [orchId]: "resumed" }));
      load();
    } catch {
      setActionStatus((p) => ({ ...p, [orchId]: "error" }));
    }
  }

  async function handleEscalate(orchId) {
    if (!window.confirm("Escalate this orchestration to operator review?")) return;
    setActionStatus((p) => ({ ...p, [orchId]: "escalating..." }));
    try {
      await api.escalateOrchestration(orchId, { reason: "Manual operator escalation" });
      setActionStatus((p) => ({ ...p, [orchId]: "escalated" }));
      load();
    } catch {
      setActionStatus((p) => ({ ...p, [orchId]: "error" }));
    }
  }

  // ── Derived data ───────────────────────────────────────────────────────────

  const failedNodes = orchestrations.flatMap((o) =>
    (o.nodes || [])
      .filter((n) => ["failed", "retrying", "escalated"].includes(n.status))
      .map((n) => ({ ...n, orchestration_id: o.orchestration_id, workspace_slug: o.workspace_slug }))
  );

  const escalationQueue = orchestrations.filter(
    (o) => o.status === "escalated" || o.escalation_status === "pending_operator_review"
  );

  // ── Render ─────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        Loading orchestration data…
      </div>
    );
  }

  const t = telemetry || {};
  const completionPct = t.completion_rate != null ? `${(t.completion_rate * 100).toFixed(1)}%` : "—";
  const agentsActive = agentUtilization.filter((a) => a.running_nodes > 0).length;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Orchestration Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">
            Multi-agent workflow coordination {ws && `· workspace: ${ws}`}
          </p>
        </div>
        <button
          onClick={load}
          className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 text-sm">
          {error}
        </div>
      )}

      {/* Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <MetricCard title="Total Orchestrations" value={t.total_orchestrations ?? 0} />
        <MetricCard title="Running" value={t.running ?? 0} sub="active pipelines" />
        <MetricCard title="Escalated" value={t.escalated ?? 0} sub="need operator action" />
        <MetricCard title="Agents Active" value={agentsActive} sub={`of ${agentUtilization.length} agents`} />
        <MetricCard title="Total Retries" value={t.total_retries ?? 0} sub={`${t.retry_frequency ?? 0} per orch`} />
        <MetricCard title="Completion Rate" value={completionPct} sub={`${t.completed ?? 0} completed`} />
      </div>

      {/* Active Orchestrations Table */}
      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-3">Active Orchestrations</h2>
        {orchestrations.length === 0 ? (
          <p className="text-sm text-gray-400 italic">No orchestrations found.</p>
        ) : (
          <div className="bg-white shadow rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 uppercase text-xs">
                <tr>
                  <th className="px-4 py-3 text-left">ID</th>
                  <th className="px-4 py-3 text-left">Workspace</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3 text-left">Priority</th>
                  <th className="px-4 py-3 text-center">Nodes</th>
                  <th className="px-4 py-3 text-center">Retries</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {orchestrations.map((o) => {
                  const totalNodes = (o.nodes || []).length;
                  const doneNodes = (o.nodes || []).filter((n) => n.status === "completed").length;
                  const inProgress = actionStatus[o.orchestration_id];
                  return (
                    <tr key={o.orchestration_id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-600">{o.orchestration_id}</td>
                      <td className="px-4 py-3 text-gray-700">{o.workspace_slug || "—"}</td>
                      <td className="px-4 py-3">
                        <Badge
                          label={o.status}
                          colorClass={STATUS_COLORS[o.status] || "bg-gray-100 text-gray-600"}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <Badge
                          label={o.priority || "normal"}
                          colorClass={PRIORITY_COLORS[o.priority] || PRIORITY_COLORS.normal}
                        />
                      </td>
                      <td className="px-4 py-3 text-center text-gray-600">
                        {doneNodes}/{totalNodes}
                      </td>
                      <td className="px-4 py-3 text-center text-gray-600">{o.retry_total ?? 0}</td>
                      <td className="px-4 py-3 text-right space-x-2">
                        {inProgress && (
                          <span className="text-xs text-gray-400 mr-2">{inProgress}</span>
                        )}
                        {o.status === "running" && (
                          <button
                            onClick={() => handlePause(o.orchestration_id)}
                            className="text-xs px-2 py-1 bg-yellow-100 text-yellow-800 rounded hover:bg-yellow-200 transition"
                          >
                            Pause
                          </button>
                        )}
                        {o.status === "paused" && (
                          <button
                            onClick={() => handleResume(o.orchestration_id)}
                            className="text-xs px-2 py-1 bg-green-100 text-green-800 rounded hover:bg-green-200 transition"
                          >
                            Resume
                          </button>
                        )}
                        {!["escalated", "completed"].includes(o.status) && (
                          <button
                            onClick={() => handleEscalate(o.orchestration_id)}
                            className="text-xs px-2 py-1 bg-orange-100 text-orange-800 rounded hover:bg-orange-200 transition"
                          >
                            Escalate
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Agent Utilization */}
      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-3">Agent Utilization</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {agentUtilization.map((agent) => {
            const pct = Math.min(100, Math.round((agent.utilization_rate || 0) * 100));
            return (
              <div key={agent.agent_name} className="bg-white rounded-lg shadow p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-gray-800 capitalize">
                    {agent.agent_name.replace(/_/g, " ")}
                  </p>
                  <span className="text-xs text-gray-400">
                    {agent.running_nodes}/{agent.max_concurrency} running
                  </span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${pct > 80 ? "bg-red-400" : pct > 50 ? "bg-yellow-400" : "bg-green-400"}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="flex justify-between text-xs text-gray-500">
                  <span>Utilization: {pct}%</span>
                  <span>Success: {((agent.success_rate || 0) * 100).toFixed(0)}%</span>
                </div>
                {agent.specializations?.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {agent.specializations.slice(0, 3).map((s) => (
                      <span key={s} className="bg-indigo-50 text-indigo-600 text-xs px-1.5 py-0.5 rounded">
                        {s.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Failed / Retrying Nodes */}
      {failedNodes.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-gray-800 mb-3">
            Failed / Retrying Nodes
            <span className="ml-2 text-sm font-normal text-red-500">({failedNodes.length})</span>
          </h2>
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 uppercase text-xs">
                <tr>
                  <th className="px-4 py-2 text-left">Orch ID</th>
                  <th className="px-4 py-2 text-left">Node ID</th>
                  <th className="px-4 py-2 text-left">Agent</th>
                  <th className="px-4 py-2 text-left">Status</th>
                  <th className="px-4 py-2 text-left">Reason</th>
                  <th className="px-4 py-2 text-center">Retries</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {failedNodes.map((n) => (
                  <tr key={`${n.orchestration_id}-${n.node_id}`} className="hover:bg-gray-50">
                    <td className="px-4 py-2 font-mono text-xs text-gray-500">{n.orchestration_id}</td>
                    <td className="px-4 py-2 font-mono text-xs text-gray-500">{n.node_id}</td>
                    <td className="px-4 py-2 capitalize text-gray-700">{(n.agent_name || "—").replace(/_/g, " ")}</td>
                    <td className="px-4 py-2">
                      <span className={`font-medium ${NODE_STATUS_COLORS[n.status] || "text-gray-600"}`}>
                        {n.status}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-gray-500 text-xs max-w-xs truncate">
                      {n.failure_reason || "—"}
                    </td>
                    <td className="px-4 py-2 text-center text-gray-600">{n.retry_count ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Escalation Queue */}
      {escalationQueue.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-gray-800 mb-3">
            Escalation Queue
            <span className="ml-2 text-sm font-normal text-orange-500">
              ({escalationQueue.length} pending review)
            </span>
          </h2>
          <div className="space-y-3">
            {escalationQueue.map((o) => (
              <div
                key={o.orchestration_id}
                className="bg-orange-50 border border-orange-200 rounded-lg p-4 flex items-start justify-between"
              >
                <div>
                  <p className="font-mono text-sm text-gray-700">{o.orchestration_id}</p>
                  <p className="text-xs text-gray-500 mt-1">
                    Workspace: {o.workspace_slug || "—"} ·{" "}
                    {o.failure_reason ? `Reason: ${o.failure_reason}` : "No failure reason recorded"}
                  </p>
                </div>
                <Badge label="pending review" colorClass="bg-orange-100 text-orange-800" />
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Agent Profiles (expandable) */}
      <section>
        <button
          onClick={() => setExpandedProfiles((v) => !v)}
          className="flex items-center gap-2 text-lg font-semibold text-gray-800 hover:text-indigo-600 transition"
        >
          <span>{expandedProfiles ? "▾" : "▸"}</span>
          Agent Profiles
          <span className="text-sm font-normal text-gray-400">({agentProfiles.length} agents)</span>
        </button>
        {expandedProfiles && (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {agentProfiles.map((p) => (
              <div key={p.agent_name} className="bg-white rounded-lg shadow p-4 space-y-2">
                <p className="font-semibold text-gray-800 capitalize">
                  {p.agent_name.replace(/_/g, " ")}
                </p>
                <div className="text-xs text-gray-500 space-y-1">
                  <div className="flex justify-between">
                    <span>Success rate</span>
                    <span className="font-medium text-gray-700">
                      {((p.success_rate || 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Avg execution</span>
                    <span className="font-medium text-gray-700">
                      {(p.avg_execution_time || 0).toFixed(1)}s
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Max concurrency</span>
                    <span className="font-medium text-gray-700">{p.max_concurrency}</span>
                  </div>
                </div>
                {p.specializations?.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {p.specializations.map((s) => (
                      <span key={s} className="bg-gray-100 text-gray-600 text-xs px-1.5 py-0.5 rounded">
                        {s.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
