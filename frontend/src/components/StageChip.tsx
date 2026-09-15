import type { Lead } from "../lib/api";
import { leadSources, srcClass, srcLabel, stageClass, stageLabel } from "../lib/leads";

/* One chip per source the buyer arrived from — Meta then 99acres shows both. */
export function SourceChips({ lead }: { lead: Pick<Lead, "source" | "sources"> }) {
  return (
    <span className="src-list">
      {leadSources(lead).map((s) => <span key={s} className={`src ${srcClass(s)}`}>{srcLabel(s)}</span>)}
    </span>
  );
}

/* "(3)" in red beside the name once a buyer has arrived more than once — total
   arrivals, so a lead that came in twice reads (2). Nothing for a single arrival. */
export function ArrivalCount({ lead }: { lead: Pick<Lead, "count_leads_repeat"> }) {
  const n = (lead.count_leads_repeat ?? 0) + 1;
  return n > 1 ? <span className="arrival-count" title={`Arrived ${n} times`}>({n})</span> : null;
}

/* The starburst NEW badge (Direct Inventory's asset).

   60x60 rendered small -- 3x DPR headroom, ~5KB, so shipping the image is cheaper
   than drawing it. `alt` carries the word for anyone not seeing the image, and for
   html2canvas, which rasterises the Live Inventory poster. */
export function NewBadge({ size = 22, className = "", style }: {
  size?: number; className?: string; style?: React.CSSProperties;
}) {
  return (
    <img className={"new-badge-img " + className} src="/new.png" alt="NEW"
         style={{ height: size, ...style }} />
  );
}

/* The stage as it renders everywhere: a tinted chip.

   A component rather than a repeated span — the chip was written out at six call
   sites, so any change to it had six places to miss.

   NOTE: the starburst NewBadge is NOT a stage. It marks a lead that arrived or was
   assigned TODAY, which is true of leads in several stages and false of most leads
   in stage `new`. See `isNewToday` in lib/leads.ts. */
export function StageChip({ stage, className = "", style }: {
  stage: string;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <span className={`stage ${stageClass(stage)} ${className}`} style={style}>{stageLabel(stage)}</span>
  );
}
