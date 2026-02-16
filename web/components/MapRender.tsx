'use client';

import { ImageOverlay, MapContainer, Marker, TileLayer } from 'react-leaflet';
import type { LatLngBoundsExpression, LatLngTuple } from 'leaflet';
import 'leaflet/dist/leaflet.css';

type Preview = {
  bounds?: unknown;
  overlay_url?: string;
  turbines_geojson?: { features?: Array<{ properties?: { id?: string | number }; geometry?: { coordinates?: [number, number] } }> };
};

const FALLBACK_BOUNDS: LatLngBoundsExpression = [[45, 10], [46, 11]];

function toLatLngTuple(value: unknown): LatLngTuple | null {
  if (!Array.isArray(value) || value.length !== 2) return null;
  const lat = Number(value[0]);
  const lon = Number(value[1]);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  return [lat, lon];
}

function normalizeBounds(rawBounds: unknown): LatLngBoundsExpression {
  if (!Array.isArray(rawBounds) || rawBounds.length !== 2) return FALLBACK_BOUNDS;

  const first = toLatLngTuple(rawBounds[0]);
  const second = toLatLngTuple(rawBounds[1]);
  if (!first || !second) return FALLBACK_BOUNDS;

  const south = Math.min(first[0], second[0]);
  const north = Math.max(first[0], second[0]);
  const west = Math.min(first[1], second[1]);
  const east = Math.max(first[1], second[1]);

  return [[south, west], [north, east]];
}

function resolveOverlayUrl(overlayUrl?: string): string | null {
  if (!overlayUrl) return null;
  if (/^https?:\/\//i.test(overlayUrl)) return overlayUrl;

  const apiBase = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';
  const base = apiBase.endsWith('/') ? apiBase.slice(0, -1) : apiBase;
  const path = overlayUrl.startsWith('/') ? overlayUrl : `/${overlayUrl}`;
  return `${base}${path}`;
}

export default function MapRender({ preview }: { preview: Preview }) {
  if (!preview) return null;

  const bounds = normalizeBounds(preview.bounds);
  const overlayUrl = resolveOverlayUrl(preview.overlay_url);

  return (
    <MapContainer bounds={bounds} style={{ height: 360, width: '100%' }}>
      <TileLayer url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" />
      {overlayUrl && <ImageOverlay url={overlayUrl} bounds={bounds} opacity={0.55} />}
      {(preview.turbines_geojson?.features || []).map((f) => {
        const coords = f.geometry?.coordinates;
        if (!coords) return null;
        return <Marker key={f.properties?.id ?? `${coords[0]}-${coords[1]}`} position={[coords[1], coords[0]]} />;
      })}
    </MapContainer>
  );
}
