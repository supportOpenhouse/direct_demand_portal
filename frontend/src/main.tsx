import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import Inventory from "./pages/Inventory";
import Supply from "./pages/Supply";
import NewLeads from "./pages/NewLeads";
import LeadsSegment from "./pages/LeadsSegment";
import LeadDetail from "./pages/LeadDetail";
import Settings from "./pages/Settings";
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
      { index: true, element: <Stub title="Dashboard" /> },
      { path: "leads/new", element: <NewLeads /> },
      { path: "leads/qualified", element: <LeadsSegment segment="qualified" /> },
      { path: "leads/pipeline", element: <LeadsSegment segment="pipeline" /> },
      { path: "leads/converted", element: <LeadsSegment segment="converted" /> },
      { path: "leads/:id", element: <LeadDetail /> },
      { path: "reminders", element: <Stub title="Reminders" /> },
      { path: "inventory", element: <Inventory /> },
      { path: "supply", element: <Supply /> },
      { path: "societies", element: <Stub title="Society Insights" /> },
      { path: "goldmine", element: <Stub title="Gold Mine" /> },
      { path: "settings", element: <Settings /> },
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
