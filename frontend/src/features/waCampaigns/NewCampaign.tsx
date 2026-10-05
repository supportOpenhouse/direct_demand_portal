/* New campaign (spec §5.1, §9) — ONE inline panel, top to bottom:
   template → who gets it (upload / paste / WhatsApp contacts / repeat a list) → column mapping → CHECK LIST →
   name · send window · rate → Save draft. Nothing is sent from here: a draft is a frozen list, and launching it
   is a later step.

   Preview and Save send the SAME body. `buildWaPayload` is the only place a request is assembled, so the list the
   admin checked is the list that gets saved; and Save only wakes once the CURRENT inputs have been checked — the
   result for an earlier template / file / mapping is shown faded and never trusted. (The server re-validates on
   Save either way; what this prevents is saving a list the admin never saw.) */
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import SlideTabs from "../../components/SlideTabs";
import { useToast } from "../../components/Toast";
import { slotRe, waReasonLabel, WaPreview, WaPreviewIn, WaSource } from "../../lib/api";
import { useCreateWaCampaign, useWaCampaigns, useWaPreview, useWaTemplates } from "../../lib/queries";

export const WA_COOLDOWN_DAYS = 7;                  // spec §10's default; the server applies it again on Save
const MAX_FILE_BYTES = 10 * 1024 * 1024;            // the server's file_b64 cap is 14M base64 characters ≈ 10.5 MB
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;           // routers/wa_campaigns.HHMM — the send loop compares these as TEXT

const SOURCES: { key: WaSource; label: string }[] = [
  { key: "upload", label: "Upload" },
  { key: "paste", label: "Paste" },
  { key: "wa_contacts", label: "WhatsApp contacts" },
  { key: "repeat", label: "Repeat a list" },
];

/* Where one template variable gets its value: a column of the list, or one fixed text for everybody. */
export type WaSlot = { kind: "col"; col: number } | { kind: "fixed"; value: string };

/* A slot nobody has touched. Upload and paste read the columns right after the phone (phone, then one value per
   variable). WhatsApp contacts have only [phone, name], so the FIRST slot starts as the name and the rest as a
   fixed value (left blank it falls back to the template's own default). A repeat has no mapping at all.
   ponytail: an upload's first check runs on this positional guess, because the file's headers only come back WITH
   a check. Guessing columns from the header names — or re-checking once, automatically, when they arrive — is
   the upgrade; today the admin fixes the mapping boxes and checks again. */
export function defaultSlot(source: WaSource, i: number): WaSlot {
  if (source === "wa_contacts") return i === 0 ? { kind: "col", col: 1 } : { kind: "fixed", value: "" };
  if (source === "repeat") return { kind: "fixed", value: "" };
  return { kind: "col", col: i + 1 };
}

export interface WaForm {
  templateId: string;
  source: WaSource;
  fileName: string | null;
  fileB64: string | null;
  paste: string;
  repeatOf: string;
  repeatMode: "everyone" | "non_responders";
  phoneCol: number;
  nameCol: number | null;
  slots: WaSlot[];
}

/* The ONE place a preview / create body is built. Only what the chosen source uses is sent — a file picked
   earlier and then abandoned for a paste must not ride along as a 10 MB base64 string. */
export function buildWaPayload(f: WaForm): WaPreviewIn {
  const upload = f.source === "upload";
  const mapped = f.source !== "repeat";             // a repeat copies the source campaign's own stored variables
  return {
    template_id: f.templateId, source: f.source,
    file_name: upload ? f.fileName : null, file_b64: upload ? f.fileB64 : null,
    paste: f.source === "paste" ? f.paste : null,
    repeat_of: f.source === "repeat" ? f.repeatOf || null : null, repeat_mode: f.repeatMode,
    phone_col: upload ? f.phoneCol : 0,             // paste: the phone is always the first cell
    name_col: upload ? f.nameCol : f.source === "wa_contacts" ? 1 : null,
    var_cols: mapped ? f.slots.map((s) => (s.kind === "col" ? s.col : null)) : [],
    fixed: mapped ? f.slots.map((s) => (s.kind === "fixed" ? s.value : null)) : [],
    cooldown_days: WA_COOLDOWN_DAYS,
  };
}

const slotKey = (source: WaSource, i: number) => `${source}:${i}`;
const fmtSize = (b: number) =>
  b < 1024 * 1024 ? `${Math.max(1, Math.round(b / 1024))} KB` : `${(b / 1024 / 1024).toFixed(1)} MB`;
const num = (n: number) => n.toLocaleString("en-IN");

const COUNT_BOXES = [
  { key: "valid", label: "Valid", hue: "var(--emerald)" },
  { key: "invalid", label: "Invalid", hue: "var(--coral)" },
  { key: "duplicate", label: "Duplicate", hue: "var(--amber)" },
  { key: "skipped", label: "Skipped", hue: "var(--ink-2)" },
] as const;

const ROW_CHIP: Record<string, { cls: string; label: string }> = {
  valid: { cls: "on", label: "Valid" },
  invalid: { cls: "off", label: "Invalid" },
  duplicate: { cls: "amber", label: "Duplicate" },
  skipped: { cls: "", label: "Skipped" },
};

function PreviewResults({ data, stale }: { data: WaPreview; stale: boolean }) {
  const { counts, rows } = data;
  const total = counts.valid + counts.invalid + counts.duplicate + counts.skipped;
  /* Excel rounds a 12-digit phone to 9.19877E+11 once the column is a number, and the real digits are gone — when
     most of a list reads as "not a phone" that is the usual reason. Judged on the rows the server sends back (the
     first 200): `counts.invalid` also holds blank variables, which say nothing about the phone column.
     ponytail: a damaged phone column is damaged all the way down, so 200 rows is enough to see it; a list that is
     only bad past row 200 slips through. Have the preview return an invalid_phone count to judge the whole list. */
  const unreadable = rows.filter((r) => r.reason === "invalid_phone").length;
  const mostlyUnreadable = rows.length > 0 && unreadable * 2 > rows.length;
  return (
    <div className={"wc-results" + (stale ? " wc-stale" : "")}>
      <div className="stage-counts">
        <div className="stage-pills">
          {COUNT_BOXES.map((b) => (
            <div key={b.key} className="count-pill wc-count" style={{ ["--pill-hue" as string]: b.hue }}>
              <span className="num">{num(counts[b.key])}</span>
              <span className="lbl">{b.label.toUpperCase()}</span>
            </div>
          ))}
        </div>
      </div>
      {data.over_daily_limit && (
        <div className="wc-warn">
          {num(counts.valid)} valid numbers is more than the {num(data.daily_limit)} people this business can message
          in 24 hours. The list is saved whole, but it will take more than a day to send — sending pauses while the
          last 24 hours already hold {num(data.daily_limit)} people.
        </div>
      )}
      {mostlyUnreadable && (
        <div className="wc-hint bad">
          Most numbers couldn't be read. If this came from Excel, format the phone column as Text before saving —
          Excel rounds long numbers (9.19877E+11) and the real digits are lost.
        </div>
      )}
      {data.samples.length > 0 && (
        <>
          <div className="wc-hint">Sample messages — exactly what each person will see</div>
          {data.samples.map((s, i) => <div className="wc-preview" key={i}>{s}</div>)}
        </>
      )}
      {rows.length > 0 && (
        <>
          <div className="wc-hint">
            {rows.length < total ? `The first ${num(rows.length)} of ${num(total)} rows, in list order` : `All ${num(total)} rows, in list order`}
          </div>
          <div className="card table-wrap wc-rows">
            <table className="wc-table">
              <thead><tr><th>#</th><th>Phone</th><th>Name</th><th>Values</th><th>Status</th><th>Why</th></tr></thead>
              <tbody>{rows.map((r, i) => {
                const chip = ROW_CHIP[r.status] ?? { cls: "", label: r.status };
                const values = r.variables.map((v) => v ?? "—").join(" · ");
                return (
                  <tr key={i}>
                    <td className="cell-tight">{i + 1}</td>
                    <td className="cell-tight wc-id">{r.phone10 ?? "—"}</td>
                    <td className="cell-text"><span title={r.name ?? ""}>{r.name || "—"}</span></td>
                    <td className="cell-text"><span title={values}>{values || "—"}</span></td>
                    <td className="cell-tight"><span className={"wc-chip " + chip.cls}>{chip.label}</span></td>
                    <td>{waReasonLabel(r.reason, WA_COOLDOWN_DAYS)}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export default function NewCampaign({ onClose, initialRepeat = null }: { onClose: () => void; initialRepeat?: string | null }) {
  const toast = useToast();
  const navigate = useNavigate();
  const templates = useWaTemplates();
  const campaigns = useWaCampaigns();
  const preview = useWaPreview();
  const create = useCreateWaCampaign();

  const [templateId, setTemplateId] = useState("");
  const [source, setSource] = useState<WaSource>(initialRepeat ? "repeat" : "upload");   // ?repeat=<id> preselects it
  // upload
  const [file, setFile] = useState<{ name: string; size: number } | null>(null);
  const [fileB64, setFileB64] = useState<string | null>(null);
  const [fileId, setFileId] = useState(0);              // which file the base64 is — stands in for it in the change key
  const [fileErr, setFileErr] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  const [phoneCol, setPhoneCol] = useState(0);
  const [nameCol, setNameCol] = useState<number | null>(null);
  const picks = useRef(0);                              // each file pick bumps this: a slow read must not land late
  // paste
  const [paste, setPaste] = useState("");
  // repeat
  const [rawRepeat, setRepeatOf] = useState(initialRepeat ?? "");
  const [repeatMode, setRepeatMode] = useState<"everyone" | "non_responders">("everyone");
  // per-slot choices the admin has made, keyed by source + slot; a slot without one shows its source's default
  const [picked, setPicked] = useState<Record<string, WaSlot>>({});
  // the draft
  const [name, setName] = useState("");
  const [winStart, setWinStart] = useState("10:00");
  const [winEnd, setWinEnd] = useState("19:00");
  const [rate, setRate] = useState("30");               // text, so the box can be empty while it is being retyped
  const [saveErr, setSaveErr] = useState<string | null>(null);
  // the latest check, with the key of the inputs it answered
  const [result, setResult] = useState<{ key: string; data?: WaPreview; error?: string } | null>(null);

  const active = (templates.data?.items ?? []).filter((t) => t.active);
  const tpl = active.find((t) => t.id === templateId);
  const n = tpl?.variable_count ?? 0;
  const labels = tpl?.variable_labels ?? [];
  const defaults = tpl?.variable_defaults ?? [];
  const slots: WaSlot[] = Array.from({ length: n }, (_, i) => picked[slotKey(source, i)] ?? defaultSlot(source, i));
  const headers = source === "upload" ? result?.data?.headers ?? [] : [];
  const repeatable = (campaigns.data?.items ?? []).filter((c) => c.counts.recipients > 0);
  // the select can only show a campaign it lists: an id from the URL that isn't one of them (or not loaded yet)
  // must not ride along into the request while the box reads "Pick a campaign…"
  const repeatOf = repeatable.some((c) => c.id === rawRepeat) ? rawRepeat : "";

  // ONE body for Preview and Save. The key stands for it in the change check (the file is far too big to stringify).
  const body = buildWaPayload({ templateId, source, fileName: file?.name ?? null, fileB64, paste, repeatOf, repeatMode,
    phoneCol, nameCol, slots });
  const key = JSON.stringify({ ...body, file_b64: body.file_b64 ? fileId : null });
  const fresh = !!result && result.key === key;
  const data = result?.data;

  const needs = !tpl ? "Pick a template first."
    : source === "upload" && !fileB64 ? (reading ? "Reading the file…" : "Choose a file first.")
    : source === "paste" && !paste.trim() ? "Paste at least one number first."
    : source === "repeat" && !repeatOf ? "Pick the campaign to repeat first."
    : null;

  const nameOk = name.trim().length > 0 && name.trim().length <= 120;
  const windowOk = HHMM.test(winStart) && HHMM.test(winEnd) && winStart < winEnd;
  const rateNum = Number(rate);
  const rateOk = rate.trim() !== "" && Number.isInteger(rateNum) && rateNum >= 1 && rateNum <= 600;
  const blocked = !data ? "Check the list first."
    : !fresh ? "You changed something since the last check — check the list again."
    : data.counts.valid === 0 ? "Nothing to send — no number in this list can be messaged."
    : !nameOk ? "Give the campaign a name."
    : !windowOk ? "The send window must end after it starts (same day, IST)."
    : !rateOk ? "The rate must be a whole number from 1 to 600 per minute."
    : null;

  const pickTemplate = (id: string) => { setTemplateId(id); setPicked({}); };
  const setSlot = (i: number, s: WaSlot) => setPicked((p) => ({ ...p, [slotKey(source, i)]: s }));
  const onSlotSelect = (i: number, v: string) => {
    const cur = slots[i];
    setSlot(i, v === "fixed" ? { kind: "fixed", value: cur.kind === "fixed" ? cur.value : "" } : { kind: "col", col: Number(v) });
  };

  /* A new file is a new mapping: its columns are not the last file's. Everything about the old one goes, including
     any check that was run on it (its headers are what the mapping boxes list). */
  const onFile = (f: File | null) => {
    const mine = ++picks.current;
    setResult(null); setFile(null); setFileB64(null); setFileErr(null); setReading(false);
    setPhoneCol(0); setNameCol(null);
    setPicked((p) => Object.fromEntries(Object.entries(p).filter(([k]) => !k.startsWith("upload:"))));
    if (!f) return;
    if (!/\.(csv|xlsx)$/i.test(f.name)) { setFileErr("Upload a .csv or .xlsx file — an old .xls needs Save As → .xlsx first."); return; }
    if (f.size === 0) { setFileErr("That file is empty."); return; }
    if (f.size > MAX_FILE_BYTES) { setFileErr("That file is over 10 MB — split it into smaller lists."); return; }
    setFile({ name: f.name, size: f.size });
    setReading(true);
    const rd = new FileReader();
    rd.onload = () => {
      if (picks.current !== mine) return;
      const url = String(rd.result);
      setFileB64(url.slice(url.indexOf(",") + 1));      // "data:text/csv;base64,AAAA…" → "AAAA…"
      setFileId(mine); setReading(false);
    };
    rd.onerror = () => {
      if (picks.current !== mine) return;
      setFile(null); setReading(false); setFileErr("Couldn't read that file.");
    };
    rd.readAsDataURL(f);
  };

  const check = () => {
    const k = key, pick = picks.current;
    preview.mutate(body, {
      // A check started for a file the admin has since replaced answers a question nobody is asking — and would put
      // the OLD file's columns back in the mapping boxes. Anything else that changed meanwhile just makes it stale.
      onSuccess: (d) => { if (picks.current === pick) setResult({ key: k, data: d }); },
      onError: (e: Error) => { if (picks.current === pick) setResult({ key: k, error: e.message }); },
    });
  };

  const save = () => {
    setSaveErr(null);
    create.mutate({ ...body, name: name.trim(), send_window_start: winStart, send_window_end: winEnd, rate_per_minute: rateNum }, {
      onSuccess: (r) => { toast("Draft saved", "green"); onClose(); navigate(`/wa-campaigns/${r.id}`); },
      onError: (e: Error) => setSaveErr(e.message),
    });
  };

  const colOptions = (current: number | null) => [
    ...headers.map((h, j) => <option key={j} value={j}>{h.trim() || `Column ${j + 1}`}</option>),
    // a saved index past the header row is an empty column — listed, so the box shows what is really selected
    ...(current != null && current >= headers.length
      ? [<option key="beyond" value={current}>{`Column ${current + 1} (empty)`}</option>] : []),
  ];

  const slotRows = slots.map((s, i) => (
    <div className="two" key={i}>
      <div className="field">
        <label htmlFor={`wc-slot-${i}`}>{`{{${i + 1}}}`} · {labels[i] || `Variable ${i + 1}`}</label>
        <select id={`wc-slot-${i}`} value={s.kind === "fixed" ? "fixed" : s.col} onChange={(e) => onSlotSelect(i, e.target.value)}>
          {source === "upload" ? colOptions(s.kind === "col" ? s.col : null) : <option value={1}>Their WhatsApp name</option>}
          <option value="fixed">Fixed value…</option>
        </select>
      </div>
      {s.kind === "fixed" ? (
        <div className="field">
          <label htmlFor={`wc-fixed-${i}`}>Same for everyone</label>
          <input id={`wc-fixed-${i}`} value={s.value} placeholder={defaults[i] ? `Blank → "${defaults[i]}"` : "Type the value"}
            onChange={(e) => setSlot(i, { kind: "fixed", value: e.target.value })} />
        </div>
      ) : <div />}
    </div>
  ));

  const bodyPreview = tpl ? tpl.body.replace(slotRe(), (_, d) => `‹${labels[Number(d) - 1] || `Variable ${d}`}›`) : "";

  return (
    <div className="card panel-pad wc-new">
      <div className="wc-new-head">
        <div>
          <h3 className="sec-title">New campaign</h3>
          <p className="sec-sub">Build the list, check it, then save it as a draft. Nothing is sent from here.</p>
        </div>
        <button className="btn ghost sm" onClick={onClose}>Cancel</button>
      </div>

      <div className="field">
        <label htmlFor="wc-template">Template</label>
        <select id="wc-template" value={templateId} onChange={(e) => pickTemplate(e.target.value)}>
          <option value="">{templates.isLoading ? "Loading templates…" : "Pick a template…"}</option>
          {active.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        {templates.error && <div className="wc-hint bad">Couldn't load the templates — {templates.error.message}</div>}
        {!templates.isLoading && !templates.error && !active.length && (
          <div className="wc-hint">No active templates — add the approved ones on the Templates tab first.</div>)}
      </div>
      {tpl && <div className="wc-preview">{bodyPreview}</div>}

      <div className="wc-step">
        <h4>Who gets it</h4>
        <SlideTabs className="view-toggle">
          {SOURCES.map((s) => (
            <button key={s.key} className={s.key === source ? "on" : ""} onClick={() => setSource(s.key)}>{s.label}</button>))}
        </SlideTabs>

        {source === "upload" && (
          <div className="wc-src">
            <div className="wc-file">
              <label className="btn ghost sm wc-file-btn">
                Choose file…
                <input type="file" accept=".csv,.xlsx"
                  onChange={(e) => { onFile(e.target.files?.[0] ?? null); e.target.value = ""; }} />
              </label>
              <span className="wc-file-name">
                {reading ? "Reading…" : file ? `${file.name} · ${fmtSize(file.size)}` : "No file chosen"}
              </span>
            </div>
            <div className={"wc-hint" + (fileErr ? " bad" : "")}>
              {fileErr ?? ".csv or .xlsx — the first sheet, with a header row (up to 10 MB). Check the list once and the file's columns appear here for mapping."}
            </div>
            {headers.length > 0 && (
              <>
                <div className="two">
                  <div className="field">
                    <label htmlFor="wc-phone-col">Phone column</label>
                    <select id="wc-phone-col" value={phoneCol} onChange={(e) => setPhoneCol(Number(e.target.value))}>
                      {colOptions(phoneCol)}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="wc-name-col">Name column (optional)</label>
                    <select id="wc-name-col" value={nameCol ?? ""}
                      onChange={(e) => setNameCol(e.target.value === "" ? null : Number(e.target.value))}>
                      <option value="">None</option>
                      {colOptions(nameCol)}
                    </select>
                  </div>
                </div>
                {slotRows}
              </>
            )}
          </div>
        )}

        {source === "paste" && (
          <div className="wc-src">
            <div className="field">
              <label htmlFor="wc-paste">Numbers</label>
              <textarea id="wc-paste" rows={6} value={paste} onChange={(e) => setPaste(e.target.value)}
                placeholder={["98765 43210", ...Array.from({ length: n }, (_, i) => labels[i] || `Variable ${i + 1}`)].join(", ")} />
              <div className="wc-hint">
                One person per line: phone, then one value per variable, comma or tab.
                {n > 0 && ` For this template: phone, ${Array.from({ length: n }, (_, i) => labels[i] || `Variable ${i + 1}`).join(", ")}.`}
              </div>
            </div>
          </div>
        )}

        {source === "wa_contacts" && (
          <div className="wc-src">
            <div className="wc-hint">
              Everyone who has written to either WhatsApp number, isn't a lead yet, and hasn't opted out or been marked
              rejected — most recent first.
            </div>
            {slotRows}
          </div>
        )}

        {source === "repeat" && (
          <div className="wc-src">
            <div className="field">
              <label htmlFor="wc-repeat">Campaign to repeat</label>
              <select id="wc-repeat" value={repeatOf} onChange={(e) => setRepeatOf(e.target.value)}>
                <option value="">{campaigns.isLoading ? "Loading campaigns…" : "Pick a campaign…"}</option>
                {repeatable.map((c) => (
                  <option key={c.id} value={c.id}>{`${c.name} · ${c.template_name} · ${num(c.counts.recipients)} in list`}</option>))}
              </select>
              {campaigns.error && <div className="wc-hint bad">Couldn't load the campaigns — {campaigns.error.message}</div>}
            </div>
            <div className="wc-radios">
              <label className="wc-check">
                <input type="radio" name="wc-repeat-mode" checked={repeatMode === "everyone"} onChange={() => setRepeatMode("everyone")} />
                Everyone
              </label>
              <label className="wc-check">
                <input type="radio" name="wc-repeat-mode" checked={repeatMode === "non_responders"} onChange={() => setRepeatMode("non_responders")} />
                Only non-responders
              </label>
            </div>
            <div className="wc-hint">
              The same people and values are copied, then checked again: anyone who has opted out, become a lead or been
              messaged by another campaign recently is left out. The template must have as many variables as the one that list was sent with.
            </div>
          </div>
        )}
      </div>

      <div className="wc-step">
        <button className="btn primary" disabled={needs !== null || preview.isPending} onClick={check}>
          {preview.isPending ? "Checking…" : "Check list"}
        </button>
        {needs && <span className="wc-hint wc-inline">{needs}</span>}
        {result?.error && fresh && <div className="wc-hint bad">{result.error}</div>}
        {data && <PreviewResults data={data} stale={!fresh} />}
        {data && !fresh && (
          <div className="wc-hint">You changed something since this check — check the list again before saving.</div>)}
      </div>

      <div className="wc-step">
        <h4>Name and pace</h4>
        <div className="field">
          <label htmlFor="wc-campaign-name">Campaign name</label>
          <input id="wc-campaign-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="three">
          <div className="field">
            <label htmlFor="wc-from">Send from (IST)</label>
            <input id="wc-from" type="time" value={winStart} onChange={(e) => setWinStart(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="wc-until">Send until (IST)</label>
            <input id="wc-until" type="time" value={winEnd} onChange={(e) => setWinEnd(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="wc-rate">Messages per minute</label>
            <input id="wc-rate" type="number" min={1} max={600} step={1} value={rate} onChange={(e) => setRate(e.target.value)} />
          </div>
        </div>
        <button className="btn primary" disabled={blocked !== null || create.isPending} onClick={save}>
          {create.isPending ? "Saving…" : "Save draft"}
        </button>
        {blocked && !create.isPending && <span className="wc-hint wc-inline">{blocked}</span>}
        {saveErr && <div className="wc-hint bad">{saveErr}</div>}
      </div>
    </div>
  );
}
