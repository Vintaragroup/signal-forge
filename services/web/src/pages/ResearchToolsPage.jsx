import { useEffect, useMemo, useState } from "react";
import { Check, RefreshCw, SearchCheck, Target, UserPlus, X } from "lucide-react";
import { api } from "../api.js";
import DataTable from "../components/DataTable.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const STATUS_FILTERS = ["", "needs_review", "approved", "rejected", "converted_to_contact", "converted_to_lead"];

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

function percent(value) {
  const number = Number(value || 0);
  return `${Math.round(number * 100)}%`;
}

export default function ResearchToolsPage() {
  const [toolRuns, setToolRuns] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [status, setStatus] = useState("needs_review");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");

  async function loadData(nextStatus = status) {
    const [runsData, candidatesData] = await Promise.all([
      api.toolRuns({ limit: "25" }),
      api.scrapedCandidates({ limit: "200", ...(nextStatus ? { status: nextStatus } : {}) }),
    ]);
    setToolRuns(runsData.items || []);
    setCandidates(candidatesData.items || []);
  }

  useEffect(() => {
    loadData();
  }, []);

  async function decide(candidate, decision) {
    setBusyId(candidate._id);
    setNotice("");
    try {
      const result = await api.decideScrapedCandidate(candidate._id, { decision, note: "Reviewed in Research / Tools." });
      setNotice(result.message || "Candidate decision recorded.");
      await loadData();
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusyId("");
    }
  }

  const stats = useMemo(
    () => ({
      visible: candidates.length,
      runs: toolRuns.length,
      review: candidates.filter((candidate) => candidate.status === "needs_review").length,
      converted: candidates.filter((candidate) => String(candidate.status || "").startsWith("converted_to_")).length,
    }),
    [candidates, toolRuns],
  );

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase text-slate-400">Read-only Research</div>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">Research / Tools</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">Tool outputs stay separate from human approvals until an operator reviews them here.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge value={`${stats.visible} visible`} />
            <StatusBadge value={`${stats.runs} tool_runs`} />
            <StatusBadge value={`${stats.review} needs_review`} />
            <StatusBadge value={`${stats.converted} converted`} />
          </div>
        </div>
      </section>

      {notice ? <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">{notice}</div> : null}

      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-950">Scraped Candidates</h3>
            <p className="mt-1 text-xs text-slate-500">Approving marks a candidate reviewed. Conversion creates a local contact or lead record only after this click.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <select
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                loadData(event.target.value);
              }}
              className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
            >
              {STATUS_FILTERS.map((value) => (
                <option key={value || "all"} value={value}>
                  {value || "all"}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => loadData()}
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>
        <DataTable
          columns={[
            { key: "company", label: "Candidate", render: (row) => <div className="font-medium text-slate-900">{row.company || row.name || "Research Candidate"}</div> },
            { key: "source_quality", label: "Source", render: (row) => <StatusBadge value={row.source_quality || "unknown"} /> },
            { key: "confidence", label: "Confidence", render: (row) => percent(row.confidence) },
            { key: "contact", label: "Public Contact", render: (row) => <span>{row.email || row.phone || "-"}</span> },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status || "needs_review"} /> },
            {
              key: "actions",
              label: "Actions",
              render: (row) => (
                <div className="flex flex-wrap gap-2">
                  <button type="button" disabled={busyId === row._id} onClick={() => decide(row, "approve")} className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 px-2 text-xs font-semibold text-slate-700 hover:border-green-200 hover:text-green-700 disabled:opacity-50">
                    <Check className="h-3.5 w-3.5" /> Approve
                  </button>
                  <button type="button" disabled={busyId === row._id} onClick={() => decide(row, "reject")} className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 px-2 text-xs font-semibold text-slate-700 hover:border-red-200 hover:text-red-700 disabled:opacity-50">
                    <X className="h-3.5 w-3.5" /> Reject
                  </button>
                  <button type="button" disabled={busyId === row._id} onClick={() => decide(row, "convert_to_contact")} className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 px-2 text-xs font-semibold text-slate-700 hover:border-blue-200 hover:text-blue-700 disabled:opacity-50">
                    <UserPlus className="h-3.5 w-3.5" /> Contact
                  </button>
                  <button type="button" disabled={busyId === row._id} onClick={() => decide(row, "convert_to_lead")} className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 px-2 text-xs font-semibold text-slate-700 hover:border-blue-200 hover:text-blue-700 disabled:opacity-50">
                    <Target className="h-3.5 w-3.5" /> Lead
                  </button>
                </div>
              ),
            },
          ]}
          rows={candidates}
          emptyMessage="No scraped candidates match this filter."
        />
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <SearchCheck className="h-4 w-4 text-blue-600" />
          <h3 className="text-sm font-semibold text-slate-950">Recent Tool Runs</h3>
        </div>
        <DataTable
          columns={[
            { key: "tool_name", label: "Tool", render: (row) => <span className="font-medium text-slate-900">{row.tool_name}</span> },
            { key: "mode", label: "Mode", render: (row) => <StatusBadge value={row.mode || "read_only"} /> },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> },
            { key: "created_at", label: "Created", render: (row) => formatDate(row.created_at) },
            { key: "outbound", label: "Outbound", render: (row) => row.outbound_actions_taken || 0 },
          ]}
          rows={toolRuns}
          emptyMessage="No tool runs recorded yet."
        />
      </section>
    </div>
  );
}
