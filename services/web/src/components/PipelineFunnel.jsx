export default function PipelineFunnel({ items = [] }) {
  const max = Math.max(...items.map((item) => item.count || 0), 1);
  const colors = {
    blue: "bg-blue-500",
    green: "bg-green-500",
    purple: "bg-purple-500",
    amber: "bg-amber-500",
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-950">Pipeline Funnel</h2>
        <span className="text-xs text-slate-500">{items.length} stages</span>
      </div>
      <div className="space-y-3">
        {items.map((item) => (
          <div key={item.stage}>
            <div className="mb-1 flex items-center justify-between text-sm">
              <span className="font-medium text-slate-700">{item.stage}</span>
              <span className="text-slate-500">{item.count}</span>
            </div>
            <div className="h-2 rounded-full bg-slate-100">
              <div
                className={`h-2 rounded-full ${colors[item.tone] || colors.blue}`}
                style={{ width: `${Math.max(5, ((item.count || 0) / max) * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
