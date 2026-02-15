'use client';

import { MapContainer, Marker, TileLayer, ImageOverlay } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

export default function MapRender({ preview }: { preview: any }) {
  if (!preview) return null;
  const bounds = preview.bounds || [[45, 10], [46, 11]];
  return (
    <MapContainer bounds={bounds} style={{ height: 360, width: '100%' }}>
      <TileLayer url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" />
      {preview.overlay_url && <ImageOverlay url={preview.overlay_url} bounds={bounds} opacity={0.55} />}
      {(preview.turbines_geojson?.features || []).map((f: any) => (
        <Marker key={f.properties.id} position={[f.geometry.coordinates[1], f.geometry.coordinates[0]]} />
      ))}
    </MapContainer>
  );
}
