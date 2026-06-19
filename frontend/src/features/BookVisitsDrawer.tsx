/* Book Visits — DESIGN ONLY (no API wired yet).
   A focused, guided 3-step checkout drawer (Details → Review → Done) for booking
   1–10 Openhouse app visits on behalf of a Channel Partner. Slot/date logic is real
   (lib/slots); the Channel-Partner list and the confirm/result step are mocked so the
   whole flow is reviewable before any server-to-server integration is built. */
import { useMemo, useState } from "react";
import { formatPrice } from "../lib/queries";
import { useToast } from "../components/Toast";
import { SLOTS, next7Days, isSlotDisabled, maskMobile, DayOption } from "../lib/slots";

export interface BookUnit {
  homeId: string | number;
  name: string | null;
  society: string | null;
  locality: string | null;
  city: string | null;
  configuration: string | null;
  priceText: string | null;
  priceLacs: number | null;
  status?: "ready" | "coming_soon";
  isNew?: boolean;
}

// Channel Partner is fixed to "Direct Leads" (broker #708) — no picker, no source toggle.
const FIXED_CP = { name: "Direct Leads", brokerId: 708 };

interface Buyer { name: string; mobile: string; }
type Result = { homeId: string | number; ok: boolean; visitId?: number; reason?: string };

const STEPS = ["Details", "Review", "Done"] as const;

export function BookVisitsDrawer({ units, onClose }: { units: BookUnit[]; onClose: () => void }) {
  const toast = useToast();
  const days = useMemo(() => next7Days(), []);
  const [step, setStep] = useState(0);

  // step 1 state
  const [date, setDate] = useState<DayOption>(days[0]);
  const [slot, setSlot] = useState<string>("");
  const [oneBuyer, setOneBuyer] = useState(true);
  const [shared, setShared] = useState<Buyer>({ name: "", mobile: "" });
  const [perUnit, setPerUnit] = useState<Record<string, Buyer>>({});

  // step 3 state
  const [booking, setBooking] = useState(false);
  const [results, setResults] = useState<Result[]>([]);

  const buyerFor = (u: BookUnit): Buyer => (oneBuyer ? shared : perUnit[String(u.homeId)] || { name: "", mobile: "" });
  const setBuyerFor = (u: BookUnit, patch: Partial<Buyer>) =>
    setPerUnit((p) => ({ ...p, [String(u.homeId)]: { ...(p[String(u.homeId)] || { name: "", mobile: "" }), ...patch } }));

  const buyerValid = (b: Buyer) => b.name.trim().length > 0 && b.mobile.replace(/\D/g, "").length >= 5;
  const buyersOk = oneBuyer ? buyerValid(shared) : units.every((u) => buyerValid(buyerFor(u)));
  const canReview = !!slot && !!date && buyersOk;

  const visits = units.map((u) => ({ unit: u, buyer: buyerFor(u) }));

  const confirm = () => {
    // DESIGN ONLY — simulate the sequential server-to-server booking.
    setBooking(true);
    window.setTimeout(() => {
      const mock: Result[] = units.map((u, i) => {
        // demo a realistic partial-success: the 2nd unit (if any) comes back "locked"
        if (units.length >= 2 && i === 1) {
          return { homeId: u.homeId, ok: false, reason: "Buyer registered with another CP for 12 more days" };
        }
        return { homeId: u.homeId, ok: true, visitId: 480000 + i + Math.floor((Date.parse(date.date) % 9000)) };
      });
      setResults(mock);
      setBooking(false);
      setStep(2);
    }, 1400);
  };

  const booked = results.filter((r) => r.ok).length;
  const failed = results.length - booked;

  return (
    <div className="bv-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="bv-drawer" role="dialog" aria-label="Book visits">
        {/* header + beta banner */}
        <div className="bv-head">
          <div>
            <div className="bv-title">📲 Book Visits</div>
            <div className="bv-beta">Beta · authorized users only · <b>design preview, no bookings are sent</b></div>
          </div>
          <button className="bv-x" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {/* progress */}
        <div className="bv-steps">
          {STEPS.map((s, i) => (
            <div key={s} className={"bv-step" + (i === step ? " active" : "") + (i < step ? " done" : "")}>
              <span className="bv-step-dot">{i < step ? "✓" : i + 1}</span>
              <span className="bv-step-label">{s}</span>
              {i < STEPS.length - 1 && <span className="bv-step-line" />}
            </div>
          ))}
        </div>

        <div className="bv-body">
          {/* ---------------------------------------------------------------- STEP 1 */}
          {step === 0 && (
            <>
              <div className="bv-sec-label">Booking for {units.length} unit{units.length !== 1 ? "s" : ""}</div>

              {/* Channel Partner — fixed to Direct Leads (broker #708) */}
              <div className="bv-field">
                <label>Channel Partner</label>
                <div className="bv-cp-fixed">
                  <span><b>Direct Leads</b> <span className="bv-cp-code">Broker #{FIXED_CP.brokerId}</span></span>
                  <span className="bv-fixed-tag">Fixed</span>
                </div>
              </div>

              {/* date chips */}
              <div className="bv-field">
                <label>Date <span className="bv-req">*</span></label>
                <div className="bv-chips">
                  {days.map((d) => (
                    <button key={d.date} className={"bv-chip" + (date.date === d.date ? " sel" : "")} onClick={() => setDate(d)}>
                      <span className="bv-chip-dow">{d.isToday ? "Today" : d.dow}</span>
                      <span className="bv-chip-num">{d.dayNum}</span>
                      <span className="bv-chip-mon">{d.month}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* slot grid */}
              <div className="bv-field">
                <label>Time slot <span className="bv-req">*</span></label>
                <div className="bv-slot-grid">
                  {SLOTS.map((s) => {
                    const disabled = isSlotDisabled(date.date, s.startHour);
                    return (
                      <button
                        key={s.label}
                        className={"bv-slot" + (slot === s.label ? " sel" : "") + (disabled ? " disabled" : "")}
                        disabled={disabled}
                        onClick={() => setSlot(s.label)}
                        title={disabled ? "This slot has passed for today" : ""}
                      >
                        {s.label}
                      </button>
                    );
                  })}
                </div>
                {date.isToday && <div className="bv-hint">Today's slots close 1 hour after they start.</div>}
              </div>

              {/* buyer(s) */}
              {units.length > 1 && (
                <label className="bv-toggle">
                  <input type="checkbox" checked={oneBuyer} onChange={(e) => setOneBuyer(e.target.checked)} />
                  <span>One buyer is touring all {units.length} units</span>
                </label>
              )}

              {oneBuyer ? (
                <div className="bv-field">
                  <label>Buyer <span className="bv-req">*</span></label>
                  <div className="bv-two">
                    <input className="bv-input" placeholder="Buyer name" value={shared.name} onChange={(e) => setShared({ ...shared, name: e.target.value })} />
                    <input className="bv-input" placeholder="Mobile (last 5–10 digits)" inputMode="numeric" value={shared.mobile} onChange={(e) => setShared({ ...shared, mobile: e.target.value.replace(/\D/g, "").slice(0, 10) })} />
                  </div>
                  {!buyerValid(shared) && (shared.name || shared.mobile) && <div className="bv-warn-text">Name + at least 5 mobile digits required.</div>}
                </div>
              ) : (
                <div className="bv-field">
                  <label>Buyer per unit <span className="bv-req">*</span></label>
                  {units.map((u) => {
                    const b = buyerFor(u);
                    return (
                      <div key={String(u.homeId)} className="bv-perunit">
                        <div className="bv-perunit-name">{u.name || u.society || `Home #${u.homeId}`}</div>
                        <div className="bv-two">
                          <input className="bv-input" placeholder="Buyer name" value={b.name} onChange={(e) => setBuyerFor(u, { name: e.target.value })} />
                          <input className="bv-input" placeholder="Mobile (last 5–10)" inputMode="numeric" value={b.mobile} onChange={(e) => setBuyerFor(u, { mobile: e.target.value.replace(/\D/g, "").slice(0, 10) })} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}

          {/* ---------------------------------------------------------------- STEP 2 */}
          {step === 1 && (
            <>
              <div className="bv-danger">
                <b>⚠ This is final.</b> On confirm, {units.length} visit{units.length !== 1 ? "s are" : " is"} created on the Openhouse app and
                <b> cannot be edited or undone</b>. The buyer &amp; CP are notified immediately.
              </div>
              <div className="bv-sec-label">Direct Leads · Broker #{FIXED_CP.brokerId} · {date.isToday ? "Today" : date.dow} {date.dayNum} {date.month} · {slot}</div>
              {visits.map(({ unit, buyer }) => (
                <div key={String(unit.homeId)} className="bv-visit-card">
                  <div className="bv-vc-top">
                    <span className="bv-vc-name">{unit.name || unit.society || `Home #${unit.homeId}`}</span>
                    <span className="bv-vc-home">Home #{unit.homeId}</span>
                  </div>
                  <div className="bv-vc-grid">
                    <span>Location</span><b>{[unit.locality, unit.city].filter(Boolean).join(", ") || "—"}</b>
                    <span>Config · price</span><b>{unit.configuration || "—"} · {formatPrice(unit.priceLacs, unit.priceText)}</b>
                    <span>Buyer</span><b>{buyer.name || "—"} · {maskMobile(buyer.mobile)}</b>
                    <span>CP</span><b>Direct Leads · Broker #{FIXED_CP.brokerId}</b>
                    <span>When</span><b>{date.isToday ? "Today" : date.dow} {date.dayNum} {date.month} · {slot}</b>
                    <span>Source</span><b>Direct</b>
                  </div>
                </div>
              ))}
            </>
          )}

          {/* ---------------------------------------------------------------- STEP 3 */}
          {step === 2 && (
            <>
              <div className={"bv-result-head" + (failed ? " mixed" : " ok")}>
                Booked <b>{booked}</b> of {results.length}{failed ? <> · <b>{failed}</b> failed</> : ""}
                <span className="bv-demo">demo · no real bookings sent</span>
              </div>
              {results.map((r) => {
                const u = units.find((x) => String(x.homeId) === String(r.homeId))!;
                return (
                  <div key={String(r.homeId)} className={"bv-result " + (r.ok ? "ok" : "fail")}>
                    <span className="bv-result-ico">{r.ok ? "✓" : "✗"}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="bv-result-name">{u?.name || u?.society || `Home #${r.homeId}`}</div>
                      <div className="bv-result-sub">{r.ok ? `Visit #${r.visitId} scheduled · ${slot}` : r.reason}</div>
                    </div>
                    {!r.ok && <button className="bv-link" onClick={() => { setResults([]); setStep(0); }}>Fix &amp; rebook</button>}
                  </div>
                );
              })}
            </>
          )}
        </div>

        {/* footer */}
        <div className="bv-foot">
          {step === 0 && (
            <>
              <button className="btn ghost" onClick={onClose}>Cancel</button>
              <button className="bv-cta" disabled={!canReview} onClick={() => setStep(1)}>Review {units.length} visit{units.length !== 1 ? "s" : ""} →</button>
            </>
          )}
          {step === 1 && (
            <>
              <button className="btn ghost" disabled={booking} onClick={() => setStep(0)}>← Back</button>
              <button className="bv-cta danger" disabled={booking} onClick={confirm}>{booking ? "Booking…" : `Confirm & book ${units.length}`}</button>
            </>
          )}
          {step === 2 && (
            <button className="bv-cta" onClick={() => { toast("Closed booking preview", "gold", "📲"); onClose(); }}>Done</button>
          )}
        </div>
      </aside>
    </div>
  );
}
