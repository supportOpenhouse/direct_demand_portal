/* Inline notes thread for the lead list tables — shows the latest note, expands to
   the full thread (newest first), fetched lazily only when opened. */
import { useState } from "react";
import { useLeadNotes, formatDateTime } from "../lib/queries";

export function NotesCell({ leadId, latest, count }: { leadId: string; latest: string | null; count: number }) {
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useLeadNotes(leadId, open);
  const items = data?.items ?? [];
  const stop = (e: React.MouseEvent) => e.stopPropagation();

  if (!latest) {
    return <span style={{ color: "var(--muted)", fontSize: 12 }}>No notes yet</span>;
  }
  return (
    <div style={{ minWidth: 200, maxWidth: 300 }} onClick={stop}>
      {!open ? (
        <>
          <div className="note-latest" title={latest}>{latest}</div>
          {count > 1 && (
            <button className="note-toggle" onClick={() => setOpen(true)}>▾ {count} notes</button>
          )}
        </>
      ) : (
        <div className="note-thread">
          {isLoading ? (
            <div style={{ fontSize: 11, color: "var(--muted)" }}>Loading…</div>
          ) : (
            [...items].reverse().map((n, i) => (
              <div key={n.id ?? `${i}`} className={"note-line" + (i === 0 ? " first" : "")}>
                <div className="nl-body">{n.body}</div>
                <div className="nl-meta">
                  {n.author || (n.source === "remarks" ? "source" : "—")}
                  {n.created_at ? ` · ${formatDateTime(n.created_at)}` : ""}
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
