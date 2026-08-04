// Shared stat card used by PublishingPage.jsx's LinkedIn/Instagram tabs —
// previously copy-pasted identically across two separate pages.
export default function TelemetryCard({ label, value, sub, color = "text-white" }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex flex-col gap-1">
      <p className="text-gray-500 text-xs">{label}</p>
      <p className={`font-bold text-xl ${color}`}>{value}</p>
      {sub && <p className="text-gray-600 text-xs">{sub}</p>}
    </div>
  );
}
