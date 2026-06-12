/**
 * Visit recordings card — .rec rows: round play button, file name + who/when,
 * faux waveform, mm:ss duration.
 */
import { EmptyState } from '../../components/EmptyState';
import { IconPlay } from '../../components/icons';
import { useToast } from '../../components/Toast';
import { formatDate } from '../../lib/format';
import type { Recording } from '../../lib/types';

function mmss(totalSec: number): string {
  const sec = Math.max(0, Math.round(totalSec));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function RecordingsPanel({ recordings }: { recordings: Recording[] }) {
  const { push } = useToast();

  return (
    <div className="card panel-pad">
      <div className="panel-title">
        <IconPlay size={16} />
        <span>Visit recordings</span>
      </div>
      {recordings.length === 0 ? (
        <EmptyState msg="No recordings yet — they appear after site visits." />
      ) : (
        recordings.map((r) => (
          <div key={r.id} className="rec">
            <button
              type="button"
              className="play"
              title={`Play ${r.file_ref}`}
              onClick={() => push({ kind: 'blue', title: 'Playing recording', sub: r.file_ref })}
            >
              <IconPlay size={13} />
            </button>
            <div style={{ minWidth: 0, maxWidth: '55%' }}>
              <div
                style={{
                  fontSize: 12.5,
                  fontWeight: 600,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {r.file_ref}
              </div>
              <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                {r.recorded_by_name ?? '—'} · {formatDate(r.recorded_at)}
              </div>
            </div>
            <span className="wave" />
            <span className="dur">{mmss(r.duration_sec)}</span>
          </div>
        ))
      )}
    </div>
  );
}
