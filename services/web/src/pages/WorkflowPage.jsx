import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
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
} from "lucide-react";
import { api } from "../api.js";
import { PROFILE_MAP } from "../navigation/systemProfiles.js";
import { WORKFLOW_TEMPLATES, DEFAULT_TEMPLATE } from "../navigation/workflowTemplates.js";
import DemoPageBanner from "../components/DemoPageBanner.jsx";
import LiveAgentRunPanel from "../components/LiveAgentRunPanel.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import WorkflowAssetCard from "../components/WorkflowAssetCard.jsx";

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
 * New props:
 *   expanded    boolean — whether this step is currently open
 *   onExpand    () => void — called when the header is clicked while collapsed
 *
 * Existing props (all preserved):
 *   step, title, subtitle, active, count, children
 */
function StepSection({ step, title, subtitle, active, count, children, expanded, onExpand, stageStatus }) {
  if (expanded) {
    // Full panel — same markup as before
    return (
      <section className={["rounded-lg border bg-white p-5 shadow-sm transition", active ? "border-blue-300 ring-2 ring-blue-100" : "border-slate-200"].join(" ")}>
        <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase text-slate-400">Step {step}</div>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">{title}</h2>
            {subtitle ? <p className="mt-2 text-sm leading-6 text-slate-600">{subtitle}</p> : null}
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

/**
 * Converts a persisted admin workflow definition into the same shape as WORKFLOW_TEMPLATES
 * entries so WorkflowPage renders from DB data without changing agent execution logic.
 * DB stage labels/subtitles merge over the base template; runCards/agentFit are preserved.
 */
function normalizeWorkflowDefinition(definition, activeProfile) {
  const baseTemplate =
    WORKFLOW_TEMPLATES[definition.system_profile_id] ??
    WORKFLOW_TEMPLATES[activeProfile] ??
    DEFAULT_TEMPLATE;

  const mergedSteps = { ...baseTemplate.steps };
  const dbStageNums = new Set();
  for (const stage of definition.stages || []) {
    const n = stage.stage_number;
    if (n >= 1 && n <= 7) {
      dbStageNums.add(n);
      mergedSteps[n] = {
        ...mergedSteps[n],
        label: stage.label || mergedSteps[n]?.label || `Stage ${n}`,
        subtitle: stage.notes || mergedSteps[n]?.subtitle || "",
        required: stage.required !== false,
      };
    }
  }
  // Step 3: rename to "Active Agent Processing" when DB-driven, unless explicitly labeled
  const step3HasCustomLabel = dbStageNums.has(3) && (definition.stages || []).find((s) => s.stage_number === 3)?.label;
  if (!step3HasCustomLabel) {
    mergedSteps[3] = {
      ...mergedSteps[3],
      label: "Active Agent Processing",
      subtitle: mergedSteps[3]?.subtitle || "Monitor the active agent run and review outputs as they appear.",
    };
  }

  const step1Stage = (definition.stages || []).find((s) => s.stage_number === 1);
  const step1Guidance = step1Stage?.notes || definition.notes || baseTemplate.step1Guidance;

  return {
    ...baseTemplate,
    step1Guidance,
    steps: mergedSteps,
    _fromDB: true,
    _dbSlug: definition.slug,
    _dbDisplayName: definition.display_name,
    _dbStageNums: dbStageNums,
  };
}

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

function CommandContextCard({ activeProfile, activeWorkspace, demoMode, nextStep, reviewNeeded, readyToSend, responses, openDeals, template }) {
  const profile = PROFILE_MAP[activeProfile] ?? PROFILE_MAP["custom"];
  const tpl = template ?? WORKFLOW_TEMPLATES[activeProfile] ?? DEFAULT_TEMPLATE;
  const nextLabel = tpl.steps[nextStep]?.label ?? `Step ${nextStep}`;
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

export default function WorkflowPage({ activeProfile = "custom", demoMode = false, activeWorkspace }) {
  const livePanelRef = useRef(null);
  const [distributionDrafts, setDistributionDrafts] = useState({});
  const [publishDraftOpen, setPublishDraftOpen] = useState({});
  const [tasks, setTasks] = useState([]);
  const [messages, setMessages] = useState([]);
  const [approvalRequests, setApprovalRequests] = useState([]);
  const [workflowAssets, setWorkflowAssets] = useState([]);
  const [deals, setDeals] = useState([]);
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
  // Phase 6B: resolved template — DB-normalized or static fallback
  const [resolvedTemplate, setResolvedTemplate] = useState(() => WORKFLOW_TEMPLATES[activeProfile] ?? DEFAULT_TEMPLATE);
  // Stepper state — tracks which step is expanded.
  // `manualStepOverride` is set true when the user clicks a step header;
  // it suppresses auto-advance until the next full loadWorkflow() completes.
  const [expandedStep, setExpandedStep] = useState(1);
  const manualStepOverride = useRef(false);

  // Sync resolvedTemplate with activeProfile when there is no DB definition loaded
  const activeTemplate = resolvedTemplate; // alias kept for compatibility

  function selectStep(stepNumber) {
    manualStepOverride.current = true;
    setExpandedStep(stepNumber);
  }

  async function loadWorkflow() {
    const [taskData, messageData, approvalData, dealData, runData, assetData] = await Promise.all([
      api.agentTasks({ limit: "200" }),
      api.messages({ limit: "250" }),
      api.approvalRequests({ limit: "200" }),
      api.deals({ limit: "250" }),
      api.agentRuns({ limit: "25" }),
      api.workflowAssets({ limit: "200" }).catch(() => ({ items: [] })),
    ]);
    const nextTasks = taskData.items || [];
    const nextRuns = runData.items || [];
    setTasks(nextTasks);
    setMessages(messageData.items || []);
    setApprovalRequests(approvalData.items || []);
    setWorkflowAssets(assetData.items || []);
    setDeals(dealData.items || []);
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

  useEffect(() => {
    loadWorkflow();
  }, []);

  // Phase 6B: Try to resolve a persisted workflow definition for the active workspace.
  // Falls back silently — never blocks the existing workflow render.
  useEffect(() => {
    setClientWorkflowDef(null);
    setResolvedTemplate(WORKFLOW_TEMPLATES[activeProfile] ?? DEFAULT_TEMPLATE);
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
          setResolvedTemplate(normalizeWorkflowDefinition(defData.item, activeProfile));
        }
      })
      .catch(() => {
        // 404 or any error — silently ignore, fallback is current behavior
      });
    return () => { cancelled = true; };
  }, [activeWorkspace]);

  // When profile changes without a workspace change, sync the fallback template
  useEffect(() => {
    if (!clientWorkflowDef) {
      setResolvedTemplate(WORKFLOW_TEMPLATES[activeProfile] ?? DEFAULT_TEMPLATE);
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
      if (action === "mark_published") {
        setPublishDraftOpen((current) => ({ ...current, [asset._id]: false }));
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
  const stageStatuses = {
    1: "ready",
    2: completedTodayTasks.length > 0 ? "completed" : "ready",
    3: activeTask?.status === "running" ? "running"
       : latestRun ? "completed"
       : "not_started",
    4: (draftsNeedingReview.length + openApprovals.length + currentRunAssets.length > 0) ? "needs_review"
       : (latestRun ? "ready" : "not_started"),
    5: (readyToSend.length + activeDistributionWorkCount > 0) ? "ready" : "not_started",
    6: (awaitingResponse.length + interested.length + booked.length > 0) ? "ready" : "not_started",
    7: (openDeals.length + closedWon.length > 0) ? "ready" : "not_started",
  };

  const nextStep = useMemo(() => {
    if (activeTask?.status === "running") return 3;
    if (readyToSend.length || activeDistributionWorkCount) return 5;
    if (draftsNeedingReview.length || openApprovals.length) return 4;
    if (awaitingResponse.length || interested.length || booked.length) return 6;
    if (openDeals.length || closedWon.length) return 7;
    return 1;
  }, [activeTask?.status, draftsNeedingReview.length, openApprovals.length, readyToSend.length, activeDistributionWorkCount, awaitingResponse.length, interested.length, booked.length, openDeals.length, closedWon.length]);

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
        template={resolvedTemplate}
      />
      <WorkflowSourceIndicator
        fromDB={!!resolvedTemplate._fromDB}
        dbDisplayName={resolvedTemplate._dbDisplayName}
        dbSlug={resolvedTemplate._dbSlug}
      />
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

      <StepSection step="1" title={activeTemplate.steps[1].label} subtitle={activeTemplate.steps[1].subtitle} active={nextStep === 1} expanded={expandedStep === 1} onExpand={() => selectStep(1)} stageStatus={stageStatuses[1]}>
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

      <StepSection step="2" title={activeTemplate.steps[2].label} subtitle={activeTemplate.steps[2].subtitle} active={nextStep === 2} count={tasks.length} expanded={expandedStep === 2} onExpand={() => selectStep(2)} stageStatus={stageStatuses[2]}>
        {completedTodayTasks.length > 0 && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-xs text-green-800">
            <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-green-600 text-white">
              <Check className="h-3 w-3" />
            </span>
            <span className="font-semibold">Completed Today</span>
            <span className="text-green-600">—</span>
            <span>{completedTodayTasks[0].agent_name} / {completedTodayTasks[0].task_type}</span>
            <span className="ml-auto shrink-0 text-green-600">{formatDate(completedTodayTasks[0].updated_at || completedTodayTasks[0].created_at)}</span>
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
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
      </StepSection>

      <div ref={livePanelRef}>
        <StepSection step="3" title={activeTemplate.steps[3].label} subtitle={activeTemplate.steps[3].subtitle} active={nextStep === 3} count={latestRun ? 1 : 0} expanded={expandedStep === 3} onExpand={() => selectStep(3)} stageStatus={stageStatuses[3]}>
          {latestRun || activeTask ? (
            <LiveAgentRunPanel task={activeTask} runDetail={activeRunDetail} loading={panelLoading} onRefresh={() => refreshRunDetail(activeTask?.linked_run_id || latestRun?.run_id)} />
          ) : (
            <EmptyState>No agent run yet. Use Step 2 to queue a run — outputs and timeline will appear here as the agent works.</EmptyState>
          )}
        </StepSection>
      </div>

      <StepSection step="4" title={activeTemplate.steps[4].label} subtitle={activeTemplate.steps[4].subtitle} active={nextStep === 4} count={draftsNeedingReview.length + openApprovals.length} expanded={expandedStep === 4} onExpand={() => selectStep(4)} stageStatus={stageStatuses[4]}>
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

      <StepSection step="5" title={activeTemplate.steps[5].label} subtitle={activeTemplate.steps[5].subtitle} active={nextStep === 5} count={readyToSend.length + activeDistributionWorkCount} expanded={expandedStep === 5} onExpand={() => selectStep(5)} stageStatus={stageStatuses[5]}>
        <div className="space-y-6">
          <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs leading-5 text-slate-500">
            Approved content awaiting publishing assignment. This step covers final distribution staging — platform selection, channel assignment, and publish queue management. It is not a content review step.
          </p>
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

      <StepSection step="6" title={activeTemplate.steps[6].label} subtitle={activeTemplate.steps[6].subtitle} active={nextStep === 6} count={awaitingResponse.length + interested.length + booked.length} expanded={expandedStep === 6} onExpand={() => selectStep(6)} stageStatus={stageStatuses[6]}>
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

      <StepSection step="7" title={activeTemplate.steps[7].label} subtitle={activeTemplate.steps[7].subtitle} active={nextStep === 7} count={openDeals.length + closedWon.length} expanded={expandedStep === 7} onExpand={() => selectStep(7)} stageStatus={stageStatuses[7]}>
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