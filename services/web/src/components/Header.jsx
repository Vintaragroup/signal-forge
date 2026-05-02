import { useState } from "react";
import { Clapperboard, Database } from "lucide-react";
import StatusBadge from "./StatusBadge.jsx";

function ModeTooltip({ demoMode, visible }) {
  if (!visible) return null;
  return (
    <div className="absolute right-0 top-full z-40 mt-2 w-64 rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-600 shadow-lg">
      {demoMode ? (
        <>
          <p className="font-semibold text-purple-700">Demo Mode is active.</p>
          <p className="mt-1">Synthetic browser-only data. Nothing is written to MongoDB. All records are labeled as demo data.</p>
          <p className="mt-1 text-slate-400">Click to switch to Real Mode.</p>
        </>
      ) : (
        <>
          <p className="font-semibold text-blue-700">Real Mode is active.</p>
          <p className="mt-1">Using local SignalForge MongoDB data. No automated outbound sending occurs.</p>
          <p className="mt-1 text-slate-400">Click to switch to Demo Mode.</p>
        </>
      )}
    </div>
  );
}

export default function Header({ title, health, gptRuntime, lastRefresh, action, demoMode, onToggleDemo }) {
  const [tooltipVisible, setTooltipVisible] = useState(false);

  const mongoReady = health?.mongo?.ready;
  const vaultReady = health?.vault?.exists;
  const gptLabel = gptRuntime?.enabled ? "gpt enabled" : "gpt disabled";
  const gptModel = gptRuntime?.model ? `model ${gptRuntime.model}` : "model not set";

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-[1500px] items-center justify-between px-5 py-4 lg:px-8">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">SignalForge</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-normal text-slate-950">{title}</h1>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-2 md:flex">
            <StatusBadge value={mongoReady ? "mongo ready" : "mongo offline"} />
            <StatusBadge value={vaultReady ? "vault ready" : "vault missing"} />
            <StatusBadge value={gptLabel} />
            {gptRuntime?.enabled ? <StatusBadge value={gptModel} /> : null}
          </div>

          {/* Mode Switcher with tooltip */}
          <div
            className="relative"
            onMouseEnter={() => setTooltipVisible(true)}
            onMouseLeave={() => setTooltipVisible(false)}
          >
            <button
              type="button"
              onClick={onToggleDemo}
              className={[
                "inline-flex h-9 items-center gap-2 rounded-lg border px-3 text-sm font-semibold shadow-sm transition",
                demoMode
                  ? "border-purple-400 bg-purple-600 text-white hover:bg-purple-700"
                  : "border-blue-200 bg-blue-50 text-blue-800 hover:border-blue-300 hover:bg-blue-100",
              ].join(" ")}
            >
              {demoMode ? (
                <>
                  <Clapperboard className="h-4 w-4" />
                  Demo Mode
                </>
              ) : (
                <>
                  <Database className="h-4 w-4" />
                  Real Mode
                </>
              )}
            </button>
            <ModeTooltip demoMode={demoMode} visible={tooltipVisible} />
          </div>

          <div className="hidden text-right text-xs text-slate-500 sm:block">
            <div>Updated</div>
            <div className="font-medium text-slate-700">{lastRefresh.toLocaleTimeString()}</div>
          </div>
          {action}
        </div>
      </div>
    </header>
  );
}
