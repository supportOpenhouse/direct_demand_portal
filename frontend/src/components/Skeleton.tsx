/* Shape-holding placeholders. A shimmer beats a spinner because it keeps the
   layout still — the real rows land into the space already reserved for them. */

export function Skeleton({ w = "100%", h = 11, r }: { w?: number | string; h?: number; r?: number }) {
  return <span className="skel" style={{ width: w, height: h, borderRadius: r }} />;
}

/** Placeholder rows for a table body. `cols` widths are percentages of the row. */
export function SkeletonRows({ rows = 8, cols = [22, 16, 14, 18, 12] }: { rows?: number; cols?: number[] }) {
  return (
    <>
      {Array.from({ length: rows }, (_, i) => (
        <div className="skel-row" key={i}>
          <Skeleton w={32} h={32} r={9} />
          {cols.map((c, j) => <Skeleton key={j} w={`${c}%`} />)}
        </div>
      ))}
    </>
  );
}

/** Placeholder for a row of stat cards. */
export function SkeletonCards({ n = 4 }: { n?: number }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${n}, 1fr)`, gap: 14 }}>
      {Array.from({ length: n }, (_, i) => (
        <div className="card panel-pad" key={i}>
          <Skeleton w="55%" h={10} />
          <div style={{ height: 10 }} />
          <Skeleton w="40%" h={26} r={8} />
        </div>
      ))}
    </div>
  );
}

/** Placeholder rows for a real <tbody>. Emits <tr>/<td> so the table keeps its
    column widths — a colSpan'd "Loading…" cell collapses them and the header
    jumps the moment data lands. */
export function SkeletonTable({ rows = 8, cols = 6 }: { rows?: number; cols?: number }) {
  const w = ["70%", "55%", "80%", "45%", "62%", "50%", "68%", "40%"];
  return (
    <>
      {Array.from({ length: rows }, (_, i) => (
        <tr key={i}>
          {Array.from({ length: cols }, (_, j) => (
            <td key={j}><Skeleton w={w[(i + j) % w.length]} /></td>
          ))}
        </tr>
      ))}
    </>
  );
}
