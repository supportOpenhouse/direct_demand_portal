/* 99acres listings on the Demand Dashboard — admin only.
   Spec: docs/superpowers/specs/2026-11-05-99acres-listing-design.md.

   Kept out of pages/DemandDashboard.tsx on purpose: tests/test_demand_dashboard.py scans
   that page for every `p.<field>` it reads and fails on anything the API doesn't send. */
import { Fragment, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type AcresCheck, type AcresPostResult, type AcresStatus, type DemandProperty } from "../../lib/api";
import { useAcresListings, useAcresMark, useAcresPost } from "../../lib/queries";
import { useModalExit } from "../../lib/useModalExit";
import { useToast } from "../../components/Toast";
import { IconX } from "../../components/icons";

/* Same ids as OWNTYPE_IDS in backend/app/services/acres_payload.py
   (tests/test_acres_router.py::test_the_modal_offers_exactly_the_99acres_ids). */
export const OWNTYPE_OPTIONS = [
  { value: "1", label: "Freehold" },
  { value: "2", label: "Leasehold" },
  { value: "3", label: "Co-operative society" },
  { value: "4", label: "Power of attorney" },
];
/* Display only — the age is worked out from master_societies.possession_year server-side. */
export const AGE_LABEL: Record<string, string> = { "6": "0–1 yrs", "1": "1–5 yrs", "2": "5–10 yrs", "3": "10+ yrs" };

const CHIP: Record<AcresStatus, { cls: string; label: string }> = {
  live: { cls: "won", label: "Live" },
  unknown: { cls: "visit", label: "Unknown — check" },
  failed: { cls: "lost", label: "Failed" },
  duplicate: { cls: "nego", label: "Duplicate" },
  removed: { cls: "planned", label: "Removed" },
};

const istDay = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric" }) : "—";

export function AcresStatusChip({ status, propId, availability, error }:
  { status: AcresStatus | null | undefined; propId?: string | null; availability?: string; error?: string | null }) {
  if (!status) return <>—</>;
  // The API can't delete a listing, so a sold home stays live until someone takes it down by hand.
  if (status === "live" && availability && availability !== "Available") {
    return <span className="stage lost" title={`${propId ?? ""} is still live on 99acres — delete it in the 99acres dashboard, then mark it removed`}>Live — take down</span>;
  }
  return (
    <span className={`stage ${CHIP[status].cls}`} title={error ?? undefined}>
      {CHIP[status].label}{status === "live" && propId ? ` · ${propId}` : ""}
    </span>
  );
}

/* The table cell. Every row reads the same cached map, so this is one request for the page. */
export function AcresChip({ uid, availability }: { uid: string; availability: string }) {
  const row = useAcresListings(true).data?.get(uid);
  return <AcresStatusChip status={row?.status} propId={row?.prop_id} availability={availability} error={row?.error} />;
}

/* The popup's "99acres" section: where it stands, and the hand transitions — the API can't
   list or delete listings, so these are how the record stays true. */
export function AcresSection({ p }: { p: DemandProperty }) {
  const [listing, setListing] = useState(false);
  const row = useAcresListings(true).data?.get(p.uid);
  const mark = useAcresMark();
  const toast = useToast();
  const status = row?.status ?? null;
  const act = (to: "live" | "failed" | "removed", propId?: string) =>
    mark.mutate({ uid: p.uid, status: to, prop_id: propId }, {
      onSuccess: () => toast("99acres record updated", "green"),
      onError: (e) => toast(e instanceof Error ? e.message : "Couldn't update the 99acres record", "gold"),
    });
  const recordLive = () => {
    const id = window.prompt("Its 99acres listing id (e.g. E95607134):");
    if (id && id.trim()) act("live", id.trim());
  };
  const remove = () => {
    if (window.confirm("Only do this once it's deleted in the 99acres dashboard.")) act("removed");
  };
  return (
    <div className="dd-section">
      <div className="dd-section-t">99acres</div>
      <div className="dd-fields">
        <div className="field-row"><span className="field-lbl">Status</span>
          <span className="field-val"><AcresStatusChip status={status} propId={row?.prop_id} availability={p.availability_status} /></span></div>
        <div className="field-row"><span className="field-lbl">Listing id</span><span className="field-val">{row?.prop_id ?? "—"}</span></div>
        <div className="field-row"><span className="field-lbl">Posted</span><span className="field-val">{istDay(row?.posted_at ?? null)}</span></div>
        {row?.error && <div className="field-row dd-wide"><span className="field-lbl">Last error</span><span className="field-val">{row.error}</span></div>}
      </div>
      <div className="acres-actions">
        {(status === null || status === "failed" || status === "removed") && (
          <button className="btn sm" onClick={() => setListing(true)}>List on 99acres</button>)}
        {(status === null || status === "failed" || status === "duplicate" || status === "unknown") && (
          <button className="btn ghost sm" onClick={recordLive} disabled={mark.isPending}>Already on 99acres</button>)}
        {status === "unknown" && <button className="btn ghost sm" onClick={() => act("failed")} disabled={mark.isPending}>Not on 99acres</button>}
        {status === "duplicate" && <button className="btn ghost sm" onClick={() => act("failed")} disabled={mark.isPending}>Try again</button>}
        {status === "live" && <button className="btn ghost sm" onClick={remove} disabled={mark.isPending}>Mark removed</button>}
      </div>
      {listing && <ListOnAcresModal properties={[p]} onClose={() => setListing(false)} />}
    </div>
  );
}

const CHECK_MAX = 300;   // /v1/acres/check's cap
const NOT_ATTEMPTED = "Not attempted — the run stopped";   // = acres_listings.NOT_ATTEMPTED
// User, 13 Nov: no "How many to post this run?" prompt — every Post sends exactly one property
// (the first ticked, ready row), so the next listing is always a deliberate click.
const PER_RUN = 1;

/* List one or many properties on 99acres. The server decides everything (what would be sent,
   what blocks it); this window collects ownership and shows the answer. Each Post sends ONE
   property — a listing's cost in pack credits is still unknown (STATUS.md, "295 Credits"). */
export function ListOnAcresModal({ properties, onClose: rawClose }: { properties: DemandProperty[]; onClose: () => void }) {
  const { onClose, overlayClass } = useModalExit(rawClose);
  const stored = useAcresListings(true).data;
  const post = useAcresPost();
  const toast = useToast();
  const [allOwn, setAllOwn] = useState("");
  const [own, setOwn] = useState<Record<string, string>>({});
  const [photos, setPhotos] = useState(true);
  const [checks, setChecks] = useState<Map<string, AcresCheck> | null>(null);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const everOk = useRef(new Set<string>());
  const [results, setResults] = useState<Record<string, AcresPostResult>>({});
  const [running, setRunning] = useState(false);
  const [round, setRound] = useState(0);   // bumped after a run to re-check

  const inRun = new Set(properties.map((p) => p.uid));
  const ownOf = (uid: string) => own[uid] ?? (allOwn || stored?.get(uid)?.owntype || "");
  const items = properties.map((p) => ({ uid: p.uid, owntype: ownOf(p.uid) || null }));
  const key = JSON.stringify([items, photos, round]);

  useEffect(() => {
    let live = true;
    const t = setTimeout(async () => {
      const chunks: (typeof items)[] = [];
      for (let i = 0; i < items.length; i += CHECK_MAX) chunks.push(items.slice(i, i + CHECK_MAX));
      try {
        const answers = await Promise.all(chunks.map((c) => api.acresCheck(c, photos)));
        if (!live) return;
        const m = new Map(answers.flatMap((a) => a.items).map((r) => [r.uid, r]));
        // A row is ticked the first time it becomes postable; an admin's untick sticks.
        // Worked out OUTSIDE the updater: React may run an updater twice, and one that
        // touches a ref drops the rows on its second run.
        const fresh = [...m.values()].filter((r) => r.ok && !everOk.current.has(r.uid)).map((r) => r.uid);
        fresh.forEach((u) => everOk.current.add(u));
        setTicked((prev) => new Set([...[...prev].filter((u) => m.get(u)?.ok), ...fresh]));
        setChecks(m); setCheckError(null);
      } catch (e) {
        if (live) setCheckError(e instanceof Error ? e.message : "Couldn't check these properties");
      }
    }, 400);
    return () => { live = false; clearTimeout(t); };
  }, [key]);   // eslint-disable-line react-hooks/exhaustive-deps

  const ready = properties.map((p) => p.uid).filter((u) => checks?.get(u)?.ok && !results[u]);
  const tickedReady = ready.filter((u) => ticked.has(u));
  const run = async () => {
    const chunk = tickedReady.slice(0, PER_RUN).map((uid) => ({ uid, owntype: ownOf(uid) || null }));
    setRunning(true);
    try {
      const r = await post.mutateAsync({ items: chunk, photos });
      // A row the server never reached stays Ready for the next click — it isn't a result.
      const reached = r.items.filter((x) => x.error !== NOT_ATTEMPTED);
      setResults((prev) => ({ ...prev, ...Object.fromEntries(reached.map((x) => [x.uid, x])) }));
      if (r.halt) toast(r.items.find((x) => x.halt)?.error ?? "99acres stopped the post", "gold");
    } catch (e) {
      // 502/503 = login, our IP or config: refused before anything was claimed.
      toast(e instanceof Error ? e.message : "99acres refused the post", "gold");
    }
    setRunning(false);
    setRound((x) => x + 1);
  };

  const lookalikeText = (l: AcresCheck["lookalikes"][number]) =>
    `Looks like ${l.uid} (${l.status ? `${l.status} on 99acres` : inRun.has(l.uid) ? "also in this run" : "not listed"})`;

  return createPortal(
    <div className={overlayClass} onClick={running ? undefined : onClose}>
      <div className="modal acres-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="List on 99acres">
        <button className="modal-x" onClick={onClose} aria-label="Close"><IconX /></button>
        <h3>List on 99acres <span className="acres-sub">{properties.length} selected</span></h3>
        <div className="acres-top">
          <label>Set ownership for all
            <select className="ctl" value={allOwn} disabled={running}
                    onChange={(e) => { setAllOwn(e.target.value); setOwn({}); }}>
              <option value="">Choose…</option>
              {OWNTYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
          <label className="acres-check-l">
            <input type="checkbox" checked={photos} disabled={running} onChange={(e) => setPhotos(e.target.checked)} /> Send photos
          </label>
          <span className="acres-sub">Map pin and age come from master_societies.</span>
        </div>

        {checkError && <div className="acres-err">{checkError}</div>}
        <div className="acres-rows">
          <table className="tbl">
            <thead><tr><th className="cell-tight" /><th>Property</th><th className="cell-tight">Age</th><th className="cell-tight">Ownership</th><th>99acres</th></tr></thead>
            <tbody>
              {properties.map((p) => {
                const c = checks?.get(p.uid);
                const res = results[p.uid];
                const blocked = c && !c.ok && c.problems.length === 0;   // already live / unknown / duplicate
                return (
                  <Fragment key={p.uid}>
                    <tr className={blocked ? "acres-blocked" : undefined}>
                      <td className="cell-tight">
                        {c?.ok && !res && (
                          <input type="checkbox" checked={ticked.has(p.uid)} disabled={running}
                                 onChange={() => setTicked((s) => { const x = new Set(s); x.has(p.uid) ? x.delete(p.uid) : x.add(p.uid); return x; })} />
                        )}
                      </td>
                      <td>
                        <b>{p.uid}</b> · {p.society_name ?? "—"}
                        <div className="sub">{[p.tower_no && `T-${p.tower_no}`, p.unit_no, p.configuration, p.listing_price != null && `₹${Number(p.listing_price).toLocaleString("en-IN")} L`].filter(Boolean).join(" · ")}</div>
                      </td>
                      <td className="cell-tight">{c?.age ? AGE_LABEL[c.age] : "—"}</td>
                      <td className="cell-tight">
                        <select className="ctl" value={ownOf(p.uid)} disabled={running || !!res || !!blocked}
                                onChange={(e) => setOwn((o) => ({ ...o, [p.uid]: e.target.value }))}>
                          <option value="">Choose…</option>
                          {OWNTYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                      </td>
                      <td>
                        <div>{res ? (
                          res.status === "live"
                            ? <span className="stage won">Live · {res.prop_id}{res.quality_score != null ? ` · score ${res.quality_score}` : ""}</span>
                            : <span className="acres-err">{res.error ?? res.problems.join(" · ")}</span>
                        ) : !c ? <span className="acres-sub">Checking…</span>
                          : blocked ? <>Already {c.status} on 99acres</>
                          : c.problems.length ? <span className="acres-err">{c.problems.join(" · ")}</span>
                          : <span className="stage won">Ready</span>}</div>
                        {c?.lookalikes.map((l) => <div key={l.uid} className="acres-warn">{lookalikeText(l)}</div>)}
                        {c?.pin && (
                          <a className="acres-link" href={`https://www.google.com/maps?q=${c.pin.lat},${c.pin.lng}`}
                             target="_blank" rel="noreferrer">Pin</a>
                        )}
                        {c?.payload && (
                          <details className="acres-payload"><summary>Show payload</summary>
                            <pre>{JSON.stringify(c.payload, null, 2)}</pre></details>
                        )}
                      </td>
                    </tr>
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="acres-foot">
          <span className="acres-sub">{tickedReady.length} ticked and ready · each Post lists the next one</span>
          <div style={{ flex: 1 }} />
          <button className="btn primary" disabled={running || !tickedReady.length} onClick={run}>
            {running ? "Posting…" : `Post ${PER_RUN}`}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
