import { safeRate, formatRate } from "../utils/telemetry";

/**
 * ChannelHealthCard.jsx
 *
 * Shared per-channel success-rate breakdown used by PublishingPage.jsx's
 * LinkedIn/Instagram tabs — previously two separately-implemented copies
 * that had already drifted (LinkedIn read a raw stats.success_rate field
 * with no zero-total guard and printed "NaN%"; Instagram computed its own
 * safe ratio). Both now go through the same safeRate()/formatRate() so this
 * can't drift again.
 *
 * Props:
 *   telemetry    — the object returned by getDistributionTelemetry()
 *   footerLabel  — e.g. "Verification failures" or "Instagram verification failures"
 *   footerValue  — the failed-count to show next to footerLabel
 */
export default function ChannelHealthCard({ telemetry, footerLabel = "Verification failures", footerValue = 0 }) {
  if (!telemetry) return null;
  const channels = telemetry.channels ?? {};

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
      <h3 className="text-white font-semibold text-sm mb-4">Channel Health</h3>
      {Object.entries(channels).length === 0 ? (
        <p className="text-gray-500 text-xs">No channel data yet.</p>
      ) : (
        <div className="space-y-2">
          {Object.entries(channels).map(([ch, stats]) => {
            const rate = safeRate(stats.verified, stats.total);
            return (
              <div key={ch} className="flex items-center justify-between text-xs">
                <span className="text-gray-400 capitalize">{ch}</span>
                <span className={`font-semibold ${
                  rate == null ? "text-gray-500" : rate >= 0.9 ? "text-green-400" : "text-yellow-400"
                }`}>
                  {formatRate(rate, 0)}
                </span>
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-4 pt-4 border-t border-gray-800 text-xs text-gray-500">
        <p>Retry frequency: <span className="text-gray-300">
          {typeof telemetry.retry_frequency === "number" ? formatRate(telemetry.retry_frequency, 0) : "—"}
        </span></p>
        <p>{footerLabel}: <span className="text-gray-300">{footerValue}</span></p>
      </div>
    </div>
  );
}
