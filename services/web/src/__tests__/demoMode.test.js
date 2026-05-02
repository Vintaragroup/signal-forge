/**
 * demoMode.test.js
 *
 * Tests for localStorage-based Demo Mode:
 * - isDemoModeEnabled / startDemoMode / stopDemoMode persistence
 * - resetDemoData restores seeded records
 * - demoItems returns records with is_demo: true
 * - api wrapper routes demo calls to localStorage (no fetch)
 * - api wrapper routes real-mode calls to fetch (backend)
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  isDemoModeEnabled,
  startDemoMode,
  stopDemoMode,
  resetDemoData,
  demoItems,
} from "../demoMode.js";

// api must be imported AFTER demoMode so its module-level demoEnabled() reads
// from the same localStorage that the test has manipulated.
// We import it dynamically inside each test group where needed.

// ─────────────────────────────────────────────
// localStorage is provided by jsdom automatically.
// ─────────────────────────────────────────────

beforeEach(() => {
  localStorage.clear();
  // Suppress window event listener warnings in jsdom
  vi.restoreAllMocks();
});

// ─────────────────────────────────────────────
// isDemoModeEnabled
// ─────────────────────────────────────────────
describe("isDemoModeEnabled", () => {
  it("returns false when localStorage is empty", () => {
    expect(isDemoModeEnabled()).toBe(false);
  });

  it("returns false when key is set to 'false'", () => {
    localStorage.setItem("signalforge.demo.enabled", "false");
    expect(isDemoModeEnabled()).toBe(false);
  });
});

// ─────────────────────────────────────────────
// startDemoMode / stopDemoMode
// ─────────────────────────────────────────────
describe("startDemoMode / stopDemoMode", () => {
  it("startDemoMode sets enabled key to 'true'", () => {
    startDemoMode();
    expect(localStorage.getItem("signalforge.demo.enabled")).toBe("true");
    expect(isDemoModeEnabled()).toBe(true);
  });

  it("stopDemoMode sets enabled key to 'false'", () => {
    startDemoMode();
    stopDemoMode();
    expect(isDemoModeEnabled()).toBe(false);
  });

  it("startDemoMode seeds state records into localStorage", () => {
    startDemoMode();
    const raw = localStorage.getItem("signalforge.demo.state");
    expect(raw).not.toBeNull();
    const state = JSON.parse(raw);
    expect(Array.isArray(state.contacts)).toBe(true);
    expect(state.contacts.length).toBeGreaterThan(0);
  });
});

// ─────────────────────────────────────────────
// resetDemoData
// ─────────────────────────────────────────────
describe("resetDemoData", () => {
  it("restores exactly 2 seeded contacts", () => {
    startDemoMode();
    // Simulate mutation: remove contacts
    const state = JSON.parse(localStorage.getItem("signalforge.demo.state"));
    state.contacts = [];
    localStorage.setItem("signalforge.demo.state", JSON.stringify(state));

    const fresh = resetDemoData();
    expect(fresh.contacts.length).toBe(2);
  });

  it("restored contacts have is_demo: true", () => {
    startDemoMode();
    const fresh = resetDemoData();
    expect(fresh.contacts.every((c) => c.is_demo === true)).toBe(true);
  });

  it("restored contacts come from seed (not modified state)", () => {
    startDemoMode();
    // Mutate name in state
    const state = JSON.parse(localStorage.getItem("signalforge.demo.state"));
    state.contacts[0].name = "Mutated Name";
    localStorage.setItem("signalforge.demo.state", JSON.stringify(state));

    const fresh = resetDemoData();
    expect(fresh.contacts[0].name).not.toBe("Mutated Name");
  });
});

// ─────────────────────────────────────────────
// demoItems
// ─────────────────────────────────────────────
describe("demoItems", () => {
  it("returns an array with is_demo:true items after startDemoMode", () => {
    startDemoMode();
    const contacts = demoItems("contacts");
    expect(Array.isArray(contacts)).toBe(true);
    expect(contacts.length).toBeGreaterThan(0);
    expect(contacts.every((c) => c.is_demo === true)).toBe(true);
  });

  it("returns empty array for unknown collection", () => {
    startDemoMode();
    const result = demoItems("unknown_collection");
    expect(result).toEqual([]);
  });
});

// ─────────────────────────────────────────────
// API wrapper — demo mode (no fetch)
// ─────────────────────────────────────────────
describe("api wrapper in demo mode", () => {
  it("contacts() does not call fetch in demo mode", async () => {
    startDemoMode();
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    const { api } = await import("../api.js");
    await api.contacts({ limit: "10" });

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("contacts() returns demo records in demo mode", async () => {
    startDemoMode();
    const { api } = await import("../api.js");
    const result = await api.contacts({ limit: "10" });
    expect(result.items.every((c) => c.is_demo === true)).toBe(true);
  });

  it("leads() does not call fetch in demo mode", async () => {
    startDemoMode();
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const { api } = await import("../api.js");
    await api.leads({ limit: "10" });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────
// API wrapper — real mode (calls fetch)
// ─────────────────────────────────────────────
describe("api wrapper in real mode", () => {
  it("contacts() calls fetch when demo mode is off", async () => {
    stopDemoMode();
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0 }),
    });

    const { api } = await import("../api.js");
    await api.contacts({ limit: "10" });
    expect(fetchSpy).toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────
// ModeBanner rendering
// ─────────────────────────────────────────────
// Note: React component rendering tests require @testing-library/react.
// Those are skipped here to keep the test setup lightweight (jsdom only).
// The banner render is validated by the Vite build step.
