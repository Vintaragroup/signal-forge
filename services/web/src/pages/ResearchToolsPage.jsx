import { useEffect, useMemo, useState } from "react";
import { Check, RefreshCw, SearchCheck, Target, Upload, UserPlus, X } from "lucide-react";
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

function compactJson(value) {
  const json = JSON.stringify(value || {}, null, 2);
  return json.length > 260 ? `${json.slice(0, 260)}...` : json;
}

function displayBusinessType(row) {
  return row.service_category || row.extracted_fields?.service_category || row.enrichment_fields?.business_type || "";
}

export default function ResearchToolsPage() {
  const [toolRuns, setToolRuns] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [status, setStatus] = useState("needs_review");
  const [showDuplicates, setShowDuplicates] = useState(false);
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");
  const [researchForm, setResearchForm] = useState({ query: "Austin roofing contractors", module: "contractor_growth", location: "Austin, TX", limit: 2 });
  const [runningResearch, setRunningResearch] = useState(false);
  const [importForm, setImportForm] = useState({ module: "contractor_growth", source_label: "manual_upload", csv_path: "" });
  const [importFile, setImportFile] = useState(null);
  const [runningImport, setRunningImport] = useState(false);

  async function loadData(nextStatus = status, nextShowDuplicates = showDuplicates) {
    const [runsData, candidatesData] = await Promise.all([
      api.toolRuns({ limit: "25" }),
      api.scrapedCandidates({ limit: "200", include_duplicates: nextShowDuplicates ? "true" : "false", ...(nextStatus ? { status: nextStatus } : {}) }),
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

  async function runResearch(event) {
    event.preventDefault();
    setRunningResearch(true);
    setNotice("");
    try {
      const result = await api.runWebSearchTool({ ...researchForm, limit: Number(researchForm.limit) || 2 });
      setNotice(`${result.message} Candidates created: ${(result.candidate_ids || []).length}.`);
      setStatus("needs_review");
      await loadData("needs_review", showDuplicates);
    } catch (error) {
      setNotice(error.message);
    } finally {
      setRunningResearch(false);
    }
  }

  async function importCandidates(event) {
    event.preventDefault();
    setRunningImport(true);
    setNotice("");
    try {
      const formData = new FormData();
      formData.append("module", importForm.module);
      formData.append("source_label", importForm.source_label || "manual_upload");
      if (importFile) {
        formData.append("file", importFile);
      } else {
        formData.append("csv_path", importForm.csv_path);
      }
      const result = await api.importCandidates(formData);
      setNotice(`${result.message} Imported: ${result.candidate_count || 0}. Duplicates: ${result.duplicate_count || 0}.`);
      setStatus("needs_review");
      await loadData("needs_review", showDuplicates);
    } catch (error) {
      setNotice(error.message);
    } finally {
      setRunningImport(false);
    }
  }

  const stats = useMemo(
    () => ({
      visible: candidates.length,
      runs: toolRuns.length,
      review: candidates.filter((candidate) => candidate.status === "needs_review").length,
      converted: candidates.filter((candidate) => String(candidate.status || "").startsWith("converted_to_")).length,
      duplicates: candidates.filter((candidate) => candidate.is_duplicate).length,
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
            <p className="mt-2 text-sm leading-6 text-slate-600">Tool outputs create review records and approval requests before any local conversion.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge value={`${stats.visible} visible`} />
            <StatusBadge value={`${stats.runs} tool_runs`} />
            <StatusBadge value={`${stats.review} needs_review`} />
            <StatusBadge value={`${stats.converted} converted`} />
            <StatusBadge value={`${stats.duplicates} duplicates`} />
          </div>
        </div>
      </section>

      {notice ? <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">{notice}</div> : null}

      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-950">Run Mock Research</h3>
            <p className="mt-1 text-xs text-slate-500">Creates read-only tool runs, candidates, artifacts, and approvals for operator review.</p>
          </div>
          <StatusBadge value="mock read only" />
        </div>
        <form onSubmit={runResearch} className="grid gap-3 lg:grid-cols-[1.5fr_1fr_1fr_0.4fr_auto]">
          <input
            value={researchForm.query}
            onChange={(event) => setResearchForm((current) => ({ ...current, query: event.target.value }))}
            className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-800"
            placeholder="Search query"
          />
          <select
            value={researchForm.module}
            onChange={(event) => setResearchForm((current) => ({ ...current, module: event.target.value }))}
            className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800"
          >
            <option value="contractor_growth">contractor_growth</option>
            <option value="insurance_growth">insurance_growth</option>
            <option value="artist_growth">artist_growth</option>
            <option value="media_growth">media_growth</option>
          </select>
          <input
            value={researchForm.location}
            onChange={(event) => setResearchForm((current) => ({ ...current, location: event.target.value }))}
            className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-800"
            placeholder="Location"
          />
          <input
            type="number"
            min="1"
            max="25"
            value={researchForm.limit}
            onChange={(event) => setResearchForm((current) => ({ ...current, limit: event.target.value }))}
            className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-800"
          />
          <button type="submit" disabled={runningResearch} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-slate-950 px-4 text-sm font-medium text-white transition hover:bg-blue-700 disabled:bg-slate-300">
            <SearchCheck className="h-4 w-4" />
            Run
          </button>
        </form>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-950">Import CSV</h3>
            <p className="mt-1 text-xs text-slate-500">Imports real source lists into the same review-only candidate flow.</p>
          </div>
          <StatusBadge value="manual upload" />
        </div>
        <form onSubmit={importCandidates} className="grid gap-3 lg:grid-cols-[1fr_1fr_1.2fr_auto]">
          <select
            value={importForm.module}
            onChange={(event) => setImportForm((current) => ({ ...current, module: event.target.value }))}
            className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800"
          >
            <option value="contractor_growth">contractor_growth</option>
            <option value="insurance_growth">insurance_growth</option>
            <option value="artist_growth">artist_growth</option>
            <option value="media_growth">media_growth</option>
          </select>
          <input
            value={importForm.source_label}
            onChange={(event) => setImportForm((current) => ({ ...current, source_label: event.target.value }))}
            className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-800"
            placeholder="Source label"
          />
          <div className="grid gap-2 md:grid-cols-2">
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => setImportFile(event.target.files?.[0] || null)}
              className="h-10 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800"
            />
            <input
              value={importForm.csv_path}
              onChange={(event) => setImportForm((current) => ({ ...current, csv_path: event.target.value }))}
              className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-800"
              placeholder="data/imports/contractor_sources.csv"
            />
          </div>
          <button type="submit" disabled={runningImport || (!importFile && !importForm.csv_path.trim())} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-slate-950 px-4 text-sm font-medium text-white transition hover:bg-blue-700 disabled:bg-slate-300">
            <Upload className="h-4 w-4" />
            Import
          </button>
        </form>
        <div className="mt-3 text-xs text-slate-500">
          Selected: {importFile?.name || importForm.csv_path || "No CSV selected"}
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-950">Scraped Candidates</h3>
            <p className="mt-1 text-xs text-slate-500">Approve a candidate first, then convert it locally when it is ready for the pipeline.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <select
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                loadData(event.target.value, showDuplicates);
              }}
              className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
            >
              {STATUS_FILTERS.map((value) => (
                <option key={value || "all"} value={value}>
                  {value || "all"}
                </option>
              ))}
            </select>
            <label className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700">
              <input
                type="checkbox"
                checked={showDuplicates}
                onChange={(event) => {
                  setShowDuplicates(event.target.checked);
                  loadData(status, event.target.checked);
                }}
                className="h-4 w-4 rounded border-slate-300"
              />
              Duplicates
            </label>
            <button
              type="button"
              onClick={() => loadData(status, showDuplicates)}
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>
        <DataTable
          columns={[
            { key: "company", label: "Candidate", render: (row) => (
              <div className="space-y-1">
                <div className="font-medium text-slate-900">{row.company || row.name || "Research Candidate"}</div>
                <div className="flex flex-wrap gap-1">
                  {row.is_duplicate ? <StatusBadge value="duplicate" /> : null}
                  {displayBusinessType(row) ? <StatusBadge value={displayBusinessType(row)} /> : null}
                </div>
                {row.is_duplicate ? <div className="text-xs text-amber-700">Duplicate: {(row.duplicate_reasons || []).join(", ") || "matched existing record"}</div> : null}
              </div>
            ) },
            { key: "source_quality", label: "Source", render: (row) => <StatusBadge value={row.source_quality || "unknown"} /> },
            { key: "source_url", label: "URL", render: (row) => row.source_url ? <a href={row.source_url} className="max-w-52 truncate text-blue-700 hover:underline" target="_blank" rel="noreferrer">{row.source_url}</a> : "-" },
            { key: "location", label: "Location", render: (row) => [row.enrichment_fields?.city || row.city, row.enrichment_fields?.state || row.state].filter(Boolean).join(", ") || "-" },
            { key: "quality", label: "Quality", render: (row) => <span className="font-semibold text-slate-900">{Number(row.quality_score || 0)}/100</span> },
            { key: "completeness", label: "Complete", render: (row) => <StatusBadge value={percent(row.completeness_score)} /> },
            { key: "fields", label: "Extracted Fields", render: (row) => <pre className="max-w-72 whitespace-pre-wrap text-xs text-slate-600">{compactJson(row.extracted_fields)}</pre> },
            { key: "confidence", label: "Confidence", render: (row) => percent(row.confidence) },
            { key: "contact", label: "Public Contact", render: (row) => <span>{row.email || row.phone || "-"}</span> },
            { key: "approval", label: "Approval", render: (row) => row.approval_request_id ? <a href={`#approvals?request=${encodeURIComponent(row.approval_request_id)}`} className="text-blue-700 hover:underline">Open</a> : "-" },
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
                  <button type="button" disabled={busyId === row._id || row.status !== "approved"} onClick={() => decide(row, "convert_to_contact")} className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 px-2 text-xs font-semibold text-slate-700 hover:border-blue-200 hover:text-blue-700 disabled:opacity-50">
                    <UserPlus className="h-3.5 w-3.5" /> Contact
                  </button>
                  <button type="button" disabled={busyId === row._id || row.status !== "approved"} onClick={() => decide(row, "convert_to_lead")} className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 px-2 text-xs font-semibold text-slate-700 hover:border-blue-200 hover:text-blue-700 disabled:opacity-50">
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
            { key: "input", label: "Input", render: (row) => <pre className="max-w-72 whitespace-pre-wrap text-xs text-slate-600">{compactJson(row.input)}</pre> },
            { key: "mode", label: "Mode", render: (row) => <StatusBadge value={row.mode || "read_only"} /> },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> },
            { key: "source_url", label: "Source URL", render: (row) => row.source_url ? <a href={row.source_url} className="max-w-52 truncate text-blue-700 hover:underline" target="_blank" rel="noreferrer">{row.source_url}</a> : "-" },
            { key: "fields", label: "Extracted Fields", render: (row) => <pre className="max-w-72 whitespace-pre-wrap text-xs text-slate-600">{compactJson(row.extracted_fields)}</pre> },
            { key: "agent", label: "Agent Run", render: (row) => row.linked_agent_run_id ? <a href={`#agents?run=${encodeURIComponent(row.linked_agent_run_id)}`} className="text-blue-700 hover:underline">Open</a> : "-" },
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
