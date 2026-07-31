/**
 * OutputQualityReviewPanel.jsx
 * Phase 6Y — Scoring panel for reviewing agent-generated content.
 * 5 dimension sliders (0-5), approve/reject/publish-ready actions,
 * revision reason dropdown, memory comparison toggle.
 */

import React, { useState, useCallback } from "react";
import {
  CheckCircle,
  XCircle,
  RefreshCw,
  Send,
  ChevronDown,
} from "lucide-react";
import {
  postQualityReview,
  patchQualityReview,
  postRevisionLoop,
  postMemoryComparison,
} from "../api.js";

const DIMENSIONS = [
  { key: "relevance",         label: "Relevance" },
  { key: "clarity",           label: "Clarity" },
  { key: "client_fit",        label: "Client Fit" },
  { key: "publish_readiness", label: "Publish Readiness" },
  { key: "strategic_value",   label: "Strategic Value" },
];

const REVISION_REASONS = [
  "tone_mismatch",
  "off_brand",
  "too_generic",
  "factually_unsafe",
  "weak_cta",
  "off_audience",
  "too_long",
  "too_short",
  "not_original",
  "blocked_claim",
];

const DEFAULT_SCORES = Object.fromEntries(DIMENSIONS.map((d) => [d.key, 3]));

function avg(scores) {
  const vals = Object.values(scores);
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
}

export default function OutputQualityReviewPanel({
  workspaceSlug = "default",
  contentItemId = "",
  contentType   = "linkedin_post",
  contentText   = "",
  reviewId      = null,        // if set, component is in update mode
  memoryVersion = 0,
  onSubmit      = null,        // callback(result)
  compact       = false,
}) {
  const [scores, setScores]             = useState(DEFAULT_SCORES);
  const [approved, setApproved]         = useState(false);
  const [publishReady, setPublishReady] = useState(false);
  const [revision, setRevision]         = useState(false);
  const [revisionReason, setRevisionReason] = useState("");
  const [reviewerNotes, setReviewerNotes]   = useState("");
  const [showComparison, setShowComparison] = useState(false);
  const [submitting, setSubmitting]     = useState(false);
  const [result, setResult]             = useState(null);
  const [error, setError]               = useState(null);

  const handleScore = useCallback((dim, val) => {
    setScores((prev) => ({ ...prev, [dim]: Number(val) }));
  }, []);

  const avgScore = avg(scores);
  const autoPublish = avgScore >= 3.5;

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      let res;
      if (reviewId) {
        res = await patchQualityReview(reviewId, {
          scores,
          approved,
          publish_ready:      publishReady || autoPublish,
          revision_requested: revision,
          revision_reason:    revision ? revisionReason : null,
          reviewer_notes:     reviewerNotes || null,
        });
      } else {
        res = await postQualityReview({
          workspace_slug:     workspaceSlug,
          content_item_id:    contentItemId,
          content_type:       contentType,
          content_text:       contentText,
          scores,
          approved,
          publish_ready:      publishReady || autoPublish,
          revision_requested: revision,
          revision_reason:    revision ? revisionReason : null,
          reviewer_notes:     reviewerNotes || null,
          memory_version:     memoryVersion,
        });
      }
      setResult(res);
      if (onSubmit) onSubmit(res);
    } catch (e) {
      setError(e.message || "Submission failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRevisionLoop() {
    if (!reviewId) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await postRevisionLoop(reviewId, workspaceSlug);
      setResult(res);
      if (onSubmit) onSubmit(res);
    } catch (e) {
      setError(e.message || "Revision loop failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={`bg-white border border-gray-200 rounded-xl shadow-sm ${compact ? "p-4" : "p-6"} space-y-4`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-800">
          Quality Review
          {contentType && (
            <span className="ml-2 text-xs font-normal text-gray-400 bg-gray-100 rounded px-2 py-0.5">
              {contentType.replace(/_/g, " ")}
            </span>
          )}
        </h3>
        <span
          className={`text-xs font-bold px-2 py-0.5 rounded-full ${
            avgScore >= 3.5
              ? "bg-green-100 text-green-700"
              : avgScore >= 2.5
              ? "bg-yellow-100 text-yellow-700"
              : "bg-red-100 text-red-700"
          }`}
        >
          Avg {avgScore.toFixed(1)} / 5
        </span>
      </div>

      {/* Content preview */}
      {contentText && !compact && (
        <div className="text-xs text-gray-600 bg-gray-50 rounded p-3 max-h-28 overflow-y-auto whitespace-pre-wrap">
          {contentText}
        </div>
      )}

      {/* Dimension sliders */}
      <div className="space-y-3">
        {DIMENSIONS.map(({ key, label }) => (
          <div key={key} className="flex items-center gap-3">
            <span className="w-36 text-xs text-gray-600 shrink-0">{label}</span>
            <input
              type="range"
              min={0}
              max={5}
              step={1}
              value={scores[key]}
              onChange={(e) => handleScore(key, e.target.value)}
              className="flex-1 h-1.5 accent-indigo-600"
            />
            <span className="w-5 text-xs text-center font-semibold text-gray-700">
              {scores[key]}
            </span>
          </div>
        ))}
      </div>

      {/* Auto-publish notice */}
      {autoPublish && (
        <p className="text-xs text-green-600 font-medium">
          ✓ Average ≥ 3.5 — will be marked publish-ready automatically.
        </p>
      )}

      {/* Action toggles */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => { setApproved((v) => !v); setRevision(false); }}
          className={`flex items-center gap-1 text-xs px-3 py-1.5 rounded-full border transition-colors ${
            approved
              ? "bg-green-600 text-white border-green-600"
              : "text-green-700 border-green-300 hover:bg-green-50"
          }`}
        >
          <CheckCircle className="w-3.5 h-3.5" />
          Approve
        </button>

        <button
          onClick={() => { setRevision((v) => !v); setApproved(false); }}
          className={`flex items-center gap-1 text-xs px-3 py-1.5 rounded-full border transition-colors ${
            revision
              ? "bg-red-600 text-white border-red-600"
              : "text-red-700 border-red-300 hover:bg-red-50"
          }`}
        >
          <XCircle className="w-3.5 h-3.5" />
          Request Revision
        </button>

        <button
          onClick={() => setPublishReady((v) => !v)}
          className={`flex items-center gap-1 text-xs px-3 py-1.5 rounded-full border transition-colors ${
            publishReady
              ? "bg-indigo-600 text-white border-indigo-600"
              : "text-indigo-700 border-indigo-300 hover:bg-indigo-50"
          }`}
        >
          <Send className="w-3.5 h-3.5" />
          Mark Publish-Ready
        </button>

        <button
          onClick={() => setShowComparison((v) => !v)}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-full border text-purple-700 border-purple-300 hover:bg-purple-50 transition-colors"
        >
          <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showComparison ? "rotate-180" : ""}`} />
          Memory Compare
        </button>
      </div>

      {/* Revision reason */}
      {revision && (
        <div className="space-y-2">
          <label className="text-xs font-medium text-gray-600">Revision Reason</label>
          <select
            value={revisionReason}
            onChange={(e) => setRevisionReason(e.target.value)}
            className="w-full text-xs border border-gray-200 rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-red-400"
          >
            <option value="">Select reason…</option>
            {REVISION_REASONS.map((r) => (
              <option key={r} value={r}>
                {r.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Memory compare panel */}
      {showComparison && (
        <MemoryCompareRow scores={scores} workspaceSlug={workspaceSlug} contentType={contentType} contentText={contentText} />
      )}

      {/* Reviewer notes */}
      <textarea
        placeholder="Reviewer notes (optional)…"
        value={reviewerNotes}
        onChange={(e) => setReviewerNotes(e.target.value)}
        rows={2}
        className="w-full text-xs border border-gray-200 rounded px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-400 resize-none"
      />

      {/* Errors */}
      {error && (
        <p className="text-xs text-red-600 bg-red-50 rounded px-3 py-2">{error}</p>
      )}

      {/* Success result */}
      {result && (
        <div className="text-xs text-green-700 bg-green-50 rounded px-3 py-2 space-y-0.5">
          <p className="font-medium">Submitted ✓</p>
          {result.review_id && <p>Review ID: <span className="font-mono">{result.review_id}</span></p>}
          {result.new_review_id && <p>Revision ID: <span className="font-mono">{result.new_review_id}</span></p>}
        </div>
      )}

      {/* Submit */}
      <div className="flex gap-2">
        <button
          onClick={handleSubmit}
          disabled={submitting}
          className="flex-1 text-xs font-medium bg-indigo-600 text-white rounded-lg px-4 py-2 hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {submitting ? "Submitting…" : reviewId ? "Update Review" : "Submit Review"}
        </button>

        {reviewId && (
          <button
            onClick={handleRevisionLoop}
            disabled={submitting}
            title="Run revision loop — generate fresh memory-informed content"
            className="flex items-center gap-1 text-xs font-medium border border-gray-200 text-gray-700 rounded-lg px-3 py-2 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Revise
          </button>
        )}
      </div>
    </div>
  );
}


// ── Memory comparison inline widget ──────────────────────────────────────────

function MemoryCompareRow({ scores, workspaceSlug, contentType, contentText }) {
  const [baselineScores, setBaselineScores] = useState(
    Object.fromEntries(Object.keys(scores).map((k) => [k, Math.max(0, scores[k] - 1)]))
  );
  const [result, setResult]   = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  async function runCompare() {
    setLoading(true);
    setError(null);
    try {
      const res = await postMemoryComparison({
        workspace_slug:  workspaceSlug,
        content_type:    contentType,
        content_text:    contentText,
        baseline_scores: baselineScores,
        memory_scores:   scores,
      });
      setResult(res);
    } catch (e) {
      setError(e.message || "Comparison failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-purple-50 border border-purple-100 rounded-lg p-3 space-y-2 text-xs">
      <p className="font-medium text-purple-700">Memory Impact Comparison</p>
      <p className="text-gray-500">Baseline scores (pre-memory) are set 1 point lower. Adjust if needed, then run.</p>

      {result ? (
        <div className="space-y-1">
          <div className="flex gap-4">
            <span className="text-gray-500">Baseline avg: <strong>{result.baseline_avg}</strong></span>
            <span className="text-gray-500">Memory avg: <strong>{result.memory_avg}</strong></span>
            <span className={result.improved ? "text-green-700 font-semibold" : "text-red-600"}>
              {result.improved ? `↑ +${result.delta.toFixed(2)} Improved` : `→ ${result.delta.toFixed(2)} No significant lift`}
            </span>
          </div>
        </div>
      ) : (
        <button
          onClick={runCompare}
          disabled={loading}
          className="text-xs bg-purple-600 text-white rounded px-3 py-1 hover:bg-purple-700 disabled:opacity-50"
        >
          {loading ? "Comparing…" : "Run Comparison"}
        </button>
      )}
      {error && <p className="text-red-600">{error}</p>}
    </div>
  );
}
