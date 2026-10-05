/* The Campaigns tab (spec §9): every run — manual and auto — newest first, with its delivery funnel. The funnel is
   computed on the server from the recipients on every read, and the list is polled (15 s), so a sending campaign's
   numbers move on their own. "+ New campaign" opens the build panel inline above the list; saving a draft closes it
   and the draft is the first row. A name links to /wa-campaigns/:id, the campaign's own page. */
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { SkeletonRows } from "../../components/Skeleton";
import { WaCampaignRow } from "../../lib/api";
import { useWaCampaigns } from "../../lib/queries";
import { fmtIST } from "../../lib/wa";
import NewCampaign from "./NewCampaign";

const SOURCE_LABEL: Record<string, string> = {
  upload: "Upload", paste: "Paste", wa_contacts: "WhatsApp contacts", repeat: "Repeat", auto: "Auto",
};

// a status's chip colour — `.wc-chip` modifiers: "" neutral, on = green, off = red, blue / amber
const STATUS_CHIP: Record<string, string> = { draft: "", sending: "blue", paused: "amber", done: "on", cancelled: "off" };
// the Templates tab's chips are capitalised ("Active"); a status the server adds later shows as it came
const STATUS_LABEL: Record<string, string> = { draft: "Draft", sending: "Sending", paused: "Paused", done: "Done", cancelled: "Cancelled" };

// the six funnel columns; `hint` explains what a number means where the name alone can't
const FUNNEL_COLS = [
  { key: "accepted", label: "Accepted",
    hint: "Gupshup took the message and no 'sent' receipt has arrived yet. A number that never goes down means the template app isn't subscribed to the sent / delivered / read events in Gupshup." },
  { key: "sent", label: "Sent", hint: "Handed to WhatsApp — includes everything delivered or read." },
  { key: "delivered", label: "Delivered", hint: "Reached the phone — includes everything read." },
  { key: "read", label: "Read", hint: "" },
  { key: "replied", label: "Replied", hint: "Wrote back after this campaign's message and before the next one to them." },
  { key: "failed", label: "Failed", hint: "" },
] as const;

function Row({ c }: { c: WaCampaignRow }) {
  const draft = c.status === "draft";
  const inList = c.counts.recipients;
  return (
    <tr>
      <td>
        <Link to={`/wa-campaigns/${c.id}`} className="wc-link">{c.name}</Link>
        <div className="wc-sub">{inList.toLocaleString("en-IN")} in list{c.counts.skipped ? ` · ${c.counts.skipped.toLocaleString("en-IN")} skipped` : ""}</div>
      </td>
      <td className="cell-text"><span title={c.template_name}>{c.template_name}</span></td>
      <td className="cell-tight">{c.auto_campaign_id || c.source === "auto" ? SOURCE_LABEL.auto : SOURCE_LABEL[c.source] ?? c.source}</td>
      <td className="cell-tight"><span className={"wc-chip " + (STATUS_CHIP[c.status] ?? "")}>{STATUS_LABEL[c.status] ?? c.status}</span></td>
      <td className="cell-tight">{draft ? "—" : fmtIST(c.launched_at)}</td>
      {FUNNEL_COLS.map((f) => {
        const n = c.counts[f.key];
        // a draft has sent nothing, so a column of zeros would only read as "all of it failed" — a dash instead
        const cls = "cell-tight wc-num" + (draft || n === 0 ? " zero" : f.key === "failed" ? " bad" : "");
        return <td key={f.key} className={cls}>{draft ? "—" : n.toLocaleString("en-IN")}</td>;
      })}
    </tr>
  );
}

export default function CampaignsTab() {
  const { data, isLoading, error } = useWaCampaigns();
  /* `?repeat=<id>` (the campaign page's "Repeat this list") opens the panel straight away with that list picked.
     Read once; closing the panel drops it from the URL so "+ New campaign" afterwards starts blank. */
  const [params, setParams] = useSearchParams();
  const [initialRepeat] = useState(params.get("repeat"));
  const [creating, setCreating] = useState(!!initialRepeat);
  const closeNew = () => {
    setCreating(false);
    if (params.has("repeat")) setParams((p) => { p.delete("repeat"); return p; }, { replace: true });
  };
  const items = data?.items ?? [];
  return (
    <>
      <div className="wc-bar">
        <button className={"btn sm " + (creating ? "ghost" : "primary")} onClick={() => (creating ? closeNew() : setCreating(true))}>
          {creating ? "Close" : "+ New campaign"}
        </button>
      </div>
      {creating && <NewCampaign onClose={closeNew} initialRepeat={initialRepeat} />}
      <div className="card table-wrap">
        {isLoading ? <SkeletonRows rows={4} /> : error ? (
          // a failed load must not read as an empty book — "No campaigns yet" invites building one that exists
          <div className="empty" style={{ padding: 40 }}>Couldn't load the campaigns — {error.message}</div>
        ) : !items.length ? (
          <div className="empty" style={{ padding: 40 }}>No campaigns yet — press + New campaign to build the first one.</div>
        ) : (
          <table className="wc-table">
            <thead>
              <tr>
                <th>Name</th><th>Template</th><th>Source</th><th>Status</th><th>Launched (IST)</th>
                {FUNNEL_COLS.map((f) => <th key={f.key} className="wc-num" title={f.hint || undefined}>{f.label}</th>)}
              </tr>
            </thead>
            <tbody>{items.map((c) => <Row key={c.id} c={c} />)}</tbody>
          </table>
        )}
      </div>
    </>
  );
}
