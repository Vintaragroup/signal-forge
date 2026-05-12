/**
 * Route Registry — single declarative source of truth for every route.
 *
 * Fields:
 *   id           — hash key used in window.location.hash
 *   label        — display name used in the header title and tooltips
 *   icon         — Lucide icon component
 *   group        — nav group id this route belongs to
 *   primary      — true = this route is the default entry-point for its group
 */

import {
  Activity,
  Bot,
  Briefcase,
  Building2,
  Clapperboard,
  ClipboardCheck,
  FileText,
  Gauge,
  ListChecks,
  Mail,
  PenLine,
  SearchCheck,
  Users,
  Workflow,
} from "lucide-react";

export const ROUTES = [
  // ── Command Center ───────────────────────────────────────────────────────
  { id: "workflow",        label: "Workflow",         icon: Workflow,      group: "command-center",  primary: true  },
  { id: "approvals",       label: "Approvals",        icon: ClipboardCheck, group: "command-center", primary: false },
  { id: "agent-tasks",     label: "Agent Tasks",      icon: ListChecks,    group: "command-center",  primary: false },

  // ── CRM ──────────────────────────────────────────────────────────────────
  { id: "pipeline",        label: "Pipeline",         icon: Users,         group: "crm",             primary: true  },
  { id: "messages",        label: "Messages",         icon: Mail,          group: "crm",             primary: false },
  { id: "deals",           label: "Deals",            icon: Building2,     group: "crm",             primary: false },
  { id: "research-tools",  label: "Research / Tools", icon: SearchCheck,   group: "crm",             primary: false },

  // ── Campaign Studio ───────────────────────────────────────────────────────
  { id: "creative-studio", label: "Creative Studio",  icon: PenLine,       group: "campaign-studio", primary: true  },

  // ── Analytics ─────────────────────────────────────────────────────────────
  { id: "overview",        label: "Overview",         icon: Gauge,         group: "analytics",       primary: true  },
  { id: "reports",         label: "Reports",          icon: FileText,      group: "analytics",       primary: false },

  // ── System ────────────────────────────────────────────────────────────────
  { id: "workspaces",      label: "Workspaces",       icon: Briefcase,     group: "system",          primary: true  },
  { id: "agents",          label: "Agent Console",    icon: Bot,           group: "system",          primary: false },
  { id: "gpt-diagnostics", label: "GPT Diagnostics",  icon: Activity,      group: "system",          primary: false },
  { id: "demo",            label: "Demo Mode",        icon: Clapperboard,  group: "system",          primary: false },
];

/** Keyed by route id — O(1) lookups for active-group detection and title derivation. */
export const ROUTE_MAP = Object.fromEntries(ROUTES.map((r) => [r.id, r]));
