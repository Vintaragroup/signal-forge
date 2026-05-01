import { useEffect, useState } from "react";
import { Check, Search, X, RotateCcw } from "lucide-react";
import { api } from "../api.js";
import DataTable from "../components/DataTable.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const emptyFilters = {
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
    <label>
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

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

function shortId(value) {
  return value ? String(value).slice(0, 8) : "-";
}

function MessageDetailDrawer({ message, onClose, onReview, busyId }) {
  if (!message) return null;

  const linkedContact = message.linked_contact;
  const linkedLead = message.linked_lead;
  const linkedDeal = message.linked_deal;
  const timeline = message.timeline || [];
  const responseEvents = message.response_events || [];

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-full max-w-2xl border-l border-slate-200 bg-white shadow-soft">
      <div className="flex h-full flex-col">
        <div className="flex items-start justify-between border-b border-slate-200 p-5">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Message Review</div>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">{message.subject_line || "Message draft"}</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {message.source === "gpt" ? <StatusBadge value="source=gpt" /> : null}
              <StatusBadge value={message.review_status} />
              <StatusBadge value={message.send_status} />
              <StatusBadge value={message.response_status || "not_set"} />
              <StatusBadge value={message.module} />
            </div>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 scrollbar-soft">
          <section className="grid gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <h3 className="text-sm font-semibold text-slate-950">Recipient</h3>
              <div className="mt-3 space-y-2 text-sm text-slate-700">
                <div><span className="font-medium">Name:</span> {message.recipient_name || linkedContact?.name || "-"}</div>
                <div><span className="font-medium">Company:</span> {message.company || linkedContact?.company || linkedLead?.company_name || "-"}</div>
                <div><span className="font-medium">Role:</span> {linkedContact?.role || "-"}</div>
                <div><span className="font-medium">Source:</span> {message.source || linkedContact?.source || linkedLead?.source || "-"}</div>
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <h3 className="text-sm font-semibold text-slate-950">Linked Records</h3>
              <div className="mt-3 space-y-2 text-sm text-slate-700">
                <div><span className="font-medium">Contact:</span> {linkedContact?.name || "not linked"}</div>
                <div><span className="font-medium">Lead:</span> {linkedLead?.company_name || "not linked"}</div>
                <div><span className="font-medium">Deal:</span> {linkedDeal?.outcome || linkedDeal?.deal_status || "none"}</div>
                <div><span className="font-medium">Note:</span> {message.message_note_path || "-"}</div>
              </div>
            </div>
          </section>

          {(message.source === "gpt" || message.generated_by_agent || message.agent_run_id) ? (
            <section className="mt-6 rounded-lg border border-purple-200 bg-purple-50 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-purple-950">GPT Provenance</h3>
                <div className="flex flex-wrap gap-2">
                  <StatusBadge value={message.source ? `source=${message.source}` : "source not set"} />
                  <StatusBadge value={message.generated_by_agent || "agent not set"} />
                </div>
              </div>
              <div className="mt-3 grid gap-2 text-sm text-purple-950 md:grid-cols-2">
                <div><span className="font-medium">Review:</span> {message.review_status || "not_set"}</div>
                <div><span className="font-medium">Send:</span> {message.send_status || "not_set"}</div>
                <div><span className="font-medium">Agent run:</span> {message.agent_run_id || "not linked"}</div>
                <div><span className="font-medium">Step:</span> {message.agent_step_name || "not linked"}</div>
                <div><span className="font-medium">Confidence:</span> {message.gpt_confidence ?? "-"}</div>
                <div className="md:col-span-2"><span className="font-medium">Reasoning:</span> {message.gpt_reasoning_summary || "No reasoning summary recorded."}</div>
              </div>
            </section>
          ) : null}

          <section className="mt-6">
            <h3 className="text-sm font-semibold text-slate-950">Message Body</h3>
            <div className="mt-3 whitespace-pre-wrap rounded-lg border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-800">
              {message.message_body || "No body recorded."}
            </div>
          </section>

          <section className="mt-6">
            <h3 className="text-sm font-semibold text-slate-950">Review Actions</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busyId === message._id}
                onClick={() => onReview(message, "approve")}
                className="inline-flex h-9 items-center gap-2 rounded-lg bg-green-600 px-3 text-sm font-medium text-white transition hover:bg-green-700 disabled:bg-slate-300"
              >
                <Check className="h-4 w-4" />
                Approve
              </button>
              <button
                type="button"
                disabled={busyId === message._id}
                onClick={() => onReview(message, "revise")}
                className="inline-flex h-9 items-center gap-2 rounded-lg bg-amber-500 px-3 text-sm font-medium text-white transition hover:bg-amber-600 disabled:bg-slate-300"
              >
                <RotateCcw className="h-4 w-4" />
                Revise
              </button>
              <button
                type="button"
                disabled={busyId === message._id}
                onClick={() => onReview(message, "reject")}
                className="inline-flex h-9 items-center gap-2 rounded-lg bg-slate-800 px-3 text-sm font-medium text-white transition hover:bg-red-700 disabled:bg-slate-300"
              >
                <X className="h-4 w-4" />
                Reject
              </button>
            </div>
          </section>

          <section className="mt-6">
            <h3 className="text-sm font-semibold text-slate-950">Approval / Send / Response Timeline</h3>
            <div className="mt-3 space-y-3">
              {timeline.map((event, index) => (
                <div key={`${event.event}-${index}`} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <StatusBadge value={event.event} />
                      <StatusBadge value={event.status || "not_set"} />
                    </div>
                    <span className="text-xs text-slate-500">{formatDate(event.timestamp)}</span>
                  </div>
                  {event.note ? <p className="mt-2 text-sm text-slate-700">{event.note}</p> : null}
                </div>
              ))}
              {!timeline.length ? <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-500">No timeline events yet.</div> : null}
            </div>
          </section>

          <section className="mt-6">
            <h3 className="text-sm font-semibold text-slate-950">Response History</h3>
            <div className="mt-3 space-y-2">
              {responseEvents.map((event, index) => (
                <div key={`${event.outcome}-${index}`} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <StatusBadge value={event.outcome} />
                    <span className="text-xs text-slate-500">{formatDate(event.responded_at)}</span>
                  </div>
                  {event.note ? <p className="mt-2 text-sm text-slate-700">{event.note}</p> : null}
                </div>
              ))}
              {!responseEvents.length ? <div className="text-sm text-slate-500">No responses logged.</div> : null}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export default function MessagesPage() {
  const [messages, setMessages] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [deals, setDeals] = useState([]);
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState(hashFilters);
  const [busyId, setBusyId] = useState("");
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState(null);

  async function load() {
    const [messageData, contactData, dealData] = await Promise.all([
      api.messages({ limit: "250" }),
      api.contacts({ limit: "250" }),
      api.deals({ limit: "250" }),
    ]);
    setMessages(messageData.items || []);
    setContacts(contactData.items || []);
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

  async function review(message, decision) {
    setBusyId(message._id);
    setNotice("");
    try {
      await api.reviewMessage(message._id, {
        decision,
        note: `Reviewed from Web Dashboard v1: ${decision}.`,
      });
      await load();
      setNotice(`Saved ${decision}. No message sent.`);
      setSelected((current) => (current?._id === message._id ? { ...current, review_status: decision === "approve" ? "approved" : decision === "reject" ? "rejected" : "needs_revision" } : current));
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusyId("");
    }
  }

  const contactById = new Map(contacts.map((contact) => [contact._id, contact]));
  const dealByMessageId = new Map(deals.map((deal) => [deal.message_draft_id, deal]));
  const enrichedRows = messages.map((message) => {
    const linkedContact = message.target_type === "contact" ? contactById.get(message.target_id) : null;
    const linkedDeal = dealByMessageId.get(message._id);
    return {
      ...message,
      contact_status: linkedContact?.contact_status || "",
      deal_outcome: linkedDeal?.outcome || linkedDeal?.deal_status || "",
      effective_response_status: message.response_status || "not_set",
    };
  });

  const rows = enrichedRows.filter((message) => {
    const text = `${message.subject_line} ${message.recipient_name} ${message.company} ${message.module}`.toLowerCase();
    return (
      (!filters.module || message.module === filters.module) &&
      (!filters.source || message.source === filters.source) &&
      (!filters.segment || message.segment === filters.segment) &&
      (!filters.review_status || message.review_status === filters.review_status) &&
      (!filters.send_status || message.send_status === filters.send_status) &&
      (!filters.response_status || message.effective_response_status === filters.response_status) &&
      (!filters.contact_status || message.contact_status === filters.contact_status) &&
      (!filters.deal_outcome || message.deal_outcome === filters.deal_outcome) &&
      text.includes(query.toLowerCase())
    );
  });

  const queueCounts = {
    needsReview: messages.filter((message) => message.review_status === "needs_review").length,
    readyToSend: messages.filter((message) => message.review_status === "approved" && message.send_status === "not_sent").length,
    awaitingResponse: messages.filter((message) => message.send_status === "sent" && !message.response_status).length,
    responseNextAction: messages.filter((message) => ["interested", "requested_info", "call_booked"].includes(message.response_status)).length,
  };

  const columns = [
    {
      key: "subject_line",
      label: "Subject",
      render: (row) => (
        <div>
          <span className="font-medium text-slate-900">{row.subject_line || "-"}</span>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {row.source === "gpt" ? <StatusBadge value="source=gpt" /> : null}
            {row.agent_run_id ? <span className="text-xs text-slate-500">run {shortId(row.agent_run_id)}</span> : null}
          </div>
        </div>
      ),
    },
    { key: "recipient_name", label: "Recipient" },
    { key: "module", label: "Module", render: (row) => <StatusBadge value={row.module} /> },
    { key: "source", label: "Source", render: (row) => <StatusBadge value={row.source || "not_set"} /> },
    { key: "review_status", label: "Review", render: (row) => <StatusBadge value={row.review_status} /> },
    { key: "send_status", label: "Send", render: (row) => <StatusBadge value={row.send_status} /> },
    { key: "generated_by_agent", label: "Agent", render: (row) => <span className="text-xs text-slate-600">{row.generated_by_agent || "-"}</span> },
    { key: "agent_run_id", label: "Run", render: (row) => <span className="font-mono text-xs text-slate-500">{shortId(row.agent_run_id)}</span> },
    { key: "response_status", label: "Response", render: (row) => <StatusBadge value={row.response_status || "not_set"} /> },
    { key: "contact_status", label: "Contact", render: (row) => <StatusBadge value={row.contact_status || "not_linked"} /> },
    { key: "deal_outcome", label: "Deal", render: (row) => <StatusBadge value={row.deal_outcome || "none"} /> },
    {
      key: "actions",
      label: "Actions",
      render: (row) => (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busyId === row._id}
            onClick={(event) => {
              event.stopPropagation();
              review(row, "approve");
            }}
            className="inline-flex h-8 items-center gap-1 rounded-lg bg-green-600 px-2.5 text-xs font-medium text-white transition hover:bg-green-700 disabled:bg-slate-300"
          >
            <Check className="h-3.5 w-3.5" />
            Approve
          </button>
          <button
            type="button"
            disabled={busyId === row._id}
            onClick={(event) => {
              event.stopPropagation();
              review(row, "revise");
            }}
            className="inline-flex h-8 items-center gap-1 rounded-lg bg-amber-500 px-2.5 text-xs font-medium text-white transition hover:bg-amber-600 disabled:bg-slate-300"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Revise
          </button>
          <button
            type="button"
            disabled={busyId === row._id}
            onClick={(event) => {
              event.stopPropagation();
              review(row, "reject");
            }}
            className="inline-flex h-8 items-center gap-1 rounded-lg bg-slate-800 px-2.5 text-xs font-medium text-white transition hover:bg-red-700 disabled:bg-slate-300"
          >
            <X className="h-3.5 w-3.5" />
            Reject
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-4">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">Needs review</div>
          <div className="mt-2 text-2xl font-semibold text-slate-950">{queueCounts.needsReview}</div>
          <p className="mt-2 text-sm text-slate-500">Approve, revise, or reject before any manual send.</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">Ready to send</div>
          <div className="mt-2 text-2xl font-semibold text-green-700">{queueCounts.readyToSend}</div>
          <p className="mt-2 text-sm text-slate-500">Approved drafts awaiting a human send outside SignalForge.</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">Awaiting response</div>
          <div className="mt-2 text-2xl font-semibold text-purple-700">{queueCounts.awaitingResponse}</div>
          <p className="mt-2 text-sm text-slate-500">Sent messages with no response logged.</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">Needs next action</div>
          <div className="mt-2 text-2xl font-semibold text-blue-700">{queueCounts.responseNextAction}</div>
          <p className="mt-2 text-sm text-slate-500">Interested or booked-call responses to work next.</p>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-4">
          <h2 className="text-sm font-semibold text-slate-950">Message Review Workflow</h2>
          <p className="mt-1 text-sm text-slate-500">
            Dashboard actions only update review state and vault logs. SignalForge still does not send messages.
          </p>
        </div>
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="h-9 w-full rounded-lg border border-slate-200 pl-9 pr-3 text-sm outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
            placeholder="Search messages"
          />
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3 xl:grid-cols-8">
          <SelectFilter label="Module" value={filters.module} onChange={(value) => updateFilter("module", value)} options={uniqueValues(enrichedRows, "module")} />
          <SelectFilter label="Source" value={filters.source} onChange={(value) => updateFilter("source", value)} options={uniqueValues(enrichedRows, "source")} />
          <SelectFilter label="Segment" value={filters.segment} onChange={(value) => updateFilter("segment", value)} options={uniqueValues(enrichedRows, "segment")} />
          <SelectFilter label="Review" value={filters.review_status} onChange={(value) => updateFilter("review_status", value)} options={uniqueValues(enrichedRows, "review_status")} />
          <SelectFilter label="Send" value={filters.send_status} onChange={(value) => updateFilter("send_status", value)} options={uniqueValues(enrichedRows, "send_status")} />
          <SelectFilter label="Response" value={filters.response_status} onChange={(value) => updateFilter("response_status", value)} options={uniqueValues(enrichedRows, "effective_response_status")} />
          <SelectFilter label="Contact" value={filters.contact_status} onChange={(value) => updateFilter("contact_status", value)} options={uniqueValues(enrichedRows, "contact_status")} />
          <SelectFilter label="Deal" value={filters.deal_outcome} onChange={(value) => updateFilter("deal_outcome", value)} options={uniqueValues(enrichedRows, "deal_outcome")} />
        </div>
        <div className="mt-3 flex items-center justify-between gap-3">
          <div className="text-sm text-slate-500">{rows.length} message drafts match current filters.</div>
          <button
            type="button"
            onClick={() => {
              setFilters(emptyFilters);
              setQuery("");
              window.location.hash = "messages";
            }}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700"
          >
            Clear filters
          </button>
        </div>
      </div>

      {notice ? <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">{notice}</div> : null}
      <DataTable
        columns={columns}
        rows={rows}
        onRowClick={setSelected}
        emptyLabel="No message drafts match these filters. Draft messages from scored contacts or approved leads to populate this queue."
      />
      <MessageDetailDrawer message={selected} onClose={() => setSelected(null)} onReview={review} busyId={busyId} />
    </div>
  );
}
