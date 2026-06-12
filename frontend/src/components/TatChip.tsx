import { tatLabel } from '../lib/format';
import type { TatInfo } from '../lib/types';

export interface TatChipProps {
  tat: TatInfo;
}

/**
 * Spline-Mono TAT chip — .ok (emerald) / .warn (amber) / .breach (coral,
 * pulsing). Renders a muted "—" chip when state is null (confirmed / n.a.).
 */
export function TatChip({ tat }: TatChipProps) {
  if (!tat.state) return <span className="tat">—</span>;
  return <span className={`tat ${tat.state}`}>{tatLabel(tat.minutes_left)}</span>;
}
