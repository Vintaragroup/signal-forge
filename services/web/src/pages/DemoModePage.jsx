import { useEffect, useState } from "react";
import { Check, DollarSign, MessageSquare, Play, RefreshCw, Send } from "lucide-react";
import { api } from "../api.js";
import StatusBadge from "../components/StatusBadge.jsx";

function money(value) {
  return `$${Number(value || 0).toLocaleString()}`;
}

function StepCard({ number, title, active, complete, children }) {
  return (
    <section className={["rounded-lg border bg-white p-5 shadow-sm", active ? "border-blue-300 ring-2 ring-blue-100" : "border-slate-200"].join(" ")}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase text-slate-400">Step {number}</div>
          <h2 className="mt-1 text-lg font-semibold text-slate-950">{title}</h2>
        </div>
        <StatusBadge value={complete ? "demo complete" : active ? "demo next" : "demo ready"} />
      </div>
      {children}
    </section>
  );
}

export default function DemoModePage() {
  const [state, setState] = useState(null);
  const [notice, setNotice] = useState("");

  async function loadDemo() {
    if (!api.demoEnabled()) await api.startDemo();
    setState(await api.demoState());
  }

  async function resetDemo() {
    await api.startDemo();
    setState(await api.demoState());
    setNotice("Demo data reset to seeded synthetic records.");
  }

  useEffect(() => {
    loadDemo();
    const sync = () => loadDemo();
    window.addEventListener("signalforge-demo-change", sync);
    return () => window.removeEventListener("signalforge-demo-change", sync);
  }, []);

  async function runOutreach() {
    await api.runDemoOutreach();
    setState(await api.demoState());
    setNotice("Demo outreach generated synthetic review-only drafts. No real messages were sent.");
  }

  async function approveDraft() {
    await api.reviewMessage("demo-draft-1", { decision: "approve", note: "Approved during Demo Mode." });
    setState(await api.demoState());
    setNotice("Demo draft approved. It remains not sent.");
  }

  async function simulateResponse() {
    await api.simulateDemoResponse("demo-draft-1");
    setState(await api.demoState());
    setNotice("Demo response logged as synthetic call booked. No inbox or platform was contacted.");
  }

  async function showDealOutcome() {
    await api.showDemoDealOutcome();
    setState(await api.demoState());
    setNotice("Demo deal moved to closed won. No invoice or CRM update was created.");
  }

  if (!state) {
    return <div className="rounded-lg border border-slate-200 bg-white p-8 text-sm text-slate-500 shadow-sm">Loading Demo Mode...</div>;
  }

  const primaryDraft = state.messages.find((message) => message._id === "demo-draft-1") || state.messages[0];
  const primaryDeal = state.deals.find((deal) => deal._id === "demo-deal-1") || state.deals[0];
  const approved = primaryDraft?.review_status === "approved";
  const responseReady = Boolean(primaryDraft?.response_status);
  const closedWon = primaryDeal?.outcome === "closed_won" || primaryDeal?.deal_status === "closed_won";

  return (
    <div className="space-y-5">
      <section className="rounded-lg border-2 border-purple-300 bg-purple-50 p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-bold uppercase tracking-widest text-purple-700">Demo Mode v1</div>
            <h2 className="mt-1 text-2xl font-semibold text-purple-950">Demo Mode — Synthetic data only</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-purple-800">
              This guided flow uses seeded synthetic contacts, leads, drafts, responses, and deals.
              Every record is labeled <strong>DEMO</strong> and stored only in your browser. MongoDB is never written to from Demo Mode.
            </p>
          </div>
          <button
            type="button"
            onClick={resetDemo}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-purple-300 bg-white px-3 text-sm font-semibold text-purple-800 shadow-sm transition hover:bg-purple-50"
          >
            <RefreshCw className="h-4 w-4" />
            Reset Demo Data
          </button>
        </div>
      </section>

      {notice ? <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">{notice}</div> : null}

      <div className="grid gap-4 md:grid-cols-5">
        {[
          ["Contacts", state.contacts.length],
          ["Leads", state.leads.length],
          ["Drafts", state.messages.length],
          ["Responses", state.messages.filter((message) => message.response_status).length],
          ["Deals", state.deals.length],
        ].map(([label, count]) => (
          <div key={label} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <div className="text-xs font-semibold uppercase text-slate-400">Demo {label}</div>
            <div className="mt-2 text-2xl font-semibold text-slate-950">{count}</div>
          </div>
        ))}
      </div>

      <div className="space-y-4">
        <StepCard number="1" title="Run Outreach" active={!state.outreachRun} complete={state.outreachRun}>
          <p className="text-sm leading-6 text-slate-600">Create a synthetic outreach run from seeded demo contacts and leads.</p>
          <button type="button" onClick={runOutreach} className="mt-4 inline-flex h-9 items-center gap-2 rounded-lg bg-blue-600 px-3 text-sm font-semibold text-white transition hover:bg-blue-700">
            <Play className="h-4 w-4" />
            Run Outreach
          </button>
        </StepCard>

        <StepCard number="2" title="Review Drafts" active={state.outreachRun && !approved} complete={approved}>
          <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="font-semibold text-slate-950">{primaryDraft.subject_line}</div>
                <div className="mt-1 text-sm text-slate-500">{primaryDraft.recipient_name} at {primaryDraft.company}</div>
              </div>
              <div className="flex flex-wrap gap-2"><StatusBadge value="Demo Mode" /><StatusBadge value={primaryDraft.review_status} /></div>
            </div>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-700">{primaryDraft.message_body}</p>
          </article>
        </StepCard>

        <StepCard number="3" title="Approve Message" active={state.outreachRun && !approved} complete={approved}>
          <p className="text-sm leading-6 text-slate-600">Approve the synthetic draft. The send state stays local and no real message is sent.</p>
          <button type="button" disabled={!state.outreachRun || approved} onClick={approveDraft} className="mt-4 inline-flex h-9 items-center gap-2 rounded-lg bg-green-600 px-3 text-sm font-semibold text-white transition hover:bg-green-700 disabled:bg-slate-300">
            <Check className="h-4 w-4" />
            Approve Message
          </button>
        </StepCard>

        <StepCard number="4" title="Simulate Response" active={approved && !responseReady} complete={responseReady}>
          <p className="text-sm leading-6 text-slate-600">Log a synthetic response as if the operator sent the message manually outside SignalForge.</p>
          <button type="button" disabled={!approved || responseReady} onClick={simulateResponse} className="mt-4 inline-flex h-9 items-center gap-2 rounded-lg bg-blue-600 px-3 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:bg-slate-300">
            <MessageSquare className="h-4 w-4" />
            Simulate Response
          </button>
        </StepCard>

        <StepCard number="5" title="Show Deal Outcome" active={responseReady && !closedWon} complete={closedWon}>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="font-semibold text-slate-950">{primaryDeal.company}</div>
                <div className="mt-1 text-sm text-slate-500">{primaryDeal.person}</div>
              </div>
              <div className="flex flex-wrap gap-2"><StatusBadge value="Demo Mode" /><StatusBadge value={primaryDeal.outcome} /></div>
            </div>
            <div className="mt-3 inline-flex items-center gap-2 text-lg font-semibold text-green-700"><DollarSign className="h-5 w-5" />{money(primaryDeal.deal_value)}</div>
            <p className="mt-2 text-sm leading-6 text-slate-600">{primaryDeal.note}</p>
          </div>
          <button type="button" disabled={!responseReady || closedWon} onClick={showDealOutcome} className="mt-4 inline-flex h-9 items-center gap-2 rounded-lg bg-green-600 px-3 text-sm font-semibold text-white transition hover:bg-green-700 disabled:bg-slate-300">
            <Send className="h-4 w-4" />
            Show Deal Outcome
          </button>
        </StepCard>
      </div>
    </div>
  );
}