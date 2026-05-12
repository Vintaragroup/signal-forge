/**
 * Nav Groups — the five primary navigation sections shown in the Sidebar.
 *
 * Fields:
 *   id           — matches the `group` field in ROUTES
 *   label        — display label for the sidebar button
 *   icon         — Lucide icon component
 *   defaultRoute — hash route navigated to when the group button is clicked
 */

import { BarChart3, LayoutDashboard, PenLine, Settings, Users } from "lucide-react";

export const NAV_GROUPS = [
  {
    id: "command-center",  label: "Command Center",  icon: LayoutDashboard, defaultRoute: "workflow",
    subRoutes: ["workflow", "approvals", "agent-tasks"],
  },
  {
    id: "crm",             label: "CRM",             icon: Users,           defaultRoute: "pipeline",
    subRoutes: ["pipeline", "messages", "deals", "research-tools"],
  },
  {
    id: "campaign-studio", label: "Campaign Studio", icon: PenLine,         defaultRoute: "creative-studio",
    subRoutes: ["creative-studio"],
  },
  {
    id: "analytics",       label: "Analytics",       icon: BarChart3,       defaultRoute: "overview",
    subRoutes: ["overview", "reports"],
  },
  {
    id: "system",          label: "System",          icon: Settings,        defaultRoute: "workspaces",
    subRoutes: ["workspaces", "admin-onboarding", "agents", "gpt-diagnostics", "demo"],
  },
];
