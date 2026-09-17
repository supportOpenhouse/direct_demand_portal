/* ALL + one box per stage, for a page that holds more than one stage (Call Not Received,
   Visited Leads). The same `.count-pill` boxes Home → Table uses, so a page split by stage
   reads exactly like the book split by page.

   Counts are FACETED, as on Home: the page counts every lead passing all its OTHER filters
   and hands them over, so picking a stage doesn't zero the box beside it. Counting with the
   stage selection applied would leave every other box reading 0 — the ramp stops being
   something you can read. Clicking the active box again goes back to ALL. */
import { stageHue, stageLabel } from "../lib/leads";
import { Skeleton } from "./Skeleton";

export function StageBoxes({
  stages, counts, total, value, onChange, loading = false,
}: {
  stages: string[];
  /** leads per stage, with every filter EXCEPT the stage selection applied */
  counts: Record<string, number>;
  total: number;
  /** "" = ALL */
  value: string;
  onChange: (stage: string) => void;
  loading?: boolean;
}) {
  const num = (n: number, w: number) =>
    loading ? <Skeleton w={w} h={26} r={6} /> : n.toLocaleString("en-IN");
  return (
    <div className="stage-counts">
      <div className="stage-pills">
        <button className={"count-pill" + (value ? "" : " on")} onClick={() => onChange("")}>
          <span className="num">{num(total, 64)}</span>
          <span className="lbl">ALL</span>
        </button>
        {stages.map((st) => (
          <button key={st}
            className={"count-pill" + (value === st ? " on" : "")}
            style={{ ["--pill-hue" as string]: stageHue(st) }}
            onClick={() => onChange(value === st ? "" : st)}
            title={`Show only ${stageLabel(st)}`}
          >
            <span className="num">{num(counts[st] ?? 0, 44)}</span>
            <span className="lbl">{stageLabel(st).toUpperCase()}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
