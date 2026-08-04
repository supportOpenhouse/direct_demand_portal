import { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";

const COLLAPSE_KEY = "dd_sidebar_collapsed";

/* A reload keeps you where you are. There used to be an effect here that read the
   Navigation Timing type and redirected to the Dashboard on F5 — deliberate, but it
   threw away the page you were on (and, on a filtered list, the reason you reloaded).
   The URL already carries the route, so the default browser behaviour is correct. */
export default function App() {
  // remembered per browser — collapsing is a workspace preference, not session state
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_KEY) === "1");
  const toggleSidebar = () => setCollapsed((v) => {
    localStorage.setItem(COLLAPSE_KEY, v ? "0" : "1");
    return !v;
  });

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
