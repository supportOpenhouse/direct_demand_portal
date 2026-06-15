/* New Leads — 1:1 with the prototype's tplNewLeads(), wired to GET /v1/leads?segment=new.
   Two source categories (Meta + listing portals) land in one table; rows clickable → lead detail. */
import { useNavigate } from "react-router-dom";
import { useLeads } from "../lib/queries";
import { Lead } from "../lib/api";
import { srcClass, srcLabel, planClass, initials } from "../lib/leads";
import { useSearch, matches } from "../components/SearchContext";
import { FilterSelect, uniqueValues } from "../components/Filters";
import { WhatsAppIcon } from "../components/icons";
import { useToast } from "../components/Toast";
import { useState } from "react";

function PlanChip({ plan }: { plan: string | null }) {
  if (!plan) return <span style={{ color: "var(--muted)" }}>—</span>;
  return <span className={`plan-chip ${planClass(plan)}`}>{plan}</span>;
}

export default function NewLeads() {
  const { data, isLoading } = useLeads("new");
  const nav = useNavigate();
  const toast = useToast();
  const { query } = useSearch();
  const [source, setSource] = useState("");
  const [city, setCity] = useState("");

  const all = data?.items ?? [];
  const list = all.filter(
    (l) =>
      (!source || l.source === source) &&
      (!city || l.city === city) &&
      matches(query, l.name, l.phone, l.city, l.society, l.budget_band, srcLabel(l.source))
  );

  const wa = (e: React.MouseEvent, l: Lead) => {
    e.stopPropagation();
    toast(`Opening WhatsApp chat with ${l.name}`, "wa", "↗");
  };

  return (
    <>
      <div className="section-head" style={{ marginBottom: 10 }}>
        <p className="sec-sub" style={{ margin: 0 }}>
          Untouched leads still inside their first-contact window (TAT) — call before it lapses.
          {data?.status === "ok" && (
            <>
              {" "}
              <b style={{ color: "var(--ink-2)" }}>
                {list.length !== all.length ? `${list.length} of ${all.length}` : all.length}
              </b>{" "}
              new
            </>
          )}
        </p>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <FilterSelect label="Source" value={source} options={uniqueValues(all, (l) => l.source).map(srcLabel)}
            onChange={(v) => setSource(uniqueValues(all, (l) => l.source).find((s) => srcLabel(s) === v) || "")} width={140} />
          <FilterSelect label="City" value={city} options={uniqueValues(all, (l) => l.city)} onChange={setCity} width={130} />
        </div>
      </div>

      <div className="card panel-pad" id="needing-action">
        <div className="section-head">
          <div className="panel-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 6v6l4 2" />
            </svg>{" "}
            New Leads: Urgent action required
          </div>
          <button
            className="btn sm"
            style={{ background: "var(--cyan)", color: "#fff", boxShadow: "0 6px 16px -8px var(--cyan)" }}
            onClick={() => nav("/leads/qualified")}
          >
            Qualified Leads →
          </button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Lead</th>
              <th>City</th>
              <th>Society (from source)</th>
              <th>Config</th>
              <th>Budget</th>
              <th>Plan to Buy</th>
              <th>Assigned To</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={8}>
                  <div className="empty" style={{ padding: 24 }}>Loading leads…</div>
                </td>
              </tr>
            ) : list.length === 0 ? (
              <tr>
                <td colSpan={8}>
                  <div className="empty" style={{ padding: 24 }}>
                    {all.length === 0 ? "No new leads right now. 🎉" : "No leads match the search / filters."}
                  </div>
                </td>
              </tr>
            ) : (
              list.map((l) => (
                <tr key={l.id} className="lead-row" onClick={() => nav(`/leads/${l.id}`)}>
                  <td>
                    <div className="who">
                      <div className="av">{initials(l.name)}</div>
                      <div>
                        <div className="nm">
                          {l.name}{" "}
                          <span style={{ fontWeight: 500, color: "var(--muted)", fontSize: 11 }}>
                            ({srcLabel(l.source)})
                          </span>
                          {l.is_test && (
                            <span className="bucket-tag" style={{ marginLeft: 6 }}>TEST</span>
                          )}
                        </div>
                        <div className="ph">{l.phone}</div>
                      </div>
                    </div>
                  </td>
                  <td style={{ fontSize: 12.5 }}>{l.city || "—"}</td>
                  <td style={{ fontSize: 12.5, color: "var(--ink-2)" }}>{l.society || <span style={{ color: "var(--muted)" }}>—</span>}</td>
                  <td>{l.configuration ? <span className="cfg-chip">{l.configuration}</span> : "—"}</td>
                  <td style={{ fontSize: 12.5 }}>{l.budget_band || "—"}</td>
                  <td><PlanChip plan={l.plan_to_buy} /></td>
                  <td style={{ fontSize: 12.5 }}>{l.assigned_to || <span style={{ color: "var(--muted)" }}>—</span>}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className="wa-ico" title={`WhatsApp ${l.name}`} onClick={(e) => wa(e, l)}>
                      <WhatsAppIcon />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
