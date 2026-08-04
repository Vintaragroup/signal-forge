import { useEffect, useMemo, useState } from "react";
import { BarChart3, RefreshCw } from "lucide-react";
import Sidebar from "./components/Sidebar.jsx";
import Header from "./components/Header.jsx";
import ModeBanner from "./components/ModeBanner.jsx";
import ModeConfirmModal from "./components/ModeConfirmModal.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";
import DemoModePage from "./pages/DemoModePage.jsx";
import WorkflowPage from "./pages/WorkflowPage.jsx";
import PipelinePage from "./pages/PipelinePage.jsx";
import MessagesPage from "./pages/MessagesPage.jsx";
import ApprovalQueuePage from "./pages/ApprovalQueuePage.jsx";
import AgentTasksPage from "./pages/AgentTasksPage.jsx";
import AgentsPage from "./pages/AgentsPage.jsx";
import ResearchToolsPage from "./pages/ResearchToolsPage.jsx";
import GptDiagnosticsPage from "./pages/GptDiagnosticsPage.jsx";
import DealsPage from "./pages/DealsPage.jsx";
import ReportsPage from "./pages/ReportsPage.jsx";
import WorkspacesPage from "./pages/WorkspacesPage.jsx";
import CreativeStudioPage from "./pages/CreativeStudioPage.jsx";
import AdminOnboardingPage from "./pages/AdminOnboardingPage.jsx";
import ClientMemoryPage from "./pages/ClientMemoryPage.jsx";
import OperationalDashboardPage from "./pages/OperationalDashboardPage.jsx";
import RecommendationsDashboardPage from "./pages/RecommendationsDashboardPage.jsx";
import AutonomyControlCenter from "./pages/AutonomyControlCenter.jsx";
import OrchestrationDashboard from "./pages/OrchestrationDashboardPage.jsx";
import ProductionTelemetryPage from "./pages/ProductionTelemetryPage.jsx";
import OperationsCommandCenter from "./pages/OperationsCommandCenter.jsx";
import LinkedInPilotPage from "./pages/LinkedInPilotPage.jsx";
import InstagramPilotPage from "./pages/InstagramPilotPage.jsx";
import OutputQualityPage from "./pages/OutputQualityPage.jsx";
import { api, setAppWorkspace } from "./api.js";
import { ROUTE_MAP } from "./navigation/routeRegistry.js";
import { NAV_GROUPS } from "./navigation/navGroups.js";
import { PROFILE_STORAGE_KEY } from "./navigation/systemProfiles.js";

const PAGE_COMPONENTS = {
  demo:             DemoModePage,
  workflow:         WorkflowPage,
  overview:         OverviewPage,
  pipeline:         PipelinePage,
  messages:         MessagesPage,
  approvals:        ApprovalQueuePage,
  "agent-tasks":    AgentTasksPage,
  agents:           AgentsPage,
  "research-tools": ResearchToolsPage,
  "gpt-diagnostics": GptDiagnosticsPage,
  deals:            DealsPage,
  "creative-studio": CreativeStudioPage,
  reports:          ReportsPage,
  workspaces:       WorkspacesPage,
  "admin-onboarding": AdminOnboardingPage,
  "client-memory":    ClientMemoryPage,
  "analytics-dashboard": OperationalDashboardPage,
    "recommendations": RecommendationsDashboardPage,
    "autonomy-control": AutonomyControlCenter,
    "orchestration-dashboard": OrchestrationDashboard,
    "production-telemetry": ProductionTelemetryPage,
    "operations-command-center": OperationsCommandCenter,
    "linkedin-pilot":             LinkedInPilotPage,
    "instagram-pilot":            InstagramPilotPage,
    "output-quality":             OutputQualityPage,
};

export default function App() {
  const initialPage = () => window.location.hash.replace("#", "").split("?")[0] || "overview";
  const [activePage, setActivePage] = useState(initialPage);
  const [health, setHealth] = useState(null);
  const [gptRuntime, setGptRuntime] = useState(null);
  const [demoMode, setDemoMode] = useState(api.demoEnabled());
  const [pendingMode, setPendingMode] = useState(null); // "demo" | "real" | null
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [workspaces, setWorkspaces] = useState([]);
  const [activeWorkspace, setActiveWorkspace] = useState("all");
  const [activeProfile, setActiveProfile] = useState(
    () => localStorage.getItem(PROFILE_STORAGE_KEY) || "custom"
  );

  function handleProfileChange(profileId) {
    localStorage.setItem(PROFILE_STORAGE_KEY, profileId);
    setActiveProfile(profileId);
  }

  async function refreshHealth() {
    const [nextHealth, nextGptRuntime] = await Promise.all([
      api.health().catch(() => null),
      api.gptRuntimeSettings().catch(() => null),
    ]);
    setHealth(nextHealth);
    setGptRuntime(nextGptRuntime);
    setLastRefresh(new Date());
    setRefreshTrigger((n) => n + 1);
  }

  async function loadWorkspaces() {
    api.workspaces().then((data) => setWorkspaces(data.items || [])).catch(() => {});
  }

  function handleWorkspaceChange(slug) {
    setActiveWorkspace(slug);
    setAppWorkspace(slug);
  }

  useEffect(() => {
    refreshHealth();
    loadWorkspaces();
    const syncHash = () => setActivePage(initialPage());
    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, []);

  useEffect(() => {
    const syncDemo = () => {
      const enabled = api.demoEnabled();
      setDemoMode(enabled);
      loadWorkspaces();
      if (enabled) {
        setActiveWorkspace("john-maxwell-demo");
        setAppWorkspace("john-maxwell-demo");
      } else {
        setActiveWorkspace("all");
        setAppWorkspace("all");
      }
    };
    window.addEventListener("signalforge-demo-change", syncDemo);
    return () => window.removeEventListener("signalforge-demo-change", syncDemo);
  }, []);

  function toggleDemoMode() {
    // Show confirmation modal before switching modes
    setPendingMode(api.demoEnabled() ? "real" : "demo");
  }

  async function confirmModeSwitch() {
    const switching = pendingMode;
    setPendingMode(null);
    if (switching === "demo") {
      await api.startDemo();
      setDemoMode(true);
      setActiveWorkspace("john-maxwell-demo");
      setAppWorkspace("john-maxwell-demo");
      window.location.hash = "demo";
    } else {
      await api.stopDemo();
      setDemoMode(false);
      setActiveWorkspace("all");
      setAppWorkspace("all");
      window.location.hash = "overview";
    }
  }

  const Page = useMemo(() => PAGE_COMPONENTS[activePage] ?? OverviewPage, [activePage]);

  const title = ROUTE_MAP[activePage]?.label ?? "Overview";

  return (
    <div className="min-h-screen bg-slate-50 text-slate-950">
      <div className="flex min-h-screen">
        <Sidebar
          navGroups={NAV_GROUPS}
          routeMap={ROUTE_MAP}
          activePage={activePage}
          onChange={(page) => {
            window.location.hash = page;
            setActivePage(page);
          }}
        />
        <main className="min-w-0 flex-1">
          <Header
            title={title}
            health={health}
            gptRuntime={gptRuntime}
            lastRefresh={lastRefresh}
            demoMode={demoMode}
            onToggleDemo={toggleDemoMode}
            workspaces={workspaces}
            activeWorkspace={activeWorkspace}
            onWorkspaceChange={handleWorkspaceChange}
            activeProfile={activeProfile}
            onProfileChange={handleProfileChange}
            action={
              <button
                type="button"
                onClick={refreshHealth}
                className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 shadow-sm transition hover:border-blue-200 hover:text-blue-700"
              >
                <RefreshCw className="h-4 w-4" />
                Refresh
              </button>
            }
          />
          <ModeBanner demoMode={demoMode} />
          <ModeConfirmModal
            targetMode={pendingMode}
            onConfirm={confirmModeSwitch}
            onCancel={() => setPendingMode(null)}
          />
          <div className="mx-auto max-w-[1500px] px-5 py-5 lg:px-8">
            <Page onWorkspacesChange={loadWorkspaces} activeWorkspace={activeWorkspace} refreshTrigger={refreshTrigger} activeProfile={activeProfile} demoMode={demoMode} />
          </div>
        </main>
      </div>
      <div className="fixed bottom-4 right-4 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500 shadow-soft">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-3.5 w-3.5 text-blue-600" />
          <span>Local-first dashboard</span>
        </div>
      </div>
    </div>
  );
}
