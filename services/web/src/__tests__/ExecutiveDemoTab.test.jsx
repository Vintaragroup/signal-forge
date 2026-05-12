import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ExecutiveDemoTab from "../components/ExecutiveDemoTab.jsx";
import { startDemoMode, stopDemoMode } from "../demoMode.js";

let container;
let root;

async function renderComponent(props) {
  await act(async () => {
    root.render(<ExecutiveDemoTab {...props} />);
  });
}

describe("ExecutiveDemoTab", () => {
  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    localStorage.clear();
    startDemoMode();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
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
    stopDemoMode();
    vi.restoreAllMocks();
  });

  it("renders the executive landing summary and current phase story", async () => {
    const onNavigate = vi.fn();
    await renderComponent({ demoMode: true, onNavigate });

    expect(container.textContent).toContain("SignalForge Executive Command Mode");
    expect(container.textContent).toContain("Executive Runbook");
    expect(container.textContent).toContain("Presenter Mode");
    expect(container.textContent).toContain("Campaign Timeline Replay");
    expect(container.textContent).toContain("Audience Journey Visualization");
    expect(container.textContent).toContain("John Maxwell Executive Growth Engine");
    expect(container.textContent).toContain("SignalForge turns long-form thought leadership into a measurable content, engagement, and revenue funnel.");
    expect(container.textContent).toContain("Content Engine");
    expect(container.textContent).toContain("What is happening now");
    expect(container.textContent).toContain("Business implication");
  });

  it("renders presentation states for screenshot-safe command mode scenes", async () => {
    await renderComponent({ demoMode: true, onNavigate: vi.fn() });

    expect(container.textContent).toContain("State 1 · Pre-launch campaign setup");
    expect(container.textContent).toContain("State 5 · Executive performance overview");
    expect(container.textContent).toContain("State A · Executive Command Overview");
    expect(container.textContent).toContain("Investor Deck");
    expect(container.textContent).toContain("Launch Command Mode");
  });

  it("self-heals stale demo state when phase 4 runbook data is missing", async () => {
    const raw = JSON.parse(localStorage.getItem("signalforge.demo.state"));
    raw.executive_demo.runbook_scenes = [];
    raw.executive_demo.export_modes = [];
    raw.executive_demo.screenshot_states = [];
    localStorage.setItem("signalforge.demo.state", JSON.stringify(raw));

    await renderComponent({ demoMode: true, onNavigate: vi.fn() });

    expect(container.textContent).toContain("Opening Statement");
    expect(container.textContent).toContain("Investor Deck");
  });

  it("self-heals stale phase 5 media workflow state", async () => {
    const raw = JSON.parse(localStorage.getItem("signalforge.demo.state"));
    raw.executive_audio_clips = [];
    raw.executive_content_ideas = [];
    raw.asset_renders = (raw.asset_renders || []).map((item) => ({
      ...item,
      preview_url: "https://placehold.co/540x960/1e293b/ffffff?text=stale",
    }));
    raw.campaign_packs = (raw.campaign_packs || []).map((item) => ({
      ...item,
      render_ids: ["demo-render-1", "demo-render-2"],
    }));
    localStorage.setItem("signalforge.demo.state", JSON.stringify(raw));

    await renderComponent({ demoMode: true, onNavigate: vi.fn() });

    expect(container.textContent).toContain("Local media playback enabled");
    expect(container.textContent).toContain("Playable faceless demo renders");
    expect(container.textContent).toContain("Demo: John Maxwell Executive Growth Pack");
  });

  it("jumps scenes through the guided runbook flow", async () => {
    await renderComponent({ demoMode: true, onNavigate: vi.fn() });

    const sceneButton = Array.from(container.querySelectorAll("button")).find((item) => item.textContent.includes("Scene 7") && item.textContent.includes("Executive Summary"));
    expect(sceneButton).toBeTruthy();

    await act(async () => {
      sceneButton.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(container.textContent).toContain("SignalForge operates as an intelligent growth engine.");
    expect(container.textContent).toContain("Projected Conversion Layer");
  });

  it("can switch to an export-safe presentation mode", async () => {
    await renderComponent({ demoMode: true, onNavigate: vi.fn() });

    const investorButton = Array.from(container.querySelectorAll("button")).find((item) => item.textContent.trim() === "Investor Deck");
    expect(investorButton).toBeTruthy();

    await act(async () => {
      investorButton.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(container.textContent).toContain("Ultra-clean KPI framing with revenue and operating leverage emphasis.");
    expect(container.textContent).toContain("Show Presenter Mode");
  });

  it("opens the linked creative studio surface from the active phase", async () => {
    const onNavigate = vi.fn();
    await renderComponent({ demoMode: true, onNavigate });

    const button = Array.from(container.querySelectorAll("button")).find((item) => item.textContent.includes("Open Linked Surface"));
    expect(button).toBeTruthy();

    await act(async () => {
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(onNavigate).toHaveBeenCalledWith("ingest");
  });

  it("renders the operational media workflow proof layer", async () => {
    await renderComponent({ demoMode: true, onNavigate: vi.fn() });

    expect(container.textContent).toContain("Real Workflow Media Demonstration");
    expect(container.textContent).toContain("Operational proof: one John Maxwell media source becomes a repeatable short-form growth workflow.");
    expect(container.textContent).toContain("Clarity Under Pressure");
    expect(container.textContent).toContain("Playable faceless demo renders");
    expect(container.textContent).toContain("Demo: John Maxwell Executive Growth Pack");
  });

  it("renders the non-demo safety message when demo mode is off", async () => {
    await renderComponent({ demoMode: false, onNavigate: vi.fn() });

    expect(container.textContent).toContain("Switch to Demo Mode to open the executive walkthrough.");
    expect(container.textContent).not.toContain("John Maxwell Executive Growth Engine");
  });
});
