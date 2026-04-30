import { Activity, Sparkles } from "lucide-react";

export default function Sidebar({ items, activePage, onChange }) {
  return (
    <aside className="hidden min-h-screen w-72 shrink-0 border-r border-slate-900 bg-ink-950 px-4 py-5 text-white lg:block">
      <div className="mb-7 flex items-center gap-3 px-2">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-500 shadow-soft">
          <Sparkles className="h-5 w-5" />
        </div>
        <div>
          <div className="text-sm font-semibold tracking-wide">SignalForge</div>
          <div className="text-xs text-slate-400">Web Dashboard v1</div>
        </div>
      </div>

      <nav className="space-y-1">
        {items.map((item) => {
          const Icon = item.icon;
          const active = item.id === activePage;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onChange(item.id)}
              className={[
                "flex h-10 w-full items-center gap-3 rounded-lg px-3 text-sm font-medium transition",
                active
                  ? "bg-white text-slate-950 shadow-soft"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white",
              ].join(" ")}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </button>
          );
        })}
      </nav>

      <div className="mt-8 rounded-lg border border-slate-800 bg-slate-900 p-3">
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          <Activity className="h-3.5 w-3.5 text-green-400" />
          Operating Mode
        </div>
        <div className="text-sm font-medium text-white">Human-reviewed</div>
        <div className="mt-1 text-xs leading-5 text-slate-400">No outbound automation is enabled.</div>
      </div>
    </aside>
  );
}
