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