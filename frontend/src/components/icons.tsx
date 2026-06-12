/**
 * Line-icon set (Lucide/Feather style): 24 viewBox, stroke currentColor,
 * strokeWidth 1.8, rendered at 17px by default. Plus brand SVGs
 * (OpenhouseLogo, WhatsAppLogo, MetaLogo).
 */
import type { ReactNode, SVGProps } from 'react';

export interface IconProps extends SVGProps<SVGSVGElement> {
  size?: number;
}

function Line({ size = 17, children, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export function IconDashboard(props: IconProps) {
  return (
    <Line {...props}>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </Line>
  );
}

export function IconLeads(props: IconProps) {
  return (
    <Line {...props}>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M3.5 20c.6-3.4 2.8-5 5.5-5s4.9 1.6 5.5 5" />
      <path d="M19 6v6M16 9h6" />
    </Line>
  );
}

export function IconQualified(props: IconProps) {
  return (
    <Line {...props}>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M3.5 20c.6-3.4 2.8-5 5.5-5s4.9 1.6 5.5 5" />
      <path d="m15.5 10 2.2 2.2L22 7.8" />
    </Line>
  );
}

export function IconPipeline(props: IconProps) {
  return (
    <Line {...props}>
      <path d="M3 5h18l-7 8v6l-4 2v-8L3 5Z" />
    </Line>
  );
}

export function IconConverted(props: IconProps) {
  return (
    <Line {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8 12.5 2.7 2.7L16.5 9" />
    </Line>
  );
}

export function IconInventory(props: IconProps) {
  return (
    <Line {...props}>
      <path d="M4 21V9.5L12 4l8 5.5V21" />
      <path d="M4 21h16" />
      <path d="M9.5 21v-6h5v6" />
    </Line>
  );
}

export function IconSupply(props: IconProps) {
  return (
    <Line {...props}>
      <path d="M12 3 3.5 7.5 12 12l8.5-4.5L12 3Z" />
      <path d="M3.5 7.5V16L12 21l8.5-5V7.5" />
      <path d="M12 12v9" />
    </Line>
  );
}

export function IconSociety(props: IconProps) {
  return (
    <Line {...props}>
      <path d="M3 21h18" />
      <path d="M5 21V7l5-3v17" />
      <path d="M14 21V11l5 2.5V21" />
      <path d="M7.5 9.5v.01M7.5 13v.01M7.5 16.5v.01" />
    </Line>
  );
}

export function IconGoldmine(props: IconProps) {
  return (
    <Line {...props}>
      <path d="M6 3h12l4 6-10 12L2 9l4-6Z" />
      <path d="M2 9h20M9.5 3 8 9l4 12M14.5 3 16 9l-4 12" />
    </Line>
  );
}

export function IconSettings(props: IconProps) {
  return (
    <Line {...props}>
      <path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3" />
      <path d="M2 14h4M10 8h4M18 16h4" />
    </Line>
  );
}

export function IconSearch(props: IconProps) {
  return (
    <Line {...props}>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </Line>
  );
}

export function IconBell(props: IconProps) {
  return (
    <Line {...props}>
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 8-3 8h18s-3-1-3-8" />
      <path d="M13.7 20a2 2 0 0 1-3.4 0" />
    </Line>
  );
}

export function IconPlus(props: IconProps) {
  return (
    <Line {...props}>
      <path d="M12 5v14M5 12h14" />
    </Line>
  );
}

export function IconChevron(props: IconProps) {
  return (
    <Line {...props}>
      <path d="m6 9 6 6 6-6" />
    </Line>
  );
}

export function IconPhone(props: IconProps) {
  return (
    <Line {...props}>
      <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3-8.7A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.13.96.36 1.9.7 2.8a2 2 0 0 1-.45 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.27a2 2 0 0 1 2.1-.45c.9.34 1.84.57 2.8.7a2 2 0 0 1 1.7 2.03Z" />
    </Line>
  );
}

export function IconCalendar(props: IconProps) {
  return (
    <Line {...props}>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M8 3v4M16 3v4M3 10h18" />
    </Line>
  );
}

export function IconFlame(props: IconProps) {
  return (
    <Line {...props}>
      <path d="M12 21c4 0 6.5-2.6 6.5-6.2 0-3.3-2.2-5.6-3.9-7.7-.5-.6-1.4-.3-1.5.5-.1 1-.5 2-1.4 2.6-.5-1.9-1.7-4-3.6-5.5-.6-.5-1.5 0-1.4.7.2 2.3-.7 3.6-1.7 5.2-.8 1.3-1.5 2.6-1.5 4.2C3.5 18.4 8 21 12 21Z" />
    </Line>
  );
}

export function IconPlay(props: IconProps) {
  return (
    <Line {...props}>
      <path d="m7 5 12 7-12 7V5Z" />
    </Line>
  );
}

export function IconMapPin(props: IconProps) {
  return (
    <Line {...props}>
      <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
      <circle cx="12" cy="10" r="3" />
    </Line>
  );
}

/* ---------- brand SVGs ---------- */

/** WhatsApp glyph (the real logo path), fill = currentColor. */
export function WhatsAppLogo({ size = 18, ...rest }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" {...rest}>
      <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413Z" />
    </svg>
  );
}

/** Meta/Facebook "f" roundel, fill = currentColor (use #1877f2 via color). */
export function MetaLogo({ size = 18, ...rest }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" {...rest}>
      <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073Z" />
    </svg>
  );
}

/** Openhouse brand mark — white house + orange flag on a dark rounded square. */
export function OpenhouseLogo({ size = 38, ...rest }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 38 38" fill="none" aria-hidden="true" {...rest}>
      <rect width="38" height="38" rx="9" fill="#1c1c1c" />
      <path
        d="M9 19.5 19 11l10 8.5V29a1.5 1.5 0 0 1-1.5 1.5h-17A1.5 1.5 0 0 1 9 29v-9.5Z"
        fill="#ffffff"
      />
      <rect x="16.6" y="23.5" width="4.8" height="7" rx="1" fill="#1c1c1c" />
      <path d="M19 11V4.5" stroke="#ffffff" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M19 4.2h7.4l-2.3 2.7 2.3 2.7H19V4.2Z" fill="#fa541c" />
    </svg>
  );
}
