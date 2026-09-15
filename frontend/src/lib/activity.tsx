/* Rendering an activity_log row — shared by the Logs page and the lead popup's
   "Lead history" card.

   It lives here rather than in either page because the two must not drift: a
   stage_change that reads "new → qualified" on one screen and "stage: new → qualified"
   on the other is the same event described two ways, and the reader has to work out
   they are the same. Same reason `lib/report.ts` is shared by the report summary and
   its drill-down.

   `Details` is the whole point of both views: each action renders as a SENTENCE, not
   as three raw columns the reader assembles in their head. */
import { ActivityRow } from "./api";
import { metaQuestionLabel, srcLabel } from "./leads";
import { formatDate, formatDateTime } from "./queries";

export const pretty = (v: string) => v.replace(/_/g, " ");

/* Colour by consequence, not by verb: the reader is scanning for "did something bad
   happen to a lead", so a rejection and a lost call read the same way. */
const GOOD = new Set(["stage_change_qualified", "call_connected", "marked_hot", "assigned"]);
const BAD = new Set(["call_missed", "unmarked_hot"]);

export function actionStyle(r: ActivityRow) {
  if (r.action === "stage_change") {
    const to = r.after_value || "";
    if (["won", "qualified", "visit_scheduled", "revisit_scheduled"].includes(to))
      return { background: "var(--emerald-soft)", color: "var(--emerald-deep)" };
    if (["rejected", "rnr"].includes(to))
      return { background: "var(--coral-soft)", color: "var(--coral)" };
    return { background: "var(--amber-soft)", color: "var(--amber)" };
  }
  if (GOOD.has(r.action)) return { background: "var(--emerald-soft)", color: "var(--emerald-deep)" };
  if (BAD.has(r.action)) return { background: "var(--coral-soft)", color: "var(--coral)" };
  return { background: "var(--panel-2)", color: "var(--ink-2)" };
}

/* One sentence per action. Falls through to a generic field diff, so an action added
   later still renders something useful rather than a blank cell. */
export function Details({ r }: { r: ActivityRow }) {
  const m = (r.metadata || {}) as Record<string, any>;
  const val = (v: string | null) => v ?? "—";

  switch (r.action) {
    case "stage_change":
      return (
        <>
          <b>{val(r.before_value)}</b> → <b>{val(r.after_value)}</b>
          {m.reason && <span className="lg-sub"> · {m.reason}</span>}
          {m.notes && <span className="lg-sub"> — {m.notes}</span>}
        </>
      );
    case "assigned":
      return r.after_value
        ? <>to <b>{r.after_value}</b>{r.before_value && <span className="lg-sub"> (was {r.before_value})</span>}
            {m.bulk && <span className="lg-sub"> · part of a {m.bulk}-lead bulk assign</span>}</>
        : <>unassigned{r.before_value && <span className="lg-sub"> (was {r.before_value})</span>}</>;
    case "note_added":
      return <span className="lg-note">“{m.note}”</span>;
    case "call_connected":
      return <>reached them<span className="lg-sub"> · {m.source === "campaign" ? "auto-dialer" : "worklist"}</span></>;
    case "call_missed":
      return (
        <>
          {m.reason || "not reached"}
          <span className="lg-sub"> · miss {val(r.after_value)}</span>
          {m.follow_up_at && <span className="lg-sub"> · retry {formatDateTime(m.follow_up_at)}</span>}
          {m.notes && <span className="lg-sub"> — {m.notes}</span>}
        </>
      );
    case "lead_created": {
      // "{Lead} created on {date} via {source}". The date is the row's own created_at —
      // for backfilled entries that IS the lead's creation time, by construction.
      const src = String(m.source ?? "");
      const via = srcLabel(src) === src ? pretty(src) : srcLabel(src);
      return (
        <>
          <b>{r.lead_name || (m.name as string) || "Lead"}</b> created on {formatDate(r.created_at)}
          {src && <> via <b>{via}</b></>}
        </>
      );
    }
    case "lead_repeat": {
      // the same phone arrived from another source and was folded into this lead
      const src = String(m.source ?? "");
      const via = srcLabel(src) === src ? pretty(src) : srcLabel(src);
      return <><b>{r.lead_name || (m.name as string) || "Lead"}</b> came in again{src && <> via <b>{via}</b></>}</>;
    }
    case "meta_form_submitted": {
      // What arrived, and when. Questions are humanised with the same helper the Meta
      // Leads page uses; ANSWERS stay exactly as Meta returned them.
      const answers = Object.entries((m.answers ?? {}) as Record<string, unknown>);
      const via = [m.campaign_name, m.ad_name].filter(Boolean).join(" · ");
      return (
        <>
          Meta form {m.new_lead ? "created this lead" : m.merged ? "arrived for this lead" : "submitted again"}
          {via && <span className="lg-sub"> · {via}</span>}
          {answers.length > 0 && (
            <span className="lg-answers">
              {answers.map(([q, a]) => (
                <span key={q} className="lg-answer">
                  <span className="lg-q">{metaQuestionLabel(q)}</span> {a == null || a === "" ? "—" : String(a)}
                </span>
              ))}
            </span>
          )}
        </>
      );
    }
    case "marked_hot":   return <>starred as hot</>;
    case "unmarked_hot": return <>no longer hot</>;
    case "sync_run":
      return <>{Object.entries(m).map(([k, v]) => `${k}: ${v}`).join(" · ") || "ran"}</>;
    default:
      // generic: a field diff if there is one, else whatever context was recorded
      if (r.field) return <><b>{r.field}</b>: {val(r.before_value)} → {val(r.after_value)}</>;
      return <span className="lg-sub">{Object.keys(m).length ? JSON.stringify(m) : "—"}</span>;
  }
}
