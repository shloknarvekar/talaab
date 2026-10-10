import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import { fetchDivision, fetchDivisionOutlines } from '../api';
import { formatDate, formatRange, placeLabel, statusMeta } from '../utils';
import './DivisionOverview.css';

// Divisional Commissioner's view: every live district of Marathwada in one page. Every number is copied from
// GET /division (written by the backend after each run); nothing is computed here except sorting for display.

const fmt = (n) => (n == null ? '—' : n.toLocaleString('en-IN'));
const signed = (n) => (n > 0 ? `+${n}` : `${n}`);
const need = (d) => d.dry + d.critical;

function DivisionMap({ outlines, districts, selected, onSelect, onOpen }) {
  const el = useRef(null);
  const map = useRef(null);
  const layer = useRef(null);
  const byRegion = useMemo(() => Object.fromEntries(districts.map((d) => [d.region, d])), [districts]);
  const worst = Math.max(1, ...districts.map(need));

  useEffect(() => {
    if (!el.current || map.current) return undefined;
    map.current = L.map(el.current, { zoomControl: false, attributionControl: false, scrollWheelZoom: false });
    L.control.zoom({ position: 'topright' }).addTo(map.current);  // the legend sits top-left
    return () => { map.current?.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    if (!map.current || !outlines) return;
    layer.current?.remove();
    layer.current = L.geoJSON(outlines, {
      style: (f) => {
        const d = byRegion[f.properties.region];
        const share = d ? need(d) / worst : 0;  // colour by dry + critical ponds, relative to the worst district
        const isSel = f.properties.region === selected;
        return { color: isSel ? '#203d2d' : '#ffffff', weight: isSel ? 3 : 1.5, fillOpacity: 0.78,
                 fillColor: share > 0.66 ? '#c96b56' : share > 0.33 ? '#dfa27e' : share > 0 ? '#c9d7a8' : '#83ad95' };
      },
      onEachFeature: (f, lyr) => {
        const d = byRegion[f.properties.region];
        if (d) lyr.bindTooltip(`<strong>${d.name}</strong><br>${d.dry} dry · ${d.critical} critical · ${d.watch} watch`,
          { className: 'division-map-tooltip', sticky: true });
        lyr.on('click', () => onSelect(f.properties.region));
        lyr.on('dblclick', () => onOpen(f.properties.region));
      },
    }).addTo(map.current);
    map.current.fitBounds(layer.current.getBounds(), { padding: [12, 12] });
  }, [outlines, byRegion, selected, worst, onSelect, onOpen]);

  return <div className="division-map-wrap">
    <div ref={el} className="division-map-canvas" role="img" aria-label="Map of Marathwada's districts coloured by dry and critical ponds" />
    <div className="division-map-legend"><span><i className="risk-high" />Most dry + critical</span><span><i className="risk-low" />Fewest</span></div>
  </div>;
}

function PondRow({ pond, onOpenPond, showRatio }) {
  const meta = statusMeta(pond.status);
  const where = [placeLabel(pond), pond.taluka && `${pond.taluka} taluka`, pond.district].filter(Boolean).join(' · ');
  const detail = showRatio ? `${pond.shrinkVsNeighbours}× faster than neighbours`
    : pond.status === 'dry' ? `${pond.areaNowHa} of ${pond.maxAreaHa} ha left` : pond.dryBy ? `dry ${formatRange(pond.dryBy)}` : '';
  return <button type="button" className="division-pond-row" onClick={() => onOpenPond({ region: pond.region, id: pond.id })}
    style={{ '--pond-color': meta.color, '--status-color': meta.color }}>
    <span className="division-pond-dot" />
    <span className="division-pond-main"><strong>{pond.id} · {pond.district}</strong>
      <small>{where}{pond.confidence === 'low' ? ' · low confidence' : ''}</small></span>
    <span className="division-pond-status">{showRatio ? 'INSPECT' : meta.label}</span>
    <span className="division-pond-dry">{detail}</span>
    <span className="division-chevron" aria-hidden="true">›</span>
  </button>;
}

export default function DivisionOverview({ division, onOpenDistrict, onOpenPond, onOpenPlan }) {
  const [doc, setDoc] = useState(null);
  const [outlines, setOutlines] = useState(null);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const divisionId = division?.id;

  useEffect(() => {
    if (!divisionId) return undefined;
    let alive = true;
    setError('');
    fetchDivision(divisionId).then((d) => { if (alive) { setDoc(d); setSelected(d.districts?.[0]?.region ?? null); } })
      .catch((e) => alive && setError(e.message));
    fetchDivisionOutlines(divisionId).then((o) => alive && setOutlines(o)).catch(() => {});  // the page works without the map
    return () => { alive = false; };
  }, [divisionId]);

  if (!divisionId) return <section className="division-overview-page"><div className="division-error">No division summary is published yet.</div></section>;
  if (error) return <section className="division-overview-page"><div className="division-error">Could not load the division summary: {error}</div></section>;
  if (!doc) return <section className="division-overview-page"><div className="division-loading">Loading all Marathwada districts…</div></section>;

  const t = doc.totals;
  const ch = doc.change;
  const sel = doc.districts.find((d) => d.region === selected) ?? doc.districts[0];
  const selTalukas = (doc.allTalukas ?? []).filter((g) => g.region === sel?.region);
  const name = doc.division.name.replace(/\s*\(.*\)$/, '');

  return <section className="division-overview-page">
    <div className="division-overview-hero">
      <div className="division-overview-heading">
        <span className="division-kicker">DIVISIONAL OVERVIEW · {t.districts} DROUGHT DISTRICTS · LIVE</span>
        <h2>{name}, <em>all at once.</em></h2>
        <p>Which districts and talukas need tankers first, the most urgent ponds and the ones worth an inspection,
          from every district's latest Sentinel-2 pass. Click a district to see its talukas; double-click it on the map to open its ponds.</p>
        <span className="division-asof">DATA AS OF {formatDate(doc.asOf, { day: 'numeric', month: 'short', year: 'numeric' }).toUpperCase()}</span>
      </div>
      <button type="button" className="division-plan-cta"
        onClick={() => onOpenPlan({ regionId: divisionId, asOf: doc.asOf, regionName: doc.division.name })}>
        Division plan (English / मराठी) <span aria-hidden="true">→</span>
      </button>
    </div>

    <div className="division-metric-mosaic">
      <div className="division-metric metric-paper"><span>PONDS TRACKED</span><strong>{fmt(t.ponds)}</strong></div>
      <div className="division-metric metric-rose"><span>DRY NOW</span><strong>{fmt(t.dry)}</strong></div>
      <div className="division-metric metric-peach"><span>CRITICAL</span><strong>{fmt(t.critical)}</strong></div>
      <div className="division-metric metric-lime"><span>WATCH</span><strong>{fmt(t.watch)}</strong></div>
      <div className="division-metric metric-lavender"><span>TOO EARLY TO SAY</span><strong>{fmt(t.unknown)}</strong></div>
      <div className="division-metric metric-mint"><span>FLAGGED TO INSPECT</span><strong>{fmt(t.flagged)}</strong></div>
    </div>

    {ch && <div className="division-change-strip">
      <div><span className="division-kicker">SINCE THE LAST RUN</span><strong>Change since {formatDate(ch.since, { day: 'numeric', month: 'short' })}</strong></div>
      <div className="division-main-change">
        <span className="change-critical">critical <b>{signed(ch.critical)}</b></span>
        <span>dry <b>{signed(ch.dry)}</b></span>
        {ch.unknown < 0 && <span className="change-unknown">hidden ponds now forecastable <b>{-ch.unknown}</b></span>}
        <small>Much of a rise in critical ponds is ponds that just became visible enough to forecast.</small>
      </div>
      <div className="division-secondary-changes"><span>watch <b>{signed(ch.watch)}</b></span><span>flagged <b>{signed(ch.flagged)}</b></span>
        <span>{ch.districts} of {t.districts} districts compared</span></div>
    </div>}

    <div className="division-overview-grid">
      <div className="division-map-card">
        <div className="division-section-heading"><div><span className="division-kicker">WHERE</span><h3>Districts by <em>need</em></h3></div>
          <small>Coloured by dry + critical ponds</small></div>
        <DivisionMap outlines={outlines} districts={doc.districts} selected={sel?.region} onSelect={setSelected} onOpen={onOpenDistrict} />
        <div className="division-map-credit">{outlines?.credit ?? 'District boundaries © OpenStreetMap contributors'}</div>
      </div>

      <div className="division-ranked-card">
        <div className="division-section-heading"><div><span className="division-kicker">RANKED</span><h3>Most in need <em>first</em></h3></div>
          <small>Dry + critical, then watch, then the earliest likely dry date</small></div>
        <div className="division-district-list">
          {doc.districts.map((d, i) => <div key={d.region} className={`division-district-row ${d.region === sel?.region ? 'is-selected' : ''}`}>
            <button type="button" className="division-district-select" onClick={() => setSelected(d.region)} aria-pressed={d.region === sel?.region}>
              <span className="division-rank">{String(i + 1).padStart(2, '0')}</span>
              <span className="division-district-name"><strong>{d.name}{d.nameMr ? ` · ${d.nameMr}` : ''}</strong>
                <small>{fmt(d.ponds)} ponds · {d.talukas} talukas</small></span>
              <span className="division-district-risk"><b>{d.dry}</b><small>dry</small><b>{d.critical}</b><small>critical</small></span>
              <span className="division-chevron" aria-hidden="true">›</span>
            </button>
            {d.region === sel?.region && <div className="division-row-details">
              {d.watch} watch · {d.unknown} too early · {d.flagged} flagged
              {d.earliestLikelyDry && <> · first likely dry {formatDate(d.earliestLikelyDry, { day: 'numeric', month: 'short' })}</>}
              {d.change && <div className="division-change-pair"><span className="change-critical">critical <b>{signed(d.change.critical)}</b></span>
                <span>dry <b>{signed(d.change.dry)}</b></span><small>since {formatDate(d.change.since, { day: 'numeric', month: 'short' })}</small></div>}
              <button type="button" className="division-open-map" onClick={() => onOpenDistrict(d.region)}>Open {d.name}'s pond map <span aria-hidden="true">→</span></button>
            </div>}
          </div>)}
        </div>
      </div>
    </div>

    <div className="division-taluka-section"><div className="division-taluka-grid">
      <div className="division-taluka-panel">
        <div className="division-subheading"><strong>{sel?.name} talukas</strong><span>{selTalukas.length} talukas · most in need first</span></div>
        {selTalukas.length ? selTalukas.map((g) => <div key={g.name} className="division-taluka-row">
          <div><strong>{g.name}{g.nameMr ? ` · ${g.nameMr}` : ''}</strong><small>{g.ponds} ponds</small></div>
          <div className="division-taluka-counts"><span>{g.dry} dry</span><span>{g.critical} critical</span><span>{g.watch} watch</span></div>
        </div>) : <div className="division-muted">No taluka breakdown for this district yet.</div>}
      </div>
      <div className="division-taluka-panel top-talukas-panel">
        <div className="division-subheading"><strong>Talukas needing action first</strong><span>across all districts</span></div>
        {doc.talukas.length ? doc.talukas.map((g) => <div key={`${g.region}-${g.name}`} className="division-taluka-row">
          <div><strong>{g.name}</strong><small>{g.district} district</small></div>
          <div className="division-taluka-counts"><span>{g.dry} dry</span><span>{g.critical} critical</span><span>{g.watch} watch</span></div>
        </div>) : <div className="division-muted">No taluka has dry, critical or watch ponds.</div>}
      </div>
    </div></div>

    <div className="division-ponds-section"><div className="division-ponds-grid">
      <div className="division-ponds-panel">
        <div className="division-subheading"><strong>Most urgent ponds</strong><span>dry first, then critical; trusted countdowns first</span></div>
        {doc.urgentPonds.length ? doc.urgentPonds.map((p) => <PondRow key={`${p.region}-${p.id}`} pond={p} onOpenPond={onOpenPond} />)
          : <div className="division-muted">No dry, critical or watch ponds.</div>}
      </div>
      <div className="division-ponds-panel inspect-panel">
        <div className="division-subheading"><strong>Inspect first</strong><span>shrinking faster than the sun: suggests pumping, not proof</span></div>
        {doc.inspect.length ? doc.inspect.map((p) => <PondRow key={`${p.region}-${p.id}`} pond={p} onOpenPond={onOpenPond} showRatio />)
          : <div className="division-muted">No pond is flagged.</div>}
      </div>
    </div></div>

    <div className="division-data-credit">Sentinel-2 L2A (Copernicus) via AWS Open Data · weather Open-Meteo (CC BY 4.0) ·
      village, taluka and district boundaries © OpenStreetMap contributors (ODbL). Counts come from each district's latest published run.</div>
  </section>;
}
