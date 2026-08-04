// Shared null-safe rate math for the distribution telemetry pages
// (LinkedInPilotPage.jsx, InstagramPilotPage.jsx). A zero-total channel has
// no rate to report — never divide-by-zero into NaN and print "NaN%".

export function safeRate(numerator, denominator) {
  return denominator ? numerator / denominator : null;
}

export function formatRate(rate, decimals = 1) {
  return typeof rate === "number" && Number.isFinite(rate) ? `${(rate * 100).toFixed(decimals)}%` : "—";
}
