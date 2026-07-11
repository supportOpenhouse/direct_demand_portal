import { useEffect } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";

export default function App() {
  const navigate = useNavigate();

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
    <div className="app">
      <Sidebar />
      <main className="main">
        <Topbar />
        <div className="view">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
