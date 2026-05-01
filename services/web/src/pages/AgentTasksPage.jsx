import { useEffect, useMemo, useRef, useState } from "react";
import { Ban, Megaphone, MessageCircle, Music2, Newspaper, Play, RefreshCw, X } from "lucide-react";
import { api } from "../api.js";
import LiveAgentRunPanel from "../components/LiveAgentRunPanel.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const MODULES = ["contractor_growth", "insurance_growth", "artist_growth", "media_growth"];
const PRIORITIES = ["low", "normal", "high"];

const AGENT_ACTIONS = [
  { agent_name: "outreach", task_type: "run_outreach", label: "Run Outreach", icon: Megaphone },
  { agent_name: "followup", task_type: "run_followup", label: "Run Follow-up", icon: MessageCircle },
  { agent_name: "content", task_type: "generate_content", label: "Generate Content", icon: Newspaper },
  { agent_name: "fan_engagement", task_type: "engage_fans", label: "Fan Engagement", icon: Music2 },
];

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

function taskActionLabel(task) {
  return AGENT_ACTIONS.find((action) => action.task_type === task.task_type)?.label || task.task_type;
}

export default function AgentTasksPage() {
  const livePanelRef = useRef(null);
  const [tasks, setTasks] = useState([]);
  const [status, setStatus] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");
  const [activeTask, setActiveTask] = useState(null);
  const [activeRunDetail, setActiveRunDetail] = useState(null);
  const [panelLoading, setPanelLoading] = useState(false);
  const [activeAction, setActiveAction] = useState(null);
  const [config, setConfig] = useState({
    module: "contractor_growth",
    limit: 10,
    priority: "normal",
    segment: "",
    high_priority: false,
  });

  async function loadTasks(nextStatus = status) {
    const params = nextStatus ? { status: nextStatus, limit: "200" } : { limit: "200" };
    const data = await api.agentTasks(params);
    setTasks(data.items || []);
  }

  useEffect(() => {
    loadTasks();
  }, []);

  useEffect(() => {
    if (!activeTask) return;
    livePanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [activeTask?._id]);

  useEffect(() => {
    if (!activeTask?.linked_run_id) return;
    if (!["running", "waiting_for_approval"].includes(activeTask.status)) return;
    const interval = window.setInterval(() => {
      refreshRunDetail(activeTask.linked_run_id, { quiet: true });
      loadTasks();
    }, 2500);
    return () => window.clearInterval(interval);
  }, [activeTask?.linked_run_id, activeTask?.status]);

  function openModal(action) {
    setNotice("");
    setActiveAction(action);
    setConfig({ module: "contractor_growth", limit: 10, priority: "normal", segment: "", high_priority: false });
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
      setNotice("Agent task queued. Live run panel opened.");
      setActiveAction(null);
      setActiveTask({ ...task, status: "running", started_at: new Date().toISOString() });
      setActiveRunDetail(null);
      await loadTasks();
      await runTask(task, { focusPanel: true });
    } catch (error) {
      setNotice(error.message);
    }
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

  async function runTask(task, options = {}) {
    setBusyId(task._id);
    if (options.focusPanel) {
      setActiveTask({ ...task, status: "running", started_at: task.started_at || new Date().toISOString() });
      setActiveRunDetail(null);
      setPanelLoading(true);
    }
    setNotice("");
    try {
      const result = await api.runAgentTask(task._id);
      const updatedTask = result.item || task;
      setActiveTask(updatedTask);
      setNotice(result.message || "Agent task dry-run completed.");
      if (updatedTask.linked_run_id) {
        await refreshRunDetail(updatedTask.linked_run_id, { quiet: false });
      }
      await loadTasks();
    } catch (error) {
      setNotice(error.message);
      await loadTasks();
    } finally {
      setBusyId("");
      setPanelLoading(false);
    }
  }

  async function cancelTask(task) {
    setBusyId(task._id);
    setNotice("");
    try {
      const result = await api.cancelAgentTask(task._id);
      setNotice(result.message || "Agent task cancelled.");
      await loadTasks();
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusyId("");
    }
  }

  const stats = useMemo(
    () => ({
      queued: tasks.filter((task) => task.status === "queued").length,
      running: tasks.filter((task) => task.status === "running").length,
      approvals: tasks.filter((task) => task.status === "waiting_for_approval").length,
      completed: tasks.filter((task) => task.status === "completed").length,
      failed: tasks.filter((task) => task.status === "failed").length,
    }),
    [tasks],
  );

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase text-slate-400">Run Agent</div>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">Agent Tasks</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">Agents are now run from the dashboard via Agent Tasks. Every task uses the existing simulation-first agent runner.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge value={`${stats.queued} queued`} />
            <StatusBadge value={`${stats.running} running`} />
            <StatusBadge value={`${stats.approvals} waiting_for_approval`} />
            <StatusBadge value={`${stats.completed} completed`} />
            {stats.failed ? <StatusBadge value={`${stats.failed} failed`} /> : null}
          </div>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {AGENT_ACTIONS.map((action) => {
            const Icon = action.icon;
            return (
              <button
                key={action.task_type}
                type="button"
                onClick={() => openModal(action)}
                className="inline-flex h-12 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-800 transition hover:border-blue-200 hover:text-blue-700"
              >
                <Icon className="h-4 w-4" />
                {action.label}
              </button>
            );
          })}
        </div>
      </section>

      {notice ? <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">{notice}</div> : null}

      {activeTask ? (
        <div ref={livePanelRef}>
          <LiveAgentRunPanel
            task={activeTask}
            runDetail={activeRunDetail}
            loading={panelLoading}
            onRefresh={() => activeTask.linked_run_id && refreshRunDetail(activeTask.linked_run_id)}
          />
        </div>
      ) : null}

      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-slate-950">Task Queue</h3>
          <div className="flex flex-wrap gap-2">
            <select value={status} onChange={(event) => { setStatus(event.target.value); loadTasks(event.target.value); }} className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700">
              <option value="">All</option>
              <option value="queued">Queued</option>
              <option value="running">Running</option>
              <option value="waiting_for_approval">Waiting for approval</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="cancelled">Cancelled</option>
            </select>
            <button type="button" onClick={() => loadTasks()} className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700">
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead>
              <tr className="text-left text-xs font-semibold uppercase text-slate-500">
                <th className="px-3 py-3">Agent</th>
                <th className="px-3 py-3">Module</th>
                <th className="px-3 py-3">Status</th>
                <th className="px-3 py-3">Priority</th>
                <th className="px-3 py-3">Created</th>
                <th className="px-3 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {tasks.map((task) => (
                <tr key={task._id} className="align-top">
                  <td className="px-3 py-3">
                    <div className="font-medium text-slate-950">{task.agent_name}</div>
                    <div className="mt-1 text-xs text-slate-500">{taskActionLabel(task)}</div>
                  </td>
                  <td className="px-3 py-3 text-slate-700">{task.module}</td>
                  <td className="px-3 py-3"><StatusBadge value={task.status} /></td>
                  <td className="px-3 py-3 text-slate-700">{task.priority}</td>
                  <td className="px-3 py-3 text-slate-500">{formatDate(task.created_at)}</td>
                  <td className="px-3 py-3">
                    <div className="flex flex-wrap gap-2">
                      <button type="button" disabled={busyId === task._id || task.status !== "queued"} onClick={() => runTask(task, { focusPanel: true })} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 text-xs font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
                        <Play className="h-3.5 w-3.5" />
                        Run
                      </button>
                      <button type="button" disabled={busyId === task._id || ["running", "completed", "cancelled"].includes(task.status)} onClick={() => cancelTask(task)} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 text-xs font-medium text-slate-700 transition hover:border-red-200 hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-60">
                        <Ban className="h-3.5 w-3.5" />
                        Cancel
                      </button>
                      {task.linked_run_id ? <button type="button" onClick={() => { setActiveTask(task); refreshRunDetail(task.linked_run_id); }} className="inline-flex h-8 items-center rounded-lg border border-slate-200 px-2.5 text-xs font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700">Live Run</button> : null}
                      {task.linked_run_id ? <a href={`#agents?run=${encodeURIComponent(task.linked_run_id)}`} className="inline-flex h-8 items-center rounded-lg border border-slate-200 px-2.5 text-xs font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700">Agent Console</a> : null}
                      {task.status === "waiting_for_approval" ? <a href="#approvals" className="inline-flex h-8 items-center rounded-lg border border-slate-200 px-2.5 text-xs font-medium text-slate-700 transition hover:border-amber-200 hover:text-amber-700">View Approvals</a> : null}
                    </div>
                    {task.error ? <div className="mt-2 text-xs text-red-700">{task.error}</div> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!tasks.length ? <div className="rounded-lg bg-slate-50 p-4 text-sm text-slate-500">No agent tasks match this view.</div> : null}
        </div>
      </section>

      {activeAction ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <form onSubmit={createTask} className="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-xs font-semibold uppercase text-slate-400">Create Task</div>
                <h3 className="mt-1 text-lg font-semibold text-slate-950">{activeAction.label}</h3>
              </div>
              <button type="button" onClick={() => setActiveAction(null)} className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition hover:text-slate-900">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-5 grid gap-4">
              <label className="grid gap-1 text-sm font-medium text-slate-700">
                Module
                <select value={config.module} onChange={(event) => setConfig((current) => ({ ...current, module: event.target.value }))} className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700">
                  {MODULES.map((module) => <option key={module} value={module}>{module}</option>)}
                </select>
              </label>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Limit
                  <input type="number" min="1" max="50" value={config.limit} onChange={(event) => setConfig((current) => ({ ...current, limit: event.target.value }))} className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-700" />
                </label>
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Priority
                  <select value={config.priority} onChange={(event) => setConfig((current) => ({ ...current, priority: event.target.value }))} className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700">
                    {PRIORITIES.map((priority) => <option key={priority} value={priority}>{priority}</option>)}
                  </select>
                </label>
              </div>
              <label className="grid gap-1 text-sm font-medium text-slate-700">
                Segment
                <input value={config.segment} onChange={(event) => setConfig((current) => ({ ...current, segment: event.target.value }))} className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-700" />
              </label>
              <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700">
                <input type="checkbox" checked={config.high_priority} onChange={(event) => setConfig((current) => ({ ...current, high_priority: event.target.checked }))} className="h-4 w-4 rounded border-slate-300" />
                High priority filter
              </label>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setActiveAction(null)} className="inline-flex h-10 items-center rounded-lg border border-slate-200 px-4 text-sm font-medium text-slate-700 transition hover:text-slate-950">Cancel</button>
              <button type="submit" className="inline-flex h-10 items-center gap-2 rounded-lg bg-blue-600 px-4 text-sm font-semibold text-white transition hover:bg-blue-700">
                <Play className="h-4 w-4" />
                Queue Task
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}