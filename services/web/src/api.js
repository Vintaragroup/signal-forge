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
  overview: () => request("/stats/overview"),
  contacts: (params = {}) => request(`/contacts?${new URLSearchParams(params)}`),
  leads: (params = {}) => request(`/leads?${new URLSearchParams(params)}`),
  messages: (params = {}) => request(`/messages?${new URLSearchParams(params)}`),
  reviewMessage: (id, payload) =>
    request(`/messages/${encodeURIComponent(id)}/review`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  agents: () => request("/agents"),
  runAgent: (payload) =>
    request("/agents/run", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  agentRuns: (params = {}) => request(`/agent-runs?${new URLSearchParams(params)}`),
  agentRunDetail: (id) => request(`/agent-runs/${encodeURIComponent(id)}`),
  deals: (params = {}) => request(`/deals?${new URLSearchParams(params)}`),
  reports: () => request("/reports"),
};

export { API_BASE_URL };
