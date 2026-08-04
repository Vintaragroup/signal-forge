// Shared formatting/detection helpers for agent-run views (AgentTasksPage's
// LiveAgentRunPanel and Agent Console's AgentsPage) — previously two
// independently re-implemented copies.

export function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

export function formatConfidence(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return String(value);
  return `${Math.round(numeric * 100)}%`;
}

export function isGptStep(step) {
  return step?.step_name?.startsWith("gpt_") || step?.output?.used_gpt;
}
