/* The Templates tab (spec §9): every `wa_templates` row, with Add / Edit. A template is
   deactivated from its Edit form (the Active box) rather than deleted — a campaign built on it
   (even an unsent draft) still has to render the text it was built with. `used` is the server's
   "ANY campaign references this template, drafts included" — NOT "has been sent"; it is what
   locks the body and Gupshup id, and what the Used chip shows. */
import { useState } from "react";
import { useWaTemplates } from "../../lib/queries";
import { WaTemplate } from "../../lib/api";
import TemplateForm from "./TemplateForm";
import { SkeletonRows } from "../../components/Skeleton";

export default function TemplatesTab() {
  const { data, isLoading, error } = useWaTemplates();
  const [editing, setEditing] = useState<WaTemplate | "new" | null>(null);
  const items = data?.items ?? [];
  return (
    <>
      <div className="wc-bar"><button className="btn primary sm" onClick={() => setEditing("new")}>+ Add template</button></div>
      {/* .table-wrap: the Name column carries a body preview (up to 420px) beside a 36-character
          Gupshup ID, so on a narrow window the table scrolls inside the card instead of spilling
          past it — the same wrapper Logs / Reports / Demand Dashboard use. */}
      <div className="card table-wrap">
        {isLoading ? <SkeletonRows rows={4} /> : error ? (
          // a failed load must not read as an empty book — "No templates yet" invites re-adding them
          <div className="empty" style={{ padding: 40 }}>Couldn't load the templates — {error.message}</div>
        ) : !items.length ? (
          <div className="empty" style={{ padding: 40 }}>No templates yet — add the approved ones from Gupshup.</div>
        ) : (
          <table><thead><tr><th>Name</th><th>Gupshup id</th><th>Variables</th><th>Buttons</th><th>Status</th><th /></tr></thead>
            <tbody>{items.map((t) => (
              <tr key={t.id}>
                <td><b>{t.name}</b><div className="wc-sub">{t.body}</div></td>
                <td className="cell-tight wc-id">{t.gupshup_template_id}</td>
                <td className="cell-tight">{t.variable_labels.join(", ") || "—"}</td>
                <td className="cell-tight">{t.buttons.join(" · ") || "—"}</td>
                <td className="cell-tight"><span className={"wc-chip " + (t.active ? "on" : "off")}>{t.active ? "Active" : "Inactive"}</span>
                  {t.used && <span className="wc-chip">Used</span>}</td>
                <td className="cell-tight"><button className="btn ghost sm" onClick={() => setEditing(t)}>Edit</button></td>
              </tr>))}</tbody></table>
        )}
      </div>
      {editing && <TemplateForm t={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
    </>
  );
}
