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

// Smooth raster basemaps: load tiles once a zoom settles (not on every animation frame) and keep a ring of
// off-screen tiles so short pans never show blank squares.
const TILE_OPTIONS = { updateWhenZooming: false, updateWhenIdle: true, keepBuffer: 4 };
const darkMatter = () => L.layerGroup([
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19, maxNativeZoom: 16, ...TILE_OPTIONS, attribution: 'Tiles &copy; Esri — Esri, HERE, Garmin, &copy; OpenStreetMap contributors',
  }),
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19, maxNativeZoom: 16, ...TILE_OPTIONS,
  }),
]);

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

  // Basemaps are raster tiles only: Leaflet moves them with the pond markers in one transform, so zooming stays
  // smooth on any laptop and the map can't lag behind the dots (a WebGL vector style did both on weak graphics).
  // Map view: Esri Dark Gray Canvas (base + place labels). Satellite: Amazon Location (key injected at build by
  // backend/scripts/deploy_web.py, locked to our site and localhost), else Esri World Imagery.
  useEffect(() => {
    if (!mapRef.current) return undefined;
    const awsKey = import.meta.env.VITE_AWS_MAPS_KEY?.trim();
    const satelliteTiles = awsKey
      ? L.tileLayer(`https://maps.geo.us-west-2.amazonaws.com/v2/tiles/raster.satellite/{z}/{x}/{y}?key=${encodeURIComponent(awsKey)}`, {
          maxZoom: 18, ...TILE_OPTIONS,
          attribution: '&copy; <a href="https://docs.aws.amazon.com/location/latest/developerguide/data-attribution.html">AWS</a>, '
            + '<a href="https://legal.here.com/en-gb/terms/general-content-supplier-terms-and-notices">HERE</a>',
        })
      : L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
          maxZoom: 19, ...TILE_OPTIONS, attribution: 'Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics',
        });
    layersRef.current.tiles?.remove();
    layersRef.current.tiles = (satellite ? satelliteTiles : darkMatter()).addTo(mapRef.current);
    return undefined;
  }, [satellite]);

  useEffect(() => {
    if (!mapRef.current || !region?.bbox) return;
    const [minLon, minLat, maxLon, maxLat] = region.bbox;
    mapRef.current.fitBounds([[minLat, minLon], [maxLat, maxLon]], { padding: [28, 28], animate: false });
  }, [region]);

  // A deliberate selection (from the list or a marker) brings the pond into view.
  // The request counter prevents normal date/data refreshes from repeatedly zooming.
  useEffect(() => {
    if (!mapRef.current || !selectedId || !focusRequest || focusRequest === lastFocusRequestRef.current) return;
    const pond = ponds.find((item) => item.id === selectedId);
    lastFocusRequestRef.current = focusRequest;
    if (!pond || !Number.isFinite(Number(pond.lat)) || !Number.isFinite(Number(pond.lon))) return;
    const map = mapRef.current;
    // Jump, don't fly: a multi-level fly-over stretches the marker canvas into giant blurred dots until it lands.
    const target = [Number(pond.lat), Number(pond.lon)];
    const zoom = Math.min(16, Math.max(13, map.getZoom()));
    if (Math.abs(zoom - map.getZoom()) < 0.5) map.panTo(target, { animate: true, duration: 0.3 });
    else map.setView(target, zoom, { animate: false });
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
      color: selected ? '#ffffff' : flagged ? '#fbbf24' : 'rgba(244,247,245,0.85)', weight: selected ? 3 : flagged ? 2.4 : 1.4,
    };
  };

  const refreshLabels = () => {
    const map = mapRef.current; const b = built.current;
    if (!map || !b.labels) return;
    // Outlines are invisible specks below zoom 12 but cost the most to redraw: draw them only when they show.
    // Only outlines near the view are on the map: jumping to street zoom then draws a dozen shapes, not ~400.
    if (b.outlineLayer) {
      const want = map.getZoom() >= 12;
      if (want && !map.hasLayer(b.outlineLayer)) b.outlineLayer.addTo(map);
      else if (!want && map.hasLayer(b.outlineLayer)) b.outlineLayer.remove();
      if (want) {
        const near = map.getBounds().pad(0.5);
        const status = new Map(latest.current.ponds.map((p) => [p.id, p.status]));
        for (const [id, o] of b.outlines) {
          const keep = latest.current.visible.has(status.get(id)) && near.intersects(o.getBounds());
          if (keep && !b.outlineLayer.hasLayer(o)) b.outlineLayer.addLayer(o);
          else if (!keep && b.outlineLayer.hasLayer(o)) b.outlineLayer.removeLayer(o);
        }
      }
    }
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
    b.renderer = b.renderer || L.canvas({ padding: 0.2, tolerance: L.Browser.mobile ? 10 : 4 });
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
      });
      b.outlineLayer.clearLayers();  // refreshLabels adds back only the outlines near the view
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
      if (o) {  // style only; which outlines are on the map is decided by refreshLabels (zoom, view, filter)
        const color = statusMeta(pond.status).color;
        const st = { color, fillColor: color, opacity: selected ? 1 : 0.92, fillOpacity: selected ? 0.32 : 0.17, weight: selected ? 3 : pond.flag === 'faster-than-sun' ? 2.4 : 1.6 };
        if (o._map) o.setStyle(st); else L.Util.setOptions(o, st);
      }
    }
    refreshRef.current = refreshLabels;
    refreshLabels();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ponds, selectedId, visibleStatuses, outlines]);

  return <div className="map-host" ref={hostRef} aria-label="Talaab pond map" />;
}
