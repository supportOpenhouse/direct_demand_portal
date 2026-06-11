/**
 * Routes (react-router v6 createBrowserRouter):
 *   /login                       public
 *   everything else              <RequireAuth> + app shell
 *   /goldmine                    <RequireRole roles={['admin','cm']}>
 *   /settings                    <RequireRole roles={['admin']}>
 *   *                            redirect to /
 *
 * Shell convention: AppShell renders <Sidebar/> + <main class="main"><Outlet/></main>.
 * EACH PAGE renders its own <Topbar title=…/> followed by <div className="view">…</div>
 * (so pages control the title, search wiring and the Add-Lead callback).
 */
import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import GoldMine from './pages/GoldMine';
import Inventory from './pages/Inventory';
import LeadDetail from './pages/LeadDetail';
import LeadsSegment from './pages/LeadsSegment';
import Login from './pages/Login';
import NewLeads from './pages/NewLeads';
import Reminders from './pages/Reminders';
import Settings from './pages/Settings';
import SocietyInsights from './pages/SocietyInsights';
import Supply from './pages/Supply';
import { RequireAuth, RequireRole } from './store/auth';

function AppShell() {
  return (
    <RequireAuth>
      <div className="app">
        <Sidebar />
        <main className="main">
          <Outlet />
        </main>
      </div>
    </RequireAuth>
  );
}

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    element: <AppShell />,
    children: [
      { path: '/', element: <Dashboard /> },
      { path: '/leads/new', element: <NewLeads /> },
      { path: '/leads/qualified', element: <LeadsSegment segment="qualified" /> },
      { path: '/leads/pipeline', element: <LeadsSegment segment="pipeline" /> },
      { path: '/leads/converted', element: <LeadsSegment segment="converted" /> },
      { path: '/leads/:id', element: <LeadDetail /> },
      { path: '/reminders', element: <Reminders /> },
      { path: '/inventory', element: <Inventory /> },
      { path: '/supply', element: <Supply /> },
      { path: '/societies', element: <SocietyInsights /> },
      {
        path: '/goldmine',
        element: (
          <RequireRole roles={['admin', 'cm']}>
            <GoldMine />
          </RequireRole>
        ),
      },
      {
        path: '/settings',
        element: (
          <RequireRole roles={['admin']}>
            <Settings />
          </RequireRole>
        ),
      },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);
