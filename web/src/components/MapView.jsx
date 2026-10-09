import { useEffect, useRef } from 'react';
import L from 'leaflet';
import { statusMeta } from '../utils';

export default function MapView({ region, ponds, selectedId, onSelect, satellite, outlines }) {
  const hostRef = useRef(null);
  const mapRef = useRef(null);
  const layersRef = useRef({ markers: null, tiles: null, outlines: null });

  useEffect(() => {
    if (!hostRef.current || mapRef.current) return;
    const map = L.map(hostRef.current, { zoomControl: false, attributionControl: true, preferCanvas: true });
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    mapRef.current = map;
    layersRef.current.markers = L.layerGroup().addTo(map);
    const resize = new ResizeObserver(() => map.invalidateSize());
    resize.observe(hostRef.current);
    return () => {
      resize.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Dark Matter is the default. Satellite imagery is an explicit, reversible layer switch.
  useEffect(() => {
    if (!mapRef.current) return;
    // CARTO now requires an API key for external basemap requests. If no key is
    // configured, fall back to standard OpenStreetMap tiles instead of showing
    // CARTO's API-key-required watermark across the whole map.
    const cartoKey = import.meta.env.VITE_CARTO_API_KEY?.trim();
    const darkTiles = cartoKey
      ? L.tileLayer(`https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png?key=${encodeURIComponent(cartoKey)}`, {
          maxZoom: 19,
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
        })
      : L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          maxZoom: 19,
          subdomains: 'abc',
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
        });
    const tile = satellite
      ? L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
          maxZoom: 19,
          attribution: 'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics',
        })
      : darkTiles;
    layersRef.current.tiles?.remove();
    layersRef.current.tiles = tile.addTo(mapRef.current);
  }, [satellite]);

  useEffect(() => {
    if (!mapRef.current || !region) return;
    const [minLon, minLat, maxLon, maxLat] = region.bbox;
    mapRef.current.fitBounds([[minLat, minLon], [maxLat, maxLon]], { padding: [28, 28] });
  }, [region]);

  useEffect(() => {
    if (!mapRef.current || !ponds) return;
    const map = mapRef.current;
    layersRef.current.outlines?.remove();
    layersRef.current.markers.clearLayers();
    const pondById = new Map(ponds.map((pond) => [pond.id, pond]));
    const featureList = outlines?.type === 'FeatureCollection' && Array.isArray(outlines.features) ? outlines.features : [];
    const matchingFeatures = featureList.filter((feature) => {
      const id = feature?.properties?.id ?? feature?.properties?.pondId;
      return id && pondById.has(id) && feature?.geometry;
    });
    const hasMatchingOutlines = matchingFeatures.length > 0;

    if (hasMatchingOutlines) {
      layersRef.current.outlines = L.geoJSON({ type: 'FeatureCollection', features: matchingFeatures }, {
        style: (feature) => {
          const id = feature?.properties?.id ?? feature?.properties?.pondId;
          const pond = pondById.get(id);
          const color = statusMeta(pond?.status).color;
          const selected = id === selectedId;
          return {
            color,
            weight: selected ? 3 : 1.6,
            opacity: selected ? 1 : 0.92,
            fillColor: color,
            fillOpacity: selected ? 0.32 : 0.17,
            lineCap: 'round',
            lineJoin: 'round',
          };
        },
        onEachFeature: (feature, layer) => {
          const id = feature?.properties?.id ?? feature?.properties?.pondId;
          const pond = pondById.get(id);
          const meta = statusMeta(pond?.status);
          layer.bindTooltip(`${id} · ${meta.label}`, { sticky: true, className: 'pond-outline-tooltip' });
          layer.on('click', () => onSelect(id));
        },
      }).addTo(map);
    }

    const dense = ponds.length > 60;
    ponds.forEach((pond) => {
      const meta = statusMeta(pond.status);
      const iconHtml = hasMatchingOutlines
        ? `<div class="pond-marker outline-backed ${dense ? 'dense' : ''} ${pond.id === selectedId ? 'is-selected' : ''}" style="--pond-color:${meta.color}"><span class="pond-label">${pond.id}</span></div>`
        : `<div class="pond-marker ${dense ? 'dense' : ''} ${pond.id === selectedId ? 'is-selected' : ''}" style="--pond-color:${meta.color}"><span class="pond-dot"></span><span class="pond-label">${pond.id}</span></div>`;
      const icon = L.divIcon({
        className: 'pond-marker-wrap',
        html: iconHtml,
        iconSize: [96, 28],
        iconAnchor: hasMatchingOutlines ? [4, 14] : (dense ? [5, 14] : [10, 14]),
      });
      const marker = L.marker([pond.lat, pond.lon], { icon, title: `${pond.id} — ${meta.label}`, keyboard: true });
      marker.bindTooltip(`${pond.id} · ${meta.label}`, { direction: 'top', offset: [22, -12] });
      marker.on('click', () => onSelect(pond.id));
      marker.addTo(layersRef.current.markers);
    });
  }, [ponds, selectedId, onSelect, outlines]);

  return <div className="map-host" ref={hostRef} aria-label="Talaab pond map" />;
}
