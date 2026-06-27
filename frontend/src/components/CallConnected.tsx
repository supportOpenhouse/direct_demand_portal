/* "Call connected?" gate for the New Leads / Follow-up worklists.
   The lead row is NOT clickable — Yes is the only way in:
     Yes → logs a connected call (resets the miss streak) and opens the lead.
     No  → logs a miss → +3h follow-up; 10 misses on a never-reached lead → RNR. */
import { useNavigate } from "react-router-dom";
import { useCallResult } from "../lib/queries";
import { useToast } from "./Toast";

export function CallConnected({ leadId }: { leadId: string }) {
  const nav = useNavigate();
  const toast = useToast();
  const m = useCallResult();

  const yes = (e: React.MouseEvent) => {
    e.stopPropagation();
    m.mutate({ id: leadId, connected: true }, { onSuccess: () => nav(`/leads/${leadId}`) });
  };
  const no = (e: React.MouseEvent) => {
    e.stopPropagation();
    m.mutate(
      { id: leadId, connected: false },
      {
        onSuccess: (d) =>
          toast(
            d.moved_to_rnr ? "10 missed calls — moved to RNR" : "Not reached · follow-up in 3h",
            "gold",
            d.moved_to_rnr ? "✕" : "↻",
          ),
      },
    );
  };

  return (
    <div className="cc" onClick={(e) => e.stopPropagation()}>
      <span className="cc-q">Connected?</span>
      <button className="cc-btn yes" disabled={m.isPending} onClick={yes}>Yes</button>
      <button className="cc-btn no" disabled={m.isPending} onClick={no}>No</button>
    </div>
  );
}
