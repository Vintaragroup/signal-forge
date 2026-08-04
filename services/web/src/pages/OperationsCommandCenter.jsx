import { useState, useEffect } from "react";
import { getHealthSummary } from "../api";
import HealthBadge from "../components/HealthBadge.jsx";
import WorkspaceReadinessPanel from "../components/WorkspaceReadinessPanel.jsx";
import ActivityTimelinePanel from "../components/ActivityTimelinePanel.jsx";
import DemoWorkspaceSeeder from "../components/DemoWorkspaceSeeder.jsx";
import RecoveryAssistantModal from "../components/RecoveryAssistantModal.jsx";
import ExplainabilityDrawer from "../components/ExplainabilityDrawer.jsx";

export default function OperationsCommandCenter() {
  const [health, setHealth] = useState(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState(null);
  const [workspaceSlug, setWorkspaceSlug] = useState("default");
  const [recoveryOpen, setRecoveryOpen] = useState(false);
  const [explainOpen, setExplainOpen] = useState(false);
  const [explainTarget, setExplainTarget] = useState({ type: "", id: "" });
  const [activeTab, setActiveTab] = useState("overview");

  async function loadHealth() {
    setHealthLoading(true);
    setHealthError(null);
    try {
      const data = await getHealthSummary(workspaceSlug);
      setHealth(data);
    } catch (e) {
      setHealthError(e.message || "Failed to load health summary");
    } finally {
      setHealthLoading(false);
    }
  }

  useEffect(() => {
    loadHealth();
    const id = setInterval(loadHealth, 30_000);
    return () => clearInterval(id);
  }, [workspaceSlug]);

  function openExplain(entityType, entityId) {
    setExplainTarget({ type: entityType, id: entityId });
    setExplainOpen(true);
  }

  // Health dimension display config. Most of these are system-wide
  // proxies, not per-workspace scores — the Readiness tab's checklist is
  // the only one of these panels actually scoped to a single workspace.
  // "sub" makes that scope explicit so it doesn't read as directly
  // comparable to the Readiness tab's percentage.
  const HEALTH_DIMS = [
    { key: "system_health",          label: "System",       sub: "system-wide" },
    { key: "autonomy_confidence",    label: "API Activity", sub: "requests served since restart, system-wide" },
    { key: "memory_health",          label: "Memory",       sub: `workspace: ${workspaceSlug || "system-wide"}` },
    { key: "orchestration_health",   label: "Orchestrations", sub: "system-wide" },
    { key: "worker_health",          label: "Workers",      sub: "system-wide" },
    { key: "recommendation_quality", label: "Recommendations", sub: "system-wide" },
  ];

  const INDICATOR_ORDER = ["mongodb", "workers", "recommendations", "autonomy", "memory", "orchestrations"];

  const tabs = [
    { id: "overview",   label: "Overview"    },
    { id: "readiness",  label: "Readiness"   },
    { id: "activity",   label: "Activity"    },
    { id: "demo",       label: "Demo Tools"  },
  ];

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Top bar */}
      <div className="border-b border-gray-800 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold">Operations Command Center</h1>
            <p className="text-gray-400 text-sm mt-0.5">
              System health, workspace readiness, and operator controls
            </p>
          </div>
          <div className="flex items-center gap-3">
            {health && (
              <HealthBadge
                value={health.system_health}
                label="System"
                size="lg"
              />
            )}
            <button
              onClick={() => setRecoveryOpen(true)}
              className="px-3 py-1.5 bg-yellow-800 hover:bg-yellow-700 text-yellow-200 rounded text-sm font-medium"
            >
              🔧 Recovery
            </button>
            <button
              onClick={loadHealth}
              className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-sm"
            >
              ↺ Refresh
            </button>
          </div>
        </div>

        {/* Indicator chips */}
        {health?.indicators && (
          <div className="flex flex-wrap gap-2 mt-3">
            {INDICATOR_ORDER.map((key) => {
              const val = health.indicators[key];
              if (!val) return null;
              return (
                <HealthBadge key={key} value={val} label={key} size="sm" />
              );
            })}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 px-6 py-3 border-b border-gray-800">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
              activeTab === t.id
                ? "bg-blue-700 text-white"
                : "text-gray-400 hover:text-white hover:bg-gray-800"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="p-6">
        {/* ─── Overview Tab ─────────────────────────────────────────────────── */}
        {activeTab === "overview" && (
          <div>
            {healthError && (
              <div className="bg-red-950 border border-red-800 rounded-lg p-4 mb-4 text-red-300 text-sm">
                {healthError}
                <button onClick={loadHealth} className="ml-2 text-blue-400 underline text-xs">Retry</button>
              </div>
            )}

            {/* Health dimensions grid */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
              {HEALTH_DIMS.map(({ key, label, sub }) => {
                const val = healthLoading ? null : (health?.[key] ?? 0);
                return (
                  <div
                    key={key}
                    className="bg-gray-900 border border-gray-800 rounded-lg p-4"
                  >
                    <p className="text-gray-400 text-xs uppercase tracking-wide">{label}</p>
                    {sub && <p className="text-gray-600 text-[10px] mb-2">{sub}</p>}
                    {healthLoading ? (
                      <div className="h-4 bg-gray-800 rounded animate-pulse" />
                    ) : (
                      <>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-white font-bold text-lg">{val}%</span>
                          <HealthBadge value={val} size="sm" />
                        </div>
                        <div className="w-full bg-gray-800 rounded-full h-1.5">
                          <div
                            className={`h-1.5 rounded-full ${
                              val >= 80 ? "bg-green-500" :
                              val >= 60 ? "bg-yellow-500" : "bg-red-500"
                            }`}
                            style={{ width: `${val}%` }}
                          />
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Pilot readiness banner */}
            {!healthLoading && health && (
              <div className={`rounded-lg p-4 mb-6 border flex items-center justify-between ${
                health.pilot_ready
                  ? "bg-green-950 border-green-800"
                  : "bg-yellow-950 border-yellow-800"
              }`}>
                <div>
                  <p className={`font-semibold text-sm ${health.pilot_ready ? "text-green-300" : "text-yellow-300"}`}>
                    {health.pilot_ready ? "✓ Pilot Ready" : "⚠ Pilot Not Ready"}
                  </p>
                  <p className={`text-xs mt-0.5 ${health.pilot_ready ? "text-green-400" : "text-yellow-400"}`}>
                    Readiness score: {health.pilot_readiness}%
                  </p>
                </div>
                {!health.pilot_ready && (
                  <button
                    onClick={() => setActiveTab("readiness")}
                    className="px-3 py-1.5 bg-yellow-800 hover:bg-yellow-700 text-yellow-200 text-xs rounded"
                  >
                    View Issues →
                  </button>
                )}
              </div>
            )}

            {/* Activity mini-feed */}
            <div className="h-72">
              <ActivityTimelinePanel
                workspaceSlug={workspaceSlug}
                limit={20}
              />
            </div>
          </div>
        )}

        {/* ─── Readiness Tab ─────────────────────────────────────────────────── */}
        {activeTab === "readiness" && (
          <div className="max-w-2xl">
            <div className="flex items-center gap-3 mb-4">
              <label className="text-gray-400 text-sm">Workspace:</label>
              <input
                type="text"
                value={workspaceSlug}
                onChange={(e) => setWorkspaceSlug(e.target.value)}
                className="bg-gray-800 border border-gray-700 text-white text-sm rounded px-3 py-1.5 font-mono focus:outline-none focus:border-blue-600"
                placeholder="workspace-slug"
              />
            </div>
            <WorkspaceReadinessPanel workspaceSlug={workspaceSlug} />
          </div>
        )}

        {/* ─── Activity Tab ──────────────────────────────────────────────────── */}
        {activeTab === "activity" && (
          <div className="h-[calc(100vh-14rem)]">
            <ActivityTimelinePanel
              workspaceSlug={workspaceSlug}
              limit={100}
              autoRefresh={15_000}
            />
          </div>
        )}

        {/* ─── Demo Tools Tab ────────────────────────────────────────────────── */}
        {activeTab === "demo" && (
          <div className="max-w-lg">
            <div className="bg-yellow-950 border border-yellow-800 rounded-lg p-3 mb-4">
              <p className="text-yellow-300 text-xs font-medium">⚠ Demo Mode</p>
              <p className="text-yellow-400 text-xs mt-0.5">
                Seeds synthetic data for demonstration purposes only. Do not use on production workspaces.
              </p>
            </div>
            <DemoWorkspaceSeeder
              defaultSlug="demo-workspace"
              onSeeded={() => loadHealth()}
            />
            <div className="mt-4 text-center">
              <button
                onClick={() => openExplain("recommendation", "demo-rec-1")}
                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-sm"
              >
                Try Explainability Demo
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modals */}
      <RecoveryAssistantModal
        isOpen={recoveryOpen}
        onClose={() => setRecoveryOpen(false)}
      />
      <ExplainabilityDrawer
        entityType={explainTarget.type}
        entityId={explainTarget.id}
        isOpen={explainOpen}
        onClose={() => setExplainOpen(false)}
      />
    </div>
  );
}
