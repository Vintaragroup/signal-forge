import { Bot, PlayCircle } from "lucide-react";
import StatusBadge from "./StatusBadge.jsx";

export default function AgentActivityCard({ agent, modules = [], onRun, running }) {
  const defaultModule = modules[0] || "contractor_growth";

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-purple-50 p-2 text-purple-700 ring-1 ring-purple-100">
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-semibold capitalize text-slate-950">{agent.name?.replaceAll("_", " ")}</div>
            <div className="mt-1 text-sm leading-5 text-slate-500">{agent.description}</div>
          </div>
        </div>
        <StatusBadge value={agent.available ? "ready" : "unavailable"} />
      </div>
      <button
        type="button"
        disabled={!agent.available || running}
        onClick={() => onRun(agent.name, defaultModule)}
        className="mt-4 inline-flex h-9 items-center gap-2 rounded-lg bg-slate-950 px-3 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        <PlayCircle className="h-4 w-4" />
        Dry Run
      </button>
    </div>
  );
}
