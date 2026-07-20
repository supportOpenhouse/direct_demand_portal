/* Booked-visit status for the Pipeline tab. A buyer usually tours several societies in
   one trip and EACH is a separate Openhouse visit with its own visit id — so the cell
   collapses to the latest and cascades open to show every visit, fetched on expand. */
import { useState } from "react";
import { useLeadCrmVisits } from "../lib/queries";

const LABEL: Record<string, string> = { upcoming: "Upcoming", completed: "Completed", cancelled: "Cancelled" };
const cls = (s: string | null) => `visit-chip ${s && LABEL[s] ? s : "upcoming"}`;

export function VisitsCell({
  leadId, status, date, count,
}: { leadId: string; status: string | null; date: string | null; count: number }) {
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useLeadCrmVisits(leadId, open);
  const visits = data?.items ?? [];

  if (!status) return <span style={{ color: "var(--muted)", fontSize: 12 }}>—</span>;

  return (
    <div className="visits-cell" onClick={(e) => e.stopPropagation()}>
      {!open ? (
        <>
          <span className={cls(status)}>{LABEL[status] || status}{date ? ` · ${date}` : ""}</span>
          {count > 1 && (
            <button className="note-toggle" onClick={() => setOpen(true)}>▾ all {count} visits</button>
          )}
        </>
      ) : (
        <div className="visit-list">
          {isLoading ? (
            <div style={{ fontSize: 11, color: "var(--muted)" }}>Loading…</div>
          ) : (
            visits.map((v) => (
              <div key={v.visit_id} className="visit-line">
                <span className={cls(v.status)}>{LABEL[v.status] || v.status}</span>
                <div className="vl-meta">
                  <span className="vl-society">{v.society || "—"}</span>
                  <span className="vl-sub">
                    {v.selected_date || "—"}{v.selected_time ? ` · ${v.selected_time}` : ""} · #{v.visit_id}
                    {v.booked_by ? ` · ${v.booked_by}` : ""}
                  </span>
                </div>
              </div>
            ))
          )}
          <button className="note-toggle" onClick={() => setOpen(false)}>▴ hide</button>
        </div>
      )}
    </div>
  );
}
