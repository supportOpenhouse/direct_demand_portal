/**
 * Matched-units panel (right column) — top-5 from
 * GET /leads/:id/matches/{inventory|supply}, rendered as expandable
 * OptionRows with match % + matched-on reasons.
 */
import { EmptyState } from '../../components/EmptyState';
import { IconInventory, IconSupply } from '../../components/icons';
import { OptionRow } from '../../components/OptionRow';
import { ApiError } from '../../lib/api';
import { useMatches } from '../../lib/queries';
import type { UnitKind } from '../../lib/types';

const META: Record<UnitKind, { title: string; tag: string }> = {
  inventory: { title: 'Best matches from inventory', tag: 'Acquired property' },
  supply: { title: 'From supply pipeline', tag: 'Supply closure tracker' },
};

export function MatchesPanel({ leadId, kind }: { leadId: string; kind: UnitKind }) {
  const { data, isLoading, error } = useMatches(leadId, kind);
  const Icon = kind === 'inventory' ? IconInventory : IconSupply;

  return (
    <div className="card panel-pad">
      <div className="panel-title">
        <Icon size={16} />
        <span>{META[kind].title}</span>
        <span
          className="mono"
          style={{
            marginLeft: 'auto',
            fontSize: 10,
            fontWeight: 500,
            color: 'var(--muted)',
            textTransform: 'uppercase',
            letterSpacing: '.08em',
            whiteSpace: 'nowrap',
          }}
        >
          {META[kind].tag}
        </span>
      </div>

      {isLoading && <div className="empty">Loading…</div>}
      {error && (
        <div className="note">
          {error instanceof ApiError ? error.detail : 'Could not load matches.'}
        </div>
      )}
      {data &&
        (data.length === 0 ? (
          <EmptyState msg="No matches yet — confirm requirements to improve matching." />
        ) : (
          data.map((m) => (
            <OptionRow
              key={m.unit.id}
              unit={m.unit}
              matchPct={m.match_pct}
              matchedOn={m.matched_on}
            />
          ))
        ))}
    </div>
  );
}
