import type { Stage } from '../lib/types';

export const STAGE_LABELS: Record<Stage, string> = {
  new: 'New',
  contacted: 'Contacted',
  visit_scheduled: 'Visit Scheduled',
  visit_feedback: 'Visit Feedback',
  negotiation: 'Negotiation',
  won: 'Won',
  lost: 'Lost',
  future_prospect: 'Future Prospect',
  timepass: 'Timepass',
};

export interface StageChipProps {
  stage: Stage;
}

/** Pill chip with dot — semantic hue per stage (.stage.<key>). */
export function StageChip({ stage }: StageChipProps) {
  return <span className={`stage ${stage}`}>{STAGE_LABELS[stage]}</span>;
}
