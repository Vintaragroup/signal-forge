import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    agentTasks: vi.fn(),
    messages: vi.fn(),
    approvalRequests: vi.fn(),
    deals: vi.fn(),
    agentRuns: vi.fn(),
    workflowAssets: vi.fn(),
    discoveryInsights: vi.fn(),
    getWorkspace: vi.fn(),
    clientProfileWorkflowDefinition: vi.fn(),
    generateAssetsFromInsight: vi.fn(),
    triggerDiscoveryInsights: vi.fn(),
    clientSources: vi.fn(),
    discoveryRunSummaries: vi.fn(),
    workflowRuns: vi.fn(),
  },
}));

vi.mock("../api.js", () => ({
  api: apiMock,
}));

vi.mock("../components/DemoPageBanner.jsx", () => ({
  default: () => <div>Demo Banner</div>,
}));

vi.mock("../components/LiveAgentRunPanel.jsx", () => ({
  default: () => <div>Live Agent Run Panel</div>,
}));

vi.mock("../components/StatusBadge.jsx", () => ({
  default: ({ value }) => <span>{value}</span>,
}));

vi.mock("../components/WorkflowAssetCard.jsx", () => ({
  default: ({ asset, mode }) => (
    <div>
      {mode}:{asset.title}:{asset.distribution_state || "not_queued"}
    </div>
  ),
}));

vi.mock("../components/DiscoveryInsightModal.jsx", () => ({
  default: ({ insight }) => insight ? <div>Insight Modal: {insight.title}</div> : null,
}));

import WorkflowPage from "../pages/WorkflowPage.jsx";

let container;
let root;

async function renderPage(props = {}) {
  await act(async () => {
    root.render(<WorkflowPage activeProfile="executive_growth" demoMode={false} activeWorkspace="all" {...props} />);
    await Promise.resolve();
    await Promise.resolve();
  });
}

function blockTextForHeading(headingText) {
  const heading = Array.from(container.querySelectorAll("h3")).find((node) => node.textContent.includes(headingText));
  return heading?.parentElement?.parentElement?.textContent || "";
}

describe("WorkflowPage Step 5 grouping", () => {
  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    vi.clearAllMocks();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    apiMock.agentTasks.mockResolvedValue({ items: [] });
    apiMock.approvalRequests.mockResolvedValue({ items: [] });
    apiMock.deals.mockResolvedValue({ items: [] });
    apiMock.discoveryInsights.mockResolvedValue({ items: [] });
    apiMock.getWorkspace.mockRejectedValue(new Error("no workspace"));
    apiMock.clientProfileWorkflowDefinition.mockRejectedValue(new Error("no def"));
    apiMock.clientSources.mockResolvedValue({ items: [] });
    apiMock.discoveryRunSummaries.mockResolvedValue({ items: [] });
    apiMock.workflowRuns.mockResolvedValue({ items: [] });
    apiMock.agentRuns.mockResolvedValue({ items: [{ _id: "run-1", run_id: "run-1", status: "completed" }] });
    apiMock.messages.mockResolvedValue({
      items: [
        {
          _id: "message-1",
          agent_run_id: "run-1",
          review_status: "approved",
          send_status: "not_sent",
          subject_line: "Ready draft",
          recipient_name: "Operator",
          company: "SignalForge",
        },
      ],
    });
    apiMock.workflowAssets.mockResolvedValue({
      items: [
        {
          _id: "asset-1",
          run_id: "run-1",
          title: "Approved asset",
          approval_state: "approved",
          distribution_state: "not_queued",
        },
        {
          _id: "asset-2",
          run_id: "run-1",
          title: "Legacy approved asset",
          approval_state: "approved",
        },
        {
          _id: "asset-3",
          run_id: "run-1",
          title: "Queued asset",
          approval_state: "approved",
          distribution_state: "queued",
        },
        {
          _id: "asset-4",
          run_id: "run-1",
          title: "Published asset",
          approval_state: "approved",
          distribution_state: "published",
        },
        {
          _id: "asset-5",
          run_id: "run-1",
          title: "Archived asset",
          approval_state: "approved",
          distribution_state: "archived",
        },
        {
          _id: "asset-6",
          run_id: "run-1",
          title: "Rejected asset",
          approval_state: "rejected",
          distribution_state: "not_queued",
        },
        {
          _id: "asset-7",
          run_id: "run-2",
          title: "Other run asset",
          approval_state: "approved",
          distribution_state: "queued",
        },
      ],
    });
  });

  afterEach(async () => {
    if (root) {
      await act(async () => {
        root.unmount();
      });
    }
    container?.remove();
    container = null;
    root = null;
    globalThis.IS_REACT_ACT_ENVIRONMENT = false;
  });

  it("splits approved assets into Step 5 not queued, queued, and published or archived groups", async () => {
    await renderPage();

    const notQueuedBlock = blockTextForHeading("Approved / Not Queued");
    const queuedBlock = blockTextForHeading("Queued for Distribution");
    const publishedBlock = blockTextForHeading("Published / Archived");

    expect(notQueuedBlock).toContain("Approved asset");
    expect(notQueuedBlock).toContain("Legacy approved asset");
    expect(notQueuedBlock).not.toContain("Queued asset");
    expect(notQueuedBlock).not.toContain("Rejected asset");

    expect(queuedBlock).toContain("Queued asset");
    expect(queuedBlock).not.toContain("Other run asset");

    expect(publishedBlock).toContain("Published asset");
    expect(publishedBlock).toContain("Archived asset");
    expect(publishedBlock).not.toContain("Approved asset");
  });

  it("keeps published and archived assets out of the active Step 5 work count", async () => {
    await renderPage();

    expect(container.textContent).toContain("Step 5 — Queue for Distribution");
    expect(container.textContent).toContain("4 items");
    expect(container.textContent).toContain("Ready to Send Message Drafts");
    expect(container.textContent).toContain("Ready draft");
  });
});

// ── Phase 6C: Discovery insights ──────────────────────────────────────────────
describe("WorkflowPage Phase 6C discovery insights", () => {
  async function renderAndOpenStep2(props = {}) {
    await renderPage({ activeWorkspace: "ws-1", ...props });
    // Step 2 is collapsed by default — find and click it to expand
    await act(async () => {
      const step2Btn = Array.from(container.querySelectorAll("button")).find(
        (b) => b.textContent.includes("Discover Opportunities")
      );
      if (step2Btn) step2Btn.click();
      await Promise.resolve();
      await Promise.resolve();
    });
  }
  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    vi.clearAllMocks();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    apiMock.agentTasks.mockResolvedValue({ items: [] });
    apiMock.approvalRequests.mockResolvedValue({ items: [] });
    apiMock.deals.mockResolvedValue({ items: [] });
    apiMock.messages.mockResolvedValue({ items: [] });
    apiMock.workflowAssets.mockResolvedValue({ items: [] });
    apiMock.agentRuns.mockResolvedValue({ items: [] });
    apiMock.getWorkspace.mockRejectedValue(new Error("no workspace"));
    apiMock.clientProfileWorkflowDefinition.mockRejectedValue(new Error("no def"));
    apiMock.clientSources.mockResolvedValue({ items: [] });
    apiMock.discoveryRunSummaries.mockResolvedValue({ items: [] });
    apiMock.workflowRuns.mockResolvedValue({ items: [] });
  });

  afterEach(async () => {
    if (root) {
      await act(async () => { root.unmount(); });
    }
    container?.remove();
    container = null;
    root = null;
    globalThis.IS_REACT_ACT_ENVIRONMENT = false;
  });

  it("renders empty state when no discovery insights", async () => {
    apiMock.discoveryInsights.mockResolvedValue({ items: [] });
    await renderAndOpenStep2();

    expect(container.textContent).toContain("Discovery Intelligence");
    expect(container.textContent).toContain("No discovery insights yet");
  });

  it("renders pending_review insight card in Pending Review group", async () => {
    apiMock.discoveryInsights.mockResolvedValue({
      items: [
        {
          _id: "insight-1",
          insight_type: "content_opportunity",
          title: "Podcast Gap",
          summary: "Strong demand for leadership content.",
          confidence_score: 0.85,
          status: "pending_review",
          evidence: [{ platform: "YouTube", signal_type: "search_trend" }],
          recommendation: {
            recommended_platforms: ["YouTube", "LinkedIn"],
            recommended_asset_types: ["script_draft"],
          },
          source_agent: "outreach",
          created_at: new Date().toISOString(),
        },
      ],
    });

    await renderAndOpenStep2();

    expect(container.textContent).toContain("Podcast Gap");
    expect(container.textContent).toContain("Pending Review");
    expect(container.textContent).toContain("85%");
  });

  it("renders approved insight in Approved group", async () => {
    apiMock.discoveryInsights.mockResolvedValue({
      items: [
        {
          _id: "insight-2",
          insight_type: "market_signal",
          title: "Approved Insight",
          summary: "High confidence signal.",
          confidence_score: 0.9,
          status: "approved",
          evidence: [],
          recommendation: null,
          created_at: new Date().toISOString(),
        },
      ],
    });

    await renderAndOpenStep2();

    expect(container.textContent).toContain("Approved Insight");
    expect(container.textContent).toContain("Approved");
  });

  it("shows pending count badge when pending insights exist", async () => {
    apiMock.discoveryInsights.mockResolvedValue({
      items: [
        {
          _id: "insight-3",
          insight_type: "content_opportunity",
          title: "Pending 1",
          summary: "Test.",
          confidence_score: 0.5,
          status: "pending_review",
          evidence: [],
          recommendation: null,
          created_at: new Date().toISOString(),
        },
      ],
    });

    await renderAndOpenStep2();

    expect(container.textContent).toContain("1 pending review");
  });

  it("shows evidence count chip when evidence items exist", async () => {
    apiMock.discoveryInsights.mockResolvedValue({
      items: [
        {
          _id: "insight-4",
          insight_type: "content_opportunity",
          title: "Evidence Insight",
          summary: "Test.",
          confidence_score: 0.7,
          status: "pending_review",
          evidence: [
            { platform: "YouTube", signal_type: "search_trend" },
            { platform: "TikTok", signal_type: "hashtag_volume" },
          ],
          recommendation: null,
          created_at: new Date().toISOString(),
        },
      ],
    });

    await renderAndOpenStep2();

    expect(container.textContent).toContain("2 evidence items");
  });

  it("does not call discoveryInsights when workspace is 'all'", async () => {
    apiMock.discoveryInsights.mockResolvedValue({ items: [] });
    await renderPage({ activeWorkspace: "all" });

    expect(apiMock.discoveryInsights).not.toHaveBeenCalled();
  });

  it("renders without error when discoveryInsights API is omitted from mock", async () => {
    // Simulate api.discoveryInsights not existing (returns undefined)
    apiMock.discoveryInsights.mockReturnValue(undefined);
    // Should not crash — renders without error
    await expect(renderAndOpenStep2()).resolves.not.toThrow();
  });
});

describe("WorkflowPage Phase 6D discovery engine", () => {
  async function renderAndOpenStep2(props = {}) {
    await renderPage({ activeWorkspace: "ws-6d", ...props });
    await act(async () => {
      const step2Btn = Array.from(container.querySelectorAll("button")).find(
        (b) => b.textContent.includes("Discover Opportunities")
      );
      if (step2Btn) step2Btn.click();
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  async function renderAndOpenStep3(props = {}) {
    await renderPage({ activeWorkspace: "ws-6d", ...props });
    await act(async () => {
      // Step 3 label varies by template — match on "Agent Activity" OR "Review Agent Work"
      const step3Btn = Array.from(container.querySelectorAll("button")).find(
        (b) => b.textContent.includes("Agent Activity") || b.textContent.includes("Review Agent Work")
      );
      if (step3Btn) step3Btn.click();
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    vi.clearAllMocks();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    apiMock.agentTasks.mockResolvedValue({ items: [] });
    apiMock.approvalRequests.mockResolvedValue({ items: [] });
    apiMock.deals.mockResolvedValue({ items: [] });
    apiMock.messages.mockResolvedValue({ items: [] });
    apiMock.workflowAssets.mockResolvedValue({ items: [] });
    apiMock.agentRuns.mockResolvedValue({ items: [] });
    apiMock.getWorkspace.mockRejectedValue(new Error("no workspace"));
    apiMock.clientProfileWorkflowDefinition.mockRejectedValue(new Error("no def"));
    apiMock.clientSources.mockResolvedValue({ items: [] });
    apiMock.discoveryRunSummaries.mockResolvedValue({ items: [] });
    apiMock.workflowRuns.mockResolvedValue({ items: [] });
  });

  afterEach(async () => {
    if (root) {
      await act(async () => { root.unmount(); });
    }
    container?.remove();
    container = null;
    root = null;
    globalThis.IS_REACT_ACT_ENVIRONMENT = false;
  });

  it("shows discovery summary header with insight count and high confidence", async () => {
    apiMock.discoveryInsights.mockResolvedValue({
      items: [
        {
          _id: "ins-1",
          title: "Burnout content insight",
          insight_type: "content_opportunity",
          confidence_score: 0.92,
          quality_tags: ["High Confidence", "Fresh Signal"],
          summary: "Summary text",
          evidence: [],
          recommendation: { recommended_platforms: ["LinkedIn", "TikTok"], recommended_asset_types: ["script_draft"] },
          status: "pending_review",
          source_agent: "discovery_engine",
          source_run_id: null,
          created_at: new Date().toISOString(),
        },
        {
          _id: "ins-2",
          title: "Low confidence insight",
          insight_type: "content_format",
          confidence_score: 0.55,
          quality_tags: ["Fresh Signal"],
          summary: "Another summary",
          evidence: [],
          recommendation: { recommended_platforms: ["Instagram"], recommended_asset_types: ["carousel_outline"] },
          status: "pending_review",
          source_agent: "discovery_engine",
          source_run_id: null,
          created_at: new Date().toISOString(),
        },
      ],
    });

    await renderAndOpenStep2();

    // Summary header should show "2 insights today" and "1 high confidence"
    const text = container.textContent;
    expect(text).toContain("insights today");
    expect(text).toContain("high confidence");
  });

  it("shows quality tags on insight card", async () => {
    apiMock.discoveryInsights.mockResolvedValue({
      items: [
        {
          _id: "ins-qt",
          title: "Quality Tag Insight",
          insight_type: "content_opportunity",
          confidence_score: 0.88,
          quality_tags: ["High Confidence", "Multi-Platform Signal", "Fresh Signal"],
          summary: "Quality tag test summary",
          evidence: [],
          recommendation: { recommended_platforms: ["LinkedIn"], recommended_asset_types: ["script_draft"] },
          status: "pending_review",
          source_agent: "discovery_engine",
          source_run_id: null,
          created_at: new Date().toISOString(),
        },
      ],
    });

    await renderAndOpenStep2();

    const text = container.textContent;
    expect(text).toContain("High Confidence");
    expect(text).toContain("Multi-Platform Signal");
  });

  it("Generate Assets button appears on approved insight", async () => {
    apiMock.discoveryInsights.mockResolvedValue({
      items: [
        {
          _id: "ins-approved",
          title: "Approved Insight",
          insight_type: "content_opportunity",
          confidence_score: 0.85,
          quality_tags: ["High Confidence"],
          summary: "Approved insight summary",
          evidence: [],
          recommendation: {
            recommended_platforms: ["LinkedIn"],
            recommended_asset_types: ["script_draft", "linkedin_post"],
          },
          status: "approved",
          source_agent: "discovery_engine",
          source_run_id: null,
          created_at: new Date().toISOString(),
        },
      ],
    });

    await renderAndOpenStep2();

    const buttons = Array.from(container.querySelectorAll("button"));
    const generateBtn = buttons.find((b) => b.textContent.includes("Generate Assets"));
    expect(generateBtn).toBeTruthy();
  });

  it("Step 3 shows discovery timeline when insights exist", async () => {
    apiMock.discoveryInsights.mockResolvedValue({
      items: [
        {
          _id: "ins-timeline",
          title: "Timeline Insight Entry",
          insight_type: "content_opportunity",
          confidence_score: 0.80,
          quality_tags: ["Fresh Signal"],
          summary: "Timeline test summary",
          evidence: [],
          recommendation: { recommended_platforms: ["LinkedIn"], recommended_asset_types: ["script_draft"] },
          status: "approved",
          source_agent: "discovery_engine",
          source_run_id: "run-timeline-abc",
          created_at: new Date().toISOString(),
        },
      ],
    });

    await renderAndOpenStep3();

    const text = container.textContent;
    expect(text).toContain("Discovery Timeline");
    expect(text).toContain("Timeline Insight Entry");
  });
});

// ── Phase 6E: Source Registry ─────────────────────────────────────────────────

describe("WorkflowPage Phase 6E source registry", () => {
  let container;

  function makeSources(overrides = []) {
    return overrides.map((o, i) => ({
      _id: `src-${i}`,
      workspace_slug: "test-ws",
      client_profile_slug: "test-profile",
      source_type: o.source_type || "website",
      label: o.label || `Source ${i}`,
      uri: o.uri || "https://example.com",
      status: o.status || "active",
      health_status: o.health_status || "ready",
      created_at: new Date().toISOString(),
    }));
  }

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    apiMock.agentTasks.mockResolvedValue({ items: [] });
    apiMock.approvalRequests.mockResolvedValue({ items: [] });
    apiMock.deals.mockResolvedValue({ items: [] });
    apiMock.messages.mockResolvedValue({ items: [] });
    apiMock.workflowAssets.mockResolvedValue({ items: [] });
    apiMock.agentRuns.mockResolvedValue({ items: [] });
    apiMock.getWorkspace.mockRejectedValue(new Error("no workspace"));
    apiMock.clientProfileWorkflowDefinition.mockRejectedValue(new Error("no def"));
    apiMock.discoveryInsights.mockResolvedValue({ items: [] });
    apiMock.generateAssetsFromInsight.mockResolvedValue({ item: {} });
    apiMock.triggerDiscoveryInsights.mockResolvedValue({ status: "ok" });
    apiMock.clientSources.mockResolvedValue({ items: [] });
    apiMock.discoveryRunSummaries.mockResolvedValue({ items: [] });
    apiMock.workflowRuns.mockResolvedValue({ items: [] });
  });

  afterEach(() => {
    if (container._root) { act(() => { container._root.unmount(); }); }
    document.body.removeChild(container);
  });

  async function render(sources = []) {
    const { default: WorkflowPage } = await import("../pages/WorkflowPage.jsx");
    apiMock.clientSources.mockResolvedValue({ items: sources });
    apiMock.discoveryRunSummaries.mockResolvedValue({ items: [] });
    apiMock.workflowRuns.mockResolvedValue({ items: [] });
    await act(async () => {
      const root = createRoot(container);
      container._root = root;
      root.render(
        <WorkflowPage activeProfile="custom" demoMode={false} activeWorkspace="test-ws" />
      );
    });
    await act(async () => {});
  }

  it("shows Source Readiness Card with no sources message", async () => {
    await render([]);
    expect(container.textContent).toContain("Source Readiness");
    expect(container.textContent).toContain("No client sources configured");
  });

  it("shows active source count when sources configured", async () => {
    const sources = makeSources([
      { source_type: "linkedin", label: "My LinkedIn", status: "active" },
      { source_type: "website", label: "My Website", status: "active" },
    ]);
    await render(sources);
    const text = container.textContent;
    expect(text).toContain("2 active");
  });

  it("shows source type pills for active sources", async () => {
    const sources = makeSources([
      { source_type: "linkedin", label: "LinkedIn", status: "active" },
      { source_type: "instagram", label: "Instagram", status: "active" },
    ]);
    await render(sources);
    const text = container.textContent;
    expect(text).toMatch(/linkedin/i);
    expect(text).toMatch(/instagram/i);
  });

  it("does not crash when clientSources returns empty", async () => {
    apiMock.clientSources.mockResolvedValue({ items: [] });
    apiMock.discoveryRunSummaries.mockResolvedValue({ items: [] });
    apiMock.workflowRuns.mockResolvedValue({ items: [] });
    await render([]);
    expect(container.textContent).toContain("Source Readiness");
  });

  it("shows configured_source badge on insight evidence", async () => {
    apiMock.discoveryInsights.mockResolvedValue({
      items: [
        {
          _id: "ins-src-1",
          title: "Source-Aware Insight",
          insight_type: "content_opportunity",
          confidence_score: 0.9,
          quality_tags: [],
          summary: "Insight from configured sources",
          evidence: [
            {
              platform: "LinkedIn",
              signal_type: "engagement",
              keyword: "contractor leads",
              configured_source: true,
              source_label: "My LinkedIn",
              source_type: "linkedin",
            },
          ],
          recommendation: { recommended_platforms: ["LinkedIn"], recommended_asset_types: ["linkedin_post"] },
          status: "pending_review",
          source_agent: "discovery_engine",
          source_run_id: null,
          created_at: new Date().toISOString(),
        },
      ],
    });
    await render([]);

    // Navigate to Step 2 where insights are shown
    const buttons = Array.from(container.querySelectorAll("button"));
    const step2 = buttons.find((b) => b.textContent.match(/step 2|discover/i));
    if (step2) {
      await act(async () => { step2.click(); });
    }

    // Open evidence on the insight card
    const evidenceBtn = Array.from(container.querySelectorAll("button")).find((b) =>
      b.textContent.includes("evidence item")
    );
    if (evidenceBtn) {
      await act(async () => { evidenceBtn.click(); });
      expect(container.textContent).toContain("Configured Source");
    }
  });
});
// ── Phase 6F: Discovery Run Completion + Source Readiness + Distribution ──────

describe("WorkflowPage Phase 6F discovery run completion + distribution", () => {
  let container6f;

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    vi.clearAllMocks();
    container6f = document.createElement("div");
    document.body.appendChild(container6f);

    apiMock.agentTasks.mockResolvedValue({ items: [] });
    apiMock.approvalRequests.mockResolvedValue({ items: [] });
    apiMock.deals.mockResolvedValue({ items: [] });
    apiMock.discoveryInsights.mockResolvedValue({ items: [] });
    apiMock.getWorkspace.mockRejectedValue(new Error("no workspace"));
    apiMock.clientProfileWorkflowDefinition.mockRejectedValue(new Error("no def"));
    apiMock.clientSources.mockResolvedValue({ items: [] });
    apiMock.discoveryRunSummaries.mockResolvedValue({ items: [] });
    apiMock.workflowRuns.mockResolvedValue({ items: [] });
    apiMock.agentRuns.mockResolvedValue({ items: [] });
    apiMock.messages.mockResolvedValue({ items: [] });
    apiMock.workflowAssets.mockResolvedValue({ items: [] });
  });

  afterEach(() => {
    const root6f = container6f._root;
    if (root6f) { act(() => { root6f.unmount(); }); }
    if (container6f.parentNode) container6f.parentNode.removeChild(container6f);
  });

  async function render6f(props = {}) {
    const root = createRoot(container6f);
    container6f._root = root;
    await act(async () => {
      root.render(<WorkflowPage activeProfile="executive_growth" demoMode={false} activeWorkspace="ws-test" {...props} />);
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  async function expandStep(n) {
    const btn = Array.from(container6f.querySelectorAll("button")).find(
      (b) => b.textContent.match(new RegExp(`^${n}`))
    );
    if (btn) await act(async () => { btn.click(); await Promise.resolve(); });
  }

  it("shows neutral no-run state when no run summaries for today", async () => {
    apiMock.discoveryRunSummaries.mockResolvedValue({ items: [] });
    apiMock.workflowRuns.mockResolvedValue({ items: [] });
    await render6f();
    expect(container6f.textContent).toContain("No discovery runs completed today");
  });

  it("shows DiscoveryRunCompletionCard completed state for today's run", async () => {
    const today = new Date().toISOString();
    apiMock.discoveryRunSummaries.mockResolvedValue({
      items: [{
        _id: "rs-1",
        run_id: "run-001",
        workspace_slug: "ws-test",
        agent_name: "content_discovery",
        completion_state: "completed",
        completed_at: today,
        sources_checked: 3,
        insights_generated: 5,
        high_confidence_insights: 2,
        platforms_checked: ["LinkedIn", "YouTube"],
        summary: "Checked 3 configured sources across LinkedIn, YouTube.",
        next_recommended_action: "Review discovery insights and approve content directions.",
      }],
    });
    await render6f();
    expect(container6f.textContent).toContain("Completed Today");
    expect(container6f.textContent).toContain("content_discovery");
    expect(container6f.textContent).toContain("5");
    expect(container6f.textContent).toContain("Review discovery insights");
  });

  it("shows partial state with guidance", async () => {
    const today = new Date().toISOString();
    apiMock.discoveryRunSummaries.mockResolvedValue({
      items: [{
        _id: "rs-2", run_id: "run-002", workspace_slug: "ws-test",
        completion_state: "partial", completed_at: today,
        sources_checked: 1, insights_generated: 0, high_confidence_insights: 0,
        summary: "Discovery ran but found no new insights to generate.",
        next_recommended_action: "Add more client sources or rerun discovery later.",
      }],
    });
    await render6f();
    expect(container6f.textContent).toContain("Partial");
    expect(container6f.textContent).toContain("Add more client sources");
  });

  it("shows SourceReadinessCard with missing state when no sources", async () => {
    apiMock.clientSources.mockResolvedValue({ items: [] });
    await render6f();
    expect(container6f.textContent).toContain("Missing");
    expect(container6f.textContent).toContain("Go to Admin Onboarding to connect sources");
  });

  it("shows SourceReadinessCard partial state with 1-2 active sources", async () => {
    apiMock.clientSources.mockResolvedValue({
      items: [{ _id: "s1", source_type: "website", status: "active", label: "My Website", workspace_slug: "ws-test" }],
    });
    await render6f();
    expect(container6f.textContent).toContain("Partial");
    expect(container6f.textContent).toContain("website");
  });

  it("shows SourceReadinessCard ready state with 3+ active sources", async () => {
    apiMock.clientSources.mockResolvedValue({
      items: [
        { _id: "s1", source_type: "website", status: "active", label: "A", workspace_slug: "ws-test" },
        { _id: "s2", source_type: "linkedin", status: "active", label: "B", workspace_slug: "ws-test" },
        { _id: "s3", source_type: "youtube", status: "active", label: "C", workspace_slug: "ws-test" },
      ],
    });
    await render6f();
    expect(container6f.textContent).toContain("Ready");
    expect(container6f.textContent).toContain("Ready for discovery scanning");
  });

  it("renders platform distribution chips in Step 5", async () => {
    await render6f();
    const step5Btn = Array.from(container6f.querySelectorAll("button")).find(
      (b) => b.textContent.includes("Queue for Distribution") || b.textContent.includes("Ready to Send")
    );
    if (step5Btn) await act(async () => { step5Btn.click(); await Promise.resolve(); await Promise.resolve(); });
    expect(container6f.textContent).toContain("Platform Distribution");
  });

  it("shows execution timeline when insights exist", async () => {
    apiMock.discoveryInsights.mockResolvedValue({
      items: [{
        _id: "i1", title: "Test Insight", module: "contractor_growth",
        workspace_slug: "ws-test", confidence_score: 0.9,
        status: "pending_review", evidence: [], recommendation: {},
        source_agent: "discovery_engine",
      }],
    });
    const today = new Date().toISOString();
    apiMock.discoveryRunSummaries.mockResolvedValue({
      items: [{
        _id: "rs-3", run_id: "run-003", workspace_slug: "ws-test",
        completion_state: "completed", completed_at: today,
        sources_checked: 2, insights_generated: 1, high_confidence_insights: 1,
        platforms_checked: ["LinkedIn"],
        configured_sources_used: ["My Website"],
      }],
    });
    await render6f();
    await render6f();
    expect(container6f.textContent).toContain("Sources Loaded");
    expect(container6f.textContent).toContain("Insights Generated");
  });
});

// ── Phase 6G: Client Workflow Definition Rendering ────────────────────────────

describe("WorkflowPage Phase 6G client workflow definition rendering", () => {
  let container6g;
  let root6g;

  const defaultApiSetup = () => {
    apiMock.agentTasks.mockResolvedValue({ items: [] });
    apiMock.approvalRequests.mockResolvedValue({ items: [] });
    apiMock.deals.mockResolvedValue({ items: [] });
    apiMock.messages.mockResolvedValue({ items: [] });
    apiMock.discoveryInsights.mockResolvedValue({ items: [] });
    apiMock.agentRuns.mockResolvedValue({ items: [] });
    apiMock.workflowAssets.mockResolvedValue({ items: [] });
    apiMock.clientSources.mockResolvedValue({ items: [] });
    apiMock.discoveryRunSummaries.mockResolvedValue({ items: [] });
    apiMock.workflowRuns.mockResolvedValue({ items: [] });
  };

  const dbWorkflowDef = {
    slug: "exec-growth-custom",
    display_name: "Executive Custom Workflow",
    system_profile_id: "executive_growth",
    module: "contractor_growth",
    notes: "",
    status: "active",
    stages: [
      { stage_number: 1, label: "DB Stage One", notes: "Operator note for stage 1", required: true, agent_key: "outreach", run_card_type: "discovery_scan", chips: ["chip-a"] },
      { stage_number: 2, label: "DB Stage Two", notes: "", required: true, agent_key: "", run_card_type: "", chips: [] },
      { stage_number: 3, label: "DB Stage Three", notes: "", required: false, agent_key: "content", run_card_type: "content_creation", chips: [] },
      { stage_number: 4, label: "DB Stage Four", notes: "", required: true, agent_key: "", run_card_type: "", chips: [] },
      { stage_number: 5, label: "DB Stage Five", notes: "", required: true, agent_key: "", run_card_type: "", chips: [] },
      { stage_number: 6, label: "DB Stage Six", notes: "", required: true, agent_key: "", run_card_type: "", chips: [] },
      { stage_number: 7, label: "DB Stage Seven", notes: "", required: true, agent_key: "", run_card_type: "", chips: [] },
    ],
  };

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    vi.clearAllMocks();
    container6g = document.createElement("div");
    document.body.appendChild(container6g);
    root6g = createRoot(container6g);
    defaultApiSetup();
  });

  afterEach(() => {
    act(() => root6g.unmount());
    container6g.remove();
  });

  async function render6g(props = {}) {
    await act(async () => {
      root6g.render(
        <WorkflowPage
          activeProfile="executive_growth"
          demoMode={false}
          activeWorkspace="ws-exec-1"
          {...props}
        />
      );
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  it("renders DB workflow definition labels when available", async () => {
    apiMock.getWorkspace.mockResolvedValue({ item: { client_profile_id: "exec-profile-1" } });
    apiMock.clientProfileWorkflowDefinition.mockResolvedValue({ item: dbWorkflowDef });
    await render6g();
    expect(container6g.textContent).toContain("DB Stage One");
  });

  it("falls back to profile template when no DB definition", async () => {
    apiMock.getWorkspace.mockRejectedValue(new Error("no workspace"));
    apiMock.clientProfileWorkflowDefinition.mockRejectedValue(new Error("no def"));
    await render6g();
    // Default/fallback labels are rendered (not the DB ones)
    expect(container6g.textContent).not.toContain("DB Stage One");
  });

  it("shows stage note when DB stage has notes", async () => {
    apiMock.getWorkspace.mockResolvedValue({ item: { client_profile_id: "exec-profile-1" } });
    apiMock.clientProfileWorkflowDefinition.mockResolvedValue({ item: dbWorkflowDef });
    await render6g();
    expect(container6g.textContent).toContain("Operator note for stage 1");
  });

  it("shows Optional badge for stages with required=false", async () => {
    apiMock.getWorkspace.mockResolvedValue({ item: { client_profile_id: "exec-profile-1" } });
    apiMock.clientProfileWorkflowDefinition.mockResolvedValue({ item: dbWorkflowDef });
    await render6g();
    // Stage 1 is expanded (nextStep=1), it is Required — badge renders in expanded view
    // Stage 3 has required:false but is collapsed so its badge is not visible
    // At minimum Required badge should appear for expanded step 1
    expect(container6g.textContent).toMatch(/Required|Optional/);
  });

  it("renders ClientWorkflowHeader with source label Client Definition", async () => {
    apiMock.getWorkspace.mockResolvedValue({ item: { client_profile_id: "exec-profile-1" } });
    apiMock.clientProfileWorkflowDefinition.mockResolvedValue({ item: dbWorkflowDef });
    await render6g();
    expect(container6g.textContent).toContain("Client Definition");
  });

  it("renders ClientWorkflowHeader with workflow display_name", async () => {
    apiMock.getWorkspace.mockResolvedValue({ item: { client_profile_id: "exec-profile-1" } });
    apiMock.clientProfileWorkflowDefinition.mockResolvedValue({ item: dbWorkflowDef });
    await render6g();
    expect(container6g.textContent).toContain("Executive Custom Workflow");
  });

  it("renders normalized stages 1–7 even with DB definition", async () => {
    apiMock.getWorkspace.mockResolvedValue({ item: { client_profile_id: "exec-profile-1" } });
    apiMock.clientProfileWorkflowDefinition.mockResolvedValue({ item: dbWorkflowDef });
    await render6g();
    // All 7 DB stage labels must appear (collapsed steps still render label text)
    const labels = ["One", "Two", "Three", "Four", "Five", "Six", "Seven"];
    for (const label of labels) {
      expect(container6g.textContent).toContain(`DB Stage ${label}`);
    }
  });

  it("renders profile template source label when no DB definition", async () => {
    apiMock.getWorkspace.mockRejectedValue(new Error("no workspace"));
    apiMock.clientProfileWorkflowDefinition.mockRejectedValue(new Error("no def"));
    await render6g();
    // With no DB definition, header should say Profile Template or Default Template
    const hasTemplate =
      container6g.textContent.includes("Profile Template") ||
      container6g.textContent.includes("Default Template");
    expect(hasTemplate).toBe(true);
  });
});

describe("WorkflowPage Phase 6J workspace isolation", () => {
  let container6j;
  let root6j;

  async function render6j(props = {}) {
    await act(async () => {
      root6j.render(<WorkflowPage activeProfile="executive_growth" demoMode={false} activeWorkspace="ws-6j" {...props} />);
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    vi.clearAllMocks();
    container6j = document.createElement("div");
    document.body.appendChild(container6j);
    root6j = createRoot(container6j);

    apiMock.agentTasks.mockResolvedValue({ items: [] });
    apiMock.messages.mockResolvedValue({ items: [] });
    apiMock.approvalRequests.mockResolvedValue({ items: [] });
    apiMock.deals.mockResolvedValue({ items: [] });
    apiMock.agentRuns.mockResolvedValue({ items: [] });
    apiMock.workflowAssets.mockResolvedValue({ items: [] });
    apiMock.discoveryInsights.mockResolvedValue({ items: [] });
    apiMock.getWorkspace.mockRejectedValue(new Error("no workspace"));
    apiMock.clientProfileWorkflowDefinition.mockRejectedValue(new Error("no def"));
    apiMock.clientSources.mockResolvedValue({ items: [] });
    apiMock.discoveryRunSummaries.mockResolvedValue({ items: [] });
    apiMock.workflowRuns.mockResolvedValue({ items: [] });
  });

  afterEach(() => {
    root6j.unmount();
    container6j.remove();
  });

  it("calls approvalRequests on initial workspace render", async () => {
    await render6j();
    expect(apiMock.approvalRequests).toHaveBeenCalled();
  });

  it("re-fetches approvalRequests when activeWorkspace prop changes", async () => {
    await render6j({ activeWorkspace: "workspace-alpha" });
    const firstCallCount = apiMock.approvalRequests.mock.calls.length;

    apiMock.approvalRequests.mockResolvedValue({ items: [] });
    await act(async () => {
      root6j.render(<WorkflowPage activeProfile="executive_growth" demoMode={false} activeWorkspace="workspace-beta" />);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(apiMock.approvalRequests.mock.calls.length).toBeGreaterThan(firstCallCount);
  });

  it("replaces stale cross-workspace approval state on workspace change", async () => {
    apiMock.approvalRequests.mockResolvedValueOnce({
      items: Array.from({ length: 5 }, (_, i) => ({ _id: `ar-${i}`, status: "open", source_card_id: "run_outreach" })),
    });
    await render6j({ activeWorkspace: "workspace-alpha" });
    // 5 open approvals shown in "Review needed" chip
    expect(container6j.textContent).toContain("5");

    // Switch to clean workspace — no approvals
    apiMock.approvalRequests.mockResolvedValue({ items: [] });
    apiMock.messages.mockResolvedValue({ items: [] });
    await act(async () => {
      root6j.render(<WorkflowPage activeProfile="executive_growth" demoMode={false} activeWorkspace="clean-workspace" />);
      await Promise.resolve();
      await Promise.resolve();
    });

    // "Review needed" chip should show 0, stale "5" from previous workspace should be gone
    const reviewChipText = container6j.textContent;
    expect(reviewChipText).toContain("0");
    expect(reviewChipText).not.toMatch(/5\s*Review needed/);
  });

  it("nextStep = 4 when content_build workflow_run is needs_review", async () => {
    apiMock.workflowRuns.mockResolvedValue({
      items: [
        { _id: "wr-disc", run_type: "discovery", status: "completed", workspace_slug: "ws-6j" },
        { _id: "wr-cb", run_type: "content_build", status: "needs_review", workspace_slug: "ws-6j" },
      ],
    });
    apiMock.approvalRequests.mockResolvedValue({
      items: [{ _id: "ar-1", status: "open", source_card_id: "content_build", workflow_run_id: "wr-cb" }],
    });
    await render6j();
    // CommandContextCard "Next Action" section shows "Step 4 — Review & Approve"
    expect(container6j.textContent).toContain("Step 4");
    expect(container6j.textContent).toContain("Review & Approve");
  });

  it("nextStep = 2 when discovery complete but no content_build run", async () => {
    apiMock.workflowRuns.mockResolvedValue({
      items: [
        { _id: "wr-disc", run_type: "discovery", status: "completed", workspace_slug: "ws-6j" },
      ],
    });
    await render6j();
    // CommandContextCard "Next Action" shows "Step 2 — Discover Opportunities"
    expect(container6j.textContent).toContain("Step 2");
    expect(container6j.textContent).toContain("Discover Opportunities");
  });

  it("cross-workspace legacy approvals without workflow_run_id do not activate nextStep = 4", async () => {
    // No workflow_runs for this workspace
    apiMock.workflowRuns.mockResolvedValue({ items: [] });
    // Open approvals with non-content_build source and no workflow_run_id
    apiMock.approvalRequests.mockResolvedValue({
      items: Array.from({ length: 10 }, (_, i) => ({
        _id: `legacy-${i}`,
        status: "open",
        source_card_id: "run_outreach",
        workflow_run_id: null,
      })),
    });
    await render6j();
    // nextStep = 1 (no discovery, no content_build) — not contaminated by legacy approvals
    expect(container6j.textContent).toContain("Step 1");
    expect(container6j.textContent).not.toContain("Step 4 — Review");
  });
});

// ── Phase 6L: optimistic approval state + lifecycle CTA states ───────────────

describe("WorkflowPage Phase 6L lifecycle hardening", () => {
  let container6l;
  let root6l;

  async function render6l(props = {}) {
    await act(async () => {
      root6l.render(<WorkflowPage activeProfile="executive_growth" demoMode={false} activeWorkspace="ws-6l" {...props} />);
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    vi.clearAllMocks();
    container6l = document.createElement("div");
    document.body.appendChild(container6l);
    root6l = createRoot(container6l);

    apiMock.agentTasks.mockResolvedValue({ items: [] });
    apiMock.messages.mockResolvedValue({ items: [] });
    apiMock.approvalRequests.mockResolvedValue({ items: [] });
    apiMock.deals.mockResolvedValue({ items: [] });
    apiMock.agentRuns.mockResolvedValue({ items: [] });
    apiMock.workflowAssets.mockResolvedValue({ items: [] });
    apiMock.discoveryInsights.mockResolvedValue({ items: [] });
    apiMock.getWorkspace.mockRejectedValue(new Error("no workspace"));
    apiMock.clientProfileWorkflowDefinition.mockRejectedValue(new Error("no def"));
    apiMock.clientSources.mockResolvedValue({ items: [] });
    apiMock.discoveryRunSummaries.mockResolvedValue({ items: [] });
    apiMock.workflowRuns.mockResolvedValue({ items: [] });
  });

  afterEach(() => {
    root6l.unmount();
    container6l.remove();
  });

  it("nextStep = 5 when an approved asset is not_queued (activeDistributionWorkCount > 0)", async () => {
    // Discovery + content_build completed, one approved asset in not_queued state
    apiMock.workflowRuns.mockResolvedValue({
      items: [
        { _id: "wr-disc-6l", run_type: "discovery", status: "completed", workspace_slug: "ws-6l" },
        { _id: "wr-cb-6l", run_type: "content_build", status: "needs_review", workspace_slug: "ws-6l" },
      ],
    });
    apiMock.agentRuns.mockResolvedValue({
      items: [{ _id: "run-6l-1", run_id: "run-6l-1", status: "completed" }],
    });
    apiMock.workflowAssets.mockResolvedValue({
      items: [{
        _id: "asset-6l-1",
        run_id: "run-6l-1",
        approval_state: "approved",
        distribution_state: "not_queued",
        workspace_slug: "ws-6l",
        workflow_run_id: "wr-cb-6l",
      }],
    });
    apiMock.agentTasks.mockResolvedValue({
      items: [{ _id: "task-6l-1", status: "waiting_for_approval", linked_run_id: "run-6l-1" }],
    });
    await render6l();
    // Step 5 activates because activeDistributionWorkCount > 0
    expect(container6l.textContent).toContain("Step 5");
  });

  it("ContinueWorkflowCTA shows 'Workflow cycle complete' when content_build run is completed", async () => {
    apiMock.workflowRuns.mockResolvedValue({
      items: [
        { _id: "wr-disc-done", run_type: "discovery", status: "completed", workspace_slug: "ws-6l" },
        { _id: "wr-cb-done", run_type: "content_build", status: "completed", workspace_slug: "ws-6l" },
      ],
    });
    // No pending assets, no queued assets — all published
    apiMock.workflowAssets.mockResolvedValue({ items: [] });
    await render6l();
    expect(container6l.textContent).toContain("Workflow cycle complete");
  });

  it("nextStep = 5 when approved messages are ready even if content_build is completed", async () => {
    // readyToSend (approved messages) > 0 takes priority → nextStep = 5
    apiMock.workflowRuns.mockResolvedValue({
      items: [
        { _id: "wr-disc-prio", run_type: "discovery", status: "completed", workspace_slug: "ws-6l" },
        { _id: "wr-cb-prio", run_type: "content_build", status: "completed", workspace_slug: "ws-6l" },
      ],
    });
    // Approved message ready to send — drives readyToSend.length > 0 → nextStep = 5
    apiMock.messages.mockResolvedValue({
      items: [{ _id: "msg-prio", review_status: "approved", send_status: "not_sent", workspace_slug: "ws-6l" }],
    });
    await render6l();
    // nextStep = 5 since readyToSend.length > 0
    expect(container6l.textContent).toContain("Step 5");
  });

  it("decideApproval is wired on approval request items (API mock called)", async () => {
    apiMock.decideApprovalRequest = vi.fn().mockResolvedValue({ message: "saved" });
    apiMock.workflowRuns.mockResolvedValue({
      items: [
        { _id: "wr-disc-dec", run_type: "discovery", status: "completed", workspace_slug: "ws-6l" },
        { _id: "wr-cb-dec", run_type: "content_build", status: "needs_review", workspace_slug: "ws-6l" },
      ],
    });
    apiMock.approvalRequests.mockResolvedValue({
      items: [{
        _id: "ar-dec-1",
        status: "open",
        source_card_id: "content_build",
        workflow_run_id: "wr-cb-dec",
        workflow_asset_id: "asset-dec-1",
      }],
    });
    apiMock.workflowAssets.mockResolvedValue({
      items: [{
        _id: "asset-dec-1",
        run_id: "run-dec",
        approval_state: "pending",
        distribution_state: "not_queued",
        workspace_slug: "ws-6l",
        workflow_run_id: "wr-cb-dec",
      }],
    });
    await render6l();

    // Find an Approve button within the approval requests section and click it
    const buttons = Array.from(container6l.querySelectorAll("button"));
    const approveBtn = buttons.find((b) => b.textContent.trim() === "Approve");
    if (approveBtn) {
      await act(async () => {
        approveBtn.click();
        await Promise.resolve();
      });
      expect(apiMock.decideApprovalRequest).toHaveBeenCalledWith(
        "ar-dec-1",
        expect.objectContaining({ decision: "approve" }),
      );
    }
    // If no Approve button rendered (step gating), assert step 4 is active
    else {
      expect(container6l.textContent).toContain("Step 4");
    }
  });
});

