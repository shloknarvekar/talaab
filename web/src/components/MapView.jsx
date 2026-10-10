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

  // Basemaps. With an Amazon Location key (set at build time by backend/scripts/deploy_web.py; it only works
  // from our site and localhost) the map uses AWS: the Monochrome Dark vector style (MapLibre, loaded on demand)
  // and AWS satellite tiles. Without one: CARTO Dark Matter if configured, else OpenStreetMap, and Esri satellite.
  useEffect(() => {
    if (!mapRef.current) return undefined;
    const awsKey = import.meta.env.VITE_AWS_MAPS_KEY?.trim();
    if (awsKey) {
      const aws = 'https://maps.geo.us-west-2.amazonaws.com/v2';
      const attribution = '&copy; <a href="https://docs.aws.amazon.com/location/latest/developerguide/data-attribution.html">AWS</a>, '
        + '<a href="https://legal.here.com/en-gb/terms/general-content-supplier-terms-and-notices">HERE</a>';
      let cancelled = false;
      const show = (layer) => {
        if (cancelled || !mapRef.current) return;
        layersRef.current.tiles?.remove();
        layersRef.current.tiles = layer.addTo(mapRef.current);
      };
      if (satellite) {
        show(L.tileLayer(`${aws}/tiles/raster.satellite/{z}/{x}/{y}?key=${encodeURIComponent(awsKey)}`, { maxZoom: 18, attribution }));
      } else {
        Promise.all([import('maplibre-gl'), import('maplibre-gl/dist/maplibre-gl.css')])
          .then(([maplibre]) => {
            maplibre.setWorkerUrl('/maplibre/maplibre-gl-worker.mjs');  // copied there by vite.config.js
            return import('@maplibre/maplibre-gl-leaflet');
          })
          .then(() => show(L.maplibreGL({
            style: `${aws}/styles/Monochrome/descriptor?key=${encodeURIComponent(awsKey)}&color-scheme=Dark`,
            attribution,
            // The vector basemap redraws on every zoom frame: cap its pixel density and skip label fades so zooming
            // stays smooth on laptops with integrated graphics (pond markers stay sharp; they're drawn by Leaflet).
            pixelRatio: Math.min(window.devicePixelRatio || 1, 1.25),
            fadeDuration: 0,
          })))
          .catch(() => show(L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19, subdomains: 'abc', attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
          })));
      }
      return () => { cancelled = true; };
    }
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
    return undefined;
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

  // Markers and outlines are built once per set of ponds (a region) and drawn on the map's single canvas; dates,
  // filters and selection only restyle them. Rebuilding ~650 DOM markers with drop-shadows on every change is
  // what made zooming, scrubbing the timeline and selecting a pond freeze for up to 1.5 s.
  const built = useRef({ key: '', markers: new Map(), outlines: new Map(), outlineLayer: null, labels: null, renderer: null });
  const latest = useRef({ ponds: [], visible: new Set(), selectedId: null, onSelect });
  const refreshRef = useRef(() => {});
  latest.current.onSelect = onSelect;

  const styleFor = (pond, visible, selected, dense) => {
    const meta = statusMeta(pond.status);
    const urgent = pond.status === 'dry' || pond.status === 'critical';
    const flagged = pond.flag === 'faster-than-sun';
    const base = urgent ? 7 : flagged ? 6 : pond.status === 'watch' ? 5.5 : pond.status === 'unknown' ? 4 : 5;
    return {
      radius: visible ? (selected ? base + 3 : dense ? base - 0.5 : base) : 0,
      fillColor: meta.color, fillOpacity: visible ? 0.92 : 0, opacity: visible ? 1 : 0,
      color: selected ? '#ffffff' : flagged ? '#fbbf24' : '#0b1410', weight: selected ? 3 : flagged ? 2.4 : 1.4,
    };
  };

  const refreshLabels = () => {
    const map = mapRef.current; const b = built.current;
    if (!map || !b.labels) return;
    b.labels.clearLayers();
    if (map.getZoom() < 13) return;
    const bounds = map.getBounds().pad(0.05);
    let shown = 0;
    for (const pond of latest.current.ponds) {
      if (shown >= 80) break;
      if (!latest.current.visible.has(pond.status) || !bounds.contains([pond.lat, pond.lon])) continue;
      L.tooltip({ permanent: true, direction: 'right', offset: [8, 0], className: `pond-map-label status-${pond.status}`, interactive: false })
        .setLatLng([pond.lat, pond.lon]).setContent(pond.id).addTo(b.labels);
      shown += 1;
    }
  };

  // Build: when the region's ponds or outlines change.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !Array.isArray(ponds)) return;
    const b = built.current;
    const key = `${ponds.length}:${ponds[0]?.id ?? ''}:${ponds.at(-1)?.id ?? ''}:${outlines?.features?.length ?? 0}`;
    if (key === b.key) return;
    b.key = key;
    layersRef.current.markers.clearLayers();
    b.outlineLayer?.remove(); b.outlineLayer = null;
    b.labels?.remove();
    b.markers = new Map(); b.outlines = new Map();
    b.renderer = b.renderer || L.canvas({ padding: 0.4, tolerance: L.Browser.mobile ? 10 : 4 });
    b.labels = L.layerGroup().addTo(map);

    const features = outlines?.type === 'FeatureCollection' && Array.isArray(outlines.features) ? outlines.features : [];
    const ids = new Set(ponds.map((p) => p.id));
    const own = features.filter((f) => ids.has(f?.properties?.id ?? f?.properties?.pondId) && f?.geometry);
    if (own.length) {
      b.outlineLayer = L.geoJSON({ type: 'FeatureCollection', features: own }, {
        renderer: b.renderer,
        style: { weight: 1.6, opacity: 0.92, fillOpacity: 0.17, lineCap: 'round', lineJoin: 'round' },
        onEachFeature: (feature, layer) => {
          const id = feature?.properties?.id ?? feature?.properties?.pondId;
          b.outlines.set(id, layer);
          layer.on('click', () => latest.current.onSelect(id));
          layer.bindTooltip(() => { const p = latest.current.ponds.find((x) => x.id === id); return `${id} · ${statusMeta(p?.status).label}`; }, { sticky: true, className: 'pond-outline-tooltip' });
        },
      }).addTo(map);
    }
    // Most urgent drawn last, so they sit on top of crowded areas.
    [...ponds].sort((a, b2) => pondPriority(a) - pondPriority(b2) || a.id.localeCompare(b2.id)).forEach((pond) => {
      const m = L.circleMarker([pond.lat, pond.lon], { renderer: b.renderer, bubblingMouseEvents: false });
      m.on('click', () => latest.current.onSelect(pond.id));
      m.bindTooltip(() => { const p = latest.current.ponds.find((x) => x.id === pond.id) ?? pond; return `${p.id} · ${statusMeta(p.status).label}${p.flag === 'faster-than-sun' ? ' · inspect' : ''}`; }, { direction: 'top', offset: [0, -8] });
      m.addTo(layersRef.current.markers);
      b.markers.set(pond.id, m);
    });
    if (!b.labelHandler) { b.labelHandler = () => refreshRef.current(); map.on('zoomend moveend', b.labelHandler); }  // one stable listener
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ponds, outlines]);

  // Restyle: every date, filter or selection change (cheap: canvas repaint, no DOM churn).
  useEffect(() => {
    const b = built.current;
    if (!mapRef.current || !Array.isArray(ponds) || !b.markers.size && !b.outlines.size) return;
    const visible = new Set(visibleStatuses);
    latest.current = { ...latest.current, ponds, visible, selectedId };
    const dense = ponds.filter((p) => visible.has(p.status)).length > 60;
    for (const pond of ponds) {
      const on = visible.has(pond.status);
      const selected = pond.id === selectedId;
      const m = b.markers.get(pond.id);
      if (m) {  // hidden ponds leave the map entirely, so they can't be clicked
        const group = layersRef.current.markers;
        if (!on) { if (group.hasLayer(m)) group.removeLayer(m); }
        else {
          if (!group.hasLayer(m)) group.addLayer(m);
          const st = styleFor(pond, true, selected, dense);
          m.setStyle(st); m.setRadius(st.radius);
          if (selected) m.bringToFront();
        }
      }
      const o = b.outlines.get(pond.id);
      if (o && b.outlineLayer) {
        if (!on) { if (b.outlineLayer.hasLayer(o)) b.outlineLayer.removeLayer(o); }
        else {
          if (!b.outlineLayer.hasLayer(o)) b.outlineLayer.addLayer(o);
          const color = statusMeta(pond.status).color;
          o.setStyle({ color, fillColor: color, opacity: selected ? 1 : 0.92, fillOpacity: selected ? 0.32 : 0.17, weight: selected ? 3 : pond.flag === 'faster-than-sun' ? 2.4 : 1.6 });
        }
      }
    }
    refreshRef.current = refreshLabels;
    refreshLabels();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ponds, selectedId, visibleStatuses, outlines]);

  return <div className="map-host" ref={hostRef} aria-label="Talaab pond map" />;
}
