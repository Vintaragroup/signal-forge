export default function StatCard({ label, value, helper, tone = "blue", icon: Icon }) {
  const tones = {
    blue: "bg-blue-50 text-blue-700 ring-blue-100",
    green: "bg-green-50 text-green-700 ring-green-100",
    purple: "bg-purple-50 text-purple-700 ring-purple-100",
    amber: "bg-amber-50 text-amber-700 ring-amber-100",
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-slate-500">{label}</div>
          <div className="mt-2 text-2xl font-semibold text-slate-950">{value}</div>
        </div>
        {Icon ? (
          <div className={`rounded-lg p-2 ring-1 ${tones[tone] || tones.blue}`}>
            <Icon className="h-5 w-5" />
          </div>
        ) : null}
      </div>
      {helper ? <div className="mt-3 text-xs leading-5 text-slate-500">{helper}</div> : null}
    </div>
  );
}
