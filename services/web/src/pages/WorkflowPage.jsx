import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  Brain,
  Check,
  Clock3,
  Compass,
  DollarSign,
  FileText,
  FilePlus2,
  Film,
  Gift,
  Mail,
  MapPin,
  Megaphone,
  MessageCircle,
  Music2,
  Newspaper,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  Star,
  TrendingUp,
  Users,
  X,
  Lightbulb,
  ChevronDown,
  AlertCircle,
  CheckCircle2,
  Maximize2,
  Volume2,
} from "lucide-react";
import { api } from "../api.js";
import { PROFILE_MAP } from "../navigation/systemProfiles.js";
import { WORKFLOW_TEMPLATES, DEFAULT_TEMPLATE } from "../navigation/workflowTemplates.js";
import { normalizeWorkflowDefinition } from "../utils/workflowDefinitionNormalizer.js";
import { getWorkflowOverrideCount } from "../utils/workflowTemplateDiff.js";
import DemoPageBanner from "../components/DemoPageBanner.jsx";
import LiveAgentRunPanel from "../components/LiveAgentRunPanel.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import WorkflowAssetCard from "../components/WorkflowAssetCard.jsx";
import DiscoveryInsightModal from "../components/DiscoveryInsightModal.jsx";

const MODULES = ["contractor_growth", "insurance_growth", "artist_growth", "media_growth"];
const PRIORITIES = ["low", "normal", "high"];
const OPEN_DEAL_OUTCOMES = ["proposal_sent", "negotiation", "nurture"];

const AGENT_ACTIONS = [
  { agent_name: "outreach", task_type: "run_outreach", label: "Run Outreach", icon: Megaphone },
  { agent_name: "followup", task_type: "run_followup", label: "Run Follow-up", icon: MessageCircle },
  { agent_name: "content", task_type: "generate_content", label: "Generate Content", icon: Newspaper },
  { agent_name: "fan_engagement", task_type: "engage_fans", label: "Fan Engagement", icon: Music2 },
];

// Icon lookup for run card icons referenced by name in workflowTemplates.js
const ICON_MAP = {
  Compass, DollarSign, FileText, Film, Gift, Mail, MapPin, Megaphone,
  MessageCircle, Music2, Newspaper, Search, Send, Star, TrendingUp, Users,
};

const APPROVAL_DECISIONS = [
  { value: "approve", label: "Approve", icon: Check },
  { value: "needs_revision", label: "Revise", icon: RotateCcw },
  { value: "reject", label: "Reject", icon: X },
  { value: "convert_to_draft", label: "Convert to draft", icon: FilePlus2 },
];

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

function formatMoney(value) {
  return `$${Number(value || 0).toLocaleString()}`;
}

function recordTitle(item) {
  return item.subject_line || item.title || item.company || item.company_name || item.recipient_name || item.person || item.request_type || item._id || "Untitled";
}

/**
 * StepSection — renders expanded (full content) or collapsed (compact header row).
 *
 * New props (Phase 6G):
 *   stageNote   string  — operator note below subtitle (muted)
 *   required    boolean — if false, shows Optional badge
 *   agentKey    string  — primary agent display
 *   runCardType string  — run card type display
 *
 * Existing props (all preserved):
 *   step, title, subtitle, active, count, children, expanded, onExpand, stageStatus
 */
function StepSection({ step, title, subtitle, active, count, children, expanded, onExpand, stageStatus, stageNote, required, agentKey, runCardType }) {
  if (expanded) {
    const hasMetadata = stageNote || agentKey || runCardType || required === false;
    // Full panel — same markup as before
    return (
      <section className={["rounded-lg border bg-white p-5 shadow-sm transition", active ? "border-blue-300 ring-2 ring-blue-100" : "border-slate-200"].join(" ")}>
        <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase text-slate-400">Step {step}</div>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">{title}</h2>
            {subtitle ? <p className="mt-2 text-sm leading-6 text-slate-600">{subtitle}</p> : null}
            {stageNote ? <p className="mt-1 text-xs text-slate-400 italic">{stageNote}</p> : null}
            {hasMetadata && (
              <div className="mt-1.5 flex flex-wrap items-center gap-2">
                {(agentKey || runCardType) && (
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                    required !== false ? "bg-blue-50 text-blue-600" : "bg-slate-100 text-slate-500"
                  }`}>
                    {required !== false ? "Required" : "Optional"}
                  </span>
                )}
                {required === false && !agentKey && !runCardType && (
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500">Optional</span>
                )}
                {agentKey && (
                  <span className="text-[10px] text-slate-400">
                    Primary Agent: <span className="font-medium text-slate-600">{agentKey}</span>
                  </span>
                )}
                {runCardType && (
                  <span className="text-[10px] text-slate-400">
                    Run Type: <span className="font-medium text-slate-600">{runCardType}</span>
                  </span>
                )}
              </div>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {active ? <StatusBadge value="next action" /> : null}
            {count !== undefined ? <StatusBadge value={`${count} items`} /> : null}
            <StageStatusPill status={stageStatus} />
          </div>
        </div>
        {children}
      </section>
    );
  }

  // Collapsed — compact single-row header, clickable to expand
  return (
    <button
      type="button"
      onClick={onExpand}
      className="flex w-full items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white px-5 py-3 text-left shadow-sm transition hover:border-blue-200 hover:bg-blue-50"
    >
      <div className="flex items-center gap-3 min-w-0">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-bold text-slate-500">{step}</span>
        <span className="font-semibold text-slate-800 truncate">{title}</span>
        {subtitle ? <span className="hidden text-sm text-slate-500 truncate sm:block">{subtitle}</span> : null}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {active ? <StatusBadge value="next action" /> : null}
        {count !== undefined ? <StatusBadge value={`${count} items`} /> : null}
        <StageStatusPill status={stageStatus} />
      </div>
    </button>
  );
}

// Phase 6G: normalizeWorkflowDefinition and getWorkflowOverrideCount are now
// imported from ../utils/workflowDefinitionNormalizer.js and ../utils/workflowTemplateDiff.js
// The inline implementation has been removed.

const STAGE_STATUS_CONFIG = {
  running:      { label: "Running",       className: "bg-amber-100 text-amber-800 animate-pulse" },
  needs_review: { label: "Needs Review",  className: "bg-amber-100 text-amber-700" },
  completed:    { label: "Done Today",    className: "bg-green-100 text-green-700" },
};

function StageStatusPill({ status }) {
  const cfg = STAGE_STATUS_CONFIG[status];
  if (!cfg) return null;
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${cfg.className}`}>
      {cfg.label}
    </span>
  );
}

function WorkflowSourceIndicator({ fromDB, dbDisplayName, dbSlug }) {
  return (
    <div className={[
      "flex items-center gap-2 rounded-lg border px-3 py-1.5 text-[11px]",
      fromDB
        ? "border-indigo-200 bg-indigo-50 text-indigo-700"
        : "border-slate-200 bg-slate-50 text-slate-500",
    ].join(" ")}>
      <span className={`h-1.5 w-1.5 rounded-full ${fromDB ? "bg-indigo-400" : "bg-slate-300"}`} />
      <span className="font-semibold">Workflow Source:</span>
      {fromDB ? (
        <>
          <span>Client Definition</span>
          <span className="text-slate-300">—</span>
          <span className="font-medium">{dbDisplayName}</span>
          <span className="font-mono opacity-60">({dbSlug})</span>
        </>
      ) : (
        <span>Default Template</span>
      )}
    </div>
  );
}

function EmptyState({ children }) {
  return <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">{children}</div>;
}

function Chip({ label, count }) {
  return (
    <div className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs">
      <span className="font-bold text-slate-900">{count}</span>
      <span className="text-slate-500">{label}</span>
    </div>
  );
}

// ── Phase 6G: ClientWorkflowHeader ───────────────────────────────────────────

function ClientWorkflowHeader({ activeProfile, resolvedWorkflow, overrideCount }) {
  const profile = PROFILE_MAP[activeProfile] ?? PROFILE_MAP["custom"];
  const source = resolvedWorkflow._source || "profile_template";
  const sourceLabel =
    source === "client_definition" ? "Client Definition"
    : source === "profile_template" ? "Profile Template"
    : "Default Template";
  const activeStageCount = Object.values(resolvedWorkflow.stages || {}).filter(
    (s) => s.required !== false
  ).length;
  const sourceColors =
    source === "client_definition"
      ? "border-indigo-200 bg-indigo-50 text-indigo-700"
      : source === "profile_template"
      ? "border-blue-200 bg-blue-50 text-blue-700"
      : "border-slate-200 bg-slate-50 text-slate-500";

  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Client</div>
            <div className="font-semibold text-slate-800">{profile.label}</div>
          </div>
          {profile.module ? (
            <>
              <div className="hidden h-6 w-px bg-slate-200 sm:block" />
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Module</div>
                <div className="text-slate-600 capitalize">{profile.module.replace(/_/g, " ")}</div>
              </div>
            </>
          ) : null}
          {resolvedWorkflow.display_name ? (
            <>
              <div className="hidden h-6 w-px bg-slate-200 sm:block" />
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Workflow</div>
                <div className="font-medium text-slate-800">{resolvedWorkflow.display_name}</div>
              </div>
            </>
          ) : null}
          <div className="hidden h-6 w-px bg-slate-200 sm:block" />
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Active Stages</div>
            <div className="font-semibold text-slate-800">{activeStageCount}</div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold ${sourceColors}`}>
            <span className="h-1.5 w-1.5 rounded-full bg-current opacity-60" />
            {sourceLabel}
          </span>
          {resolvedWorkflow._dbSlug ? (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-mono text-slate-500">
              {resolvedWorkflow._dbSlug}
            </span>
          ) : null}
          {overrideCount > 0 ? (
            <span className="rounded-full border border-amber-200 bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
              {overrideCount} customized stage{overrideCount !== 1 ? "s" : ""}
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function CommandContextCard({ activeProfile, activeWorkspace, demoMode, nextStep, reviewNeeded, readyToSend, responses, openDeals, template }) {
  const profile = PROFILE_MAP[activeProfile] ?? PROFILE_MAP["custom"];
  const tpl = template ?? WORKFLOW_TEMPLATES[activeProfile] ?? DEFAULT_TEMPLATE;
  const nextLabel = tpl.stages?.[nextStep]?.label ?? tpl.steps?.[nextStep]?.label ?? `Step ${nextStep}`;
  const chips = tpl.chips;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-5 py-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3 min-w-0">
          <div className="min-w-0">
            <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">System</div>
            <div className="mt-0.5 font-semibold text-slate-900 truncate">{profile.label}</div>
            {profile.module ? <div className="text-xs text-slate-500 capitalize">{profile.module.replace(/_/g, " ")}</div> : null}
          </div>
          <div className="hidden h-8 w-px bg-slate-200 sm:block" />
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Workspace</div>
            <div className="mt-0.5 text-sm font-medium text-slate-700">{activeWorkspace || "all"}</div>
          </div>
          <div className="hidden h-8 w-px bg-slate-200 sm:block" />
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Mode</div>
            <div className={["mt-0.5 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold", demoMode ? "bg-amber-100 text-amber-800" : "bg-green-100 text-green-800"].join(" ")}>
              {demoMode ? "Demo" : "Real"}
            </div>
          </div>
          <div className="hidden h-8 w-px bg-slate-200 sm:block" />
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Next Action</div>
            <div className="mt-0.5 text-sm font-semibold text-blue-700">Step {nextStep} — {nextLabel}</div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Chip label={chips.reviewNeeded} count={reviewNeeded} />
          <Chip label={chips.readyToSend} count={readyToSend} />
          <Chip label={chips.responses} count={responses} />
          <Chip label={chips.openDeals} count={openDeals} />
        </div>
      </div>
    </div>
  );
}

// ── Phase 6C: InsightCard ─────────────────────────────────────────────────────
const INSIGHT_ACCENT = {
  amber: { chip: "bg-amber-100 text-amber-700", bar: "bg-amber-400" },
  green: { chip: "bg-green-100 text-green-700", bar: "bg-green-500" },
  slate: { chip: "bg-slate-100 text-slate-500", bar: "bg-slate-400" },
};

function InsightCard({ insight, evidenceOpen, onToggleEvidence, onViewFull, onStatusChange, onGenerateAssets, generatingAssets }) {
  const pct = Math.round((insight.confidence_score ?? 0) * 100);
  const rec = insight.recommendation;
  const isPending = insight.status === "pending_review";
  const isApproved = insight.status === "approved";
  const accent =
    insight.status === "approved" ? INSIGHT_ACCENT.green
    : insight.status === "pending_review" ? INSIGHT_ACCENT.amber
    : INSIGHT_ACCENT.slate;

  const qualityTags = insight.quality_tags || [];

  return (
    <div className="flex flex-col rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-sm">
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <span className={`shrink-0 rounded-full px-1.5 py-0.5 font-semibold capitalize ${accent.chip}`}>
          {insight.insight_type?.replace(/_/g, " ")}
        </span>
        <button type="button" onClick={onViewFull} className="shrink-0 text-violet-600 underline hover:text-violet-800 whitespace-nowrap">
          View Full
        </button>
      </div>
      <div className="font-semibold text-slate-800 leading-snug mb-1">{insight.title}</div>
      <p className="text-slate-500 line-clamp-2 leading-relaxed mb-2">{insight.summary}</p>

      {/* Quality tags */}
      {qualityTags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {qualityTags.map((tag) => (
            <span key={tag} className="rounded-full bg-violet-50 border border-violet-200 px-1.5 py-0.5 text-[10px] font-semibold text-violet-700">
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Confidence bar */}
      <div className="mb-2">
        <div className="flex justify-between text-[10px] text-slate-400 mb-0.5">
          <span>Confidence</span><span className="font-semibold text-slate-600">{pct}%</span>
        </div>
        <div className="h-1 w-full rounded-full bg-slate-100">
          <div className={`h-1 rounded-full transition-all ${accent.bar}`} style={{ width: `${pct}%` }} />
        </div>
      </div>

      {/* Recommended platforms / asset types */}
      {rec?.recommended_platforms?.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-1.5">
          {rec.recommended_platforms.slice(0, 3).map((p) => (
            <span key={p} className="rounded-full bg-violet-50 border border-violet-200 px-1.5 text-violet-600">{p}</span>
          ))}
        </div>
      )}
      {rec?.recommended_asset_types?.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-1.5">
          {rec.recommended_asset_types.slice(0, 3).map((t) => (
            <span key={t} className="rounded-full bg-slate-100 px-1.5 text-slate-600">{t.replace(/_/g, " ")}</span>
          ))}
        </div>
      )}

      {/* Evidence toggle */}
      {insight.evidence?.length > 0 && (
        <button
          type="button"
          onClick={onToggleEvidence}
          className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-slate-700 mb-1.5 w-fit"
        >
          <ChevronDown size={11} className={evidenceOpen ? "rotate-180 transition-transform" : "transition-transform"} />
          {insight.evidence.length} evidence item{insight.evidence.length !== 1 ? "s" : ""}
        </button>
      )}
      {evidenceOpen && insight.evidence?.length > 0 && (
        <div className="mb-2 space-y-1.5">
          {insight.evidence.map((ev, idx) => (
            <div key={idx} className="rounded border border-slate-100 bg-slate-50 px-2 py-1.5 space-y-0.5">
              <div className="flex items-center gap-1.5 flex-wrap">
                {ev.platform && <span className="font-semibold text-slate-700">{ev.platform}</span>}
                {ev.signal_type && <span className="rounded-full bg-blue-50 border border-blue-100 px-1.5 text-blue-500">{ev.signal_type}</span>}
                {ev.configured_source && (
                  <span className="rounded-full bg-teal-50 border border-teal-200 px-1.5 py-0.5 text-[9px] font-semibold text-teal-700">
                    ✓ Configured Source{ev.source_label ? `: ${ev.source_label}` : ""}
                  </span>
                )}
              </div>
              {ev.keyword && (
                <div className="text-slate-500">
                  {ev.keyword}
                  {ev.growth_pct != null && <span className="ml-1 text-green-600 font-semibold">+{ev.growth_pct}%</span>}
                </div>
              )}
              {ev.metric && ev.value != null && (
                <div className="text-slate-500">{ev.metric}: <span className="font-medium">{ev.value.toLocaleString()}</span></div>
              )}
              {ev.notes && <div className="text-slate-400 italic">{ev.notes}</div>}
            </div>
          ))}
        </div>
      )}

      {/* Footer: meta + actions */}
      <div className="mt-auto pt-2 border-t border-slate-100 flex items-center justify-between gap-2">
        <div className="text-[10px] text-slate-400 truncate">
          {insight.source_agent && <span>{insight.source_agent}</span>}
        </div>
        <div className="flex gap-1.5 shrink-0 flex-wrap justify-end">
          {isPending && (
            <>
              <button
                type="button"
                onClick={() => onStatusChange("approved")}
                className="rounded px-2 py-0.5 bg-green-100 text-green-700 font-semibold hover:bg-green-200"
              >Approve</button>
              <button
                type="button"
                onClick={() => onStatusChange("deferred")}
                className="rounded px-2 py-0.5 bg-slate-100 text-slate-500 font-semibold hover:bg-slate-200"
              >Defer</button>
            </>
          )}
          {isApproved && onGenerateAssets && (
            <button
              type="button"
              onClick={onGenerateAssets}
              disabled={generatingAssets}
              className="rounded px-2 py-0.5 bg-violet-100 text-violet-700 font-semibold hover:bg-violet-200 disabled:opacity-50"
            >
              {generatingAssets ? "Generating…" : "Generate Assets"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Phase 6E: SourceReadinessCard ────────────────────────────────────────────

const RECOMMENDED_SOURCES = ["website", "linkedin"];

function SourceReadinessCard({ clientSources }) {
  const activeSources = clientSources.filter((s) => s.status === "active");
  const connectedTypes = [...new Set(activeSources.map((s) => s.source_type))];
  const missing = RECOMMENDED_SOURCES.filter((t) => !connectedTypes.includes(t));

  // Phase 6F: readiness scoring
  let readiness, readinessLabel, readinessClass, guidanceText;
  if (activeSources.length >= 3) {
    readiness = "ready";
    readinessLabel = "Ready";
    readinessClass = "bg-green-100 text-green-700 border-green-300";
    guidanceText = "Ready for discovery scanning.";
  } else if (activeSources.length >= 1) {
    readiness = "partial";
    readinessLabel = "Partial";
    readinessClass = "bg-amber-100 text-amber-700 border-amber-300";
    guidanceText = "Discovery quality will improve with more connected media sources.";
  } else {
    readiness = "missing";
    readinessLabel = "Missing";
    readinessClass = "bg-red-100 text-red-700 border-red-300";
    guidanceText = "No client sources configured yet.";
  }

  const cardBorder = readiness === "ready"
    ? "border-teal-200 bg-teal-50"
    : readiness === "partial"
    ? "border-amber-200 bg-amber-50"
    : "border-slate-200 bg-white";

  return (
    <div className={`rounded-lg border px-4 py-3 text-xs space-y-2 ${cardBorder}`}>
      <div className="flex items-center justify-between">
        <span className="font-semibold text-slate-800">Source Readiness</span>
        <div className="flex items-center gap-2">
          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${readinessClass}`}>
            {readinessLabel}
          </span>
          <span className="text-slate-500">{activeSources.length} active / {clientSources.length} total</span>
        </div>
      </div>
      <p className="text-slate-600">{guidanceText}</p>
      {connectedTypes.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {connectedTypes.map((t) => (
            <span key={t} className="rounded-full bg-teal-100 border border-teal-200 px-2 py-0.5 text-[10px] font-medium text-teal-700 capitalize">
              {t.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      )}
      {readiness === "missing" && (
        <p className="text-slate-500 italic">
          Go to Admin Onboarding to connect sources.
        </p>
      )}
      {missing.length > 0 && readiness !== "missing" && (
        <p className="text-amber-700 text-[10px]">
          Missing recommended: {missing.map((t) => t.replace(/_/g, " ")).join(", ")}
        </p>
      )}
    </div>
  );
}

// ── Phase 6F: DiscoveryRunCompletionCard ──────────────────────────────────────

const COMPLETION_BORDER = {
  completed: "border-green-200 bg-green-50",
  partial: "border-amber-200 bg-amber-50",
  failed: "border-red-200 bg-red-50",
  running: "border-blue-200 bg-blue-50",
};

const COMPLETION_BADGE = {
  completed: "bg-green-600 text-white",
  partial: "bg-amber-500 text-white",
  failed: "bg-red-600 text-white",
  running: "bg-blue-500 text-white",
};

function DiscoveryRunCompletionCard({ runSummaries }) {
  const today = new Date().toDateString();
  const todaySummaries = runSummaries.filter((s) => {
    const ts = s.completed_at || s.created_at;
    return ts && new Date(ts).toDateString() === today;
  });

  if (todaySummaries.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
        No discovery runs completed today.
      </div>
    );
  }

  const latest = todaySummaries[0];
  const state = latest.completion_state || "running";
  const cardClass = COMPLETION_BORDER[state] || "border-slate-200 bg-white";
  const badgeClass = COMPLETION_BADGE[state] || "bg-slate-500 text-white";
  const ts = latest.completed_at || latest.created_at;

  return (
    <div className={`rounded-lg border px-4 py-3 text-xs space-y-2 ${cardClass}`}>
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize ${badgeClass}`}>
          {state === "completed" ? "Completed Today" : state.charAt(0).toUpperCase() + state.slice(1)}
        </span>
        {latest.agent_name && (
          <span className="text-slate-600 font-medium">{latest.agent_name}</span>
        )}
        {ts && (
          <span className="ml-auto text-slate-400">
            {new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>
        )}
      </div>
      {latest.summary && (
        <p className="text-slate-700 leading-relaxed">{latest.summary}</p>
      )}
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-slate-600">
        <span><strong>{latest.sources_checked ?? 0}</strong> sources checked</span>
        <span><strong>{latest.insights_generated ?? 0}</strong> insights generated</span>
        <span><strong>{latest.high_confidence_insights ?? 0}</strong> high confidence</span>
        {latest.platforms_checked?.length > 0 && (
          <span>Platforms: {latest.platforms_checked.slice(0, 4).join(", ")}</span>
        )}
      </div>
      {latest.next_recommended_action && (
        <p className="text-slate-700 font-medium">
          Next: {latest.next_recommended_action}
        </p>
      )}
    </div>
  );
}

// ── Phase 6F: DiscoveryExecutionTimeline ──────────────────────────────────────

const EXECUTION_STAGES = [
  { key: "sources_loaded", label: "Sources Loaded", icon: CheckCircle2 },
  { key: "platforms_scanned", label: "Platforms Scanned", icon: Search },
  { key: "signals_ranked", label: "Signals Ranked", icon: TrendingUp },
  { key: "insights_generated", label: "Insights Generated", icon: Lightbulb },
  { key: "recommendations_prepared", label: "Recommendations Prepared", icon: CheckCircle2 },
];

function DiscoveryExecutionTimeline({ runSummaries, discoveryInsights }) {
  const latestSummary = runSummaries.length > 0 ? runSummaries[0] : null;

  if (!latestSummary && discoveryInsights.length === 0) return null;

  const isCompleted = latestSummary?.completion_state === "completed";
  const isFailed = latestSummary?.completion_state === "failed";

  function stageDetail(stage) {
    if (!latestSummary) return null;
    if (stage.key === "sources_loaded") {
      const used = latestSummary.configured_sources_used || [];
      return used.length > 0 ? used.join(", ") : `${latestSummary.sources_checked ?? 0} sources`;
    }
    if (stage.key === "platforms_scanned") {
      const plats = latestSummary.platforms_checked || [];
      return plats.length > 0 ? plats.join(", ") : null;
    }
    if (stage.key === "insights_generated") {
      return latestSummary.insights_generated != null
        ? `${latestSummary.insights_generated} insight${latestSummary.insights_generated !== 1 ? "s" : ""}`
        : null;
    }
    if (stage.key === "recommendations_prepared" && latestSummary.next_recommended_action) {
      return latestSummary.next_recommended_action;
    }
    return null;
  }

  function stageStatus(idx) {
    if (isFailed) return idx === 0 ? "done" : "error";
    if (!latestSummary) return discoveryInsights.length > 0 ? "done" : "pending";
    if (isCompleted) return "done";
    return idx < 2 ? "done" : "pending";
  }

  const ts = latestSummary?.completed_at || latestSummary?.created_at;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 justify-between">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Execution Timeline</h4>
        {ts && (
          <span className="text-[10px] text-slate-400">
            {new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>
        )}
      </div>
      <ol className="space-y-1.5">
        {EXECUTION_STAGES.map((stage, idx) => {
          const status = stageStatus(idx);
          const detail = stageDetail(stage);
          const Icon = stage.icon;
          return (
            <li key={stage.key} className="flex items-start gap-2 text-xs">
              <Icon
                size={13}
                className={`mt-0.5 shrink-0 ${
                  status === "done" ? "text-green-500"
                  : status === "error" ? "text-red-400"
                  : "text-slate-300"
                }`}
              />
              <div className="min-w-0">
                <span className={`font-medium ${status === "done" ? "text-slate-700" : "text-slate-400"}`}>
                  {stage.label}
                </span>
                {detail && (
                  <span className="ml-2 text-slate-400">{detail}</span>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// ── Phase 6H: WorkflowRunStatusPill ──────────────────────────────────────────

const WF_RUN_STATUS_CONFIG = {
  queued:       { label: "Queued",        className: "bg-slate-100 text-slate-500" },
  running:      { label: "Running",       className: "bg-amber-100 text-amber-700 animate-pulse" },
  completed:    { label: "Completed",     className: "bg-green-100 text-green-700" },
  failed:       { label: "Failed",        className: "bg-red-100 text-red-600" },
  needs_review: { label: "Needs Review",  className: "bg-violet-100 text-violet-700" },
};

function WorkflowRunStatusPill({ status }) {
  const cfg = WF_RUN_STATUS_CONFIG[status] || { label: status, className: "bg-slate-100 text-slate-500" };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${cfg.className}`}>
      {cfg.label}
    </span>
  );
}

// ── Phase 6H: WorkflowRunSummaryCard ─────────────────────────────────────────

function WorkflowRunSummaryCard({ run, onContinue, continueLabel }) {
  if (!run) return null;
  const timeAgo = run.completed_at ? (() => {
    const diff = Date.now() - new Date(run.completed_at).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  })() : null;

  const outputs = run.outputs || {};

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-3">
      {/* Header row */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-slate-800">{run.title || run.run_type}</span>
            <WorkflowRunStatusPill status={run.status} />
          </div>
          {timeAgo && (
            <div className="text-xs text-slate-400 mt-0.5">Completed {timeAgo}</div>
          )}
        </div>
        {onContinue && (
          <button
            type="button"
            onClick={onContinue}
            className="shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 transition"
          >
            {continueLabel || "Continue"}
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Summary */}
      {run.summary && (
        <p className="text-xs text-slate-600 leading-relaxed">{run.summary}</p>
      )}

      {/* Outputs */}
      {Object.keys(outputs).length > 0 && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
          {outputs.insights_generated != null && (
            <div><span className="text-slate-400">Insights:</span> <strong className="text-slate-700">{outputs.insights_generated}</strong></div>
          )}
          {outputs.high_confidence_count != null && (
            <div><span className="text-slate-400">High confidence:</span> <strong className="text-slate-700">{outputs.high_confidence_count}</strong></div>
          )}
          {outputs.assets_generated != null && (
            <div><span className="text-slate-400">Assets:</span> <strong className="text-slate-700">{outputs.assets_generated}</strong></div>
          )}
          {outputs.approval_requests_created != null && (
            <div><span className="text-slate-400">For review:</span> <strong className="text-slate-700">{outputs.approval_requests_created}</strong></div>
          )}
          {outputs.platforms_checked?.length > 0 && (
            <div className="col-span-2 sm:col-span-3">
              <span className="text-slate-400">Platforms:</span>{" "}
              <span className="text-slate-600">{outputs.platforms_checked.join(", ")}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Phase 6H: ContinueWorkflowCTA ────────────────────────────────────────────

// ── Phase 6N: MemoryContextPanel ─────────────────────────────────────────────
function MemoryContextPanel({ run }) {
  if (!run?.client_memory_version || !run?.memory_snapshot) return null;
  const snap = run.memory_snapshot;
  const vt = snap.voice_tone || {};
  const toneParts = [vt.tone, vt.style].filter(Boolean);
  const winning = (snap.winning_patterns || []).slice(0, 3);
  const blocked = (snap.blocked_claims || []).slice(0, 3);
  const hasSignals = toneParts.length + winning.length + blocked.length > 0;

  return (
    <div className="rounded-lg border border-violet-200 bg-violet-50 px-4 py-3 text-xs">
      <div className="flex items-center gap-2 mb-2">
        <Brain className="h-3.5 w-3.5 text-violet-500" />
        <span className="font-semibold text-violet-700">
          Using Client Memory v{run.client_memory_version}
        </span>
        {run.memory_context_hash && (
          <span className="text-violet-400 font-mono text-[10px]">#{run.memory_context_hash.slice(0, 8)}</span>
        )}
      </div>
      {hasSignals ? (
        <div className="space-y-1">
          {toneParts.length > 0 && (
            <div className="text-violet-700">
              <span className="font-medium">Tone:</span> {toneParts.join(", ")}
            </div>
          )}
          {winning.map((p, i) => (
            <div key={i} className="text-violet-600">✓ {p}</div>
          ))}
          {blocked.map((c, i) => (
            <div key={i} className="text-amber-600">⚠ Blocked: {c}</div>
          ))}
        </div>
      ) : (
        <div className="text-violet-500 italic">Memory loaded — no patterns configured yet.</div>
      )}
    </div>
  );
}

function ContinueWorkflowCTA({ discoveryRun, contentBuildRun, onRunContentBuild, onGoToReview, onGoToDistribution, readyToSendCount }) {
  // Determine the primary CTA based on workflow progression

  // Phase 6K: all assets published — content_build run is fully completed
  if (contentBuildRun?.status === "completed" && readyToSendCount === 0) {
    return (
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
        <div className="flex items-center gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-700">Workflow cycle complete</div>
            <div className="text-xs text-slate-500 mt-0.5">All content assets from this build have been published or archived.</div>
          </div>
        </div>
      </div>
    );
  }

  if (readyToSendCount > 0) {
    return (
      <div className="rounded-lg border border-green-200 bg-green-50 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-green-800">Content approved and ready</div>
            <div className="text-xs text-green-600 mt-0.5">{readyToSendCount} asset{readyToSendCount !== 1 ? "s" : ""} ready for distribution in Step 5.</div>
          </div>
          <button
            type="button"
            onClick={onGoToDistribution}
            className="shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-green-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-green-700 transition"
          >
            Go to Distribution <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    );
  }

  if (contentBuildRun) {
    return (
      <div className="rounded-lg border border-violet-200 bg-violet-50 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-violet-800">Content build complete</div>
            <div className="text-xs text-violet-600 mt-0.5">Review generated assets in Step 4 before distribution.</div>
          </div>
          <button
            type="button"
            onClick={onGoToReview}
            className="shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-violet-700 transition"
          >
            Review Content <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    );
  }

  if (discoveryRun?.status === "completed" && !contentBuildRun) {
    return (
      <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-blue-800">Discovery complete — run Content Build next</div>
            <div className="text-xs text-blue-600 mt-0.5">
              {discoveryRun.outputs?.insights_generated
                ? `${discoveryRun.outputs.insights_generated} insight${discoveryRun.outputs.insights_generated !== 1 ? "s" : ""} ready to convert into content assets.`
                : "Convert discovery insights into reviewable content assets."}
            </div>
          </div>
          {onRunContentBuild && (
            <button
              type="button"
              onClick={onRunContentBuild}
              className="shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 transition"
            >
              Run Content Build <ArrowRight className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>
    );
  }

  return null;
}

// ── Phase 6F: WorkflowAssetPreviewModal ───────────────────────────────────────

function WorkflowAssetPreviewModal({ asset, discoveryInsightMap, workflowRunsById, onClose }) {
  if (!asset) return null;

  const linkedInsight = asset.source_discovery_insight_id
    ? discoveryInsightMap?.[asset.source_discovery_insight_id]
    : asset.source_insight_id
    ? discoveryInsightMap?.[asset.source_insight_id]
    : null;
  const linkedWorkflowRun = asset.workflow_run_id
    ? workflowRunsById?.[asset.workflow_run_id]
    : null;
  const hasAudio = asset.audio_url || asset.source_audio_url;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-2xl rounded-xl bg-white shadow-2xl overflow-hidden max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 px-5 pt-5 pb-3 border-b border-slate-100">
          <div className="min-w-0">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-1">
              {asset.asset_type?.replace(/_/g, " ")} · {asset.approval_state}
            </div>
            <h3 className="text-base font-semibold text-slate-900 leading-snug">{asset.title || "Untitled Asset"}</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="overflow-y-auto flex-1 px-5 py-4 space-y-4">
          {/* Full content */}
          {(asset.content || asset.body) && (
            <div>
              <h4 className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1.5">Content</h4>
              <div className="whitespace-pre-wrap rounded-lg border border-slate-100 bg-slate-50 p-3 text-sm leading-6 text-slate-700">
                {asset.content || asset.body}
              </div>
            </div>
          )}

          {/* Audio player */}
          {hasAudio && (
            <div>
              <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1.5">
                <Volume2 size={11} />
                Audio
              </div>
              <audio
                controls
                src={asset.audio_url || asset.source_audio_url}
                className="w-full rounded"
              />
            </div>
          )}

          {/* Phase 6H: full lineage — Discovery Insight → Workflow Run → Asset */}
          {(linkedInsight || linkedWorkflowRun) && (
            <div>
              <h4 className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-2">Content Lineage</h4>
              <div className="space-y-2">
                {/* Insight node */}
                {linkedInsight && (
                  <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 space-y-1 text-xs">
                    <div className="flex items-center gap-1.5 font-semibold text-violet-700">
                      <Lightbulb className="h-3 w-3" />
                      Discovery Insight
                    </div>
                    <div className="text-violet-800 font-medium">{linkedInsight.title}</div>
                    {linkedInsight.confidence_score != null && (
                      <div className="text-violet-600">Confidence: {Math.round(linkedInsight.confidence_score * 100)}%</div>
                    )}
                    {linkedInsight.recommendation?.rationale && (
                      <p className="text-violet-600 leading-relaxed">{linkedInsight.recommendation.rationale}</p>
                    )}
                  </div>
                )}
                {(linkedInsight && linkedWorkflowRun) && (
                  <div className="flex items-center gap-2 text-xs text-slate-400 pl-4">
                    <ArrowRight className="h-3 w-3" /> used in
                  </div>
                )}
                {/* Workflow run node */}
                {linkedWorkflowRun && (
                  <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 space-y-1 text-xs">
                    <div className="flex items-center gap-1.5 font-semibold text-blue-700">
                      <Play className="h-3 w-3" />
                      Workflow Run
                    </div>
                    <div className="text-blue-800 font-medium">{linkedWorkflowRun.title || linkedWorkflowRun.run_type}</div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <WorkflowRunStatusPill status={linkedWorkflowRun.status} />
                      <span className="text-blue-500">Stage {linkedWorkflowRun.workflow_stage}</span>
                      {linkedWorkflowRun.completed_at && (
                        <span className="text-blue-400">{new Date(linkedWorkflowRun.completed_at).toLocaleString()}</span>
                      )}
                    </div>
                  </div>
                )}
                {linkedWorkflowRun && (
                  <div className="flex items-center gap-2 text-xs text-slate-400 pl-4">
                    <ArrowRight className="h-3 w-3" /> generated
                  </div>
                )}
                {/* Asset node (current) */}
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs">
                  <div className="flex items-center gap-1.5 font-semibold text-slate-600">
                    <FileText className="h-3 w-3" />
                    Content Asset (this item)
                  </div>
                  <div className="text-slate-700 font-medium mt-0.5">{asset.title || "Untitled Asset"}</div>
                  <div className="text-slate-400 mt-0.5">{asset.asset_type?.replace(/_/g, " ")} · {asset.platform}</div>
                </div>
              </div>
            </div>
          )}

          {/* Legacy: discovery lineage for assets without workflow_run linkage */}
          {!linkedWorkflowRun && linkedInsight && (
            <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 space-y-2 text-xs">
              <div className="font-semibold text-violet-800">Generated from Discovery Insight</div>
              <div className="text-violet-700 font-medium">{linkedInsight.title}</div>
              {linkedInsight.confidence_score != null && (
                <div className="text-violet-600">
                  Confidence: {Math.round(linkedInsight.confidence_score * 100)}%
                </div>
              )}
              {linkedInsight.recommendation?.rationale && (
                <p className="text-violet-600 leading-relaxed">{linkedInsight.recommendation.rationale}</p>
              )}
              {linkedInsight.evidence?.length > 0 && (
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-violet-500 mb-1">Evidence</div>
                  <ul className="space-y-0.5">
                    {linkedInsight.evidence.slice(0, 4).map((ev, i) => (
                      <li key={i} className="text-violet-600">
                        {ev.platform && <strong>{ev.platform}</strong>}
                        {ev.keyword && <span> — {ev.keyword}</span>}
                        {ev.configured_source && (
                          <span className="ml-1 rounded-full bg-teal-100 border border-teal-200 px-1.5 text-[9px] font-semibold text-teal-700">
                            ✓ Configured
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Metadata */}
          <div>
            <h4 className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1.5">Metadata</h4>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-600">
              {asset.platform && <><dt className="text-slate-400">Platform</dt><dd>{asset.platform}</dd></>}
              {asset.module && <><dt className="text-slate-400">Module</dt><dd>{asset.module}</dd></>}
              {asset.workspace_slug && <><dt className="text-slate-400">Workspace</dt><dd>{asset.workspace_slug}</dd></>}
              {asset.created_at && (
                <><dt className="text-slate-400">Generated</dt>
                <dd>{new Date(asset.created_at).toLocaleString()}</dd></>
              )}
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function WorkflowPage({ activeProfile = "custom", demoMode = false, activeWorkspace }) {
  const livePanelRef = useRef(null);
  const [distributionDrafts, setDistributionDrafts] = useState({});
  const [publishDraftOpen, setPublishDraftOpen] = useState({});
  const [tasks, setTasks] = useState([]);
  const [messages, setMessages] = useState([]);
  const [approvalRequests, setApprovalRequests] = useState([]);
  const [workflowAssets, setWorkflowAssets] = useState([]);
  const [deals, setDeals] = useState([]);
  const [commerceRevenueCents, setCommerceRevenueCents] = useState(0);
  const [agentRuns, setAgentRuns] = useState([]);
  const [activeTask, setActiveTask] = useState(null);
  const [activeRunDetail, setActiveRunDetail] = useState(null);
  const [activeAction, setActiveAction] = useState(null);
  const [config, setConfig] = useState({ module: "contractor_growth", limit: 10, priority: "normal", segment: "", high_priority: false });
  const [operatorConfig, setOperatorConfig] = useState({});
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [otherReviewOpen, setOtherReviewOpen] = useState(false);
  const [backlogOpen, setBacklogOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");
  const [panelLoading, setPanelLoading] = useState(false);
  const [notes, setNotes] = useState({});
  // Phase 6A: persisted workflow definition for the active workspace
  const [clientWorkflowDef, setClientWorkflowDef] = useState(null);
  // Phase 6B/6G: resolved workflow — DB-normalized or static fallback, always uses stages shape
  const [resolvedWorkflow, setResolvedWorkflow] = useState(() =>
    normalizeWorkflowDefinition({
      workflowDefinition: null,
      fallbackTemplate: WORKFLOW_TEMPLATES[activeProfile] ?? DEFAULT_TEMPLATE,
      defaultTemplate: DEFAULT_TEMPLATE,
    })
  );
  // Phase 6C: discovery insights
  const [discoveryInsights, setDiscoveryInsights] = useState([]);
  const [clientSources, setClientSources] = useState([]);
  const [discoveryRunSummaries, setDiscoveryRunSummaries] = useState([]);
  const [activeInsightModal, setActiveInsightModal] = useState(null);
  const [insightEvidenceOpen, setInsightEvidenceOpen] = useState({});
  // Phase 6F: asset preview modal + distribution platforms
  const [activeAssetPreview, setActiveAssetPreview] = useState(null);
  const [distributionPlatforms, setDistributionPlatforms] = useState([]);
  // Phase 6D: generating assets state
  const [generatingAssetForInsight, setGeneratingAssetForInsight] = useState("");
  // Phase 6H: structured workflow runs
  const [workflowRuns, setWorkflowRuns] = useState([]);
  // Stepper state — tracks which step is expanded.
  // `manualStepOverride` is set true when the user clicks a step header;
  // it suppresses auto-advance until the next full loadWorkflow() completes.
  const [expandedStep, setExpandedStep] = useState(1);
  const manualStepOverride = useRef(false);

  // Sync resolvedWorkflow with activeProfile when there is no DB definition loaded
  const activeTemplate = resolvedWorkflow; // alias kept for backward compat (runCards, chips)

  function selectStep(stepNumber) {
    manualStepOverride.current = true;
    setExpandedStep(stepNumber);
  }

  async function loadWorkflow() {
    const [taskData, messageData, approvalData, dealData, runData, assetData, commerceData] = await Promise.all([
      api.agentTasks({ limit: "200" }),
      api.messages({ limit: "250" }),
      api.approvalRequests({ limit: "200" }),
      api.deals({ limit: "250" }),
      api.agentRuns({ limit: "25" }),
      api.workflowAssets({ limit: "200" }).catch(() => ({ items: [] })),
      api.commerceTransactions({}).catch(() => ({ items: [] })),
    ]);
    const nextTasks = taskData.items || [];
    const nextRuns = runData.items || [];
    setTasks(nextTasks);
    setMessages(messageData.items || []);
    setApprovalRequests(approvalData.items || []);
    setWorkflowAssets(assetData.items || []);
    setDeals(dealData.items || []);
    setCommerceRevenueCents(
      (commerceData.items || [])
        .filter((t) => t.status === "completed")
        .reduce((sum, t) => sum + (t.amount_cents || 0), 0)
    );
    setAgentRuns(nextRuns);

    if (!activeTask && !activeRunDetail) {
      const latestTaskWithRun = nextTasks.find((task) => task.linked_run_id);
      if (latestTaskWithRun) {
        setActiveTask(latestTaskWithRun);
        await refreshRunDetail(latestTaskWithRun.linked_run_id, { quiet: true });
      } else if (nextRuns[0]?.run_id) {
        await refreshRunDetail(nextRuns[0].run_id, { quiet: true });
      }
    }
    // Allow auto-advance again after a full data refresh
    manualStepOverride.current = false;
  }

  // Phase 6J: re-run loadWorkflow on workspace change to prevent cross-workspace
  // approval/message/task state contamination (fixes "32 Review needed" stale count).
  useEffect(() => {
    loadWorkflow();
  }, [activeWorkspace]); // eslint-disable-line react-hooks/exhaustive-deps

  // Phase 6B/6G: Try to resolve a persisted workflow definition for the active workspace.
  // Falls back silently — never blocks the existing workflow render.
  useEffect(() => {
    setClientWorkflowDef(null);
    setResolvedWorkflow(
      normalizeWorkflowDefinition({
        workflowDefinition: null,
        fallbackTemplate: WORKFLOW_TEMPLATES[activeProfile] ?? DEFAULT_TEMPLATE,
        defaultTemplate: DEFAULT_TEMPLATE,
      })
    );
    if (!activeWorkspace || activeWorkspace === "all") return;
    let cancelled = false;
    api.getWorkspace(activeWorkspace)
      .then((wsData) => {
        const profileSlug = wsData?.item?.client_profile_id;
        if (!profileSlug || cancelled) return null;
        return api.clientProfileWorkflowDefinition(profileSlug);
      })
      .then((defData) => {
        if (!cancelled && defData?.item) {
          setClientWorkflowDef(defData.item);
          setResolvedWorkflow(
            normalizeWorkflowDefinition({
              workflowDefinition: defData.item,
              fallbackTemplate:
                WORKFLOW_TEMPLATES[defData.item.system_profile_id] ??
                WORKFLOW_TEMPLATES[activeProfile] ??
                DEFAULT_TEMPLATE,
              defaultTemplate: DEFAULT_TEMPLATE,
            })
          );
        }
      })
      .catch(() => {
        // 404 or any error — silently ignore, fallback is current behavior
      });
    return () => { cancelled = true; };
  }, [activeWorkspace]);

  // Phase 6C: load discovery insights for the active workspace
  useEffect(() => {
    setDiscoveryInsights([]);
    if (!activeWorkspace || activeWorkspace === "all") return;
    const result = api.discoveryInsights({ workspace_slug: activeWorkspace, limit: "100" });
    if (!result?.then) return;
    result
      .then((data) => setDiscoveryInsights(data.items || []))
      .catch(() => {});
  }, [activeWorkspace]);

  // Phase 6E: load client sources for the active workspace
  useEffect(() => {
    setClientSources([]);
    if (!activeWorkspace || activeWorkspace === "all") return;
    api.clientSources({ workspace_slug: activeWorkspace, limit: "100" })
      .then((data) => setClientSources(data.items || []))
      .catch(() => {});
  }, [activeWorkspace]);

  // Phase 6F: load discovery run summaries
  useEffect(() => {
    setDiscoveryRunSummaries([]);
    if (!activeWorkspace || activeWorkspace === "all") return;
    api.discoveryRunSummaries(activeWorkspace)
      .then((data) => setDiscoveryRunSummaries(data.items || []))
      .catch(() => {});
  }, [activeWorkspace]);

  // Phase 6H: load structured workflow runs
  useEffect(() => {
    setWorkflowRuns([]);
    if (!activeWorkspace || activeWorkspace === "all") return;
    api.workflowRuns({ workspaceSlug: activeWorkspace, limit: 50 })
      .then((data) => setWorkflowRuns(data.items || []))
      .catch(() => {});
  }, [activeWorkspace]);

  // When profile changes without a workspace change, sync the fallback workflow
  useEffect(() => {
    if (!clientWorkflowDef) {
      setResolvedWorkflow(
        normalizeWorkflowDefinition({
          workflowDefinition: null,
          fallbackTemplate: WORKFLOW_TEMPLATES[activeProfile] ?? DEFAULT_TEMPLATE,
          defaultTemplate: DEFAULT_TEMPLATE,
        })
      );
    }
  }, [activeProfile]);

  useEffect(() => {
    if (!activeTask?.linked_run_id) return;
    if (!["running", "waiting_for_approval"].includes(activeTask.status)) return;
    const interval = window.setInterval(() => {
      refreshRunDetail(activeTask.linked_run_id, { quiet: true });
      loadWorkflow();
    }, 2500);
    return () => window.clearInterval(interval);
  }, [activeTask?.linked_run_id, activeTask?.status]);

  function openModal(card) {
    setNotice("");
    setActiveAction(card);
    setAdvancedOpen(false);
    const opFields = {};
    for (const field of card.modalFields ?? []) {
      opFields[field.id] = field.defaultValue ?? "";
    }
    setOperatorConfig(opFields);
    setConfig({
      module: card.defaultModule ?? "contractor_growth",
      limit: card.defaultLimit ?? 10,
      priority: card.defaultPriority ?? "normal",
      segment: "",
      high_priority: false,
    });
  }

  async function refreshRunDetail(runId, options = {}) {
    if (!runId) return;
    if (!options.quiet) setPanelLoading(true);
    try {
      const detail = await api.agentRunDetail(runId);
      setActiveRunDetail(detail);
    } catch (error) {
      if (!options.quiet) setNotice(error.message);
    } finally {
      if (!options.quiet) setPanelLoading(false);
    }
  }

  async function createTask(event) {
    event.preventDefault();
    if (!activeAction) return;
    setNotice("");
    const hasOperatorFields = (activeAction.modalFields?.length ?? 0) > 0;
    const RESERVED_IDS = new Set(["limit", "priority"]);
    const effectiveLimit = hasOperatorFields ? Number(operatorConfig.limit ?? config.limit) : Number(config.limit);
    const effectivePriority = hasOperatorFields ? (operatorConfig.priority ?? config.priority) : config.priority;
    const operatorFieldEntries = hasOperatorFields
      ? Object.entries(operatorConfig)
          .filter(([id, val]) => !RESERVED_IDS.has(id) && String(val ?? "").trim() !== "")
          .map(([id, val]) => [id === "notes" ? "campaign_notes" : id, val])
      : [];
    const input_config = {
      limit: effectiveLimit,
      ...Object.fromEntries(operatorFieldEntries),
      filters: {
        ...(config.segment.trim() ? { segment: config.segment.trim() } : {}),
        ...(config.high_priority ? { high_priority: true } : {}),
      },
    };
    try {
      const result = await api.createAgentTask({
        agent_name: activeAction.agent_name,
        module: config.module,
        task_type: activeAction.task_type,
        priority: effectivePriority,
        input_config,
        workspace_slug: activeWorkspace || "",
        card_id: activeAction.id || "",
      });
      const task = result.item;
      setActiveAction(null);
      setActiveTask({ ...task, status: "running", started_at: new Date().toISOString() });
      setActiveRunDetail(null);
      setPanelLoading(true);
      // Ensure Step 3 (Agent Activity) is expanded before scrolling
      manualStepOverride.current = false;
      setExpandedStep(3);
      livePanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      const runResult = await api.runAgentTask(task._id);
      const updatedTask = runResult.item || task;
      setActiveTask(updatedTask);
      setNotice(runResult.message || "Agent task dry-run completed. No outbound action taken.");
      if (updatedTask.linked_run_id) await refreshRunDetail(updatedTask.linked_run_id);
      await loadWorkflow();
      // Phase 6H: refresh workflow runs after any task run
      if (activeWorkspace && activeWorkspace !== "all") {
        api.workflowRuns({ workspaceSlug: activeWorkspace, limit: 50 })
          .then((data) => setWorkflowRuns(data.items || []))
          .catch(() => {});
      }
      // Phase 6D: refresh discovery insights after a content_discovery run
      if (activeAction?.id === "content_discovery" && activeWorkspace && activeWorkspace !== "all") {
        const insightResult = api.discoveryInsights({ workspace_slug: activeWorkspace, limit: "100" });
        if (insightResult?.then) {
          insightResult.then((data) => setDiscoveryInsights(data.items || [])).catch(() => {});
        }
      }
    } catch (error) {
      setNotice(error.message);
    } finally {
      setPanelLoading(false);
    }
  }

  async function reviewMessage(message, decision) {
    setBusyId(message._id);
    setNotice("");
    try {
      await api.reviewMessage(message._id, { decision, note: `Reviewed from Workflow Mode v1: ${decision}.` });
      setNotice(`Saved ${decision}. No message sent.`);
      await loadWorkflow();
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusyId("");
    }
  }

  async function decideApproval(item, decision) {
    setBusyId(item._id);
    setNotice("");
    try {
      const result = await api.decideApprovalRequest(item._id, { decision, note: notes[item._id] || "" });
      setNotice(result.message || "Approval decision saved. No outbound action taken.");
      // Phase 6K: when approving an approval_request linked to a workflow_asset, optimistically
      // set that asset's approval_state so Step 5 activates without waiting for loadWorkflow().
      if (decision === "approve" && item.workflow_asset_id) {
        setWorkflowAssets((prev) =>
          prev.map((a) =>
            a._id === item.workflow_asset_id ? { ...a, approval_state: "approved" } : a
          )
        );
      }
      await loadWorkflow();
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusyId("");
    }
  }

  async function decideWorkflowAsset(asset, decision) {
    setBusyId(asset._id);
    setNotice("");
    try {
      const result = await api.decideWorkflowAsset(asset._id, { decision });
      setNotice(result.message || `Asset ${decision}d.`);
      // Optimistically update local state so UI responds immediately
      setWorkflowAssets((prev) =>
        prev.map((a) =>
          a._id === asset._id ? { ...a, approval_state: decision === "approve" ? "approved" : "rejected" } : a
        )
      );
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusyId("");
    }
  }

  function draftForAsset(asset) {
    return distributionDrafts[asset._id] || {
      distribution_channel: asset.distribution_channel || asset.platform || asset.metadata?.platform || "",
      distribution_notes: asset.distribution_notes || "",
      published_url: asset.published_url || "",
    };
  }

  function updateDistributionDraft(asset, patch) {
    setDistributionDrafts((current) => ({
      ...current,
      [asset._id]: {
        ...draftForAsset(asset),
        ...current[asset._id],
        ...patch,
      },
    }));
  }

  async function updateWorkflowAssetDistribution(asset, action) {
    setBusyId(asset._id);
    setNotice("");
    try {
      const draft = draftForAsset(asset);
      const payload = {
        action,
        distribution_channel: draft.distribution_channel || "",
        distribution_notes: draft.distribution_notes || "",
        ...(action === "mark_published" || asset.distribution_state === "published"
          ? { published_url: draft.published_url || "" }
          : {}),
      };
      const result = await api.updateWorkflowAssetDistribution(asset._id, payload);
      setNotice(result.message || "Distribution state updated.");
      setWorkflowAssets((prev) => prev.map((item) => (item._id === asset._id ? result.item : item)));
      if (action === "mark_published" || action === "archive") {
        setPublishDraftOpen((current) => ({ ...current, [asset._id]: false }));
        // Refresh workflow_runs so content_build completion state propagates immediately
        loadWorkflow();
      }
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusyId("");
    }
  }

  const latestRun = activeRunDetail?.run || agentRuns[0] || null;
  const draftsNeedingReview = messages.filter((message) => message.review_status === "needs_review");
  const openApprovals = approvalRequests.filter((item) => item.status === "open");
  const currentRunId = activeTask?.linked_run_id || activeRunDetail?.run?._id || agentRuns[0]?._id || null;
  const currentRunApprovals = currentRunId ? openApprovals.filter((item) => item.run_id === currentRunId) : [];
  // Workflow assets for the current run (Phase 5A — additive, above approval requests)
  const currentRunAssets = currentRunId
    ? workflowAssets.filter(
        (a) => a.run_id === currentRunId && a.approval_state !== "rejected" && !["queued", "published", "archived"].includes(a.distribution_state || "not_queued")
      )
    : [];
  const currentRunNotQueuedAssets = currentRunId
    ? workflowAssets.filter((a) => a.run_id === currentRunId && a.approval_state === "approved" && (a.distribution_state || "not_queued") === "not_queued")
    : [];
  const currentRunQueuedAssets = currentRunId
    ? workflowAssets.filter((a) => a.run_id === currentRunId && a.approval_state === "approved" && (a.distribution_state || "not_queued") === "queued")
    : [];
  const currentRunPublishedOrArchivedAssets = currentRunId
    ? workflowAssets.filter((a) => a.run_id === currentRunId && a.approval_state === "approved" && ["published", "archived"].includes(a.distribution_state || "not_queued"))
    : [];
  const activeDistributionWorkCount = currentRunNotQueuedAssets.length + currentRunQueuedAssets.length;
  const activeProfileModule = PROFILE_MAP[activeProfile]?.module || null;
  // "Same profile · other runs" — same module, not the current run
  const otherApprovals = openApprovals.filter((item) =>
    item.run_id !== currentRunId &&
    (activeProfileModule ? item.module === activeProfileModule : false)
  );
  // "All backlog" — cross-module / unrelated historical records
  const backlogApprovals = openApprovals.filter((item) =>
    item.run_id !== currentRunId &&
    (activeProfileModule ? item.module !== activeProfileModule : true)
  );
  const currentRunDrafts = currentRunId ? draftsNeedingReview.filter((m) => m.agent_run_id === currentRunId) : [];
  const otherDrafts = draftsNeedingReview.filter((m) =>
    m.agent_run_id !== currentRunId &&
    (activeProfileModule ? m.module === activeProfileModule : false)
  );
  const backlogDrafts = draftsNeedingReview.filter((m) =>
    m.agent_run_id !== currentRunId &&
    (activeProfileModule ? m.module !== activeProfileModule : true)
  );
  const readyToSend = messages.filter((message) => message.review_status === "approved" && message.send_status === "not_sent");
  const awaitingResponse = messages.filter((message) => message.send_status === "sent" && !message.response_status);
  const interested = messages.filter((message) => ["interested", "requested_info"].includes(message.response_status));
  const booked = messages.filter((message) => message.response_status === "call_booked");
  const openDeals = deals.filter((deal) => OPEN_DEAL_OUTCOMES.includes(deal.outcome || deal.deal_status));
  const closedWon = deals.filter((deal) => (deal.outcome || deal.deal_status) === "closed_won");

  // Phase 6B: stage completion state derived from runtime data only
  const today = new Date().toDateString();
  const completedTodayTasks = tasks.filter(
    (t) => t.status === "completed" && new Date(t.updated_at || t.created_at).toDateString() === today
  );
  // Phase 6C: insight groups
  const todayInsights = discoveryInsights.filter((i) => new Date(i.created_at).toDateString() === today);
  const pendingInsights = discoveryInsights.filter((i) => i.status === "pending_review");
  const approvedInsights = discoveryInsights.filter((i) => i.status === "approved");
  const deferredInsights = discoveryInsights.filter((i) => i.status === "deferred");
  const archivedInsights = discoveryInsights.filter((i) => i.status === "archived");
  // Phase 6D: summary header values
  const highConfidenceInsights = discoveryInsights.filter((i) => (i.confidence_score ?? 0) >= 0.8);
  const topPlatform = (() => {
    const freq = {};
    for (const i of discoveryInsights) {
      for (const p of i.recommendation?.recommended_platforms ?? []) {
        freq[p] = (freq[p] || 0) + 1;
      }
    }
    return Object.entries(freq).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
  })();
  const lastDiscoveryTimestamp = discoveryInsights.length > 0
    ? discoveryInsights.reduce((latest, i) => {
        const t = i.created_at ? new Date(i.created_at).getTime() : 0;
        return t > latest ? t : latest;
      }, 0)
    : null;
  // Approvals from content_discovery runs are discovery artifacts, not content review items.
  // Filter them out of Step 4 and nextStep so discovery doesn't jump to Review & Approve.
  const contentApprovals = openApprovals.filter((a) => a.source_card_id !== "content_discovery");

  // Phase 6H: derive step completion from workflow_run lineage
  const latestDiscoveryRun = useMemo(() =>
    workflowRuns.find((r) => r.run_type === "discovery") || null,
  [workflowRuns]);

  const latestContentBuildRun = useMemo(() =>
    workflowRuns.find((r) => r.run_type === "content_build") || null,
  [workflowRuns]);

  // Content-build approval_requests (linked to a content_build workflow_run)
  const contentBuildApprovals = useMemo(() =>
    contentApprovals.filter((a) => a.source_card_id === "content_build" || a.workflow_run_id),
  [contentApprovals]);

  // Step 2 completed: latest discovery workflow_run exists and is completed
  const discoveryRunCompleted = latestDiscoveryRun?.status === "completed";

  // Step 3 completed: latest content_build workflow_run exists
  const contentBuildRunCompleted = latestContentBuildRun?.status === "needs_review" || latestContentBuildRun?.status === "completed";

  const stageStatuses = {
    1: "ready",
    // Phase 6I: driven exclusively by workflow_runs — no legacy insight/task fallbacks
    2: discoveryRunCompleted ? "completed" : "ready",
    // Phase 6I: content_build completion driven exclusively by workflow_runs
    3: activeTask?.status === "running" ? "running"
       : contentBuildRunCompleted ? "completed"
       : "not_started",
    4: (draftsNeedingReview.length + contentApprovals.length + currentRunAssets.length > 0) ? "needs_review"
       : (latestRun ? "ready" : "not_started"),
    5: (readyToSend.length + activeDistributionWorkCount > 0) ? "ready" : "not_started",
    6: (awaitingResponse.length + interested.length + booked.length > 0) ? "ready" : "not_started",
    7: (openDeals.length + closedWon.length > 0) ? "ready" : "not_started",
  };

  // Phase 6C: map insight_id → insight for lineage display in WorkflowAssetCard
  const discoveryInsightMap = useMemo(() => {
    const map = {};
    for (const i of discoveryInsights) { map[i._id] = i; }
    return map;
  }, [discoveryInsights]);

  // Phase 6H: map workflow_run_id → workflow_run for asset lineage
  const workflowRunsById = useMemo(() => {
    const map = {};
    for (const r of workflowRuns) { map[r._id] = r; }
    return map;
  }, [workflowRuns]);

  // Phase 6I: discoveryDoneToday derives exclusively from workflow_run lineage.
  // discovery_run_summaries are kept for display components only — they do not drive routing.
  const discoveryDoneToday = discoveryRunCompleted;

  // Phase 6G: count stages that differ from the fallback template
  const overrideCount = useMemo(() => {
    if (!clientWorkflowDef) return 0;
    return getWorkflowOverrideCount({
      workflowDefinition: clientWorkflowDef,
      fallbackTemplate: WORKFLOW_TEMPLATES[activeProfile] ?? DEFAULT_TEMPLATE,
    });
  }, [clientWorkflowDef, activeProfile]);

  const nextStep = useMemo(() => {
    if (activeTask?.status === "running") return 3;
    if (readyToSend.length || activeDistributionWorkCount) return 5;
    // After discovery completes today, stay on Step 2 so operator reviews insights
    // (takes priority over pending approvals to avoid wrongly jumping to Step 4 after discovery)
    if (discoveryDoneToday && !contentBuildRunCompleted) return 2;
    // After content_build, route to Step 4 for review — driven by workflow_run lineage
    // Phase 6I: contentBuildApprovals (workflow_run-linked) replaces legacy contentApprovals routing
    // Lifecycle fully complete: content_build done + nothing in distribution queue → prompt new cycle
    if (latestContentBuildRun?.status === "completed" && activeDistributionWorkCount === 0) return 2;
    if (contentBuildRunCompleted || contentBuildApprovals.length) return 4;
    if (awaitingResponse.length || interested.length || booked.length) return 6;
    if (openDeals.length || closedWon.length) return 7;
    // Discovery done but no content build yet — show Step 2 to prompt Content Build run
    if (discoveryDoneToday) return 2;
    return 1;
  }, [activeTask?.status, draftsNeedingReview.length, contentBuildApprovals.length, readyToSend.length, activeDistributionWorkCount, awaitingResponse.length, interested.length, booked.length, openDeals.length, closedWon.length, discoveryDoneToday, contentBuildRunCompleted, latestContentBuildRun?.status]);

  // Sync expandedStep with nextStep unless the user has manually selected a step
  useEffect(() => {
    if (!manualStepOverride.current) {
      setExpandedStep(nextStep);
    }
  }, [nextStep]);

  return (
    <div className="space-y-5">
      <DemoPageBanner onReset={loadWorkflow} />
      <CommandContextCard
        activeProfile={activeProfile}
        activeWorkspace={activeWorkspace}
        demoMode={demoMode}
        nextStep={nextStep}
        reviewNeeded={draftsNeedingReview.length + openApprovals.length}
        readyToSend={readyToSend.length + activeDistributionWorkCount}
        responses={awaitingResponse.length + interested.length + booked.length}
        openDeals={openDeals.length}
        template={resolvedWorkflow}
      />
      <WorkflowSourceIndicator
        fromDB={!!resolvedWorkflow._fromDB}
        dbDisplayName={resolvedWorkflow._dbDisplayName}
        dbSlug={resolvedWorkflow._dbSlug}
      />
      <SourceReadinessCard clientSources={clientSources} />
      <DiscoveryRunCompletionCard runSummaries={discoveryRunSummaries} />
      {(discoveryRunCompleted || discoveryInsights.length > 0) && (
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <DiscoveryExecutionTimeline runSummaries={discoveryRunSummaries} discoveryInsights={discoveryInsights} />
        </div>
      )}
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase text-slate-400">Workflow Mode v1</div>
            <h2 className="mt-1 text-2xl font-semibold text-slate-950">Guided Campaign Workflow</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">Run agents, review generated work, prepare manual outreach, and track responses and deals from one continuous operator page.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge value="simulation only" />
            <StatusBadge value="human reviewed" />
            <button type="button" onClick={loadWorkflow} className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700">
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>
      </section>

      {notice ? <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">{notice}</div> : null}

      <ClientWorkflowHeader
        activeProfile={activeProfile}
        resolvedWorkflow={resolvedWorkflow}
        overrideCount={overrideCount}
      />
      <StepSection step="1" title={resolvedWorkflow.stages[1].label} subtitle={resolvedWorkflow.stages[1].subtitle} stageNote={resolvedWorkflow.stages[1].notes || undefined} required={resolvedWorkflow.stages[1].required} agentKey={resolvedWorkflow.stages[1].agent_key || undefined} runCardType={resolvedWorkflow.stages[1].run_card_type || undefined} active={nextStep === 1} expanded={expandedStep === 1} onExpand={() => selectStep(1)} stageStatus={stageStatuses[1]}>
        {(() => {
          const profile = PROFILE_MAP[activeProfile] ?? PROFILE_MAP["custom"];
          return (
            <div className="space-y-5">
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Active Profile</div>
                  <div className="mt-1.5 font-semibold text-slate-900">{profile.label}</div>
                  {profile.description ? <p className="mt-1 text-xs leading-5 text-slate-500">{profile.description}</p> : null}
                  {profile.module ? <div className="mt-2 inline-flex items-center rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700 capitalize">{profile.module.replace(/_/g, " ")}</div> : null}
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Workspace</div>
                  <div className="mt-1.5 font-semibold text-slate-900">{activeWorkspace || "all"}</div>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Mode</div>
                  <div className={["mt-1.5 inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold", demoMode ? "bg-amber-100 text-amber-800" : "bg-green-100 text-green-800"].join(" ")}>
                    {demoMode ? "Demo" : "Real"}
                  </div>
                </div>
              </div>
              <p className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
                {activeTemplate.step1Guidance}
              </p>
              <div>
                <button
                  type="button"
                  onClick={() => selectStep(2)}
                  className="inline-flex h-10 items-center gap-2 rounded-lg bg-blue-600 px-4 text-sm font-semibold text-white transition hover:bg-blue-700"
                >
                  Continue to Run Agent
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          );
        })()}
      </StepSection>

      <StepSection step="2" title={resolvedWorkflow.stages[2].label} subtitle={resolvedWorkflow.stages[2].subtitle} stageNote={resolvedWorkflow.stages[2].notes || undefined} required={resolvedWorkflow.stages[2].required} agentKey={resolvedWorkflow.stages[2].agent_key || undefined} runCardType={resolvedWorkflow.stages[2].run_card_type || undefined} active={nextStep === 2} count={tasks.length} expanded={expandedStep === 2} onExpand={() => selectStep(2)} stageStatus={stageStatuses[2]}>
        {/* Phase 6H: Workflow Run Summary Cards */}
        {(latestDiscoveryRun || latestContentBuildRun) && (
          <div className="mb-5 grid gap-4 sm:grid-cols-2">
            {latestDiscoveryRun && (
              <div className="space-y-2">
                <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1.5">Last Discovery Run</div>
                <WorkflowRunSummaryCard
                  run={latestDiscoveryRun}
                  onContinue={latestDiscoveryRun.status === "completed" && !latestContentBuildRun
                    ? () => openModal({ id: "content_build", label: "Content Build", agent_name: "content", task_type: "content_build", defaultModule: activeProfile !== "custom" ? activeProfile : "contractor_growth", defaultLimit: 10, defaultPriority: "normal", modalFields: [] })
                    : undefined}
                  continueLabel="Run Content Build"
                />
                {/* Phase 6N: memory context for this run */}
                <MemoryContextPanel run={latestDiscoveryRun} />
              </div>
            )}
            {latestContentBuildRun && (
              <div className="space-y-2">
                <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1.5">Last Content Build Run</div>
                <WorkflowRunSummaryCard
                  run={latestContentBuildRun}
                  onContinue={() => openModal({ id: "content_build", label: "Content Build", agent_name: "content", task_type: "content_build", defaultModule: activeProfile !== "custom" ? activeProfile : "contractor_growth", defaultLimit: 10, defaultPriority: "normal", modalFields: [] })}
                  continueLabel="Run Again"
                />
                {/* Phase 6N: memory context for this run */}
                <MemoryContextPanel run={latestContentBuildRun} />
              </div>
            )}
          </div>
        )}

        {/* Phase 6H: Continue Workflow CTA */}
        <ContinueWorkflowCTA
          discoveryRun={latestDiscoveryRun}
          contentBuildRun={latestContentBuildRun}
          onRunContentBuild={() => openModal({ id: "content_build", label: "Content Build", agent_name: "content", task_type: "content_build", defaultModule: activeProfile !== "custom" ? activeProfile : "contractor_growth", defaultLimit: 10, defaultPriority: "normal", modalFields: [] })}
          onGoToReview={() => selectStep(4)}
          onGoToDistribution={() => selectStep(5)}
          readyToSendCount={readyToSend.length}
        />

        <div className={`grid gap-4 sm:grid-cols-2 xl:grid-cols-3 ${latestDiscoveryRun || latestContentBuildRun ? "mt-5" : ""}`}>
          {activeTemplate.runCards.map((card) => {
            const Icon = ICON_MAP[card.icon] ?? Megaphone;
            return (
              <button
                key={card.id}
                type="button"
                onClick={() => {
                  if (card.isLive) {
                    openModal(card);
                  } else {
                    setNotice(`"${card.label}" is planned for a future release. Use Review & Approve to manually log work in the meantime.`);
                  }
                }}
                className={["group flex flex-col rounded-lg border bg-white p-4 text-left transition", card.isLive ? "border-slate-200 hover:border-blue-200 hover:shadow-sm" : "border-slate-200 opacity-60"].join(" ")}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className={["flex h-9 w-9 shrink-0 items-center justify-center rounded-lg", card.isLive ? "bg-slate-100 group-hover:bg-blue-50 group-hover:text-blue-700" : "bg-slate-100 text-slate-400"].join(" ")}>
                    <Icon className="h-4 w-4" />
                  </div>
                  {!card.isLive ? (
                    <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Coming soon</span>
                  ) : null}
                </div>
                <div className="mt-3">
                  <div className={["text-sm font-semibold", card.isLive ? "text-slate-900 group-hover:text-blue-700" : "text-slate-500"].join(" ")}>{card.label}</div>
                  <p className="mt-1 text-xs leading-5 text-slate-500">{card.description}</p>
                </div>
              </button>
            );
          })}
        </div>

        {/* Phase 6C: Discovery Intelligence Panel */}
        <div className="mt-6 space-y-4">
          <div className="flex items-center gap-2">
            <Lightbulb size={13} className="text-violet-500 shrink-0" />
            <h3 className="text-sm font-semibold text-slate-950">Discovery Intelligence</h3>
            <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-semibold text-violet-700">
              {discoveryInsights.length}
            </span>
            {pendingInsights.length > 0 && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700">
                {pendingInsights.length} pending review
              </span>
            )}
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
              Live Tavily search
            </span>
          </div>
          <p className="text-xs text-slate-500">
            Real web search results (via Tavily), scored and ranked — requires TAVILY_ENABLED +
            TAVILY_API_KEY, otherwise Content Discovery Run completes with no insights. Each insight
            links back to its real source. A separate pipeline stages curated candidates in Campaign
            Studio → Source Content for clipping — this panel is for trend/opportunity intelligence,
            not raw content candidates.
          </p>

          {/* Phase 6D: Discovery summary header */}
          {discoveryInsights.length > 0 && (
            <div className="rounded-lg border border-violet-200 bg-violet-50 px-4 py-2.5">
              <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs">
                <div>
                  <span className="font-semibold text-violet-800">{todayInsights.length}</span>
                  <span className="ml-1 text-violet-600">insights today</span>
                </div>
                <div>
                  <span className="font-semibold text-violet-800">{highConfidenceInsights.length}</span>
                  <span className="ml-1 text-violet-600">high confidence</span>
                </div>
                {topPlatform && (
                  <div>
                    <span className="text-violet-600">Top platform: </span>
                    <span className="font-semibold text-violet-800">{topPlatform}</span>
                  </div>
                )}
                {lastDiscoveryTimestamp && (
                  <div className="text-violet-500">
                    Last run: {new Date(lastDiscoveryTimestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </div>
                )}
              </div>
            </div>
          )}

          {discoveryInsights.length === 0 ? (
            <EmptyState>
              No discovery insights yet. Run a discovery agent to generate intelligence from signal sources.
            </EmptyState>
          ) : (
            <div className="space-y-6">
              {[
                { label: "Pending Review", items: pendingInsights },
                { label: "Approved", items: approvedInsights },
                { label: "Deferred / Archived", items: [...deferredInsights, ...archivedInsights] },
              ].filter((g) => g.items.length > 0).map((group) => (
                <div key={group.label}>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">{group.label}</h4>
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {group.items.map((insight) => (
                      <InsightCard
                        key={insight._id}
                        insight={insight}
                        evidenceOpen={insightEvidenceOpen[insight._id]}
                        onToggleEvidence={() => setInsightEvidenceOpen((prev) => ({ ...prev, [insight._id]: !prev[insight._id] }))}
                        onViewFull={() => setActiveInsightModal(insight)}
                        onStatusChange={(status) => {
                          api.updateDiscoveryInsightStatus(insight._id, status)
                            .then((data) => {
                              if (data?.item) setDiscoveryInsights((prev) => prev.map((i) => i._id === data.item._id ? data.item : i));
                            })
                            .catch(() => {});
                        }}
                        onGenerateAssets={() => {
                          setGeneratingAssetForInsight(insight._id);
                          api.generateAssetsFromInsight(insight._id)
                            .then((data) => {
                              if (data?.items) {
                                setWorkflowAssets((prev) => [...prev, ...data.items]);
                              }
                            })
                            .catch(() => {})
                            .finally(() => setGeneratingAssetForInsight(""));
                        }}
                        generatingAssets={generatingAssetForInsight === insight._id}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </StepSection>

      <div ref={livePanelRef}>
        <StepSection step="3" title={resolvedWorkflow.stages[3].label} subtitle={resolvedWorkflow.stages[3].subtitle} stageNote={resolvedWorkflow.stages[3].notes || undefined} required={resolvedWorkflow.stages[3].required} agentKey={resolvedWorkflow.stages[3].agent_key || undefined} runCardType={resolvedWorkflow.stages[3].run_card_type || undefined} active={nextStep === 3} count={latestRun ? 1 : 0} expanded={expandedStep === 3} onExpand={() => selectStep(3)} stageStatus={stageStatuses[3]}>
          {/* Discovery run completion card — shown when latest run was a content_discovery */}
          {latestRun?.agent_name === "content_discovery" && discoveryRunCompleted ? (
            <div className="space-y-4">
              <DiscoveryRunCompletionCard runSummaries={discoveryRunSummaries} />
              <DiscoveryExecutionTimeline runSummaries={discoveryRunSummaries} discoveryInsights={discoveryInsights} />
            </div>
          ) : latestRun || activeTask ? (
            <LiveAgentRunPanel task={activeTask} runDetail={activeRunDetail} loading={panelLoading} onRefresh={() => refreshRunDetail(activeTask?.linked_run_id || latestRun?.run_id)} />
          ) : (
            <EmptyState>No agent run yet. Use Step 2 to queue a run — outputs and timeline will appear here as the agent works.</EmptyState>
          )}

          {/* Discovery Timeline — always shown when insights exist (original Phase 6D behaviour) */}
          {discoveryInsights.length > 0 && (
            <div className="mt-5 border-t border-slate-100 pt-4">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Discovery Timeline</h3>
              <ol className="space-y-2">
                {[...discoveryInsights]
                  .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
                  .slice(0, 6)
                  .map((insight) => (
                    <li key={insight._id} className="flex items-start gap-2 text-xs">
                      <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-violet-400" />
                      <div className="min-w-0">
                        <span className="font-medium text-slate-700">{insight.title}</span>
                        <span className="ml-2 text-slate-400">
                          {insight.created_at ? new Date(insight.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
                        </span>
                        {insight.status === "approved" && (
                          <span className="ml-2 rounded-full bg-green-100 px-1.5 text-green-700 font-semibold">approved</span>
                        )}
                        {insight.source_run_id && (
                          <span className="ml-2 font-mono text-slate-400">…{insight.source_run_id.slice(-8)}</span>
                        )}
                      </div>
                    </li>
                  ))}
              </ol>
            </div>
          )}
        </StepSection>
      </div>

      <StepSection step="4" title={resolvedWorkflow.stages[4].label} subtitle={resolvedWorkflow.stages[4].subtitle} stageNote={resolvedWorkflow.stages[4].notes || undefined} required={resolvedWorkflow.stages[4].required} agentKey={resolvedWorkflow.stages[4].agent_key || undefined} runCardType={resolvedWorkflow.stages[4].run_card_type || undefined} active={nextStep === 4} count={draftsNeedingReview.length + contentApprovals.length} expanded={expandedStep === 4} onExpand={() => selectStep(4)} stageStatus={stageStatuses[4]}>
        <div className="space-y-6">

          {/* Run context banner */}
          <div className={["rounded-lg border px-4 py-2.5 text-xs", currentRunId ? "border-blue-200 bg-blue-50 text-blue-800" : "border-slate-200 bg-slate-50 text-slate-500"].join(" ")}>
            {currentRunId ? (
              <span>
                Showing outputs from:{" "}
                <strong>{activeTask?.agent_name || "agent"} / {activeTask?.module || "module"}</strong>
                {activeTask?.input_config?.campaign_notes ? <> · <span className="font-mono">{activeTask.input_config.campaign_notes}</span></> : null}
                {" "}· run <span className="font-mono">…{currentRunId.slice(-8)}</span>
              </span>
            ) : (
              "Queue a run from Step 2 to see its outputs here. All pending items appear in the global queue below."
            )}
          </div>

          {/* ── Workflow Assets (Phase 5A) ── renders ABOVE approval requests ── */}
          {currentRunAssets.length > 0 && (
            <div>
              <div className="mb-3 flex items-center gap-3">
                <h3 className="text-sm font-semibold text-slate-950">Workflow Assets</h3>
                <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-700">
                  {currentRunAssets.length} asset{currentRunAssets.length !== 1 ? "s" : ""}
                </span>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Phase 5A</span>
              </div>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {currentRunAssets.map((asset) => (
                  <WorkflowAssetCard
                    key={asset._id}
                    asset={asset}
                    onDecide={decideWorkflowAsset}
                    busyId={busyId}
                    discoveryInsightMap={discoveryInsightMap}
                    onViewInsight={(insight) => setActiveInsightModal(insight)}
                    onOpenPreview={(a) => setActiveAssetPreview(a)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* From this run */}
          <div>
            <h3 className="mb-3 text-sm font-semibold text-slate-950">From this run</h3>
            {currentRunId && (currentRunDrafts.length + currentRunApprovals.length > 0) ? (
              <div className="grid gap-4 xl:grid-cols-2">
                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Drafts needing review</h4>
                  <div className="space-y-3">
                    {currentRunDrafts.map((message) => (
                      <article key={`crdr-${message._id}`} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="font-semibold text-slate-950">{recordTitle(message)}</div>
                            <div className="mt-1 text-sm text-slate-600">{message.recipient_name || "-"} · {message.company || message.module || "-"}</div>
                          </div>
                          <StatusBadge value={message.review_status} />
                        </div>
                        <div className="mt-3 max-h-32 overflow-y-auto whitespace-pre-wrap rounded border border-slate-100 bg-white p-2 text-sm leading-6 text-slate-700">{message.message_body || "No body recorded."}</div>
                        <div className="mt-4 flex flex-wrap gap-2">
                          <button type="button" disabled={busyId === message._id} onClick={() => reviewMessage(message, "approve")} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-green-600 px-3 text-xs font-medium text-white transition hover:bg-green-700 disabled:bg-slate-300"><Check className="h-3.5 w-3.5" />Approve</button>
                          <button type="button" disabled={busyId === message._id} onClick={() => reviewMessage(message, "revise")} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-amber-500 px-3 text-xs font-medium text-white transition hover:bg-amber-600 disabled:bg-slate-300"><RotateCcw className="h-3.5 w-3.5" />Revise</button>
                          <button type="button" disabled={busyId === message._id} onClick={() => reviewMessage(message, "reject")} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-slate-800 px-3 text-xs font-medium text-white transition hover:bg-red-700 disabled:bg-slate-300"><X className="h-3.5 w-3.5" />Reject</button>
                        </div>
                      </article>
                    ))}
                    {!currentRunDrafts.length ? <EmptyState>No drafts from this run.</EmptyState> : null}
                  </div>
                </div>
                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Approval requests</h4>
                  <div className="space-y-3">
                    {currentRunApprovals.map((item) => (
                      <article key={`crar-${item._id}`} className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap gap-2"><StatusBadge value={item.request_type} /><StatusBadge value={item.status} /></div>
                            <div className="mt-3 font-semibold text-amber-950">{recordTitle(item)}</div>
                            <p className="mt-2 text-sm leading-6 text-amber-900">{item.reason_for_review || item.summary || "Review requested."}</p>
                          </div>
                          <div className="text-xs text-amber-800">{formatDate(item.created_at)}</div>
                        </div>
                        <textarea value={notes[item._id] || ""} onChange={(event) => setNotes((current) => ({ ...current, [item._id]: event.target.value }))} placeholder="Operator note" className="mt-4 min-h-16 w-full rounded-lg border border-amber-200 bg-white p-3 text-sm text-slate-700 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100" />
                        <div className="mt-3 flex flex-wrap gap-2">
                          {APPROVAL_DECISIONS.map((decision) => {
                            const Icon = decision.icon;
                            return <button key={decision.value} type="button" disabled={busyId === item._id} onClick={() => decideApproval(item, decision.value)} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-amber-200 bg-white px-3 text-xs font-medium text-amber-900 transition hover:border-amber-300 disabled:opacity-60"><Icon className="h-3.5 w-3.5" />{decision.label}</button>;
                          })}
                        </div>
                      </article>
                    ))}
                    {!currentRunApprovals.length ? <EmptyState>No approval requests from this run.</EmptyState> : null}
                  </div>
                </div>
              </div>
            ) : (
              <EmptyState>{currentRunId ? "No review items from the selected run yet." : "Queue a run from Step 2 to see its outputs here first."}</EmptyState>
            )}
          </div>

          {/* Same profile · other runs — collapsible */}
          <div>
            <button
              type="button"
              onClick={() => setOtherReviewOpen((v) => !v)}
              className="flex w-full items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white px-4 py-3 text-left text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
            >
              <span>Same profile · other runs <span className="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">{otherDrafts.length + otherApprovals.length}</span></span>
              <span className="text-slate-400 text-xs">{otherReviewOpen ? "▾" : "▸"}</span>
            </button>
            {otherReviewOpen ? (
              <div className="mt-3 grid gap-4 xl:grid-cols-2">
                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Drafts needing review</h4>
                  <div className="space-y-3">
                    {otherDrafts.map((message) => (
                      <article key={`otdr-${message._id}`} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="font-semibold text-slate-950">{recordTitle(message)}</div>
                            <div className="mt-1 text-sm text-slate-600">{message.recipient_name || "-"} · {message.company || message.module || "-"}</div>
                          </div>
                          <StatusBadge value={message.review_status} />
                        </div>
                        <div className="mt-3 max-h-32 overflow-y-auto whitespace-pre-wrap rounded border border-slate-100 bg-white p-2 text-sm leading-6 text-slate-700">{message.message_body || "No body recorded."}</div>
                        <div className="mt-4 flex flex-wrap gap-2">
                          <button type="button" disabled={busyId === message._id} onClick={() => reviewMessage(message, "approve")} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-green-600 px-3 text-xs font-medium text-white transition hover:bg-green-700 disabled:bg-slate-300"><Check className="h-3.5 w-3.5" />Approve</button>
                          <button type="button" disabled={busyId === message._id} onClick={() => reviewMessage(message, "revise")} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-amber-500 px-3 text-xs font-medium text-white transition hover:bg-amber-600 disabled:bg-slate-300"><RotateCcw className="h-3.5 w-3.5" />Revise</button>
                          <button type="button" disabled={busyId === message._id} onClick={() => reviewMessage(message, "reject")} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-slate-800 px-3 text-xs font-medium text-white transition hover:bg-red-700 disabled:bg-slate-300"><X className="h-3.5 w-3.5" />Reject</button>
                        </div>
                      </article>
                    ))}
                    {!otherDrafts.length ? <EmptyState>No same-profile drafts from other runs.</EmptyState> : null}
                  </div>
                </div>
                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Approval requests</h4>
                  <div className="space-y-3">
                    {otherApprovals.map((item) => (
                      <article key={`otar-${item._id}`} className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap gap-2"><StatusBadge value={item.request_type} /><StatusBadge value={item.status} /></div>
                            <div className="mt-3 font-semibold text-amber-950">{recordTitle(item)}</div>
                            <p className="mt-2 text-sm leading-6 text-amber-900">{item.reason_for_review || item.summary || "Review requested."}</p>
                          </div>
                          <div className="text-xs text-amber-800">{formatDate(item.created_at)}</div>
                        </div>
                        <textarea value={notes[item._id] || ""} onChange={(event) => setNotes((current) => ({ ...current, [item._id]: event.target.value }))} placeholder="Operator note" className="mt-4 min-h-16 w-full rounded-lg border border-amber-200 bg-white p-3 text-sm text-slate-700 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100" />
                        <div className="mt-3 flex flex-wrap gap-2">
                          {APPROVAL_DECISIONS.map((decision) => {
                            const Icon = decision.icon;
                            return <button key={decision.value} type="button" disabled={busyId === item._id} onClick={() => decideApproval(item, decision.value)} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-amber-200 bg-white px-3 text-xs font-medium text-amber-900 transition hover:border-amber-300 disabled:opacity-60"><Icon className="h-3.5 w-3.5" />{decision.label}</button>;
                          })}
                        </div>
                      </article>
                    ))}
                    {!otherApprovals.length ? <EmptyState>No same-profile approval requests from other runs.</EmptyState> : null}
                  </div>
                </div>
              </div>
            ) : null}
          </div>

          {/* All backlog — cross-module / historical, collapsible */}
          <div>
            <button
              type="button"
              onClick={() => setBacklogOpen((v) => !v)}
              className="flex w-full items-center justify-between gap-4 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-left text-sm font-medium text-slate-500 transition hover:border-slate-300 hover:bg-slate-100"
            >
              <span>All backlog <span className="ml-1 rounded-full bg-slate-200 px-2 py-0.5 text-xs font-semibold text-slate-600">{backlogDrafts.length + backlogApprovals.length}</span><span className="ml-2 text-xs font-normal text-slate-400">cross-profile &amp; historical</span></span>
              <span className="text-slate-400 text-xs">{backlogOpen ? "▾" : "▸"}</span>
            </button>
            {backlogOpen ? (
              <div className="mt-3 grid gap-4 xl:grid-cols-2">
                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Drafts</h4>
                  <div className="space-y-3">
                    {backlogDrafts.map((message) => (
                      <article key={`bldr-${message._id}`} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="font-semibold text-slate-950">{recordTitle(message)}</div>
                            <div className="mt-1 text-sm text-slate-600">{message.recipient_name || "-"} · {message.company || message.module || "-"}</div>
                          </div>
                          <StatusBadge value={message.review_status} />
                        </div>
                        <div className="mt-3 max-h-32 overflow-y-auto whitespace-pre-wrap rounded border border-slate-100 bg-white p-2 text-sm leading-6 text-slate-700">{message.message_body || "No body recorded."}</div>
                        <div className="mt-4 flex flex-wrap gap-2">
                          <button type="button" disabled={busyId === message._id} onClick={() => reviewMessage(message, "approve")} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-green-600 px-3 text-xs font-medium text-white transition hover:bg-green-700 disabled:bg-slate-300"><Check className="h-3.5 w-3.5" />Approve</button>
                          <button type="button" disabled={busyId === message._id} onClick={() => reviewMessage(message, "revise")} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-amber-500 px-3 text-xs font-medium text-white transition hover:bg-amber-600 disabled:bg-slate-300"><RotateCcw className="h-3.5 w-3.5" />Revise</button>
                          <button type="button" disabled={busyId === message._id} onClick={() => reviewMessage(message, "reject")} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-slate-800 px-3 text-xs font-medium text-white transition hover:bg-red-700 disabled:bg-slate-300"><X className="h-3.5 w-3.5" />Reject</button>
                        </div>
                      </article>
                    ))}
                    {!backlogDrafts.length ? <EmptyState>No backlog drafts.</EmptyState> : null}
                  </div>
                </div>
                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Approval requests</h4>
                  <div className="space-y-3">
                    {backlogApprovals.map((item) => (
                      <article key={`blar-${item._id}`} className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap gap-2"><StatusBadge value={item.request_type} /><StatusBadge value={item.status} />{item.module ? <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">{item.module}</span> : null}</div>
                            <div className="mt-3 font-semibold text-amber-950">{recordTitle(item)}</div>
                            <p className="mt-2 text-sm leading-6 text-amber-900">{item.reason_for_review || item.summary || "Review requested."}</p>
                          </div>
                          <div className="text-xs text-amber-800">{formatDate(item.created_at)}</div>
                        </div>
                        <textarea value={notes[item._id] || ""} onChange={(event) => setNotes((current) => ({ ...current, [item._id]: event.target.value }))} placeholder="Operator note" className="mt-4 min-h-16 w-full rounded-lg border border-amber-200 bg-white p-3 text-sm text-slate-700 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100" />
                        <div className="mt-3 flex flex-wrap gap-2">
                          {APPROVAL_DECISIONS.map((decision) => {
                            const Icon = decision.icon;
                            return <button key={decision.value} type="button" disabled={busyId === item._id} onClick={() => decideApproval(item, decision.value)} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-amber-200 bg-white px-3 text-xs font-medium text-amber-900 transition hover:border-amber-300 disabled:opacity-60"><Icon className="h-3.5 w-3.5" />{decision.label}</button>;
                          })}
                        </div>
                      </article>
                    ))}
                    {!backlogApprovals.length ? <EmptyState>No backlog approval requests.</EmptyState> : null}
                  </div>
                </div>
              </div>
            ) : null}
          </div>

        </div>
      </StepSection>

      <StepSection step="5" title={resolvedWorkflow.stages[5].label} subtitle={resolvedWorkflow.stages[5].subtitle} stageNote={resolvedWorkflow.stages[5].notes || undefined} required={resolvedWorkflow.stages[5].required} agentKey={resolvedWorkflow.stages[5].agent_key || undefined} runCardType={resolvedWorkflow.stages[5].run_card_type || undefined} active={nextStep === 5} count={readyToSend.length + activeDistributionWorkCount} expanded={expandedStep === 5} onExpand={() => selectStep(5)} stageStatus={stageStatuses[5]}>
        <div className="space-y-6">
          {/* Phase 6F: Distribution Clarity Panel */}
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-4 space-y-3">
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">Platform Distribution &amp; Scheduling</h4>
              <p className="text-xs leading-5 text-slate-500">
                Approved content awaiting publishing assignment. This step determines where approved content will be distributed and scheduled — platform selection, channel assignment, and publish queue management. It is not a content review step.
              </p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-600 mb-2">Select target distribution platforms:</p>
              <div className="flex flex-wrap gap-2">
                {["LinkedIn", "X", "Instagram", "Facebook", "YouTube", "Email", "Podcast"].map((platform) => {
                  const selected = distributionPlatforms.includes(platform);
                  return (
                    <button
                      key={platform}
                      type="button"
                      onClick={() =>
                        setDistributionPlatforms((prev) =>
                          selected ? prev.filter((p) => p !== platform) : [...prev, platform]
                        )
                      }
                      className={[
                        "rounded-full border px-3 py-1 text-xs font-medium transition",
                        selected
                          ? "border-blue-400 bg-blue-100 text-blue-700"
                          : "border-slate-200 bg-white text-slate-600 hover:border-blue-300 hover:text-blue-600",
                      ].join(" ")}
                    >
                      {platform}
                    </button>
                  );
                })}
              </div>
              {distributionPlatforms.length > 0 && (
                <p className="mt-2 text-[10px] text-slate-400">
                  Selected: {distributionPlatforms.join(", ")}
                </p>
              )}
            </div>
          </div>
          <div>
            <div className="mb-3 flex items-center gap-3">
              <h3 className="text-sm font-semibold text-slate-950">Approved / Not Queued</h3>
              <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-700">
                {currentRunNotQueuedAssets.length} asset{currentRunNotQueuedAssets.length !== 1 ? "s" : ""}
              </span>
            </div>
            {currentRunNotQueuedAssets.length ? (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {currentRunNotQueuedAssets.map((asset) => (
                  <WorkflowAssetCard
                    key={`not-queued-${asset._id}`}
                    asset={asset}
                    busyId={busyId}
                    mode="distribution"
                    distributionDraft={draftForAsset(asset)}
                    onDistributionDraftChange={updateDistributionDraft}
                    onDistributionAction={updateWorkflowAssetDistribution}
                    showPublishFields={publishDraftOpen[asset._id] === true}
                    onTogglePublishFields={(item) => setPublishDraftOpen((current) => ({ ...current, [item._id]: !current[item._id] }))}
                  />
                ))}
              </div>
            ) : (
              <EmptyState>No approved workflow assets from this run are waiting for distribution.</EmptyState>
            )}
          </div>

          <div>
            <div className="mb-3 flex items-center gap-3">
              <h3 className="text-sm font-semibold text-slate-950">Queued for Distribution</h3>
              <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-700">
                {currentRunQueuedAssets.length} asset{currentRunQueuedAssets.length !== 1 ? "s" : ""}
              </span>
            </div>
            {currentRunQueuedAssets.length ? (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {currentRunQueuedAssets.map((asset) => (
                  <WorkflowAssetCard
                    key={`queued-${asset._id}`}
                    asset={asset}
                    busyId={busyId}
                    mode="distribution"
                    distributionDraft={draftForAsset(asset)}
                    onDistributionDraftChange={updateDistributionDraft}
                    onDistributionAction={updateWorkflowAssetDistribution}
                    showPublishFields={publishDraftOpen[asset._id] === true}
                    onTogglePublishFields={(item) => setPublishDraftOpen((current) => ({ ...current, [item._id]: !current[item._id] }))}
                  />
                ))}
              </div>
            ) : (
              <EmptyState>No assets are currently queued for manual distribution.</EmptyState>
            )}
          </div>

          <div>
            <div className="mb-3 flex items-center gap-3">
              <h3 className="text-sm font-semibold text-slate-950">Published / Archived</h3>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
                {currentRunPublishedOrArchivedAssets.length} asset{currentRunPublishedOrArchivedAssets.length !== 1 ? "s" : ""}
              </span>
            </div>
            {currentRunPublishedOrArchivedAssets.length ? (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {currentRunPublishedOrArchivedAssets.map((asset) => (
                  <WorkflowAssetCard
                    key={`history-${asset._id}`}
                    asset={asset}
                    busyId={busyId}
                    mode="distribution"
                    distributionDraft={draftForAsset(asset)}
                    onDistributionDraftChange={updateDistributionDraft}
                    onDistributionAction={updateWorkflowAssetDistribution}
                    showPublishFields={asset.distribution_state === "published"}
                  />
                ))}
              </div>
            ) : (
              <EmptyState>No published or archived workflow assets from this run yet.</EmptyState>
            )}
          </div>

          <div>
            <div className="mb-3 flex items-center gap-3">
              <h3 className="text-sm font-semibold text-slate-950">Ready to Send Message Drafts</h3>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
                {readyToSend.length} draft{readyToSend.length !== 1 ? "s" : ""}
              </span>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {readyToSend.map((message) => (
                <article key={`send-${message._id}`} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <div className="font-semibold text-slate-950">{recordTitle(message)}</div>
                  <div className="mt-1 text-sm text-slate-600">{message.recipient_name || "-"} · {message.company || message.module || "-"}</div>
                  <div className="mt-3 flex flex-wrap gap-2"><StatusBadge value={message.review_status} /><StatusBadge value={message.send_status} /></div>
                  <button type="button" onClick={() => setNotice("Send manually from your external inbox. SignalForge did not send anything.")} className="mt-4 inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700">
                    <Send className="h-4 w-4" />
                    Send manually
                  </button>
                </article>
              ))}
              {!readyToSend.length ? <EmptyState>No approved drafts are waiting for manual send.</EmptyState> : null}
            </div>
          </div>
        </div>
      </StepSection>

      <StepSection step="6" title={resolvedWorkflow.stages[6].label} subtitle={resolvedWorkflow.stages[6].subtitle} stageNote={resolvedWorkflow.stages[6].notes || undefined} required={resolvedWorkflow.stages[6].required} agentKey={resolvedWorkflow.stages[6].agent_key || undefined} runCardType={resolvedWorkflow.stages[6].run_card_type || undefined} active={nextStep === 6} count={awaitingResponse.length + interested.length + booked.length} expanded={expandedStep === 6} onExpand={() => selectStep(6)} stageStatus={stageStatuses[6]}>
        <div className="grid gap-4 lg:grid-cols-3">
          {[{ label: "Awaiting response", rows: awaitingResponse, icon: Clock3 }, { label: "Interested", rows: interested, icon: MessageCircle }, { label: "Call booked", rows: booked, icon: Check }].map((group) => {
            const Icon = group.icon;
            return (
              <div key={group.label} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="mb-3 flex items-center justify-between gap-2"><div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-950"><Icon className="h-4 w-4 text-blue-600" />{group.label}</div><StatusBadge value={`${group.rows.length} items`} /></div>
                <div className="space-y-2">
                  {group.rows.slice(0, 6).map((message) => <div key={`resp-${group.label}-${message._id}`} className="rounded-lg border border-slate-200 bg-white p-3 text-sm"><div className="font-medium text-slate-950">{recordTitle(message)}</div><div className="mt-1 text-slate-500">{message.recipient_name || message.company || "-"}</div></div>)}
                  {!group.rows.length ? <div className="text-sm text-slate-500">Nothing in this state.</div> : null}
                </div>
              </div>
            );
          })}
        </div>
      </StepSection>

      <StepSection step="7" title={resolvedWorkflow.stages[7].label} subtitle={resolvedWorkflow.stages[7].subtitle} stageNote={resolvedWorkflow.stages[7].notes || undefined} required={resolvedWorkflow.stages[7].required} agentKey={resolvedWorkflow.stages[7].agent_key || undefined} runCardType={resolvedWorkflow.stages[7].run_card_type || undefined} active={nextStep === 7} count={openDeals.length + closedWon.length} expanded={expandedStep === 7} onExpand={() => selectStep(7)} stageStatus={stageStatuses[7]}>
        <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs text-emerald-800">
          <span>
            <strong>{formatMoney(commerceRevenueCents / 100)}</strong> in Commerce product revenue this workspace — tracked separately from the CRM deals below.
          </span>
          <a href="#commerce" className="whitespace-nowrap font-semibold text-emerald-700 hover:underline">
            View Commerce →
          </a>
        </div>
        <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 px-4 py-2.5 text-xs text-slate-600">
          This view is read-only. Deal outcomes are logged by running <code className="rounded bg-slate-200 px-1 py-0.5 font-mono text-xs">scripts/log_deal_outcome.py</code> outside the app, not from a button here — see the <a href="#deals" className="font-semibold text-slate-700 hover:underline">Deals</a> tab for the same data.
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          {[{ label: "Open deals", rows: openDeals }, { label: "Closed won", rows: closedWon }].map((group) => (
            <div key={group.label} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="mb-3 flex items-center justify-between gap-3"><h3 className="text-sm font-semibold text-slate-950">{group.label}</h3><StatusBadge value={formatMoney(group.rows.reduce((sum, deal) => sum + Number(deal.deal_value || 0), 0))} /></div>
              <div className="grid gap-3 md:grid-cols-2">
                {group.rows.slice(0, 8).map((deal) => (
                  <article key={deal._id} className="rounded-lg border border-slate-200 bg-white p-3">
                    <div className="font-semibold text-slate-950">{deal.company || deal.person || "Deal"}</div>
                    <div className="mt-1 text-sm text-slate-500">{deal.person || deal.module || "-"}</div>
                    <div className="mt-3 flex items-center justify-between gap-2"><span className="text-sm font-semibold text-slate-900">{formatMoney(deal.deal_value)}</span><StatusBadge value={deal.outcome || deal.deal_status || "unknown"} /></div>
                  </article>
                ))}
              </div>
              {!group.rows.length ? <EmptyState>No {group.label.toLowerCase()}.</EmptyState> : null}
            </div>
          ))}
        </div>
      </StepSection>

      {/* Phase 6C: Discovery Insight detail modal */}
      {activeInsightModal ? (
        <DiscoveryInsightModal insight={activeInsightModal} onClose={() => setActiveInsightModal(null)} />
      ) : null}

      {/* Phase 6F: Workflow Asset preview modal */}
      {activeAssetPreview ? (
        <WorkflowAssetPreviewModal
          asset={activeAssetPreview}
          discoveryInsightMap={discoveryInsightMap}
          workflowRunsById={workflowRunsById}
          onClose={() => setActiveAssetPreview(null)}
        />
      ) : null}

      {activeAction ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <form onSubmit={createTask} className="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-xs font-semibold uppercase text-slate-400">Create Task</div>
                <h3 className="mt-1 text-lg font-semibold text-slate-950">{activeAction.label}</h3>
                <p className="mt-0.5 text-xs text-slate-400">Underlying task: {activeAction.agent_name} / {activeAction.task_type}</p>
              </div>
              <button type="button" onClick={() => setActiveAction(null)} className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition hover:text-slate-900"><X className="h-4 w-4" /></button>
            </div>
            {activeAction.modalHint ? (
              <p className="mt-4 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2.5 text-xs leading-5 text-blue-800">{activeAction.modalHint}</p>
            ) : null}
            <div className="mt-5 grid gap-4">
              {activeAction.modalFields?.length ? (
                <>
                  {activeAction.modalFields.map((field) => (
                    <label key={field.id} className="grid gap-1 text-sm font-medium text-slate-700">
                      {field.label}
                      {field.type === "select" ? (
                        <select value={operatorConfig[field.id] ?? field.defaultValue ?? ""} onChange={(e) => setOperatorConfig((c) => ({ ...c, [field.id]: e.target.value }))} className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700">
                          {field.options?.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                        </select>
                      ) : field.type === "number" ? (
                        <input type="number" min={field.min ?? 1} max={field.max ?? 50} value={operatorConfig[field.id] ?? field.defaultValue ?? ""} onChange={(e) => setOperatorConfig((c) => ({ ...c, [field.id]: e.target.value }))} className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-700" />
                      ) : (
                        <input type="text" placeholder={field.placeholder ?? ""} value={operatorConfig[field.id] ?? field.defaultValue ?? ""} onChange={(e) => setOperatorConfig((c) => ({ ...c, [field.id]: e.target.value }))} className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-700" />
                      )}
                    </label>
                  ))}
                  <div>
                    <button type="button" onClick={() => setAdvancedOpen((v) => !v)} className="text-xs font-medium text-slate-400 hover:text-slate-600">{advancedOpen ? "\u25be" : "\u25b8"} Advanced settings</button>
                    {advancedOpen ? (
                      <div className="mt-3 grid gap-3 rounded-lg border border-slate-100 bg-slate-50 p-3">
                        <p className="text-[10px] leading-4 text-slate-400">These settings are pre-configured for this run. Edit only if you know what you want to change.</p>
                        <label className="grid gap-1 text-xs font-medium text-slate-500">Module<select value={config.module} onChange={(event) => setConfig((current) => ({ ...current, module: event.target.value }))} className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs text-slate-700">{MODULES.map((module) => <option key={module} value={module}>{module}</option>)}</select></label>
                        <label className="grid gap-1 text-xs font-medium text-slate-500">Segment<input value={config.segment} onChange={(event) => setConfig((current) => ({ ...current, segment: event.target.value }))} className="h-9 rounded-lg border border-slate-200 px-3 text-xs text-slate-700" /></label>
                        <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-500"><input type="checkbox" checked={config.high_priority} onChange={(event) => setConfig((current) => ({ ...current, high_priority: event.target.checked }))} className="h-4 w-4 rounded border-slate-300" />High priority filter</label>
                      </div>
                    ) : null}
                  </div>
                </>
              ) : (
                <>
                  <label className="grid gap-1 text-sm font-medium text-slate-700">Module<select value={config.module} onChange={(event) => setConfig((current) => ({ ...current, module: event.target.value }))} className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700">{MODULES.map((module) => <option key={module} value={module}>{module}</option>)}</select></label>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="grid gap-1 text-sm font-medium text-slate-700">Limit<input type="number" min="1" max="50" value={config.limit} onChange={(event) => setConfig((current) => ({ ...current, limit: event.target.value }))} className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-700" /></label>
                    <label className="grid gap-1 text-sm font-medium text-slate-700">Priority<select value={config.priority} onChange={(event) => setConfig((current) => ({ ...current, priority: event.target.value }))} className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700">{PRIORITIES.map((priority) => <option key={priority} value={priority}>{priority}</option>)}</select></label>
                  </div>
                  <label className="grid gap-1 text-sm font-medium text-slate-700">Segment<input value={config.segment} onChange={(event) => setConfig((current) => ({ ...current, segment: event.target.value }))} className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-700" /></label>
                  <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700"><input type="checkbox" checked={config.high_priority} onChange={(event) => setConfig((current) => ({ ...current, high_priority: event.target.checked }))} className="h-4 w-4 rounded border-slate-300" />High priority filter</label>
                </>
              )}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setActiveAction(null)} className="inline-flex h-10 items-center rounded-lg border border-slate-200 px-4 text-sm font-medium text-slate-700 transition hover:text-slate-950">Cancel</button>
              <button type="submit" className="inline-flex h-10 items-center gap-2 rounded-lg bg-blue-600 px-4 text-sm font-semibold text-white transition hover:bg-blue-700"><Play className="h-4 w-4" />Queue Task</button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}