import { useLocation, useNavigate } from 'react-router-dom';
import { useReminders } from '../lib/queries';
import { useAuth } from '../store/auth';
import { IconBell, IconPlus, IconSearch } from './icons';
import { useToast } from './Toast';

export interface TopbarProps {
  /** Page title — derived from the route (Dashboard -> "Hello, {first name}") when omitted. */
  title?: string;
  /** Wire the Add-New-Lead modal here. Without it the button shows a stub toast. */
  onAddLead?: () => void;
  /** Controlled search (uncontrolled local input when omitted). */
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  searchPlaceholder?: string;
}

const ROUTE_TITLES: [RegExp, string][] = [
  [/^\/leads\/new$/, 'New Leads'],
  [/^\/leads\/qualified$/, 'Qualified Leads'],
  [/^\/leads\/pipeline$/, 'Pipeline Leads'],
  [/^\/leads\/converted$/, 'Converted Leads'],
  [/^\/leads\/.+$/, 'Lead Details'],
  [/^\/reminders$/, 'Reminders'],
  [/^\/inventory$/, 'Live Inventory'],
  [/^\/supply$/, 'Supply Pipeline'],
  [/^\/societies$/, 'Society Insights'],
  [/^\/goldmine$/, 'Gold Mine'],
  [/^\/settings$/, 'Settings & Access'],
];

/**
 * 60px sticky blurred topbar: page title, search pill, orange Reminders
 * button (live undone count -> /reminders), accent "+ Add New Lead" button.
 */
export function Topbar({
  title,
  onAddLead,
  searchValue,
  onSearchChange,
  searchPlaceholder,
}: TopbarProps) {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { push } = useToast();
  const { data: reminders } = useReminders();

  const derivedTitle =
    title ??
    (pathname === '/'
      ? `Hello, ${user?.name.split(' ')[0] ?? 'there'}`
      : (ROUTE_TITLES.find(([re]) => re.test(pathname))?.[1] ?? 'Openhouse Direct Demand'));

  const dueCount = reminders?.filter((r) => !r.done).length ?? 0;

  const handleAddLead = () => {
    if (onAddLead) onAddLead();
    else push({ kind: 'blue', title: 'Add New Lead', sub: 'Coming soon on this page' });
  };

  return (
    <header className="topbar">
      <h1>{derivedTitle}</h1>
      <div className="tb-right">
        <div className="search">
          <IconSearch size={15} />
          <input
            type="text"
            placeholder={searchPlaceholder ?? 'Search leads, societies…'}
            value={searchValue}
            onChange={onSearchChange ? (e) => onSearchChange(e.target.value) : undefined}
            readOnly={!onSearchChange && searchValue !== undefined}
          />
        </div>
        <button type="button" className="btn orange" onClick={() => navigate('/reminders')}>
          <IconBell size={15} />
          Reminders
          {dueCount > 0 && <span className="btn-badge">{dueCount}</span>}
        </button>
        <button type="button" className="btn green" onClick={handleAddLead}>
          <IconPlus size={15} />
          Add New Lead
        </button>
      </div>
    </header>
  );
}
