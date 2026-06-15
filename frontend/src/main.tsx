import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import Inventory from "./pages/Inventory";
import Supply from "./pages/Supply";
import NewLeads from "./pages/NewLeads";
import LeadDetail from "./pages/LeadDetail";
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
      { path: "leads/:id", element: <LeadDetail /> },
      { path: "leads/qualified", element: <Stub title="Qualified Leads" /> },
      { path: "leads/pipeline", element: <Stub title="Pipeline Leads" /> },
      { path: "leads/converted", element: <Stub title="Converted Leads" /> },
      { path: "reminders", element: <Stub title="Reminders" /> },
      { path: "inventory", element: <Inventory /> },
      { path: "supply", element: <Supply /> },
      { path: "societies", element: <Stub title="Society Insights" /> },
      { path: "goldmine", element: <Stub title="Gold Mine" /> },
      { path: "settings", element: <Stub title="Settings & Access" /> },
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
