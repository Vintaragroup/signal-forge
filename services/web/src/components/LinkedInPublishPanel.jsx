import { useState, useEffect } from "react";
import {
  postLinkedInPublish,
  postLinkedInRetry,
  getLinkedInAttemptStatus,
  api,
} from "../api";

const STATUS_BADGE = {
  pending:   "bg-yellow-900 text-yellow-300 border-yellow-700",
  verified:  "bg-green-900  text-green-300  border-green-700",
  failed:    "bg-red-900    text-red-300    border-red-700",
  retrying:  "bg-blue-900   text-blue-300   border-blue-700",
  escalated: "bg-orange-900 text-orange-300 border-orange-700",
};

/**
 * LinkedInPublishPanel.jsx
 *
 * Publish a workflow asset to LinkedIn with real-time attempt tracking.
 *
 * Props:
 *   workspaceSlug  — workspace
 *   defaultAssetId — optional pre-fill for asset ID
 *   defaultText    — optional pre-fill for content text
 */
export default function LinkedInPublishPanel({
  workspaceSlug = "default",
  defaultAssetId = "",
  defaultText = "",
}) {
  const [assetId, setAssetId]       = useState(defaultAssetId);
  const [contentText, setContent]   = useState(defaultText);
  const [attempt, setAttempt]       = useState(null);
  const [publishing, setPublishing] = useState(false);
  const [retrying, setRetrying]     = useState(false);
  const [polling, setPolling]       = useState(false);
  const [error, setError]           = useState(null);
  const [approvedAssets, setApprovedAssets]     = useState([]);
  const [assetsLoading, setAssetsLoading]       = useState(true);

  useEffect(() => {
    let cancelled = false;
    setAssetsLoading(true);
    api.workflowAssets({
      workspace_slug: workspaceSlug,
      approval_state: "approved",
      distribution_state: "not_queued",
      limit: 50,
    })
      .then((data) => { if (!cancelled) setApprovedAssets(data.items || []); })
      .catch(() => { if (!cancelled) setApprovedAssets([]); })
      .finally(() => { if (!cancelled) setAssetsLoading(false); });
    return () => { cancelled = true; };
  }, [workspaceSlug]);

  async function handlePublish(e) {
    e.preventDefault();
    if (!assetId.trim() || !contentText.trim()) {
      setError("Asset ID and content text are required.");
      return;
    }
    setPublishing(true);
    setError(null);
    try {
      const result = await postLinkedInPublish({
        workspace_slug:    workspaceSlug,
        workflow_asset_id: assetId.trim(),
        content_text:      contentText.trim(),
      });
      setAttempt(result);
    } catch (e) {
      if (e?.status === 409) {
        setError("This asset has already been published. Use a different asset ID to publish again.");
      } else {
        setError(e.message || "Publish failed.");
      }
    } finally {
      setPublishing(false);
    }
  }

  async function handleRetry() {
    if (!attempt) return;
    setRetrying(true);
    setError(null);
    try {
      const result = await postLinkedInRetry(attempt.distribution_attempt_id, {
        workspace_slug: workspaceSlug,
      });
      setAttempt(result);
    } catch (e) {
      setError(e.message || "Retry failed.");
    } finally {
      setRetrying(false);
    }
  }

  async function pollStatus() {
    if (!attempt) return;
    setPolling(true);
    try {
      const result = await getLinkedInAttemptStatus(attempt.distribution_attempt_id);
      setAttempt(result);
    } catch (e) {
      setError(e.message || "Status check failed.");
    } finally {
      setPolling(false);
    }
  }

  const canRetry = attempt && ["failed", "retrying"].includes(attempt.status);

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
      <h3 className="text-white font-semibold text-sm mb-4">Publish to LinkedIn</h3>

      {error && (
        <div className="bg-red-950 border border-red-800 rounded p-2 mb-4 text-red-300 text-xs">
          {error}
        </div>
      )}

      {/* Form */}
      <form onSubmit={handlePublish} className="space-y-3 mb-5">
        <div>
          <label className="block text-gray-400 text-xs mb-1">Approved assets ready for distribution</label>
          {assetsLoading ? (
            <div className="h-9 bg-gray-800 rounded animate-pulse" />
          ) : approvedAssets.length === 0 ? (
            <p className="text-gray-600 text-xs">No approved assets ready for distribution yet.</p>
          ) : (
            <select
              value=""
              onChange={(e) => { if (e.target.value) setAssetId(e.target.value); }}
              disabled={publishing}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-600"
            >
              <option value="">Select an approved asset…</option>
              {approvedAssets.map((a) => (
                <option key={a._id} value={a._id}>
                  {(a.title || a.asset_type || "asset")} · …{String(a._id).slice(-6)}
                </option>
              ))}
            </select>
          )}
        </div>
        <div>
          <label className="block text-gray-400 text-xs mb-1">Workflow Asset ID</label>
          <input
            type="text"
            value={assetId}
            onChange={e => setAssetId(e.target.value)}
            placeholder="e.g. wfa_abc123"
            disabled={publishing}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-600"
          />
        </div>
        <div>
          <label className="block text-gray-400 text-xs mb-1">Content Text</label>
          <textarea
            value={contentText}
            onChange={e => setContent(e.target.value)}
            rows={4}
            placeholder="Write your LinkedIn post here…"
            disabled={publishing}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-600 resize-none"
          />
          <p className="text-gray-600 text-xs mt-0.5">{contentText.length} / 3000</p>
        </div>
        <button
          type="submit"
          disabled={publishing}
          className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
            publishing
              ? "bg-gray-700 text-gray-500 cursor-not-allowed"
              : "bg-blue-700 hover:bg-blue-600 text-white"
          }`}
        >
          {publishing ? "Publishing…" : "Publish Now"}
        </button>
      </form>

      {/* Attempt result */}
      {attempt && (
        <div className="border border-gray-800 rounded p-4 bg-gray-950 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-gray-400 text-xs font-mono">{attempt.distribution_attempt_id}</p>
            <span className={`px-2 py-0.5 rounded text-xs font-semibold uppercase border ${
              STATUS_BADGE[attempt.status] ?? "bg-gray-800 text-gray-400 border-gray-700"
            }`}>
              {attempt.status}
            </span>
          </div>

          {attempt.external_post_id && (
            <div className="text-xs space-y-0.5">
              <p className="text-gray-400">Post ID: <span className="text-gray-300 font-mono">{attempt.external_post_id}</span></p>
              {attempt.published_url && (
                <p className="text-gray-400">
                  URL:{" "}
                  <a
                    href={attempt.published_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-400 hover:underline font-mono truncate"
                  >
                    {attempt.published_url}
                  </a>
                </p>
              )}
            </div>
          )}

          {attempt._simulated && (
            <p className="text-yellow-400 text-xs">⚡ Simulated publish (no live LinkedIn credentials configured)</p>
          )}

          {attempt.escalated && (
            <p className="text-orange-400 text-xs">⚠ Escalated — retry limit reached. Manual review required.</p>
          )}

          <div className="flex gap-2 pt-1">
            <button
              onClick={pollStatus}
              disabled={polling}
              className="px-3 py-1 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-xs"
            >
              {polling ? "Checking…" : "↺ Refresh Status"}
            </button>
            {canRetry && (
              <button
                onClick={handleRetry}
                disabled={retrying}
                className={`px-3 py-1 rounded text-xs ${
                  retrying
                    ? "bg-gray-700 text-gray-500 cursor-not-allowed"
                    : "bg-orange-900 hover:bg-orange-800 text-orange-300"
                }`}
              >
                {retrying ? "Retrying…" : "Retry Publish"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
