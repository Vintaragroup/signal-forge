import { useState } from "react";
import { getExplainability } from "../api";

/**
 * ExplainabilityDrawer.jsx
 *
 * Slide-in drawer showing the explainability payload for any system entity.
 *
 * Props:
 *   entityType  — "recommendation" | "autonomy_action" | "orchestration" | etc.
 *   entityId    — string entity ID
 *   isOpen      — boolean
 *   onClose     — () => void
 */
export default function ExplainabilityDrawer({ entityType, entityId, isOpen, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [loaded, setLoaded] = useState(null); // track which entity was loaded

  async function load() {
    if (!entityType || !entityId) return;
    const key = `${entityType}/${entityId}`;
    if (loaded === key && data) return; // already loaded
    setLoading(true);
    setError(null);
    try {
      const result = await getExplainability(entityType, entityId);
      setData(result);
      setLoaded(key);
    } catch (e) {
      setError(e.message || "Failed to load explanation");
    } finally {
      setLoading(false);
    }
  }

  // Trigger load when drawer opens
  if (isOpen && entityType && entityId && !data && !loading) {
    load();
  }

  if (!isOpen) return null;

  const CONF_COLOR = (c) =>
    c >= 0.8 ? "text-green-400" : c >= 0.6 ? "text-yellow-400" : "text-red-400";

  function Section({ title, children }) {
    return (
      <div className="mb-5">
        <h4 className="text-gray-400 text-xs uppercase tracking-wider font-semibold mb-2">
          {title}
        </h4>
        {children}
      </div>
    );
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="fixed right-0 top-0 h-full w-96 bg-gray-950 border-l border-gray-800 z-50 flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <div>
            <h2 className="text-white font-semibold text-sm">Why did this happen?</h2>
            <p className="text-gray-500 text-xs mt-0.5">
              {entityType?.replace(/_/g, " ")} · {entityId}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white text-xl leading-none"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading && (
            <div className="animate-pulse space-y-3">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-3 bg-gray-800 rounded" />
              ))}
            </div>
          )}

          {error && (
            <div className="text-red-400 text-sm">
              {error}
              <button onClick={() => { setData(null); setLoaded(null); load(); }}
                className="ml-2 text-blue-400 underline text-xs">Retry</button>
            </div>
          )}

          {!loading && !error && data && (
            <>
              {/* Status + Confidence */}
              <div className="flex items-center gap-3 mb-5 p-3 bg-gray-900 rounded-lg">
                <div>
                  <p className="text-gray-500 text-xs">Status</p>
                  <p className="text-white text-sm font-medium capitalize">
                    {data.status || "—"}
                  </p>
                </div>
                <div className="border-l border-gray-700 pl-3">
                  <p className="text-gray-500 text-xs">Confidence</p>
                  <p className={`text-sm font-bold ${CONF_COLOR(data.confidence || 0)}`}>
                    {data.confidence != null ? `${Math.round(data.confidence * 100)}%` : "—"}
                  </p>
                </div>
              </div>

              {/* Explanation */}
              <Section title="Explanation">
                <p className="text-gray-300 text-sm leading-relaxed">
                  {data.explanation || "No explanation available."}
                </p>
              </Section>

              {/* Evidence */}
              {data.evidence?.length > 0 && (
                <Section title="Evidence">
                  <ul className="space-y-1">
                    {data.evidence.map((e, i) => (
                      <li key={i} className="text-gray-400 text-xs flex gap-2">
                        <span className="text-blue-500 flex-shrink-0">•</span>
                        {e}
                      </li>
                    ))}
                  </ul>
                </Section>
              )}

              {/* Policy checks */}
              {data.policy_checks?.length > 0 && (
                <Section title="Policy Checks">
                  <ul className="space-y-1">
                    {data.policy_checks.map((p, i) => (
                      <li key={i} className="text-gray-400 text-xs flex gap-2">
                        <span className="text-green-500">✓</span>
                        {p}
                      </li>
                    ))}
                  </ul>
                </Section>
              )}

              {/* Triggering metrics */}
              {data.triggering_metrics && Object.keys(data.triggering_metrics).length > 0 && (
                <Section title="Triggering Metrics">
                  <div className="space-y-1">
                    {Object.entries(data.triggering_metrics).map(([k, v]) => (
                      <div key={k} className="flex justify-between text-xs">
                        <span className="text-gray-500">{k}</span>
                        <span className="text-gray-300 font-mono">{String(v)}</span>
                      </div>
                    ))}
                  </div>
                </Section>
              )}

              {/* Lineage */}
              {data.lineage_refs?.length > 0 && (
                <Section title="Lineage References">
                  <ul className="space-y-1">
                    {data.lineage_refs.map((ref, i) => (
                      <li key={i} className="text-blue-400 text-xs font-mono">{ref}</li>
                    ))}
                  </ul>
                </Section>
              )}

              <p className="text-gray-700 text-xs mt-4">
                Evaluated {data.evaluated_at ? new Date(data.evaluated_at).toLocaleString() : "—"}
              </p>
            </>
          )}

          {!loading && !error && !data && (
            <div className="text-gray-600 text-sm text-center py-8">
              No explanation data available.
            </div>
          )}
        </div>
      </div>
    </>
  );
}
