const DEMO_ENABLED_KEY = "signalforge.demo.enabled";
const DEMO_STATE_KEY = "signalforge.demo.state";

function nowIso() {
  return new Date().toISOString();
}

function daysAgo(days) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString();
}

const seedState = {
  currentStep: 1,
  outreachRun: false,
  responseSimulated: false,
  dealShown: false,
  contacts: [
    {
      _id: "demo-contact-1",
      contact_key: "demo-maya-rivera",
      name: "Maya Rivera",
      company: "Demo Apex Roofing",
      role: "Owner",
      email: "maya.demo@example.invalid",
      module: "contractor_growth",
      source: "demo_seed",
      contact_status: "demo_contact",
      contact_score: 94,
      segment: "high_priority",
      priority_reason: "Demo record: high-intent local contractor with urgent growth goal.",
      notes: "Demo Mode synthetic contact. No real message will be sent.",
      imported_at: daysAgo(4),
      updated_at: daysAgo(1),
      is_demo: true,
    },
    {
      _id: "demo-contact-2",
      contact_key: "demo-eli-hart",
      name: "Eli Hart",
      company: "Demo Northline HVAC",
      role: "Operations Lead",
      email: "eli.demo@example.invalid",
      module: "contractor_growth",
      source: "demo_seed",
      contact_status: "demo_contact",
      contact_score: 82,
      segment: "warm_fit",
      priority_reason: "Demo record: strong fit with seasonal demand signals.",
      notes: "Demo Mode synthetic contact. No real message will be sent.",
      imported_at: daysAgo(3),
      updated_at: daysAgo(1),
      is_demo: true,
    },
  ],
  leads: [
    {
      _id: "demo-lead-1",
      company_slug: "demo-apex-roofing",
      company_name: "Demo Apex Roofing",
      business_type: "roofing contractor",
      location: "Austin, TX",
      module: "contractor_growth",
      source: "demo_seed",
      review_status: "demo_qualified",
      outreach_status: "draft_ready",
      lead_score: 91,
      score: 91,
      marketing_gap: "Demo signal: strong reviews, weak estimate follow-up system.",
      recommended_action: "Run a human-reviewed outreach draft around faster estimate follow-up.",
      updated_at: daysAgo(1),
      is_demo: true,
    },
    {
      _id: "demo-lead-2",
      company_slug: "demo-northline-hvac",
      company_name: "Demo Northline HVAC",
      business_type: "HVAC contractor",
      location: "Denver, CO",
      module: "contractor_growth",
      source: "demo_seed",
      review_status: "demo_qualified",
      outreach_status: "not_started",
      lead_score: 78,
      score: 78,
      marketing_gap: "Demo signal: seasonal demand but no visible follow-up campaign.",
      recommended_action: "Prepare a local growth audit offer for human review.",
      updated_at: daysAgo(2),
      is_demo: true,
    },
  ],
  messages: [
    {
      _id: "demo-draft-1",
      draft_key: "demo-apex-roofing-outreach",
      recipient_name: "Maya Rivera",
      company: "Demo Apex Roofing",
      module: "contractor_growth",
      source: "demo_seed",
      target_type: "contact",
      target_id: "demo-contact-1",
      target_key: "demo-maya-rivera",
      subject_line: "Demo: tighten estimate follow-up this month",
      message_body: "Hi Maya, I noticed Demo Apex Roofing has strong local demand but a few signs that estimate follow-up could be tightened. SignalForge would flag this as a good fit for a short, human-reviewed outreach sequence focused on booked estimates and missed follow-ups. No real message is sent from Demo Mode.",
      review_status: "needs_review",
      send_status: "not_sent",
      response_status: "",
      created_at: daysAgo(1),
      updated_at: daysAgo(1),
      is_demo: true,
    },
    {
      _id: "demo-draft-2",
      draft_key: "demo-northline-hvac-outreach",
      recipient_name: "Eli Hart",
      company: "Demo Northline HVAC",
      module: "contractor_growth",
      source: "demo_seed",
      target_type: "contact",
      target_id: "demo-contact-2",
      target_key: "demo-eli-hart",
      subject_line: "Demo: seasonal follow-up workflow",
      message_body: "Hi Eli, this demo draft shows how SignalForge can turn local contractor signals into review-only outreach. A human operator would review, edit, and send outside SignalForge if appropriate.",
      review_status: "approved",
      send_status: "manual_demo_send_logged",
      response_status: "requested_info",
      response_events: [
        {
          outcome: "requested_info",
          note: "Preloaded demo response: asked for a short seasonal follow-up example.",
          logged_at: daysAgo(1),
          is_demo: true,
        },
      ],
      created_at: daysAgo(1),
      updated_at: daysAgo(1),
      is_demo: true,
    },
  ],
  deals: [
    {
      _id: "demo-deal-1",
      company: "Demo Apex Roofing",
      person: "Maya Rivera",
      module: "contractor_growth",
      source: "demo_seed",
      contact_id: "demo-contact-1",
      message_draft_id: "demo-draft-1",
      outcome: "proposal_sent",
      deal_status: "proposal_sent",
      deal_value: 4500,
      note: "Demo deal outcome waiting for simulated response.",
      created_at: daysAgo(1),
      updated_at: daysAgo(1),
      is_demo: true,
    },
  ],
};

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function readState() {
  const raw = window.localStorage.getItem(DEMO_STATE_KEY);
  if (!raw) return clone(seedState);
  try {
    return { ...clone(seedState), ...JSON.parse(raw) };
  } catch {
    return clone(seedState);
  }
}

function writeState(state) {
  window.localStorage.setItem(DEMO_STATE_KEY, JSON.stringify(state));
  window.dispatchEvent(new Event("signalforge-demo-change"));
  return state;
}

function withDemoLabel(records) {
  return records.map((record) => ({ ...record, is_demo: true, demo_label: "Demo Mode" }));
}

export function isDemoModeEnabled() {
  return window.localStorage.getItem(DEMO_ENABLED_KEY) === "true";
}

export function startDemoMode() {
  window.localStorage.setItem(DEMO_ENABLED_KEY, "true");
  return writeState(clone(seedState));
}

export function stopDemoMode() {
  window.localStorage.setItem(DEMO_ENABLED_KEY, "false");
  window.dispatchEvent(new Event("signalforge-demo-change"));
}

export function getDemoState() {
  return readState();
}

export function runDemoOutreach() {
  const state = readState();
  state.outreachRun = true;
  state.currentStep = Math.max(state.currentStep, 2);
  state.messages = state.messages.map((message) => ({ ...message, demo_label: "Demo Mode", updated_at: nowIso() }));
  return writeState(state);
}

export function approveDemoMessage(messageId) {
  const state = readState();
  state.currentStep = Math.max(state.currentStep, 4);
  state.messages = state.messages.map((message) =>
    message._id === messageId
      ? {
          ...message,
          review_status: "approved",
          review_decision: "approve",
          review_note: "Demo approval only. No real message was sent.",
          reviewed_at: nowIso(),
          updated_at: nowIso(),
          send_status: "not_sent",
        }
      : message,
  );
  return writeState(state);
}

export function simulateDemoResponse(messageId) {
  const state = readState();
  state.responseSimulated = true;
  state.currentStep = Math.max(state.currentStep, 5);
  state.messages = state.messages.map((message) =>
    message._id === messageId
      ? {
          ...message,
          send_status: "manual_demo_send_logged",
          response_status: "call_booked",
          response_events: [
            {
              outcome: "call_booked",
              note: "Demo response: prospect asked for a quick estimate follow-up workflow review.",
              logged_at: nowIso(),
              is_demo: true,
            },
          ],
          updated_at: nowIso(),
        }
      : message,
  );
  state.deals = state.deals.map((deal) =>
    deal.message_draft_id === messageId ? { ...deal, outcome: "negotiation", deal_status: "negotiation", updated_at: nowIso() } : deal,
  );
  return writeState(state);
}

export function showDemoDealOutcome() {
  const state = readState();
  state.dealShown = true;
  state.currentStep = 5;
  state.deals = state.deals.map((deal) =>
    deal._id === "demo-deal-1"
      ? {
          ...deal,
          outcome: "closed_won",
          deal_status: "closed_won",
          deal_value: 4500,
          note: "Demo outcome: closed-won starter engagement. No invoice or CRM update was created.",
          updated_at: nowIso(),
        }
      : deal,
  );
  return writeState(state);
}

export function demoOverview() {
  const state = readState();
  const contacts = state.contacts;
  const leads = state.leads;
  const messages = state.messages;
  const deals = state.deals;
  const closedWon = deals.filter((deal) => deal.outcome === "closed_won" || deal.deal_status === "closed_won");
  const responses = messages.filter((message) => message.response_status);
  return {
    demo_mode: true,
    kpis: {
      total_contacts: contacts.length,
      total_leads: leads.length,
      message_drafts: messages.length,
      sent_messages: messages.filter((message) => message.send_status === "manual_demo_send_logged").length,
      responses: responses.length,
      meetings: messages.filter((message) => message.response_status === "call_booked").length,
      deals: deals.length,
      closed_won_revenue: closedWon.reduce((sum, deal) => sum + Number(deal.deal_value || 0), 0),
    },
    pipeline_funnel: [
      { stage: "Demo Contacts", count: contacts.length, tone: "blue" },
      { stage: "Demo Leads", count: leads.length, tone: "purple" },
      { stage: "Demo Drafts", count: messages.length, tone: "amber" },
      { stage: "Approved", count: messages.filter((message) => message.review_status === "approved").length, tone: "green" },
      { stage: "Responses", count: responses.length, tone: "blue" },
      { stage: "Closed Won", count: closedWon.length, tone: "green" },
    ],
    responses_by_status: responses.reduce((counts, message) => ({ ...counts, [message.response_status]: (counts[message.response_status] || 0) + 1 }), { not_set: messages.length - responses.length }),
    deals_by_outcome: deals.reduce((counts, deal) => ({ ...counts, [deal.outcome]: (counts[deal.outcome] || 0) + 1 }), {}),
    revenue_over_time: closedWon.map((deal) => ({ date: String(deal.updated_at || "").slice(0, 10), revenue: Number(deal.deal_value || 0) })),
    top_modules: [{ module: "contractor_growth", contacts: contacts.length, messages: messages.length, deals: deals.length, revenue: closedWon.reduce((sum, deal) => sum + Number(deal.deal_value || 0), 0) }],
    tasks: [
      { label: "Demo drafts needing review", count: messages.filter((message) => message.review_status === "needs_review").length, tone: "review" },
      { label: "Demo responses", count: responses.length, tone: "interested" },
      { label: "Demo deal outcomes", count: deals.length, tone: "closed_won" },
    ],
    next_actions: [
      { key: "demo", label: "Continue Demo", helper: "Walk the guided demo from outreach through deal outcome.", count: state.currentStep, tone: "demo", page: "demo" },
      { key: "review", label: "Review Drafts", helper: "Approve a synthetic draft. No message is sent.", count: messages.filter((message) => message.review_status === "needs_review").length, tone: "review", page: "messages", filters: { review_status: "needs_review" } },
    ],
    agent_activity: [],
  };
}

export function demoItems(collection) {
  const state = readState();
  return withDemoLabel(state[collection] || []);
}