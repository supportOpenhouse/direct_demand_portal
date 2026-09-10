/* Meta Leads — every lead-ads webhook delivery and the form behind it.

   Same shape as the WhatsApp page: a list on the left, the selected item's detail on
   the right, both scrolling inside a fixed panel rather than running to the bottom of
   the viewport.

   Admin only. Unlike WhatsApp there is no per-lead RM view: a Meta delivery is a
   record of what arrived, not a conversation anyone owns, so there is nothing here to
   scope to a single RM. The endpoint is admin-gated too — this page just reflects it.

   The list is the delivery log, not the lead list. A `failed` row is the whole point
   of showing it: those leads exist at Meta and are NOT in the CRM, and this is the
   only place that difference is visible. */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMetaLeads } from "../lib/queries";
import { MetaLeadEvent } from "../lib/api";
import { useAuth } from "../components/AuthContext";

// fixed panel height — matches the WhatsApp page so the two read as siblings
const PANEL_H = 560;

const STATUS_STYLE: Record<string, { bg: string; fg: string; label: string }> = {
  success:   { bg: "var(--emerald-soft)", fg: "var(--emerald)", label: "in CRM" },
  failed:    { bg: "var(--coral-soft)",   fg: "var(--coral)",   label: "failed" },
  duplicate: { bg: "var(--blue-soft)",    fg: "var(--blue)",    label: "duplicate" },
  pending:   { bg: "var(--amber-soft)",   fg: "var(--amber)",   label: "pending" },
};

function StatusChip({ status }: { status: string }) {
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.pending;
  return (
    <span className="bucket-tag" style={{ background: s.bg, color: s.fg }}>{s.label}</span>
  );
}

/* Meta's field keys are machine names ("your_budget_range", "where_do_you_currently
   live"). The form asked them in words, so show words. */
function prettyQuestion(name: string): string {
  const s = name.replace(/_/g, " ").replace(/\s+/g, " ").trim();
  return s ? s[0].toUpperCase() + s.slice(1) : name;
}

function when(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-IN", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: true,
  });
}

/* The buyer's name, from the lead if the ingest produced one and from the form itself
   if it didn't — a failed delivery still has to be identifiable in the list. */
function labelOf(e: MetaLeadEvent): string {
  if (e.lead?.name) return e.lead.name;
  const fromForm = e.responses.find((r) => r.question === "full_name")?.answer;
  return fromForm || e.lead?.phone || e.meta_lead_id;
}

export default function MetaLeads() {
  const { enabled, user } = useAuth();
  const isAdmin = !enabled || user?.role === "admin";

  const { data, isLoading, error } = useMetaLeads();
  const [active, setActive] = useState<string | null>(null);
  // "everything" plus one entry per status that actually occurs — a filter for a
  // status with no rows is a control that can only disappoint
  const [filter, setFilter] = useState<string>("all");

  const items = data?.items ?? [];
  const counts = useMemo(() => {
    const by: Record<string, number> = {};
    for (const e of items) by[e.status] = (by[e.status] ?? 0) + 1;
    return by;
  }, [items]);

  const shown = useMemo(
    () => (filter === "all" ? items : items.filter((e) => e.status === filter)),
    [items, filter],
  );
  const selected = shown.find((e) => e.meta_lead_id === active) ?? shown[0] ?? null;

  if (!isAdmin) {
    return (
      <div className="card">
        <div className="empty" style={{ padding: 48, textAlign: "center" }}>
          <div style={{ fontWeight: 600, color: "var(--ink-2)" }}>Admins only</div>
          <div style={{ fontSize: 12.5, marginTop: 6 }}>
            Meta lead deliveries are an account-wide record, not a per-RM worklist.
          </div>
        </div>
      </div>
    );
  }

  if (isLoading) return <div className="card"><div className="empty" style={{ padding: 48 }}>Loading…</div></div>;
  if (error) {
    return (
      <div className="card">
        <div className="empty" style={{ padding: 48 }}>
          <div style={{ fontWeight: 600, color: "var(--coral)" }}>Couldn’t load Meta leads</div>
          <div style={{ fontSize: 12.5, marginTop: 4 }}>{(error as Error).message}</div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="section-head" style={{ marginBottom: 10 }}>
        <p className="sec-sub" style={{ margin: 0 }}>
          <b style={{ color: "var(--ink-2)" }}>{items.length}</b> deliver{items.length === 1 ? "y" : "ies"}
          {counts.failed ? (
            <span style={{ color: "var(--coral)", marginLeft: 8 }}>
              · {counts.failed} not in the CRM
            </span>
          ) : null}
        </p>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {/* selected = solid, rest = ghost. There is no `.btn.active` in the
              stylesheet, so a class name would have been silently inert. */}
          <button className={filter === "all" ? "btn sm" : "btn ghost sm"}
            onClick={() => setFilter("all")}>All</button>
          {Object.keys(STATUS_STYLE)
            .filter((s) => counts[s])
            .map((s) => (
              <button key={s} className={filter === s ? "btn sm" : "btn ghost sm"}
                onClick={() => setFilter(s)}>
                {STATUS_STYLE[s].label} ({counts[s]})
              </button>
            ))}
        </div>
      </div>

      {items.length === 0 ? (
        <div className="card">
          <div className="empty" style={{ padding: 48, textAlign: "center" }}>
            <div style={{ fontWeight: 600, color: "var(--ink-2)" }}>No deliveries yet</div>
            <div style={{ fontSize: 12.5, marginTop: 6, lineHeight: 1.6 }}>
              Nothing has arrived on the leadgen webhook. If a form has been submitted since
              it went live, check that the Page is subscribed and that “Verify and Save”
              went green in the app dashboard — a subscribed but unverified callback is
              accepted and then delivers nothing.
            </div>
          </div>
        </div>
      ) : (
        <div style={{
          display: "grid", gridTemplateColumns: "minmax(220px, 320px) 1fr", gap: 12,
          height: PANEL_H,
        }}>
          {/* delivery list */}
          <div className="card" style={{ padding: 0, overflowY: "auto" }}>
            {shown.map((e, i) => {
              const isSel = e.meta_lead_id === selected?.meta_lead_id;
              return (
                <button
                  key={e.meta_lead_id}
                  onClick={() => setActive(e.meta_lead_id)}
                  style={{
                    display: "block", width: "100%", textAlign: "left", padding: "11px 13px",
                    border: 0, font: "inherit", cursor: "pointer",
                    borderTop: i ? "1px solid var(--line)" : undefined,
                    // failed rows carry their own background: they are the rows that
                    // need acting on, and they must read as different from a glance
                    background: isSel ? "var(--panel-2)"
                      : e.status === "failed" ? "var(--coral-soft)" : "transparent",
                    borderLeft: e.lead ? "3px solid var(--amber)" : "3px solid transparent",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <span style={{ fontWeight: 600, color: "var(--ink-2)", overflow: "hidden",
                                   textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {labelOf(e)}
                    </span>
                    <StatusChip status={e.status} />
                  </div>
                  <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 3,
                                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {e.campaign_name || "no campaign"} · {when(e.received_at)}
                  </div>
                </button>
              );
            })}
          </div>

          {/* detail */}
          <div className="card" style={{ overflowY: "auto" }}>
            {selected && (
              <>
                <div style={{ display: "flex", justifyContent: "space-between",
                              alignItems: "flex-start", gap: 12, marginBottom: 14 }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 16, color: "var(--ink-2)" }}>
                      {labelOf(selected)}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 3 }}>
                      Received {when(selected.received_at)} · leadgen_id {selected.meta_lead_id}
                    </div>
                  </div>
                  {selected.lead ? (
                    <Link className="btn sm" to={`/leads/${selected.lead.id}`}>
                      Open lead →
                    </Link>
                  ) : (
                    <StatusChip status={selected.status} />
                  )}
                </div>

                {selected.status === "failed" && (
                  <div style={{
                    background: "var(--coral-soft)", color: "var(--coral)", padding: "10px 12px",
                    borderRadius: 8, fontSize: 12.5, marginBottom: 14, lineHeight: 1.55,
                  }}>
                    <b>Not in the CRM.</b> {selected.error_message || "No error recorded."}
                    <div style={{ marginTop: 4, opacity: 0.85 }}>
                      Attempt {selected.attempts}. The lead still exists at Meta — it can be
                      re-fetched by leadgen_id.
                    </div>
                  </div>
                )}

                <Section title="The form">
                  {selected.responses.length === 0 ? (
                    <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
                      No answers recorded — the lead was never fetched from Meta.
                    </div>
                  ) : (
                    <table className="table" style={{ width: "100%" }}>
                      <tbody>
                        {selected.responses.map((r) => (
                          <tr key={r.question}>
                            <td style={{ width: "45%", color: "var(--muted)", fontSize: 12.5 }}>
                              {prettyQuestion(r.question)}
                            </td>
                            <td style={{ fontWeight: 500 }}>{r.answer || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </Section>

                <Section title="Attribution">
                  <table className="table" style={{ width: "100%" }}>
                    <tbody>
                      <Row label="Campaign" value={selected.campaign_name} id={selected.campaign_id} />
                      <Row label="Ad set" value={selected.adset_name} id={selected.adset_id} />
                      <Row label="Ad" value={selected.ad_name} id={selected.ad_id} />
                      <Row label="Form" value={null} id={selected.form_id} />
                    </tbody>
                  </table>
                  {!selected.campaign_id && (
                    <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 6 }}>
                      Test leads from the Lead Ads Testing Tool carry no campaign — that’s normal.
                    </div>
                  )}
                </Section>

                {selected.lead && (
                  <Section title="In the CRM">
                    <table className="table" style={{ width: "100%" }}>
                      <tbody>
                        <Row label="Phone" value={selected.lead.phone} />
                        <Row label="City" value={selected.lead.city} />
                        <Row label="Stage" value={selected.lead.stage} />
                        <Row label="Assigned to" value={selected.lead.assigned_to} />
                      </tbody>
                    </table>
                  </Section>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.6, textTransform: "uppercase",
                    color: "var(--muted)", marginBottom: 6 }}>
        {title}
      </div>
      {children}
    </div>
  );
}

/* An id with no name is still worth showing — it's what you paste into Ads Manager. */
function Row({ label, value, id }: { label: string; value?: string | null; id?: string | null }) {
  return (
    <tr>
      <td style={{ width: "45%", color: "var(--muted)", fontSize: 12.5 }}>{label}</td>
      <td style={{ fontWeight: 500 }}>
        {value || (id ? <span style={{ color: "var(--muted)" }}>{id}</span> : "—")}
        {value && id && (
          <span style={{ color: "var(--muted)", fontSize: 11, marginLeft: 6 }}>{id}</span>
        )}
      </td>
    </tr>
  );
}
