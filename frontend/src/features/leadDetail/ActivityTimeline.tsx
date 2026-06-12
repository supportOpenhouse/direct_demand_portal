/**
 * Activity card — vertical timeline of lead events (newest first from the
 * API): accent dot + connector, event (600), muted remark, actor + relative
 * time right-aligned in mono.
 */
import { EmptyState } from '../../components/EmptyState';
import { IconCalendar } from '../../components/icons';
import { timeAgo } from '../../lib/format';
import type { Activity } from '../../lib/types';

export function ActivityTimeline({ activity }: { activity: Activity[] }) {
  return (
    <div className="card panel-pad">
      <div className="panel-title">
        <IconCalendar size={16} />
        <span>Activity</span>
      </div>
      {activity.length === 0 ? (
        <EmptyState msg="No activity yet — calls, confirms and stage changes land here." />
      ) : (
        <div>
          {activity.map((a, i) => {
            const last = i === activity.length - 1;
            return (
              <div
                key={a.id}
                style={{ display: 'flex', gap: 12, paddingBottom: last ? 0 : 14 }}
              >
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    flex: '0 0 auto',
                  }}
                >
                  <span
                    style={{
                      width: 9,
                      height: 9,
                      borderRadius: '50%',
                      background: i === 0 ? 'var(--accent)' : 'var(--line)',
                      border: i === 0 ? 'none' : '2px solid var(--muted)',
                      boxSizing: 'border-box',
                      marginTop: 4,
                      flex: '0 0 auto',
                    }}
                  />
                  {!last && (
                    <span style={{ width: 2, flex: 1, background: 'var(--line-2)', marginTop: 4 }} />
                  )}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, lineHeight: 1.35 }}>{a.event}</div>
                  {a.remark && (
                    <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 2 }}>
                      {a.remark}
                    </div>
                  )}
                </div>
                <div
                  className="mono"
                  style={{
                    textAlign: 'right',
                    fontSize: 11,
                    color: 'var(--muted)',
                    flex: '0 0 auto',
                    lineHeight: 1.5,
                  }}
                >
                  <div>{a.actor_name ?? 'System'}</div>
                  <div>{timeAgo(a.created_at)}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
