import { useState, useEffect } from "react";
import {
  postInstagramPublish,
  postInstagramRetry,
  getInstagramAttemptStatus,
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
 * InstagramPublishPanel.jsx
 *
 * Publish an approved rendered asset to Instagram with real-time attempt tracking.
 * Mirrors LinkedInPublishPanel.jsx. Unlike LinkedIn's text-post flow, Instagram
 * publishes media by URL — the operator supplies a publicly-reachable media_url;
 * SignalForge does not auto-host media to the internet.
 *
 * Props:
 *   workspaceSlug   — workspace
 *   defaultRenderId — optional pre-fill for the approved asset_renders id
 */
export default function InstagramPublishPanel({
  workspaceSlug = "default",
  defaultRenderId = "",
}) {
  const [renderId, setRenderId]     = useState(defaultRenderId);
  const [caption, setCaption]       = useState("");
  const [mediaUrl, setMediaUrl]     = useState("");
  const [mediaType, setMediaType]   = useState("IMAGE");
  const [attempt, setAttempt]       = useState(null);
  const [publishing, setPublishing] = useState(false);
  const [retrying, setRetrying]     = useState(false);
  const [polling, setPolling]       = useState(false);
  const [error, setError]           = useState(null);
  const [approvedRenders, setApprovedRenders]   = useState([]);
  const [rendersLoading, setRendersLoading]     = useState(true);

  useEffect(() => {
    let cancelled = false;
    setRendersLoading(true);
    api.assetRenders({ workspace_slug: workspaceSlug, status: "approved", limit: 50 })
      .then((data) => { if (!cancelled) setApprovedRenders(data.items || []); })
      .catch(() => { if (!cancelled) setApprovedRenders([]); })
      .finally(() => { if (!cancelled) setRendersLoading(false); });
    return () => { cancelled = true; };
  }, [workspaceSlug]);

  async function handlePublish(e) {
    e.preventDefault();
    if (!renderId.trim() || !mediaUrl.trim()) {
      setError("Render ID and media URL are required.");
      return;
    }
    setPublishing(true);
    setError(null);
    try {
      const result = await postInstagramPublish({
        workspace_slug:         workspaceSlug,
        source_asset_render_id: renderId.trim(),
        caption:                caption.trim(),
        media_url:              mediaUrl.trim(),
        media_type:             mediaType,
      });
      setAttempt(result);
    } catch (e) {
      if (e?.status === 409) {
        setError("This render has already been published. Use a different render ID to publish again.");
      } else if (e?.status === 422) {
        setError(e.message || "The referenced render must be approved before it can be published.");
      } else if (e?.status === 404) {
        setError("Render not found — check the render ID.");
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
      const result = await postInstagramRetry(attempt.distribution_attempt_id, {
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
      const result = await getInstagramAttemptStatus(attempt.distribution_attempt_id);
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
      <h3 className="text-white font-semibold text-sm mb-4">Publish to Instagram</h3>

      {error && (
        <div className="bg-red-950 border border-red-800 rounded p-2 mb-4 text-red-300 text-xs">
          {error}
        </div>
      )}

      {/* Form */}
      <form onSubmit={handlePublish} className="space-y-3 mb-5">
        <div>
          <label className="block text-gray-400 text-xs mb-1">Approved renders</label>
          {rendersLoading ? (
            <div className="h-9 bg-gray-800 rounded animate-pulse" />
          ) : approvedRenders.length === 0 ? (
            <p className="text-gray-600 text-xs">No approved renders ready for distribution yet.</p>
          ) : (
            <select
              value=""
              onChange={(e) => { if (e.target.value) setRenderId(e.target.value); }}
              disabled={publishing}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-pink-600"
            >
              <option value="">Select an approved render…</option>
              {approvedRenders.map((r) => (
                <option key={r._id} value={r._id}>
                  {(r.asset_type || r.generation_engine || "render")} · {r.created_at ? new Date(r.created_at).toLocaleDateString() : ""} · …{String(r._id).slice(-6)}
                </option>
              ))}
            </select>
          )}
        </div>
        <div>
          <label className="block text-gray-400 text-xs mb-1">Rendered Asset ID (must be approved)</label>
          <input
            type="text"
            value={renderId}
            onChange={e => setRenderId(e.target.value)}
            placeholder="e.g. render-abc123"
            disabled={publishing}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-pink-600"
          />
        </div>
        <div>
          <label className="block text-gray-400 text-xs mb-1">Media Type</label>
          <select
            value={mediaType}
            onChange={e => setMediaType(e.target.value)}
            disabled={publishing}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-pink-600"
          >
            <option value="IMAGE">Image</option>
            <option value="REELS">Reels (video)</option>
          </select>
        </div>
        <div>
          <label className="block text-gray-400 text-xs mb-1">Public Media URL</label>
          <input
            type="text"
            value={mediaUrl}
            onChange={e => setMediaUrl(e.target.value)}
            placeholder="https://... (must be publicly reachable — Instagram fetches it)"
            disabled={publishing}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-pink-600"
          />
          <p className="text-gray-600 text-xs mt-0.5">
            SignalForge does not host media publicly — paste a URL you control (e.g. from your own hosting).
          </p>
        </div>
        <div>
          <label className="block text-gray-400 text-xs mb-1">Caption</label>
          <textarea
            value={caption}
            onChange={e => setCaption(e.target.value)}
            rows={4}
            placeholder="Write your Instagram caption here…"
            disabled={publishing}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-pink-600 resize-none"
          />
          <p className="text-gray-600 text-xs mt-0.5">{caption.length} / 2200</p>
        </div>
        <button
          type="submit"
          disabled={publishing}
          className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
            publishing
              ? "bg-gray-700 text-gray-500 cursor-not-allowed"
              : "bg-pink-700 hover:bg-pink-600 text-white"
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
                    className="text-pink-400 hover:underline font-mono truncate"
                  >
                    {attempt.published_url}
                  </a>
                </p>
              )}
            </div>
          )}

          {attempt.simulated && (
            <p className="text-yellow-400 text-xs">⚡ Simulated publish (no live Instagram credentials configured)</p>
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
