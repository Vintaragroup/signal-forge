export default function StatusBadge({ value }) {
  const normalized = String(value || "not_set").toLowerCase();
  let tone = "slate";
  if (normalized.includes("running")) tone = "blue";
  if (normalized.includes("waiting_for_approval") || normalized.includes("waiting for approval")) tone = "amber";
  if (
    normalized.includes("completed") ||
    normalized.includes("won") ||
    normalized.includes("approved") ||
    normalized.includes("ready") ||
    normalized.includes("enabled") ||
    normalized.includes("sent") ||
    normalized.includes("high_priority")
  ) tone = "green";
  if (normalized.includes("failed") || normalized.includes("error") || normalized.includes("lost") || normalized.includes("rejected") || normalized.includes("offline")) tone = "red";
  if (
    normalized.includes("revision") ||
    normalized.includes("review") ||
    normalized.includes("disabled") ||
    normalized.includes("proposal") ||
    normalized.includes("follow")
  ) tone = "amber";
  if (normalized.includes("booked") || normalized.includes("negotiation") || normalized.includes("interested")) tone = "blue";
  if (normalized.includes("gpt") || normalized.includes("nurture") || normalized.includes("research")) tone = "purple";
  if (normalized.includes("test") || normalized.includes("synthetic") || normalized.includes("system")) tone = "slate";

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
