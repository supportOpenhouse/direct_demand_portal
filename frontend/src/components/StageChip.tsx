import { stageClass, stageLabel } from "../lib/leads";

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
