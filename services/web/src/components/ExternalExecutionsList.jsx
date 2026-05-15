import { useState, useEffect } from "react";
import {
  getExternalExecutions,
  getExternalExecutionDetail,
  postLinkedInRetry,
} from "../api";

const STATUS_BADGE = {
  pending:   "bg-yellow-900 text-yellow-300 border-yellow-700",
  verified:  "bg-green-900  text-green-300  border-green-700",
  failed:    "bg-red-900    text-red-300    border-red-700",
  retrying:  "bg-blue-900   text-blue-300   border-blue-700",
  escalated: "bg-orange-900 text-orange-300 border-orange-700",
};

function StatusBadge({ status }) {
  return (
    <span className={`px-1.5 py-0.5 rounded text-xs font-semibold uppercase border ${
      STATUS_BADGE[status] ?? "bg-gray-800 text-gray-400 border-gray-700"
    }`}>
      {status}
    </span>
  );
}

/**
 * ExternalExecutionsList.jsx
 *
 * Table of distribution_attempts with status badges, post links, retry buttons.
 *
 * Props:
 *   workspaceSlug  — workspace to fetch
 *   limit          — max rows to show (default 25)
 *   onRetried      — optional callback() when a retry is triggered
 */
export default function ExternalExecutionsList({
  workspaceSlug = "default",
  limit = 25,
  onRetried,
}) {
  const [executions, setExecutions] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [retrying, setRetrying]     = useState({});  // { attempt_id: true }
  const [expanded, setExpanded]     = useState(null);
  const [detail, setDetail]         = useState(null);
  const [detailLoading, setDL]      = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await getExternalExecutions(workspaceSlug, limit);
      setExecutions(data.executions ?? []);
    } catch (e) {
      setError(e.message || "Failed to load executions");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [workspaceSlug, limit]);

  async function handleRetry(attemptId) {
    setRetrying(prev => ({ ...prev, [attemptId]: true }));
    try {
      await postLinkedInRetry(attemptId, { workspace_slug: workspaceSlug });
      await load();
      onRetried?.();
    } catch (e) {
      setError(e.message || "Retry failed");
    } finally {
      setRetrying(prev => ({ ...prev, [attemptId]: false }));
    }
  }

  async function handleExpand(attemptId) {
    if (expanded === attemptId) {
      setExpanded(null);
      setDetail(null);
      return;
    }
    setExpanded(attemptId);
    setDL(true);
    try {
      const d = await getExternalExecutionDetail(attemptId);
      setDetail(d);
    } catch (e) {
      setDetail({ error: e.message });
    } finally {
      setDL(false);
    }
  }

  if (loading) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/4 mb-3" />
        <div className="space-y-2">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-8 bg-gray-800 rounded" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-white font-semibold text-sm">Distribution Attempts</h3>
        <button
          onClick={load}
          className="px-3 py-1 bg-gray-800 hover:bg-gray-700 text-gray-400 rounded text-xs"
        >
          ↺ Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-950 border border-red-800 rounded p-2 mb-4 text-red-300 text-xs">
          {error}
        </div>
      )}

      {executions.length === 0 ? (
        <p className="text-gray-500 text-sm text-center py-8">No distribution attempts yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 border-b border-gray-800">
                <th className="text-left pb-2 pr-4 font-medium">Attempt ID</th>
                <th className="text-left pb-2 pr-4 font-medium">Asset</th>
                <th className="text-left pb-2 pr-4 font-medium">Status</th>
                <th className="text-left pb-2 pr-4 font-medium">Retries</th>
                <th className="text-left pb-2 pr-4 font-medium">Post URL</th>
                <th className="text-left pb-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {executions.map(ex => (
                <>
                  <tr
                    key={ex.distribution_attempt_id}
                    className="hover:bg-gray-800 cursor-pointer"
                    onClick={() => handleExpand(ex.distribution_attempt_id)}
                  >
                    <td className="py-2 pr-4 font-mono text-gray-300">
                      {ex.distribution_attempt_id}
                    </td>
                    <td className="py-2 pr-4 text-gray-400 truncate max-w-[140px]">
                      {ex.workflow_asset_id}
                    </td>
                    <td className="py-2 pr-4">
                      <StatusBadge status={ex.status} />
                    </td>
                    <td className="py-2 pr-4 text-gray-400 text-center">
                      {ex.retry_count ?? 0}
                    </td>
                    <td className="py-2 pr-4">
                      {ex.published_url ? (
                        <a
                          href={ex.published_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-400 hover:underline truncate block max-w-[160px]"
                          onClick={e => e.stopPropagation()}
                        >
                          View post ↗
                        </a>
                      ) : (
                        <span className="text-gray-600">—</span>
                      )}
                    </td>
                    <td className="py-2">
                      {["failed", "retrying"].includes(ex.status) && (
                        <button
                          onClick={e => {
                            e.stopPropagation();
                            handleRetry(ex.distribution_attempt_id);
                          }}
                          disabled={retrying[ex.distribution_attempt_id]}
                          className={`px-2 py-0.5 rounded text-xs ${
                            retrying[ex.distribution_attempt_id]
                              ? "bg-gray-700 text-gray-500 cursor-not-allowed"
                              : "bg-orange-900 hover:bg-orange-800 text-orange-300"
                          }`}
                        >
                          {retrying[ex.distribution_attempt_id] ? "…" : "Retry"}
                        </button>
                      )}
                    </td>
                  </tr>

                  {/* Expanded detail row */}
                  {expanded === ex.distribution_attempt_id && (
                    <tr key={`${ex.distribution_attempt_id}-detail`}>
                      <td colSpan={6} className="px-0 pb-2">
                        <div className="bg-gray-950 border border-gray-800 rounded p-3 mx-0 text-xs text-gray-400">
                          {detailLoading ? (
                            <p>Loading detail…</p>
                          ) : detail?.error ? (
                            <p className="text-red-400">{detail.error}</p>
                          ) : detail ? (
                            <pre className="whitespace-pre-wrap font-mono text-[11px] text-gray-300">
                              {JSON.stringify(detail, null, 2)}
                            </pre>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
