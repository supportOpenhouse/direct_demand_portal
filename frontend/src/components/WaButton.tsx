import { WhatsAppLogo } from './icons';

export interface WaButtonProps {
  phone: string;
  message?: string;
}

/** Builds a wa.me href; bare 10-digit numbers get the +91 prefix. */
export function waHref(phone: string, message?: string): string {
  let digits = phone.replace(/\D/g, '');
  if (digits.length === 10) digits = `91${digits}`;
  const text = message ? `?text=${encodeURIComponent(message)}` : '';
  return `https://wa.me/${digits}${text}`;
}

/** 36×36 green rounded-square WhatsApp icon button (.wa-ico). */
export function WaButton({ phone, message }: WaButtonProps) {
  return (
    <a
      className="wa-ico"
      href={waHref(phone, message)}
      target="_blank"
      rel="noreferrer"
      title="WhatsApp"
      onClick={(e) => e.stopPropagation()}
    >
      <WhatsAppLogo size={18} />
    </a>
  );
}
