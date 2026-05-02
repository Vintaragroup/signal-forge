/**
 * Persistent full-width mode banner.
 * Demo Mode: purple — prominent "DEMO MODE" warning.
 * Real Mode: subtle blue — "REAL MODE" status.
 */
export default function ModeBanner({ demoMode }) {
  if (demoMode) {
    return (
      <div
        role="status"
        aria-label="Demo Mode active"
        className="border-b-2 border-purple-400 bg-purple-600 px-5 py-2 text-center text-sm font-bold tracking-wide text-white lg:px-8"
      >
        DEMO MODE &mdash; Synthetic data only. No real records are affected.
      </div>
    );
  }

  return (
    <div
      role="status"
      aria-label="Real Mode active"
      className="border-b border-blue-100 bg-blue-50 px-5 py-1.5 text-center text-xs font-semibold tracking-wide text-blue-700 lg:px-8"
    >
      REAL MODE &mdash; Using local SignalForge data. No automated outbound sending.
    </div>
  );
}
