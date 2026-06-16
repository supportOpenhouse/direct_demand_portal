/* Route geometry — haversine distance + nearest-neighbour/2-opt optimization with
   a FIXED start (the RM's current location). The visit order is optimized
   regardless of the order societies were picked. */
export interface Pt {
  lat: number;
  lng: number;
}

export function haversine(a: Pt, b: Pt): number {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((a.lat * Math.PI) / 180) * Math.cos((b.lat * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

/** total straight-line km along start → stops (in the given order) */
export function pathKm(start: Pt, stops: Pt[]): number {
  let t = 0;
  let prev = start;
  for (const s of stops) {
    t += haversine(prev, s);
    prev = s;
  }
  return t;
}

function twoOpt<T extends Pt>(start: Pt, route: T[]): T[] {
  let best = route;
  let improved = true;
  while (improved) {
    improved = false;
    for (let i = 0; i < best.length - 1; i++) {
      for (let k = i + 1; k < best.length; k++) {
        const cand = [...best.slice(0, i), ...best.slice(i, k + 1).reverse(), ...best.slice(k + 1)];
        if (pathKm(start, cand) < pathKm(start, best) - 1e-9) {
          best = cand;
          improved = true;
        }
      }
    }
  }
  return best;
}

/** Optimize the visit order to minimize total drive starting from `start`.
    Nearest-neighbour from the fixed start, then 2-opt refinement. */
export function optimizeRoute<T extends Pt>(start: Pt, stops: T[]): T[] {
  if (stops.length < 2) return stops;
  const unvisited = [...stops];
  const route: T[] = [];
  let last: Pt = start;
  while (unvisited.length) {
    let bi = 0;
    let bd = Infinity;
    unvisited.forEach((s, idx) => {
      const d = haversine(last, s);
      if (d < bd) {
        bd = d;
        bi = idx;
      }
    });
    last = unvisited[bi];
    route.push(unvisited.splice(bi, 1)[0]);
  }
  return twoOpt(start, route);
}

/** estimate: straight-line × road factor; ~26 km/h city average */
export function estimateLeg(a: Pt, b: Pt): { km: number; min: number } {
  const km = haversine(a, b) * 1.4;
  return { km: +km.toFixed(1), min: Math.max(1, Math.round((km / 26) * 60)) };
}

export function fmtMin(m: number): string {
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return `${h}h ${mm ? mm + "m" : ""}`.trim();
}
