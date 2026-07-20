/* Booked-visit status for the Pipeline tab. A buyer usually tours several societies in
   one trip and EACH is a separate Openhouse visit with its own visit id — so the cell
   collapses to the latest and cascades open to show every visit, fetched on expand. */
import { useState } from "react";
import { useLeadCrmVisits } from "../lib/queries";

// the booked-visit state IS the lead's stage once a visit exists, so it renders as a
// stage chip in the Stage column rather than a separate one
const LABEL: Record<string, string> = {
  upcoming: "Visit Scheduled", completed: "Visit Completed", cancelled: "Visit Cancelled",
};
const STAGE_CLS: Record<string, string> = { upcoming: "visit", completed: "won", cancelled: "lost" };
const cls = (s: string | null) => `stage ${(s && STAGE_CLS[s]) || "visit"}`;

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
          <span className={cls(status)}>{LABEL[status] || status}</span>
          {date && <div className="vc-date">{date}</div>}
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
