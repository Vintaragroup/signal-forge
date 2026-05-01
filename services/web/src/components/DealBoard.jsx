import StatusBadge from "./StatusBadge.jsx";

const COLUMNS = ["proposal_sent", "negotiation", "closed_won", "closed_lost", "nurture", "no_show", "not_fit"];

export default function DealBoard({ deals = [] }) {
  return (
    <div className="grid gap-4 xl:grid-cols-7 lg:grid-cols-4 md:grid-cols-2">
      {COLUMNS.map((column) => {
        const columnDeals = deals.filter((deal) => (deal.outcome || deal.deal_status) === column);
        const total = columnDeals.reduce((sum, deal) => sum + Number(deal.deal_value || 0), 0);
        return (
          <section key={column} className="min-h-[360px] rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="mb-3 flex items-center justify-between gap-2">
              <StatusBadge value={column} />
              <span className="text-xs font-medium text-slate-500">${total.toLocaleString()}</span>
            </div>
            <div className="space-y-3">
              {columnDeals.map((deal) => (
                <article key={deal._id} className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                  <div className="text-sm font-semibold text-slate-950">{deal.company || deal.person || "Deal"}</div>
                  <div className="mt-1 text-xs text-slate-500">{deal.person || deal.module || "-"}</div>
                  <div className="mt-3 flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-slate-900">${Number(deal.deal_value || 0).toLocaleString()}</span>
                    <div className="flex flex-wrap justify-end gap-1.5">
                      {deal.is_demo ? <StatusBadge value="Demo Mode" /> : null}
                      <StatusBadge value={deal.module || "unknown"} />
                    </div>
                  </div>
                </article>
              ))}
              {!columnDeals.length ? <div className="rounded-lg border border-dashed border-slate-200 p-4 text-center text-sm text-slate-400">Empty</div> : null}
            </div>
          </section>
        );
      })}
    </div>
  );
}
