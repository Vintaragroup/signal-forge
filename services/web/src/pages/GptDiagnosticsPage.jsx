import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw, Terminal, XCircle } from "lucide-react";
import { api } from "../api.js";
import StatusBadge from "../components/StatusBadge.jsx";

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "None recorded";
}


function boolLabel(value) {
  return value ? "yes" : "no";
}

function Stat({ label, value, tone }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-semibold uppercase text-slate-400">{label}</div>
      <div className={['mt-2 text-lg font-semibold', tone || 'text-slate-950'].join(' ')}>{value}</div>
    </div>
  );
}

export default function GptDiagnosticsPage() {
  const [diagnostics, setDiagnostics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadDiagnostics() {
    setLoading(true);
    setError("");
    try {
      const data = await api.gptDiagnostics();
      setDiagnostics(data);
    } catch (nextError) {
      setError(nextError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDiagnostics();
  }, []);

  const recentSteps = diagnostics?.recent_gpt_agent_steps || [];
  const recentErrors = diagnostics?.recent_system_approval_errors || [];
  const keyPresent = diagnostics?.has_api_key;
  const enabled = diagnostics?.gpt_agent_enabled;

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase text-slate-400">GPT Diagnostics v1</div>
            <h2 className="mt-1 text-2xl font-semibold text-slate-950">Runtime Configuration</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">Read-only diagnostics for GPT configuration, recent safe GPT steps, and GPT-related system approval errors.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge value="no secrets" />
            <StatusBadge value="no outbound automation" />
            <button type="button" onClick={loadDiagnostics} className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700">
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>
      </section>

      {error ? <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div> : null}
      {loading ? <div className="rounded-lg border border-slate-200 bg-white p-5 text-sm text-slate-500 shadow-sm">Loading GPT diagnostics...</div> : null}

      {diagnostics ? (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <Stat label="GPT enabled" value={boolLabel(enabled)} tone={enabled ? "text-green-700" : "text-slate-700"} />
            <Stat label="Model" value={diagnostics.openai_model || "not set"} />
            <Stat label="API key present" value={boolLabel(keyPresent)} tone={keyPresent ? "text-green-700" : "text-amber-700"} />
            <Stat label="Client available" value={boolLabel(diagnostics.client_available)} tone={diagnostics.client_available ? "text-green-700" : "text-red-700"} />
          </div>

          <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-slate-950">Last GPT Activity</h3>
                <p className="mt-1 text-sm text-slate-600">Summaries are derived from sanitized agent step metadata.</p>
              </div>
              <StatusBadge value={`api key ${diagnostics.api_key_source}`} />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="inline-flex items-center gap-2 text-sm font-semibold text-green-800"><CheckCircle2 className="h-4 w-4" />Last success</div>
                <div className="mt-2 text-sm text-slate-700">{formatDate(diagnostics.last_successful_gpt_call_at)}</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="inline-flex items-center gap-2 text-sm font-semibold text-red-800"><XCircle className="h-4 w-4" />Last error</div>
                <div className="mt-2 text-sm text-slate-700">{diagnostics.last_gpt_error_summary || "None recorded"}</div>
                <div className="mt-1 text-xs text-slate-500">{formatDate(diagnostics.last_gpt_error_at)}</div>
              </div>
            </div>
          </section>

          <section className="rounded-lg border border-blue-200 bg-blue-50 p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="inline-flex items-center gap-2 text-sm font-semibold text-blue-950"><Terminal className="h-4 w-4" />Safe Live Test</div>
                <p className="mt-2 text-sm leading-6 text-blue-900">Run from Docker only when you want to call OpenAI with the minimal diagnostic prompt.</p>
              </div>
              <code className="max-w-full rounded-lg bg-white px-3 py-2 text-xs text-blue-950 ring-1 ring-blue-200">docker compose run --rm api python scripts/gpt_diagnostics.py --live-test</code>
            </div>
          </section>

          <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-lg font-semibold text-slate-950">Recent GPT Steps</h3>
              <StatusBadge value={`${recentSteps.length} steps`} />
            </div>
            <div className="overflow-hidden rounded-lg border border-slate-200">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-500">
                  <tr><th className="px-4 py-3">When</th><th className="px-4 py-3">Step</th><th className="px-4 py-3">Agent</th><th className="px-4 py-3">Confidence</th><th className="px-4 py-3">Result</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {recentSteps.map((step, index) => (
                    <tr key={`${step.run_id}-${step.step_name}-${index}`}>
                      <td className="px-4 py-3 text-slate-500">{formatDate(step.timestamp)}</td>
                      <td className="px-4 py-3 font-medium text-slate-900">{step.step_name}</td>
                      <td className="px-4 py-3 text-slate-600">{step.agent_name || "-"}</td>
                      <td className="px-4 py-3 text-slate-600">{step.confidence ?? "-"}</td>
                      <td className="px-4 py-3 text-slate-600">{step.error || step.reasoning_summary || "No summary recorded"}</td>
                    </tr>
                  ))}
                  {!recentSteps.length ? <tr><td colSpan="5" className="px-4 py-5 text-slate-500">No GPT steps recorded.</td></tr> : null}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-lg font-semibold text-slate-950">GPT System Approval Errors</h3>
              <StatusBadge value={`${recentErrors.length} errors`} />
            </div>
            <div className="space-y-3">
              {recentErrors.map((item) => (
                <article key={item._id} className="rounded-lg border border-red-200 bg-red-50 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="inline-flex items-center gap-2 text-sm font-semibold text-red-950"><AlertTriangle className="h-4 w-4" />{item.title || item.request_type}</div>
                      <p className="mt-2 text-sm leading-6 text-red-900">{item.user_facing_summary || item.technical_reason || "System issue recorded."}</p>
                    </div>
                    <StatusBadge value={item.severity || "error"} />
                  </div>
                  <div className="mt-2 text-xs text-red-800">{formatDate(item.created_at)}</div>
                </article>
              ))}
              {!recentErrors.length ? <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">No GPT-related system approval errors recorded.</div> : null}
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}