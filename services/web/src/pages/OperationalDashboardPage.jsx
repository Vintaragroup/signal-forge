import { useEffect, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  Brain,
  CheckCircle2,
  Clock,
  Package,
  Target,
  TrendingUp,
  Trophy,
  Workflow,
  Zap,
} from "lucide-react";
import { api } from "../api.js";

const TIME_WINDOWS = [
  { label: "7d", value: 7 },
  { label: "30d", value: 30 },
  { label: "90d", value: 90 },
  { label: "All", value: 0 },
];

function MetricCard({ label, value, sub, color = "blue", icon: Icon }) {
  const colors = {
    blue: "bg-blue-50 border-blue-200 text-blue-800",
    green: "bg-green-50 border-green-200 text-green-800",
    amber: "bg-amber-50 border-amber-200 text-amber-800",
    red: "bg-red-50 border-red-200 text-red-800",
    slate: "bg-slate-50 border-slate-200 text-slate-700",
    purple: "bg-purple-50 border-purple-200 text-purple-800",
  };
  return (
    <div className={`border rounded-lg p-4 ${colors[color]}`}>
      <div className="flex items-center gap-1.5 mb-1">
        {Icon && <Icon size={13} className="opacity-70" />}
        <span className="text-xs font-semibold uppercase tracking-wide opacity-70">{label}</span>
      </div>
      <div className="text-2xl font-bold leading-tight">{value}</div>
      {sub && <div className="text-xs mt-0.5 opacity-60">{sub}</div>}
    </div>
  );
}

function RateBar({ label, rate, color = "blue" }) {
  const pct = Math.round((rate || 0) * 100);
  const barColors = {
    blue: "bg-blue-500",
    green: "bg-green-500",
    amber: "bg-amber-500",
    red: "bg-red-500",
  };
  return (
    <div className="mb-2">
      <div className="flex justify-between text-xs text-slate-500 mb-1">
        <span>{label}</span>
        <span className="font-semibold text-slate-700">{pct}%</span>
      </div>
      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`h-full ${barColors[color]} rounded-full transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function Section({ title, icon: Icon, children, loading }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 mb-4 shadow-sm">
      <div className="flex items-center gap-2 mb-4 pb-3 border-b border-slate-100">
        {Icon && <Icon size={15} className="text-slate-500" />}
        <h2 className="text-xs font-bold text-slate-600 uppercase tracking-widest">{title}</h2>
      </div>
      {loading ? (
        <div className="text-sm text-slate-400 text-center py-6 animate-pulse">Loading…</div>
      ) : (
        children
      )}
    </div>
  );
}

function pct(rate) {
  return `${Math.round((rate || 0) * 100)}%`;
}

function fmtNum(n) {
  if (n === null || n === undefined) return "—";
  if (typeof n === "number") return n.toLocaleString();
  return String(n);
}

export default function OperationalDashboardPage({ activeWorkspace }) {
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({});

  useEffect(() => {
    setLoading(true);
    const ws = activeWorkspace && activeWorkspace !== "all" ? activeWorkspace : "";
    Promise.all([
      api.analyticsWorkflows(ws, days).catch(() => null),
      api.analyticsMemory(ws, days).catch(() => null),
      api.analyticsDistribution(ws, days).catch(() => null),
      api.analyticsApprovals(ws, days).catch(() => null),
      api.analyticsTemplates(ws, days).catch(() => null),
      api.analyticsClientHealth(ws, days).catch(() => null),
      api.analyticsLearningSignals(ws, days).catch(() => null),
      api.analyticsBottlenecks(ws, days).catch(() => null),
    ]).then(([workflows, memory, distribution, approvals, templates, clientHealth, learning, bottlenecks]) => {
      setData({ workflows, memory, distribution, approvals, templates, clientHealth, learning, bottlenecks });
      setLoading(false);
    });
  }, [days, activeWorkspace]);

  const { workflows, memory, distribution, approvals, templates, clientHealth, learning, bottlenecks } = data;
  const bottleneckList = bottlenecks?.bottlenecks || [];

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <BarChart3 size={18} className="text-blue-600" />
            Operational Analytics
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            {activeWorkspace && activeWorkspace !== "all"
              ? `Workspace: ${activeWorkspace}`
              : "All workspaces"}{" "}
            — live operational intelligence
          </p>
        </div>
        <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
          {TIME_WINDOWS.map((w) => (
            <button
              key={w.value}
              onClick={() => setDays(w.value)}
              className={`px-3 py-1 rounded-md text-xs font-semibold transition-colors ${
                days === w.value
                  ? "bg-white text-blue-600 shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>

      {/* Bottleneck alerts */}
      {!loading && bottleneckList.length > 0 && (
        <div className="mb-4 bg-amber-50 border border-amber-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={14} className="text-amber-600" />
            <span className="text-sm font-semibold text-amber-800">
              {bottleneckList.length} Bottleneck{bottleneckList.length > 1 ? "s" : ""} Detected
            </span>
          </div>
          <div className="space-y-1.5">
            {bottleneckList.map((b, i) => (
              <div key={i} className="flex items-start gap-2.5 bg-white/80 rounded-lg px-3 py-2">
                <span
                  className={`mt-1.5 inline-block w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                    b.severity === "high"
                      ? "bg-red-500"
                      : b.severity === "medium"
                      ? "bg-amber-500"
                      : "bg-blue-400"
                  }`}
                />
                <div className="min-w-0">
                  <span
                    className={`text-xs font-bold mr-1.5 ${
                      b.severity === "high"
                        ? "text-red-700"
                        : b.severity === "medium"
                        ? "text-amber-700"
                        : "text-blue-600"
                    }`}
                  >
                    {b.status}
                  </span>
                  <span className="text-xs text-slate-600">{b.description}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Workflow Performance */}
      <Section title="Workflow Performance" icon={Workflow} loading={loading && !workflows}>
        {workflows && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
              <MetricCard label="Total Runs" value={fmtNum(workflows.total_runs)} icon={Workflow} color="blue" />
              <MetricCard
                label="Completion"
                value={pct(workflows.completion_rate)}
                icon={CheckCircle2}
                color={workflows.completion_rate >= 0.7 ? "green" : "amber"}
              />
              <MetricCard
                label="Failed"
                value={pct(workflows.failure_rate)}
                icon={AlertTriangle}
                color={workflows.failure_rate > 0.1 ? "red" : "slate"}
              />
              <MetricCard
                label="Memory-Informed"
                value={pct(workflows.memory_informed_rate)}
                icon={Brain}
                color="purple"
                sub={`${fmtNum(workflows.memory_informed_runs)} runs`}
              />
            </div>
            {workflows.avg_duration_seconds != null && (
              <p className="text-xs text-slate-500 mb-3">
                Avg duration:{" "}
                <span className="font-semibold text-slate-700">
                  {Math.round(workflows.avg_duration_seconds)}s
                </span>
              </p>
            )}
            {workflows.by_run_type && Object.keys(workflows.by_run_type).length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wide">By run type</p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(workflows.by_run_type).map(([k, v]) => (
                    <span key={k} className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded text-xs">
                      {k}: <strong>{v}</strong>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </Section>

      {/* Approval Funnel */}
      <Section title="Approval Funnel" icon={CheckCircle2} loading={loading && !approvals}>
        {approvals && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
              <MetricCard label="Total Requests" value={fmtNum(approvals.total_requests)} color="blue" />
              <MetricCard
                label="Open"
                value={fmtNum(approvals.open_count)}
                color={approvals.open_count > 10 ? "red" : approvals.open_count > 3 ? "amber" : "slate"}
              />
              <MetricCard
                label="Approval Rate"
                value={pct(approvals.approval_rate)}
                color={approvals.approval_rate >= 0.7 ? "green" : "amber"}
              />
              <MetricCard
                label="Avg Latency"
                value={approvals.avg_approval_latency_hours != null ? `${approvals.avg_approval_latency_hours}h` : "—"}
                icon={Clock}
                color="slate"
              />
            </div>
            <RateBar label="Approval rate" rate={approvals.approval_rate} color="green" />
            <RateBar label="Rejection rate" rate={approvals.rejection_rate} color="red" />
          </>
        )}
      </Section>

      {/* Distribution Funnel */}
      <Section title="Distribution Funnel" icon={Package} loading={loading && !distribution}>
        {distribution && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
              <MetricCard label="Total Assets" value={fmtNum(distribution.total_assets)} color="blue" />
              <MetricCard
                label="Published"
                value={fmtNum(distribution.published_count)}
                color="green"
                sub={pct(distribution.publish_rate)}
              />
              <MetricCard label="Queued" value={fmtNum(distribution.queued_count)} color="amber" />
              <MetricCard label="Not Queued" value={fmtNum(distribution.not_queued_count)} color="slate" />
            </div>
            <RateBar label="Publish rate" rate={distribution.publish_rate} color="green" />
            <RateBar label="Queue rate" rate={distribution.queue_rate} color="amber" />
            {distribution.by_channel && Object.keys(distribution.by_channel).length > 0 && (
              <div className="mt-3">
                <p className="text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wide">Published by channel</p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(distribution.by_channel).map(([k, v]) => (
                    <span key={k} className="px-2 py-0.5 bg-green-50 text-green-700 rounded text-xs font-medium">
                      {k}: {v}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </Section>

      {/* Memory Effectiveness */}
      <Section title="Memory Effectiveness" icon={Brain} loading={loading && !memory}>
        {memory && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
              <MetricCard label="Proposals" value={fmtNum(memory.total_proposals)} color="blue" />
              <MetricCard
                label="Approval Rate"
                value={pct(memory.approval_rate)}
                color={memory.approval_rate >= 0.6 ? "green" : "amber"}
              />
              <MetricCard
                label="Avg Confidence"
                value={pct(memory.avg_confidence)}
                color="purple"
              />
              <MetricCard
                label="Duplicates"
                value={fmtNum(memory.duplicate_proposals)}
                color={memory.duplicate_proposals > 0 ? "amber" : "slate"}
              />
            </div>
            <div className="grid grid-cols-3 gap-3 mb-3 text-center">
              <div className="bg-green-50 rounded-lg p-3">
                <div className="text-lg font-bold text-green-700">{fmtNum(memory.governance_auto_approve_count)}</div>
                <div className="text-xs text-green-600 mt-0.5">Auto Approve</div>
              </div>
              <div className="bg-red-50 rounded-lg p-3">
                <div className="text-lg font-bold text-red-700">{fmtNum(memory.governance_auto_reject_count)}</div>
                <div className="text-xs text-red-600 mt-0.5">Auto Reject</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-3">
                <div className="text-lg font-bold text-slate-700">{fmtNum(memory.governance_review_count)}</div>
                <div className="text-xs text-slate-500 mt-0.5">Needs Review</div>
              </div>
            </div>
            <p className="text-xs text-slate-500">
              Patterns:{" "}
              <span className="font-semibold text-green-700">{fmtNum(memory.total_winning_patterns)} winning</span> ·{" "}
              <span className="font-semibold text-red-600">{fmtNum(memory.total_losing_patterns)} losing</span> ·{" "}
              <span className="font-semibold text-amber-600">{fmtNum(memory.total_blocked_claims)} blocked claims</span>
            </p>
          </>
        )}
      </Section>

      {/* Template Leaderboard */}
      <Section title="Template Leaderboard" icon={Trophy} loading={loading && !templates}>
        {templates && templates.templates && templates.templates.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-slate-400 text-left">
                  <th className="pb-2 font-semibold">Module</th>
                  <th className="pb-2 text-right font-semibold">Runs</th>
                  <th className="pb-2 text-right font-semibold">Completion</th>
                  <th className="pb-2 text-right font-semibold">Approval</th>
                  <th className="pb-2 text-right font-semibold">Distribution</th>
                  <th className="pb-2 text-right font-semibold">Mem Conf</th>
                </tr>
              </thead>
              <tbody>
                {templates.templates.map((t, i) => (
                  <tr key={t.module} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                    <td className="py-2 font-medium text-slate-700">
                      {i === 0 && <span className="text-yellow-400 mr-1">★</span>}
                      {t.module}
                    </td>
                    <td className="py-2 text-right text-slate-500">{t.workflow_runs}</td>
                    <td className="py-2 text-right">
                      <span className={t.workflow_completion_rate >= 0.7 ? "text-green-600 font-semibold" : "text-amber-600"}>
                        {pct(t.workflow_completion_rate)}
                      </span>
                    </td>
                    <td className="py-2 text-right">
                      <span className={t.approval_rate >= 0.7 ? "text-green-600 font-semibold" : "text-amber-600"}>
                        {pct(t.approval_rate)}
                      </span>
                    </td>
                    <td className="py-2 text-right text-slate-500">{pct(t.distribution_completion_rate)}</td>
                    <td className="py-2 text-right text-slate-500">{pct(t.avg_memory_proposal_confidence)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-xs text-slate-400">No template data for this period.</p>
        )}
      </Section>

      {/* Client Health */}
      <Section title="Client Health" icon={Target} loading={loading && !clientHealth}>
        {clientHealth && clientHealth.workspaces && clientHealth.workspaces.length > 0 ? (
          <div className="space-y-3">
            {clientHealth.workspaces.map((ws) => (
              <div key={ws.workspace_slug} className="border border-slate-100 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-semibold text-slate-700">{ws.workspace_slug}</span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
                      ws.status === "healthy"
                        ? "bg-green-100 text-green-700"
                        : ws.status === "needs_attention"
                        ? "bg-amber-100 text-amber-700"
                        : "bg-red-100 text-red-700"
                    }`}
                  >
                    {(ws.status || "").replace("_", " ")} — {pct(ws.overall_health_score)}
                  </span>
                </div>
                <div className="grid grid-cols-4 gap-2 text-xs text-center">
                  <div>
                    <div className="font-semibold text-slate-700">{pct(ws.workflow_completion_rate)}</div>
                    <div className="text-slate-400">Workflow</div>
                  </div>
                  <div>
                    <div className="font-semibold text-slate-700">{pct(ws.approval_efficiency)}</div>
                    <div className="text-slate-400">Approvals</div>
                  </div>
                  <div>
                    <div className="font-semibold text-slate-700">{pct(ws.distribution_efficiency)}</div>
                    <div className="text-slate-400">Distribution</div>
                  </div>
                  <div>
                    <div className="font-semibold text-slate-700">{ws.pending_approvals}</div>
                    <div className="text-slate-400">Pending</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-slate-400">No workspace health data available.</p>
        )}
      </Section>

      {/* Learning Signals */}
      <Section title="Learning Signals" icon={TrendingUp} loading={loading && !learning}>
        {learning && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <div>
              <p className="text-xs font-bold text-green-700 mb-2 flex items-center gap-1">
                <Zap size={11} /> Top Winning Patterns
              </p>
              {learning.top_winning_patterns && learning.top_winning_patterns.length > 0 ? (
                <ul className="space-y-1">
                  {learning.top_winning_patterns.slice(0, 6).map((item, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs">
                      <span className="text-green-500 font-bold flex-shrink-0 w-4">{i + 1}.</span>
                      <span className="flex-1 text-slate-600 truncate" title={item.pattern}>
                        {item.pattern}
                      </span>
                      {item.frequency > 1 && (
                        <span className="text-slate-400 flex-shrink-0">×{item.frequency}</span>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-400">None yet.</p>
              )}
            </div>

            <div>
              <p className="text-xs font-bold text-red-600 mb-2 flex items-center gap-1">
                <AlertTriangle size={11} /> Top Rejected Patterns
              </p>
              {learning.top_rejected_patterns && learning.top_rejected_patterns.length > 0 ? (
                <ul className="space-y-1">
                  {learning.top_rejected_patterns.slice(0, 6).map((item, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs">
                      <span className="text-red-400 font-bold flex-shrink-0 w-4">{i + 1}.</span>
                      <span className="flex-1 text-slate-600 truncate" title={item.pattern}>
                        {item.pattern}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-400">None yet.</p>
              )}
            </div>

            <div>
              <p className="text-xs font-bold text-blue-700 mb-2">Top Distribution Channels</p>
              {learning.top_distribution_channels && learning.top_distribution_channels.length > 0 ? (
                <ul className="space-y-1">
                  {learning.top_distribution_channels.map((item, i) => (
                    <li key={i} className="flex justify-between text-xs">
                      <span className="text-slate-600">{item.channel}</span>
                      <span className="font-semibold text-blue-600">{item.published_count} published</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-400">No published assets yet.</p>
              )}
            </div>

            <div>
              <p className="text-xs font-bold text-purple-700 mb-2">Top Tone Profiles</p>
              {learning.top_tone_profiles && learning.top_tone_profiles.length > 0 ? (
                <ul className="space-y-1">
                  {learning.top_tone_profiles.map((item, i) => (
                    <li key={i} className="flex justify-between text-xs">
                      <span className="text-slate-600 capitalize">{item.tone}</span>
                      <span className="font-semibold text-purple-600">
                        {item.workspace_count} workspace{item.workspace_count > 1 ? "s" : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-400">No tone data yet.</p>
              )}
            </div>
          </div>
        )}
      </Section>
    </div>
  );
}
