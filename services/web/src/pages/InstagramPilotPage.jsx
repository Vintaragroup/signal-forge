import { useState, useEffect } from "react";
import InstagramConnectionPanel from "../components/InstagramConnectionPanel";
import InstagramPublishPanel    from "../components/InstagramPublishPanel";
import ExternalExecutionsList   from "../components/ExternalExecutionsList";
import TelemetryCard            from "../components/TelemetryCard";
import ChannelHealthCard        from "../components/ChannelHealthCard";
import { getDistributionTelemetry } from "../api";
import { safeRate, formatRate } from "../utils/telemetry";

/**
 * InstagramPilotPage.jsx
 *
 * Full Instagram pilot experience, mirroring LinkedInPilotPage.jsx:
 *   - Connection status + OAuth
 *   - Publish panel (approved render -> caption + public media URL -> post)
 *   - Distribution attempts list (shared, provider-agnostic — shows LinkedIn
 *     and Instagram attempts together)
 *   - Telemetry dashboard (shared /distribution/telemetry, both channels)
 */
export default function InstagramPilotPage({ workspaceSlug = "default" }) {
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

  const igStats = telemetry?.channels?.instagram;
  const igSuccessRate = safeRate(igStats?.verified, igStats?.total);
  const successRateLabel = formatRate(igSuccessRate);

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6 space-y-8">
      {/* ── Page header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Instagram Pilot</h1>
          <p className="text-gray-500 text-sm mt-0.5">
            Live external workflow execution — Pillar 2
          </p>
        </div>
        <button
          onClick={refresh}
          className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-sm"
        >
          ↺ Refresh All
        </button>
      </div>

      {/* ── Telemetry row (Instagram channel only) ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <TelemetryCard
          label="Success Rate"
          value={successRateLabel}
          sub="verified / total"
          color={
            igSuccessRate == null
              ? "text-gray-500"
              : igSuccessRate >= 0.9
                ? "text-green-400"
                : igSuccessRate >= 0.7
                  ? "text-yellow-400"
                  : "text-red-400"
          }
        />
        <TelemetryCard
          label="Verified"
          value={telemetryLoading ? "…" : (igStats?.verified ?? 0)}
          sub="posts confirmed live"
          color="text-green-400"
        />
        <TelemetryCard
          label="Failed"
          value={telemetryLoading ? "…" : (igStats?.failed ?? 0)}
          sub="need attention"
          color={(igStats?.failed ?? 0) > 0 ? "text-red-400" : "text-gray-400"}
        />
        <TelemetryCard
          label="Retrying"
          value={telemetryLoading ? "…" : (igStats?.retrying ?? 0)}
          sub="in backoff"
          color={(igStats?.retrying ?? 0) > 0 ? "text-orange-400" : "text-gray-400"}
        />
      </div>

      {/* ── Two-column main area ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: connection + publish */}
        <div className="space-y-6">
          <InstagramConnectionPanel
            workspaceSlug={workspaceSlug}
            onConnected={refresh}
          />
          <InstagramPublishPanel
            workspaceSlug={workspaceSlug}
          />
        </div>

        {/* Right: telemetry detail + channels (all distribution channels, same as LinkedIn Pilot) */}
        <div className="space-y-6">
          <ChannelHealthCard
            telemetry={telemetry}
            footerLabel="Instagram verification failures"
            footerValue={igStats?.failed ?? 0}
          />
        </div>
      </div>

      {/* ── Executions list (shared across all channels) ── */}
      <ExternalExecutionsList
        key={refreshKey}
        workspaceSlug={workspaceSlug}
        limit={25}
        onRetried={refresh}
      />
    </div>
  );
}
