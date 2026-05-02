import { useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  Clock3,
  FilePlus2,
  Megaphone,
  MessageCircle,
  Music2,
  Newspaper,
  Play,
  RefreshCw,
  RotateCcw,
  Send,
  X,
} from "lucide-react";
import { api } from "../api.js";
import DemoPageBanner from "../components/DemoPageBanner.jsx";
import LiveAgentRunPanel from "../components/LiveAgentRunPanel.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const MODULES = ["contractor_growth", "insurance_growth", "artist_growth", "media_growth"];
const PRIORITIES = ["low", "normal", "high"];
const OPEN_DEAL_OUTCOMES = ["proposal_sent", "negotiation", "nurture"];

const AGENT_ACTIONS = [
  { agent_name: "outreach", task_type: "run_outreach", label: "Run Outreach", icon: Megaphone },
  { agent_name: "followup", task_type: "run_followup", label: "Run Follow-up", icon: MessageCircle },
  { agent_name: "content", task_type: "generate_content", label: "Generate Content", icon: Newspaper },
  { agent_name: "fan_engagement", task_type: "engage_fans", label: "Fan Engagement", icon: Music2 },
];

const APPROVAL_DECISIONS = [
  { value: "approve", label: "Approve", icon: Check },
  { value: "needs_revision", label: "Revise", icon: RotateCcw },
  { value: "reject", label: "Reject", icon: X },
  { value: "convert_to_draft", label: "Convert to draft", icon: FilePlus2 },
];

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

function formatMoney(value) {
  return `$${Number(value || 0).toLocaleString()}`;
}

function recordTitle(item) {
  return item.subject_line || item.title || item.company || item.company_name || item.recipient_name || item.person || item.request_type || item._id || "Untitled";
}

function StepSection({ step, title, subtitle, active, count, children }) {
  return (
    <section className={["rounded-lg border bg-white p-5 shadow-sm transition", active ? "border-blue-300 ring-2 ring-blue-100" : "border-slate-200"].join(" ")}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-xs font-semibold uppercase text-slate-400">Step {step}</div>
          <h2 className="mt-1 text-xl font-semibold text-slate-950">{title}</h2>
          {subtitle ? <p className="mt-2 text-sm leading-6 text-slate-600">{subtitle}</p> : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {active ? <StatusBadge value="next action" /> : null}
          {count !== undefined ? <StatusBadge value={`${count} items`} /> : null}
        </div>
      </div>
      {children}
    </section>
  );
}

function EmptyState({ children }) {
  return <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">{children}</div>;
}

export default function WorkflowPage() {
  const livePanelRef = useRef(null);
  const [tasks, setTasks] = useState([]);
  const [messages, setMessages] = useState([]);
  const [approvalRequests, setApprovalRequests] = useState([]);
  const [deals, setDeals] = useState([]);
  const [agentRuns, setAgentRuns] = useState([]);
  const [activeTask, setActiveTask] = useState(null);
  const [activeRunDetail, setActiveRunDetail] = useState(null);
  const [activeAction, setActiveAction] = useState(null);
  const [config, setConfig] = useState({ module: "contractor_growth", limit: 10, priority: "normal", segment: "", high_priority: false });
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");
  const [panelLoading, setPanelLoading] = useState(false);
  const [notes, setNotes] = useState({});

  async function loadWorkflow() {
    const [taskData, messageData, approvalData, dealData, runData] = await Promise.all([
      api.agentTasks({ limit: "200" }),
      api.messages({ limit: "250" }),
      api.approvalRequests({ limit: "200" }),
      api.deals({ limit: "250" }),
      api.agentRuns({ limit: "25" }),
    ]);
    const nextTasks = taskData.items || [];
    const nextRuns = runData.items || [];
    setTasks(nextTasks);
    setMessages(messageData.items || []);
    setApprovalRequests(approvalData.items || []);
    setDeals(dealData.items || []);
    setAgentRuns(nextRuns);

    if (!activeTask && !activeRunDetail) {
      const latestTaskWithRun = nextTasks.find((task) => task.linked_run_id);
      if (latestTaskWithRun) {
        setActiveTask(latestTaskWithRun);
        await refreshRunDetail(latestTaskWithRun.linked_run_id, { quiet: true });
      } else if (nextRuns[0]?.run_id) {
        await refreshRunDetail(nextRuns[0].run_id, { quiet: true });
      }
    }
  }

  useEffect(() => {
    loadWorkflow();
  }, []);

  useEffect(() => {
    if (!activeTask?.linked_run_id) return;
    if (!["running", "waiting_for_approval"].includes(activeTask.status)) return;
    const interval = window.setInterval(() => {
      refreshRunDetail(activeTask.linked_run_id, { quiet: true });
      loadWorkflow();
    }, 2500);
    return () => window.clearInterval(interval);
  }, [activeTask?.linked_run_id, activeTask?.status]);

  function openModal(action) {
    setNotice("");
    setActiveAction(action);
    setConfig({ module: "contractor_growth", limit: 10, priority: "normal", segment: "", high_priority: false });
  }

  async function refreshRunDetail(runId, options = {}) {
    if (!runId) return;
    if (!options.quiet) setPanelLoading(true);
    try {
      const detail = await api.agentRunDetail(runId);
      setActiveRunDetail(detail);
    } catch (error) {
      if (!options.quiet) setNotice(error.message);
    } finally {
      if (!options.quiet) setPanelLoading(false);
    }
  }

  async function createTask(event) {
    event.preventDefault();
    if (!activeAction) return;
    setNotice("");
    const input_config = {
      limit: Number(config.limit),
      filters: {
        ...(config.segment.trim() ? { segment: config.segment.trim() } : {}),
        ...(config.high_priority ? { high_priority: true } : {}),
      },
    };
    try {
      const result = await api.createAgentTask({
        agent_name: activeAction.agent_name,
        module: config.module,
        task_type: activeAction.task_type,
        priority: config.priority,
        input_config,
      });
      const task = result.item;
      setActiveAction(null);
      setActiveTask({ ...task, status: "running", started_at: new Date().toISOString() });
      setActiveRunDetail(null);
      setPanelLoading(true);
      livePanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      const runResult = await api.runAgentTask(task._id);
      const updatedTask = runResult.item || task;
      setActiveTask(updatedTask);
      setNotice(runResult.message || "Agent task dry-run completed. No outbound action taken.");
      if (updatedTask.linked_run_id) await refreshRunDetail(updatedTask.linked_run_id);
      await loadWorkflow();
    } catch (error) {
      setNotice(error.message);
    } finally {
      setPanelLoading(false);
    }
  }

  async function reviewMessage(message, decision) {
    setBusyId(message._id);
    setNotice("");
    try {
      await api.reviewMessage(message._id, { decision, note: `Reviewed from Workflow Mode v1: ${decision}.` });
      setNotice(`Saved ${decision}. No message sent.`);
      await loadWorkflow();
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusyId("");
    }
  }

  async function decideApproval(item, decision) {
    setBusyId(item._id);
    setNotice("");
    try {
      const result = await api.decideApprovalRequest(item._id, { decision, note: notes[item._id] || "" });
      setNotice(result.message || "Approval decision saved. No outbound action taken.");
      await loadWorkflow();
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusyId("");
    }
  }

  const latestRun = activeRunDetail?.run || agentRuns[0] || null;
  const draftsNeedingReview = messages.filter((message) => message.review_status === "needs_review");
  const openApprovals = approvalRequests.filter((item) => item.status === "open");
  const readyToSend = messages.filter((message) => message.review_status === "approved" && message.send_status === "not_sent");
  const awaitingResponse = messages.filter((message) => message.send_status === "sent" && !message.response_status);
  const interested = messages.filter((message) => ["interested", "requested_info"].includes(message.response_status));
  const booked = messages.filter((message) => message.response_status === "call_booked");
  const openDeals = deals.filter((deal) => OPEN_DEAL_OUTCOMES.includes(deal.outcome || deal.deal_status));
  const closedWon = deals.filter((deal) => (deal.outcome || deal.deal_status) === "closed_won");

  const nextStep = useMemo(() => {
    if (activeTask?.status === "running") return 2;
    if (draftsNeedingReview.length || openApprovals.length) return 3;
    if (readyToSend.length) return 4;
    if (awaitingResponse.length || interested.length || booked.length) return 5;
    if (openDeals.length || closedWon.length) return 6;
    return 1;
  }, [activeTask?.status, draftsNeedingReview.length, openApprovals.length, readyToSend.length, awaitingResponse.length, interested.length, booked.length, openDeals.length, closedWon.length]);

  return (
    <div className="space-y-5">
      <DemoPageBanner onReset={loadWorkflow} />
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase text-slate-400">Workflow Mode v1</div>
            <h2 className="mt-1 text-2xl font-semibold text-slate-950">Guided Campaign Workflow</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">Run agents, review generated work, prepare manual outreach, and track responses and deals from one continuous operator page.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge value="simulation only" />
            <StatusBadge value="human reviewed" />
            <button type="button" onClick={loadWorkflow} className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700">
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>
      </section>

      {notice ? <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">{notice}</div> : null}

      <StepSection step="1" title="Run Agent" subtitle="Start the same safe Agent Tasks dry-run from the top of the workflow." active={nextStep === 1} count={tasks.length}>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {AGENT_ACTIONS.map((action) => {
            const Icon = action.icon;
            return (
              <button key={action.task_type} type="button" onClick={() => openModal(action)} className="inline-flex h-12 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-800 transition hover:border-blue-200 hover:text-blue-700">
                <Icon className="h-4 w-4" />
                {action.label}
              </button>
            );
          })}
        </div>
      </StepSection>

      <div ref={livePanelRef}>
        <StepSection step="2" title="Agent Activity" subtitle="Current or most recent run, including timeline and generated outputs." active={nextStep === 2} count={latestRun ? 1 : 0}>
          {latestRun || activeTask ? (
            <LiveAgentRunPanel task={activeTask} runDetail={activeRunDetail} loading={panelLoading} onRefresh={() => refreshRunDetail(activeTask?.linked_run_id || latestRun?.run_id)} />
          ) : (
            <EmptyState>No agent run is available yet. Run an agent to populate the live panel.</EmptyState>
          )}
        </StepSection>
      </div>

      <StepSection step="3" title="Review Outputs" subtitle="Approve, revise, reject, or convert generated work without leaving Workflow." active={nextStep === 3} count={draftsNeedingReview.length + openApprovals.length}>
        <div className="grid gap-4 xl:grid-cols-2">
          <div>
            <h3 className="mb-3 text-sm font-semibold text-slate-950">Drafts needing review</h3>
            <div className="space-y-3">
              {draftsNeedingReview.map((message) => (
                <article key={message._id} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold text-slate-950">{recordTitle(message)}</div>
                      <div className="mt-1 text-sm text-slate-600">{message.recipient_name || "-"} · {message.company || message.module || "-"}</div>
                    </div>
                    <StatusBadge value={message.review_status} />
                  </div>
                  <div className="mt-3 line-clamp-3 whitespace-pre-wrap text-sm leading-6 text-slate-700">{message.message_body || "No body recorded."}</div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button type="button" disabled={busyId === message._id} onClick={() => reviewMessage(message, "approve")} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-green-600 px-3 text-xs font-medium text-white transition hover:bg-green-700 disabled:bg-slate-300"><Check className="h-3.5 w-3.5" />Approve</button>
                    <button type="button" disabled={busyId === message._id} onClick={() => reviewMessage(message, "revise")} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-amber-500 px-3 text-xs font-medium text-white transition hover:bg-amber-600 disabled:bg-slate-300"><RotateCcw className="h-3.5 w-3.5" />Revise</button>
                    <button type="button" disabled={busyId === message._id} onClick={() => reviewMessage(message, "reject")} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-slate-800 px-3 text-xs font-medium text-white transition hover:bg-red-700 disabled:bg-slate-300"><X className="h-3.5 w-3.5" />Reject</button>
                  </div>
                </article>
              ))}
              {!draftsNeedingReview.length ? <EmptyState>No drafts need review.</EmptyState> : null}
            </div>
          </div>

          <div>
            <h3 className="mb-3 text-sm font-semibold text-slate-950">Approval requests</h3>
            <div className="space-y-3">
              {openApprovals.map((item) => (
                <article key={item._id} className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap gap-2"><StatusBadge value={item.request_type} /><StatusBadge value={item.status} /></div>
                      <div className="mt-3 font-semibold text-amber-950">{recordTitle(item)}</div>
                      <p className="mt-2 text-sm leading-6 text-amber-900">{item.reason_for_review || item.summary || "Review requested."}</p>
                    </div>
                    <div className="text-xs text-amber-800">{formatDate(item.created_at)}</div>
                  </div>
                  <textarea value={notes[item._id] || ""} onChange={(event) => setNotes((current) => ({ ...current, [item._id]: event.target.value }))} placeholder="Operator note" className="mt-4 min-h-16 w-full rounded-lg border border-amber-200 bg-white p-3 text-sm text-slate-700 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100" />
                  <div className="mt-3 flex flex-wrap gap-2">
                    {APPROVAL_DECISIONS.map((decision) => {
                      const Icon = decision.icon;
                      return <button key={decision.value} type="button" disabled={busyId === item._id} onClick={() => decideApproval(item, decision.value)} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-amber-200 bg-white px-3 text-xs font-medium text-amber-900 transition hover:border-amber-300 disabled:opacity-60"><Icon className="h-3.5 w-3.5" />{decision.label}</button>;
                    })}
                  </div>
                </article>
              ))}
              {!openApprovals.length ? <EmptyState>No approval requests are open.</EmptyState> : null}
            </div>
          </div>
        </div>
      </StepSection>

      <StepSection step="4" title="Ready to Send" subtitle="Approved drafts are ready for a human to send outside SignalForge." active={nextStep === 4} count={readyToSend.length}>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {readyToSend.map((message) => (
            <article key={message._id} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="font-semibold text-slate-950">{recordTitle(message)}</div>
              <div className="mt-1 text-sm text-slate-600">{message.recipient_name || "-"} · {message.company || message.module || "-"}</div>
              <div className="mt-3 flex flex-wrap gap-2"><StatusBadge value={message.review_status} /><StatusBadge value={message.send_status} /></div>
              <button type="button" onClick={() => setNotice("Send manually from your external inbox. SignalForge did not send anything.")} className="mt-4 inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700">
                <Send className="h-4 w-4" />
                Send manually
              </button>
            </article>
          ))}
          {!readyToSend.length ? <EmptyState>No approved drafts are waiting for manual send.</EmptyState> : null}
        </div>
      </StepSection>

      <StepSection step="5" title="Responses" subtitle="Track response states after a human manually sends outreach." active={nextStep === 5} count={awaitingResponse.length + interested.length + booked.length}>
        <div className="grid gap-4 lg:grid-cols-3">
          {[{ label: "Awaiting response", rows: awaitingResponse, icon: Clock3 }, { label: "Interested", rows: interested, icon: MessageCircle }, { label: "Call booked", rows: booked, icon: Check }].map((group) => {
            const Icon = group.icon;
            return (
              <div key={group.label} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="mb-3 flex items-center justify-between gap-2"><div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-950"><Icon className="h-4 w-4 text-blue-600" />{group.label}</div><StatusBadge value={`${group.rows.length} items`} /></div>
                <div className="space-y-2">
                  {group.rows.slice(0, 6).map((message) => <div key={message._id} className="rounded-lg border border-slate-200 bg-white p-3 text-sm"><div className="font-medium text-slate-950">{recordTitle(message)}</div><div className="mt-1 text-slate-500">{message.recipient_name || message.company || "-"}</div></div>)}
                  {!group.rows.length ? <div className="text-sm text-slate-500">Nothing in this state.</div> : null}
                </div>
              </div>
            );
          })}
        </div>
      </StepSection>

      <StepSection step="6" title="Deals" subtitle="Review open opportunities and closed wins generated by the workflow." active={nextStep === 6} count={openDeals.length + closedWon.length}>
        <div className="grid gap-4 xl:grid-cols-2">
          {[{ label: "Open deals", rows: openDeals }, { label: "Closed won", rows: closedWon }].map((group) => (
            <div key={group.label} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="mb-3 flex items-center justify-between gap-3"><h3 className="text-sm font-semibold text-slate-950">{group.label}</h3><StatusBadge value={formatMoney(group.rows.reduce((sum, deal) => sum + Number(deal.deal_value || 0), 0))} /></div>
              <div className="grid gap-3 md:grid-cols-2">
                {group.rows.slice(0, 8).map((deal) => (
                  <article key={deal._id} className="rounded-lg border border-slate-200 bg-white p-3">
                    <div className="font-semibold text-slate-950">{deal.company || deal.person || "Deal"}</div>
                    <div className="mt-1 text-sm text-slate-500">{deal.person || deal.module || "-"}</div>
                    <div className="mt-3 flex items-center justify-between gap-2"><span className="text-sm font-semibold text-slate-900">{formatMoney(deal.deal_value)}</span><StatusBadge value={deal.outcome || deal.deal_status || "unknown"} /></div>
                  </article>
                ))}
              </div>
              {!group.rows.length ? <EmptyState>No {group.label.toLowerCase()}.</EmptyState> : null}
            </div>
          ))}
        </div>
      </StepSection>

      {activeAction ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <form onSubmit={createTask} className="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-xs font-semibold uppercase text-slate-400">Create Task</div>
                <h3 className="mt-1 text-lg font-semibold text-slate-950">{activeAction.label}</h3>
              </div>
              <button type="button" onClick={() => setActiveAction(null)} className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition hover:text-slate-900"><X className="h-4 w-4" /></button>
            </div>
            <div className="mt-5 grid gap-4">
              <label className="grid gap-1 text-sm font-medium text-slate-700">Module<select value={config.module} onChange={(event) => setConfig((current) => ({ ...current, module: event.target.value }))} className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700">{MODULES.map((module) => <option key={module} value={module}>{module}</option>)}</select></label>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="grid gap-1 text-sm font-medium text-slate-700">Limit<input type="number" min="1" max="50" value={config.limit} onChange={(event) => setConfig((current) => ({ ...current, limit: event.target.value }))} className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-700" /></label>
                <label className="grid gap-1 text-sm font-medium text-slate-700">Priority<select value={config.priority} onChange={(event) => setConfig((current) => ({ ...current, priority: event.target.value }))} className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700">{PRIORITIES.map((priority) => <option key={priority} value={priority}>{priority}</option>)}</select></label>
              </div>
              <label className="grid gap-1 text-sm font-medium text-slate-700">Segment<input value={config.segment} onChange={(event) => setConfig((current) => ({ ...current, segment: event.target.value }))} className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-700" /></label>
              <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700"><input type="checkbox" checked={config.high_priority} onChange={(event) => setConfig((current) => ({ ...current, high_priority: event.target.checked }))} className="h-4 w-4 rounded border-slate-300" />High priority filter</label>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setActiveAction(null)} className="inline-flex h-10 items-center rounded-lg border border-slate-200 px-4 text-sm font-medium text-slate-700 transition hover:text-slate-950">Cancel</button>
              <button type="submit" className="inline-flex h-10 items-center gap-2 rounded-lg bg-blue-600 px-4 text-sm font-semibold text-white transition hover:bg-blue-700"><Play className="h-4 w-4" />Queue Task</button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}