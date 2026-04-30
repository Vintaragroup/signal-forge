import { X } from "lucide-react";
import StatusBadge from "./StatusBadge.jsx";

function Field({ label, value }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-1 text-sm text-slate-800">{value || "-"}</div>
    </div>
  );
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

function sortedTimeline(item, linkedMessages, linkedDeals) {
  const events = [];
  const imported = item.imported_at || item.created_at;
  if (imported) {
    events.push({ event: item.type === "contact" ? "imported" : "created", status: item.status || item.contact_status || item.review_status, timestamp: imported, note: item.source });
  }
  if (item.scored_at || item.contact_score || item.lead_score) {
    events.push({ event: "scored", status: item.segment || item.review_status, timestamp: item.scored_at || item.updated_at || imported, note: item.priority_reason || `Score: ${item.contact_score || item.lead_score || item.score || "-"}` });
  }
  (item.contact_lifecycle || item.outreach_lifecycle || item.deal_lifecycle || []).forEach((event) => {
    events.push({
      event: event.event || event.status || event.outcome || "record_event",
      status: event.status || event.outcome || event.decision,
      timestamp: event.created_at || event.logged_at || event.reviewed_at,
      note: event.note || event.summary || "",
    });
  });
  linkedMessages.forEach((message) => {
    events.push({ event: "drafted", status: message.review_status, timestamp: message.created_at, note: message.subject_line });
    (message.review_events || []).forEach((event) => {
      events.push({ event: "reviewed", status: event.review_status || event.decision, timestamp: event.reviewed_at, note: event.note });
    });
    (message.send_events || []).forEach((event) => {
      events.push({ event: "manual_send_logged", status: event.channel || "sent", timestamp: event.sent_at, note: event.note });
    });
    (message.response_events || []).forEach((event) => {
      events.push({ event: "response_logged", status: event.outcome, timestamp: event.responded_at, note: event.note });
      if (event.outcome === "call_booked") {
        events.push({ event: "meeting_prep_needed", status: "call_booked", timestamp: event.responded_at, note: "Generate or review meeting prep." });
      }
    });
  });
  linkedDeals.forEach((deal) => {
    events.push({ event: "deal_outcome", status: deal.outcome || deal.deal_status, timestamp: deal.updated_at || deal.created_at, note: deal.note || `$${Number(deal.deal_value || 0).toLocaleString()}` });
  });
  return events
    .filter((event) => event.timestamp || event.note || event.status)
    .sort((a, b) => String(b.timestamp || "").localeCompare(String(a.timestamp || "")));
}

export default function DetailDrawer({ item, messages = [], deals = [], onClose }) {
  if (!item) return null;

  const linkedMessages = messages.filter(
    (message) =>
      message.target_id === item._id ||
      message.target_key === item.contact_key ||
      message.target_key === item.company_slug ||
      message.linked_contact?._id === item._id ||
      message.linked_lead?._id === item._id,
  );
  const linkedMessageIds = linkedMessages.map((message) => message._id);
  const linkedDeals = deals.filter(
    (deal) =>
      deal.contact_id === item._id ||
      deal.lead_id === item._id ||
      linkedMessageIds.includes(deal.message_draft_id),
  );
  const timeline = sortedTimeline(item, linkedMessages, linkedDeals);

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-full max-w-xl border-l border-slate-200 bg-white shadow-soft">
      <div className="flex h-full flex-col">
        <div className="flex items-start justify-between border-b border-slate-200 p-5">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{item.type || item.target_type || "record"}</div>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">{item.name || item.company_name || item.recipient_name || item.company || "Record"}</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              <StatusBadge value={item.status || item.contact_status || item.review_status || item.outreach_status || item.send_status} />
              <StatusBadge value={item.module || "unknown"} />
            </div>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 scrollbar-soft">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Company" value={item.company || item.company_name} />
            <Field label="Source" value={item.source} />
            <Field label="Score" value={item.score || item.contact_score || item.lead_score} />
            <Field label="Segment" value={item.segment || item.review_status} />
            <Field label="Role" value={item.role || item.business_type} />
            <Field label="Location" value={[item.city, item.state].filter(Boolean).join(", ") || item.location} />
          </div>

          <section className="mt-7">
            <h3 className="text-sm font-semibold text-slate-950">Timeline</h3>
            <div className="mt-3 space-y-3">
              {timeline.slice(0, 12).map((event, index) => (
                <div key={`${event.timestamp || event.created_at || event.logged_at || index}`} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex flex-wrap gap-2">
                      <StatusBadge value={event.event || "event"} />
                      <StatusBadge value={event.status || event.outcome || event.decision} />
                    </div>
                    <span className="text-xs text-slate-500">{formatDate(event.timestamp || event.created_at || event.logged_at || event.reviewed_at)}</span>
                  </div>
                  {event.note ? <p className="mt-2 text-sm text-slate-700">{event.note}</p> : null}
                </div>
              ))}
              {!timeline.length ? <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-500">No timeline entries.</div> : null}
            </div>
          </section>

          <section className="mt-7">
            <h3 className="text-sm font-semibold text-slate-950">Messages</h3>
            <div className="mt-3 space-y-2">
              {linkedMessages.map((message) => (
                <div key={message._id} className="rounded-lg border border-slate-200 p-3">
                  <div className="text-sm font-medium text-slate-900">{message.subject_line}</div>
                  <div className="mt-2 flex gap-2">
                    <StatusBadge value={message.review_status} />
                    <StatusBadge value={message.send_status} />
                    <StatusBadge value={message.response_status || "no_response"} />
                  </div>
                  {message.message_body ? <p className="mt-3 line-clamp-4 whitespace-pre-wrap text-sm leading-6 text-slate-600">{message.message_body}</p> : null}
                  {(message.response_events || []).length ? (
                    <div className="mt-3 space-y-2">
                      {message.response_events.map((event, index) => (
                        <div key={`${event.outcome}-${index}`} className="rounded-lg bg-slate-50 p-2 text-xs text-slate-600">
                          <span className="font-medium">{event.outcome}</span>
                          {event.note ? `: ${event.note}` : ""}
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}
              {!linkedMessages.length ? <div className="text-sm text-slate-500">No linked messages.</div> : null}
            </div>
          </section>

          <section className="mt-7">
            <h3 className="text-sm font-semibold text-slate-950">Deals</h3>
            <div className="mt-3 space-y-2">
              {linkedDeals.map((deal) => (
                <div key={deal._id} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-medium text-slate-900">{deal.company || deal.person}</div>
                    <StatusBadge value={deal.outcome || deal.deal_status} />
                  </div>
                  <div className="mt-1 text-sm text-slate-600">${Number(deal.deal_value || 0).toLocaleString()}</div>
                </div>
              ))}
              {!linkedDeals.length ? <div className="text-sm text-slate-500">No linked deals.</div> : null}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
