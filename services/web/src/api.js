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
  workspaces: () => (isDemoModeEnabled() ? Promise.resolve({ items: [] }) : request("/workspaces")),
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
    request(`/manual-publish-logs?${new URLSearchParams({ ...wsParam(), ...params })}`),

  createManualPublishLog: (payload) =>
    request("/manual-publish-logs", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  assetPerformanceRecords: (params = {}) =>
    request(`/asset-performance-records?${new URLSearchParams({ ...wsParam(), ...params })}`),

  createAssetPerformanceRecord: (payload) =>
    request("/asset-performance-records", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  importPerformanceCSV: (payload) =>
    request("/asset-performance-records/import-csv", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  creativePerformanceSummaries: (params = {}) =>
    request(`/creative-performance-summaries?${new URLSearchParams({ ...wsParam(), ...params })}`),

  generateCreativePerformanceSummary: (payload) =>
    request("/creative-performance-summaries/generate", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  performanceRecommendations: (params = {}) =>
    request(`/creative-performance-summaries/recommendations?${new URLSearchParams({ ...wsParam(), ...params })}`),

  // v8: Campaign Packs
  campaignPacks: (params = {}) =>
    request(`/campaign-packs?${new URLSearchParams({ ...wsParam(), ...params })}`),

  createCampaignPack: (payload) =>
    request("/campaign-packs", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  getCampaignPack: (id) =>
    request(`/campaign-packs/${id}`),

  addCampaignPackItem: (packId, payload) =>
    request(`/campaign-packs/${packId}/items`, {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  generateCampaignReport: (packId) =>
    request(`/campaign-packs/${packId}/generate-report`, { method: "POST", body: "{}" }),

  campaignReports: (params = {}) =>
    request(`/campaign-reports?${new URLSearchParams({ ...wsParam(), ...params })}`),

  reviewCampaignReport: (reportId, payload) =>
    request(`/campaign-reports/${reportId}/review`, {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  // v8.5: Campaign Exports
  campaignExports: (params = {}) =>
    request(`/campaign-exports?${new URLSearchParams({ ...wsParam(), ...params })}`),

  createCampaignExport: (payload) =>
    request("/campaign-exports", {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),

  getCampaignExport: (id) =>
    request(`/campaign-exports/${id}`),

  reviewCampaignExport: (exportId, payload) =>
    request(`/campaign-exports/${exportId}/review`, {
      method: "POST",
      body: JSON.stringify({ ...wsParam(), ...payload }),
    }),
};

export { API_BASE_URL };
