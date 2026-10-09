import { useEffect, useRef } from 'react';
import L from 'leaflet';
import { statusMeta } from '../utils';

export default function MapView({ region, ponds, selectedId, onSelect, satellite }) {
  const hostRef = useRef(null);
  const mapRef = useRef(null);
  const layersRef = useRef({ markers: null, tiles: null });

  useEffect(() => {
    if (!hostRef.current || mapRef.current) return;
    const map = L.map(hostRef.current, { zoomControl: false, attributionControl: true });
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    mapRef.current = map;
    layersRef.current.markers = L.layerGroup().addTo(map);
    // Leaflet must be told when its box changes size (layout, window resize), or tiles and
    // markers are placed for the old size.
    const resize = new ResizeObserver(() => map.invalidateSize());
    resize.observe(hostRef.current);

    return () => {
      resize.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;
    const tile = satellite
      ? L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
          maxZoom: 19,
          attribution: 'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics',
        })
      : L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          maxZoom: 19,
          attribution: '&copy; OpenStreetMap contributors',
        });
    layersRef.current.tiles?.remove();
    layersRef.current.tiles = tile.addTo(map);
  }, [satellite]);

  useEffect(() => {
    if (!mapRef.current || !region) return;
    const [minLon, minLat, maxLon, maxLat] = region.bbox;
    mapRef.current.fitBounds([[minLat, minLon], [maxLat, maxLon]], { padding: [28, 28] });
  }, [region]);

  useEffect(() => {
    if (!mapRef.current || !ponds) return;
    const group = layersRef.current.markers;
    group.clearLayers();
    const dense = ponds.length > 60;
    ponds.forEach((pond) => {
      const meta = statusMeta(pond.status);
      const icon = L.divIcon({
        className: 'pond-marker-wrap',
        html: `<div class="pond-marker ${dense ? 'dense' : ''} ${pond.id === selectedId ? 'is-selected' : ''}" style="--pond-color:${meta.color}"><span class="pond-dot"></span><span class="pond-label">${pond.id}</span></div>`,
        iconSize: [96, 38],
        iconAnchor: dense ? [6, 19] : [12, 19],
      });
      const marker = L.marker([pond.lat, pond.lon], { icon, title: `${pond.id} — ${meta.label}` });
      marker.bindTooltip(`${pond.id} · ${meta.label}`, { direction: 'top', offset: [26, -18] });
      marker.on('click', () => onSelect(pond.id));
      marker.addTo(group);
    });
  }, [ponds, selectedId, onSelect]);

  return <div className="map-host" ref={hostRef} aria-label="Talaab pond map" />;
}
