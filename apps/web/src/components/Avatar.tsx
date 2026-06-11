import { initials } from '../lib/format';

export interface AvatarProps {
  name: string;
  size?: number; // px, default 32
}

/** Gradient initials square (.avatar). */
export function Avatar({ name, size = 32 }: AvatarProps) {
  return (
    <span
      className="avatar"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.38) }}
    >
      {initials(name)}
    </span>
  );
}
