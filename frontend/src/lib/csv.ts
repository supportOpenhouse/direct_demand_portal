/* Client-side CSV export for the lead worklists. Exports exactly what's on screen
   (the filtered + sorted rows the page passes in), so filters/search/sort carry
   through. No backend needed. */
import { Lead } from "./api";
import { srcLabel, stageLabel } from "./leads";

const fmt = (iso: string | null): string =>
  iso ? new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "";

// escape one cell per RFC 4180 (quote if it contains a comma, quote, or newline)
const cell = (v: unknown): string => {
  const s = v == null ? "" : String(v);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

const COLUMNS: { header: string; get: (l: Lead) => unknown }[] = [
  { header: "Name", get: (l) => l.name },
  { header: "Phone", get: (l) => l.phone },
  { header: "Email", get: (l) => l.email },
  { header: "Source", get: (l) => srcLabel(l.source) },
  { header: "City", get: (l) => l.city },
  { header: "Society", get: (l) => l.society },
  { header: "Configuration", get: (l) => l.configuration },
  { header: "Budget", get: (l) => l.budget_band },
  { header: "Plan to buy", get: (l) => l.plan_to_buy },
  { header: "Stage", get: (l) => stageLabel(l.stage) },
  { header: "Assigned to", get: (l) => l.assigned_to },
  { header: "Received", get: (l) => fmt(l.received_at) },
  { header: "Follow-up due", get: (l) => fmt(l.follow_up_at) },
  { header: "Misses", get: (l) => l.miss_count },
  { header: "Ever connected", get: (l) => (l.ever_connected ? "Yes" : "No") },
  { header: "Reject reason", get: (l) => l.reject_reason },
  { header: "Reject notes", get: (l) => l.reject_notes },
  { header: "Notes", get: (l) => l.note_count },
  { header: "Latest note", get: (l) => l.latest_note },
];

function leadsToCsv(leads: Lead[]): string {
  const head = COLUMNS.map((c) => cell(c.header)).join(",");
  const rows = leads.map((l) => COLUMNS.map((c) => cell(c.get(l))).join(","));
  return [head, ...rows].join("\r\n");
}

export function downloadLeadsCsv(filename: string, leads: Lead[]): void {
  // leading BOM so Excel reads UTF-8 (₹, non-ASCII names) correctly
  const blob = new Blob(["﻿" + leadsToCsv(leads)], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
