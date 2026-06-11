import type { Source } from '../lib/types';

export const SOURCE_LABELS: Record<Source, string> = {
  meta: 'Meta',
  gads: 'Google Ads',
  '99acres': '99acres',
  magicbricks: 'MagicBricks',
  youtube: 'YouTube',
  whatsapp: 'WhatsApp',
  api: 'API',
  webhook: 'Webhook',
  sheets: 'Sheets',
};

/* "99acres" can't be a leading-digit CSS class — mapped to .acres99. */
const SOURCE_CLASS: Record<Source, string> = {
  meta: 'meta',
  gads: 'gads',
  '99acres': 'acres99',
  magicbricks: 'magicbricks',
  youtube: 'youtube',
  whatsapp: 'whatsapp',
  api: 'api',
  webhook: 'webhook',
  sheets: 'sheets',
};

export interface SrcBadgeProps {
  source: Source;
}

/** Square-dot brand-coloured source chip (.src.<key>). */
export function SrcBadge({ source }: SrcBadgeProps) {
  return <span className={`src ${SOURCE_CLASS[source]}`}>{SOURCE_LABELS[source]}</span>;
}
