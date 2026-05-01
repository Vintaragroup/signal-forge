import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, FilePlus2, RefreshCw, RotateCcw, X } from "lucide-react";
import { api } from "../api.js";
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

function recordLabel(record) {
  if (!record) return "not linked";
  return record.name || record.recipient_name || record.company || record.company_name || record.subject_line || record._id || "linked";
}

function linkedSummary(item) {
  return [
    ["Contact", recordLabel(item.linked_contact)],
    ["Lead", recordLabel(item.linked_lead)],
    ["Message", recordLabel(item.linked_message)],
  ];
}

const DECISIONS = [
  { value: "approve", label: "Approve", icon: Check },
  { value: "reject", label: "Reject", icon: X },
  { value: "convert_to_draft", label: "Convert", icon: FilePlus2 },
  { value: "needs_revision", label: "Revise", icon: RotateCcw },
];

const VIEWS = [
  { value: "actionable", label: "Actionable" },
  { value: "all", label: "All" },
  { value: "gpt", label: "GPT" },
  { value: "system", label: "System Issues" },
  { value: "test", label: "Test / Synthetic" },
];

function classificationBadges(item) {
  const badges = [];
  if (item.is_test || item.request_origin === "test") badges.push("Test");
  if (item.request_origin === "gpt" || item.request_type?.startsWith("gpt_")) badges.push("GPT");
  if (item.request_origin === "system") badges.push("System");
  if (item.severity === "error") badges.push("Error");
  return badges;
}

function isSystemIssue(item) {
  return item.request_origin === "system" || item.severity === "error";
}

function isDiagnosticOnly(item) {
  return isSystemIssue(item) || item.is_test || item.request_origin === "test";
}

export default function ApprovalQueuePage() {
  const [items, setItems] = useState([]);
  const [view, setView] = useState("actionable");
  const [expanded, setExpanded] = useState({});
  const [notes, setNotes] = useState({});
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");

  const highlightedId = useMemo(() => {
    const query = window.location.hash.split("?")[1] || "";
    return new URLSearchParams(query).get("request") || "";
  }, []);

  async function loadQueue(nextView = view) {
    const params = { status: "open", view: nextView, limit: "200" };
    const data = await api.approvalRequests(params);
    setItems(data.items || []);
  }

  useEffect(() => {
    loadQueue();
  }, []);

  async function decide(item, decision) {
    setBusyId(item._id);
    setNotice("");
    try {
      const result = await api.decideApprovalRequest(item._id, { decision, note: notes[item._id] || "" });
      setNotice(result.message || "Approval decision saved. No outbound action taken.");
      await loadQueue();
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusyId("");
    }
  }

  const openCount = items.filter((item) => item.status === "open").length;
  const gptCount = items.filter((item) => item.request_origin === "gpt" || item.request_type?.startsWith("gpt_")).length;
  const systemItems = items.filter(isSystemIssue);
  const visibleItems = view === "system" ? items : items.filter((item) => !isSystemIssue(item));

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">Approval Queue</div>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">Human Review Requests</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">Internal workflow decisions only. No message, post, schedule, CRM sync, or external action is triggered here.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge value={`${openCount} open`} />
            <StatusBadge value={`${gptCount} gpt`} />
            {systemItems.length ? <StatusBadge value={`${systemItems.length} system issues`} /> : null}
            <select
              value={view}
              onChange={(event) => {
                setView(event.target.value);
                loadQueue(event.target.value);
              }}
              className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
            >
              {VIEWS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <button
              type="button"
              onClick={() => loadQueue()}
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>
      </section>

      {notice ? <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">{notice}</div> : null}

      {view !== "system" && systemItems.length ? (
        <section className="rounded-lg border border-red-200 bg-red-50 p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-red-950"><AlertTriangle className="h-4 w-4" />System / GPT Issues</div>
              <p className="mt-1 text-sm text-red-800">These are not operator approval tasks. Use the System Issues filter to inspect technical details.</p>
            </div>
            <button type="button" onClick={() => { setView("system"); loadQueue("system"); }} className="inline-flex h-9 items-center rounded-lg border border-red-200 bg-white px-3 text-sm font-medium text-red-800 transition hover:border-red-300">View issues</button>
          </div>
        </section>
      ) : null}

      <div className="space-y-3">
        {visibleItems.map((item) => (
          <section
            key={item._id}
            className={[
              "rounded-lg border bg-white p-4 shadow-sm",
              highlightedId === item._id ? "border-blue-300 ring-2 ring-blue-100" : "border-slate-200",
            ].join(" ")}
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge value={item.request_type} />
                  <StatusBadge value={item.status} />
                  {classificationBadges(item).map((badge) => <StatusBadge key={badge} value={badge} />)}
                  {item.gpt_confidence !== undefined ? <StatusBadge value={`confidence ${formatConfidence(item.gpt_confidence)}`} /> : null}
                </div>
                <h3 className="mt-3 text-base font-semibold text-slate-950">{item.title || item.request_type}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">{item.user_facing_summary || item.summary || "Human review is needed before manual action."}</p>
                <button type="button" onClick={() => setExpanded((current) => ({ ...current, [item._id]: !current[item._id] }))} className="mt-2 text-xs font-medium text-blue-700 transition hover:text-blue-900">
                  {expanded[item._id] ? "Hide technical reason" : "Show technical reason"}
                </button>
                {expanded[item._id] ? <p className="mt-2 rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-600">{item.technical_reason || item.reason_for_review || item.summary || "No technical reason recorded."}</p> : null}
              </div>
              <div className="text-right text-xs text-slate-500">
                <div>{formatDate(item.created_at)}</div>
                {item.run_id ? <a className="mt-2 inline-block text-blue-700 hover:text-blue-900" href={`#agents?run=${encodeURIComponent(item.run_id)}`}>Agent run</a> : null}
              </div>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-4">
              <div className="rounded-lg bg-slate-50 p-3">
                <div className="text-xs text-slate-500">Agent</div>
                <div className="mt-1 text-sm font-medium text-slate-900">{item.agent_name || "-"}</div>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <div className="text-xs text-slate-500">Module</div>
                <div className="mt-1 text-sm font-medium text-slate-900">{item.module || "-"}</div>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <div className="text-xs text-slate-500">Target</div>
                <div className="mt-1 text-sm font-medium text-slate-900">{item.target_type || "record"}: {item.target || "-"}</div>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <div className="text-xs text-slate-500">Confidence</div>
                <div className="mt-1 text-sm font-medium text-slate-900">{formatConfidence(item.gpt_confidence)}</div>
              </div>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-3">
              {linkedSummary(item).map(([label, value]) => (
                <div key={label} className="rounded-lg border border-slate-200 p-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</div>
                  <div className="mt-1 truncate text-sm text-slate-700">{value}</div>
                </div>
              ))}
            </div>

            {isDiagnosticOnly(item) ? (
              <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                Diagnostic-only item. Inspect the technical details, then use the source workflow for any real operator decision.
              </div>
            ) : (
              <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_auto]">
                <textarea
                  value={notes[item._id] || ""}
                  onChange={(event) => setNotes((current) => ({ ...current, [item._id]: event.target.value }))}
                  placeholder="Operator note"
                  className="min-h-20 rounded-lg border border-slate-200 p-3 text-sm text-slate-700 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                />
                <div className="flex flex-wrap content-start gap-2">
                  {DECISIONS.map((decision) => {
                    const Icon = decision.icon;
                    return (
                      <button
                        key={decision.value}
                        type="button"
                        disabled={busyId === item._id}
                        onClick={() => decide(item, decision.value)}
                        className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <Icon className="h-4 w-4" />
                        {decision.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </section>
        ))}
        {!visibleItems.length ? <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-500 shadow-sm">No approval requests match this view.</div> : null}
      </div>
    </div>
  );
}