/**
 * WorkflowAssetCard — Phase 5A
 *
 * Generic card component for workflow_assets records.
 * Supports asset_type: content_idea | script_draft | video_prompt
 *
 * Actions:
 * - Review mode: Approve · Reject
 * - Distribution mode: Queue · Remove from Queue · Mark Published · Archive
 */

import { Check, FileText, Film, Lightbulb, X } from "lucide-react";

const ASSET_TYPE_META = {
  content_idea:  { label: "Content Idea",   icon: Lightbulb, color: "blue" },
  script_draft:  { label: "Script Draft",   icon: FileText,  color: "violet" },
  video_prompt:  { label: "Video Prompt",   icon: Film,      color: "purple" },
};

const COLOR_CLASSES = {
  blue:   { border: "border-blue-200",   bg: "bg-blue-50",   badge: "bg-blue-100 text-blue-700",   title: "text-blue-950" },
  violet: { border: "border-violet-200", bg: "bg-violet-50", badge: "bg-violet-100 text-violet-700", title: "text-violet-950" },
  purple: { border: "border-purple-200", bg: "bg-purple-50", badge: "bg-purple-100 text-purple-700", title: "text-purple-950" },
};

function StateBadge({ state }) {
  const map = {
    needs_review: "bg-amber-100 text-amber-800",
    approved:     "bg-green-100 text-green-800",
    rejected:     "bg-slate-100 text-slate-600 line-through",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${map[state] ?? "bg-slate-100 text-slate-500"}`}>
      {state?.replace(/_/g, " ")}
    </span>
  );
}

function DistributionBadge({ state }) {
  const map = {
    not_queued: "bg-slate-100 text-slate-700",
    queued: "bg-blue-100 text-blue-700",
    published: "bg-emerald-100 text-emerald-700",
    archived: "bg-slate-200 text-slate-500",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${map[state] ?? "bg-slate-100 text-slate-500"}`}>
      {state?.replace(/_/g, " ")}
    </span>
  );
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

export default function WorkflowAssetCard({
  asset,
  onDecide,
  busyId,
  mode = "review",
  distributionDraft,
  onDistributionDraftChange,
  onDistributionAction,
  showPublishFields = false,
  onTogglePublishFields,
}) {
  const type = asset.asset_type || "content_idea";
  const meta = ASSET_TYPE_META[type] ?? ASSET_TYPE_META.content_idea;
  const colors = COLOR_CLASSES[meta.color];
  const Icon = meta.icon;

  const isSynthetic = asset.metadata?.synthetic_demo === true;
  const isApproved  = asset.approval_state === "approved";
  const isRejected  = asset.approval_state === "rejected";
  const distributionState = asset.distribution_state || "not_queued";
  const busy        = busyId === asset._id;
  const isDistributionMode = mode === "distribution";
  const isPublished = distributionState === "published";
  const isArchived = distributionState === "archived";
  const canEditDistributionFields = isDistributionMode && (distributionState === "not_queued" || distributionState === "queued");

  if (isRejected) return null;

  return (
    <article className={`rounded-lg border ${colors.border} ${colors.bg} p-4`}>
      {/* Header row */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${colors.badge}`}>
            <Icon className="h-3 w-3" />
            {meta.label}
          </span>
          {isSynthetic && (
            <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              synthetic demo
            </span>
          )}
          <StateBadge state={asset.approval_state} />
          {isDistributionMode ? <DistributionBadge state={distributionState} /> : null}
        </div>
        <div className="text-xs text-slate-400">{formatDate(asset.created_at)}</div>
      </div>

      {/* Title */}
      <div className={`mt-3 font-semibold leading-snug ${colors.title}`}>{asset.title || "Untitled asset"}</div>

      {/* Summary */}
      {asset.summary ? (
        <p className="mt-1.5 text-sm leading-6 text-slate-700">{asset.summary}</p>
      ) : null}

      {/* Body preview (first 400 chars) */}
      {asset.body ? (
        <div className="mt-3 max-h-40 overflow-hidden rounded-lg border border-slate-200 bg-white p-3 text-xs leading-6 text-slate-600 relative">
          <pre className="whitespace-pre-wrap font-sans">{asset.body.slice(0, 400)}{asset.body.length > 400 ? "…" : ""}</pre>
          {asset.body.length > 400 && (
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-white" />
          )}
        </div>
      ) : null}

      {/* Platform / metadata chips */}
      {asset.platform || asset.metadata?.platform ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
            {asset.platform || asset.metadata?.platform}
          </span>
        </div>
      ) : null}

      {isDistributionMode ? (
        <div className="mt-4 space-y-3 rounded-lg border border-slate-200 bg-white/70 p-3">
          <div className="text-xs font-medium text-slate-600">Manual distribution only. SignalForge will not post, schedule, or publish this asset automatically.</div>

          {canEditDistributionFields ? (
            <div className="grid gap-3">
              <label className="grid gap-1 text-xs font-medium text-slate-600">
                Distribution channel
                <input
                  type="text"
                  value={distributionDraft?.distribution_channel ?? ""}
                  onChange={(event) => onDistributionDraftChange?.(asset, { distribution_channel: event.target.value })}
                  placeholder={asset.platform || asset.metadata?.platform || "e.g. LinkedIn"}
                  className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
                />
              </label>
              <label className="grid gap-1 text-xs font-medium text-slate-600">
                Distribution notes
                <textarea
                  value={distributionDraft?.distribution_notes ?? ""}
                  onChange={(event) => onDistributionDraftChange?.(asset, { distribution_notes: event.target.value })}
                  placeholder="Manual-only notes for posting context"
                  className="min-h-20 rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-700"
                />
              </label>
            </div>
          ) : null}

          {(showPublishFields || isPublished) ? (
            <label className="grid gap-1 text-xs font-medium text-slate-600">
              Published URL {isPublished ? "" : "(optional)"}
              <input
                type="url"
                value={distributionDraft?.published_url ?? asset.published_url ?? ""}
                onChange={(event) => onDistributionDraftChange?.(asset, { published_url: event.target.value })}
                placeholder="https://..."
                disabled={!showPublishFields && !isPublished}
                className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 disabled:bg-slate-50 disabled:text-slate-500"
              />
            </label>
          ) : null}

          {(asset.distribution_channel || asset.distribution_notes || asset.published_at || asset.published_url) && !canEditDistributionFields ? (
            <div className="space-y-1 text-xs text-slate-600">
              {asset.distribution_channel ? <div><span className="font-semibold text-slate-700">Channel:</span> {asset.distribution_channel}</div> : null}
              {asset.distribution_notes ? <div><span className="font-semibold text-slate-700">Notes:</span> {asset.distribution_notes}</div> : null}
              {asset.published_at ? <div><span className="font-semibold text-slate-700">Published:</span> {formatDate(asset.published_at)}</div> : null}
              {asset.published_url ? <div className="break-all"><span className="font-semibold text-slate-700">URL:</span> {asset.published_url}</div> : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Actions */}
      {!isDistributionMode && !isApproved && (
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => onDecide?.(asset, "approve")}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-green-600 px-3 text-xs font-medium text-white transition hover:bg-green-700 disabled:bg-slate-300"
          >
            <Check className="h-3.5 w-3.5" />
            Approve
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onDecide?.(asset, "reject")}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-slate-800 px-3 text-xs font-medium text-white transition hover:bg-red-700 disabled:bg-slate-300"
          >
            <X className="h-3.5 w-3.5" />
            Reject
          </button>
        </div>
      )}

      {!isDistributionMode && isApproved && (
        <div className="mt-3 text-xs font-medium text-green-700">✓ Approved — ready for distribution queue.</div>
      )}

      {isDistributionMode && isApproved ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {distributionState === "not_queued" ? (
            <>
              <button
                type="button"
                disabled={busy}
                onClick={() => onDistributionAction?.(asset, "queue")}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-blue-600 px-3 text-xs font-medium text-white transition hover:bg-blue-700 disabled:bg-slate-300"
              >
                Queue for Distribution
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => onDistributionAction?.(asset, "archive")}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-slate-800 px-3 text-xs font-medium text-white transition hover:bg-slate-900 disabled:bg-slate-300"
              >
                Archive
              </button>
            </>
          ) : null}

          {distributionState === "queued" ? (
            <>
              {!showPublishFields ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onTogglePublishFields?.(asset)}
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700 disabled:opacity-60"
                >
                  Add Publish URL
                </button>
              ) : null}
              <button
                type="button"
                disabled={busy}
                onClick={() => onDistributionAction?.(asset, "mark_published")}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-green-600 px-3 text-xs font-medium text-white transition hover:bg-green-700 disabled:bg-slate-300"
              >
                Mark Published
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => onDistributionAction?.(asset, "unqueue")}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 transition hover:border-slate-300 disabled:opacity-60"
              >
                Remove from Queue
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => onDistributionAction?.(asset, "archive")}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-slate-800 px-3 text-xs font-medium text-white transition hover:bg-slate-900 disabled:bg-slate-300"
              >
                Archive
              </button>
            </>
          ) : null}

          {distributionState === "published" ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => onDistributionAction?.(asset, "archive")}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-slate-800 px-3 text-xs font-medium text-white transition hover:bg-slate-900 disabled:bg-slate-300"
            >
              Archive
            </button>
          ) : null}

          {isArchived ? (
            <div className="text-xs font-medium text-slate-500">Archived. Hidden from active queue counts.</div>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
