import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { api } from "../api.js";
import DataTable from "../components/DataTable.jsx";
import DemoPageBanner from "../components/DemoPageBanner.jsx";
import DetailDrawer from "../components/DetailDrawer.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const emptyFilters = {
  type: "",
  module: "",
  source: "",
  segment: "",
  review_status: "",
  send_status: "",
  response_status: "",
  contact_status: "",
  deal_outcome: "",
};

function hashFilters() {
  const [, queryString = ""] = window.location.hash.split("?");
  const params = new URLSearchParams(queryString);
  return Object.fromEntries(Object.keys(emptyFilters).map((key) => [key, params.get(key) || ""]));
}

function uniqueValues(rows, key) {
  return [...new Set(rows.map((row) => row[key]).filter(Boolean))].sort();
}

function SelectFilter({ label, value, onChange, options }) {
  return (
    <label className="min-w-0">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
      >
        <option value="">All</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option.replaceAll("_", " ")}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function PipelinePage() {
  const [contacts, setContacts] = useState([]);
  const [leads, setLeads] = useState([]);
  const [messages, setMessages] = useState([]);
  const [deals, setDeals] = useState([]);
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState(hashFilters);
  const [selected, setSelected] = useState(null);

  async function load() {
    const [contactData, leadData, messageData, dealData] = await Promise.all([
      api.contacts({ limit: "250" }),
      api.leads({ limit: "250" }),
      api.messages({ limit: "250" }),
      api.deals({ limit: "250" }),
    ]);
    setContacts(contactData.items || []);
    setLeads(leadData.items || []);
    setMessages(messageData.items || []);
    setDeals(dealData.items || []);
  }

  useEffect(() => {
    load();
    const syncFilters = () => setFilters(hashFilters());
    window.addEventListener("hashchange", syncFilters);
    return () => window.removeEventListener("hashchange", syncFilters);
  }, []);

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  const rows = useMemo(() => {
    const messagesByTarget = new Map();
    messages.forEach((message) => {
      const key = message.target_id || message.target_key;
      if (!key) return;
      if (!messagesByTarget.has(key)) messagesByTarget.set(key, []);
      messagesByTarget.get(key).push(message);
    });

    const dealOutcomeByTarget = new Map();
    deals.forEach((deal) => {
      [deal.contact_id, deal.lead_id, deal.message_draft_id].filter(Boolean).forEach((key) => {
        dealOutcomeByTarget.set(key, deal.outcome || deal.deal_status || "not_set");
      });
    });

    const contactRows = contacts.map((contact) => ({
      ...contact,
      type: "contact",
      display: contact.name || contact.company,
      score: contact.contact_score || 0,
      segment: contact.segment || (contact.contact_score ? "" : "unscored"),
      contact_status: contact.contact_status || "imported",
      status: contact.contact_status || "imported",
      latest_message: messagesByTarget.get(contact._id)?.[0] || messagesByTarget.get(contact.contact_key)?.[0] || {},
      deal_outcome: dealOutcomeByTarget.get(contact._id) || contact.deal_outcome || "",
      last_activity: contact.updated_at || contact.imported_at,
    }));
    const leadRows = leads.map((lead) => ({
      ...lead,
      type: "lead",
      display: lead.company_name,
      score: lead.lead_score || lead.score || 0,
      segment: lead.review_status,
      status: lead.outreach_status || lead.review_status || "not_set",
      contact_status: "",
      latest_message: messagesByTarget.get(lead._id)?.[0] || messagesByTarget.get(lead.company_slug)?.[0] || {},
      deal_outcome: dealOutcomeByTarget.get(lead._id) || lead.deal_outcome || "",
      last_activity: lead.updated_at || lead.created_at,
    }));
    return [...contactRows, ...leadRows]
      .filter((row) => !filters.type || row.type === filters.type)
      .filter((row) => !filters.module || row.module === filters.module)
      .filter((row) => !filters.source || row.source === filters.source)
      .filter((row) => !filters.segment || row.segment === filters.segment)
      .filter((row) => !filters.contact_status || row.contact_status === filters.contact_status)
      .filter((row) => !filters.review_status || row.review_status === filters.review_status)
      .filter((row) => !filters.send_status || row.latest_message?.send_status === filters.send_status)
      .filter((row) => {
        if (!filters.response_status) return true;
        const response = row.latest_message?.response_status || "not_set";
        return response === filters.response_status;
      })
      .filter((row) => !filters.deal_outcome || row.deal_outcome === filters.deal_outcome)
      .filter((row) => {
        const text = `${row.display} ${row.company} ${row.company_name} ${row.email} ${row.source} ${row.status} ${row.module}`.toLowerCase();
        return text.includes(query.toLowerCase());
      })
      .sort((a, b) => String(b.last_activity || "").localeCompare(String(a.last_activity || "")));
  }, [contacts, leads, messages, deals, filters, query]);

  const allRows = useMemo(() => {
    const contactRows = contacts.map((contact) => ({
      ...contact,
      type: "contact",
      display: contact.name || contact.company,
      score: contact.contact_score || 0,
      segment: contact.segment || (contact.contact_score ? "" : "unscored"),
      contact_status: contact.contact_status || "imported",
      status: contact.contact_status || "imported",
    }));
    const leadRows = leads.map((lead) => ({
      ...lead,
      type: "lead",
      display: lead.company_name,
      score: lead.lead_score || lead.score || 0,
      segment: lead.review_status,
      status: lead.outreach_status || lead.review_status || "not_set",
    }));
    return [...contactRows, ...leadRows];
  }, [contacts, leads]);

  const columns = [
    { key: "display", label: "Name" },
    { key: "demo", label: "Mode", render: (row) => (row.is_demo ? <StatusBadge value="Demo Mode" /> : <StatusBadge value="live data" />) },
    { key: "type", label: "Type", render: (row) => <StatusBadge value={row.type} /> },
    { key: "module", label: "Module", render: (row) => <StatusBadge value={row.module || "unknown"} /> },
    { key: "score", label: "Score" },
    { key: "segment", label: "Segment", render: (row) => <StatusBadge value={row.segment || row.review_status || "not_set"} /> },
    { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> },
    { key: "source", label: "Source" },
    { key: "send_status", label: "Send", render: (row) => <StatusBadge value={row.latest_message?.send_status || "no_draft"} /> },
    { key: "response_status", label: "Response", render: (row) => <StatusBadge value={row.latest_message?.response_status || "not_set"} /> },
    { key: "deal_outcome", label: "Deal", render: (row) => <StatusBadge value={row.deal_outcome || "none"} /> },
    { key: "last_activity", label: "Last Activity", render: (row) => row.last_activity ? new Date(row.last_activity).toLocaleString() : "-" },
  ];

  return (
    <div className="space-y-4">
      <DemoPageBanner showReset onReset={load} />
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-4">
          <h2 className="text-sm font-semibold text-slate-950">Campaign CRM</h2>
          <p className="mt-1 text-sm text-slate-500">
            Review imported contacts, scored segments, lead status, linked message state, and deal outcomes from one local-first view.
          </p>
        </div>
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="h-9 w-full rounded-lg border border-slate-200 pl-9 pr-3 text-sm outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
            placeholder="Search contacts and leads"
          />
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3 xl:grid-cols-9">
          <SelectFilter label="Type" value={filters.type} onChange={(value) => updateFilter("type", value)} options={["contact", "lead"]} />
          <SelectFilter label="Module" value={filters.module} onChange={(value) => updateFilter("module", value)} options={uniqueValues(allRows, "module")} />
          <SelectFilter label="Source" value={filters.source} onChange={(value) => updateFilter("source", value)} options={uniqueValues(allRows, "source")} />
          <SelectFilter label="Segment" value={filters.segment} onChange={(value) => updateFilter("segment", value)} options={uniqueValues(allRows, "segment")} />
          <SelectFilter label="Contact" value={filters.contact_status} onChange={(value) => updateFilter("contact_status", value)} options={uniqueValues(allRows, "contact_status")} />
          <SelectFilter label="Review" value={filters.review_status} onChange={(value) => updateFilter("review_status", value)} options={uniqueValues(allRows, "review_status")} />
          <SelectFilter label="Send" value={filters.send_status} onChange={(value) => updateFilter("send_status", value)} options={uniqueValues(messages, "send_status")} />
          <SelectFilter label="Response" value={filters.response_status} onChange={(value) => updateFilter("response_status", value)} options={["not_set", ...uniqueValues(messages, "response_status")]} />
          <SelectFilter label="Deal" value={filters.deal_outcome} onChange={(value) => updateFilter("deal_outcome", value)} options={uniqueValues(deals.map((deal) => ({ outcome: deal.outcome || deal.deal_status })), "outcome")} />
        </div>
        <div className="mt-3 flex items-center justify-between gap-3">
          <div className="text-sm text-slate-500">{rows.length} records match current filters.</div>
          <button
            type="button"
            onClick={() => {
              setFilters(emptyFilters);
              setQuery("");
              window.location.hash = "pipeline";
            }}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700"
          >
            Clear filters
          </button>
        </div>
      </div>
      <DataTable
        columns={columns}
        rows={rows}
        onRowClick={setSelected}
        emptyLabel="No CRM records match these filters. Clear filters, import contacts, or run the lead pipeline to add records."
      />
      <DetailDrawer item={selected} messages={messages} deals={deals} onClose={() => setSelected(null)} />
    </div>
  );
}
