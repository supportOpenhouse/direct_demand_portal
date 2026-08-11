/* The lead's number under their name in list views.

   Shown unless an admin has switched "Hide lead phone numbers in tables" on in
   Settings & Access — for shared screens, screenshots and demos. Org-wide rather than
   per-browser: it's a PII decision, so one person makes it for everyone.

   This hides the number, it does not withhold it. The value is still in the API
   payload and the call/WhatsApp buttons still work, because they need it. Anyone with
   devtools can read it — the point is what a shoulder or a screenshot catches.

   An older variant gated on miss_count — hidden until an RM had missed the lead
   enough times to need the digits. Kept below rather than deleted; it's the likely
   shape if this ever needs to be conditional again, and `missCount` stays in the
   props for the same reason: every call site already passes it. */
import { useAppSettings } from "../lib/queries";

export default function LeadPhone({ phone }: { phone: string | null; missCount: number }) {
  const { data: settings } = useAppSettings();
  if (!phone) return null;

  // While the settings request is in flight `data` is undefined. Falling back to
  // "show" keeps today's behaviour on a slow or failed load — the alternative is a
  // blank column flashing on every page load for everyone.
  if (settings?.hide_lead_phones) return null;

  // --- older gate: only show the number once the calls keep failing -----------
  // const PHONE_AFTER_MISSES = 5;
  // if (missCount < PHONE_AFTER_MISSES) return null;
  // (also add `missCount` back to the destructure above, and swap the title below
  //  for: `Shown because this lead has ${missCount} missed calls`)
  // ---------------------------------------------------------------------------

  return <div className="ph">{phone}</div>;
}
