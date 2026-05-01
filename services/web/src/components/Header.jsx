import StatusBadge from "./StatusBadge.jsx";

export default function Header({ title, health, gptRuntime, lastRefresh, action }) {
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
