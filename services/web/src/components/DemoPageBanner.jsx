import { Clapperboard, RefreshCw } from "lucide-react";
import { api } from "../api.js";

/**
 * Inline page-level banner shown at the top of pages when Demo Mode is active.
 * Optionally shows a Reset Demo Data button.
 */
export default function DemoPageBanner({ showReset = false, onReset }) {
  if (!api.demoEnabled()) return null;

  async function handleReset() {
    await api.resetDemo();
    if (onReset) onReset();
  }

  return (
    <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border-2 border-purple-300 bg-purple-50 px-4 py-3">
      <div className="flex items-center gap-2">
        <Clapperboard className="h-4 w-4 shrink-0 text-purple-600" />
        <div>
          <span className="text-sm font-bold text-purple-800">DEMO MODE</span>
          <span className="ml-2 text-sm text-purple-700">
            Synthetic data only — no real records are shown or affected.
          </span>
        </div>
      </div>
      {showReset ? (
        <button
          type="button"
          onClick={handleReset}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-purple-300 bg-white px-3 py-1.5 text-xs font-semibold text-purple-700 transition hover:bg-purple-50"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Reset Demo Data
        </button>
      ) : null}
    </div>
  );
}
