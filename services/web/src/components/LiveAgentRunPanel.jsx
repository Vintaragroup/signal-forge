import { AlertTriangle, CheckCircle2, ClipboardCheck, Clock3, FileText, RefreshCw, Sparkles } from "lucide-react";
import StatusBadge from "./StatusBadge.jsx";

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

function formatConfidence(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return String(value);
  return `${Math.round(numeric * 100)}%`;
}

function stepIcon(step, isLast, runStatus) {
  if (step?.status === "failed") return <AlertTriangle className="h-4 w-4 text-red-600" />;
  if (runStatus === "waiting_for_approval" && isLast) return <AlertTriangle className="h-4 w-4 text-amber-600" />;
  if (step?.status === "running") return <Clock3 className="h-4 w-4 animate-pulse text-blue-600" />;
  return <CheckCircle2 className="h-4 w-4 text-green-600" />;
}

function isGptStep(step) {
  return step?.step_name?.startsWith("gpt_") || step?.output?.used_gpt;
}

function outputTitle(item) {
  return item.subject_line || item.title || item.label || item.recipient_name || item.request_type || item.artifact_type || item._id;
}

function EmptyState({ children }) {
  return <div className="rounded-lg bg-slate-50 p-3 text-sm text-slate-500">{children}</div>;
}

export default function LiveAgentRunPanel({ task, runDetail, loading, onRefresh }) {
  const run = runDetail?.run;
  const steps = runDetail?.steps || [];
  const approvals = runDetail?.approval_requests || [];
  const artifacts = runDetail?.artifacts || [];
  const drafts = runDetail?.related?.messages || [];
  const status = task?.status || run?.status || (loading ? "running" : "queued");
  const agentName = task?.agent_name || run?.agent_name || "agent";
  const module = task?.module || run?.module || "module";
  const needsApproval = status === "waiting_for_approval" || approvals.some((item) => item.status === "open");
  const gptSteps = steps.filter(isGptStep);
  const latestGptStep = gptSteps[gptSteps.length - 1];
  const panelTone = needsApproval ? "border-amber-300 bg-amber-50/30" : "border-slate-200 bg-white";
  const runId = task?.linked_run_id || run?.run_id;

  return (
    <section className={`rounded-lg border p-5 shadow-sm transition-all duration-300 ${panelTone}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-xs font-semibold uppercase text-slate-400">Live Agent Run</div>
          <h2 className="mt-1 text-xl font-semibold text-slate-950">{agentName} / {module}</h2>
          <div className="mt-2 text-sm text-slate-600">Started {formatDate(task?.started_at || run?.started_at)} · Completed {formatDate(task?.completed_at || run?.completed_at)}</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge value={status} />
          {loading ? <StatusBadge value="refreshing" /> : null}
          {gptSteps.length ? <StatusBadge value="gpt reasoning" /> : null}
          {runId ? <a href={`#agents?run=${encodeURIComponent(runId)}`} className="inline-flex h-9 items-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700">Agent Console</a> : null}
          <button type="button" onClick={onRefresh} className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {needsApproval ? (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 transition-colors duration-300">
          <div className="font-semibold">Waiting for approval</div>
          <div className="mt-1">Review Outputs is ready for the generated approval requests.</div>
        </div>
      ) : null}

      {latestGptStep ? (
        <div className="mt-4 rounded-lg border border-purple-200 bg-purple-50 p-4">
          <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-purple-950">
            <Sparkles className="h-4 w-4" />
            GPT reasoning
            <StatusBadge value={`confidence ${formatConfidence(latestGptStep.output?.confidence)}`} />
          </div>
          <p className="mt-2 text-sm leading-6 text-purple-900">{latestGptStep.output?.reasoning_summary || latestGptStep.output?.error || "No reasoning summary recorded."}</p>
        </div>
      ) : null}

      <div className="mt-5 grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <div>
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-slate-950">Step Timeline</h3>
            <StatusBadge value={`${steps.length} steps`} />
          </div>
          <div className="space-y-3">
            {steps.map((step, index) => (
              <div key={step._id || `${step.step_number}-${step.step_name}`} className="rounded-lg border border-slate-200 bg-white p-3 transition duration-300 hover:border-blue-200">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5">{stepIcon(step, index === steps.length - 1, status)}</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="text-sm font-semibold text-slate-950">{step.step_name?.replaceAll("_", " ") || "Agent step"}</div>
                      {isGptStep(step) ? <StatusBadge value="gpt" /> : null}
                      <StatusBadge value={step.status || "completed"} />
                    </div>
                    <p className="mt-1 text-sm leading-6 text-slate-600">{step.decision || step.output?.summary || "Step completed."}</p>
                    {isGptStep(step) ? (
                      <div className="mt-2 text-xs leading-5 text-purple-800">
                        Confidence {formatConfidence(step.output?.confidence)} · {step.output?.reasoning_summary || step.output?.error || "No reasoning summary recorded."}
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            ))}
            {!steps.length ? <EmptyState>{loading ? "Waiting for step data..." : "No agent steps recorded yet."}</EmptyState> : null}
          </div>
        </div>

        <div>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-slate-950">Output Preview</h3>
            {(drafts.length || approvals.length || artifacts.length) ? <a href={approvals.length ? "#approvals" : "#messages"} className="inline-flex h-8 items-center rounded-lg bg-blue-600 px-3 text-xs font-semibold text-white transition hover:bg-blue-700">Review Outputs</a> : null}
          </div>
          <div className="grid gap-3">
            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-950"><FileText className="h-4 w-4 text-blue-600" /> Drafts created</div>
              <div className="mt-3 space-y-2">
                {drafts.map((item) => (
                  <div key={item._id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 p-2">
                    <div className="min-w-0 text-sm text-slate-700">{outputTitle(item)}</div>
                    <a href="#messages" className="inline-flex h-8 items-center rounded-lg border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700">Review Now</a>
                  </div>
                ))}
                {!drafts.length ? <EmptyState>No drafts created for this run.</EmptyState> : null}
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-950"><ClipboardCheck className="h-4 w-4 text-amber-600" /> Approval requests</div>
              <div className="mt-3 space-y-2">
                {approvals.map((item) => (
                  <div key={item._id} className="rounded-lg bg-amber-50 p-3 ring-1 ring-amber-100">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="text-sm font-medium text-amber-950">{outputTitle(item)}</div>
                      <StatusBadge value={item.status} />
                    </div>
                    <div className="mt-2 text-xs leading-5 text-amber-900">
                      Confidence {formatConfidence(item.gpt_confidence)} · {item.reason_for_review || item.summary || "Review requested."}
                    </div>
                    <a href={`#approvals?request=${encodeURIComponent(item._id)}`} className="mt-3 inline-flex h-8 items-center rounded-lg border border-amber-200 bg-white px-3 text-xs font-medium text-amber-800 transition hover:border-amber-300">Review Now</a>
                  </div>
                ))}
                {!approvals.length ? <EmptyState>No approval requests created.</EmptyState> : null}
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <div className="text-sm font-semibold text-slate-950">Artifacts</div>
              <div className="mt-3 space-y-2">
                {artifacts.map((item) => (
                  <div key={item._id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 p-2">
                    <div className="min-w-0 text-sm text-slate-700">{outputTitle(item)}</div>
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge value={item.artifact_type} />
                      <a href={approvals.length ? "#approvals" : "#messages"} className="inline-flex h-8 items-center rounded-lg border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700">Review Now</a>
                    </div>
                  </div>
                ))}
                {!artifacts.length ? <EmptyState>No artifacts recorded.</EmptyState> : null}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}