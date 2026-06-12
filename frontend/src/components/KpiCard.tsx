import type { CSSProperties, ReactNode } from 'react';

export interface KpiCardProps {
  label: string;
  value: number | string;
  /** CSS colour for the left accent bar (--accent-c), e.g. 'var(--blue)'. */
  accent?: string;
  /** CSS colour for the icon square background, e.g. 'var(--blue-soft)'. */
  soft?: string;
  icon?: ReactNode;
  onClick?: () => void;
}

/** .stat KPI card — left accent bar, 30px Bricolage value, soft icon square. */
export function KpiCard({ label, value, accent, soft, icon, onClick }: KpiCardProps) {
  const style = { '--accent-c': accent ?? 'var(--accent)' } as CSSProperties;
  return (
    <div
      className={`stat${onClick ? ' clickable' : ''}`}
      style={style}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
    >
      <div className="k">{label}</div>
      <div className="v">{value}</div>
      {icon && (
        <span className="ico" style={{ background: soft ?? 'var(--panel-2)', color: accent ?? 'var(--accent)' }}>
          {icon}
        </span>
      )}
    </div>
  );
}
