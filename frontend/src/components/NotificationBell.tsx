/* Topbar bell. Opens to a list of CATEGORIES with counts; clicking a category
   expands a drawer of its leads. Clicking a lead opens the lead popup.

   The lead categories are built from queries the lists already run (`useLeads`), so
   they cost no extra round trip and can never disagree with the page you click
   through to -- both read the same react-query cache.

   The two WhatsApp categories DO cost a request (`useWaPending`). It is a deliberate
   four-column endpoint polled at 60s rather than a reuse of `useWaMessages`, which
   carries every message body and polls at 5s -- acceptable on the one page it mounts
   on, not in a topbar that renders everywhere.

   Ported from Direct Inventory's NotificationBell. */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLeads, useWaPending } from "../lib/queries";
import { useOpenLead } from "./LeadModal";
import { srcLabel } from "../lib/leads";
import { todayIST } from "../lib/report";
import { useWaAllowed, waWindowOpen } from "../lib/wa";
import { IconBell, IconChevronDown } from "./icons";
import type { Lead, WaPending } from "../lib/api";

/* One row, whatever produced it. The bell used to be typed to `Lead` throughout,
   which is why adding conversations needed this: a WhatsApp thread with no lead has
   no lead id to open, and its click goes to the Chat page instead. */
interface BellRow {
  id: string;
  name: string;
  meta: string;
  open: () => void;
}

const IST_OFFSET_MIN = 330;   // Asia/Kolkata, no DST

/* A callback is "today" on the IST calendar, not the browser's. An RM in another
   timezone, or one working past midnight IST, must see the same Today a manager in
   Delhi does -- a UTC boundary rolls the day at 05:30 IST, mid-shift. */
const istDayOf = (iso: string) =>
  new Date(new Date(iso).getTime() + IST_OFFSET_MIN * 60_000).toISOString().slice(0, 10);

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [openCat, setOpenCat] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const openLead = useOpenLead();

  const news = useLeads("new");
  const fups = useLeads("followup");
  const nav = useNavigate();
  /* Same gate as the sidebar's WhatsApp link — these rows carry names and phone
     numbers, so an RM who cannot open /chat must not be shown its inbox here. */
  const waAllowed = useWaAllowed();
  const waPending = useWaPending(waAllowed);

  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const newLeads = news.data?.items ?? [];
  const today = todayIST();
  /* "Reminder" is today's callbacks for now -- the reminder flow itself is a later
     change, and an empty bell section would have been worse than an honest proxy. */
  const reminders = (fups.data?.items ?? []).filter(
    (l) => l.follow_up_at && istDayOf(l.follow_up_at) <= today,
  );

  const leadRow = (l: Lead, meta: (l: Lead) => string): BellRow => ({
    id: l.id,
    name: l.name || "Unnamed",
    meta: meta(l) || l.phone || "-",
    open: () => openLead(l.id),
  });

  /* A conversation nobody has turned into a lead. Split by the 24-hour reply window
     because the two are different jobs: one still takes a normal message and has a
     deadline, the other needs an approved template. `waWindowOpen` is the thread
     view's own rule (lib/wa.ts), so the bell cannot promise a reply the composer
     then refuses. */
  const pending = waPending.data?.items ?? [];
  const split = (wantOpen: boolean) =>
    pending.filter((c) => waWindowOpen(c.last_inbound_at ? +new Date(c.last_inbound_at) : null) === wantOpen);
  const waRow = (c: WaPending): BellRow => ({
    id: c.phone,
    name: c.name || c.phone,
    meta: [c.last_inbound_at ? `last reply ${new Date(c.last_inbound_at).toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}` : null,
           c.assigned_to, c.tag].filter(Boolean).join(" - ") || c.phone,
    // no lead to open — the thread is the thing, so land on it in the Chat page
    open: () => nav(`/chat?phone=${encodeURIComponent(c.phone)}`),
  });

  const categories: { key: string; label: string; hint: string; rows: BellRow[] }[] = [
    {
      key: "new", label: "New Leads", hint: "not yet called",
      rows: newLeads.map((l) => leadRow(l, (x) => [x.city, x.society, srcLabel(x.source)].filter(Boolean).join(" - "))),
    },
    {
      key: "reminder", label: "Reminder", hint: "callbacks due today",
      rows: reminders.map((l) => leadRow(l, (x) =>
        [x.follow_up_at
          ? new Date(x.follow_up_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })
          : null, x.city, x.assigned_to].filter(Boolean).join(" - "))),
    },
    // Replyable first: it is the one with a clock on it.
    ...(waAllowed ? [
      {
        key: "wa-open", label: "WhatsApp - still replyable",
        hint: "no lead yet - 24h window open",
        rows: split(true).map(waRow),
      },
      {
        key: "wa-closed", label: "WhatsApp - template only",
        hint: "no lead yet - 24h window closed",
        rows: split(false).map(waRow),
      },
    ] : []),
  ];
  const total = categories.reduce((n, c) => n + c.rows.length, 0);

  return (
    <div className="bell-wrap" ref={ref}>
      <button type="button" className="icon-btn bell-btn"
              onClick={() => { setOpen((p) => !p); setOpenCat(null); }}
              aria-label={`Notifications: ${total}`} title="Notifications">
        <IconBell />
        {total > 0 && <span className="bell-badge">{total > 99 ? "99+" : total}</span>}
      </button>

      {open && (
        <div className="bell-dropdown">
          {categories.map((c) => (
            <div key={c.key} className="bell-cat">
              <button type="button" className="bell-cat-head" aria-expanded={openCat === c.key}
                      onClick={() => setOpenCat((p) => (p === c.key ? null : c.key))}>
                <span className="bell-cat-name">
                  {c.label}<span className="bell-hint">{c.hint}</span>
                </span>
                <span className={"bell-cat-count" + (c.rows.length ? "" : " zero")}>{c.rows.length}</span>
                <span className={"bell-cat-chev" + (openCat === c.key ? " open" : "")} aria-hidden="true">
                  <IconChevronDown />
                </span>
              </button>
              {openCat === c.key && (
                <div className="bell-drawer">
                  {c.rows.length === 0 ? (
                    <div className="bell-empty">Nothing here.</div>
                  ) : c.rows.slice(0, 50).map((r) => (
                    <button key={r.id} type="button" className="bell-row"
                            onClick={() => { setOpen(false); r.open(); }}>
                      <span className="bell-name">{r.name}</span>
                      <span className="bell-meta">{r.meta}</span>
                    </button>
                  ))}
                  {c.rows.length > 50 && (
                    <div className="bell-empty">+{c.rows.length - 50} more on the page</div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
