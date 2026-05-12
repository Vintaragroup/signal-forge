import { useState } from "react";
import { Briefcase, ChevronDown, Clapperboard, Database, Layers } from "lucide-react";
import StatusBadge from "./StatusBadge.jsx";
import { SYSTEM_PROFILES } from "../navigation/systemProfiles.js";

function WorkspaceSelector({ workspaces, activeWorkspace, onWorkspaceChange }) {
  return (
    <div className="flex items-center gap-1.5">
      <Briefcase className="h-3.5 w-3.5 text-slate-400" />
      <select
        value={activeWorkspace}
        onChange={(e) => onWorkspaceChange(e.target.value)}
        className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs font-medium text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        aria-label="Active workspace"
      >
        <option value="all">All Workspaces</option>
        {workspaces.map((ws) => (
          <option key={ws.slug} value={ws.slug}>
            {ws.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function ProfileSelector({ activeProfile, onProfileChange }) {
  const [open, setOpen] = useState(false);
  const current = SYSTEM_PROFILES.find((p) => p.id === activeProfile) ?? SYSTEM_PROFILES[SYSTEM_PROFILES.length - 1];

  function select(id) {
    onProfileChange(id);
    setOpen(false);
  }

  return (
    <div className="relative">
      <div className="flex flex-col items-center gap-0.5">
        <span className="text-[10px] font-semibold uppercase tracking-widest leading-none text-slate-400">System Profile</span>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-100"
        >
          <Layers className="h-4 w-4 text-slate-400" />
          <span className="max-w-[180px] truncate">{current.label}</span>
          <ChevronDown className={["h-3.5 w-3.5 text-slate-400 transition-transform", open ? "rotate-180" : ""].join(" ")} />
        </button>
      </div>
      {open && (
        <ul className="absolute right-0 top-full z-40 mt-1.5 min-w-[220px] overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg">
          {SYSTEM_PROFILES.map((profile) => (
            <li key={profile.id}>
              <button
                type="button"
                onClick={() => select(profile.id)}
                className={[
                  "flex w-full items-center gap-2 px-4 py-2 text-left text-sm transition",
                  profile.id === activeProfile
                    ? "bg-blue-50 font-semibold text-blue-700"
                    : "text-slate-700 hover:bg-slate-50",
                ].join(" ")}
              >
                {profile.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

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

export default function Header({ title, health, gptRuntime, lastRefresh, action, demoMode, onToggleDemo, workspaces = [], activeWorkspace = "all", onWorkspaceChange, activeProfile, onProfileChange }) {
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

          {/* Workspace selector */}
          {!demoMode && onWorkspaceChange && (
            <WorkspaceSelector
              workspaces={workspaces}
              activeWorkspace={activeWorkspace}
              onWorkspaceChange={onWorkspaceChange}
            />
          )}

          {/* System Profile selector */}
          {onProfileChange && (
            <ProfileSelector activeProfile={activeProfile} onProfileChange={onProfileChange} />
          )}

          {/* Mode Switcher — environment state indicator, not navigation */}
          <div
            className="relative"
            onMouseEnter={() => setTooltipVisible(true)}
            onMouseLeave={() => setTooltipVisible(false)}
          >
            <div className="flex flex-col items-center gap-0.5">
              <span className="text-[10px] font-semibold uppercase tracking-widest leading-none text-slate-400">Environment</span>
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
            </div>
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
