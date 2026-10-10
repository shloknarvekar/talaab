import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import { fetchDivision, fetchDivisionOutlines } from '../api';
import { formatDate, formatRange, formatRatio, placeLabel, statusMeta } from '../utils';
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
    <div ref={el} className="division-map-canvas" aria-label="Map of Marathwada's districts coloured by dry and critical ponds" />
    <div className="division-map-legend"><span><i className="risk-high" />Most dry + critical</span><span><i className="risk-low" />Fewest</span></div>
  </div>;
}

function PondRow({ pond, onOpenPond, showRatio }) {
  const meta = statusMeta(pond.status);
  const where = [placeLabel(pond), pond.taluka && `${pond.taluka} taluka`, pond.district].filter(Boolean).join(' · ');
  const detail = showRatio ? `${formatRatio(pond.shrinkVsNeighbours)}× faster than neighbours`
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
  const [districtQuery, setDistrictQuery] = useState('');
  const [districtFilter, setDistrictFilter] = useState('all');
  const [talukaFilter, setTalukaFilter] = useState('all');
  const [retryVersion, setRetryVersion] = useState(0);
  const divisionId = division?.id;

  useEffect(() => {
    if (!divisionId) return undefined;
    let alive = true;
    setError('');
    fetchDivision(divisionId).then((d) => { if (alive) { setDoc(d); setSelected(d.districts?.[0]?.region ?? null); } })
      .catch((e) => alive && setError(e.message));
    fetchDivisionOutlines(divisionId).then((o) => alive && setOutlines(o)).catch(() => {});  // the page works without the map
    return () => { alive = false; };
  }, [divisionId, retryVersion]);

  if (!divisionId) return <section className="division-overview-page"><div className="division-error">No division summary is published yet.</div></section>;
  if (error) return <section className="division-overview-page"><div className="division-error" role="alert"><p>Could not load the division summary: {error}</p><button type="button" className="retry-action" onClick={() => { setDoc(null); setOutlines(null); setError(''); setRetryVersion((v) => v + 1); }}>Retry connection</button></div></section>;
  if (!doc) return <section className="division-overview-page"><div className="division-loading">Loading all Marathwada districts…</div></section>;

  const t = doc.totals;
  const ch = doc.change;
  const sel = doc.districts.find((d) => d.region === selected) ?? doc.districts[0];
  const selTalukas = (doc.allTalukas ?? []).filter((g) => g.region === sel?.region);
  const query = districtQuery.trim().toLowerCase();
  const visibleDistricts = doc.districts.map((d, apiIndex) => ({ ...d, apiRank: apiIndex + 1 })).filter((d) => {
    const matchesQuery = !query || `${d.name} ${d.nameMr ?? ''} ${d.region}`.toLowerCase().includes(query);
    const matchesFilter = districtFilter === 'all' || (districtFilter === 'dry' && d.dry > 0) || (districtFilter === 'critical' && d.critical > 0) || (districtFilter === 'flagged' && d.flagged > 0) || (districtFilter === 'watch' && d.watch > 0) || (districtFilter === 'unknown' && d.unknown > 0);
    return matchesQuery && matchesFilter;
  });
  const filterTalukas = (list) => list.filter((g) => talukaFilter === 'all' || (talukaFilter === 'priority' && (g.dry > 0 || g.critical > 0)) || (talukaFilter === 'watch' && g.watch > 0));
  const visibleSelTalukas = filterTalukas(selTalukas);
  const visibleDivisionTalukas = filterTalukas(doc.talukas);
  const focusDistrictFilter = (filter) => {
    setDistrictFilter(filter);
    const target = document.getElementById('division-ranked');
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    target?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
  };
  const name = doc.division.name.replace(/\s*\(.*\)$/, '');

  return <section className="division-overview-page">
    <div className="division-overview-hero">
      <div className="division-overview-heading">
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

    <div className="division-metric-mosaic" aria-label="Tap a summary count to filter the district ranking">
      <button type="button" className={`division-metric metric-paper ${districtFilter === 'all' ? 'is-active' : ''}`} aria-pressed={districtFilter === 'all'} onClick={() => focusDistrictFilter('all')}><span>PONDS TRACKED <i aria-hidden="true">↗</i></span><strong>{fmt(t.ponds)}</strong><small>Explore all districts</small></button>
      <button type="button" className={`division-metric metric-rose ${districtFilter === 'dry' ? 'is-active' : ''}`} aria-pressed={districtFilter === 'dry'} onClick={() => focusDistrictFilter('dry')}><span>DRY NOW <i aria-hidden="true">↗</i></span><strong>{fmt(t.dry)}</strong><small>Find districts with dry ponds</small></button>
      <button type="button" className={`division-metric metric-peach ${districtFilter === 'critical' ? 'is-active' : ''}`} aria-pressed={districtFilter === 'critical'} onClick={() => focusDistrictFilter('critical')}><span>CRITICAL <i aria-hidden="true">↗</i></span><strong>{fmt(t.critical)}</strong><small>Find critical ponds</small></button>
      <button type="button" className={`division-metric metric-lime ${districtFilter === 'watch' ? 'is-active' : ''}`} aria-pressed={districtFilter === 'watch'} onClick={() => focusDistrictFilter('watch')}><span>WATCH <i aria-hidden="true">↗</i></span><strong>{fmt(t.watch)}</strong><small>Review watch districts</small></button>
      <button type="button" className={`division-metric metric-lavender ${districtFilter === 'unknown' ? 'is-active' : ''}`} aria-pressed={districtFilter === 'unknown'} onClick={() => focusDistrictFilter('unknown')}><span>TOO EARLY TO SAY <i aria-hidden="true">↗</i></span><strong>{fmt(t.unknown)}</strong><small>Under 3 clear passes since the monsoon</small></button>
      <button type="button" className={`division-metric metric-mint ${districtFilter === 'flagged' ? 'is-active' : ''}`} aria-pressed={districtFilter === 'flagged'} onClick={() => focusDistrictFilter('flagged')}><span>FLAGGED TO INSPECT <i aria-hidden="true">↗</i></span><strong>{fmt(t.flagged)}</strong><small>Prioritize field checks</small></button>
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
      <div className="division-map-card" id="division-map">
        <div className="division-section-heading"><div><span className="division-kicker">WHERE</span><h3>Districts by <em>need</em></h3></div>
          <small>Coloured by dry + critical ponds</small></div>
        <DivisionMap outlines={outlines} districts={doc.districts} selected={sel?.region} onSelect={setSelected} onOpen={onOpenDistrict} />
        <div className="division-map-credit">{outlines?.credit ?? 'District boundaries © OpenStreetMap contributors'}</div>
      </div>

      <div className="division-ranked-card" id="division-ranked">
        <div className="division-section-heading"><div><span className="division-kicker">RANKED</span><h3>Most in need <em>first</em></h3></div>
          <small>Dry + critical, then watch, then the earliest likely dry date</small></div>
        <div className="division-ranking-tools">
          <label className="division-search"><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5"/><path d="m13 13 4 4"/></svg><span className="sr-only">Search districts</span><input type="search" value={districtQuery} onChange={(event) => setDistrictQuery(event.target.value)} placeholder="Find a district…" /></label>
          <div className="division-filter-chips" role="group" aria-label="Filter districts"><button type="button" className={districtFilter === 'all' ? 'active' : ''} onClick={() => setDistrictFilter('all')}>All <span>{doc.districts.length}</span></button><button type="button" className={districtFilter === 'dry' ? 'active' : ''} onClick={() => setDistrictFilter('dry')}>Dry</button><button type="button" className={districtFilter === 'critical' ? 'active' : ''} onClick={() => setDistrictFilter('critical')}>Critical</button><button type="button" className={districtFilter === 'watch' ? 'active' : ''} onClick={() => setDistrictFilter('watch')}>Watch</button><button type="button" className={districtFilter === 'flagged' ? 'active' : ''} onClick={() => setDistrictFilter('flagged')}>Flagged</button><button type="button" className={districtFilter === 'unknown' ? 'active' : ''} onClick={() => setDistrictFilter('unknown')}>Unknown</button></div>
          <span className="division-ranking-count">Showing <b>{visibleDistricts.length}</b> of {doc.districts.length}</span>
        </div>
        <div className="division-district-list">
          {visibleDistricts.map((d) => <div key={d.region} className={`division-district-row ${d.region === sel?.region ? 'is-selected' : ''}`} style={{ '--row-index': d.apiRank - 1 }}>
            <button type="button" className="division-district-select" onClick={() => setSelected(d.region)} aria-pressed={d.region === sel?.region}>
              <span className="division-rank">{String(d.apiRank).padStart(2, '0')}</span>
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
          {visibleDistricts.length === 0 && <div className="division-ranking-empty">No districts match this view. Clear the search or choose another filter.</div>}
        </div>
      </div>
    </div>

    <div className="division-taluka-section" id="division-talukas"><div className="division-taluka-toolbar"><div><span className="division-kicker">FIELD ROUTING</span><strong>Choose what to focus on</strong></div><div className="division-filter-chips" role="group" aria-label="Filter taluka rows"><button type="button" className={talukaFilter === 'all' ? 'active' : ''} onClick={() => setTalukaFilter('all')}>All</button><button type="button" className={talukaFilter === 'priority' ? 'active' : ''} onClick={() => setTalukaFilter('priority')}>Dry / critical</button><button type="button" className={talukaFilter === 'watch' ? 'active' : ''} onClick={() => setTalukaFilter('watch')}>Watch</button></div></div><div className="division-taluka-grid">
      <div className="division-taluka-panel">
        <div className="division-subheading"><strong>{sel?.name} talukas</strong><span>{selTalukas.length} talukas · most in need first</span></div>
        {visibleSelTalukas.length ? visibleSelTalukas.map((g, i) => <div key={g.name} className="division-taluka-row" style={{ '--row-index': i }}>
          <div><strong>{g.name}{g.nameMr ? ` · ${g.nameMr}` : ''}</strong><small>{g.ponds} ponds</small></div>
          <div className="division-taluka-counts"><span>{g.dry} dry</span><span>{g.critical} critical</span><span>{g.watch} watch</span></div>
        </div>) : <div className="division-muted">No talukas match this filter for the selected district.</div>}
      </div>
      <div className="division-taluka-panel top-talukas-panel">
        <div className="division-subheading"><strong>Talukas needing action first</strong><span>across all districts</span></div>
        {visibleDivisionTalukas.length ? visibleDivisionTalukas.map((g, i) => <div key={`${g.region}-${g.name}`} className="division-taluka-row" style={{ '--row-index': i }}>
          <div><strong>{g.name}</strong><small>{g.district} district</small></div>
          <div className="division-taluka-counts"><span>{g.dry} dry</span><span>{g.critical} critical</span><span>{g.watch} watch</span></div>
        </div>) : <div className="division-muted">No talukas match this filter across the division.</div>}
      </div>
    </div></div>

    <div className="division-ponds-section" id="division-urgent-ponds"><div className="division-ponds-grid">
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
