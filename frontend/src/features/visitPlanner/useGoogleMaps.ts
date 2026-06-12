import { useEffect, useState } from 'react';

/**
 * Lazily loads the Google Maps JS API using VITE_MAPS_API_KEY.
 * Without a key it returns { ready: false, google: null } forever —
 * callers fall back to estimates + a placeholder (see MapCanvas).
 */

let loaderPromise: Promise<void> | null = null;

function loadMapsScript(key: string): Promise<void> {
  if (!loaderPromise) {
    loaderPromise = new Promise((resolve, reject) => {
      if (window.google?.maps) {
        resolve();
        return;
      }
      const script = document.createElement('script');
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}`;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => {
        loaderPromise = null;
        reject(new Error('Google Maps script failed to load'));
      };
      document.head.appendChild(script);
    });
  }
  return loaderPromise;
}

export interface GoogleMapsState {
  ready: boolean;
  /** window.google when ready (google.maps namespace available), else null. */
  google: GoogleGlobal | null;
}

export function useGoogleMaps(): GoogleMapsState {
  const key = import.meta.env.VITE_MAPS_API_KEY;
  const [ready, setReady] = useState<boolean>(() => !!(key && window.google?.maps));

  useEffect(() => {
    if (!key || ready) return;
    let active = true;
    loadMapsScript(key)
      .then(() => {
        if (active) setReady(true);
      })
      .catch(() => {
        /* stays not-ready; planner keeps working on estimates */
      });
    return () => {
      active = false;
    };
  }, [key, ready]);

  return ready ? { ready: true, google: window.google ?? null } : { ready: false, google: null };
}
