# Modes and Demo Guide

## Overview

SignalForge operates in one of two modes at all times:

| Mode | Data Source | MongoDB | Outbound Sends |
|------|-------------|---------|----------------|
| **Real Mode** | Local MongoDB | Read + Write | Never automated |
| **Demo Mode** | Browser localStorage | Never touched | Never sent |

The current mode is always visible in the header (blue = Real, purple = Demo) and in the persistent banner below the header.

---

## Real Mode

**What it does:**
- Reads contacts, leads, messages, deals, and logs from your local MongoDB instance.
- Writes all operator actions (import, score, status updates, deal outcomes) to MongoDB.
- Agent tasks run as dry-run or review-only — no outbound automation.

**What data is affected:**
- All data lives in the local MongoDB Docker container (`mongodb://mongodb:27017/signalforge`).
- No data is sent to any external service without a manual operator action outside the system.

**Safety:**
- SignalForge does not send automated messages in any mode.
- Every outreach draft requires human approval before a manual send outside the platform.
- No real mode action touches a live CRM or email provider.

---

## Demo Mode

**What it is:**
- A fully self-contained walkthrough using seeded synthetic data stored only in your browser's localStorage.
- Used to show clients, investors, or new operators how the system works end-to-end.

**How to start:**
1. Click the mode button in the top-right header (shows **Real Mode** by default).
2. A confirmation dialog appears — review the safety note and click **Enter Demo Mode**.
3. The header turns purple, and the Demo Mode banner appears at the top of every page.

**How to stop:**
1. Click the purple **Demo Mode** button in the header.
2. Confirm the switch in the dialog — system returns to Real Mode.

**How to reset:**
- Click **Reset Demo Data** on the Demo Mode page or on any page with the purple page banner.
- This clears the current demo state and reloads the original seeded records.
- MongoDB is **never touched** by a reset.

**What's synthetic:**
- 2 contacts (Maya Rivera / Demo Apex Roofing, Eli Hart / Demo Northline HVAC)
- 2 leads, 1 outreach draft, 1 simulated response, 1 demo deal
- All records have `is_demo: true` and are labeled **DEMO** in the UI
- All email addresses use `.invalid` domains — they can never be sent to

**What Demo Mode does NOT do:**
- Read from or write to MongoDB
- Call any backend API for record operations
- Run GPT, agents, or any external service
- Persist data if the browser clears localStorage

---

## Mode Switcher UI

The mode switcher is always in the top-right of the header:

- **Blue outline button** (`Real Mode`) — current mode is Real
- **Purple filled button** (`Demo Mode`) — current mode is Demo
- Hover the button for a tooltip explaining the current mode
- Click to initiate a switch — a confirmation dialog appears before any change takes effect

The persistent banner below the header also shows the current mode:
- **Purple banner** (bold, high-contrast) — Demo Mode active
- **Light blue banner** (subtle) — Real Mode active

---

## Overview Page Checklists

The Overview page shows a mode-specific checklist:

### Real Mode: "Ready for Real Test Campaign"
1. Import candidates
2. Review candidates
3. Convert to contacts / leads
4. Run outreach agent
5. Review drafts / approvals
6. Log manual sends / responses
7. Generate report

### Demo Mode: "Demo Walkthrough"
1. Start demo
2. Run outreach
3. Review draft
4. Simulate response
5. Show deal outcome

Items auto-check based on KPI counts from the current session state.

---

## Settings / Help Section

The bottom of the Overview page contains a **Mode Reference** card that explains both modes side-by-side and links to this guide. It is always visible regardless of current mode.
