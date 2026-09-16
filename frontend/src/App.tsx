import { useEffect, useRef, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import { LeadModalProvider } from "./components/LeadModal";

const COLLAPSE_KEY = "dd_sidebar_collapsed";

/* A reload keeps you where you are. There used to be an effect here that read the
   Navigation Timing type and redirected to Home on F5 — deliberate, but it
   threw away the page you were on (and, on a filtered list, the reason you reloaded).
   The URL already carries the route, so the default browser behaviour is correct. */
export default function App() {
  // remembered per browser — collapsing is a workspace preference, not session state
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_KEY) === "1");
  const toggleSidebar = () => setCollapsed((v) => {
    localStorage.setItem(COLLAPSE_KEY, v ? "0" : "1");
    return !v;
  });

  /* Direction from path depth: deeper enters from the right, shallower from the
     left, same depth just fades. Keyed on pathname so the animation actually
     re-runs — React reuses the node otherwise and nothing plays. */
  const { pathname } = useLocation();

  /* Supply-side pages carry the orange accent. It goes on <html> rather than on a
     page wrapper because the SIDEBAR has to change with it — the accent says which
     side of the business you are on, and the nav is where that reads first.
     Cleaned up on unmount so a route outside this shell can't inherit it. */
  // dormant while those two routes are commented out (main.tsx): nothing matches, so no
  // page takes the orange accent. Left in place so uncommenting the routes restores it.
  const supplySide = pathname.startsWith("/inventory") || pathname.startsWith("/supply");
  useEffect(() => {
    const root = document.documentElement;
    if (supplySide) root.setAttribute("data-accent", "orange");
    else root.removeAttribute("data-accent");
    return () => root.removeAttribute("data-accent");
  }, [supplySide]);

  const prev = useRef(pathname);
  const depth = (s: string) => s.split("/").filter(Boolean).length;
  // NB: these must NOT be bare `fwd`/`back` — `.back` is also the "← Back" link
  // utility (display:inline-flex), and it would collapse the whole page wrapper to
  // content width on any shallower navigation. Scope them to the animation.
  const dir = depth(pathname) > depth(prev.current) ? " anim-fwd"
            : depth(pathname) < depth(prev.current) ? " anim-back" : "";
  prev.current = pathname;

  return (
    <LeadModalProvider>
      <div className={"app" + (collapsed ? " collapsed" : "")}>
        <Sidebar collapsed={collapsed} onToggle={toggleSidebar} />
        <main className="main">
          <Topbar />
          <div className="view">
            <div className={"page-anim" + dir} key={pathname}>
              <Outlet />
            </div>
          </div>
        </main>
      </div>
    </LeadModalProvider>
  );
}
