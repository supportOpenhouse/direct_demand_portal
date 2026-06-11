export interface EmptyStateProps {
  msg: string;
}

/** Centered muted empty state (.empty). */
export function EmptyState({ msg }: EmptyStateProps) {
  return <div className="empty">{msg}</div>;
}
