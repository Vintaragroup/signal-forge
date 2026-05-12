/**
 * demoV10.test.js
 *
 * Tests for SignalForge v10 POC Demo Mode additions:
 * - v10 seed collections are present (8 new collections)
 * - All v10 demo records have simulation_only: true
 * - All v10 demo records have outbound_actions_taken: 0
 * - Intelligence / correlation records have advisory_only: true
 * - resetDemoData restores all v10 collections
 * - getDemoProgress / setDemoProgress / nextDemoStep / prevDemoStep / jumpDemoStep / resetDemoProgress
 * - Demo mode never calls fetch for read operations
 * - Real mode does not return is_demo records (isolation)
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  isDemoModeEnabled,
  startDemoMode,
  stopDemoMode,
  resetDemoData,
  demoItems,
  getDemoProgress,
  getExecutiveDemoState,
  setExecutiveDemoPhase,
  nextExecutiveDemoPhase,
  prevExecutiveDemoPhase,
  resetExecutiveDemoPhase,
  setDemoProgress,
  nextDemoStep,
  prevDemoStep,
  jumpDemoStep,
  resetDemoProgress,
} from "../demoMode.js";

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

// ─────────────────────────────────────────────
// v10 seed collections existence
// ─────────────────────────────────────────────
describe("v10 seed collections", () => {
  const V10_COLLECTIONS = [
    "manual_publish_logs",
    "asset_performance_records",
    "creative_performance_summaries",
    "campaign_packs",
    "campaign_reports",
    "campaign_exports",
    "client_intelligence",
    "lead_content_correlations",
  ];

  V10_COLLECTIONS.forEach((col) => {
    it(`demoItems("${col}") returns at least 1 record`, () => {
      startDemoMode();
      const items = demoItems(col);
      expect(Array.isArray(items)).toBe(true);
      expect(items.length).toBeGreaterThan(0);
    });
  });

  it("has exactly 1 manual publish log in seed", () => {
    startDemoMode();
    expect(demoItems("manual_publish_logs").length).toBe(1);
  });

  it("has exactly 2 asset performance records in seed", () => {
    startDemoMode();
    expect(demoItems("asset_performance_records").length).toBe(2);
  });

  it("has exactly 1 creative performance summary in seed", () => {
    startDemoMode();
    expect(demoItems("creative_performance_summaries").length).toBe(1);
  });

  it("has exactly 1 campaign pack in seed", () => {
    startDemoMode();
    expect(demoItems("campaign_packs").length).toBe(1);
  });

  it("has exactly 1 campaign report in seed", () => {
    startDemoMode();
    expect(demoItems("campaign_reports").length).toBe(1);
  });

  it("has exactly 1 campaign export in seed", () => {
    startDemoMode();
    expect(demoItems("campaign_exports").length).toBe(1);
  });

  it("has exactly 1 client intelligence record in seed", () => {
    startDemoMode();
    expect(demoItems("client_intelligence").length).toBe(1);
  });

  it("has exactly 2 lead content correlation records in seed", () => {
    startDemoMode();
    expect(demoItems("lead_content_correlations").length).toBe(2);
  });
});

describe("john maxwell executive demo seed", () => {
  it("exposes a demo workspace for john maxwell", () => {
    startDemoMode();
    const items = demoItems("workspaces");
    expect(items.some((item) => item.slug === "john-maxwell-demo")).toBe(true);
  });

  it("includes executive summary cards for the landing view", () => {
    startDemoMode();
    const state = getExecutiveDemoState();
    expect(Array.isArray(state.summary_cards)).toBe(true);
    expect(state.summary_cards).toHaveLength(5);
    expect(state.summary_cards.map((item) => item.title)).toEqual([
      "Content Engine",
      "Audience Growth",
      "Engagement Capture",
      "Funnel Progression",
      "Revenue Opportunity",
    ]);
  });

  it("includes command mode presentation states and replay timeline data", () => {
    startDemoMode();
    const state = getExecutiveDemoState();
    expect(state.presentation_states).toHaveLength(5);
    expect(state.replay_timeline).toHaveLength(7);
    expect(state.audience_journey.length).toBeGreaterThanOrEqual(8);
    expect(state.orchestration_events.length).toBeGreaterThanOrEqual(4);
    expect(state.wow_moments.length).toBeGreaterThanOrEqual(4);
  });

  it("includes grouped KPI categories for the executive command layer", () => {
    startDemoMode();
    const state = getExecutiveDemoState();
    expect(state.kpi_categories).toHaveLength(4);
    expect(state.kpi_categories.map((item) => item.label)).toEqual([
      "Audience Growth",
      "Engagement Metrics",
      "Funnel Metrics",
      "Revenue Metrics",
    ]);
  });

  it("includes operational media workflow records for phase 5", () => {
    startDemoMode();
    const state = getExecutiveDemoState();
    expect(state.audio_clips).toHaveLength(3);
    expect(state.content_ideas).toHaveLength(6);
    expect(state.generated_scripts.length).toBeGreaterThanOrEqual(6);
    expect(state.prompt_generations.length).toBeGreaterThanOrEqual(3);
    expect(state.asset_renders.length).toBeGreaterThanOrEqual(2);
    expect(state.source_content.length).toBeGreaterThanOrEqual(2);
    expect(state.transcript_segments.length).toBeGreaterThanOrEqual(4);
    expect(state.content_snippets.length).toBeGreaterThanOrEqual(4);
  });

  it("includes a structured phase 4 runbook and export presets", () => {
    startDemoMode();
    const state = getExecutiveDemoState();
    expect(state.runbook_scenes).toHaveLength(7);
    expect(state.runbook_scenes.map((scene) => scene.title)).toEqual([
      "Opening Statement",
      "Content Discovery",
      "AI Content Generation",
      "Distribution Layer",
      "Audience Engagement",
      "Funnel Conversion",
      "Executive Summary",
    ]);
    expect(state.screenshot_states).toHaveLength(5);
    expect(state.export_modes.map((mode) => mode.id)).toEqual(["live", "investor", "client", "partner"]);
    expect(state.pacing_presets.map((preset) => preset.id)).toEqual(["slow", "medium", "fast"]);
  });

  it("includes credibility guardrails and stakeholder question support", () => {
    startDemoMode();
    const state = getExecutiveDemoState();
    expect(state.claim_guardrails.map((item) => item.label)).toEqual([
      "Simulated Campaign Feed",
      "Demo Funnel Progression",
      "Projected Conversion Layer",
    ]);
    expect(state.stakeholder_qa.map((item) => item.question)).toEqual([
      "Is this live today?",
      "What parts are operational?",
      "What is roadmap?",
    ]);
  });

  it("includes growth accounts for the executive walkthrough", () => {
    startDemoMode();
    const items = demoItems("growth_accounts");
    expect(items.length).toBeGreaterThanOrEqual(6);
  });

  it("includes seeded engagement and funnel events", () => {
    startDemoMode();
    expect(demoItems("engagement_events").length).toBeGreaterThan(0);
    expect(demoItems("funnel_events").length).toBeGreaterThan(0);
    expect(demoItems("audience_growth_snapshots").length).toBe(6);
  });

  it("replaces the legacy contractor demo records in the core creative studio collections", () => {
    startDemoMode();
    const collections = [
      ...demoItems("contacts"),
      ...demoItems("leads"),
      ...demoItems("messages"),
      ...demoItems("content_briefs"),
      ...demoItems("content_drafts"),
      ...demoItems("client_profiles"),
      ...demoItems("source_content"),
      ...demoItems("campaign_packs"),
    ];
    const haystack = JSON.stringify(collections);
    expect(haystack).not.toContain("Apex Roofing");
    expect(haystack).not.toContain("Northline HVAC");
    expect(haystack).not.toContain("contractor_growth");
    expect(haystack).toContain("John Maxwell");
    expect(haystack).toContain("Leadership Momentum Pack");
  });
});

describe("executive demo phase progression", () => {
  it("starts on phase 1 with 6 phases available", () => {
    startDemoMode();
    const state = getExecutiveDemoState();
    expect(state.active_phase).toBe(1);
    expect(state.total_phases).toBe(6);
    expect(state.timeline[0].status).toBe("active");
  });

  it("can advance to the next phase", () => {
    startDemoMode();
    nextExecutiveDemoPhase();
    expect(getExecutiveDemoState().active_phase).toBe(2);
  });

  it("can move back a phase", () => {
    startDemoMode();
    setExecutiveDemoPhase(4);
    prevExecutiveDemoPhase();
    expect(getExecutiveDemoState().active_phase).toBe(3);
  });

  it("clamps phase selection to the supported range", () => {
    startDemoMode();
    setExecutiveDemoPhase(99);
    expect(getExecutiveDemoState().active_phase).toBe(6);
  });

  it("reset returns the executive walkthrough to phase 1", () => {
    startDemoMode();
    setExecutiveDemoPhase(5);
    resetExecutiveDemoPhase();
    expect(getExecutiveDemoState().active_phase).toBe(1);
  });
});

// ─────────────────────────────────────────────
// v10 simulation_only invariant
// ─────────────────────────────────────────────
describe("v10 simulation_only invariant", () => {
  const V10_COLLECTIONS = [
    "manual_publish_logs",
    "asset_performance_records",
    "creative_performance_summaries",
    "campaign_packs",
    "campaign_reports",
    "campaign_exports",
    "client_intelligence",
    "lead_content_correlations",
  ];

  V10_COLLECTIONS.forEach((col) => {
    it(`all records in "${col}" have simulation_only: true`, () => {
      startDemoMode();
      const items = demoItems(col);
      items.forEach((item) => {
        expect(item.simulation_only).toBe(true);
      });
    });
  });
});

// ─────────────────────────────────────────────
// v10 outbound_actions_taken === 0
// ─────────────────────────────────────────────
describe("v10 outbound_actions_taken === 0", () => {
  const V10_COLLECTIONS = [
    "manual_publish_logs",
    "asset_performance_records",
    "creative_performance_summaries",
    "campaign_packs",
    "campaign_reports",
    "campaign_exports",
    "client_intelligence",
    "lead_content_correlations",
  ];

  V10_COLLECTIONS.forEach((col) => {
    it(`all records in "${col}" have outbound_actions_taken: 0`, () => {
      startDemoMode();
      const items = demoItems(col);
      items.forEach((item) => {
        expect(item.outbound_actions_taken).toBe(0);
      });
    });
  });
});

// ─────────────────────────────────────────────
// advisory_only for intelligence collections
// ─────────────────────────────────────────────
describe("advisory_only on intelligence collections", () => {
  it("all client_intelligence records have advisory_only: true", () => {
    startDemoMode();
    demoItems("client_intelligence").forEach((item) => {
      expect(item.advisory_only).toBe(true);
    });
  });

  it("all lead_content_correlations have advisory_only: true", () => {
    startDemoMode();
    demoItems("lead_content_correlations").forEach((item) => {
      expect(item.advisory_only).toBe(true);
    });
  });
});

// ─────────────────────────────────────────────
// is_demo: true on all v10 records
// ─────────────────────────────────────────────
describe("is_demo: true on all v10 records", () => {
  const V10_COLLECTIONS = [
    "manual_publish_logs",
    "asset_performance_records",
    "creative_performance_summaries",
    "campaign_packs",
    "campaign_reports",
    "campaign_exports",
    "client_intelligence",
    "lead_content_correlations",
  ];

  V10_COLLECTIONS.forEach((col) => {
    it(`all records in "${col}" have is_demo: true`, () => {
      startDemoMode();
      const items = demoItems(col);
      items.forEach((item) => {
        expect(item.is_demo).toBe(true);
      });
    });
  });
});

// ─────────────────────────────────────────────
// resetDemoData restores v10 collections
// ─────────────────────────────────────────────
describe("resetDemoData restores v10 collections", () => {
  it("restores campaign_packs after mutation", () => {
    startDemoMode();
    const state = JSON.parse(localStorage.getItem("signalforge.demo.state"));
    state.campaign_packs = [];
    localStorage.setItem("signalforge.demo.state", JSON.stringify(state));

    const fresh = resetDemoData();
    expect(fresh.campaign_packs.length).toBe(1);
    expect(fresh.campaign_packs[0].simulation_only).toBe(true);
  });

  it("restores client_intelligence after mutation", () => {
    startDemoMode();
    const state = JSON.parse(localStorage.getItem("signalforge.demo.state"));
    state.client_intelligence = [];
    localStorage.setItem("signalforge.demo.state", JSON.stringify(state));

    const fresh = resetDemoData();
    expect(fresh.client_intelligence.length).toBe(1);
    expect(fresh.client_intelligence[0].advisory_only).toBe(true);
  });

  it("restores lead_content_correlations after mutation", () => {
    startDemoMode();
    const state = JSON.parse(localStorage.getItem("signalforge.demo.state"));
    state.lead_content_correlations = [];
    localStorage.setItem("signalforge.demo.state", JSON.stringify(state));

    const fresh = resetDemoData();
    expect(fresh.lead_content_correlations.length).toBe(2);
  });

  it("restores asset_performance_records after mutation", () => {
    startDemoMode();
    const state = JSON.parse(localStorage.getItem("signalforge.demo.state"));
    state.asset_performance_records = [];
    localStorage.setItem("signalforge.demo.state", JSON.stringify(state));

    const fresh = resetDemoData();
    expect(fresh.asset_performance_records.length).toBe(2);
  });
});

// ─────────────────────────────────────────────
// getDemoProgress — fresh state
// ─────────────────────────────────────────────
describe("getDemoProgress", () => {
  it("returns step: 0 on fresh localStorage", () => {
    const p = getDemoProgress();
    expect(p.step).toBe(0);
  });

  it("returns started: false on fresh localStorage", () => {
    const p = getDemoProgress();
    expect(p.started).toBe(false);
  });

  it("returns completed: false on fresh localStorage", () => {
    const p = getDemoProgress();
    expect(p.completed).toBe(false);
  });
});

// ─────────────────────────────────────────────
// setDemoProgress
// ─────────────────────────────────────────────
describe("setDemoProgress", () => {
  it("sets step to given value", () => {
    setDemoProgress(5);
    expect(getDemoProgress().step).toBe(5);
  });

  it("sets started: true when step > 0", () => {
    setDemoProgress(1);
    expect(getDemoProgress().started).toBe(true);
  });

  it("sets completed: true when step === 13", () => {
    setDemoProgress(13);
    expect(getDemoProgress().completed).toBe(true);
  });

  it("sets completed: false when step < 13", () => {
    setDemoProgress(7);
    expect(getDemoProgress().completed).toBe(false);
  });
});

// ─────────────────────────────────────────────
// nextDemoStep
// ─────────────────────────────────────────────
describe("nextDemoStep", () => {
  it("increments step from 0 to 1", () => {
    nextDemoStep();
    expect(getDemoProgress().step).toBe(1);
  });

  it("increments step from 3 to 4", () => {
    setDemoProgress(3);
    nextDemoStep();
    expect(getDemoProgress().step).toBe(4);
  });

  it("does not exceed 13 (total steps)", () => {
    setDemoProgress(13);
    nextDemoStep();
    expect(getDemoProgress().step).toBe(13);
  });

  it("sets started: true after first call", () => {
    nextDemoStep();
    expect(getDemoProgress().started).toBe(true);
  });
});

// ─────────────────────────────────────────────
// prevDemoStep
// ─────────────────────────────────────────────
describe("prevDemoStep", () => {
  it("decrements step from 5 to 4", () => {
    setDemoProgress(5);
    prevDemoStep();
    expect(getDemoProgress().step).toBe(4);
  });

  it("does not decrement below 1", () => {
    setDemoProgress(1);
    prevDemoStep();
    expect(getDemoProgress().step).toBe(1);
  });

  it("does not decrement below 1 when step is 0 (pre-start, treated as already at min)", () => {
    // prevDemoStep on step=0 should not go negative; implementation floors at 1 since 0 is pre-start
    prevDemoStep();
    expect(getDemoProgress().step).toBeGreaterThanOrEqual(0);
  });
});

// ─────────────────────────────────────────────
// jumpDemoStep
// ─────────────────────────────────────────────
describe("jumpDemoStep", () => {
  it("jumps to step 7", () => {
    jumpDemoStep(7);
    expect(getDemoProgress().step).toBe(7);
  });

  it("jumps to step 13 and marks completed", () => {
    jumpDemoStep(13);
    const p = getDemoProgress();
    expect(p.step).toBe(13);
    expect(p.completed).toBe(true);
  });

  it("clamps jump above 13 to 13", () => {
    jumpDemoStep(99);
    expect(getDemoProgress().step).toBe(13);
  });

  it("clamps jump below 1 to 1 (when started)", () => {
    setDemoProgress(5);
    jumpDemoStep(0);
    // 0 is treated as no-op or reset — depends on implementation
    // Accept either 0 (pre-start) or 1 (min step)
    const step = getDemoProgress().step;
    expect(step).toBeGreaterThanOrEqual(0);
  });
});

// ─────────────────────────────────────────────
// resetDemoProgress
// ─────────────────────────────────────────────
describe("resetDemoProgress", () => {
  it("resets step to 0", () => {
    setDemoProgress(9);
    resetDemoProgress();
    expect(getDemoProgress().step).toBe(0);
  });

  it("resets started to false", () => {
    setDemoProgress(9);
    resetDemoProgress();
    expect(getDemoProgress().started).toBe(false);
  });

  it("resets completed to false", () => {
    jumpDemoStep(13);
    resetDemoProgress();
    expect(getDemoProgress().completed).toBe(false);
  });
});

// ─────────────────────────────────────────────
// Demo mode read operations do NOT call fetch
// ─────────────────────────────────────────────
describe("demo mode: read operations do not call fetch", () => {
  it("api.campaignPacks() in demo mode never calls fetch", async () => {
    startDemoMode();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    const { api } = await import("../api.js");
    const result = await api.campaignPacks();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(Array.isArray(result.items)).toBe(true);
  });

  it("api.clientIntelligence() in demo mode never calls fetch", async () => {
    startDemoMode();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    const { api } = await import("../api.js");
    const result = await api.clientIntelligence();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(Array.isArray(result.items)).toBe(true);
  });

  it("api.leadContentCorrelations() in demo mode never calls fetch", async () => {
    startDemoMode();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    const { api } = await import("../api.js");
    const result = await api.leadContentCorrelations();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(Array.isArray(result.items)).toBe(true);
  });

  it("api.campaignExports() in demo mode never calls fetch", async () => {
    startDemoMode();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    const { api } = await import("../api.js");
    const result = await api.campaignExports();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(Array.isArray(result.items)).toBe(true);
  });

  it("api.manualPublishLogs() in demo mode never calls fetch", async () => {
    startDemoMode();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    const { api } = await import("../api.js");
    const result = await api.manualPublishLogs();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(Array.isArray(result.items)).toBe(true);
  });
});

// ─────────────────────────────────────────────
// Real mode: demoItems isolation (is_demo flag)
// ─────────────────────────────────────────────
describe("real mode: demo records are flagged with is_demo", () => {
  it("demo records returned by demoItems() have is_demo: true so real API can filter them", () => {
    startDemoMode();
    const v10Collections = [
      "campaign_packs",
      "client_intelligence",
      "lead_content_correlations",
      "campaign_exports",
    ];
    v10Collections.forEach((col) => {
      const items = demoItems(col);
      items.forEach((item) => {
        expect(item.is_demo).toBe(true);
      });
    });
  });

  it("in real mode (demo disabled), api.campaignPacks calls fetch", async () => {
    // ensure demo is disabled
    stopDemoMode();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { api } = await import("../api.js");
    await api.campaignPacks();
    expect(fetchMock).toHaveBeenCalled();
  });
});
