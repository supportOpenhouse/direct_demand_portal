/* SSE consumed with fetch() + ReadableStream rather than EventSource.

   EventSource cannot set request headers, and auth here is `Authorization: Bearer`
   from localStorage (api.ts). The usual workaround is `?token=` in the URL, which
   puts the JWT into access logs and Referer headers — so we read the stream by hand
   instead. It costs us frame parsing and reconnect logic; that's the whole reason
   this file exists.

   `healthy` is the caller's signal to fall back to polling. Reporting it is what
   keeps a dead stream from silently becoming a dead page. */
import { useEffect, useRef, useState } from "react";
import { API_URL, getDevUser, getToken } from "./api";

const BACKOFF_MS = [1000, 2000, 4000, 8000, 15000];
// Report unhealthy after this many consecutive failures. One blip shouldn't flip the
// page into polling; a real outage should, quickly.
const FAILURES_BEFORE_FALLBACK = 3;
// How long a connection must survive before it counts as genuinely recovered. Longer
// than the server's 25s keepalive, so a stream that never carries anything still
// proves itself by staying up.
const STABLE_AFTER_MS = 30000;

export function useEventStream(path: string, onEvent: (event: any) => void) {
  const [healthy, setHealthy] = useState(false);
  // Held in a ref so reconnecting never re-runs the effect — the effect must depend
  // only on `path`, or every render would tear down and rebuild the connection.
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    const abort = new AbortController();
    let stopped = false;
    let failures = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function readStream() {
      const token = getToken();
      const dev = getDevUser();
      const res = await fetch(`${API_URL}${path}`, {
        signal: abort.signal,
        headers: {
          Accept: "text/event-stream",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(dev ? { "X-Dev-User": dev } : {}),
        },
      });
      if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);

      // Only a connection that LASTS counts as recovery. Resetting on connect alone
      // means a server that accepts then immediately closes — Redis down, so the
      // subscribe ends at once — gets reconnected every 2s forever, by every RM, at
      // exactly the moment it's least able to take it.
      const settle = setTimeout(() => { failures = 0; }, STABLE_AFTER_MS);
      setHealthy(true);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Frames are separated by a blank line. Anything after the last separator is
        // a partial frame and stays in the buffer until the rest arrives.
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";

        for (const frame of frames) {
          for (const line of frame.split("\n")) {
            // ':' prefixed lines are comments — that's what the keepalive is
            if (!line.startsWith("data:")) continue;
            try {
              handler.current(JSON.parse(line.slice(5).trim()));
            } catch {
              /* a malformed frame must not kill the connection */
            }
          }
        }
      }
      } finally {
        // A stream that died before settling leaves `failures` intact, so the backoff
        // keeps growing instead of restarting from 1s.
        clearTimeout(settle);
      }
      throw new Error("stream closed"); // fall through to reconnect
    }

    async function loop() {
      while (!stopped) {
        try {
          await readStream();
        } catch (e) {
          if (stopped || abort.signal.aborted) return;
          failures += 1;
          if (failures >= FAILURES_BEFORE_FALLBACK) setHealthy(false);
        }
        if (stopped) return;
        const wait = BACKOFF_MS[Math.min(failures, BACKOFF_MS.length - 1)];
        await new Promise((r) => { timer = setTimeout(r, wait); });
      }
    }

    loop();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      abort.abort();
    };
  }, [path]);

  return healthy;
}
