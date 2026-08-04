import { useState, useEffect } from "react";
import LinkedInConnectionPanel from "../components/LinkedInConnectionPanel";
import LinkedInPublishPanel    from "../components/LinkedInPublishPanel";
import ExternalExecutionsList  from "../components/ExternalExecutionsList";
import TelemetryCard           from "../components/TelemetryCard";
import ChannelHealthCard       from "../components/ChannelHealthCard";
import { getDistributionTelemetry } from "../api";
import { formatRate } from "../utils/telemetry";

/**
 * LinkedInPilotPage.jsx
 *
 * Full LinkedIn pilot experience:
 *   - Connection status + OAuth
 *   - Publish panel
 *   - Distribution attempts list
 *   - Telemetry dashboard
 */
export default function LinkedInPilotPage({ workspaceSlug = "default" }) {
  const [telemetry, setTelemetry]         = useState(null);
  const [telemetryLoading, setTLLoading]  = useState(true);
  const [refreshKey, setRefreshKey]       = useState(0);

  async function loadTelemetry() {
    setTLLoading(true);
    try {
      const data = await getDistributionTelemetry(workspaceSlug);
      setTelemetry(data);
    } catch {
      // non-fatal
    } finally {
      setTLLoading(false);
    }
  }

  useEffect(() => { loadTelemetry(); }, [workspaceSlug, refreshKey]);

  function refresh() {
    setRefreshKey(k => k + 1);
  }

  const successRate = telemetry ? formatRate(telemetry.publish_success_rate) : "—";

  const totals = telemetry?.totals ?? {};

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6 space-y-8">
      {/* ── Page header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">LinkedIn Pilot</h1>
          <p className="text-gray-500 text-sm mt-0.5">
            Live external workflow execution — Phase 6X
          </p>
        </div>
        <button
          onClick={refresh}
          className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-sm"
        >
          ↺ Refresh All
        </button>
      </div>

      {/* ── Telemetry row ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <TelemetryCard
          label="Success Rate"
          value={successRate}
          sub="verified / total"
          color={
            !Number.isFinite(telemetry?.publish_success_rate)
              ? "text-gray-500"
              : telemetry.publish_success_rate >= 0.9
                ? "text-green-400"
                : telemetry.publish_success_rate >= 0.7
                  ? "text-yellow-400"
                  : "text-red-400"
          }
        />
        <TelemetryCard
          label="Verified"
          value={telemetryLoading ? "…" : (totals.verified ?? 0)}
          sub="posts confirmed live"
          color="text-green-400"
        />
        <TelemetryCard
          label="Failed"
          value={telemetryLoading ? "…" : (totals.failed ?? 0)}
          sub="need attention"
          color={(totals.failed ?? 0) > 0 ? "text-red-400" : "text-gray-400"}
        />
        <TelemetryCard
          label="Escalated"
          value={telemetryLoading ? "…" : (totals.escalated ?? 0)}
          sub="retry limit reached"
          color={(totals.escalated ?? 0) > 0 ? "text-orange-400" : "text-gray-400"}
        />
      </div>

      {/* ── Two-column main area ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: connection + publish */}
        <div className="space-y-6">
          <LinkedInConnectionPanel
            workspaceSlug={workspaceSlug}
            onConnected={refresh}
          />
          <LinkedInPublishPanel
            workspaceSlug={workspaceSlug}
          />
        </div>

        {/* Right: telemetry detail + channels */}
        <div className="space-y-6">
          <ChannelHealthCard
            telemetry={telemetry}
            footerLabel="Verification failures"
            footerValue={totals.failed ?? 0}
          />
        </div>
      </div>

      {/* ── Executions list ── */}
      <ExternalExecutionsList
        key={refreshKey}
        workspaceSlug={workspaceSlug}
        limit={25}
        onRetried={refresh}
      />
    </div>
  );
}
