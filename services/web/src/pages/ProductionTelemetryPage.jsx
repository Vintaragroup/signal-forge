import { useEffect, useState, useCallback } from "react";
import {
  getSystemHealthDetailed,
  getSystemTelemetry,
  getWorkersHealth,
  getWorkersQueueDepth,
  getSystemAuditLog,
  getSystemMetrics,
  getSystemIndexes,
  postWorkersRecoverOrphaned,
} from "../api";

// ── Badge helpers ─────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const map = {
    healthy: "bg-green-900 text-green-300",
    ok: "bg-green-900 text-green-300",
    degraded: "bg-yellow-900 text-yellow-300",
    error: "bg-red-900 text-red-300",
    partial: "bg-yellow-900 text-yellow-300",
    unknown: "bg-gray-700 text-gray-400",
  };
  const cls = map[status] || map.unknown;
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wide ${cls}`}>
      {status ?? "unknown"}
    </span>
  );
}

function MetricCard({ label, value, sub, accent }) {
  const accentMap = {
    green: "border-green-700",
    yellow: "border-yellow-700",
    red: "border-red-700",
    blue: "border-blue-700",
    gray: "border-gray-700",
  };
  const border = accentMap[accent] || accentMap.gray;
  return (
    <div className={`bg-gray-900 border ${border} rounded-lg p-4`}>
      <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">{label}</p>
      <p className="text-2xl font-bold text-white">{value ?? "—"}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ProductionTelemetryPage({ activeWorkspace }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [health, setHealth] = useState(null);
  const [telemetry, setTelemetry] = useState(null);
  const [workers, setWorkers] = useState(null);
  const [queueDepth, setQueueDepth] = useState(null);
  const [auditLog, setAuditLog] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [indexes, setIndexes] = useState(null);
  const [recovering, setRecovering] = useState(false);
  const [recoveryResult, setRecoveryResult] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [h, t, w, q, al, m, idx] = await Promise.all([
        getSystemHealthDetailed().catch(() => null),
        getSystemTelemetry().catch(() => null),
        getWorkersHealth().catch(() => null),
        getWorkersQueueDepth().catch(() => null),
        getSystemAuditLog(20).catch(() => ({ entries: [] })),
        getSystemMetrics().catch(() => null),
        getSystemIndexes().catch(() => null),
      ]);
      setHealth(h);
      setTelemetry(t);
      setWorkers(w);
      setQueueDepth(q);
      setAuditLog(al?.entries ?? []);
      setMetrics(m);
      setIndexes(idx);
      setLastRefresh(new Date().toLocaleTimeString());
    } catch (e) {
      setError(e.message || "Failed to load telemetry");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 30000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const handleRecoverOrphaned = async () => {
    setRecovering(true);
    setRecoveryResult(null);
    try {
      const result = await postWorkersRecoverOrphaned();
      setRecoveryResult(result);
      fetchAll();
    } catch {
      setRecoveryResult({ error: "Recovery failed" });
    } finally {
      setRecovering(false);
    }
  };

  // ── Derived values ───────────────────────────────────────────────────────
  const overallStatus = health?.status ?? "unknown";
  const totalReqs = telemetry?.api?.total_requests ?? 0;
  const errorRate = telemetry?.api?.error_rate != null
    ? `${(telemetry.api.error_rate * 100).toFixed(2)}%`
    : "—";
  const avgLatency = telemetry?.api?.avg_latency_ms != null
    ? `${telemetry.api.avg_latency_ms} ms`
    : "—";
  const totalWorkers = workers?.total_workers ?? 0;
  const healthyWorkers = workers?.healthy ?? 0;
  const staleWorkers = workers?.stale ?? 0;
  const queueTotal = queueDepth?.total_queue_depth ?? 0;
  const dbHealthy = telemetry?.database?.healthy;

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Production Telemetry</h1>
          <p className="text-sm text-gray-400 mt-1">
            Real-time system health, API metrics, and worker monitoring
            {lastRefresh && <span className="ml-2 text-gray-500">— Last updated {lastRefresh}</span>}
          </p>
        </div>
        <button
          onClick={fetchAll}
          disabled={loading}
          className="px-4 py-2 bg-blue-700 hover:bg-blue-600 text-sm rounded-lg font-medium disabled:opacity-50"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-950 border border-red-700 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Overall system status banner */}
      <div className={`mb-6 p-4 rounded-lg border flex items-center gap-3 ${
        overallStatus === "healthy"
          ? "bg-green-950 border-green-700"
          : overallStatus === "degraded"
          ? "bg-yellow-950 border-yellow-700"
          : "bg-gray-900 border-gray-700"
      }`}>
        <StatusBadge status={overallStatus} />
        <span className="font-medium">System Status</span>
        <span className="text-sm text-gray-400 ml-2">
          Env: {health?.environment ?? "—"} · Version: {health?.version ?? "—"}
        </span>
      </div>

      {/* Top metric cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <MetricCard
          label="Database"
          value={dbHealthy === true ? "Online" : dbHealthy === false ? "Offline" : "—"}
          accent={dbHealthy === true ? "green" : dbHealthy === false ? "red" : "gray"}
        />
        <MetricCard
          label="Total Requests"
          value={totalReqs.toLocaleString()}
          sub="Since last reset"
          accent="blue"
        />
        <MetricCard
          label="Error Rate"
          value={errorRate}
          accent={telemetry?.api?.error_rate > 0.05 ? "red" : "green"}
        />
        <MetricCard
          label="Avg Latency"
          value={avgLatency}
          accent={telemetry?.api?.avg_latency_ms > 500 ? "yellow" : "green"}
        />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <MetricCard
          label="Total Workers"
          value={totalWorkers}
          accent="gray"
        />
        <MetricCard
          label="Healthy Workers"
          value={healthyWorkers}
          accent="green"
        />
        <MetricCard
          label="Stale Workers"
          value={staleWorkers}
          accent={staleWorkers > 0 ? "yellow" : "green"}
        />
        <MetricCard
          label="Queue Depth"
          value={queueTotal}
          sub="Across all workers"
          accent={queueTotal > 50 ? "red" : queueTotal > 10 ? "yellow" : "green"}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Component health table */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h2 className="text-base font-semibold mb-3">Component Health</h2>
          {health?.components ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-400 text-xs uppercase tracking-wide">
                  <th className="text-left pb-2">Component</th>
                  <th className="text-left pb-2">Status</th>
                  <th className="text-left pb-2">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {Object.entries(health.components).map(([name, info]) => (
                  <tr key={name} className="py-2">
                    <td className="py-2 font-medium capitalize">{name.replace("_", " ")}</td>
                    <td className="py-2">
                      <StatusBadge status={info.status ?? (info.enabled ? "ok" : "disabled")} />
                    </td>
                    <td className="py-2 text-gray-400 text-xs">
                      {info.error
                        ? info.error
                        : info.healthy != null
                        ? `${info.healthy} healthy, ${info.stale ?? 0} stale`
                        : info.enabled != null
                        ? (info.enabled ? "Enabled" : "Disabled")
                        : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-gray-500 text-sm">No component data</p>
          )}
        </div>

        {/* MongoDB index status */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-base font-semibold">MongoDB Indexes</h2>
            {indexes?.status && <StatusBadge status={indexes.status} />}
          </div>
          {indexes?.collections ? (
            <div className="space-y-1 max-h-56 overflow-y-auto">
              {Object.entries(indexes.collections).map(([col, info]) => (
                <div key={col} className="flex items-center justify-between py-1 border-b border-gray-800">
                  <span className="text-sm font-mono text-gray-300">{col}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500">{info.indexes ?? 0} indexes</span>
                    <StatusBadge status={info.status} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-sm">No index data</p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Top endpoints */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h2 className="text-base font-semibold mb-3">Top Endpoints</h2>
          {metrics?.top_endpoints?.length > 0 ? (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {metrics.top_endpoints.map((ep) => (
                <div key={ep.endpoint} className="flex items-center justify-between text-sm py-1 border-b border-gray-800">
                  <span className="font-mono text-xs text-gray-300 truncate max-w-[55%]">{ep.endpoint}</span>
                  <div className="flex items-center gap-3 text-xs">
                    <span className="text-gray-400">{ep.count} req</span>
                    <span className="text-blue-400">{ep.avg_latency_ms} ms</span>
                    {ep.errors > 0 && (
                      <span className="text-red-400">{ep.errors} err</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-sm">No request data yet</p>
          )}
        </div>

        {/* Worker registry */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-base font-semibold">Worker Registry</h2>
            <button
              onClick={handleRecoverOrphaned}
              disabled={recovering}
              className="text-xs px-3 py-1 bg-yellow-900 hover:bg-yellow-800 text-yellow-300 rounded font-medium disabled:opacity-50"
            >
              {recovering ? "Recovering…" : "Recover Orphaned"}
            </button>
          </div>
          {recoveryResult && (
            <div className="mb-2 p-2 bg-gray-800 rounded text-xs text-gray-300">
              Recovered: {recoveryResult.recovery?.recovered_tasks ?? 0} tasks
              {" · "}Stuck orchestrations: {recoveryResult.stuck_count ?? 0}
            </div>
          )}
          {workers?.registry?.length > 0 ? (
            <div className="space-y-2 max-h-56 overflow-y-auto">
              {workers.registry.map((w) => (
                <div key={w.worker_id} className="bg-gray-800 rounded p-2 text-xs">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-gray-200">{w.worker_id}</span>
                    <StatusBadge status={w.status === "running" ? "ok" : w.status} />
                  </div>
                  <div className="flex gap-4 text-gray-400">
                    <span>Processed: {w.tasks_processed}</span>
                    <span>Failed: {w.tasks_failed}</span>
                    <span>Queue: {w.queue_depth}</span>
                  </div>
                  <div className="text-gray-500 mt-0.5">Last seen: {w.last_seen?.slice(0, 19).replace("T", " ")}</div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-sm">No active workers registered</p>
          )}
        </div>
      </div>

      {/* Audit log */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <h2 className="text-base font-semibold mb-3">
          Audit Log
          <span className="ml-2 text-xs text-gray-400 font-normal">(last 20 events)</span>
        </h2>
        {auditLog.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-400 text-xs uppercase tracking-wide border-b border-gray-800">
                  <th className="text-left pb-2 pr-4">Time</th>
                  <th className="text-left pb-2 pr-4">Actor</th>
                  <th className="text-left pb-2 pr-4">Action</th>
                  <th className="text-left pb-2">Resource</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {[...auditLog].reverse().map((entry, i) => (
                  <tr key={i} className="text-xs">
                    <td className="py-1.5 pr-4 text-gray-500 font-mono whitespace-nowrap">
                      {entry.ts?.slice(0, 19).replace("T", " ")}
                    </td>
                    <td className="py-1.5 pr-4 text-gray-300">{entry.actor}</td>
                    <td className="py-1.5 pr-4 text-blue-400">{entry.action}</td>
                    <td className="py-1.5 text-gray-400">{entry.resource}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-gray-500 text-sm">No audit events recorded yet</p>
        )}
      </div>
    </div>
  );
}
