import { useState, useEffect, useCallback } from "react";
import { getActivityFeed } from "../api";

/**
 * ActivityTimelinePanel.jsx
 *
 * Unified chronological feed of system events (audit log + orchestrations).
 *
 * Props:
 *   workspaceSlug  — optional workspace filter
 *   limit          — max events to show (default 30)
 *   autoRefresh    — refresh interval in ms, 0 = disabled (default 0)
 */
export default function ActivityTimelinePanel({
  workspaceSlug,
  limit = 30,
  autoRefresh = 0,
}) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getActivityFeed({ workspaceSlug, limit });
      setEvents(data.events || []);
    } catch (e) {
      setError(e.message || "Failed to load activity feed");
    } finally {
      setLoading(false);
    }
  }, [workspaceSlug, limit]);

  useEffect(() => {
    load();
    if (autoRefresh > 0) {
      const id = setInterval(load, autoRefresh);
      return () => clearInterval(id);
    }
  }, [load, autoRefresh]);

  const SEV_STYLE = {
    info:    { dot: "bg-blue-500",   badge: "bg-blue-900 text-blue-300"  },
    warning: { dot: "bg-yellow-500", badge: "bg-yellow-900 text-yellow-300" },
    error:   { dot: "bg-red-500",    badge: "bg-red-900 text-red-300"    },
  };

  const filtered = filter === "all" ? events : events.filter((e) => e.severity === filter);

  function formatTime(ts) {
    if (!ts) return "—";
    try { return new Date(ts).toLocaleTimeString(); } catch { return ts; }
  }

  function formatType(type) {
    return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
        <h3 className="text-white font-semibold text-sm">Activity Timeline</h3>
        <div className="flex items-center gap-2">
          {["all", "error", "warning", "info"].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2 py-0.5 rounded text-xs capitalize ${
                filter === f
                  ? "bg-blue-700 text-white"
                  : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}
            >
              {f}
            </button>
          ))}
          <button
            onClick={load}
            className="px-2 py-0.5 bg-gray-800 text-gray-400 rounded text-xs hover:bg-gray-700"
          >
            ↺
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {loading && (
          <div className="space-y-3 animate-pulse">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="flex items-start gap-3">
                <div className="w-2 h-2 rounded-full bg-gray-700 mt-1.5 flex-shrink-0" />
                <div className="flex-1 space-y-1">
                  <div className="h-3 bg-gray-800 rounded w-1/2" />
                  <div className="h-2 bg-gray-800 rounded w-1/4" />
                </div>
              </div>
            ))}
          </div>
        )}

        {error && (
          <div className="text-red-400 text-xs p-2">{error}
            <button onClick={load} className="ml-2 text-blue-400 underline">Retry</button>
          </div>
        )}

        {!loading && !error && filtered.length === 0 && (
          <div className="text-center text-gray-600 text-sm py-8">
            <p>No activity events found.</p>
            {filter !== "all" && (
              <button onClick={() => setFilter("all")} className="mt-2 text-blue-400 text-xs underline">
                Clear filter
              </button>
            )}
          </div>
        )}

        {!loading && !error && filtered.map((evt, i) => {
          const sev = SEV_STYLE[evt.severity] || SEV_STYLE.info;
          return (
            <div key={i} className="flex items-start gap-3 py-2 border-b border-gray-800 last:border-0">
              <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${sev.dot}`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-gray-200 text-xs font-medium">{formatType(evt.type)}</span>
                  <span className={`px-1.5 py-0.5 rounded text-xs font-semibold uppercase ${sev.badge}`}>
                    {evt.severity}
                  </span>
                  {evt.actor && evt.actor !== "system" && (
                    <span className="text-gray-500 text-xs">{evt.actor}</span>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-gray-500 text-xs">{formatTime(evt.ts)}</span>
                  {evt.entity && (
                    <span className="text-gray-600 text-xs truncate">{evt.entity}</span>
                  )}
                  {evt.nav_link && (
                    <a
                      href={evt.nav_link}
                      className="text-blue-500 text-xs hover:text-blue-400 flex-shrink-0"
                    >
                      View →
                    </a>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="px-4 py-2 border-t border-gray-800 text-xs text-gray-600">
        {filtered.length} event{filtered.length !== 1 ? "s" : ""}
      </div>
    </div>
  );
}
