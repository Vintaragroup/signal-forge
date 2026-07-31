/**
 * OutputQualityPage.jsx
 * Phase 6Y — Full page: review list + scoring panel + metrics dashboard
 * + memory comparison + publish-ready filter.
 */

import React, { useState, useEffect, useCallback } from "react";
import {
  ClipboardList,
  CheckCircle,
  Send,
  BarChart2,
  RefreshCw,
  Package,
  Filter,
} from "lucide-react";
import OutputQualityReviewPanel from "../components/OutputQualityReviewPanel.jsx";
import {
  getQualityReviews,
  getQualityMetrics,
  getPublishReady,
  postContentPackage,
  postPilotWorkspaceSeed,
} from "../api.js";

const WORKSPACE_DEFAULT = "pilot-john-maxwell";

export default function OutputQualityPage() {
  const [workspaceSlug, setWorkspaceSlug] = useState(WORKSPACE_DEFAULT);
  const [tab, setTab]               = useState("reviews");  // reviews | publish | metrics | generate
  const [reviews, setReviews]       = useState([]);
  const [publishReady, setPublishReady] = useState([]);
  const [metrics, setMetrics]       = useState(null);
  const [selectedReview, setSelectedReview] = useState(null);
  const [loading, setLoading]       = useState(false);
  const [seeding, setSeeding]       = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genResult, setGenResult]   = useState(null);
  const [error, setError]           = useState(null);
  const [filterType, setFilterType] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rv, pr, mx] = await Promise.all([
        getQualityReviews({ workspace_slug: workspaceSlug, content_type: filterType || undefined }),
        getPublishReady(workspaceSlug),
        getQualityMetrics(workspaceSlug),
      ]);
      setReviews(rv.reviews || []);
      setPublishReady(pr.publish_ready || []);
      setMetrics(mx);
    } catch (e) {
      setError(e.message || "Load failed");
    } finally {
      setLoading(false);
    }
  }, [workspaceSlug, filterType]);

  useEffect(() => { load(); }, [load]);

  async function seedWorkspace() {
    setSeeding(true);
    setError(null);
    try {
      await postPilotWorkspaceSeed({ workspace_slug: workspaceSlug, force: false });
      load();
    } catch (e) {
      setError(e.message || "Seed failed");
    } finally {
      setSeeding(false);
    }
  }

  async function generatePackage() {
    setGenerating(true);
    setError(null);
    try {
      const res = await postContentPackage({
        workspace_slug: workspaceSlug,
        client_name:    "John Maxwell",
        use_memory:     true,
      });
      setGenResult(res);
      load();
    } catch (e) {
      setError(e.message || "Generation failed");
    } finally {
      setGenerating(false);
    }
  }

  const TABS = [
    { id: "reviews",  label: "Reviews",      icon: ClipboardList },
    { id: "publish",  label: "Publish-Ready", icon: Send },
    { id: "metrics",  label: "Metrics",       icon: BarChart2 },
    { id: "generate", label: "Generate",      icon: Package },
  ];

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* ── Top bar ── */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <ClipboardList className="w-5 h-5 text-indigo-600" />
          <h1 className="text-base font-semibold text-gray-800">Output Quality</h1>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <input
            type="text"
            value={workspaceSlug}
            onChange={(e) => setWorkspaceSlug(e.target.value)}
            placeholder="workspace slug"
            className="text-xs border border-gray-200 rounded px-3 py-1.5 w-52 focus:outline-none focus:ring-1 focus:ring-indigo-400"
          />

          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1 text-xs text-gray-600 border border-gray-200 rounded px-3 py-1.5 hover:bg-gray-50 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>

          <button
            onClick={seedWorkspace}
            disabled={seeding}
            className="text-xs bg-purple-600 text-white rounded px-3 py-1.5 hover:bg-purple-700 disabled:opacity-50"
          >
            {seeding ? "Seeding…" : "Seed Pilot Workspace"}
          </button>
        </div>
      </div>

      {/* ── Tabs ── */}
      <div className="bg-white border-b border-gray-200 px-6 flex gap-1">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-1.5 text-xs px-4 py-3 border-b-2 transition-colors ${
              tab === id
                ? "border-indigo-600 text-indigo-700 font-semibold"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* ── Error banner ── */}
      {error && (
        <div className="mx-6 mt-4 text-xs text-red-700 bg-red-50 border border-red-200 rounded px-4 py-2">
          {error}
        </div>
      )}

      {/* ── Content ── */}
      <div className="flex-1 overflow-y-auto p-6">

        {/* ─ Reviews tab ─ */}
        {tab === "reviews" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* List */}
            <div className="lg:col-span-2 space-y-3">
              <div className="flex items-center gap-3 mb-2">
                <h2 className="text-sm font-semibold text-gray-700">Reviews ({reviews.length})</h2>
                <div className="flex items-center gap-1">
                  <Filter className="w-3.5 h-3.5 text-gray-400" />
                  <select
                    value={filterType}
                    onChange={(e) => setFilterType(e.target.value)}
                    className="text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none"
                  >
                    <option value="">All types</option>
                    <option value="linkedin_post">LinkedIn Post</option>
                    <option value="content_hook">Content Hook</option>
                    <option value="video_concept">Video Concept</option>
                    <option value="outreach_angle">Outreach Angle</option>
                    <option value="campaign_summary">Campaign Summary</option>
                  </select>
                </div>
              </div>

              {loading && <p className="text-xs text-gray-400">Loading…</p>}

              {!loading && reviews.length === 0 && (
                <div className="text-xs text-gray-400 bg-white border border-dashed border-gray-200 rounded-xl p-8 text-center">
                  No reviews yet. Generate a content package or submit a review.
                </div>
              )}

              {reviews.map((r) => (
                <ReviewCard
                  key={r.review_id}
                  review={r}
                  selected={selectedReview?.review_id === r.review_id}
                  onClick={() => setSelectedReview(r)}
                />
              ))}
            </div>

            {/* Scoring panel */}
            <div>
              {selectedReview ? (
                <div className="space-y-3">
                  <p className="text-xs text-gray-500">
                    Editing: <span className="font-mono text-gray-700">{selectedReview.review_id}</span>
                  </p>
                  <OutputQualityReviewPanel
                    workspaceSlug={workspaceSlug}
                    reviewId={selectedReview.review_id}
                    contentType={selectedReview.content_type}
                    contentText={selectedReview.content_text}
                    memoryVersion={selectedReview.memory_version}
                    onSubmit={() => { load(); setSelectedReview(null); }}
                  />
                </div>
              ) : (
                <div className="bg-white border border-dashed border-gray-200 rounded-xl p-6 text-center text-xs text-gray-400">
                  Select a review to score it.
                  <div className="mt-4">
                    <OutputQualityReviewPanel
                      workspaceSlug={workspaceSlug}
                      contentType="linkedin_post"
                      contentText=""
                      onSubmit={() => load()}
                      compact
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ─ Publish-ready tab ─ */}
        {tab === "publish" && (
          <div className="space-y-3">
            <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <Send className="w-4 h-4 text-indigo-600" />
              Publish-Ready Content ({publishReady.length})
            </h2>
            {publishReady.length === 0 && (
              <div className="text-xs text-gray-400 bg-white border border-dashed border-gray-200 rounded-xl p-8 text-center">
                No publish-ready items yet. Score content with avg ≥ 3.5 to unlock.
              </div>
            )}
            {publishReady.map((r) => (
              <div key={r.review_id} className="bg-white border border-green-200 rounded-xl p-4 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-gray-700">
                    {r.content_type?.replace(/_/g, " ")}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <CheckCircle className="w-3.5 h-3.5 text-green-600" />
                    <span className="text-xs text-green-700 font-semibold">{r.avg_score?.toFixed(1)}</span>
                    <span className="text-xs text-gray-400 font-mono">{r.review_id}</span>
                  </div>
                </div>
                <p className="text-xs text-gray-600 line-clamp-3">{r.content_text}</p>
              </div>
            ))}
          </div>
        )}

        {/* ─ Metrics tab ─ */}
        {tab === "metrics" && (
          <div className="space-y-4">
            <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <BarChart2 className="w-4 h-4 text-indigo-600" />
              Quality Metrics
            </h2>
            {metrics ? (
              <MetricsDashboard metrics={metrics} />
            ) : (
              <p className="text-xs text-gray-400">Loading metrics…</p>
            )}
          </div>
        )}

        {/* ─ Generate tab ─ */}
        {tab === "generate" && (
          <div className="max-w-lg space-y-4">
            <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <Package className="w-4 h-4 text-indigo-600" />
              Generate Content Package
            </h2>
            <p className="text-xs text-gray-500">
              Generates a full John Maxwell content package: 5 LinkedIn posts, 5 hooks,
              3 video concepts, 3 outreach angles, 1 campaign summary (17 items total).
            </p>
            <button
              onClick={generatePackage}
              disabled={generating}
              className="w-full text-sm font-medium bg-indigo-600 text-white rounded-xl py-3 hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {generating ? "Generating…" : "Generate Full Content Package"}
            </button>
            {genResult && (
              <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-xs space-y-1 text-green-800">
                <p className="font-semibold">Package generated ✓</p>
                <p>Package ID: <span className="font-mono">{genResult.package_id}</span></p>
                <p>Total items: <strong>{genResult.total_items}</strong></p>
                <div className="pt-1 grid grid-cols-2 gap-1">
                  {Object.entries(genResult.item_counts || {}).map(([k, v]) => (
                    <span key={k} className="bg-green-100 rounded px-2 py-0.5">
                      {k.replace(/_/g, " ")}: {v}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}


// ── Review card ───────────────────────────────────────────────────────────────

function ReviewCard({ review, selected, onClick }) {
  const {
    review_id,
    content_type,
    avg_score,
    approved,
    publish_ready,
    revision_requested,
    memory_version,
    content_text,
  } = review;

  return (
    <button
      onClick={onClick}
      className={`w-full text-left bg-white border rounded-xl p-4 hover:border-indigo-300 transition-colors space-y-1 ${
        selected ? "border-indigo-400 ring-1 ring-indigo-300" : "border-gray-200"
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-700">
          {content_type?.replace(/_/g, " ")}
          {memory_version > 0 && (
            <span className="ml-1.5 text-purple-600 text-[10px] bg-purple-50 rounded px-1">
              mem v{memory_version}
            </span>
          )}
        </span>
        <div className="flex items-center gap-2">
          {publish_ready && <Send className="w-3 h-3 text-indigo-500" />}
          {approved     && <CheckCircle className="w-3 h-3 text-green-500" />}
          {revision_requested && <span className="text-[10px] text-red-600 bg-red-50 rounded px-1">revision</span>}
          <span className={`text-xs font-bold ${
            avg_score >= 3.5 ? "text-green-700" : avg_score >= 2.5 ? "text-yellow-700" : "text-red-700"
          }`}>
            {avg_score?.toFixed(1)}
          </span>
        </div>
      </div>
      <p className="text-xs text-gray-500 line-clamp-2">{content_text}</p>
      <p className="text-[10px] text-gray-300 font-mono">{review_id}</p>
    </button>
  );
}


// ── Metrics dashboard widget ──────────────────────────────────────────────────

function MetricsDashboard({ metrics }) {
  const cards = [
    { label: "Total Reviews",      value: metrics.total_reviews,               color: "text-gray-800" },
    { label: "Approval Rate",      value: pct(metrics.approval_rate),          color: "text-green-700" },
    { label: "Revision Rate",      value: pct(metrics.revision_rate),          color: "text-red-600" },
    { label: "Publish-Ready Rate", value: pct(metrics.publish_ready_rate),     color: "text-indigo-700" },
    { label: "Avg Quality Score",  value: metrics.avg_quality_score?.toFixed(2), color: "text-gray-800" },
    { label: "Memory Δ",           value: delta(metrics.memory_improvement_delta), color: metrics.memory_improvement_delta > 0 ? "text-green-700" : "text-red-500" },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
      {cards.map(({ label, value, color }) => (
        <div key={label} className="bg-white border border-gray-200 rounded-xl p-4 space-y-1">
          <p className="text-xs text-gray-400">{label}</p>
          <p className={`text-xl font-bold ${color}`}>{value}</p>
        </div>
      ))}
      {metrics.evaluated_at && (
        <p className="col-span-full text-[10px] text-gray-300">
          Evaluated at {new Date(metrics.evaluated_at).toLocaleString()}
        </p>
      )}
    </div>
  );
}

function pct(val) {
  if (val == null) return "—";
  return `${(val * 100).toFixed(0)}%`;
}

function delta(val) {
  if (val == null) return "—";
  return val >= 0 ? `+${val.toFixed(3)}` : val.toFixed(3);
}
