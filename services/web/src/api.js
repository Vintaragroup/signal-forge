import {
  approveDemoMessage,
  demoItems,
  demoOverview,
  getDemoState,
  isDemoModeEnabled,
  runDemoOutreach,
  showDemoDealOutcome,
  simulateDemoResponse,
  startDemoMode,
  stopDemoMode,
} from "./demoMode.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
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
  runDemoOutreach: async () => runDemoOutreach(),
  simulateDemoResponse: async (id) => simulateDemoResponse(id),
  showDemoDealOutcome: async () => showDemoDealOutcome(),
  overview: () => (isDemoModeEnabled() ? Promise.resolve(demoOverview()) : request("/stats/overview")),
  contacts: (params = {}) => (isDemoModeEnabled() ? Promise.resolve({ items: demoItems("contacts") }) : request(`/contacts?${new URLSearchParams(params)}`)),
  leads: (params = {}) => (isDemoModeEnabled() ? Promise.resolve({ items: demoItems("leads") }) : request(`/leads?${new URLSearchParams(params)}`)),
  messages: (params = {}) => (isDemoModeEnabled() ? Promise.resolve({ items: demoItems("messages") }) : request(`/messages?${new URLSearchParams(params)}`)),
  reviewMessage: (id, payload) =>
    isDemoModeEnabled()
      ? Promise.resolve({ item: approveDemoMessage(id), message: "Demo approval saved. No message sent." })
      : request(`/messages/${encodeURIComponent(id)}/review`, {
          method: "POST",
          body: JSON.stringify(payload),
        }),
  approvalRequests: (params = {}) => request(`/approval-requests?${new URLSearchParams(params)}`),
  decideApprovalRequest: (id, payload) =>
    request(`/approval-requests/${encodeURIComponent(id)}/decision`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  agentTasks: (params = {}) => request(`/agent-tasks?${new URLSearchParams(params)}`),
  createAgentTask: (payload) =>
    request("/agent-tasks", {
      method: "POST",
      body: JSON.stringify(payload),
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
      body: JSON.stringify(payload),
    }),
  agentRuns: (params = {}) => request(`/agent-runs?${new URLSearchParams(params)}`),
  agentRunDetail: (id) => request(`/agent-runs/${encodeURIComponent(id)}`),
  deals: (params = {}) => (isDemoModeEnabled() ? Promise.resolve({ items: demoItems("deals") }) : request(`/deals?${new URLSearchParams(params)}`)),
  reports: () => request("/reports"),
};

export { API_BASE_URL };
