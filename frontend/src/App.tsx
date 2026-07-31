import { useEffect, useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";

const COLLAPSE_KEY = "dd_sidebar_collapsed";

export default function App() {
  const navigate = useNavigate();
  // remembered per browser — collapsing is a workspace preference, not session state
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_KEY) === "1");
  const toggleSidebar = () => setCollapsed((v) => {
    localStorage.setItem(COLLAPSE_KEY, v ? "0" : "1");
    return !v;
  });

  // On a browser refresh (F5 / reload), land on the Dashboard rather than staying
  // on the current tab. Uses the Navigation Timing type so normal in-app navigation
  // and direct links are unaffected — only an actual reload redirects.
  useEffect(() => {
    const entry = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
    if (entry?.type === "reload" && window.location.pathname !== "/") {
      navigate("/", { replace: true });
    }
  }, [navigate]);

  return (
    <div className={"app" + (collapsed ? " collapsed" : "")}>
      <Sidebar collapsed={collapsed} onToggle={toggleSidebar} />
      <main className="main">
        <Topbar />
        <div className="view">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
