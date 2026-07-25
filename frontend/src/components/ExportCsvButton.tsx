/* "Export CSV" for a lead worklist — downloads the rows it's given (already
   filtered/sorted by the page) as `<name>-<date>.csv`. Admin-only: the gate lives
   here so every tab that uses it is restricted the same way. */
import { Lead } from "../lib/api";
import { downloadLeadsCsv } from "../lib/csv";
import { useAuth } from "./AuthContext";

export function ExportCsvButton({ leads, name }: { leads: Lead[]; name: string }) {
  const { enabled, user } = useAuth();
  const isAdmin = !enabled || user?.role === "admin";
  if (!isAdmin) return null;

  const today = new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD, locale-stable
  return (
    <button
      className="btn ghost sm"
      disabled={leads.length === 0}
      onClick={() => downloadLeadsCsv(`${name}-${today}.csv`, leads)}
      title={leads.length ? `Export ${leads.length} row${leads.length === 1 ? "" : "s"} to CSV` : "Nothing to export"}
    >
      ⬇ Export CSV
    </button>
  );
}
