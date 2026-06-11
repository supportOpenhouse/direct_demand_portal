/**
 * Route optimizer — pure functions, no DOM/Maps dependency, unit-testable.
 *
 * Distance model: straight-line haversine × ROAD_FACTOR (1.4) at an average
 * city driving speed of 28 km/h. The Google Directions API can later replace
 * these estimates without touching callers.
 *
 * Optimisation: nearest-neighbour seed + 2-opt improvement on the open path
 * (start is not fixed, the path does not return to origin).
 */

export interface LatLng {
  lat: number;
  lng: number;
}

export const ROAD_FACTOR = 1.4;
export const AVG_SPEED_KMPH = 28;

const EARTH_RADIUS_KM = 6371;

/** Great-circle distance in km between two coordinates. */
export function haversineKm(a: LatLng, b: LatLng): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(h));
}

/** Estimated driving leg: km (1 d.p.) and minutes (whole) via road factor + avg speed. */
export function legEstimate(a: LatLng, b: LatLng): { km: number; min: number } {
  const km = haversineKm(a, b) * ROAD_FACTOR;
  const min = (km / AVG_SPEED_KMPH) * 60;
  return { km: Math.round(km * 10) / 10, min: Math.round(min) };
}

function pathDistance(stops: LatLng[]): number {
  let total = 0;
  for (let i = 0; i < stops.length - 1; i++) {
    total += haversineKm(stops[i], stops[i + 1]);
  }
  return total;
}

/** Trip totals over consecutive stops: km (1 d.p.) and minutes (whole). */
export function routeTotals(stops: LatLng[]): { km: number; min: number } {
  const km = pathDistance(stops) * ROAD_FACTOR;
  const min = (km / AVG_SPEED_KMPH) * 60;
  return { km: Math.round(km * 10) / 10, min: Math.round(min) };
}

/** Nearest-neighbour ordering starting from stops[startIndex]. */
export function nearestNeighbour<T extends LatLng>(stops: T[], startIndex = 0): T[] {
  if (stops.length <= 2) return [...stops];
  const remaining = [...stops];
  const [first] = remaining.splice(startIndex, 1);
  const ordered: T[] = [first];
  while (remaining.length > 0) {
    const last = ordered[ordered.length - 1];
    let bestIdx = 0;
    let bestDist = Infinity;
    for (let i = 0; i < remaining.length; i++) {
      const d = haversineKm(last, remaining[i]);
      if (d < bestDist) {
        bestDist = d;
        bestIdx = i;
      }
    }
    ordered.push(remaining.splice(bestIdx, 1)[0]);
  }
  return ordered;
}

/** 2-opt improvement on an open path; loops until no improving reversal remains. */
export function twoOpt<T extends LatLng>(stops: T[]): T[] {
  if (stops.length <= 3) return [...stops];
  let best = [...stops];
  let bestDist = pathDistance(best);
  let improved = true;
  let guard = 0;
  while (improved && guard < 50) {
    improved = false;
    guard++;
    for (let i = 0; i < best.length - 1; i++) {
      for (let j = i + 1; j < best.length; j++) {
        const candidate = [
          ...best.slice(0, i),
          ...best.slice(i, j + 1).reverse(),
          ...best.slice(j + 1),
        ];
        const d = pathDistance(candidate);
        if (d < bestDist - 1e-9) {
          best = candidate;
          bestDist = d;
          improved = true;
        }
      }
    }
  }
  return best;
}

/**
 * Full optimisation: nearest-neighbour seed (trying each start) + 2-opt.
 * Returns the reordered stops, new totals and the km/min saved vs the input order.
 */
export function optimizeRoute<T extends LatLng>(
  stops: T[],
): { order: T[]; km: number; min: number; savedKm: number; savedMin: number } {
  const before = routeTotals(stops);
  if (stops.length <= 2) {
    return { order: [...stops], km: before.km, min: before.min, savedKm: 0, savedMin: 0 };
  }
  let best: T[] = stops;
  let bestDist = pathDistance(stops);
  for (let s = 0; s < stops.length; s++) {
    const candidate = twoOpt(nearestNeighbour(stops, s));
    const d = pathDistance(candidate);
    if (d < bestDist) {
      bestDist = d;
      best = candidate;
    }
  }
  const after = routeTotals(best);
  return {
    order: [...best],
    km: after.km,
    min: after.min,
    savedKm: Math.max(0, Math.round((before.km - after.km) * 10) / 10),
    savedMin: Math.max(0, before.min - after.min),
  };
}
