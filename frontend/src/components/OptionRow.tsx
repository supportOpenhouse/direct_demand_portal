import { useState, type ReactNode } from 'react';
import { budgetLabel, formatLacs } from '../lib/format';
import type { MatchedOn, Unit } from '../lib/types';
import { IconChevron, WhatsAppLogo } from './icons';

const MATCHED_ON_LABELS: Record<MatchedOn, string> = {
  city: 'City',
  society: 'Society',
  budget: 'Budget',
  config: 'Config',
};

const SUPPLY_STAGE_LABELS: Record<string, string> = {
  msi: 'MSI',
  token_paid: 'Token paid',
  negotiating: 'Negotiating',
};

export interface OptionRowProps {
  unit: Unit;
  /** Match percentage (0–100) — renders the green .match-mini chip. */
  matchPct?: number;
  matchedOn?: MatchedOn[];
  /** Extra content appended inside the expanded detail (custom actions). */
  children?: ReactNode;
}

function unitShareText(unit: Unit): string {
  const bits = [unit.name];
  if (unit.society) bits.push(unit.society);
  if (unit.city) bits.push(unit.city);
  const tail: string[] = [];
  if (unit.configuration) tail.push(unit.configuration);
  if (unit.price_lacs !== null) tail.push(formatLacs(unit.price_lacs));
  return `${bits.join(', ')}${tail.length ? ` — ${tail.join(' · ')}` : ''}`;
}

/**
 * Expandable matched-unit row (.opt): thumbnail + name + match % + meta line,
 * chevron rotates on expand, WhatsApp share icon; detail reveals a key/value
 * grid (.opt-dl) and — for inventory units — a "↗ Share brochure" button.
 */
export function OptionRow({ unit, matchPct, matchedOn, children }: OptionRowProps) {
  const [open, setOpen] = useState(false);

  const meta: string[] = [];
  if (unit.configuration) meta.push(unit.configuration);
  if (unit.area_sqft !== null) meta.push(`${unit.area_sqft} sq.ft`);
  if (unit.price_lacs !== null) meta.push(`${formatLacs(unit.price_lacs)} ask`);

  const detail: [string, string][] = [];
  if (unit.society) detail.push(['Society', unit.society]);
  if (unit.city) detail.push(['City', unit.city]);
  if (unit.configuration) detail.push(['Configuration', unit.configuration]);
  if (unit.price_lacs !== null) detail.push(['Price', formatLacs(unit.price_lacs)]);
  if (unit.budget_min_lacs !== null || unit.budget_max_lacs !== null) {
    detail.push(['Budget band', budgetLabel(unit.budget_min_lacs, unit.budget_max_lacs)]);
  }
  if (unit.area_sqft !== null) detail.push(['Area', `${unit.area_sqft} sq.ft`]);
  if (unit.status) detail.push(['Status', unit.status]);
  if (unit.supply_stage) {
    detail.push(['Supply stage', SUPPLY_STAGE_LABELS[unit.supply_stage] ?? unit.supply_stage]);
  }
  if (unit.eta) detail.push(['ETA', unit.eta]);
  if (unit.ext_source === 'supply_tracker' && unit.interest_count > 0) {
    detail.push(['Buyer interest', `${unit.interest_count} RM${unit.interest_count === 1 ? '' : 's'}`]);
  }

  const shareHref = `https://wa.me/?text=${encodeURIComponent(unitShareText(unit))}`;

  return (
    <div className={`opt${open ? ' open' : ''}`}>
      <div className="opt-row" onClick={() => setOpen((o) => !o)}>
        {unit.image_url ? (
          <img className="thumb" src={unit.image_url} alt="" />
        ) : (
          <span className="thumb thumb-ph" />
        )}
        <div className="opt-info">
          <div className="o-name">
            <span>{unit.name}</span>
            {matchPct !== undefined && <span className="match-mini">{Math.round(matchPct)}%</span>}
          </div>
          <div className="o-meta">{meta.join(' · ') || '—'}</div>
        </div>
        <IconChevron size={15} className="chev" />
        <a
          className="wa-ico"
          href={shareHref}
          target="_blank"
          rel="noreferrer"
          title="Share on WhatsApp"
          onClick={(e) => e.stopPropagation()}
        >
          <WhatsAppLogo size={17} />
        </a>
      </div>
      <div className="opt-detail">
        <div className="opt-dl">
          {detail.map(([k, v]) => (
            <div key={k}>
              <div className="k">{k}</div>
              <div className="v">{v}</div>
            </div>
          ))}
          {matchedOn && matchedOn.length > 0 && (
            <div>
              <div className="k">Matched on</div>
              <div className="v">{matchedOn.map((m) => MATCHED_ON_LABELS[m]).join(', ')}</div>
            </div>
          )}
        </div>
        {unit.ext_source === 'acquired_property' && (
          <a
            className="btn green sm"
            href={shareHref}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
          >
            ↗ Share brochure
          </a>
        )}
        {children}
      </div>
    </div>
  );
}
