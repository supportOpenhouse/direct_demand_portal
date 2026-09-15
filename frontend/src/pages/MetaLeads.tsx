/* Meta Leads — every lead-ads webhook delivery and the form behind it.

   Same shape as the WhatsApp page: a list on the left, the selected item's detail on
   the right, both scrolling inside their own panel rather than running to the bottom
   of the viewport. The panel height is CSS (`.ml-panels`) — it fills the view with a
   560px floor, which is the WhatsApp page's fixed height.

   Admin only. Unlike WhatsApp there is no per-lead RM view: a Meta delivery is a
   record of what arrived, not a conversation anyone owns, so there is nothing here to
   scope to a single RM. The endpoint is admin-gated too — this page just reflects it.

   The list is the delivery log, not the lead list. A `failed` row is the whole point
   of showing it: those leads exist at Meta and are NOT in the CRM, and this is the
   only place that difference is visible. */
import { useEffect, useMemo, useRef, useState } from "react";
import { useAssignees, useMetaLeads } from "../lib/queries";
import { MetaLeadEvent } from "../lib/api";
import { useAuth } from "../components/AuthContext";
import { SkeletonRows } from "../components/Skeleton";
import { FilterBar, useFilterValues } from "../components/FilterBar";
import { NO_VALUE, type FilterOption } from "../components/Filters";
import { LeadLink } from "../components/LeadModal";
import { metaQuestionLabel } from "../lib/leads";

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

/* rmOptions' rules — every known RM with their count (zero included), anyone still
   holding deliveries who left the list, Unassigned, the selection pinned — but the
   counts come from the server over every delivery, not from the loaded page. */
function ownerOptions(counts: Record<string, number>, unassigned: number,
                      assignees: string[], keep: string): FilterOption[] {
  const names = [...new Set([...assignees, ...Object.keys(counts)])].sort((a, b) => a.localeCompare(b));
  const opts: FilterOption[] = names.map((n) => ({ value: n, label: `${n} (${counts[n] ?? 0})` }));
  if (unassigned > 0 || keep === NO_VALUE) opts.push({ value: NO_VALUE, label: `Unassigned (${unassigned})` });
  if (keep && keep !== NO_VALUE && !names.includes(keep)) opts.push({ value: keep, label: `${keep} (0)` });
  return opts;
}

export default function MetaLeads() {
  const { enabled, user } = useAuth();
  const isAdmin = !enabled || user?.role === "admin";

  const [active, setActive] = useState<string | null>(null);
  // "everything" plus one entry per status that actually occurs — a filter for a
  // status with no rows is a control that can only disappoint
  const [filter, setFilter] = useState<string>("all");
  /* Attribution filters. These live on meta_lead_events (campaign/adset/ad), which
     is the only place the delivery log can be sliced by where the lead came from. */
  const { values: f, set, clear } = useFilterValues({ campaign: "", adset: "", ad: "", form: "", owner: "" });
  const assignees = useAssignees();

  /* Filtering and counting are server-side, over EVERY delivery. The list loads 100 at
     a time, so anything computed here from loaded rows would silently describe only
     what has been scrolled into view. */
  const { data, isLoading, error, fetchNextPage, hasNextPage, isFetchingNextPage } = useMetaLeads({
    status: filter === "all" ? "" : filter,
    campaign: f.campaign, adset: f.adset, ad: f.ad, form: f.form,
    // the RM who owns the lead a delivery produced; a failed delivery has no lead at
    // all, so it only matches Unassigned. NO_VALUE is a client sentinel — map it.
    owner: f.owner === NO_VALUE ? "__unassigned__" : f.owner,
  });
  const first = data?.pages[0];
  const total = first?.total ?? 0;
  const counts = first?.status_counts ?? {};

  // Offset paging: a delivery landing between two page fetches shifts every row down
  // one, so the next page can repeat the last row. Dedupe by id.
  const items = useMemo(() => {
    const seen = new Set<string>();
    const out: MetaLeadEvent[] = [];
    for (const page of data?.pages ?? [])
      for (const e of page.items)
        if (!seen.has(e.meta_lead_id)) { seen.add(e.meta_lead_id); out.push(e); }
    return out;
  }, [data]);
  const selected = items.find((e) => e.meta_lead_id === active) ?? items[0] ?? null;

  /* Infinite scroll: a sentinel after the last row, observed inside the list panel
     (which scrolls on its own, not the window). Re-armed after every fetch, so a panel
     taller than the rows loaded keeps pulling pages until it is full. */
  const listRef = useRef<HTMLDivElement>(null);
  const moreRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = moreRef.current;
    if (!el || !hasNextPage || isFetchingNextPage) return;
    const io = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) fetchNextPage(); },
      { root: listRef.current, rootMargin: "300px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, items.length]);

  // a new filter is a new list — start it from the top
  useEffect(() => { listRef.current?.scrollTo({ top: 0 }); }, [filter, f]);

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

  if (isLoading) return <div className="card"><SkeletonRows rows={7} /></div>;
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
          <b style={{ color: "var(--ink-2)" }}>{total.toLocaleString("en-IN")}</b> deliver{total === 1 ? "y" : "ies"}
          {items.length < total && (
            <span style={{ marginLeft: 6 }}>· {items.length.toLocaleString("en-IN")} loaded</span>
          )}
          {counts.failed ? (
            <span style={{ color: "var(--coral)", marginLeft: 8 }}>
              · {counts.failed} not in the CRM
            </span>
          ) : null}
        </p>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {/* selected = solid, rest = ghost. There is no `.btn.active` in the
              stylesheet, so a class name would have been silently inert. */}
          <button className={filter === "all" ? "btn primary sm" : "btn ghost sm"}
            onClick={() => setFilter("all")}>All</button>
          {Object.keys(STATUS_STYLE)
            // the selected status stays listed even at 0, or it couldn't be un-picked
            .filter((s) => counts[s] || filter === s)
            .map((s) => (
              <button key={s} className={filter === s ? "btn primary sm" : "btn ghost sm"}
                onClick={() => setFilter(s)}>
                {STATUS_STYLE[s].label} ({counts[s] ?? 0})
              </button>
            ))}
          <FilterBar
            fields={[
              { key: "campaign", label: "Campaign", options: first?.facets.campaigns ?? [] },
              { key: "adset", label: "Ad set", options: first?.facets.adsets ?? [] },
              { key: "ad", label: "Ad", options: first?.facets.ads ?? [] },
              { key: "form", label: "Form", options: first?.facets.forms ?? [] },
              { key: "owner", label: "Assigned RM",
                options: ownerOptions(first?.facets.owners ?? {}, first?.facets.unassigned ?? 0,
                                      (assignees.data?.items ?? []).map((a) => a.name), f.owner) },
            ]}
            values={f} onChange={set} onClear={clear}
          />
        </div>
      </div>

      {first?.total_all === 0 ? (
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
        <div className="ml-panels">
          {/* delivery list */}
          <div className="card ml-list" ref={listRef}>
            {items.length === 0 && <div className="ml-more">No deliveries match these filters.</div>}
            {items.map((e) => (
              <button
                key={e.meta_lead_id}
                onClick={() => setActive(e.meta_lead_id)}
                className={"ml-item"
                  + (e.meta_lead_id === selected?.meta_lead_id ? " on" : "")
                  + (e.status === "failed" ? " bad" : "")}
              >
                <div className="ml-item-top">
                  <span className="ml-item-name">{labelOf(e)}</span>
                  <StatusChip status={e.status} />
                </div>
                <div className="ml-item-sub">
                  {e.campaign_name || "no campaign"} · {when(e.received_at)}
                </div>
              </button>
            ))}
            {hasNextPage && (
              <div ref={moreRef} className="ml-more">{isFetchingNextPage ? "Loading more…" : ""}</div>
            )}
          </div>

          {/* detail */}
          <div className="card ml-detail">
            {selected && (
              <>
                <div className="ml-head">
                  <div>
                    <div className="ml-head-name">{labelOf(selected)}</div>
                    <div className="ml-head-sub">
                      Received {when(selected.received_at)} · leadgen_id {selected.meta_lead_id}
                    </div>
                  </div>
                  {selected.lead ? (
                    <LeadLink className="btn sm" id={selected.lead.id}>
                      Open lead →
                    </LeadLink>
                  ) : (
                    <StatusChip status={selected.status} />
                  )}
                </div>

                {selected.status === "failed" && (
                  <div className="ml-fail">
                    <b>Not in the CRM.</b> {selected.error_message || "No error recorded."}
                    <div style={{ marginTop: 4, opacity: 0.85 }}>
                      Attempt {selected.attempts}. The lead still exists at Meta — it can be
                      re-fetched by leadgen_id.
                    </div>
                  </div>
                )}

                <Section title="The form">
                  {selected.responses.length === 0 ? (
                    <div className="ml-hint">
                      No answers recorded — the lead was never fetched from Meta.
                    </div>
                  ) : (
                    <table className="ml-fields">
                      <tbody>
                        {selected.responses.map((r) => (
                          <tr key={r.question}>
                            <td>{metaQuestionLabel(r.question)}</td>
                            <td>{r.answer || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </Section>

                <Section title="Attribution">
                  <table className="ml-fields">
                    <tbody>
                      <Row label="Campaign" value={selected.campaign_name} id={selected.campaign_id} />
                      <Row label="Ad set" value={selected.adset_name} id={selected.adset_id} />
                      <Row label="Ad" value={selected.ad_name} id={selected.ad_id} />
                      <Row label="Form" value={null} id={selected.form_id} />
                    </tbody>
                  </table>
                  {!selected.campaign_id && (
                    <div className="ml-hint">
                      Test leads from the Lead Ads Testing Tool carry no campaign — that’s normal.
                    </div>
                  )}
                </Section>

                {selected.lead && (
                  <Section title="In the CRM">
                    <table className="ml-fields">
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
    <div className="ml-sec">
      <div className="ml-sec-h">{title}</div>
      {children}
    </div>
  );
}

/* An id with no name is still worth showing — it's what you paste into Ads Manager. */
function Row({ label, value, id }: { label: string; value?: string | null; id?: string | null }) {
  return (
    <tr>
      <td>{label}</td>
      <td>
        {value || (id ? <span className="ml-id bare">{id}</span> : "—")}
        {value && id && <span className="ml-id">{id}</span>}
      </td>
    </tr>
  );
}
