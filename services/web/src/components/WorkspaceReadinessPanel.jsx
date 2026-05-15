import { useState, useEffect } from "react";
import { getWorkspaceReadiness } from "../api";
import HealthBadge from "./HealthBadge.jsx";

/**
 * WorkspaceReadinessPanel.jsx
 *
 * Displays the readiness score for a given workspace slug, with per-check
 * status rows and inline remediation guidance.
 *
 * Props:
 *   workspaceSlug   — string workspace slug to evaluate
 *   autoLoad        — auto-fetch on mount (default true)
 */
export default function WorkspaceReadinessPanel({ workspaceSlug, autoLoad = true }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function load() {
    if (!workspaceSlug) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getWorkspaceReadiness(workspaceSlug);
      setData(result);
    } catch (e) {
      setError(e.message || "Failed to load readiness");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { if (autoLoad) load(); }, [workspaceSlug]);

  const SEVERITY_COLOR = {
    high:   "text-red-400",
    medium: "text-yellow-400",
    low:    "text-blue-400",
  };

  if (!workspaceSlug) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 text-center text-gray-500 text-sm">
        Select a workspace to view readiness.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-4" />
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-3 bg-gray-800 rounded mb-2" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-900 border border-red-800 rounded-lg p-6">
        <p className="text-red-400 text-sm">{error}</p>
        <button
          onClick={load}
          className="mt-3 px-3 py-1 bg-gray-800 text-gray-300 rounded text-xs hover:bg-gray-700"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data) return null;

  const checkLabels = {
    client_memory_initialized:   "Client Memory",
    orchestration_healthy:       "Orchestrations Healthy",
    autonomy_configured:         "Autonomy Configured",
    workflows_active:            "Workflows Active",
    workers_healthy:             "Workers Healthy",
    recommendations_not_blocked: "Recommendations Not Blocked",
    sources_connected:           "Sources Connected",
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-white font-semibold text-sm">Workspace Readiness</h3>
          <p className="text-gray-500 text-xs mt-0.5">{workspaceSlug}</p>
        </div>
        <div className="flex items-center gap-2">
          <HealthBadge value={data.score} size="lg" />
          <span className={`text-xs font-semibold ${data.ready ? "text-green-400" : "text-red-400"}`}>
            {data.ready ? "READY" : "NOT READY"}
          </span>
        </div>
      </div>

      {/* Score bar */}
      <div className="w-full bg-gray-800 rounded-full h-2 mb-5">
        <div
          className={`h-2 rounded-full transition-all ${
            data.score >= 80 ? "bg-green-500" :
            data.score >= 60 ? "bg-yellow-500" : "bg-red-500"
          }`}
          style={{ width: `${data.score}%` }}
        />
      </div>

      {/* Checks */}
      <div className="space-y-2">
        {Object.entries(data.checks || {}).map(([key, passed]) => {
          const rem = data.remediation?.[key];
          return (
            <div key={key} className="flex items-start gap-3">
              <span className={`mt-0.5 text-xs ${passed ? "text-green-400" : "text-red-400"}`}>
                {passed ? "✓" : "✗"}
              </span>
              <div className="flex-1 min-w-0">
                <p className={`text-xs font-medium ${passed ? "text-gray-300" : "text-gray-400"}`}>
                  {checkLabels[key] || key}
                </p>
                {!passed && rem && (
                  <div className="mt-1">
                    <p className={`text-xs ${SEVERITY_COLOR[rem.severity] || "text-gray-400"}`}>
                      {rem.message}
                    </p>
                    <code className="text-xs text-blue-400 font-mono">{rem.action}</code>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-xs text-gray-600 mt-4">
        Evaluated {data.evaluated_at ? new Date(data.evaluated_at).toLocaleTimeString() : "—"}
        <button onClick={load} className="ml-3 text-blue-500 hover:text-blue-400">Refresh</button>
      </p>
    </div>
  );
}
