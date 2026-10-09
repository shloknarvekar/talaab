import { useEffect, useRef } from 'react';
import L from 'leaflet';
import { statusMeta, STATUS_KEYS } from '../utils';

function pondPriority(pond) {
  // Higher-priority markers are rendered last and receive a larger z-index.
  if (pond.status === 'dry') return 7;
  if (pond.status === 'critical') return 6;
  if (pond.flag === 'faster-than-sun') return 5;
  if (pond.status === 'watch') return 3;
  if (pond.status === 'unknown') return 2;
  return 1;
}

export default function MapView({
  region,
  ponds,
  selectedId,
  onSelect,
  satellite,
  outlines,
  visibleStatuses = STATUS_KEYS,
  focusRequest = 0,
}) {
  const hostRef = useRef(null);
  const mapRef = useRef(null);
  const lastFocusRequestRef = useRef(0);
  const layersRef = useRef({ markers: null, tiles: null, outlines: null });

  useEffect(() => {
    if (!hostRef.current || mapRef.current) return undefined;
    const map = L.map(hostRef.current, {
      zoomControl: false,
      attributionControl: true,
      preferCanvas: true,
    });
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    mapRef.current = map;
    layersRef.current.markers = L.layerGroup().addTo(map);

    const updateLabelVisibility = () => {
      hostRef.current?.classList.toggle('pond-labels-visible', map.getZoom() >= 13);
    };
    map.on('zoomend', updateLabelVisibility);
    updateLabelVisibility();

    const resize = new ResizeObserver(() => map.invalidateSize());
    resize.observe(hostRef.current);
    return () => {
      resize.disconnect();
      map.off('zoomend', updateLabelVisibility);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Dark Matter is used when a CARTO key is configured; otherwise keep the map usable
  // with OpenStreetMap tiles. Satellite imagery is an explicit, reversible layer switch.
  useEffect(() => {
    if (!mapRef.current) return;
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
          attribution: 'Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics',
        })
      : darkTiles;
    layersRef.current.tiles?.remove();
    layersRef.current.tiles = tile.addTo(mapRef.current);
  }, [satellite]);

  useEffect(() => {
    if (!mapRef.current || !region?.bbox) return;
    const [minLon, minLat, maxLon, maxLat] = region.bbox;
    mapRef.current.fitBounds([[minLat, minLon], [maxLat, maxLon]], { padding: [28, 28] });
  }, [region]);

  // A deliberate selection (from the list or a marker) brings the pond into view.
  // The request counter prevents normal date/data refreshes from repeatedly zooming.
  useEffect(() => {
    if (!mapRef.current || !selectedId || !focusRequest || focusRequest === lastFocusRequestRef.current) return;
    const pond = ponds.find((item) => item.id === selectedId);
    lastFocusRequestRef.current = focusRequest;
    if (!pond || !Number.isFinite(Number(pond.lat)) || !Number.isFinite(Number(pond.lon))) return;
    const map = mapRef.current;
    map.flyTo([Number(pond.lat), Number(pond.lon)], Math.min(16, Math.max(13, map.getZoom())), {
      duration: 0.65,
    });
  }, [focusRequest, selectedId, ponds]);

  useEffect(() => {
    if (!mapRef.current || !Array.isArray(ponds)) return;
    const map = mapRef.current;
    const visibleStatusSet = new Set(visibleStatuses);
    const visiblePonds = ponds.filter((pond) => visibleStatusSet.has(pond.status));
    const pondById = new Map(visiblePonds.map((pond) => [pond.id, pond]));

    layersRef.current.outlines?.remove();
    layersRef.current.outlines = null;
    layersRef.current.markers.clearLayers();

    const featureList = outlines?.type === 'FeatureCollection' && Array.isArray(outlines.features)
      ? outlines.features
      : [];
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
            weight: selected ? 3 : (pond?.flag === 'faster-than-sun' ? 2.4 : 1.6),
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

    const dense = visiblePonds.length > 60;
    const orderedPonds = [...visiblePonds].sort((a, b) => pondPriority(a) - pondPriority(b) || a.id.localeCompare(b.id));
    orderedPonds.forEach((pond) => {
      const meta = statusMeta(pond.status);
      const selected = pond.id === selectedId;
      const importanceClass = pond.status === 'dry'
        ? 'is-dry'
        : pond.status === 'critical'
          ? 'is-critical'
          : pond.flag === 'faster-than-sun'
            ? 'is-flagged'
            : '';
      const iconHtml = hasMatchingOutlines
        ? `<div class="pond-marker outline-backed ${dense ? 'dense' : ''} ${importanceClass} ${selected ? 'is-selected' : ''}" style="--pond-color:${meta.color}"><span class="pond-dot"></span><span class="pond-label">${pond.id}</span></div>`
        : `<div class="pond-marker ${dense ? 'dense' : ''} ${importanceClass} ${selected ? 'is-selected' : ''}" style="--pond-color:${meta.color}"><span class="pond-dot"></span><span class="pond-label">${pond.id}</span></div>`;
      const icon = L.divIcon({
        className: 'pond-marker-wrap',
        html: iconHtml,
        iconSize: [96, 28],
        iconAnchor: hasMatchingOutlines ? [4, 14] : [5, 14],
      });
      const marker = L.marker([pond.lat, pond.lon], {
        icon,
        title: `${pond.id} — ${meta.label}${pond.flag === 'faster-than-sun' ? ' — flagged for inspection' : ''}`,
        keyboard: true,
        zIndexOffset: pondPriority(pond) * 100 + (selected ? 10000 : 0),
      });
      marker.bindTooltip(`${pond.id} · ${meta.label}${pond.flag === 'faster-than-sun' ? ' · inspect' : ''}`, {
        direction: 'top',
        offset: [22, -12],
      });
      marker.on('click', () => onSelect(pond.id));
      marker.addTo(layersRef.current.markers);
    });
  }, [ponds, selectedId, onSelect, outlines, visibleStatuses]);

  return <div className="map-host" ref={hostRef} aria-label="Talaab pond map" />;
}
