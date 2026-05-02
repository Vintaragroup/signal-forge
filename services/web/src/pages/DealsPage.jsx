import { useEffect, useState } from "react";
import { api } from "../api.js";
import DealBoard from "../components/DealBoard.jsx";
import DemoPageBanner from "../components/DemoPageBanner.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

function initialOutcome() {
  const [, queryString = ""] = window.location.hash.split("?");
  return new URLSearchParams(queryString).get("outcome") || "";
}

export default function DealsPage() {
  const [deals, setDeals] = useState([]);
  const [outcome, setOutcome] = useState(initialOutcome);

  useEffect(() => {
    api.deals({ limit: "500" }).then((data) => setDeals(data.items || []));
    const syncFilters = () => setOutcome(initialOutcome());
    window.addEventListener("hashchange", syncFilters);
    return () => window.removeEventListener("hashchange", syncFilters);
  }, []);

  const outcomes = [...new Set(deals.map((deal) => deal.outcome || deal.deal_status).filter(Boolean))].sort();
  const visibleDeals = deals.filter((deal) => {
    const dealOutcome = deal.outcome || deal.deal_status;
    if (outcome === "open") return ["proposal_sent", "negotiation", "nurture"].includes(dealOutcome);
    return !outcome || dealOutcome === outcome;
  });

  return (
    <div className="space-y-4">
      <DemoPageBanner showReset onReset={() => api.deals({ limit: "500" }).then((data) => setDeals(data.items || []))} />
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-950">Deal Pipeline</h2>
            <div className="mt-1 text-sm text-slate-500">
              {visibleDeals.length} visible deals. Track proposals, negotiation, wins, losses, nurture, no-shows, and not-fit outcomes.
            </div>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={outcome}
              onChange={(event) => setOutcome(event.target.value)}
              className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
            >
              <option value="">All outcomes</option>
              <option value="open">Open deals</option>
              {outcomes.map((item) => (
                <option key={item} value={item}>
                  {item.replaceAll("_", " ")}
                </option>
              ))}
            </select>
            <StatusBadge value={outcome || "all outcomes"} />
          </div>
          <div className="text-left lg:text-right">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">Total Value</div>
            <div className="mt-1 text-xl font-semibold text-slate-950">
              ${visibleDeals.reduce((sum, deal) => sum + Number(deal.deal_value || 0), 0).toLocaleString()}
            </div>
          </div>
        </div>
      </div>
      {visibleDeals.length ? (
        <DealBoard deals={visibleDeals} />
      ) : (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center">
          <div className="text-sm font-semibold text-slate-950">No deals match this view.</div>
          <p className="mt-2 text-sm text-slate-500">
            Log a deal outcome after a meeting, or clear the outcome filter to review all tracked opportunities.
          </p>
        </div>
      )}
    </div>
  );
}
