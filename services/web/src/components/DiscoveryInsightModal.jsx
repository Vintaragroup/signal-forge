import { X, TrendingUp, Lightbulb, ChevronDown } from "lucide-react";

const STATUS_COLORS = {
  pending_review: "bg-amber-100 text-amber-700",
  approved: "bg-green-100 text-green-700",
  deferred: "bg-slate-100 text-slate-600",
  archived: "bg-slate-100 text-slate-500",
};

function EvidenceItem({ ev }) {
  return (
    <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs space-y-0.5">
      <div className="flex items-center gap-2 flex-wrap">
        {ev.platform && (
          <span className="font-semibold text-slate-700">{ev.platform}</span>
        )}
        {ev.signal_type && (
          <span className="rounded-full bg-blue-100 px-1.5 text-blue-600">{ev.signal_type}</span>
        )}
      </div>
      {ev.keyword && (
        <div className="text-slate-600">
          Keyword: <span className="font-medium">{ev.keyword}</span>
          {ev.growth_pct != null && (
            <span className="ml-1.5 text-green-600 font-semibold">+{ev.growth_pct}%</span>
          )}
        </div>
      )}
      {ev.metric && ev.value != null && (
        <div className="text-slate-600">
          {ev.metric}: <span className="font-medium">{ev.value.toLocaleString()}</span>
        </div>
      )}
      {ev.notes && <div className="text-slate-500 italic">{ev.notes}</div>}
      {ev.source_url && (
        <div className="truncate">
          <a
            href={ev.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-500 underline hover:text-blue-700"
          >
            {ev.source_url}
          </a>
        </div>
      )}
    </div>
  );
}

export default function DiscoveryInsightModal({ insight, onClose }) {
  if (!insight) return null;

  const statusClass = STATUS_COLORS[insight.status] ?? "bg-slate-100 text-slate-600";
  const confidencePct = Math.round((insight.confidence_score ?? 0) * 100);
  const rec = insight.recommendation ?? null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="relative w-full max-w-2xl rounded-xl bg-white shadow-2xl flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 px-5 pt-5 pb-3 border-b border-slate-100">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-semibold text-violet-700 uppercase tracking-wide">
                {insight.insight_type?.replace(/_/g, " ")}
              </span>
              <span className={`rounded-full px-2 py-0.5 text-xs font-semibold capitalize ${statusClass}`}>
                {insight.status?.replace(/_/g, " ")}
              </span>
            </div>
            <h2 className="text-base font-bold text-slate-950 leading-snug">{insight.title}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="overflow-y-auto px-5 py-4 space-y-5 text-sm">
          {/* Confidence */}
          <div className="flex items-center gap-3">
            <TrendingUp size={14} className="text-violet-400 shrink-0" />
            <div className="flex-1">
              <div className="flex justify-between mb-0.5">
                <span className="text-xs text-slate-500">Confidence</span>
                <span className="text-xs font-semibold text-slate-700">{confidencePct}%</span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-slate-200">
                <div
                  className="h-1.5 rounded-full bg-violet-500 transition-all"
                  style={{ width: `${confidencePct}%` }}
                />
              </div>
            </div>
          </div>

          {/* Summary */}
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Summary</h3>
            <p className="text-slate-700 leading-relaxed">{insight.summary}</p>
          </div>

          {/* Recommendation */}
          {rec && (
            <div className="rounded-lg border border-violet-200 bg-violet-50 px-4 py-3 space-y-2">
              <div className="flex items-center gap-1.5 mb-1">
                <Lightbulb size={13} className="text-violet-500" />
                <h3 className="text-xs font-semibold uppercase tracking-wide text-violet-600">Recommendation</h3>
              </div>
              {rec.rationale && (
                <p className="text-violet-800 text-xs leading-relaxed">{rec.rationale}</p>
              )}
              {rec.recommended_next_stage && (
                <div className="text-xs text-violet-700">
                  Next Stage:{" "}
                  <span className="font-semibold">{rec.recommended_next_stage.replace(/_/g, " ")}</span>
                </div>
              )}
              {rec.recommended_asset_types?.length > 0 && (
                <div>
                  <div className="text-[11px] text-violet-500 mb-1">Asset Types</div>
                  <div className="flex flex-wrap gap-1">
                    {rec.recommended_asset_types.map((t) => (
                      <span key={t} className="rounded-full bg-violet-200 px-2 py-0.5 text-[11px] text-violet-700 font-medium">
                        {t.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {rec.recommended_platforms?.length > 0 && (
                <div>
                  <div className="text-[11px] text-violet-500 mb-1">Platforms</div>
                  <div className="flex flex-wrap gap-1">
                    {rec.recommended_platforms.map((p) => (
                      <span key={p} className="rounded-full bg-white border border-violet-300 px-2 py-0.5 text-[11px] text-violet-600">
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Evidence */}
          {insight.evidence?.length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Supporting Evidence ({insight.evidence.length})
              </h3>
              <div className="space-y-2">
                {insight.evidence.map((ev, idx) => (
                  <EvidenceItem key={idx} ev={ev} />
                ))}
              </div>
            </div>
          )}

          {/* Meta */}
          <div className="grid grid-cols-2 gap-3 text-xs text-slate-500">
            {insight.source_agent && (
              <div>
                <div className="font-semibold text-slate-600 mb-0.5">Source Agent</div>
                <div>{insight.source_agent}</div>
              </div>
            )}
            {insight.source_run_id && (
              <div>
                <div className="font-semibold text-slate-600 mb-0.5">Run ID</div>
                <div className="font-mono truncate">{insight.source_run_id}</div>
              </div>
            )}
            {insight.created_at && (
              <div>
                <div className="font-semibold text-slate-600 mb-0.5">Created</div>
                <div>{new Date(insight.created_at).toLocaleString()}</div>
              </div>
            )}
            {insight.approved_at && (
              <div>
                <div className="font-semibold text-slate-600 mb-0.5">Approved</div>
                <div>{new Date(insight.approved_at).toLocaleString()}</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
