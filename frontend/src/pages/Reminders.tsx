import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { EmptyState } from '../components/EmptyState';
import { useToast } from '../components/Toast';
import { Topbar } from '../components/Topbar';
import { useAddLeadModal } from '../features/modals/AddLeadModal';
import { ApiError } from '../lib/api';
import { formatDateTime } from '../lib/format';
import { useReminders, useUpdateReminder } from '../lib/queries';
import type { Reminder, ReminderType } from '../lib/types';

const TYPE_META: Record<ReminderType, { label: string; color: string; soft: string }> = {
  follow_up: { label: 'Follow-up', color: 'var(--blue)', soft: 'var(--blue-soft)' },
  visit_schedule: { label: 'Visit schedule', color: 'var(--amber)', soft: 'var(--amber-soft)' },
  visit_feedback: { label: 'Visit feedback', color: 'var(--violet)', soft: 'var(--violet-soft)' },
  negotiation: { label: 'Negotiation', color: 'var(--indigo)', soft: 'var(--indigo-soft)' },
};

const FILTERS: { label: string; type: ReminderType | undefined }[] = [
  { label: 'All', type: undefined },
  { label: 'Follow-up', type: 'follow_up' },
  { label: 'Visit schedule', type: 'visit_schedule' },
  { label: 'Visit feedback', type: 'visit_feedback' },
  { label: 'Negotiation', type: 'negotiation' },
];

function isOverdue(r: Reminder, now: number): boolean {
  return !r.done && new Date(r.due_at).getTime() < now;
}

function ReminderRow({
  reminder,
  divider,
  now,
  onDone,
  pending,
}: {
  reminder: Reminder;
  divider: boolean;
  now: number;
  onDone: (r: Reminder) => void;
  pending: boolean;
}) {
  const meta = TYPE_META[reminder.type];
  const overdue = isOverdue(reminder, now);
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '12px 16px',
        borderTop: divider ? '1px solid var(--line-2)' : undefined,
        opacity: reminder.done ? 0.55 : 1,
      }}
    >
      <span
        className="chip"
        style={{ background: meta.soft, color: meta.color, borderColor: 'transparent' }}
      >
        {meta.label}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Link
            to={`/leads/${reminder.lead_id}`}
            style={{ fontWeight: 600, color: 'var(--ink)', textDecoration: 'none' }}
          >
            {reminder.lead_name}
          </Link>
          {reminder.auto_generated && (
            <span
              style={{
                fontSize: 10.5,
                fontWeight: 600,
                color: 'var(--muted)',
                border: '1px dashed var(--line)',
                background: 'var(--panel-2)',
                borderRadius: 6,
                padding: '1px 6px',
                whiteSpace: 'nowrap',
              }}
            >
              auto-generated
            </span>
          )}
        </div>
        {reminder.note && (
          <div
            style={{
              fontSize: 12.5,
              color: 'var(--ink-2)',
              marginTop: 2,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {reminder.note}
          </div>
        )}
      </div>
      <span
        className="mono"
        style={{
          fontSize: 12,
          whiteSpace: 'nowrap',
          color: overdue ? 'var(--coral)' : 'var(--muted)',
          fontWeight: overdue ? 700 : 500,
        }}
      >
        {formatDateTime(reminder.due_at)}
        {overdue && ' · overdue'}
      </span>
      {reminder.done ? (
        <span className="chip" style={{ color: 'var(--muted)' }}>
          ✓ Done
        </span>
      ) : (
        <button
          type="button"
          className="btn ghost sm"
          disabled={pending}
          onClick={() => onDone(reminder)}
        >
          ✓ Done
        </button>
      )}
    </div>
  );
}

export default function Reminders() {
  const [filter, setFilter] = useState<ReminderType | undefined>(undefined);
  const { data: reminders, isLoading, error } = useReminders(filter);
  const updateReminder = useUpdateReminder();
  const { push } = useToast();
  const { openAddLead, addLeadModal } = useAddLeadModal();
  const now = Date.now();

  const sorted = useMemo(() => {
    if (!reminders) return [];
    return [...reminders].sort((a, b) => {
      // done items sink to the bottom
      if (a.done !== b.done) return a.done ? 1 : -1;
      // overdue first, then due_at ascending
      const aOver = isOverdue(a, now);
      const bOver = isOverdue(b, now);
      if (aOver !== bOver) return aOver ? -1 : 1;
      return new Date(a.due_at).getTime() - new Date(b.due_at).getTime();
    });
  }, [reminders, now]);

  const markDone = (r: Reminder) => {
    updateReminder.mutate(
      { id: r.id, done: true },
      {
        onSuccess: () =>
          push({ kind: 'green', title: 'Reminder marked done', sub: r.lead_name }),
        onError: (e) =>
          push({
            kind: 'blue',
            title: 'Could not update reminder',
            sub: e instanceof ApiError ? e.detail : 'Please try again',
          }),
      },
    );
  };

  return (
    <>
      <Topbar onAddLead={openAddLead} />
      <div className="view">
        <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
          {FILTERS.map((f) => (
            <button
              key={f.label}
              type="button"
              className={`btn sm ${filter === f.type ? 'primary' : 'ghost'}`}
              onClick={() => setFilter(f.type)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="card">
          {isLoading && <div className="empty">Loading…</div>}
          {error != null && (
            <div className="note" style={{ margin: 16 }}>
              {error instanceof ApiError ? error.detail : 'Failed to load reminders.'}
            </div>
          )}
          {!isLoading && error == null && sorted.length === 0 && (
            <EmptyState msg="No reminders here — you're all caught up." />
          )}
          {sorted.map((r, i) => (
            <ReminderRow
              key={r.id}
              reminder={r}
              divider={i > 0}
              now={now}
              onDone={markDone}
              pending={updateReminder.isPending}
            />
          ))}
        </div>
      </div>
      {addLeadModal}
    </>
  );
}
