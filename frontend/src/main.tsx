import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import Inventory from "./pages/Inventory";
import Supply from "./pages/Supply";
import Dashboard from "./pages/Dashboard";
import NewLeads from "./pages/NewLeads";
import Followup from "./pages/Followup";
import LeadsSegment from "./pages/LeadsSegment";
import LeadDetail from "./pages/LeadDetail";
import Settings from "./pages/Settings";
import Logs from "./pages/Logs";
import CallLog from "./pages/CallLog";
import Chat from "./pages/Chat";
import Dialer from "./pages/Dialer";
import DialerPrevious from "./pages/DialerPrevious";
import Stub from "./pages/Stub";
import { ToastProvider } from "./components/Toast";
import { SearchProvider } from "./components/SearchContext";
import { AuthProvider } from "./components/AuthContext";
import "./styles/app.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: "leads/new", element: <NewLeads /> },
      { path: "leads/call-not-received", element: <Followup segment="call_not_received" /> },
      { path: "leads/followup", element: <Followup /> },
      { path: "leads/qualified", element: <LeadsSegment segment="qualified" /> },
      { path: "leads/pipeline", element: <LeadsSegment segment="pipeline" /> },
      { path: "leads/converted", element: <LeadsSegment segment="converted" /> },
      // RNR leads live on the Rejected page now — keep old links working
      { path: "leads/rnr", element: <Navigate to="/leads/rejected" replace /> },
      { path: "leads/rejected", element: <LeadsSegment segment="rejected" /> },
      { path: "leads/:id", element: <LeadDetail /> },
      // Auto Dialer is two pages now; the bare path opens the scheduler
      { path: "dialer", element: <Navigate to="/dialer/schedule" replace /> },
      { path: "dialer/schedule", element: <Dialer /> },
      { path: "dialer/previous", element: <DialerPrevious /> },
      { path: "reminders", element: <Stub title="Reminders" /> },
      { path: "inventory", element: <Inventory /> },
      { path: "supply", element: <Supply /> },
      { path: "societies", element: <Stub title="Society Insights" /> },
      { path: "goldmine", element: <Stub title="Gold Mine" /> },
      { path: "settings", element: <Settings /> },
      { path: "logs", element: <Logs /> },
      { path: "call-log", element: <CallLog /> },
      { path: "chat", element: <Chat /> },
    ],
  },
]);

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <SearchProvider>
          <ToastProvider>
            <RouterProvider router={router} />
          </ToastProvider>
        </SearchProvider>
      </AuthProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
