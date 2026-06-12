import type { PlanToBuy } from '../lib/types';

export const PLAN_META: Record<PlanToBuy, { label: string; cls: 'hot' | 'warm' | 'cool' | 'cold' }> = {
  within_30_days: { label: 'Within 30 days', cls: 'hot' },
  '1_3_months': { label: '1–3 months', cls: 'warm' },
  '3_6_months': { label: '3–6 months', cls: 'cool' },
  just_exploring: { label: 'Just exploring', cls: 'cold' },
};

export interface PlanChipProps {
  plan: PlanToBuy | null | undefined;
}

/** Plan-to-Buy chip: hot=emerald, warm=amber, cool=blue, cold=slate. */
export function PlanChip({ plan }: PlanChipProps) {
  if (!plan) return <span className="plan-chip cold">—</span>;
  const meta = PLAN_META[plan];
  return <span className={`plan-chip ${meta.cls}`}>{meta.label}</span>;
}
