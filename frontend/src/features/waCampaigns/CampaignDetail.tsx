/* One campaign (spec §9): its funnel as count boxes, what each button got, and every recipient with their status
   and reply. A box filters the table (the server's ?status=); a row opens that person's WhatsApp thread.
   Actions — Launch / Pause / Resume / Cancel, CSV, Repeat, Make it automatic — sit in the topbar strip.

   The detail polls while the campaign is sending (queries.ts `waPollMs`), so Sent → Delivered → Read and the
   replies move on their own. */
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../../components/AuthContext";
import { Skeleton, SkeletonRows } from "../../components/Skeleton";
import { ExtraBox, StageBoxes } from "../../components/StageBoxes";
import { useToast } from "../../components/Toast";
import { TopbarSlot } from "../../components/TopbarSlot";
import { api, WaCampaignAction, WaRecipientFilter, WaRecipientRow, waReasonLabel } from "../../lib/api";
import { useWaCampaign, useWaCampaignAction, useWaCampaignRecipients, useWaRetryRecipient } from "../../lib/queries";
import { fmtIST } from "../../lib/wa";

const num = (n: number) => n.toLocaleString("en-IN");

const STATUS_LABEL: Record<string, string> = {
  draft: "Draft", sending: "Sending", paused: "Paused", done: "Done", cancelled: "Cancelled",
};
const STATUS_CHIP: Record<string, string> = { draft: "", sending: "blue", paused: "amber", done: "on", cancelled: "off" };
const SOURCE_LABEL: Record<string, string> = {
  upload: "Upload", paste: "Paste", wa_contacts: "WhatsApp contacts", repeat: "Repeat", auto: "Auto",
};

// a recipient's status as the admin reads it; "submitted" = claimed, outcome never recorded (spec §5.2)
const REC_STATUS: Record<string, { label: string; cls: string }> = {
  queued: { label: "Waiting", cls: "" },
  submitted: { label: "Unknown — check", cls: "amber" },
  accepted: { label: "Accepted", cls: "gold" },
  sent: { label: "Sent", cls: "blue" },
  delivered: { label: "Delivered", cls: "slate" },
  read: { label: "Read", cls: "on" },
  failed: { label: "Failed", cls: "off" },
  skipped: { label: "Skipped", cls: "amber" },
};

function AdminsOnly() {
  return (
    <div className="card">
      <div className="empty" style={{ padding: 48, textAlign: "center" }}>
        <div style={{ fontWeight: 600, color: "var(--ink-2)" }}>Admins only</div>
        <div style={{ fontSize: 12.5, marginTop: 6 }}>
          WhatsApp campaigns message real customers, so they are limited to admins.
        </div>
      </div>
    </div>
  );
}

export default function CampaignDetail() {
  const { enabled, user } = useAuth();
  const isAdmin = !enabled || user?.role === "admin";
  return isAdmin ? <Detail /> : <AdminsOnly />;
}

function Detail() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const [filter, setFilter] = useState<WaRecipientFilter | "">("");
  const [exporting, setExporting] = useState(false);
  const detail = useWaCampaign(id);
  const rows = useWaCampaignRecipients(id, filter || undefined);
  const action = useWaCampaignAction();
  const retry = useWaRetryRecipient();

  const c = detail.data?.campaign;
  const counts = detail.data?.counts;

  const act = (a: WaCampaignAction) => {
    const ask = a === "launch" ? `Start sending to ${num(counts?.queued ?? 0)} people now? It messages real customers.`
      : a === "cancel" ? "Cancel this campaign? Nothing more will be sent, and it can't be started again." : null;
    if (ask && !window.confirm(ask)) return;
    action.mutate({ id, action: a }, {
      onSuccess: () => toast({ launch: "Campaign launched", pause: "Paused", resume: "Resumed", cancel: "Cancelled" }[a], "green"),
      onError: (e: Error) => toast(e.message, "gold"),     // 503 names the missing env vars; 409 an illegal move
    });
  };

  const doRetry = (r: WaRecipientRow) =>
    retry.mutate({ id, rid: r.id }, {
      onSuccess: () => toast("Back in the queue", "green"),
      onError: (e: Error) => toast(e.message, "gold"),     // the server's reason: opted out, no WhatsApp, 24 h cap
    });

  const doExport = async () => {
    setExporting(true);
    try { await api.waCampaignExport(id, c?.name ?? "campaign"); }
    catch (e) { toast((e as Error).message, "gold"); }
    finally { setExporting(false); }
  };

  if (detail.isLoading) {
    return <div className="card panel-pad"><Skeleton w="40%" h={18} /><div style={{ height: 14 }} /><SkeletonRows rows={4} /></div>;
  }
  if (detail.error || !c || !counts) {
    return (
      <div>
        <Link to="/wa-campaigns" className="back">← Campaigns</Link>
        <div className="card"><div className="empty" style={{ padding: 40 }}>
          Couldn't load this campaign — {detail.error?.message ?? "not found"}
        </div></div>
      </div>
    );
  }

  const boxes: ExtraBox[] = [
    { key: "accepted", label: "Accepted", hue: "var(--gold)", count: counts.accepted,
      hint: "Gupshup took the message and no 'sent' receipt has arrived yet" },
    { key: "sent", label: "Sent", hue: "var(--blue)", count: counts.sent },
    { key: "delivered", label: "Delivered", hue: "var(--slate)", count: counts.delivered },
    { key: "read", label: "Read", hue: "var(--emerald)", count: counts.read,
      hint: "Only people with read receipts switched on — the real number is higher" },
    { key: "replied", label: "Replied", hue: "var(--brand)", count: counts.replied },
    { key: "no_reply", label: "No reply", hue: "var(--muted)", count: counts.no_reply },
    { key: "failed", label: "Failed", hue: "var(--coral)", count: counts.failed },
    { key: "skipped", label: "Skipped", hue: "var(--amber)", count: counts.skipped },
    ...(counts.unknown > 0 ? [{ key: "submitted", label: "Unknown — check", hue: "var(--ink-2)", count: counts.unknown,
      hint: "Claimed for sending but Gupshup's answer was never recorded — it may or may not have gone" }] : []),
  ];
  const tallies = Object.entries(detail.data?.buttons ?? {});
  const manual = c.source !== "auto" && !c.auto_campaign_id;
  const items = rows.data ?? [];

  return (
    <div>
      <TopbarSlot>
        {c.status === "draft" && <button className="btn primary sm" disabled={action.isPending} onClick={() => act("launch")}>Launch</button>}
        {c.status === "sending" && <button className="btn ghost sm" disabled={action.isPending} onClick={() => act("pause")}>Pause</button>}
        {c.status === "paused" && <button className="btn primary sm" disabled={action.isPending} onClick={() => act("resume")}>Resume</button>}
        {["draft", "sending", "paused"].includes(c.status) &&
          <button className="btn ghost sm" disabled={action.isPending} onClick={() => act("cancel")}>Cancel</button>}
        <button className="btn ghost sm" disabled={exporting} onClick={doExport}>{exporting ? "Exporting…" : "Export CSV"}</button>
        <Link className="btn ghost sm" to={`/wa-campaigns?tab=campaigns&repeat=${c.id}`}>Repeat this list</Link>
        {manual && c.status !== "draft" && <Link className="btn ghost sm" to={`/wa-campaigns?tab=auto&seed=${c.id}`}>Make it automatic</Link>}
      </TopbarSlot>

      <Link to="/wa-campaigns" className="back">← Campaigns</Link>
      <div className="wc-detail-head">
        <h3 className="sec-title">{c.name}</h3>
        <span className={"wc-chip " + (STATUS_CHIP[c.status] ?? "")}>{STATUS_LABEL[c.status] ?? c.status}</span>
      </div>
      <p className="sec-sub">
        Template {c.template_name} · {SOURCE_LABEL[c.source] ?? c.source}
        {c.launched_at ? ` · launched ${fmtIST(c.launched_at)} IST` : ""}
        {c.finished_at ? ` · finished ${fmtIST(c.finished_at)} IST` : ""}
        {` · ${c.send_window_start}–${c.send_window_end} IST, ${c.rate_per_minute}/min`}
        {counts.queued > 0 && c.status !== "draft" ? ` · ${num(counts.queued)} still waiting to send` : ""}
      </p>
      <div className="wc-preview">{c.template_body}</div>

      <div style={{ height: 14 }} />
      <StageBoxes total={counts.recipients} extra={boxes} extraValue={filter}
        onExtra={(k) => setFilter(k as WaRecipientFilter | "")} />
      {c.status === "paused" && c.status_note && <div className="wc-hint bad">{c.status_note}</div>}
      {tallies.length > 0 && (
        <div className="wc-hint">Buttons: {tallies.map(([t, n]) => `${t} ${num(n)}`).join(" · ")}</div>
      )}

      <div className="card table-wrap" style={{ marginTop: 12 }}>
        {rows.isLoading ? <SkeletonRows rows={4} /> : rows.error ? (
          <div className="empty" style={{ padding: 40 }}>Couldn't load the recipients — {rows.error.message}</div>
        ) : !items.length ? (
          <div className="empty" style={{ padding: 40 }}>{filter ? "Nobody in this group." : "No recipients."}</div>
        ) : (
          <table className="wc-table">
            <thead>
              <tr><th>Name</th><th>Phone</th><th>Status</th><th>Owner</th><th>First reply</th><th>Replied at (IST)</th><th /></tr>
            </thead>
            <tbody>
              {items.map((r) => {
                const st = REC_STATUS[r.status] ?? { label: r.status, cls: "" };
                const chat = `/chat?phone=91${r.phone10}`;
                const why = r.status === "failed" ? r.error : r.status === "skipped" ? waReasonLabel(r.skip_reason, null) : null;
                return (
                  <tr key={r.id} className="wc-row"
                    onClick={(e) => { if (!(e.target as HTMLElement).closest("button, a, input, select, textarea, label")) nav(chat); }}>
                    <td className="cell-text"><Link to={chat} className="wc-link" title={r.name ?? ""}>{r.name || "—"}</Link></td>
                    <td className="cell-tight wc-id">{r.phone10}</td>
                    <td>
                      <span className={"wc-chip " + st.cls}>{st.label}</span>
                      {why && <div className="wc-sub" title={why}>{why}</div>}
                    </td>
                    <td className="cell-tight">{r.owner || "—"}</td>
                    <td className="cell-text">
                      {r.first_reply ? <span title={r.first_reply}>{r.first_reply}{r.replies > 1 ? ` (+${r.replies - 1})` : ""}</span> : "—"}
                    </td>
                    <td className="cell-tight">{fmtIST(r.replied_at)}</td>
                    <td className="cell-tight">
                      {(r.status === "failed" || r.status === "submitted") && (
                        <button className="btn ghost sm" disabled={retry.isPending} onClick={() => doRetry(r)}>Retry</button>)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
