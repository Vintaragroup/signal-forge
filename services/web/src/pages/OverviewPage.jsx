import { useEffect, useState } from "react";
import { ArrowRight, Bot, Building2, CheckCircle2, Circle, Clapperboard, DollarSign, Handshake, HelpCircle, Mail, MessageSquare, Target, Users } from "lucide-react";
import { api } from "../api.js";
import StatCard from "../components/StatCard.jsx";
import PipelineFunnel from "../components/PipelineFunnel.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const kpiConfig = [
  ["total_contacts", "Contacts", Users, "blue"],
  ["total_leads", "Leads", Target, "purple"],
  ["message_drafts", "Drafts", Mail, "amber"],
  ["sent_messages", "Sent", MessageSquare, "green"],
  ["responses", "Responses", MessageSquare, "blue"],
  ["meetings", "Meetings", Handshake, "purple"],
  ["deals", "Deals", Building2, "amber"],
  ["closed_won_revenue", "Won Revenue", DollarSign, "green"],
];

function money(value) {
  return `$${Number(value || 0).toLocaleString()}`;
}

function actionHref(action) {
  const params = new URLSearchParams(action.filters || {});
  return `#${action.page}${params.toString() ? `?${params.toString()}` : ""}`;
}

export default function OverviewPage() {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .overview()
      .then(setOverview)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="rounded-lg border border-slate-200 bg-white p-8 text-sm text-slate-500 shadow-sm">Loading dashboard...</div>;
  }

  const kpis = overview?.kpis || {};
  const demoMode = api.demoEnabled();

  async function startDemo() {
    await api.startDemo();
    window.location.hash = "demo";
  }

  const realChecklist = [
    { label: "Import candidates", detail: "Use Research / Tools → Import CSV to bring in a prospect list.", done: Number(kpis.total_contacts) > 0 },
    { label: "Review candidates", detail: "Open Research / Tools and approve or reject imported candidates.", done: false },
    { label: "Convert to contacts / leads", detail: "Approve candidates to create local contacts and leads in MongoDB.", done: Number(kpis.total_leads) > 0 },
    { label: "Run outreach agent", detail: "Use Agent Tasks or Workflow to generate review-only outreach drafts.", done: Number(kpis.message_drafts) > 0 },
    { label: "Review drafts / approvals", detail: "Open Messages or Approvals and approve, revise, or reject each draft.", done: Number(kpis.sent_messages) > 0 },
    { label: "Log manual sends / responses", detail: "After sending outside SignalForge, log the send and any replies.", done: Number(kpis.responses) > 0 },
    { label: "Generate report", detail: "Open Reports to view a pipeline or revenue performance summary.", done: false },
  ];

  const demoChecklist = [
    { label: "Start demo", detail: "Launch the Demo Mode walkthrough from the Demo Mode page.", done: true },
    { label: "Run outreach", detail: "Step 2 in Demo Mode — generate synthetic review-only drafts.", done: Boolean(overview?.kpis?.message_drafts) },
    { label: "Review draft", detail: "Step 3 — review and approve a demo draft. Nothing is sent.", done: Boolean(overview?.kpis?.sent_messages) },
    { label: "Simulate response", detail: "Step 4 — log a synthetic prospect reply.", done: Boolean(overview?.kpis?.responses) },
    { label: "Show deal outcome", detail: "Step 5 — close a demo deal to see the full pipeline end state.", done: Boolean(overview?.kpis?.deals) },
  ];

  return (
    <div className="space-y-5">
      {/* Mode-specific checklist panel */}
      {demoMode ? (
        <section className="rounded-lg border-2 border-purple-300 bg-purple-50 p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-xs font-bold uppercase tracking-widest text-purple-700">Demo Mode</div>
              <h2 className="mt-1 text-xl font-semibold text-purple-950">Demo Walkthrough</h2>
              <p className="mt-1 text-sm text-purple-800">Follow these steps in Demo Mode. No real records are affected.</p>
            </div>
            <a href="#demo" className="inline-flex h-9 items-center gap-2 rounded-lg bg-purple-600 px-4 text-sm font-semibold text-white transition hover:bg-purple-700">
              <Clapperboard className="h-4 w-4" />
              Open Demo
            </a>
          </div>
          <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {demoChecklist.map((item) => (
              <div key={item.label} className="flex items-start gap-3 rounded-lg border border-purple-200 bg-white p-3">
                {item.done ? (
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-purple-600" />
                ) : (
                  <Circle className="mt-0.5 h-4 w-4 shrink-0 text-purple-300" />
                )}
                <div>
                  <div className="text-sm font-semibold text-slate-900">{item.label}</div>
                  <p className="mt-0.5 text-xs text-slate-500">{item.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : (
        <section className="rounded-lg border border-blue-200 bg-blue-50 p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-blue-700">Real Mode</div>
              <h2 className="mt-1 text-xl font-semibold text-slate-950">Ready for Real Test Campaign</h2>
              <p className="mt-1 text-sm text-slate-600">Work through each step to run a complete operator cycle. No automated sending occurs.</p>
            </div>
            <a href="#workflow" className="inline-flex h-9 items-center gap-2 rounded-lg bg-blue-600 px-4 text-sm font-semibold text-white transition hover:bg-blue-700">
              Open Workflow
              <ArrowRight className="h-4 w-4" />
            </a>
          </div>
          <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
            {realChecklist.map((item) => (
              <div key={item.label} className="flex items-start gap-3 rounded-lg border border-blue-100 bg-white p-3">
                {item.done ? (
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-blue-600" />
                ) : (
                  <Circle className="mt-0.5 h-4 w-4 shrink-0 text-slate-300" />
                )}
                <div>
                  <div className="text-sm font-semibold text-slate-900">{item.label}</div>
                  <p className="mt-0.5 text-xs text-slate-500">{item.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {kpiConfig.map(([key, label, Icon, tone]) => (
          <StatCard
            key={key}
            label={label}
            value={key === "closed_won_revenue" ? money(kpis[key]) : Number(kpis[key] || 0).toLocaleString()}
            icon={Icon}
            tone={tone}
          />
        ))}
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
        <PipelineFunnel items={overview?.pipeline_funnel || []} />

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-950">Responses By Status</h2>
            <StatusBadge value={demoMode ? "Demo Mode" : "live data"} />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {Object.entries(overview?.responses_by_status || {}).map(([status, count]) => (
              <div key={status} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <StatusBadge value={status} />
                <div className="mt-3 text-2xl font-semibold text-slate-950">{count}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-4 flex flex-col justify-between gap-2 sm:flex-row sm:items-end">
          <div>
            <h2 className="text-sm font-semibold text-slate-950">Next Actions</h2>
            <p className="mt-1 text-sm text-slate-500">
              Work these queues from left to right during a test campaign. Links open the filtered dashboard view.
            </p>
          </div>
          <StatusBadge value="operator controlled" />
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {(overview?.next_actions || []).map((action) => (
            <a
              key={action.key}
              href={actionHref(action)}
              className="group rounded-lg border border-slate-200 bg-slate-50 p-4 transition hover:border-blue-200 hover:bg-blue-50/60"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-slate-950">{action.label}</div>
                  <p className="mt-2 min-h-10 text-sm leading-5 text-slate-500">{action.helper}</p>
                </div>
                <div className="text-2xl font-semibold text-slate-950">{action.count}</div>
              </div>
              <div className="mt-4 flex items-center justify-between">
                <StatusBadge value={action.tone} />
                <span className="inline-flex items-center gap-1 text-xs font-semibold text-blue-700">
                  Open queue
                  <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" />
                </span>
              </div>
            </a>
          ))}
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="mb-4 text-sm font-semibold text-slate-950">Revenue Over Time</h2>
          <div className="space-y-3">
            {(overview?.revenue_over_time || []).map((item) => (
              <div key={item.date} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
                <span className="text-sm text-slate-600">{item.date}</span>
                <span className="text-sm font-semibold text-green-700">{money(item.revenue)}</span>
              </div>
            ))}
            {!overview?.revenue_over_time?.length ? <div className="text-sm text-slate-500">No closed-won revenue yet.</div> : null}
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="mb-4 text-sm font-semibold text-slate-950">Top Modules</h2>
          <div className="space-y-3">
            {(overview?.top_modules || []).map((item) => (
              <div key={item.module} className="rounded-lg border border-slate-200 p-3">
                <div className="flex items-center justify-between">
                  <StatusBadge value={item.module} />
                  <span className="text-sm font-semibold text-slate-900">{money(item.revenue)}</span>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs text-slate-500">
                  <div><span className="block text-sm font-semibold text-slate-900">{item.contacts || 0}</span>Contacts</div>
                  <div><span className="block text-sm font-semibold text-slate-900">{item.messages || 0}</span>Drafts</div>
                  <div><span className="block text-sm font-semibold text-slate-900">{item.deals || 0}</span>Deals</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="mb-4 text-sm font-semibold text-slate-950">Tasks / Next Actions</h2>
          <div className="space-y-3">
            {(overview?.tasks || []).map((task) => (
              <div key={task.label} className="flex items-center justify-between rounded-lg border border-slate-200 p-3">
                <div className="text-sm font-medium text-slate-800">{task.label}</div>
                <StatusBadge value={`${task.count} ${task.tone}`} />
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <Bot className="h-4 w-4 text-purple-600" />
          <h2 className="text-sm font-semibold text-slate-950">Agent Activity</h2>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {(overview?.agent_activity || []).map((log) => (
            <div key={log.path} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <div className="text-sm font-semibold text-slate-900">{log.name}</div>
              <div className="mt-1 text-xs text-slate-500">{new Date(log.updated_at).toLocaleString()}</div>
              <div className="mt-3">
                <StatusBadge value={`${log.planned_actions} planned`} />
              </div>
            </div>
          ))}
          {!overview?.agent_activity?.length ? <div className="text-sm text-slate-500">No agent logs yet.</div> : null}
        </div>
      </div>

      {/* Settings / Help — Mode explanation */}
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <HelpCircle className="h-4 w-4 text-slate-400" />
          <h2 className="text-sm font-semibold text-slate-950">Mode Reference</h2>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className={`rounded-lg p-4 ${demoMode ? "border-2 border-purple-300 bg-purple-50" : "border border-slate-200 bg-slate-50"}`}>
            <div className="mb-2 flex items-center gap-2">
              <Clapperboard className="h-4 w-4 text-purple-600" />
              <span className="text-sm font-bold text-purple-800">Demo Mode</span>
              {demoMode ? <StatusBadge value="active" /> : null}
            </div>
            <ul className="space-y-1 text-xs text-slate-600">
              <li>• Browser-only synthetic data — no MongoDB reads or writes.</li>
              <li>• All records labeled <strong>DEMO</strong> and stored in localStorage only.</li>
              <li>• Used to show clients or new operators how the system works.</li>
              <li>• Reset Demo Data at any time to restore seeded records.</li>
              <li>• Agents, GPT, and real imports do not run in Demo Mode.</li>
            </ul>
          </div>
          <div className={`rounded-lg p-4 ${!demoMode ? "border-2 border-blue-200 bg-blue-50" : "border border-slate-200 bg-slate-50"}`}>
            <div className="mb-2 flex items-center gap-2">
              <Users className="h-4 w-4 text-blue-600" />
              <span className="text-sm font-bold text-blue-800">Real Mode</span>
              {!demoMode ? <StatusBadge value="active" /> : null}
            </div>
            <ul className="space-y-1 text-xs text-slate-600">
              <li>• Reads from and writes to local MongoDB only.</li>
              <li>• Intended for actual company test campaigns.</li>
              <li>• No automated outbound sending ever occurs.</li>
              <li>• All agent actions are dry-run or review-only.</li>
              <li>• All message sends require a human operator step outside SignalForge.</li>
            </ul>
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          Switch modes using the <strong>Mode Switcher</strong> in the top-right header. A confirmation dialog will appear before any switch.
        </p>
      </section>
    </div>
  );
}
