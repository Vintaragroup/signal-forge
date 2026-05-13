import { useEffect, useState, useCallback } from "react";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Globe,
  Lightbulb,
  RefreshCw,
  TrendingUp,
  XCircle,
  Zap,
} from "lucide-react";
import { api } from "../api";

// ── Constants ─────────────────────────────────────────────────────────────────

const IMPACT_STYLES = {
  high:   "bg-red-100 text-red-700 border border-red-200",
  medium: "bg-yellow-100 text-yellow-700 border border-yellow-200",
  low:    "bg-green-100 text-green-700 border border-green-200",
};

const STATUS_STYLES = {
  active:    "bg-blue-100 text-blue-700",
  accepted:  "bg-green-100 text-green-700",
  dismissed: "bg-gray-100 text-gray-500",
  applied:   "bg-purple-100 text-purple-700",
  expired:   "bg-gray-100 text-gray-400",
};

const TYPE_LABELS = {
  workflow_optimization:    "Workflow",
  memory_refinement:        "Memory",
  template_adaptation:      "Template",
  distribution_timing:      "Distribution",
  bottleneck_remediation:   "Bottleneck",
  content_quality:          "Content",
  client_health_warning:    "Health",
  approval_efficiency:      "Approvals",
};

const TIME_WINDOWS = [
  { label: "7d",   value: 7 },
  { label: "30d",  value: 30 },
  { label: "90d",  value: 90 },
  { label: "All",  value: 0 },
];

// ── Sub-components ────────────────────────────────────────────────────────────

function ImpactBadge({ impact }) {
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${IMPACT_STYLES[impact] ?? IMPACT_STYLES.low}`}>
      {impact?.toUpperCase() ?? "LOW"}
    </span>
  );
}

function ConfidenceBadge({ score }) {
  const pct = Math.round((score ?? 0) * 100);
  const color = pct >= 85 ? "text-green-600" : pct >= 65 ? "text-yellow-600" : "text-gray-500";
  return <span className={`text-xs font-mono ${color}`}>{pct}% confidence</span>;
}

function TypeBadge({ type }) {
  return (
    <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 border border-gray-200">
      {TYPE_LABELS[type] ?? type}
    </span>
  );
}

function StatusBadge({ status }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_STYLES[status] ?? STATUS_STYLES.active}`}>
      {status}
    </span>
  );
}

function EvidencePanel({ evidence }) {
  const [open, setOpen] = useState(false);
  if (!evidence?.length) return null;
  return (
    <div className="mt-2">
      <button
        className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        {evidence.length} evidence item{evidence.length !== 1 ? "s" : ""}
      </button>
      {open && (
        <ul className="mt-1 pl-4 space-y-0.5">
          {evidence.map((e, i) => (
            <li key={i} className="text-xs text-gray-600 list-disc">
              {e}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RecommendationCard({ rec, onAction }) {
  const isActive = rec.status === "active";
  return (
    <div className={`border rounded-lg p-4 transition-opacity ${rec.status !== "active" ? "opacity-60" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <TypeBadge type={rec.recommendation_type} />
            <ImpactBadge impact={rec.impact_estimate} />
            <StatusBadge status={rec.status} />
            <ConfidenceBadge score={rec.confidence_score} />
          </div>
          <p className="font-medium text-sm text-gray-900 mt-1">{rec.title}</p>
          <p className="text-xs text-gray-600 mt-0.5 leading-relaxed">{rec.description}</p>
          <EvidencePanel evidence={rec.evidence} />
        </div>
        {isActive && (
          <div className="flex flex-col gap-1 shrink-0">
            <button
              onClick={() => onAction(rec.id, "apply")}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-purple-600 text-white hover:bg-purple-700"
            >
              <Zap size={11} /> Apply
            </button>
            <button
              onClick={() => onAction(rec.id, "accept")}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-green-600 text-white hover:bg-green-700"
            >
              <CheckCircle2 size={11} /> Accept
            </button>
            <button
              onClick={() => onAction(rec.id, "dismiss")}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-gray-200 text-gray-600 hover:bg-gray-300"
            >
              <XCircle size={11} /> Dismiss
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ title, icon: Icon, children, count }) {
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <Icon size={16} className="text-gray-500" />
        <h3 className="font-semibold text-sm text-gray-800">{title}</h3>
        {count !== undefined && (
          <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full">{count}</span>
        )}
      </div>
      {children}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function RecommendationsDashboardPage({ activeWorkspace }) {
  const [days, setDays] = useState(30);
  const [recs, setRecs] = useState([]);
  const [summary, setSummary] = useState(null);
  const [crossSignals, setCrossSignals] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState({});
  const [error, setError] = useState(null);

  const workspaceSlug = activeWorkspace?.slug ?? "";

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [recsData, summaryData, signalsData] = await Promise.all([
        api.listRecommendations(workspaceSlug, days),
        api.recommendationsSummary(workspaceSlug, days),
        api.crossClientSignals(days),
      ]);
      setRecs(recsData.recommendations ?? []);
      setSummary(summaryData);
      setCrossSignals(signalsData);
    } catch (err) {
      setError(err.message ?? "Failed to load recommendations");
    } finally {
      setLoading(false);
    }
  }, [workspaceSlug, days]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleAction = async (recId, action) => {
    setActionLoading((prev) => ({ ...prev, [recId]: action }));
    try {
      if (action === "accept") await api.acceptRecommendation(recId);
      else if (action === "dismiss") await api.dismissRecommendation(recId);
      else if (action === "apply") await api.applyRecommendation(recId);
      await loadData();
    } finally {
      setActionLoading((prev) => { const n = { ...prev }; delete n[recId]; return n; });
    }
  };

  // Group recs by type
  const byType = recs.reduce((acc, r) => {
    const t = r.recommendation_type ?? "other";
    if (!acc[t]) acc[t] = [];
    acc[t].push(r);
    return acc;
  }, {});

  const highImpact = recs.filter((r) => r.impact_estimate === "high" && r.status === "active");
  const healthWarnings = recs.filter((r) => r.recommendation_type === "client_health_warning" && r.status === "active");
  const workflowRecs = recs.filter((r) => r.recommendation_type === "workflow_optimization");
  const memoryRecs = recs.filter((r) => r.recommendation_type === "memory_refinement");
  const templateRecs = recs.filter((r) => r.recommendation_type === "template_adaptation");
  const distRecs = recs.filter((r) => r.recommendation_type === "distribution_timing");
  const bottleneckRecs = recs.filter((r) => r.recommendation_type === "bottleneck_remediation");
  const activeRecs = recs.filter((r) => r.status === "active");

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <Lightbulb size={20} className="text-yellow-500" />
            Optimization Recommendations
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Autonomous suggestions derived from workflow telemetry and operational intelligence
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex rounded-lg border border-gray-200 overflow-hidden text-xs">
            {TIME_WINDOWS.map((w) => (
              <button
                key={w.value}
                onClick={() => setDays(w.value)}
                className={`px-3 py-1.5 font-medium transition-colors ${
                  days === w.value
                    ? "bg-blue-600 text-white"
                    : "bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                {w.label}
              </button>
            ))}
          </div>
          <button
            onClick={loadData}
            disabled={loading}
            className="p-2 rounded-lg border border-gray-200 text-gray-500 hover:text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Summary Strip */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {[
            { label: "Total", value: summary.total, color: "text-gray-900" },
            { label: "Active", value: summary.active, color: "text-blue-600" },
            { label: "High Impact", value: summary.high_impact, color: "text-red-600" },
            { label: "Types", value: Object.keys(summary.by_type ?? {}).length, color: "text-purple-600" },
          ].map((m) => (
            <div key={m.label} className="bg-white border border-gray-200 rounded-lg p-3 text-center">
              <div className={`text-2xl font-bold ${m.color}`}>{m.value}</div>
              <div className="text-xs text-gray-500 mt-0.5">{m.label}</div>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-40 text-gray-400 text-sm">
          Loading recommendations...
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main column */}
          <div className="lg:col-span-2 space-y-6">

            {/* High Impact */}
            {highImpact.length > 0 && (
              <Section title="High Impact Opportunities" icon={TrendingUp} count={highImpact.length}>
                <div className="space-y-3">
                  {highImpact.map((r) => (
                    <RecommendationCard key={r.id} rec={r} onAction={handleAction} />
                  ))}
                </div>
              </Section>
            )}

            {/* Client Health Risks */}
            {healthWarnings.length > 0 && (
              <Section title="Client Health Risks" icon={AlertTriangle} count={healthWarnings.length}>
                <div className="space-y-3">
                  {healthWarnings.map((r) => (
                    <RecommendationCard key={r.id} rec={r} onAction={handleAction} />
                  ))}
                </div>
              </Section>
            )}

            {/* Workflow Optimization */}
            {workflowRecs.length > 0 && (
              <Section title="Workflow Optimization" icon={Zap} count={workflowRecs.length}>
                <div className="space-y-3">
                  {workflowRecs.map((r) => (
                    <RecommendationCard key={r.id} rec={r} onAction={handleAction} />
                  ))}
                </div>
              </Section>
            )}

            {/* Memory Refinement */}
            {memoryRecs.length > 0 && (
              <Section title="Memory Refinement" icon={Lightbulb} count={memoryRecs.length}>
                <div className="space-y-3">
                  {memoryRecs.map((r) => (
                    <RecommendationCard key={r.id} rec={r} onAction={handleAction} />
                  ))}
                </div>
              </Section>
            )}

            {/* Template Leaderboard */}
            {templateRecs.length > 0 && (
              <Section title="Template Adaptation" icon={BarChart3} count={templateRecs.length}>
                <div className="space-y-3">
                  {templateRecs.map((r) => (
                    <RecommendationCard key={r.id} rec={r} onAction={handleAction} />
                  ))}
                </div>
              </Section>
            )}

            {/* Distribution */}
            {distRecs.length > 0 && (
              <Section title="Distribution Insights" icon={TrendingUp} count={distRecs.length}>
                <div className="space-y-3">
                  {distRecs.map((r) => (
                    <RecommendationCard key={r.id} rec={r} onAction={handleAction} />
                  ))}
                </div>
              </Section>
            )}

            {/* Bottleneck Remediation */}
            {bottleneckRecs.length > 0 && (
              <Section title="Bottleneck Remediation" icon={AlertTriangle} count={bottleneckRecs.length}>
                <div className="space-y-3">
                  {bottleneckRecs.map((r) => (
                    <RecommendationCard key={r.id} rec={r} onAction={handleAction} />
                  ))}
                </div>
              </Section>
            )}

            {activeRecs.length === 0 && !loading && (
              <div className="text-center py-12 text-gray-400 text-sm">
                <CheckCircle2 size={32} className="mx-auto mb-2 text-green-400" />
                No active recommendations — system is operating well.
              </div>
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-4">

            {/* Active Recommendations list */}
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <h3 className="font-semibold text-sm text-gray-800 mb-3 flex items-center gap-2">
                <Lightbulb size={14} className="text-yellow-500" />
                All Active ({activeRecs.length})
              </h3>
              {activeRecs.length === 0 ? (
                <p className="text-xs text-gray-400">None active.</p>
              ) : (
                <ul className="space-y-2">
                  {activeRecs.slice(0, 8).map((r) => (
                    <li key={r.id} className="flex items-start gap-2">
                      <ImpactBadge impact={r.impact_estimate} />
                      <span className="text-xs text-gray-700 leading-tight">{r.title}</span>
                    </li>
                  ))}
                  {activeRecs.length > 8 && (
                    <li className="text-xs text-gray-400">+{activeRecs.length - 8} more</li>
                  )}
                </ul>
              )}
            </div>

            {/* By Type Breakdown */}
            {summary?.by_type && Object.keys(summary.by_type).length > 0 && (
              <div className="bg-white border border-gray-200 rounded-lg p-4">
                <h3 className="font-semibold text-sm text-gray-800 mb-3 flex items-center gap-2">
                  <BarChart3 size={14} className="text-blue-500" />
                  By Type
                </h3>
                <ul className="space-y-1.5">
                  {Object.entries(summary.by_type)
                    .sort((a, b) => b[1] - a[1])
                    .map(([type, count]) => (
                      <li key={type} className="flex items-center justify-between text-xs">
                        <span className="text-gray-600">{TYPE_LABELS[type] ?? type}</span>
                        <span className="font-medium text-gray-900">{count}</span>
                      </li>
                    ))}
                </ul>
              </div>
            )}

            {/* Cross-Client Signals */}
            {crossSignals && (
              <div className="bg-white border border-gray-200 rounded-lg p-4">
                <h3 className="font-semibold text-sm text-gray-800 mb-3 flex items-center gap-2">
                  <Globe size={14} className="text-indigo-500" />
                  Cross-Client Signals
                </h3>
                <div className="text-xs text-gray-500 mb-2">
                  {crossSignals.active_workspaces} active workspace{crossSignals.active_workspaces !== 1 ? "s" : ""}
                </div>

                {crossSignals.best_performing_templates?.length > 0 && (
                  <div className="mb-3">
                    <p className="text-xs font-medium text-gray-700 mb-1">Top Templates</p>
                    {crossSignals.best_performing_templates.slice(0, 3).map((t) => (
                      <div key={t.module} className="flex justify-between text-xs text-gray-600 py-0.5">
                        <span className="truncate">{t.module}</span>
                        <span className="font-medium text-green-600 ml-2">
                          {Math.round((t.approval_rate ?? 0) * 100)}%
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {crossSignals.top_channels?.length > 0 && (
                  <div className="mb-3">
                    <p className="text-xs font-medium text-gray-700 mb-1">Top Channels</p>
                    {crossSignals.top_channels.slice(0, 3).map((c) => (
                      <div key={c.channel} className="flex justify-between text-xs text-gray-600 py-0.5">
                        <span>{c.channel}</span>
                        <span className="font-medium">{c.count}</span>
                      </div>
                    ))}
                  </div>
                )}

                {crossSignals.common_bottlenecks?.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-gray-700 mb-1">Common Bottlenecks</p>
                    {crossSignals.common_bottlenecks.slice(0, 3).map((b) => (
                      <div key={b.type} className="flex justify-between text-xs text-gray-600 py-0.5">
                        <span className="truncate">{b.type.replace(/_/g, " ")}</span>
                        <span className="font-medium text-red-500">{b.count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

          </div>
        </div>
      )}
    </div>
  );
}
