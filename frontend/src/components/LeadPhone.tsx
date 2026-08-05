/* The lead's number under their name in list views.

   Currently always shown. It was briefly gated on miss_count — hidden until an RM
   had missed the lead enough times to need the digits — and that rule is kept below
   rather than deleted, since it's the likely shape if numbers ever need hiding again
   (shared screens, screenshots, a stricter PII line).

   `missCount` stays in the props for the same reason: every call site already passes
   it, so re-enabling is uncommenting two lines, not re-threading a prop through three
   tables. */
export default function LeadPhone({ phone }: { phone: string | null; missCount: number }) {
  if (!phone) return null;

  // --- gate: only show the number once the calls keep failing -----------------
  // const PHONE_AFTER_MISSES = 5;
  // if (missCount < PHONE_AFTER_MISSES) return null;
  // (also add `missCount` back to the destructure above, and swap the title below
  //  for: `Shown because this lead has ${missCount} missed calls`)
  // ---------------------------------------------------------------------------

  return <div className="ph">{phone}</div>;
}
