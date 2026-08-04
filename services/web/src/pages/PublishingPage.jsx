import { useState, useEffect } from "react";
import LinkedInConnectionPanel  from "../components/LinkedInConnectionPanel";
import LinkedInPublishPanel     from "../components/LinkedInPublishPanel";
import InstagramConnectionPanel from "../components/InstagramConnectionPanel";
import InstagramPublishPanel    from "../components/InstagramPublishPanel";
import ExternalExecutionsList   from "../components/ExternalExecutionsList";
import TelemetryCard            from "../components/TelemetryCard";
import ChannelHealthCard        from "../components/ChannelHealthCard";
import { getDistributionTelemetry } from "../api";
import { safeRate, formatRate } from "../utils/telemetry";

const PLATFORMS = [
  { id: "linkedin",  label: "LinkedIn",  activeClass: "bg-blue-700 text-white" },
  { id: "instagram", label: "Instagram", activeClass: "bg-pink-700 text-white" },
];

/**
 * PublishingPage.jsx
 *
 * Merged replacement for the former LinkedInPilotPage.jsx / InstagramPilotPage.jsx —
 * the two were ~90% identical (same telemetry source, same Channel Health widget,
 * same executions list) and had already drifted once (the NaN% bug). A platform
 * switcher keeps each platform's distinct connect/publish forms and telemetry
 * semantics while sharing everything else.
 */
export default function PublishingPage({ workspaceSlug = "default" }) {
  const [platform, setPlatform]           = useState("linkedin");
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

  const totals = telemetry?.totals ?? {};
  const linkedinSuccessRate = telemetry ? formatRate(telemetry.publish_success_rate) : "—";

  const igStats = telemetry?.channels?.instagram;
  const igSuccessRate = safeRate(igStats?.verified, igStats?.total);
  const igSuccessRateLabel = formatRate(igSuccessRate);

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6 space-y-8">
      {/* ── Page header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Publishing</h1>
          <p className="text-gray-500 text-sm mt-0.5">
            Live external workflow execution — LinkedIn &amp; Instagram
          </p>
        </div>
        <button
          onClick={refresh}
          className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-sm"
        >
          ↺ Refresh All
        </button>
      </div>

      {/* ── Platform switcher ── */}
      <div className="flex gap-2">
        {PLATFORMS.map((p) => (
          <button
            key={p.id}
            onClick={() => setPlatform(p.id)}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              platform === p.id ? p.activeClass : "bg-gray-800 text-gray-400 hover:bg-gray-700"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {platform === "linkedin" ? (
        <>
          {/* ── Telemetry row (all channels) ── */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <TelemetryCard
              label="Success Rate"
              value={linkedinSuccessRate}
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

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-6">
              <LinkedInConnectionPanel workspaceSlug={workspaceSlug} onConnected={refresh} />
              <LinkedInPublishPanel workspaceSlug={workspaceSlug} />
            </div>
            <div className="space-y-6">
              <ChannelHealthCard
                telemetry={telemetry}
                footerLabel="Verification failures"
                footerValue={totals.failed ?? 0}
              />
            </div>
          </div>
        </>
      ) : (
        <>
          {/* ── Telemetry row (Instagram channel only) ── */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <TelemetryCard
              label="Success Rate"
              value={igSuccessRateLabel}
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

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-6">
              <InstagramConnectionPanel workspaceSlug={workspaceSlug} onConnected={refresh} />
              <InstagramPublishPanel workspaceSlug={workspaceSlug} />
            </div>
            <div className="space-y-6">
              <ChannelHealthCard
                telemetry={telemetry}
                footerLabel="Instagram verification failures"
                footerValue={igStats?.failed ?? 0}
              />
            </div>
          </div>
        </>
      )}

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
