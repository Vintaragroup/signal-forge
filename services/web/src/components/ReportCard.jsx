import { FileText } from "lucide-react";

export default function ReportCard({ report }) {
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-blue-50 p-2 text-blue-700 ring-1 ring-blue-100">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-slate-950">{report.label}</h2>
            <div className="mt-1 text-xs text-slate-500">{report.path}</div>
          </div>
        </div>
        <span className="text-xs text-slate-500">{report.updated_at ? new Date(report.updated_at).toLocaleString() : "Missing"}</span>
      </div>
      <pre className="mt-4 max-h-80 overflow-auto rounded-lg bg-slate-950 p-4 text-xs leading-5 text-slate-100 scrollbar-soft">
        {report.excerpt || "Report not found."}
      </pre>
    </article>
  );
}
