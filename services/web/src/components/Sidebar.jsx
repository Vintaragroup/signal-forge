import { Activity, Sparkles } from "lucide-react";

/**
 * Grouped sidebar navigation.
 *
 * Props:
 *   navGroups      — NAV_GROUPS array from navGroups.js
 *   routeMap       — ROUTE_MAP keyed object from routeRegistry.js
 *   activePage     — current hash route string (from App.jsx state)
 *   onChange       — callback(routeId) to navigate to a route
 *   activeProfile  — current profile id string (from App.jsx state)
 *   onProfileChange — callback(profileId) — does NOT navigate, change workspace, or affect agents
 */
export default function Sidebar({ navGroups, routeMap, activePage, onChange }) {
  // Determine which group the current page belongs to, so hidden routes still
  // highlight their parent group button correctly.
  const activeGroup = routeMap[activePage]?.group ?? "";

  return (
    <aside className="hidden min-h-screen w-72 shrink-0 border-r border-slate-900 bg-ink-950 px-4 py-5 text-white lg:flex lg:flex-col">
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
        {navGroups.map((group) => {
          const Icon = group.icon;
          const active = group.id === activeGroup;
          return (
            <button
              key={group.id}
              type="button"
              onClick={() => onChange(group.defaultRoute)}
              className={[
                "flex h-10 w-full items-center gap-3 rounded-lg px-3 text-sm font-medium transition",
                active
                  ? "bg-white text-slate-950 shadow-soft"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white",
              ].join(" ")}
            >
              <Icon className="h-4 w-4" />
              {group.label}
            </button>
          );
        })}
      </nav>

      {/* Push footer card to bottom */}
      <div className="mt-auto pt-6">
        {/* Operating Mode card */}
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
            <Activity className="h-3.5 w-3.5 text-green-400" />
            Operating Mode
          </div>
          <div className="text-sm font-medium text-white">Human-reviewed</div>
          <div className="mt-1 text-xs leading-5 text-slate-400">No outbound automation is enabled.</div>
        </div>
      </div>
    </aside>
  );
}
