import { useEffect, useRef } from 'react';
import { useGoogleMaps } from './useGoogleMaps';

export interface MapStop {
  lat: number;
  lng: number;
  /** Tooltip title for the pin. */
  name?: string;
}

export interface MapCanvasProps {
  /** Ordered stops — rendered as numbered pins joined by a polyline. */
  stops: MapStop[];
  /** Pixel height of the map area (default 320). */
  height?: number;
}

const DEFAULT_CENTER = { lat: 28.4595, lng: 77.0266 }; // Gurgaon

/**
 * Live Google Map with numbered pins + route polyline when VITE_MAPS_API_KEY
 * is configured; otherwise a .note placeholder (estimates still work).
 */
export function MapCanvas({ stops, height = 320 }: MapCanvasProps) {
  const { ready, google } = useGoogleMaps();
  const divRef = useRef<HTMLDivElement | null>(null);
  // Google Maps objects are intentionally loose-typed (no @types/google.maps dep).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mapRef = useRef<any>(null);
  const overlaysRef = useRef<{ setMap: (m: unknown) => void }[]>([]);

  useEffect(() => {
    if (!ready || !google?.maps || !divRef.current) return;
    const maps = google.maps;

    if (!mapRef.current) {
      mapRef.current = new maps.Map(divRef.current, {
        zoom: 11,
        center: stops[0] ?? DEFAULT_CENTER,
        mapTypeControl: false,
        streetViewControl: false,
        fullscreenControl: false,
      });
    }
    const map = mapRef.current;

    overlaysRef.current.forEach((o) => o.setMap(null));
    overlaysRef.current = [];
    if (stops.length === 0) return;

    const bounds = new maps.LatLngBounds();
    stops.forEach((stop, i) => {
      const marker = new maps.Marker({
        position: { lat: stop.lat, lng: stop.lng },
        map,
        title: stop.name,
        label: { text: String(i + 1), color: '#ffffff', fontWeight: '700', fontSize: '12px' },
      });
      overlaysRef.current.push(marker);
      bounds.extend({ lat: stop.lat, lng: stop.lng });
    });

    const polyline = new maps.Polyline({
      path: stops.map((s) => ({ lat: s.lat, lng: s.lng })),
      map,
      strokeColor: '#fa541c',
      strokeWeight: 3,
      strokeOpacity: 0.85,
    });
    overlaysRef.current.push(polyline);

    if (stops.length > 1) {
      map.fitBounds(bounds, 48);
    } else {
      map.setCenter({ lat: stops[0].lat, lng: stops[0].lng });
      map.setZoom(13);
    }
  }, [ready, google, stops]);

  if (!ready) {
    return (
      <div
        className="note"
        style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      >
        Add VITE_MAPS_API_KEY to see the live map
      </div>
    );
  }

  return <div ref={divRef} style={{ height, borderRadius: 12, overflow: 'hidden' }} />;
}
