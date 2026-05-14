import {
  approveDemoContentDraft,
  approveDemoMessage,
  demoItems,
  demoOverview,
  generateDemoSnippets,
  getDemoState,
  isDemoModeEnabled,
  resetDemoData,
  reviewDemoCreativeAsset,
  reviewDemoPromptGeneration,
  reviewDemoAssetRender,
  reviewDemoSnippet,
  runDemoOutreach,
  showDemoDealOutcome,
  simulateDemoResponse,
  startDemoMode,
  stopDemoMode,
} from "./demoMode.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// Module-level active workspace. "all" means no workspace filter is applied.
let _appWorkspace = "all";

export function setAppWorkspace(slug) {
  _appWorkspace = slug;
}

export function getAppWorkspace() {
  return _appWorkspace;
}

function wsParam() {
  return _appWorkspace !== "all" ? { workspace_slug: _appWorkspace } : {};
}

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: isFormData ? options.headers || {} : {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || `Request failed: ${response.status}`);
  }

  return response.json();
}

export const api = {
  health: () => request("/health"),
  gptRuntimeSettings: () => request("/settings/gpt-runtime"),
  gptDiagnostics: () => request("/diagnostics/gpt"),
  demoState: async () => getDemoState(),
  demoEnabled: isDemoModeEnabled,
  startDemo: async () => startDemoMode(),
  stopDemo: async () => stopDemoMode(),
  resetDemo: async () => resetDemoData(),
  runDemoOutreach: async () => runDemoOutreach(),
  simulateDemoResponse: async (id) => simulateDemoResponse(id),
  showDemoDealOutcome: async () => showDemoDealOutcome(),
  overview: () => (isDemoModeEnabled() ? Promise.resolve(demoOverview()) : request("/stats/overview")),
  contacts: (params = {}) => (isDemoModeEnabled() ? Promise.resolve({ items: demoItems("contacts") }) : request(`/contacts?${new URLSearchParams({ ...wsParam(), ...params })}`)),
  leads: (params = {}) => (isDemoModeEnabled() ? Promise.resolve({ items: demoItems("leads") }) : request(`/leads?${new URLSearchParams({ ...wsParam(), ...params })}`)),
  messages: (params = {}) => (isDemoModeEnabled() ? Promise.resolve({ items: demoItems("messages") }) : request(`/messages?${new URLSearchParams({ ...wsParam(), ...params })}`)),
  reviewMessage: (id, payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({ item: approveDemoMessage(id), message: "Demo approval saved. No message sent." })
      : request(`/messages/${encodeURIComponent(id)}/review`, {
          method: "POST",
          body: JSON.stringify(payload),
        }),
  approvalRequests: (params = {}) => request(`/approval-requests?${new URLSearchParams({ ...wsParam(), ...params })}`),
  decideApprovalRequest: (id, payload) =>
    request(`/approval-requests/${encodeURIComponent(id)}/decision`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  workflowAssets: (params = {}) => request(`/workflow-assets?${new URLSearchParams({ ...wsParam(), ...params })}`),
  decideWorkflowAsset: (id, payload) =>
    request(`/workflow-assets/${encodeURIComponent(id)}/decision`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  updateWorkflowAssetDistribution: (id, payload) =>
    request(`/workflow-assets/${encodeURIComponent(id)}/distribution`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  toolRuns: (params = {}) => request(`/tool-runs?${new URLSearchParams({ ...wsParam(), ...params })}`),
  runWebSearchTool: (payload) =>
    request("/tools/web-search", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  importCandidates: (formData) =>
    request("/tools/import-candidates", {
      method: "POST",
      body: formData,
    }),
  scrapedCandidates: (params = {}) => request(`/scraped-candidates?${new URLSearchParams({ ...wsParam(), ...params })}`),
  decideScrapedCandidate: (id, payload) =>
    request(`/scraped-candidates/${encodeURIComponent(id)}/decision`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  bulkCandidateAction: (payload) =>
    request("/scraped-candidates/bulk-action", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  importHistory: (params = {}) => request(`/tools/import-history?${new URLSearchParams(params)}`),
  importHistoryDetail: (runId, params = {}) =>
    request(`/tools/import-history/${encodeURIComponent(runId)}/candidates?${new URLSearchParams(params)}`),
  importHistoryErrors: (runId) => request(`/tools/import-history/${encodeURIComponent(runId)}/errors`),
  agentTasks: (params = {}) => request(`/agent-tasks?${new URLSearchParams({ ...wsParam(), ...params })}`),
  createAgentTask: (payload) =>
    request("/agent-tasks", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),
  runAgentTask: (id) =>
    request(`/agent-tasks/${encodeURIComponent(id)}/run`, {
      method: "POST",
    }),
  cancelAgentTask: (id) =>
    request(`/agent-tasks/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
    }),
  agents: () => request("/agents"),
  runAgent: (payload) =>
    request("/agents/run", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),
  agentRuns: (params = {}) => request(`/agent-runs?${new URLSearchParams({ ...wsParam(), ...params })}`),
  agentRunDetail: (id) => request(`/agent-runs/${encodeURIComponent(id)}`),
  deals: (params = {}) => (isDemoModeEnabled() ? Promise.resolve({ items: demoItems("deals") }) : request(`/deals?${new URLSearchParams({ ...wsParam(), ...params })}`)),
  reports: () => request("/reports"),
  workspaces: () => (isDemoModeEnabled() ? Promise.resolve({ items: demoItems("workspaces") }) : request("/workspaces")),
  getWorkspace: (slug) => request(`/workspaces/${encodeURIComponent(slug)}`),
  createWorkspace: (payload) =>
    request("/workspaces", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateWorkspaceStatus: (slug, status) =>
    request(`/workspaces/${encodeURIComponent(slug)}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  contentBriefs: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("content_briefs") })
      : request(`/content-briefs?${new URLSearchParams({ ...wsParam(), ...params })}`),
  createContentBrief: (payload) =>
    request("/content-briefs", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),
  contentDrafts: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("content_drafts") })
      : request(`/content-drafts?${new URLSearchParams({ ...wsParam(), ...params })}`),
  createContentDraft: (payload) =>
    request("/content-drafts", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),
  reviewContentDraft: (id, payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({ item: approveDemoContentDraft(id), message: "Demo review saved. No post published." })
      : request(`/content-drafts/${encodeURIComponent(id)}/review`, {
          method: "POST",
          body: JSON.stringify(payload),
        }),

  // -------------------------------------------------------------------------
  // Social Creative Engine v2
  // -------------------------------------------------------------------------
  clientProfiles: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("client_profiles") })
      : request(`/client-profiles?${new URLSearchParams({ ...wsParam(), ...params })}`),
  createClientProfile: (payload) =>
    request("/client-profiles", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  sourceChannels: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("source_channels") })
      : request(`/source-channels?${new URLSearchParams({ ...wsParam(), ...params })}`),
  createSourceChannel: (payload) =>
    request("/source-channels", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  sourceContent: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("source_content") })
      : request(`/source-content?${new URLSearchParams({ ...wsParam(), ...params })}`),
  createSourceContent: (payload) =>
    request("/source-content", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  contentTranscripts: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("content_transcripts") })
      : request(`/content-transcripts?${new URLSearchParams({ ...wsParam(), ...params })}`),

  contentSnippets: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("content_snippets") })
      : request(`/content-snippets?${new URLSearchParams({ ...wsParam(), ...params })}`),
  reviewContentSnippet: (id, payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({
          item: reviewDemoSnippet(id, payload.decision, payload.note),
          message: "Demo snippet review saved. No post published.",
          simulation_only: true,
        })
      : request(`/content-snippets/${encodeURIComponent(id)}/review`, {
          method: "POST",
          body: JSON.stringify(payload),
        }),

  scoreContentSnippet: (id) =>
    isDemoModeEnabled()
      ? Promise.resolve({
          item: { _id: id, overall_score: 7.5, hook_type: "bold_statement", simulation_only: true },
          message: "Demo snippet scored. No post published.",
          simulation_only: true,
        })
      : request(`/content-snippets/${encodeURIComponent(id)}/score`, {
          method: "POST",
        }),

  creativeAssets: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("creative_assets") })
      : request(`/creative-assets?${new URLSearchParams({ ...wsParam(), ...params })}`),
  reviewCreativeAsset: (id, payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({
          item: reviewDemoCreativeAsset(id, payload.decision, payload.note),
          message: "Demo asset review saved. No post published.",
          simulation_only: true,
        })
      : request(`/creative-assets/${encodeURIComponent(id)}/review`, {
          method: "POST",
          body: JSON.stringify(payload),
        }),

  creativeToolRuns: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: [], simulation_only: true })
      : request(`/creative-tool-runs?${new URLSearchParams({ ...wsParam(), ...params })}`),

  // -------------------------------------------------------------------------
  // Social Creative Engine v3
  // -------------------------------------------------------------------------
  updateSourceContentMetadata: (id, payload) =>
    request(`/source-content/${encodeURIComponent(id)}/metadata`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  audioExtractionRuns: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("audio_extraction_runs"), simulation_only: true })
      : request(`/audio-extraction-runs?${new URLSearchParams({ ...wsParam(), ...params })}`),
  createAudioExtractionRun: (payload) =>
    request("/audio-extraction-runs", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  transcriptRuns: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("transcript_runs"), simulation_only: true })
      : request(`/transcript-runs?${new URLSearchParams({ ...wsParam(), ...params })}`),
  createTranscriptRun: (payload) =>
    request("/transcript-runs", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  transcriptSegments: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("transcript_segments"), simulation_only: true })
      : request(`/transcript-segments?${new URLSearchParams({ ...wsParam(), ...params })}`),

  generateSnippets: (sourceContentId, payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({
          items: generateDemoSnippets(sourceContentId),
          simulation_only: true,
          message: "Demo snippet candidates created. No post published.",
        })
      : request(`/source-content/${encodeURIComponent(sourceContentId)}/generate-snippets`, {
          method: "POST",
          body: JSON.stringify({ ...wsParam(), ...payload }),
        }),

  // -------------------------------------------------------------------------
  // Social Creative Engine v4
  // -------------------------------------------------------------------------
  updateSourceContentStatus: (id, payload) =>
    request(`/source-content/${encodeURIComponent(id)}/status`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  mediaIntakeRecords: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("media_intake_records"), simulation_only: true })
      : request(`/media-intake-records?${new URLSearchParams({ ...wsParam(), ...params })}`),
  createMediaIntakeRecord: (payload) =>
    request("/media-intake-records", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  // v10.4 — Media Folder Scans
  mediaFolderScans: (params = {}) =>
    request(`/media-folder-scans?${new URLSearchParams({ ...wsParam(), ...params })}`),
  createMediaFolderScan: (payload) =>
    request("/media-folder-scans", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),
  getMediaFolderScan: (id) =>
    request(`/media-folder-scans/${id}`),

  // v10.4 — Approved URL Downloads
  approvedUrlDownloads: (params = {}) =>
    request(`/approved-url-downloads?${new URLSearchParams({ ...wsParam(), ...params })}`),
  createApprovedUrlDownload: (payload) =>
    request("/approved-url-downloads", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),
  getApprovedUrlDownload: (id) =>
    request(`/approved-url-downloads/${id}`),

  // v10.4 — Diagnostics
  mediaIngestionDiagnostics: () =>
    request("/media-ingestion/diagnostics"),

  // Phase 11 — Renderer Validation
  rendererValidationRuns: (params = {}) =>
    request(`/renderer-validation-runs?${new URLSearchParams({ ...wsParam(), ...params })}`),
  createRendererValidationRun: (payload) =>
    request("/renderer-validation-runs", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),
  reviewRendererValidationRun: (id, payload) =>
    request(`/renderer-validation-runs/${id}/review`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  rendererValidationDiagnostics: () =>
    request("/renderer-validation/diagnostics"),

  createAudioExtractionRunV4: (payload) =>
    request("/audio-extraction-runs/v4", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  createTranscriptRunV4: (payload) =>
    request("/transcript-runs/v4", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  generateSnippetsV4: (sourceContentId, payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({
          items: generateDemoSnippets(sourceContentId),
          simulation_only: true,
          message: "Demo snippet candidates created (v4). No post published.",
        })
      : request(
          `/source-content/${encodeURIComponent(sourceContentId)}/generate-snippets/v4`,
          {
            method: "POST",
            body: JSON.stringify({ ...wsParam(), ...payload }),
          },
        ),

  // --- Social Creative Engine v4.5 ---
  promptGenerations: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("prompt_generations"), simulation_only: true })
      : request(`/prompt-generations?${new URLSearchParams({ ...wsParam(), ...params })}`),

  createPromptGeneration: (payload) =>
    request("/prompt-generations", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  reviewPromptGeneration: (id, payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({
          item: reviewDemoPromptGeneration(id, payload.decision, payload.note),
          message: "Demo review saved.",
        })
      : request(`/prompt-generations/${encodeURIComponent(id)}/review`, {
          method: "POST",
          body: JSON.stringify(payload),
        }),

  // --- Social Creative Engine v5 ---
  assetRenders: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("asset_renders"), simulation_only: true })
      : request(`/assets?${new URLSearchParams({ ...wsParam(), ...params })}`),

  createAssetRender: (payload) =>
    request("/assets/render", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  reviewAssetRender: (id, payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({
          item: reviewDemoAssetRender(id, payload.decision, payload.note),
          message: "Demo asset render review saved. No post published.",
          simulation_only: true,
        })
      : request(`/assets/${encodeURIComponent(id)}/review`, {
          method: "POST",
          body: JSON.stringify(payload),
        }),

  // --- Social Creative Engine v7.5 ---
  manualPublishLogs: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("manual_publish_logs"), simulation_only: true })
      : request(`/manual-publish-logs?${new URLSearchParams({ ...wsParam(), ...params })}`),

  createManualPublishLog: (payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({ item: { ...payload, _id: "demo-publog-new", simulation_only: true, outbound_actions_taken: 0, is_demo: true }, message: "Demo publish log recorded. SignalForge did not publish or schedule anything.", simulation_only: true })
      : request("/manual-publish-logs", {
          method: "POST",
          body: JSON.stringify({ ...wsParam(), ...payload }),
        }),

  assetPerformanceRecords: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("asset_performance_records"), simulation_only: true })
      : request(`/asset-performance-records?${new URLSearchParams({ ...wsParam(), ...params })}`),

  createAssetPerformanceRecord: (payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({ item: { ...payload, _id: "demo-perf-new", simulation_only: true, outbound_actions_taken: 0, is_demo: true }, message: "Demo performance record stored. Advisory only.", simulation_only: true })
      : request("/asset-performance-records", {
          method: "POST",
          body: JSON.stringify({ ...wsParam(), ...payload }),
        }),

  importPerformanceCSV: (payload) =>
    request("/asset-performance-records/import-csv", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  creativePerformanceSummaries: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("creative_performance_summaries"), simulation_only: true })
      : request(`/creative-performance-summaries?${new URLSearchParams({ ...wsParam(), ...params })}`),

  generateCreativePerformanceSummary: (payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({ item: (demoItems("creative_performance_summaries")[0] || {}), message: "Demo summary generated. Recommendations are advisory only.", simulation_only: true })
      : request("/creative-performance-summaries/generate", {
          method: "POST",
          body: JSON.stringify({ ...wsParam(), ...payload }),
        }),

  performanceRecommendations: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: (demoItems("creative_performance_summaries")[0] || {}).recommendations || [], simulation_only: true })
      : request(`/creative-performance-summaries/recommendations?${new URLSearchParams({ ...wsParam(), ...params })}`),

  // v8: Campaign Packs
  campaignPacks: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("campaign_packs"), simulation_only: true })
      : request(`/campaign-packs?${new URLSearchParams({ ...wsParam(), ...params })}`),

  createCampaignPack: (payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({ item: { ...payload, _id: "demo-pack-new", status: "draft", simulation_only: true, outbound_actions_taken: 0, is_demo: true }, message: "Demo campaign pack created.", simulation_only: true })
      : request("/campaign-packs", {
          method: "POST",
          body: JSON.stringify({ ...wsParam(), ...payload }),
        }),

  getCampaignPack: (id) =>
    isDemoModeEnabled()
      ? Promise.resolve({ item: demoItems("campaign_packs").find((p) => p._id === id) || {} })
      : request(`/campaign-packs/${id}`),

  addCampaignPackItem: (packId, payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({ message: "Demo item added to pack. No external actions.", simulation_only: true })
      : request(`/campaign-packs/${packId}/items`, {
          method: "POST",
          body: JSON.stringify({ ...wsParam(), ...payload }),
        }),

  generateCampaignReport: (packId) =>
    isDemoModeEnabled()
      ? Promise.resolve({ item: (demoItems("campaign_reports")[0] || {}), message: "Demo report generated. Advisory only.", simulation_only: true })
      : request(`/campaign-packs/${packId}/generate-report`, { method: "POST", body: "{}" }),

  campaignReports: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("campaign_reports"), simulation_only: true })
      : request(`/campaign-reports?${new URLSearchParams({ ...wsParam(), ...params })}`),

  reviewCampaignReport: (reportId, payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({ item: { ...(demoItems("campaign_reports").find((r) => r._id === reportId) || {}), status: payload.decision === "approve" ? "approved" : "rejected", simulation_only: true }, message: "Demo report review saved.", simulation_only: true })
      : request(`/campaign-reports/${reportId}/review`, {
          method: "POST",
          body: JSON.stringify({ ...wsParam(), ...payload }),
        }),

  // v8.5: Campaign Exports
  campaignExports: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("campaign_exports"), simulation_only: true })
      : request(`/campaign-exports?${new URLSearchParams({ ...wsParam(), ...params })}`),

  createCampaignExport: (payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({ item: { ...payload, _id: "demo-export-new", export_path: "/tmp/signalforge_exports/demo/export_demo.md", simulation_only: true, outbound_actions_taken: 0, is_demo: true }, message: "Demo export generated locally. No uploading or publishing.", simulation_only: true })
      : request("/campaign-exports", {
          method: "POST",
          body: JSON.stringify({ ...wsParam(), ...payload }),
        }),

  getCampaignExport: (id) =>
    isDemoModeEnabled()
      ? Promise.resolve({ item: demoItems("campaign_exports").find((e) => e._id === id) || {} })
      : request(`/campaign-exports/${id}`),

  reviewCampaignExport: (exportId, payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({ item: { ...(demoItems("campaign_exports").find((e) => e._id === exportId) || {}), status: "reviewed", simulation_only: true }, message: "Demo export review saved.", simulation_only: true })
      : request(`/campaign-exports/${exportId}/review`, {
          method: "POST",
          body: JSON.stringify({ ...wsParam(), ...payload }),
        }),

  // v9.5: Client Intelligence Layer
  clientIntelligence: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("client_intelligence"), simulation_only: true })
      : request(`/client-intelligence?${new URLSearchParams({ ...wsParam(), ...params })}`),

  getClientIntelligence: (clientId) =>
    isDemoModeEnabled()
      ? Promise.resolve({ item: demoItems("client_intelligence").find((r) => r.client_id === clientId) || demoItems("client_intelligence")[0] || {}, simulation_only: true })
      : request(`/client-intelligence/${clientId}?${new URLSearchParams({ ...wsParam() })}`),

  generateClientIntelligence: (clientId, payload = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ item: { ...(demoItems("client_intelligence")[0] || {}), simulation_only: true, advisory_only: true, outbound_actions_taken: 0 }, message: "Demo client intelligence generated. Advisory only. No external actions performed.", simulation_only: true })
      : request(`/client-intelligence/${clientId}/generate`, {
          method: "POST",
          body: JSON.stringify({ ...wsParam(), ...payload }),
        }),

  leadContentCorrelations: (params = {}) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("lead_content_correlations"), simulation_only: true })
      : request(`/lead-content-correlations?${new URLSearchParams({ ...wsParam(), ...params })}`),

  generateLeadContentCorrelations: (payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({ items: demoItems("lead_content_correlations"), message: "Demo correlations generated. Advisory only. No external actions performed.", simulation_only: true })
      : request("/lead-content-correlations/generate", {
          method: "POST",
          body: JSON.stringify({ ...wsParam(), ...payload }),
        }),

  patchClientProfileIntelligence: (clientId, payload) =>
    request(`/client-profiles/${clientId}/intelligence`, {
      method: "PATCH",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  linkCampaignPack: (packId, payload) =>
    request(`/campaign-packs/${packId}/link`, {
      method: "PATCH",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  patchAssetPerformanceIntelligence: (recordId, payload) =>
    request(`/asset-performance-records/${recordId}/intelligence`, {
      method: "PATCH",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  // ── Phase 6A: Admin Client Profiles ────────────────────────────────────
  clientProfiles: (params = {}) =>
    request(`/admin/client-profiles?${new URLSearchParams(params)}`),

  createClientProfile: (payload) =>
    request("/admin/client-profiles", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateClientProfile: (slug, payload) =>
    request(`/admin/client-profiles/${encodeURIComponent(slug)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  updateClientProfileStatus: (slug, status) =>
    request(`/admin/client-profiles/${encodeURIComponent(slug)}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),

  clientProfileWorkflowDefinition: (slug) =>
    request(`/admin/client-profiles/${encodeURIComponent(slug)}/workflow-definition`),

  getAdminClientProfile: (slug) =>
    request(`/admin/client-profiles/${encodeURIComponent(slug)}`),

  getAdminWorkflowDefinition: (slug) =>
    request(`/admin/workflow-definitions/${encodeURIComponent(slug)}`),

  // ── Phase 6A: Admin Workflow Definitions ────────────────────────────────
  workflowDefinitions: (params = {}) =>
    request(`/admin/workflow-definitions?${new URLSearchParams(params)}`),

  createWorkflowDefinition: (payload) =>
    request("/admin/workflow-definitions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateWorkflowDefinition: (slug, payload) =>
    request(`/admin/workflow-definitions/${encodeURIComponent(slug)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  // ── Phase 6C: Discovery Insights ─────────────────────────────────────────
  discoveryInsights: (params = {}) =>
    request(`/discovery-insights?${new URLSearchParams(params)}`),

  getDiscoveryInsight: (id) =>
    request(`/discovery-insights/${encodeURIComponent(id)}`),

  createDiscoveryInsight: (payload) =>
    request("/discovery-insights", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateDiscoveryInsight: (id, payload) =>
    request(`/discovery-insights/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  updateDiscoveryInsightStatus: (id, status) =>
    request(`/discovery-insights/${encodeURIComponent(id)}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),

  linkAssetToInsight: (assetId, insightId) =>
    request(`/workflow-assets/${encodeURIComponent(assetId)}/link-insight`, {
      method: "PATCH",
      body: JSON.stringify({ source_discovery_insight_id: insightId }),
    }),

  // Phase 6D: discovery engine
  triggerDiscoveryInsights: (payload) =>
    request("/discovery-insights/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  generateAssetsFromInsight: (insightId) =>
    request(`/discovery-insights/${encodeURIComponent(insightId)}/generate-assets`, {
      method: "POST",
    }),

  // Phase 6E: client source registry
  clientSources: (params = {}) =>
    request(`/admin/client-sources?${new URLSearchParams(params)}`),
  createClientSource: (payload) =>
    request("/admin/client-sources", { method: "POST", body: JSON.stringify(payload) }),
  updateClientSource: (id, payload) =>
    request(`/admin/client-sources/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteClientSource: (id) =>
    request(`/admin/client-sources/${encodeURIComponent(id)}`, { method: "DELETE" }),

  // Phase 6F: discovery run summaries
  discoveryRunSummaries: (workspaceSlug) =>
    request(`/discovery-run-summaries?workspace_slug=${encodeURIComponent(workspaceSlug || "")}&limit=20`),
  getDiscoveryRunSummary: (runId) =>
    request(`/discovery-run-summaries/${encodeURIComponent(runId)}`),
  createDiscoveryRunSummary: (payload) =>
    request("/discovery-run-summaries", { method: "POST", body: JSON.stringify(payload) }),
  updateDiscoveryRunSummary: (runId, payload) =>
    request(`/discovery-run-summaries/${encodeURIComponent(runId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  // Phase 6H: workflow runs (structured execution layer)
  workflowRuns: ({ workspaceSlug = "", workflowStage = 0, runType = "", status = "", limit = 50 } = {}) => {
    const params = new URLSearchParams();
    if (workspaceSlug) params.set("workspace_slug", workspaceSlug);
    if (workflowStage) params.set("workflow_stage", String(workflowStage));
    if (runType) params.set("run_type", runType);
    if (status) params.set("status", status);
    params.set("limit", String(limit));
    return request(`/workflow-runs?${params.toString()}`);
  },
  getWorkflowRun: (runId) =>
    request(`/workflow-runs/${encodeURIComponent(runId)}`),
  createWorkflowRun: (payload) =>
    request("/workflow-runs", { method: "POST", body: JSON.stringify(payload) }),
  patchWorkflowRun: (runId, payload) =>
    request(`/workflow-runs/${encodeURIComponent(runId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  // Phase 6N: memory context snapshot frozen at run time
  workflowRunMemoryContext: (runId) =>
    request(`/workflow-runs/${encodeURIComponent(runId)}/memory-context`),

  // Phase 6M: Adaptive Client Operating Memory & Template Recommendation
  foundationTemplates: () => request("/foundation-templates"),
  getFoundationTemplate: (slug) => request(`/foundation-templates/${encodeURIComponent(slug)}`),

  recommendTemplate: (payload) =>
    request("/template-recommendation", { method: "POST", body: JSON.stringify(payload) }),

  clientMemories: ({ workspaceSlug = "", clientProfileId = "", limit = 20 } = {}) => {
    const params = new URLSearchParams();
    if (workspaceSlug) params.set("workspace_slug", workspaceSlug);
    if (clientProfileId) params.set("client_profile_id", clientProfileId);
    params.set("limit", String(limit));
    return request(`/client-memory?${params.toString()}`);
  },
  createClientMemory: (payload) =>
    request("/client-memory", { method: "POST", body: JSON.stringify(payload) }),
  updateClientMemory: (memoryId, payload) =>
    request(`/client-memory/${encodeURIComponent(memoryId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  clientMemoryBrief: (memoryId) =>
    request(`/client-memory/${encodeURIComponent(memoryId)}/brief`),

  memoryUpdateProposals: ({ workspaceSlug = "", clientMemoryId = "", status = "", limit = 50 } = {}) => {
    const params = new URLSearchParams();
    if (workspaceSlug) params.set("workspace_slug", workspaceSlug);
    if (clientMemoryId) params.set("client_memory_id", clientMemoryId);
    if (status) params.set("status", status);
    params.set("limit", String(limit));
    return request(`/memory-update-proposals?${params.toString()}`);
  },
  createMemoryUpdateProposal: (payload) =>
    request("/memory-update-proposals", { method: "POST", body: JSON.stringify(payload) }),
  decideMemoryUpdateProposal: (proposalId, payload) =>
    request(`/memory-update-proposals/${encodeURIComponent(proposalId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  // Phase 6O: Memory Governance, History & Health
  clientMemoryHistory: (memoryId, limit = 50) =>
    request(`/client-memory/${encodeURIComponent(memoryId)}/history?limit=${limit}`),
  clientMemoryHealth: (memoryId) =>
    request(`/client-memory/${encodeURIComponent(memoryId)}/health`),
  rollbackClientMemory: (memoryId, payload) =>
    request(`/client-memory/${encodeURIComponent(memoryId)}/rollback`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  proposalDiff: (proposalId) =>
    request(`/memory-update-proposals/${encodeURIComponent(proposalId)}/diff`),
  proposalConflicts: (proposalId) =>
    request(`/memory-update-proposals/${encodeURIComponent(proposalId)}/conflicts`),

  // Phase 6P: Operational Analytics & Learning Dashboard
  analyticsWorkflows: (workspaceSlug = "", days = 30) =>
    request(`/analytics/workflows?workspace_slug=${encodeURIComponent(workspaceSlug)}&days=${days}`),
  analyticsMemory: (workspaceSlug = "", days = 30) =>
    request(`/analytics/memory?workspace_slug=${encodeURIComponent(workspaceSlug)}&days=${days}`),
  analyticsDistribution: (workspaceSlug = "", days = 30) =>
    request(`/analytics/distribution?workspace_slug=${encodeURIComponent(workspaceSlug)}&days=${days}`),
  analyticsApprovals: (workspaceSlug = "", days = 30) =>
    request(`/analytics/approvals?workspace_slug=${encodeURIComponent(workspaceSlug)}&days=${days}`),
  analyticsTemplates: (workspaceSlug = "", days = 30) =>
    request(`/analytics/templates?workspace_slug=${encodeURIComponent(workspaceSlug)}&days=${days}`),
  analyticsClientHealth: (workspaceSlug = "", days = 30) =>
    request(`/analytics/client-health?workspace_slug=${encodeURIComponent(workspaceSlug)}&days=${days}`),
  analyticsLearningSignals: (workspaceSlug = "", days = 30) =>
    request(`/analytics/learning-signals?workspace_slug=${encodeURIComponent(workspaceSlug)}&days=${days}`),
  analyticsBottlenecks: (workspaceSlug = "", days = 30) =>
    request(`/analytics/bottlenecks?workspace_slug=${encodeURIComponent(workspaceSlug)}&days=${days}`),

  // Phase 6Q: Autonomous Optimization & Recommendation Engine
  listRecommendations: (workspaceSlug = "", days = 30, status = "", recType = "") => {
    const p = new URLSearchParams();
    if (workspaceSlug) p.set("workspace_slug", workspaceSlug);
    p.set("days", String(days));
    if (status) p.set("status", status);
    if (recType) p.set("rec_type", recType);
    return request(`/recommendations?${p.toString()}`);
  },
  getRecommendation: (recId, workspaceSlug = "", days = 30) =>
    request(`/recommendations/${encodeURIComponent(recId)}?workspace_slug=${encodeURIComponent(workspaceSlug)}&days=${days}`),
  acceptRecommendation: (recId) =>
    request(`/recommendations/${encodeURIComponent(recId)}/accept`, { method: "POST" }),
  dismissRecommendation: (recId) =>
    request(`/recommendations/${encodeURIComponent(recId)}/dismiss`, { method: "POST" }),
  applyRecommendation: (recId) =>
    request(`/recommendations/${encodeURIComponent(recId)}/apply`, { method: "POST" }),
  recommendationsSummary: (workspaceSlug = "", days = 30) =>
    request(`/recommendations/summary?workspace_slug=${encodeURIComponent(workspaceSlug)}&days=${days}`),
  crossClientSignals: (days = 30) =>
    request(`/recommendations/cross-client-signals?days=${days}`),

  // Phase 6R: Autonomous Execution Policies & Safe Auto-Optimization
  getAutonomyPolicies: (workspaceSlug = "") =>
    request(`/autonomy/policies${workspaceSlug ? `?workspace_slug=${encodeURIComponent(workspaceSlug)}` : ""}`),
  updateAutonomyPolicy: (workspace, body) =>
    request(`/autonomy/policies/${encodeURIComponent(workspace)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  listAutonomyActions: (workspaceSlug = "", status = "", actionType = "", limit = 50) => {
    const p = new URLSearchParams();
    if (workspaceSlug) p.set("workspace_slug", workspaceSlug);
    if (status) p.set("status", status);
    if (actionType) p.set("action_type", actionType);
    p.set("limit", String(limit));
    return request(`/autonomy/actions?${p.toString()}`);
  },
  getAutonomyAction: (actionId) =>
    request(`/autonomy/actions/${encodeURIComponent(actionId)}`),
  rollbackAutonomyAction: (actionId) =>
    request(`/autonomy/actions/${encodeURIComponent(actionId)}/rollback`, { method: "POST" }),
  pauseAutonomy: () =>
    request("/autonomy/pause", { method: "POST" }),
  resumeAutonomy: () =>
    request("/autonomy/resume", { method: "POST" }),
  getAutonomyAnalytics: (workspaceSlug = "", days = 30) =>
    request(`/autonomy/analytics?workspace_slug=${encodeURIComponent(workspaceSlug)}&days=${days}`),

  // Phase 6T: Multi-Agent Coordination & Autonomous Workflow Orchestration
  createOrchestration: (body) =>
    request("/orchestrations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  listOrchestrations: (workspaceSlug = "", status = "", priority = "", limit = 50) =>
    request(`/orchestrations?workspace_slug=${encodeURIComponent(workspaceSlug)}&status=${encodeURIComponent(status)}&priority=${encodeURIComponent(priority)}&limit=${limit}`),
  getOrchestrationGlobalTelemetry: (workspaceSlug = "", days = 30) =>
    request(`/orchestrations/telemetry?workspace_slug=${encodeURIComponent(workspaceSlug)}&days=${days}`),
  getOrchestration: (orchId) =>
    request(`/orchestrations/${encodeURIComponent(orchId)}`),
  getOrchestrationGraph: (orchId) =>
    request(`/orchestrations/${encodeURIComponent(orchId)}/graph`),
  getOrchestrationTelemetry: (orchId) =>
    request(`/orchestrations/${encodeURIComponent(orchId)}/telemetry`),
  pauseOrchestration: (orchId) =>
    request(`/orchestrations/${encodeURIComponent(orchId)}/pause`, { method: "POST" }),
  resumeOrchestration: (orchId) =>
    request(`/orchestrations/${encodeURIComponent(orchId)}/resume`, { method: "POST" }),
  retryOrchestrationNode: (orchId, body) =>
    request(`/orchestrations/${encodeURIComponent(orchId)}/retry-node`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  escalateOrchestration: (orchId, body) =>
    request(`/orchestrations/${encodeURIComponent(orchId)}/escalate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  listAgentProfiles: () =>
    request("/agents/profiles"),
  getAgentUtilization: (workspaceSlug = "", days = 30) =>
    request(`/agents/utilization?workspace_slug=${encodeURIComponent(workspaceSlug)}&days=${days}`),
};

export { API_BASE_URL };

// ── Phase 6U: Production Hardening API functions ──────────────────────────────
export function getSystemHealthDetailed() {
  return request("/system/health/detailed");
}
export function getSystemMetrics() {
  return request("/system/metrics");
}
export function getSystemTelemetry() {
  return request("/system/telemetry");
}
export function getSystemIndexes() {
  return request("/system/indexes");
}
export function getSystemAuditLog(limit = 50) {
  return request(`/system/audit-log?limit=${limit}`);
}
export function postSystemResetMetrics() {
  return request("/system/reset-metrics", { method: "POST" });
}
export function getWorkersHealth() {
  return request("/workers/health");
}
export function getWorkersQueueDepth() {
  return request("/workers/queue-depth");
}
export function postWorkerHeartbeat(body) {
  return request("/workers/heartbeat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
export function postWorkersRecoverOrphaned() {
  return request("/workers/recover-orphaned", { method: "POST" });
}
export function postAuthToken(apiKey, workspaceSlug = "") {
  return request("/auth/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey, workspace_slug: workspaceSlug }),
  });
}
