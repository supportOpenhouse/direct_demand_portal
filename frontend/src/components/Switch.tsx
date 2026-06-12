export interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

/** 42×24 toggle (.switch) — accent-coloured when on. */
export function Switch({ checked, onChange, disabled }: SwitchProps) {
  return (
    <button
      type="button"
      className={`switch${checked ? ' on' : ''}`}
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
    />
  );
}
