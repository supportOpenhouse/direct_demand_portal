import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
// Live Inventory + Supply Pipeline are hidden (see the routes below). Kept commented so
// the pages drop out of the bundle too, rather than shipping unreachable code.
// import Inventory from "./pages/Inventory";
// import Supply from "./pages/Supply";
import DemandDashboard from "./pages/DemandDashboard";
import Home from "./pages/Home";
import NewLeads from "./pages/NewLeads";
import Followup from "./pages/Followup";
import LeadsSegment from "./pages/LeadsSegment";
import LeadDetail from "./pages/LeadDetail";
import Settings from "./pages/Settings";
import Logs from "./pages/Logs";
import Reports from "./pages/Reports";
import ReportDetail from "./pages/ReportDetail";
import CallLog from "./pages/CallLog";
import HuvoCalls from "./pages/HuvoCalls";
import Chat from "./pages/Chat";
import MetaLeads from "./pages/MetaLeads";
import Dialer from "./pages/Dialer";
import DialerPrevious from "./pages/DialerPrevious";
import LiveCalls from "./pages/LiveCalls";
import Stub from "./pages/Stub";
import Profile from "./pages/Profile";
import MobileApp, { MOBILE_NAV, MobileLeads } from "./MobileApp";
import { ToastProvider } from "./components/Toast";
import { SearchProvider } from "./components/SearchContext";
import { AuthProvider } from "./components/AuthContext";
import { ThemeProvider } from "./components/ThemeContext";
import "./styles/app.css";

/* Which route table to build. The two views are different component trees, not a
   restyle, so the choice is made once — and re-made by reloading when the viewport
   actually crosses the threshold (resizing the window, or flipping on the browser's
   device toolbar, which is how this gets tested). */
const mq = window.matchMedia("(max-width: 768px)");
const isMobile = mq.matches;
mq.addEventListener("change", (e) => e.matches !== isMobile && window.location.reload());

const mobileRoutes = [
  {
    path: "/",
    element: <MobileApp />,
    children: [
      { index: true, element: <Home /> },
      ...MOBILE_NAV.filter((n) => n.seg).map((n) => ({
        path: n.to.slice(1),
        element: <MobileLeads segment={n.seg!} />,
      })),
      // the real lead page — same edits, same saves, one column
      { path: "leads/:id", element: <LeadDetail mobile /> },
      // hidden 15 Sep with the Discovery nav group — uncomment to bring it back
      // { path: "inventory", element: <Inventory /> },
      { path: "profile", element: <Profile /> },
      // everything the mobile view doesn't carry lands back on Home
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
];

const desktopRoutes = [
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Home /> },
      // RM-facing half of the dialer — not under /dialer, which is admin-only
      { path: "live-calls", element: <LiveCalls /> },
      { path: "leads/new", element: <NewLeads /> },
      /* Every page that shares a component is KEYED by its page. Same component at the same
         spot, so without a key React keeps one instance across navigation — and its state
         with it: a stage box picked on Call Not Received still filtering Call Back Again to
         nothing, or Qualified's search carried into Visited. The key forces a fresh page. */
      { path: "leads/call-not-received", element: <Followup key="call_not_received" segment="call_not_received" /> },
      { path: "leads/followup", element: <Followup key="followup" /> },
      { path: "leads/qualified", element: <LeadsSegment key="qualified" segment="qualified" /> },
      { path: "leads/future-prospect", element: <LeadsSegment key="future_prospect" segment="future_prospect" /> },
      // one page for visit_scheduled + revisit_scheduled
      { path: "leads/visited", element: <LeadsSegment key="visited" segment="visited" /> },
      { path: "leads/converted", element: <LeadsSegment key="converted" segment="converted" /> },
      { path: "leads/rejected", element: <LeadsSegment key="rejected" segment="rejected" /> },
      /* Old page URLs. These are in people's bookmarks and in links already sent, and a
         dead /leads/pipeline would land on the catch-all rather than the leads it used
         to show. rnr moved from Rejected to Call Not Received with the 16 Sep pages. */
      { path: "leads/pipeline", element: <Navigate to="/leads/visited" replace /> },
      { path: "leads/revisit", element: <Navigate to="/leads/visited" replace /> },
      { path: "leads/rnr", element: <Navigate to="/leads/call-not-received" replace /> },
      { path: "leads/:id", element: <LeadDetail /> },
      // Auto Dialer is two pages now; the bare path opens the scheduler
      { path: "dialer", element: <Navigate to="/dialer/schedule" replace /> },
      { path: "dialer/schedule", element: <Dialer /> },
      { path: "dialer/previous", element: <DialerPrevious /> },
      { path: "reminders", element: <Stub title="Reminders" /> },
      // hidden 15 Sep with the Discovery nav group — uncomment (with the imports at the
      // top) to bring both back; the pages themselves were not touched
      // { path: "inventory", element: <Inventory /> },
      // { path: "supply", element: <Supply /> },
      { path: "demand-dashboard", element: <DemandDashboard /> },
      { path: "profile", element: <Profile /> },
      { path: "settings", element: <Settings /> },
      { path: "logs", element: <Logs /> },
      { path: "reports", element: <Reports /> },
      // opened in a new tab from a row on /reports; range travels in the querystring
      { path: "reports/detail", element: <ReportDetail /> },
      { path: "call-log", element: <CallLog /> },
      { path: "huvo-calls", element: <HuvoCalls /> },
      { path: "chat", element: <Chat /> },
      // admin-only: the page itself refuses a non-admin, and so does the endpoint
      { path: "meta-leads", element: <MetaLeads /> },
      // Anything unmatched lands on Home, as the mobile routes already did. Added when
      // /inventory and /supply were hidden: without it an old bookmark to either one
      // renders React Router's error screen instead of the app.
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
];

const router = createBrowserRouter(isMobile ? mobileRoutes : desktopRoutes);

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <SearchProvider>
            <ToastProvider>
              <RouterProvider router={router} />
            </ToastProvider>
          </SearchProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
