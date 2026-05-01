export default function StatusBadge({ value }) {
  const normalized = String(value || "not_set").toLowerCase();
  const tone =
    normalized.includes("won") ||
    normalized.includes("approved") ||
    normalized.includes("ready") ||
    normalized.includes("enabled") ||
    normalized.includes("sent") ||
    normalized.includes("high_priority")
      ? "green"
      : normalized.includes("lost") || normalized.includes("rejected") || normalized.includes("offline")
        ? "red"
        : normalized.includes("revision") ||
            normalized.includes("review") ||
            normalized.includes("disabled") ||
            normalized.includes("proposal") ||
            normalized.includes("follow")
          ? "amber"
          : normalized.includes("booked") ||
              normalized.includes("negotiation") ||
              normalized.includes("interested")
            ? "blue"
            : normalized.includes("nurture") || normalized.includes("research")
              ? "purple"
              : "slate";

  const styles = {
    green: "bg-green-50 text-green-700 ring-green-200",
    red: "bg-red-50 text-red-700 ring-red-200",
    amber: "bg-amber-50 text-amber-700 ring-amber-200",
    blue: "bg-blue-50 text-blue-700 ring-blue-200",
    purple: "bg-purple-50 text-purple-700 ring-purple-200",
    slate: "bg-slate-100 text-slate-700 ring-slate-200",
  };

  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ring-1 ${styles[tone]}`}>
      {String(value || "not_set").replaceAll("_", " ")}
    </span>
  );
}
