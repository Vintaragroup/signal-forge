import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, ChevronDown, ChevronRight, FileText, RefreshCw, SearchCheck, Target, Upload, UserPlus, X } from "lucide-react";
import { api } from "../api.js";
import DataTable from "../components/DataTable.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const STATUS_FILTERS = ["", "needs_review", "approved", "rejected", "converted_to_contact", "converted_to_lead"];
const MODULE_OPTIONS = ["", "contractor_growth", "insurance_growth", "artist_growth", "media_growth"];
const BULK_ACTIONS = [
  { action: "approve", label: "Approve", confirm: false },
  { action: "reject", label: "Reject", confirm: false },
  { action: "convert_to_contact", label: "→ Contact", confirm: true },
  { action: "convert_to_lead", label: "→ Lead", confirm: true },
];

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
  const [filterSourceLabel, setFilterSourceLabel] = useState("");
  const [filterModule, setFilterModule] = useState("");
  const [filterMinQuality, setFilterMinQuality] = useState("");
  const [filterMaxQuality, setFilterMaxQuality] = useState("");
  const [filterConverted, setFilterConverted] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");
  const [researchForm, setResearchForm] = useState({ query: "Austin roofing contractors", module: "contractor_growth", location: "Austin, TX", limit: 2 });
  const [runningResearch, setRunningResearch] = useState(false);
  const [importForm, setImportForm] = useState({ module: "contractor_growth", source_label: "manual_upload", csv_path: "" });
  const [importFile, setImportFile] = useState(null);
  const [runningImport, setRunningImport] = useState(false);

  // Bulk action state
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkConfirm, setBulkConfirm] = useState(null);

  // Import history state
  const [importHistoryRuns, setImportHistoryRuns] = useState([]);
  const [expandedRunId, setExpandedRunId] = useState(null);
  const [historyDetail, setHistoryDetail] = useState({});
  const [loadingDetail, setLoadingDetail] = useState(null);

  function buildCandidateParams(nextStatus, nextShowDuplicates) {
    const params = { limit: "200", include_duplicates: nextShowDuplicates ? "true" : "false" };
    if (nextStatus) params.status = nextStatus;
    if (filterSourceLabel.trim()) params.source_label = filterSourceLabel.trim();
    if (filterModule) params.module = filterModule;
    if (filterMinQuality !== "") params.min_quality = filterMinQuality;
    if (filterMaxQuality !== "") params.max_quality = filterMaxQuality;
    if (filterConverted === "converted") params.converted = "true";
    else if (filterConverted === "not_converted") params.converted = "false";
    return params;
  }

  const loadData = useCallback(
    async (nextStatus = status, nextShowDuplicates = showDuplicates) => {
      const [runsData, candidatesData, historyData] = await Promise.all([
        api.toolRuns({ limit: "25" }),
        api.scrapedCandidates(buildCandidateParams(nextStatus, nextShowDuplicates)),
        api.importHistory({ limit: "25" }),
      ]);
      setToolRuns(runsData.items || []);
      setCandidates(candidatesData.items || []);
      setImportHistoryRuns(historyData.items || []);
      setSelectedIds(new Set());
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [status, showDuplicates, filterSourceLabel, filterModule, filterMinQuality, filterMaxQuality, filterConverted],
  );

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function applyFilters() {
    await loadData(status, showDuplicates);
  }

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

  async function executeBulkAction(action) {
    setBulkConfirm(null);
    setBulkBusy(true);
    setNotice("");
    try {
      const result = await api.bulkCandidateAction({
        action,
        candidate_ids: Array.from(selectedIds),
        note: "Bulk action from Research / Tools dashboard.",
      });
      setNotice(result.message || "Bulk action completed.");
      await loadData();
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBulkBusy(false);
      setSelectedIds(new Set());
    }
  }

  function triggerBulkAction({ action, confirm: needsConfirm, label }) {
    if (needsConfirm) {
      setBulkConfirm({ action, label });
    } else {
      executeBulkAction(action);
    }
  }

  function toggleSelectAll() {
    if (selectedIds.size === candidates.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(candidates.map((c) => c._id)));
    }
  }

  function toggleSelect(id) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function toggleHistoryDetail(runId) {
    if (expandedRunId === runId) {
      setExpandedRunId(null);
      return;
    }
    setExpandedRunId(runId);
    if (historyDetail[runId]) return;
    setLoadingDetail(runId);
    try {
      const [detailData, errorsData] = await Promise.all([
        api.importHistoryDetail(runId, { include_duplicates: "true", limit: "200" }),
        api.importHistoryErrors(runId),
      ]);
      setHistoryDetail((prev) => ({ ...prev, [runId]: { candidates: detailData.items || [], errors: errorsData.items || [] } }));
    } catch (error) {
      setNotice(`Failed to load import detail: ${error.message}`);
    } finally {
      setLoadingDetail(null);
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
      const errorNote = result.error_count ? ` Errors: ${result.error_count}.` : "";
      setNotice(`${result.message} Imported: ${result.candidate_count || 0}. Duplicates: ${result.duplicate_count || 0}.${errorNote}`);
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
      review: candidates.filter((c) => c.status === "needs_review").length,
      converted: candidates.filter((c) => String(c.status || "").startsWith("converted_to_")).length,
      duplicates: candidates.filter((c) => c.is_duplicate).length,
    }),
    [candidates, toolRuns],
  );

  const allSelected = candidates.length > 0 && selectedIds.size === candidates.length;

  return (
    <div className="space-y-5">
      {/* Bulk confirm modal */}
      {bulkConfirm ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-xl">
            <h3 className="text-base font-semibold text-slate-900">Confirm Bulk {bulkConfirm.label}</h3>
            <p className="mt-2 text-sm text-slate-600">
              Apply <strong>{bulkConfirm.action}</strong> to <strong>{selectedIds.size}</strong> selected candidate{selectedIds.size !== 1 ? "s" : ""}? Only approved candidates will be converted.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setBulkConfirm(null)} className="h-9 rounded-lg border border-slate-200 px-4 text-sm font-medium text-slate-700 hover:border-slate-300">
                Cancel
              </button>
              <button type="button" onClick={() => executeBulkAction(bulkConfirm.action)} className="h-9 rounded-lg bg-slate-950 px-4 text-sm font-medium text-white hover:bg-blue-700">
                Confirm
              </button>
            </div>
          </div>
        </div>
      ) : null}

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

      {/* Run Mock Research */}
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-950">Run Mock Research</h3>
            <p className="mt-1 text-xs text-slate-500">Creates read-only tool runs, candidates, artifacts, and approvals for operator review.</p>
          </div>
          <StatusBadge value="mock read only" />
        </div>
        <form onSubmit={runResearch} className="grid gap-3 lg:grid-cols-[1.5fr_1fr_1fr_0.4fr_auto]">
          <input value={researchForm.query} onChange={(e) => setResearchForm((c) => ({ ...c, query: e.target.value }))} className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-800" placeholder="Search query" />
          <select value={researchForm.module} onChange={(e) => setResearchForm((c) => ({ ...c, module: e.target.value }))} className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800">
            {MODULE_OPTIONS.filter(Boolean).map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <input value={researchForm.location} onChange={(e) => setResearchForm((c) => ({ ...c, location: e.target.value }))} className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-800" placeholder="Location" />
          <input type="number" min="1" max="25" value={researchForm.limit} onChange={(e) => setResearchForm((c) => ({ ...c, limit: e.target.value }))} className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-800" />
          <button type="submit" disabled={runningResearch} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-slate-950 px-4 text-sm font-medium text-white transition hover:bg-blue-700 disabled:bg-slate-300">
            <SearchCheck className="h-4 w-4" /> Run
          </button>
        </form>
      </section>

      {/* Import CSV */}
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-950">Import CSV</h3>
            <p className="mt-1 text-xs text-slate-500">Imports real source lists into the same review-only candidate flow.</p>
          </div>
          <StatusBadge value="manual upload" />
        </div>
        <form onSubmit={importCandidates} className="grid gap-3 lg:grid-cols-[1fr_1fr_1.2fr_auto]">
          <select value={importForm.module} onChange={(e) => setImportForm((c) => ({ ...c, module: e.target.value }))} className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800">
            {MODULE_OPTIONS.filter(Boolean).map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <input value={importForm.source_label} onChange={(e) => setImportForm((c) => ({ ...c, source_label: e.target.value }))} className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-800" placeholder="Source label" />
          <div className="grid gap-2 md:grid-cols-2">
            <input type="file" accept=".csv,text/csv" onChange={(e) => setImportFile(e.target.files?.[0] || null)} className="h-10 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800" />
            <input value={importForm.csv_path} onChange={(e) => setImportForm((c) => ({ ...c, csv_path: e.target.value }))} className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-800" placeholder="data/imports/contractor_sources.csv" />
          </div>
          <button type="submit" disabled={runningImport || (!importFile && !importForm.csv_path.trim())} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-slate-950 px-4 text-sm font-medium text-white transition hover:bg-blue-700 disabled:bg-slate-300">
            <Upload className="h-4 w-4" /> Import
          </button>
        </form>
        <div className="mt-3 text-xs text-slate-500">Selected: {importFile?.name || importForm.csv_path || "No CSV selected"}</div>
      </section>

      {/* Scraped Candidates */}
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-950">Scraped Candidates</h3>
            <p className="mt-1 text-xs text-slate-500">Approve a candidate first, then convert it locally when it is ready for the pipeline.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <select value={status} onChange={(e) => { setStatus(e.target.value); loadData(e.target.value, showDuplicates); }} className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700">
              {STATUS_FILTERS.map((v) => <option key={v || "all"} value={v}>{v || "all"}</option>)}
            </select>
            <label className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700">
              <input type="checkbox" checked={showDuplicates} onChange={(e) => { setShowDuplicates(e.target.checked); loadData(status, e.target.checked); }} className="h-4 w-4 rounded border-slate-300" />
              Duplicates
            </label>
            <button type="button" onClick={() => loadData(status, showDuplicates)} className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700">
              <RefreshCw className="h-4 w-4" /> Refresh
            </button>
          </div>
        </div>

        {/* Advanced Filters */}
        <details className="mb-4">
          <summary className="cursor-pointer text-xs font-semibold text-slate-500 hover:text-slate-800">Advanced Filters</summary>
          <div className="mt-3 grid gap-3 border-t border-slate-100 pt-3 sm:grid-cols-2 lg:grid-cols-5">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Source Label</label>
              <input value={filterSourceLabel} onChange={(e) => setFilterSourceLabel(e.target.value)} className="h-9 w-full rounded-lg border border-slate-200 px-3 text-xs text-slate-800" placeholder="e.g. manual_upload" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Module</label>
              <select value={filterModule} onChange={(e) => setFilterModule(e.target.value)} className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-xs text-slate-800">
                {MODULE_OPTIONS.map((m) => <option key={m || "all"} value={m}>{m || "all modules"}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Min Quality</label>
              <input type="number" min="0" max="100" value={filterMinQuality} onChange={(e) => setFilterMinQuality(e.target.value)} className="h-9 w-full rounded-lg border border-slate-200 px-3 text-xs text-slate-800" placeholder="0" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Max Quality</label>
              <input type="number" min="0" max="100" value={filterMaxQuality} onChange={(e) => setFilterMaxQuality(e.target.value)} className="h-9 w-full rounded-lg border border-slate-200 px-3 text-xs text-slate-800" placeholder="100" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Converted</label>
              <select value={filterConverted} onChange={(e) => setFilterConverted(e.target.value)} className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-xs text-slate-800">
                <option value="">any</option>
                <option value="converted">converted only</option>
                <option value="not_converted">not converted</option>
              </select>
            </div>
          </div>
          <button type="button" onClick={applyFilters} className="mt-3 inline-flex h-8 items-center gap-1 rounded-lg bg-slate-950 px-3 text-xs font-medium text-white hover:bg-blue-700">
            Apply Filters
          </button>
        </details>

        {/* Bulk action bar */}
        {selectedIds.size > 0 ? (
          <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2">
            <span className="text-sm font-medium text-blue-900">{selectedIds.size} selected</span>
            {BULK_ACTIONS.map(({ action, label, confirm: needsConfirm }) => (
              <button key={action} type="button" disabled={bulkBusy} onClick={() => triggerBulkAction({ action, label, confirm: needsConfirm })} className="inline-flex h-8 items-center gap-1 rounded-lg border border-blue-200 bg-white px-3 text-xs font-semibold text-blue-800 hover:bg-blue-100 disabled:opacity-50">
                {label}
              </button>
            ))}
            <button type="button" onClick={() => setSelectedIds(new Set())} className="ml-auto inline-flex h-8 items-center gap-1 rounded-lg px-2 text-xs text-slate-500 hover:text-slate-800">
              <X className="h-3.5 w-3.5" /> Clear
            </button>
          </div>
        ) : null}

        <DataTable
          columns={[
            {
              key: "_select",
              label: <input type="checkbox" checked={allSelected} onChange={toggleSelectAll} className="h-4 w-4 rounded border-slate-300" aria-label="Select all" />,
              render: (row) => <input type="checkbox" checked={selectedIds.has(row._id)} onChange={() => toggleSelect(row._id)} className="h-4 w-4 rounded border-slate-300" aria-label={`Select ${row.company || row._id}`} />,
            },
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
            { key: "source_label", label: "Source Label", render: (row) => <span className="text-xs text-slate-600">{row.source_label || "-"}</span> },
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
            { key: "actions", label: "Actions", render: (row) => (
              <div className="flex flex-wrap gap-2">
                <button type="button" disabled={busyId === row._id} onClick={() => decide(row, "approve")} className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 px-2 text-xs font-semibold text-slate-700 hover:border-green-200 hover:text-green-700 disabled:opacity-50"><Check className="h-3.5 w-3.5" /> Approve</button>
                <button type="button" disabled={busyId === row._id} onClick={() => decide(row, "reject")} className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 px-2 text-xs font-semibold text-slate-700 hover:border-red-200 hover:text-red-700 disabled:opacity-50"><X className="h-3.5 w-3.5" /> Reject</button>
                <button type="button" disabled={busyId === row._id || row.status !== "approved"} onClick={() => decide(row, "convert_to_contact")} className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 px-2 text-xs font-semibold text-slate-700 hover:border-blue-200 hover:text-blue-700 disabled:opacity-50"><UserPlus className="h-3.5 w-3.5" /> Contact</button>
                <button type="button" disabled={busyId === row._id || row.status !== "approved"} onClick={() => decide(row, "convert_to_lead")} className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 px-2 text-xs font-semibold text-slate-700 hover:border-blue-200 hover:text-blue-700 disabled:opacity-50"><Target className="h-3.5 w-3.5" /> Lead</button>
              </div>
            ) },
          ]}
          rows={candidates}
          emptyMessage="No scraped candidates match this filter."
        />
      </section>

      {/* Import History */}
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <FileText className="h-4 w-4 text-blue-600" />
          <h3 className="text-sm font-semibold text-slate-950">Import History</h3>
          <span className="ml-auto text-xs text-slate-400">{importHistoryRuns.length} manual uploads</span>
        </div>
        {importHistoryRuns.length === 0 ? (
          <p className="text-sm text-slate-400">No manual CSV imports recorded yet.</p>
        ) : (
          <div className="space-y-2">
            {importHistoryRuns.map((run) => {
              const isExpanded = expandedRunId === run._id;
              const detail = historyDetail[run._id];
              const isLoadingThis = loadingDetail === run._id;
              return (
                <div key={run._id} className="rounded-lg border border-slate-100 bg-slate-50">
                  <button type="button" className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-slate-100" onClick={() => toggleHistoryDetail(run._id)}>
                    {isExpanded ? <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" /> : <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" />}
                    <div className="flex flex-1 flex-wrap items-center gap-3 text-xs">
                      <span className="font-semibold text-slate-900">{run.source_label || "manual_upload"}</span>
                      <StatusBadge value={run.module || "unknown"} />
                      <StatusBadge value={run.status || "completed"} />
                      <span className="text-slate-600">{run.candidate_count ?? 0} candidates</span>
                      {run.duplicate_count > 0 ? <span className="text-amber-700">{run.duplicate_count} dupes</span> : null}
                      {run.error_count > 0 ? (
                        <span className="inline-flex items-center gap-1 text-red-700"><AlertTriangle className="h-3 w-3" /> {run.error_count} errors</span>
                      ) : null}
                      <span className="ml-auto text-slate-400">{formatDate(run.created_at)}</span>
                    </div>
                  </button>
                  {isExpanded ? (
                    <div className="border-t border-slate-200 px-4 pb-4 pt-3">
                      {isLoadingThis ? (
                        <p className="text-xs text-slate-400">Loading…</p>
                      ) : detail ? (
                        <>
                          {detail.errors.length > 0 ? (
                            <div className="mb-3">
                              <div className="mb-1 text-xs font-semibold text-red-700">Row Errors ({detail.errors.length})</div>
                              <div className="space-y-1 rounded-lg border border-red-100 bg-red-50 p-2">
                                {detail.errors.map((err, idx) => (
                                  <div key={idx} className="flex gap-2 text-xs text-red-800">
                                    <span className="shrink-0 font-mono">Row {err.row}</span>
                                    {err.field ? <span className="text-red-500">[{err.field}]</span> : null}
                                    <span>{err.error}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ) : null}
                          {detail.candidates.length === 0 ? (
                            <p className="text-xs text-slate-400">No candidates stored for this import.</p>
                          ) : (
                            <DataTable
                              columns={[
                                { key: "company", label: "Company", render: (row) => <span className="font-medium text-slate-900">{row.company || "-"}</span> },
                                { key: "email", label: "Email", render: (row) => <span className="text-xs">{row.email || "-"}</span> },
                                { key: "phone", label: "Phone", render: (row) => <span className="text-xs">{row.phone || "-"}</span> },
                                { key: "location", label: "Location", render: (row) => [row.city, row.state].filter(Boolean).join(", ") || "-" },
                                { key: "quality", label: "Quality", render: (row) => `${Number(row.quality_score || 0)}/100` },
                                { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status || "needs_review"} /> },
                                { key: "is_duplicate", label: "Dup?", render: (row) => row.is_duplicate ? <StatusBadge value="duplicate" /> : "-" },
                                { key: "csv_row_number", label: "CSV Row", render: (row) => row.csv_row_number ?? "-" },
                              ]}
                              rows={detail.candidates}
                              emptyMessage="No candidates for this import."
                            />
                          )}
                        </>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Recent Tool Runs */}
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



