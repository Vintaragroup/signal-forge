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