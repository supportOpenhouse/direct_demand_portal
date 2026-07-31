/* Click-to-call, in place of the initials avatar in every lead table.

   Pressing it does NOT dial from the laptop — Bonvoice rings the user's own mobile
   first, and only bridges to the lead once they answer. The toast says so, because
   otherwise nothing appears to happen for a few seconds. */
import { usePlaceCall } from "../lib/queries";
import { useToast } from "./Toast";

function PhoneIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6
               A19.79 19.79 0 0 1 2.08 4.18 2 2 0 0 1 4.07 2h3a2 2 0 0 1 2 1.72
               12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27
               a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
    </svg>
  );
}

export function CallButton({ leadId, disabled }: { leadId: string; disabled?: boolean }) {
  const call = usePlaceCall();
  const toast = useToast();

  return (
    <button
      className="call-btn"
      title="Call this lead — your phone rings first"
      aria-label="Call this lead"
      disabled={disabled || call.isPending}
      onClick={(e) => {
        e.stopPropagation();  // rows navigate on click
        call.mutate(leadId, {
          onSuccess: (d) =>
            toast(`Ringing your phone (${d.rm_phone_masked}) — pick up to connect`, "blue", "📞"),
          onError: (err: any) => toast(err.message, "gold", "⚠"),
        });
      }}
    >
      {call.isPending ? <span className="call-spin" /> : <PhoneIcon />}
    </button>
  );
}
