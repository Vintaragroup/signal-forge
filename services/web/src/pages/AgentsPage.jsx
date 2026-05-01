import { useEffect, useMemo, useState } from "react";
import { Bot, Play, RefreshCw } from "lucide-react";
import { api } from "../api.js";
import AgentActivityCard from "../components/AgentActivityCard.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

function formatConfidence(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return String(value);
  return `${Math.round(numeric * 100)}%`;
}

function isGptStep(step) {
  return step?.step_name?.startsWith("gpt_");
}

function recordLabel(record) {
  if (!record) return "not linked";
  return record.name || record.recipient_name || record.company || record.company_name || record.subject_line || record._id || "linked";
}

function JsonBlock({ value }) {
  return (
    <pre className="max-h-64 overflow-auto rounded-lg bg-slate-950 p-3 text-xs leading-5 text-slate-100 scrollbar-soft">
      {JSON.stringify(value || {}, null, 2)}
    </pre>
  );
}

function Timeline({ steps }) {
  if (!steps?.length) {
    return <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">No agent steps recorded yet.</div>;
  }

  return (
    <div className="space-y-3">
      {steps.map((step) => (
        <div key={step._id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">Step {step.step_number}</div>
              <h3 className="mt-1 text-sm font-semibold text-slate-950">{step.step_name?.replaceAll("_", " ")}</h3>
              <p className="mt-2 text-sm leading-6 text-slate-600">{step.decision}</p>
            </div>
            <div className="flex flex-col items-end gap-2">
              <StatusBadge value={step.status} />
              <span className="text-xs text-slate-500">{formatDate(step.timestamp)}</span>
            </div>
          </div>
          {isGptStep(step) ? (
            <div className="mt-4 rounded-lg border border-purple-200 bg-purple-50 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge value="gpt step" />
                <StatusBadge value={step.output?.used_gpt ? "used gpt" : "gpt not used"} />
                <StatusBadge value={`confidence ${formatConfidence(step.output?.confidence)}`} />
              </div>
              <div className="mt-3 grid gap-2 text-sm text-purple-950 md:grid-cols-2">
                <div><span className="font-medium">Step:</span> {step.step_name}</div>
                <div><span className="font-medium">Output length:</span> {step.output?.output_length ?? "-"}</div>
                <div className="md:col-span-2"><span className="font-medium">Reasoning:</span> {step.output?.reasoning_summary || step.output?.error || "No reasoning summary recorded."}</div>
              </div>
            </div>
          ) : null}
          <div className="mt-4 grid gap-3 xl:grid-cols-2">
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Input</div>
              <JsonBlock value={step.input} />
            </div>
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Output</div>
              <JsonBlock value={step.output} />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function AgentsPage() {
  const [agents, setAgents] = useState([]);
  const [modules, setModules] = useState([]);
  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [selectedRun, setSelectedRun] = useState(null);
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState("");

  async function loadRuns(nextSelectedId = selectedRunId) {
    const data = await api.agents();
    const runData = await api.agentRuns({ limit: "50" });
    const nextRuns = runData.items || data.runs || [];
    setAgents(data.items || []);
    setModules(data.modules || []);
    setRuns(nextRuns);
    const nextId = nextSelectedId || nextRuns[0]?.run_id || "";
    setSelectedRunId(nextId);
    if (nextId) {
      const detail = await api.agentRunDetail(nextId);
      setSelectedRun(detail);
    } else {
      setSelectedRun(null);
    }
  }

  useEffect(() => {
    loadRuns();
  }, []);

  useEffect(() => {
    if (!selectedRunId) return;
    api.agentRunDetail(selectedRunId).then(setSelectedRun).catch(() => setSelectedRun(null));
  }, [selectedRunId]);

  async function runAgent(agent, module) {
    setRunning(true);
    setNotice("");
    try {
      const result = await api.runAgent({ agent, module, dry_run: true, limit: 10 });
      setNotice(`${result.message} Run ID: ${result.run?.run_id || result.result?.run_id}`);
      await loadRuns(result.run?.run_id || result.result?.run_id);
    } catch (error) {
      setNotice(error.message);
    } finally {
      setRunning(false);
    }
  }

  const run = selectedRun?.run;
  const steps = selectedRun?.steps || [];
  const approvals = selectedRun?.approval_requests || [];
  const artifacts = selectedRun?.artifacts || [];
  const related = selectedRun?.related || {};
  const openApprovalCount = approvals.filter((item) => item.status === "open").length;
  const gptSteps = steps.filter(isGptStep);
  const gptApprovals = approvals.filter((item) => item.request_type?.startsWith("gpt_"));
  const gptDrafts = (related.messages || []).filter((item) => item.source === "gpt");
  const gptArtifacts = artifacts.filter((item) => item.artifact_type?.startsWith("gpt_"));
  const usedGpt = gptSteps.some((step) => step.output?.used_gpt);
  const gptOutcome = gptDrafts.length
    ? `${gptDrafts.length} draft${gptDrafts.length === 1 ? "" : "s"}`
    : gptArtifacts.length
      ? `${gptArtifacts.length} recommendation${gptArtifacts.length === 1 ? "" : "s"}`
    : gptApprovals.length
      ? `${gptApprovals.length} approval${gptApprovals.length === 1 ? "" : "s"}`
      : gptSteps.length
        ? "no draft"
        : "not used";

  const runStats = useMemo(
    () => ({
      total: runs.length,
      running: runs.filter((item) => item.status === "running").length,
      approvals: runs.filter((item) => item.status === "waiting_for_approval").length,
      failed: runs.filter((item) => item.status === "failed").length,
    }),
    [runs],
  );

  return (
    <div className="space-y-5">
      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
        {agents.map((agent) => (
          <AgentActivityCard key={agent.name} agent={agent} modules={modules} onRun={runAgent} running={running} />
        ))}
      </div>

      {notice ? <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">{notice}</div> : null}

      <div className="grid gap-5 xl:grid-cols-[0.72fr_1.28fr]">
        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-950">Agent Runs</h2>
              <p className="mt-1 text-sm text-slate-500">Simulation-only process history from MongoDB.</p>
            </div>
            <button
              type="button"
              onClick={() => loadRuns()}
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>

          <div className="mt-4 grid grid-cols-4 gap-2">
            <div className="rounded-lg bg-slate-50 p-3">
              <div className="text-xs text-slate-500">Runs</div>
              <div className="mt-1 text-lg font-semibold text-slate-950">{runStats.total}</div>
            </div>
            <div className="rounded-lg bg-blue-50 p-3">
              <div className="text-xs text-blue-700">Running</div>
              <div className="mt-1 text-lg font-semibold text-blue-900">{runStats.running}</div>
            </div>
            <div className="rounded-lg bg-amber-50 p-3">
              <div className="text-xs text-amber-700">Approval</div>
              <div className="mt-1 text-lg font-semibold text-amber-900">{runStats.approvals}</div>
            </div>
            <div className="rounded-lg bg-red-50 p-3">
              <div className="text-xs text-red-700">Failed</div>
              <div className="mt-1 text-lg font-semibold text-red-900">{runStats.failed}</div>
            </div>
          </div>

          <div className="mt-4 max-h-[680px] space-y-2 overflow-y-auto pr-1 scrollbar-soft">
            {runs.map((item) => (
              <button
                type="button"
                key={item.run_id}
                onClick={() => setSelectedRunId(item.run_id)}
                className={[
                  "w-full rounded-lg border p-3 text-left transition",
                  selectedRunId === item.run_id ? "border-blue-300 bg-blue-50" : "border-slate-200 bg-white hover:bg-slate-50",
                ].join(" ")}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
                      <Bot className="h-4 w-4 text-blue-600" />
                      {item.agent_name}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">{item.module}</div>
                  </div>
                  <StatusBadge value={item.status} />
                </div>
                <div className="mt-2 text-xs text-slate-500">{formatDate(item.started_at)}</div>
                <div className="mt-2 line-clamp-2 text-xs text-slate-600">{item.output_summary?.log_path || item.run_id}</div>
              </button>
            ))}
            {!runs.length ? <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">Run an agent to create the first observed run.</div> : null}
          </div>
        </section>

        <section className="space-y-5">
          {run ? (
            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">Selected Run</div>
                  <h2 className="mt-1 text-xl font-semibold text-slate-950">{run.agent_name} / {run.module}</h2>
                  <p className="mt-2 text-sm text-slate-600">{run.agent_role}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <StatusBadge value={run.status} />
                  <StatusBadge value="simulation_only" />
                  <StatusBadge value={usedGpt ? "used gpt" : "gpt not used"} />
                  {openApprovalCount ? <StatusBadge value={`${openApprovalCount} approvals`} /> : null}
                </div>
              </div>

              <div className="mt-5 grid gap-3 md:grid-cols-5">
                <div className="rounded-lg bg-slate-50 p-3">
                  <div className="text-xs text-slate-500">Started</div>
                  <div className="mt-1 text-sm font-medium text-slate-900">{formatDate(run.started_at)}</div>
                </div>
                <div className="rounded-lg bg-slate-50 p-3">
                  <div className="text-xs text-slate-500">Completed</div>
                  <div className="mt-1 text-sm font-medium text-slate-900">{formatDate(run.completed_at)}</div>
                </div>
                <div className="rounded-lg bg-slate-50 p-3">
                  <div className="text-xs text-slate-500">Contacts</div>
                  <div className="mt-1 text-sm font-medium text-slate-900">{run.related_contacts?.length || 0}</div>
                </div>
                <div className="rounded-lg bg-slate-50 p-3">
                  <div className="text-xs text-slate-500">Messages</div>
                  <div className="mt-1 text-sm font-medium text-slate-900">{run.related_messages?.length || 0}</div>
                </div>
                <div className="rounded-lg bg-purple-50 p-3">
                  <div className="text-xs text-purple-700">GPT</div>
                  <div className="mt-1 text-sm font-medium text-purple-950">{gptOutcome}</div>
                </div>
              </div>

              {gptSteps.length ? (
                <div className="mt-4 rounded-lg border border-purple-200 bg-purple-50 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h3 className="text-sm font-semibold text-purple-950">GPT Activity</h3>
                    <div className="flex flex-wrap gap-2">
                      <StatusBadge value={usedGpt ? "used gpt" : "gpt not used"} />
                      <StatusBadge value={gptOutcome} />
                    </div>
                  </div>
                  <div className="mt-3 grid gap-3 md:grid-cols-3">
                    {gptSteps.map((step) => (
                      <div key={step._id} className="rounded-lg bg-white/70 p-3 text-sm text-purple-950 ring-1 ring-purple-100">
                        <div className="text-xs font-semibold uppercase tracking-wide text-purple-700">{step.step_name}</div>
                        <div className="mt-2">Confidence: {formatConfidence(step.output?.confidence)}</div>
                        <div className="mt-1 line-clamp-3 text-purple-800">{step.output?.reasoning_summary || step.output?.error || "No reasoning summary recorded."}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="grid gap-5 xl:grid-cols-2">
            <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-950">Inputs Used</h2>
              <div className="mt-3">
                <JsonBlock value={run?.input_summary} />
              </div>
            </section>
            <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-950">Final Outputs</h2>
              <div className="mt-3">
                <JsonBlock value={run?.output_summary} />
              </div>
            </section>
          </div>

          <section>
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-slate-950">Step Timeline</h2>
              <StatusBadge value={`${steps.length} steps`} />
            </div>
            <Timeline steps={steps} />
          </section>

          <div className="grid gap-5 xl:grid-cols-2">
            <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-950">Human Approvals Needed</h2>
              <div className="mt-3 space-y-2">
                {approvals.map((item) => (
                  <div key={item._id} className={["rounded-lg border p-3", item.request_type?.startsWith("gpt_") ? "border-purple-200 bg-purple-50" : "border-slate-200"].join(" ")}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-slate-900">{item.title}</div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <StatusBadge value={item.request_type} />
                          {item.request_type?.startsWith("gpt_") ? <StatusBadge value={`confidence ${formatConfidence(item.gpt_confidence)}`} /> : null}
                        </div>
                      </div>
                      <StatusBadge value={item.status} />
                    </div>
                    <p className="mt-2 text-sm text-slate-600">{item.reason_for_review || item.summary || item.target}</p>
                    {item.request_type?.startsWith("gpt_") ? (
                      <div className="mt-3 grid gap-2 text-xs text-slate-600 md:grid-cols-3">
                        <div><span className="font-medium text-slate-800">Target:</span> {item.target_type || "record"} {item.target || "-"}</div>
                        <div><span className="font-medium text-slate-800">Contact:</span> {recordLabel(item.linked_contact)}</div>
                        <div><span className="font-medium text-slate-800">Lead:</span> {recordLabel(item.linked_lead)}</div>
                        <div className="md:col-span-3"><span className="font-medium text-slate-800">Message:</span> {recordLabel(item.linked_message)}</div>
                      </div>
                    ) : null}
                  </div>
                ))}
                {!approvals.length ? <div className="text-sm text-slate-500">No approval requests were created for this run.</div> : null}
              </div>
            </section>

            <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-950">Artifacts And Links</h2>
              <div className="mt-3 space-y-2">
                {artifacts.map((item) => (
                  <div key={item._id} className="rounded-lg border border-slate-200 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-sm font-medium text-slate-900">{item.label}</div>
                      <StatusBadge value={item.artifact_type} />
                    </div>
                    <div className="mt-2 text-xs text-slate-500">{item.path || item._id}</div>
                  </div>
                ))}
                {!artifacts.length ? <div className="text-sm text-slate-500">No artifacts recorded.</div> : null}
              </div>
            </section>
          </div>

          <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-950">Related Records</h2>
            <div className="mt-3 grid gap-3 md:grid-cols-4">
              {[
                ["Contacts", related.contacts || []],
                ["Leads", related.leads || []],
                ["Messages", related.messages || []],
                ["Deals", related.deals || []],
              ].map(([label, items]) => (
                <div key={label} className="rounded-lg bg-slate-50 p-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</div>
                  <div className="mt-2 text-2xl font-semibold text-slate-950">{items.length}</div>
                  <div className="mt-2 space-y-1">
                    {items.slice(0, 4).map((item) => (
                      <div key={item._id} className="truncate text-xs text-slate-600">
                        {item.name || item.recipient_name || item.company || item.company_name || item.outcome || item._id}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {run?.errors?.length || run?.warnings?.length ? (
            <section className="rounded-lg border border-amber-200 bg-amber-50 p-4">
              <h2 className="text-sm font-semibold text-amber-950">Errors / Warnings</h2>
              <div className="mt-3 space-y-2 text-sm text-amber-900">
                {(run.errors || []).map((error) => <div key={error}>{error}</div>)}
                {(run.warnings || []).map((warning) => <div key={warning}>{warning}</div>)}
              </div>
            </section>
          ) : null}
        </section>
      </div>
    </div>
  );
}
