/**
 * HealthBadge.jsx — reusable health / trust indicator badge
 *
 * Props:
 *   value     — numeric 0-100, or string status ("ok"|"degraded"|"error"|"unknown")
 *   label     — display label
 *   size      — "sm" | "md" | "lg"  (default "md")
 *   showTrend — show a trend arrow if `trend` prop provided
 *   trend     — "up" | "down" | "stable"
 */
export default function HealthBadge({ value, label, size = "md", showTrend = false, trend }) {
  // Determine colour from numeric score or string status
  function colorClass() {
    if (typeof value === "number") {
      if (value >= 80) return "bg-green-900 text-green-300 border-green-700";
      if (value >= 60) return "bg-yellow-900 text-yellow-300 border-yellow-700";
      return "bg-red-900 text-red-300 border-red-700";
    }
    const map = {
      ok:       "bg-green-900 text-green-300 border-green-700",
      healthy:  "bg-green-900 text-green-300 border-green-700",
      degraded: "bg-yellow-900 text-yellow-300 border-yellow-700",
      warning:  "bg-yellow-900 text-yellow-300 border-yellow-700",
      error:    "bg-red-900 text-red-300 border-red-700",
      unknown:  "bg-gray-800 text-gray-400 border-gray-700",
    };
    return map[String(value).toLowerCase()] || map.unknown;
  }

  function trendIcon() {
    if (!showTrend || !trend) return null;
    const icons = { up: "↑", down: "↓", stable: "→" };
    const colors = { up: "text-green-400", down: "text-red-400", stable: "text-gray-400" };
    return (
      <span className={`ml-1 ${colors[trend] || "text-gray-400"}`}>
        {icons[trend] || ""}
      </span>
    );
  }

  const sizeMap = {
    sm: "px-1.5 py-0.5 text-xs",
    md: "px-2 py-0.5 text-xs",
    lg: "px-3 py-1 text-sm",
  };

  const displayValue = typeof value === "number" ? `${value}%` : String(value ?? "—");

  return (
    <span
      className={`inline-flex items-center rounded border font-semibold tracking-wide uppercase ${colorClass()} ${sizeMap[size] || sizeMap.md}`}
      title={label}
    >
      {label && <span className="mr-1 font-normal opacity-70">{label}</span>}
      {displayValue}
      {trendIcon()}
    </span>
  );
}
