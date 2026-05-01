import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  Bot,
  Building2,
  Clapperboard,
  FileText,
  Gauge,
  Mail,
  ClipboardCheck,
  ListChecks,
  RefreshCw,
  Users,
  Workflow,
} from "lucide-react";
import Sidebar from "./components/Sidebar.jsx";
import Header from "./components/Header.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";
import DemoModePage from "./pages/DemoModePage.jsx";
import WorkflowPage from "./pages/WorkflowPage.jsx";
import PipelinePage from "./pages/PipelinePage.jsx";
import MessagesPage from "./pages/MessagesPage.jsx";
import ApprovalQueuePage from "./pages/ApprovalQueuePage.jsx";
import AgentTasksPage from "./pages/AgentTasksPage.jsx";
import AgentsPage from "./pages/AgentsPage.jsx";
import GptDiagnosticsPage from "./pages/GptDiagnosticsPage.jsx";
import DealsPage from "./pages/DealsPage.jsx";
import ReportsPage from "./pages/ReportsPage.jsx";
import { api } from "./api.js";

const NAV_ITEMS = [
  { id: "demo", label: "Demo Mode", icon: Clapperboard },
  { id: "workflow", label: "Workflow", icon: Workflow },
  { id: "overview", label: "Overview", icon: Gauge },
  { id: "pipeline", label: "Pipeline", icon: Users },
  { id: "messages", label: "Messages", icon: Mail },
  { id: "approvals", label: "Approvals", icon: ClipboardCheck },
  { id: "agent-tasks", label: "Agent Tasks", icon: ListChecks },
  { id: "agents", label: "Agent Console", icon: Bot },
  { id: "gpt-diagnostics", label: "GPT Diagnostics", icon: Activity },
  { id: "deals", label: "Deals", icon: Building2 },
  { id: "reports", label: "Reports", icon: FileText },
];

export default function App() {
  const initialPage = () => window.location.hash.replace("#", "").split("?")[0] || "overview";
  const [activePage, setActivePage] = useState(initialPage);
  const [health, setHealth] = useState(null);
  const [gptRuntime, setGptRuntime] = useState(null);
  const [demoMode, setDemoMode] = useState(api.demoEnabled());
  const [lastRefresh, setLastRefresh] = useState(new Date());

  async function refreshHealth() {
    const [nextHealth, nextGptRuntime] = await Promise.all([
      api.health().catch(() => null),
      api.gptRuntimeSettings().catch(() => null),
    ]);
    setHealth(nextHealth);
    setGptRuntime(nextGptRuntime);
    setLastRefresh(new Date());
  }

  useEffect(() => {
    refreshHealth();
    const syncHash = () => setActivePage(initialPage());
    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, []);

  useEffect(() => {
    const syncDemo = () => setDemoMode(api.demoEnabled());
    window.addEventListener("signalforge-demo-change", syncDemo);
    return () => window.removeEventListener("signalforge-demo-change", syncDemo);
  }, []);

  async function toggleDemoMode() {
    if (api.demoEnabled()) {
      await api.stopDemo();
      setDemoMode(false);
      window.location.hash = "overview";
    } else {
      await api.startDemo();
      setDemoMode(true);
      window.location.hash = "demo";
    }
  }

  const Page = useMemo(() => {
    if (activePage === "demo") return DemoModePage;
    if (activePage === "workflow") return WorkflowPage;
    if (activePage === "pipeline") return PipelinePage;
    if (activePage === "messages") return MessagesPage;
    if (activePage === "approvals") return ApprovalQueuePage;
    if (activePage === "agent-tasks") return AgentTasksPage;
    if (activePage === "agents") return AgentsPage;
    if (activePage === "gpt-diagnostics") return GptDiagnosticsPage;
    if (activePage === "deals") return DealsPage;
    if (activePage === "reports") return ReportsPage;
    return OverviewPage;
  }, [activePage]);

  const title = NAV_ITEMS.find((item) => item.id === activePage)?.label || "Overview";

  return (
    <div className="min-h-screen bg-slate-50 text-slate-950">
      <div className="flex min-h-screen">
        <Sidebar
          items={NAV_ITEMS}
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
          {demoMode ? <div className="border-b border-blue-200 bg-blue-50 px-5 py-2 text-center text-sm font-semibold text-blue-900 lg:px-8">Demo Mode - No real messages will be sent</div> : null}
          <div className="mx-auto max-w-[1500px] px-5 py-5 lg:px-8">
            <Page />
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
