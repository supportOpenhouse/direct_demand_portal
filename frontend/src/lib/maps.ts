/* Lazy Google Maps JS loader — one shared script, resolves when ready. */
export const MAPS_API_KEY = (import.meta.env.VITE_MAPS_API_KEY as string) || "";

declare global {
  // eslint-disable-next-line no-var
  var google: any;
}

let promise: Promise<any> | null = null;

export function loadGoogleMaps(): Promise<any> {
  if (typeof google !== "undefined" && google.maps) return Promise.resolve(google);
  if (promise) return promise;
  promise = new Promise((resolve, reject) => {
    if (!MAPS_API_KEY) {
      reject(new Error("VITE_MAPS_API_KEY not set"));
      return;
    }
    const s = document.createElement("script");
    s.src = `https://maps.googleapis.com/maps/api/js?key=${MAPS_API_KEY}&libraries=geometry`;
    s.async = true;
    s.onload = () => resolve(google);
    s.onerror = () => reject(new Error("Google Maps failed to load — check the key & enabled APIs"));
    document.head.appendChild(s);
  });
  return promise;
}

/** Build a Google Maps directions URL (opens the app on mobile, maps.google on web).
   Stops are visited in the given (optimized) order. Origin defaults to the device's
   live location when `start` is null. */
export function mapsDirectionsUrl(
  start: { lat: number; lng: number } | null,
  stops: { lat?: number | null; lng?: number | null }[]
): string | null {
  const pts = stops.filter((s) => s.lat != null && s.lng != null).map((s) => `${s.lat},${s.lng}`);
  if (!pts.length) return null;
  const params = new URLSearchParams({ api: "1", travelmode: "driving", destination: pts[pts.length - 1] });
  if (start) params.set("origin", `${start.lat},${start.lng}`);
  const waypoints = pts.slice(0, -1);
  if (waypoints.length) params.set("waypoints", waypoints.join("|"));
  return `https://www.google.com/maps/dir/?${params.toString()}`;
}

export function openInMaps(start: { lat: number; lng: number } | null, stops: { lat?: number | null; lng?: number | null }[]) {
  const url = mapsDirectionsUrl(start, stops);
  if (url) window.open(url, "_blank", "noopener");
}

/** Get the RM's current location; falls back to null if denied/unavailable. */
export function getCurrentLocation(): Promise<{ lat: number; lng: number } | null> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 }
    );
  });
}
