/* Call-recording player: one button, a progress ring around it, and an elapsed-time
   readout that doubles as a link to the audio file itself.

   Replaces the browser's native <audio controls>, which renders a different
   widget in every browser and is far too wide for the Call Log's cell. The
   <audio> element is still doing all the real work — it's just not drawing
   itself. */
import React, { useRef, useState } from "react";

/* A call's duration, wrapped so it opens the recording in a new tab — where the
   browser gives you scrubbing, playback speed and Save As for nothing.

   Plain text when there's no file: a link that 404s is worse than no link, and a
   zero-duration call never has one. stopPropagation because these sit inside rows
   and cards that carry their own click. */
export function RecordingLink(
  { url, children }: { url?: string | null; children: React.ReactNode },
) {
  if (!url) return <>{children}</>;
  return (
    <a href={url} target="_blank" rel="noreferrer" className="rec-time"
       onClick={(e) => e.stopPropagation()}
       title="Open this recording in a new tab — to download, scrub or change speed">
      {children}
    </a>
  );
}

const R = 16;                       // ring radius in the 36×36 viewBox
const C = 2 * Math.PI * R;          // circumference — the dash length we offset

const fmt = (s: number) => {
  if (!isFinite(s) || s < 0) s = 0;
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
};

const IconPlay = () => (
  <svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor" style={{ marginLeft: 1.5 }}>
    <path d="M8 5v14l11-7z" />
  </svg>
);

const IconPause = () => (
  <svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor">
    <path d="M6 4h4v16H6zM14 4h4v16h-4z" />
  </svg>
);

export default function RecordingPlayer({ src, size = 34 }: { src: string; size?: number }) {
  const ref = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [t, setT] = useState(0);
  const [dur, setDur] = useState(0);
  const [err, setErr] = useState(false);

  /* Bonvoice streams some files without a length, so duration can come back
     Infinity or NaN — guard it or the ring renders NaN into the DOM. */
  const pct = dur > 0 && isFinite(dur) ? Math.min(1, t / dur) : 0;

  const toggle = () => {
    const el = ref.current;
    if (!el) return;
    if (el.paused) {
      // The Call Log lists ~25 calls. Without this, every press stacks another
      // recording on top of the last one.
      document.querySelectorAll("audio").forEach((a) => a !== el && a.pause());
      el.play().catch(() => setErr(true));
    } else {
      el.pause();  // pause, not stop — keeps your place mid-call
    }
  };

  if (err) return <span style={{ fontSize: 12, color: "var(--muted)" }}>unavailable</span>;

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 9 }}>
      <audio
        ref={ref}
        src={src}
        preload="none"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onTimeUpdate={(e) => setT(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => setDur(e.currentTarget.duration)}
        onEnded={() => { setPlaying(false); setT(0); }}
        onError={() => setErr(true)}
      />
      <button
        type="button"
        onClick={toggle}
        title={playing ? "Pause recording" : "Play recording"}
        aria-label={playing ? "Pause recording" : "Play recording"}
        style={{
          position: "relative", width: size, height: size, flex: "none", padding: 0,
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          background: "none", border: "none", cursor: "pointer", color: "var(--ink)",
        }}
      >
        <svg viewBox="0 0 36 36" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
          <circle cx="18" cy="18" r={R} fill="none" stroke="var(--line)" strokeWidth="2.5" />
          <circle
            cx="18" cy="18" r={R} fill="none"
            stroke="var(--emerald)" strokeWidth="2.5" strokeLinecap="round"
            strokeDasharray={C} strokeDashoffset={C * (1 - pct)}
            transform="rotate(-90 18 18)"   /* fill clockwise from 12 o'clock */
            style={{ transition: "stroke-dashoffset .12s linear" }}
          />
        </svg>
        {playing ? <IconPause /> : <IconPlay />}
      </button>
      {/* Both providers hand us a direct URL — Bonvoice's downloadvoice endpoint,
          Huvo's GCS object — neither of which needs an Authorization header from us,
          so a plain link works and no token goes anywhere near the URL. */}
      <span style={{ fontFamily: "'Spline Sans Mono'", fontSize: 12, color: "var(--muted)" }}>
        <RecordingLink url={src}>{fmt(t)}</RecordingLink>
      </span>
    </span>
  );
}
