import { useEffect, useMemo, useState } from "react";
import { Ban, Play, Plus, RefreshCw } from "lucide-react";
import { api } from "../api.js";
import StatusBadge from "../components/StatusBadge.jsx";

const AGENTS = ["outreach", "followup", "content", "fan_engagement"];
const MODULES = ["contractor_growth", "insurance_growth", "artist_growth", "media_growth"];

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

export default function AgentTasksPage() {
  const [tasks, setTasks] = useState([]);
  const [status, setStatus] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");
  const [form, setForm] = useState({
    agent_name: "outreach",
    module: "contractor_growth",
    task_type: "agent_dry_run",
    priority: 5,
    input_summary: "",
  });

  async function loadTasks(nextStatus = status) {
    const params = nextStatus ? { status: nextStatus, limit: "200" } : { limit: "200" };
    const data = await api.agentTasks(params);
    setTasks(data.items || []);
  }

  useEffect(() => {
    loadTasks();
  }, []);

  async function createTask(event) {
    event.preventDefault();
    setNotice("");
    let inputSummary = {};
    if (form.input_summary.trim()) {
      try {
        inputSummary = JSON.parse(form.input_summary);
      } catch (_error) {
        setNotice("Input summary must be valid JSON.");
        return;
      }
    }
    try {
      const result = await api.createAgentTask({
        agent_name: form.agent_name,
        module: form.module,
        task_type: form.task_type,
        priority: Number(form.priority),
        input_summary: inputSummary,
      });
      setNotice(result.message || "Agent task queued.");
      setForm((current) => ({ ...current, input_summary: "" }));
      await loadTasks();
    } catch (error) {
      setNotice(error.message);
    }
  }

  async function runTask(task) {
    setBusyId(task._id);
    setNotice("");
    try {
      const result = await api.runAgentTask(task._id);
      setNotice(result.message || "Agent task dry-run completed.");
      await loadTasks();
    } catch (error) {
      setNotice(error.message);
      await loadTasks();
    } finally {
      setBusyId("");
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
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">Agent Task Queue</div>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">Queue Safe Agent Dry-Runs</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">Tasks run the current dry-run/GPT-safe agent behavior only. They do not send, post, scrape, schedule, or call external platforms.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge value={`${stats.queued} queued`} />
            <StatusBadge value={`${stats.approvals} approvals`} />
            <StatusBadge value={`${stats.completed} completed`} />
            {stats.failed ? <StatusBadge value={`${stats.failed} failed`} /> : null}
          </div>
        </div>
      </section>

      {notice ? <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">{notice}</div> : null}

      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-950">Create Task</h3>
        <form onSubmit={createTask} className="mt-4 grid gap-3 lg:grid-cols-[1fr_1fr_1fr_120px]">
          <select value={form.agent_name} onChange={(event) => setForm((current) => ({ ...current, agent_name: event.target.value }))} className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700">
            {AGENTS.map((agent) => <option key={agent} value={agent}>{agent}</option>)}
          </select>
          <select value={form.module} onChange={(event) => setForm((current) => ({ ...current, module: event.target.value }))} className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700">
            {MODULES.map((module) => <option key={module} value={module}>{module}</option>)}
          </select>
          <input value={form.task_type} onChange={(event) => setForm((current) => ({ ...current, task_type: event.target.value }))} className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-700" />
          <input type="number" min="1" max="10" value={form.priority} onChange={(event) => setForm((current) => ({ ...current, priority: event.target.value }))} className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-700" />
          <textarea value={form.input_summary} onChange={(event) => setForm((current) => ({ ...current, input_summary: event.target.value }))} placeholder='Optional JSON input summary, e.g. {"limit": 5}' className="min-h-20 rounded-lg border border-slate-200 p-3 text-sm text-slate-700 lg:col-span-3" />
          <button type="submit" className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 text-sm font-medium text-white transition hover:bg-blue-700">
            <Plus className="h-4 w-4" />
            Queue
          </button>
        </form>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-slate-950">Tasks</h3>
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

        <div className="mt-4 space-y-3">
          {tasks.map((task) => (
            <div key={task._id} className="rounded-lg border border-slate-200 p-4">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge value={task.status} />
                    <StatusBadge value={task.task_type} />
                    <StatusBadge value={`priority ${task.priority}`} />
                  </div>
                  <div className="mt-3 text-sm font-semibold text-slate-950">{task.agent_name} / {task.module}</div>
                  <div className="mt-1 text-xs text-slate-500">Created {formatDate(task.created_at)} · Started {formatDate(task.started_at)} · Completed {formatDate(task.completed_at)}</div>
                  {task.error ? <div className="mt-2 text-sm text-red-700">{task.error}</div> : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  {task.linked_run_id ? <a href={`#agents?run=${encodeURIComponent(task.linked_run_id)}`} className="inline-flex h-9 items-center rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700">Agent Run</a> : null}
                  {task.status === "waiting_for_approval" ? <a href="#approvals" className="inline-flex h-9 items-center rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700">Approvals</a> : null}
                  <button type="button" disabled={busyId === task._id || ["running", "completed", "cancelled"].includes(task.status)} onClick={() => runTask(task)} className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
                    <Play className="h-4 w-4" />
                    Run
                  </button>
                  <button type="button" disabled={busyId === task._id || ["running", "completed", "cancelled"].includes(task.status)} onClick={() => cancelTask(task)} className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-700 transition hover:border-red-200 hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-60">
                    <Ban className="h-4 w-4" />
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          ))}
          {!tasks.length ? <div className="rounded-lg bg-slate-50 p-4 text-sm text-slate-500">No agent tasks match this view.</div> : null}
        </div>
      </section>
    </div>
  );
}