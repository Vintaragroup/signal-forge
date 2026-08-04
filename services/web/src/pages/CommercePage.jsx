import { useState, useEffect } from "react";
import { api } from "../api";

/**
 * CommercePage.jsx
 *
 * Pillar 3 — trackable link + hosted checkout for digital-asset sales.
 * Stripe Checkout only: card data never touches this server. An offer's
 * public link is unreachable until an operator explicitly approves it.
 */

function StripeStatusPanel() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      setStatus(await api.stripeStatus());
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-3" />
        <div className="h-3 bg-gray-800 rounded w-1/2" />
      </div>
    );
  }

  const reachable = status?.reachable;

  return (
    <div className={`bg-gray-900 border rounded-lg p-5 ${reachable ? "border-green-800" : "border-gray-800"}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-indigo-700 rounded flex items-center justify-center text-white text-xs font-bold">
            $
          </div>
          <div>
            <p className="text-white font-semibold text-sm">Stripe Checkout</p>
            <p className="text-gray-500 text-xs">Hosted payment page — no card data touches this server</p>
          </div>
        </div>
        <span className={`px-2 py-0.5 rounded text-xs font-semibold uppercase border ${
          reachable
            ? "bg-green-900 text-green-300 border-green-700"
            : "bg-gray-800 text-gray-400 border-gray-700"
        }`}>
          {reachable ? "Connected" : "Not Connected"}
        </span>
      </div>
      {status?.error && <p className="text-xs text-red-400">{status.error}</p>}
      {!status?.enabled && (
        <p className="text-xs text-gray-500">
          STRIPE_ENABLED is false — offers use simulated checkout URLs, no real charges possible.
        </p>
      )}
      <button onClick={load} className="mt-3 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-400 rounded text-sm">
        ↺ Refresh
      </button>
    </div>
  );
}

function CreateOfferForm({ workspaceSlug, onCreated }) {
  const [approvedExports, setApprovedExports] = useState([]);
  const [form, setForm] = useState({ source_campaign_export_id: "", title: "", description: "", price_dollars: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function loadExports() {
    try {
      const data = await api.campaignExports({ status: "approved" });
      setApprovedExports(data.items || []);
    } catch {
      setApprovedExports([]);
    }
  }

  useEffect(() => { loadExports(); }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const priceCents = Math.round(parseFloat(form.price_dollars || "0") * 100);
      await api.createCommerceOffer({
        workspace_slug: workspaceSlug,
        source_campaign_export_id: form.source_campaign_export_id,
        title: form.title,
        description: form.description,
        price_cents: priceCents,
        currency: "usd",
      });
      setForm({ source_campaign_export_id: "", title: "", description: "", price_dollars: "" });
      onCreated?.();
    } catch (err) {
      setError(err.message || "Failed to create offer.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
      <p className="text-white font-semibold text-sm mb-3">Create an offer</p>
      {approvedExports.length === 0 ? (
        <p className="text-xs text-gray-500">
          No approved campaign exports yet. Generate and approve a campaign export first — an offer sells an
          existing export.{" "}
          <a href="#creative-studio" className="text-indigo-400 hover:underline">
            Go to Creative Studio →
          </a>
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3">
          <select
            value={form.source_campaign_export_id}
            onChange={(e) => setForm({ ...form, source_campaign_export_id: e.target.value })}
            required
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
          >
            <option value="">Select an approved export…</option>
            {approvedExports.map((exp) => (
              <option key={exp._id} value={exp._id}>
                {exp.export_name || exp._id} ({exp.export_format})
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Title"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            required
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
          />
          <textarea
            placeholder="Description"
            rows={2}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
          />
          <input
            type="number"
            min="0.01"
            step="0.01"
            placeholder="Price (USD)"
            value={form.price_dollars}
            onChange={(e) => setForm({ ...form, price_dollars: e.target.value })}
            required
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
          />
          {error && <p className="text-xs text-red-400">{error}</p>}
          <button
            type="submit"
            disabled={busy}
            className="px-3 py-1.5 bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 text-white rounded text-sm"
          >
            {busy ? "Creating…" : "Create draft offer"}
          </button>
        </form>
      )}
    </div>
  );
}

const OFFER_STATUS_COLORS = {
  draft: "bg-gray-800 text-gray-400 border-gray-700",
  approved: "bg-green-900 text-green-300 border-green-700",
  rejected: "bg-red-950 text-red-300 border-red-800",
};

function OffersList({ offers, publicBaseUrl, onReview }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 space-y-3">
      <p className="text-white font-semibold text-sm">Offers ({offers.length})</p>
      {offers.length === 0 && <p className="text-xs text-gray-500">No offers yet.</p>}
      {offers.map((offer) => (
        <div key={offer._id} className="border border-gray-800 rounded p-3 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`px-2 py-0.5 rounded text-xs font-semibold uppercase border ${OFFER_STATUS_COLORS[offer.status] || OFFER_STATUS_COLORS.draft}`}>
              {offer.status}
            </span>
            <span className="text-white text-sm font-medium">{offer.title}</span>
            <span className="text-gray-400 text-xs">
              ${(offer.price_cents / 100).toFixed(2)} {(offer.currency || "usd").toUpperCase()}
            </span>
            <span className="text-gray-600 text-xs ml-auto">{offer.click_count || 0} clicks</span>
          </div>
          {offer.description && <p className="text-xs text-gray-500">{offer.description}</p>}
          {offer.status === "approved" && (
            <p className="text-xs text-indigo-400 break-all">
              {publicBaseUrl}/api/o/{offer.slug}
            </p>
          )}
          {offer.status === "draft" && (
            <div className="flex gap-2 pt-1">
              <button
                onClick={() => onReview(offer._id, "approve")}
                className="px-2 py-1 bg-green-800 hover:bg-green-700 text-white rounded text-xs"
              >
                Approve
              </button>
              <button
                onClick={() => onReview(offer._id, "reject")}
                className="px-2 py-1 bg-red-900 hover:bg-red-800 text-white rounded text-xs"
              >
                Reject
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function TransactionsList({ transactions, offers }) {
  const offerTitleById = Object.fromEntries(offers.map((o) => [o._id, o.title]));
  const totalRevenueCents = transactions
    .filter((t) => t.status === "completed")
    .reduce((sum, t) => sum + (t.amount_cents || 0), 0);

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-white font-semibold text-sm">Transactions ({transactions.length})</p>
        <p className="text-green-400 text-sm font-semibold">${(totalRevenueCents / 100).toFixed(2)} total</p>
      </div>
      {transactions.length === 0 && <p className="text-xs text-gray-500">No transactions yet.</p>}
      {transactions.map((txn) => (
        <div key={txn._id} className="border border-gray-800 rounded p-2 flex flex-wrap items-center gap-2 text-xs">
          <span className={`px-2 py-0.5 rounded font-semibold uppercase border ${
            txn.status === "completed"
              ? "bg-green-900 text-green-300 border-green-700"
              : "bg-gray-800 text-gray-400 border-gray-700"
          }`}>
            {txn.status}
          </span>
          <span className="text-gray-300">{offerTitleById[txn.offer_id] || txn.offer_id}</span>
          <span className="text-gray-500">${((txn.amount_cents || 0) / 100).toFixed(2)}</span>
          {txn.buyer_email && <span className="text-gray-600">{txn.buyer_email}</span>}
          <span className="text-gray-600 ml-auto">{txn.occurred_at ? new Date(txn.occurred_at).toLocaleString() : ""}</span>
        </div>
      ))}
    </div>
  );
}

export default function CommercePage({ workspaceSlug = "default" }) {
  const [offers, setOffers] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const publicBaseUrl = window.location.origin.replace(/\/$/, "");

  async function load() {
    try {
      const [offersData, txnsData] = await Promise.all([
        api.commerceOffers({}),
        api.commerceTransactions({}),
      ]);
      setOffers(offersData.items || []);
      setTransactions(txnsData.items || []);
    } catch {
      // non-fatal
    }
  }

  useEffect(() => { load(); }, [refreshKey]);

  function refresh() {
    setRefreshKey((k) => k + 1);
  }

  async function handleReview(offerId, decision) {
    try {
      await api.reviewCommerceOffer(offerId, { decision });
      refresh();
    } catch {
      // non-fatal — offer stays in its current state, operator can retry
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Commerce</h1>
          <p className="text-gray-500 text-sm mt-0.5">
            Trackable link + hosted checkout for digital-asset sales — Pillar 3
          </p>
        </div>
        <button onClick={refresh} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-sm">
          ↺ Refresh All
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <StripeStatusPanel />
        <CreateOfferForm workspaceSlug={workspaceSlug} onCreated={refresh} />
      </div>

      <OffersList offers={offers} publicBaseUrl={publicBaseUrl} onReview={handleReview} />
      <TransactionsList transactions={transactions} offers={offers} />
    </div>
  );
}
