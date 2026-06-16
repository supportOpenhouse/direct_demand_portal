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
