import { useEffect, useRef } from 'react';
import L from 'leaflet';

// Districts arrive pre-ranked by need. The map uses the supplied ranking order,
// rather than calculating a score in the browser.
const RANK_COLORS = ['#c96b56', '#d98b66', '#e1ad72', '#e4c88e', '#bdcba8', '#9dbca0', '#83ad95', '#6f9b88'];

export default function DivisionMap({ outlines, districts = [], selectedRegion, onSelectDistrict }) {
  const hostRef = useRef(null);
  const mapRef = useRef(null);
  const layerRef = useRef(null);

  useEffect(() => {
    if (!hostRef.current || mapRef.current) return undefined;
    const map = L.map(hostRef.current, { zoomControl: false, attributionControl: true, scrollWheelZoom: false, preferCanvas: true });
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 15,
      subdomains: 'abc',
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
    }).addTo(map);
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; layerRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    layerRef.current?.remove();
    layerRef.current = null;
    const collection = outlines?.type === 'FeatureCollection'
      ? outlines
      : outlines?.geojson?.type === 'FeatureCollection'
        ? outlines.geojson
        : outlines?.outlines?.type === 'FeatureCollection'
          ? outlines.outlines
          : null;
    if (!collection?.features?.length) return;

    const byRegion = new Map(districts.map((district, index) => [district.region, { district, index }]));
    layerRef.current = L.geoJSON(collection, {
      style: (feature) => {
        const region = feature?.properties?.region;
        const entry = byRegion.get(region);
        const selected = region === selectedRegion;
        const color = entry ? RANK_COLORS[Math.min(entry.index, RANK_COLORS.length - 1)] : '#b8c5b9';
        return { color: selected ? '#315c43' : '#ffffff', weight: selected ? 3 : 1.6, opacity: 1, fillColor: color, fillOpacity: selected ? 0.82 : 0.68, lineJoin: 'round' };
      },
      onEachFeature: (feature, layer) => {
        const region = feature?.properties?.region;
        const entry = byRegion.get(region)?.district;
        const name = entry?.name ?? feature?.properties?.name ?? region ?? 'District';
        const localName = entry?.nameMr ?? feature?.properties?.nameMr;
        const stats = entry ? `${entry.dry ?? 0} dry · ${entry.critical ?? 0} critical · ${entry.watch ?? 0} watch` : '';
        layer.bindTooltip(`<strong>${name}</strong>${localName ? ` · ${localName}` : ''}<br>${stats}`, { sticky: true, className: 'division-map-tooltip' });
        layer.on('click', () => region && onSelectDistrict?.(region));
      },
    }).addTo(map);
    const bounds = layerRef.current.getBounds();
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [18, 18], maxZoom: 8 });
  }, [outlines, districts, selectedRegion, onSelectDistrict]);

  return <div className="division-map-canvas" ref={hostRef} aria-label="Marathwada district map" />;
}
