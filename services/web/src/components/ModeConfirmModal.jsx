import { X } from "lucide-react";

/**
 * Confirmation modal shown before switching between Real Mode and Demo Mode.
 * targetMode: "demo" | "real"
 */
export default function ModeConfirmModal({ targetMode, onConfirm, onCancel }) {
  if (!targetMode) return null;

  const isDemo = targetMode === "demo";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="mode-confirm-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
    >
      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div
              className={`mb-2 inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${
                isDemo
                  ? "bg-purple-50 text-purple-700 ring-purple-200"
                  : "bg-blue-50 text-blue-700 ring-blue-200"
              }`}
            >
              {isDemo ? "Demo Mode" : "Real Mode"}
            </div>
            <h2 id="mode-confirm-title" className="text-lg font-semibold text-slate-950">
              {isDemo ? "Switch to Demo Mode?" : "Switch to Real Mode?"}
            </h2>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Cancel"
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <p className="mt-3 text-sm leading-6 text-slate-600">
          {isDemo
            ? "Demo Mode uses synthetic browser-only data and will not affect real records. All demo records are clearly labeled and stored only in your browser."
            : "Real Mode uses your local MongoDB data and is intended for actual company testing. No automated outbound sending will occur."}
        </p>

        <div
          className={`mt-4 rounded-lg p-3 text-xs font-medium ${
            isDemo ? "bg-purple-50 text-purple-800" : "bg-blue-50 text-blue-800"
          }`}
        >
          {isDemo
            ? "Demo Mode never writes to MongoDB. Reset Demo Data at any time to restore seeded synthetic records."
            : "Real Mode reads and writes to local MongoDB only. Outbound sending always requires a manual step outside SignalForge."}
        </div>

        <div className="mt-5 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="h-9 rounded-lg border border-slate-200 px-4 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`h-9 rounded-lg px-4 text-sm font-semibold text-white transition ${
              isDemo ? "bg-purple-600 hover:bg-purple-700" : "bg-blue-600 hover:bg-blue-700"
            }`}
          >
            {isDemo ? "Enter Demo Mode" : "Enter Real Mode"}
          </button>
        </div>
      </div>
    </div>
  );
}
