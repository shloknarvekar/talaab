import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AreaChart as ReAreaChart, Area, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Scatter, ReferenceLine } from 'recharts';
import MapView from './components/MapView';
import PondList from './components/PondList';
import TalaabLandingPage from './components/ui/TalaabLandingPage';
import DivisionOverview from './components/DivisionOverview';

// Tabs opened less often load on demand: the plan needs the Markdown renderer, About the portfolio artwork.
const PlanTab = lazy(() => import('./components/PlanTab'));
const AccuracyTab = lazy(() => import('./components/AccuracyTab'));
const AboutTab = lazy(() => import('./components/AboutTab'));
import { fetchAlerts, fetchPonds, fetchRegions, imageryBase } from './api';
import { STATUS_KEYS, addDays, formatDate, formatRange, placeLabel, sortPonds, statusMeta } from './utils';

const REPLAY_REGION = 'latur-2024';
const BASE_PATH = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');
const P003_TIMELAPSE_SRC = `${BASE_PATH}/imagery/latur-2024/P003-timelapse.gif`;

function Stat({ label, value, tone }) {
  return <div className={`stat ${tone || ''}`}><span>{label}</span><strong>{value}</strong></div>;
}

function regionLabel(region) {
  const district = region.id.includes('district');
  if (district && !region.id.startsWith('latur')) {
    return `${region.name.split(' district')[0]} district`;  // the other Marathwada districts, by name
  }
  if (region.mode === 'live') return district ? 'Whole district today' : 'Latur today';
  return district ? 'Whole district 2024' : 'Latur 2024';
}

function alertDate(alert) {
  const value = alert?.date ?? alert?.asOf ?? alert?.createdAt ?? alert?.timestamp ?? alert?.at;
  if (!value) return '';
  const parsed = String(value);
  return parsed.length >= 10 ? parsed.slice(0, 10) : parsed;
}

function alertPondId(alert) {
  return alert?.pondId ?? alert?.pond_id ?? alert?.id ?? alert?.pond ?? '';
}

function alertMessage(alert) {
  return alert?.message ?? alert?.summary ?? alert?.description ?? alert?.event ?? alert?.type ?? 'Pond risk changed';
}

// Live maps open with 'too early' ponds hidden (often a third of all dots); the legend brings them back.
const defaultStatuses = (mode) => (mode === 'live' ? STATUS_KEYS.filter((s) => s !== 'unknown') : STATUS_KEYS);

export default function App() {
  const [regions, setRegions] = useState([]);
  const [divisions, setDivisions] = useState([]);
  const [regionId, setRegionId] = useState(null);
  const [planScope, setPlanScope] = useState(null);
  const [dateIndex, setDateIndex] = useState(0);
  const [data, setData] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [satellite, setSatellite] = useState(false);
  const [visibleStatuses, setVisibleStatuses] = useState(STATUS_KEYS);
  const [focusRequest, setFocusRequest] = useState(0);
  const [talukaFilter, setTalukaFilter] = useState('');
  const [activeTab, setActiveTab] = useState('home');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [alerts, setAlerts] = useState([]);
  const [imageryIndex, setImageryIndex] = useState(null);
  const [imageryRegion, setImageryRegion] = useState(null);
  const [outlines, setOutlines] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [mobileSheetExpanded, setMobileSheetExpanded] = useState(false);
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const requestId = useRef(0);
  const pendingPondRef = useRef(null);
  const sheetTouchStart = useRef(null);

  // Warm the 1 MB map engine while the visitor reads the landing page, so opening the map doesn't stall on it.
  useEffect(() => {
    if (!import.meta.env.VITE_AWS_MAPS_KEY) return undefined;
    const warm = () => { import('maplibre-gl').then(() => import('@maplibre/maplibre-gl-leaflet')).catch(() => {}); };
    const id = 'requestIdleCallback' in window ? window.requestIdleCallback(warm, { timeout: 4000 }) : window.setTimeout(warm, 2500);
    return () => ('cancelIdleCallback' in window ? window.cancelIdleCallback(id) : window.clearTimeout(id));
  }, []);

  // On narrow screens the region chips scroll sideways: keep the selected one in view.
  useEffect(() => {
    document.querySelector('.region-switch button.active')?.scrollIntoView({ block: 'nearest', inline: 'center' });
  }, [regionId]);

  useEffect(() => {
    fetchRegions()
      .then(({ regions: list, divisions: divisionList = [] }) => {
        if (!list.length) throw new Error('No published regions yet.');
        setRegions(list);
        setDivisions(divisionList);
        const live = list.filter((r) => r.mode === 'live');
        const first = live.find((r) => r.id.includes('district')) ?? live[0] ?? list[0];
        setRegionId(first.id);
        setDateIndex(first.dates.length - 1);
        setVisibleStatuses(defaultStatuses(first.mode));
      })
      .catch((err) => { setError(`Could not reach the Talaab API: ${err.message}`); setLoading(false); });
  }, []);

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReducedMotion(query.matches);
    update();
    query.addEventListener?.('change', update);
    return () => query.removeEventListener?.('change', update);
  }, []);

  const region = regions.find((r) => r.id === regionId);
  const dates = region?.dates ?? [];
  const asOf = dates[dateIndex];

  useEffect(() => {
    if (!regionId) return undefined;
    let active = true;
    setAlerts([]);
    fetchAlerts(regionId)
      .then((items) => { if (active) setAlerts(Array.isArray(items) ? items : []); })
      .catch(() => { if (active) setAlerts([]); });
    return () => { active = false; };
  }, [regionId]);

  // Contract-driven static imagery. Missing index.json means no imagery UI and no visible error.
  useEffect(() => {
    if (!regionId) return undefined;
    let active = true;
    setImageryIndex(null);
    setImageryRegion(null);
    setOutlines(null);
    // Only this region's own imagery: pond ids are per region (district P001 is not box P001), so
    // borrowing another region's thumbnails would show the wrong pond.
    const candidates = [regionId];
    (async () => {
      for (const key of [...new Set(candidates)]) {
        try {
          const indexResponse = await fetch(`${imageryBase(key)}/${encodeURIComponent(key)}/index.json`);
          if (!indexResponse.ok) continue;
          const index = await indexResponse.json();
          let geojson = null;
          try {
            const outlineResponse = await fetch(`${imageryBase(key)}/${encodeURIComponent(key)}/outlines.geojson`);
            if (outlineResponse.ok) geojson = await outlineResponse.json();
          } catch { /* thumbnails can exist before outlines arrive */ }
          if (active) {
            setImageryIndex(index && typeof index === 'object' ? index : null);
            setImageryRegion(key);
            setOutlines(geojson?.type === 'FeatureCollection' ? geojson : null);
          }
          return;
        } catch { /* hide imagery silently until Nikhil's files land */ }
      }
    })();
    return () => { active = false; };
  }, [regionId]);

  useEffect(() => {
    if (!regionId || !asOf) return;
    const id = ++requestId.current;
    setLoading(true);
    fetchPonds(regionId, asOf)
      .then((payload) => {
        if (id !== requestId.current) return;
        setData(payload);
        setError('');
        const pendingPond = pendingPondRef.current;
        if (pendingPond?.regionId === regionId && payload.ponds.some((pond) => pond.id === pendingPond.pondId)) {
          setSelectedId(pendingPond.pondId);
          setFocusRequest((current) => current + 1);
          pendingPondRef.current = null;
        } else {
          setSelectedId((current) => (payload.ponds.some((pond) => pond.id === current) ? current : sortPonds(payload.ponds)[0]?.id));
        }
      })
      .catch((err) => id === requestId.current && setError(err.message))
      .finally(() => id === requestId.current && setLoading(false));
  }, [regionId, asOf]);

  // A replay advances exactly one published API date per step. It never invents intermediate dates.
  useEffect(() => {
    if (!playing) return undefined;
    if (reducedMotion || region?.mode !== 'replay' || dateIndex >= dates.length - 1) {
      setPlaying(false);
      return undefined;
    }
    const timer = window.setTimeout(() => setDateIndex((index) => Math.min(index + 1, dates.length - 1)), 800);
    return () => window.clearTimeout(timer);
  }, [playing, reducedMotion, region?.mode, dateIndex, dates.length]);

  const switchRegion = (id, pondId = null) => {
    const next = regions.find((r) => r.id === id);
    if (!next) return;
    setPlanScope(null);
    if (id === regionId) {
      pendingPondRef.current = null;
      if (pondId) { setSelectedId(pondId); setFocusRequest((current) => current + 1); }
      return;
    }
    pendingPondRef.current = pondId ? { regionId: id, pondId } : null;
    setPlaying(false);
    setRegionId(id);
    setDateIndex(next.dates.length - 1);
    setTalukaFilter('');
    setVisibleStatuses(defaultStatuses(next.mode));
    setMobileDetailOpen(false);
  };

  const ponds = useMemo(() => sortPonds(data?.ponds ?? []), [data]);
  const talukas = data?.talukas ?? [];
  const filteredPonds = useMemo(
    () => talukaFilter ? ponds.filter((pond) => pond.taluka === talukaFilter) : ponds,
    [ponds, talukaFilter],
  );
  const selected = ponds.find((pond) => pond.id === selectedId) ?? ponds[0];
  const counts = useMemo(() => ponds.reduce((acc, pond) => ({ ...acc, [pond.status]: (acc[pond.status] || 0) + 1 }), {}), [ponds]);
  const isLive = region?.mode === 'live';
  const otherDistricts = regions.filter((r) => !r.id.startsWith('latur'));  // rest of Marathwada, in a dropdown
  const marathwadaDivision = divisions.find((item) => item.id === 'marathwada-2026') ?? divisions[0];
  const criticalPonds = ponds.filter((pond) => pond.status === 'critical');
  const flaggedCount = ponds.filter((pond) => pond.flag === 'faster-than-sun').length;
  const soonestCritical = [...criticalPonds].sort((a, b) => (a.daysLeft?.likely ?? Infinity) - (b.daysLeft?.likely ?? Infinity))[0];
  const headline = criticalPonds.length === 0
    ? 'No pond is currently marked critical.'
    : soonestCritical?.daysLeft?.likely <= 7
      ? `${criticalPonds.length} critical pond${criticalPonds.length === 1 ? '' : 's'}; one may dry within a week.`
      : `${criticalPonds.length} pond${criticalPonds.length === 1 ? ' is' : 's are'} at critical risk.`;
  const visibleAlerts = useMemo(() => alerts
    .filter((alert) => !alertDate(alert) || !asOf || alertDate(alert) <= asOf)
    .sort((a, b) => alertDate(b).localeCompare(alertDate(a)))
    .slice(0, 5), [alerts, asOf]);
  const openPondFromList = useCallback((id) => {
    setSelectedId(id);
    const pond = ponds.find((item) => item.id === id);
    if (pond) setVisibleStatuses((current) => current.includes(pond.status) ? current : [...current, pond.status]);
    setFocusRequest((current) => current + 1);
    // The map-first layout opens details as a floating inspector on every screen size.
    setMobileDetailOpen(true);
  }, [ponds]);

  const selectPondFromMap = useCallback((id) => {
    setSelectedId(id);
    // Reveal the inspector only after a deliberate map selection.
    setMobileDetailOpen(true);
  }, []);

  const toggleMapStatus = useCallback((status) => {
    setVisibleStatuses((current) => {
      if (current.includes(status)) {
        const remaining = current.filter((item) => item !== status);
        return remaining.length ? remaining : STATUS_KEYS;
      }
      return STATUS_KEYS.filter((item) => item === status || current.includes(item));
    });
  }, []);

  const toggleTimelinePlayback = () => {
    if (playing) {
      setPlaying(false);
      return;
    }
    if (dateIndex >= dates.length - 1) setDateIndex(0);
    setPlaying(true);
  };

  const changeTaluka = useCallback((event) => {
    const nextTaluka = event.target.value;
    setTalukaFilter(nextTaluka);
    const firstMatch = nextTaluka ? ponds.find((pond) => pond.taluka === nextTaluka) : ponds[0];
    if (firstMatch) openPondFromList(firstMatch.id);
  }, [openPondFromList, ponds]);

  if (activeTab === 'home') {
    return <TalaabLandingPage onExplore={() => setActiveTab('ponds')} onOpenView={setActiveTab} />;
  }

  if (!data) {
    return <main className="loading-screen"><div className="loading-mark">तालाब</div><p>{error || 'Loading pond intelligence…'}</p></main>;
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="app-primary-nav">
          <button
            type="button"
            className="brand-lockup brand-home-button"
            onClick={() => setActiveTab('home')}
            aria-label="Return to Talaab website home"
          >
            <div className="brand-mark" aria-hidden="true">जल</div>
            <div>
              <h1>Talaab</h1>
              <p>Water intelligence, with honest uncertainty.</p>
            </div>
          </button>
          <nav className="tab-group" aria-label="Main navigation">
            {[
              ['ponds', 'Pond map'],
              ['plan', 'Plan'],
              ['accuracy', 'Accuracy'],
              ['about', 'About'],
            ].map(([key, label]) => (
              <button
                key={key}
                className={`tab-button ${activeTab === key ? 'active' : ''}`}
                aria-current={activeTab === key ? 'page' : undefined}
                onClick={() => { setPlanScope(null); setActiveTab(key); }}
              >
                {label}
              </button>
            ))}
          </nav>
        </div>

        <div className={`app-context-row ${['accuracy', 'about'].includes(activeTab) ? 'is-hidden' : ''}`}>
          <div className="region-block">

            <div className="region-switch" role="group" aria-label="Choose region">
              {/* Grouped by what the viewer is looking at: today's live monitoring, then the 2024 backtest replay. */}
              <span className="region-group-label">Live</span>
              {marathwadaDivision && <button type="button" data-region={marathwadaDivision.id} className={`division-launch-button ${activeTab === 'division' ? 'active' : ''}`} onClick={() => { setPlaying(false); setPlanScope(null); setActiveTab('division'); }} aria-pressed={activeTab === 'division'}>Marathwada · all {marathwadaDivision.members?.length ?? 8} districts</button>}
              {regions.filter((r) => r.id === 'latur-district-2026').map((r) => (
                <button key={r.id} data-region={r.id} aria-pressed={r.id === regionId && activeTab !== 'division'} className={r.id === regionId && activeTab !== 'division' ? 'active' : ''} onClick={() => { if (activeTab === 'division') setActiveTab('ponds'); switchRegion(r.id); }}>Latur district</button>
              ))}
              {otherDistricts.length > 0 && (
                <select
                  aria-label="Other Marathwada districts"
                  className={otherDistricts.some((r) => r.id === regionId) && activeTab !== 'division' ? 'active' : ''}
                  value={otherDistricts.some((r) => r.id === regionId) ? regionId : ''}
                  onChange={(e) => { if (!e.target.value) return; if (activeTab === 'division') setActiveTab('ponds'); switchRegion(e.target.value); }}
                >
                  <option value="">{otherDistricts.length} more districts</option>
                  {otherDistricts.map((r) => <option key={r.id} value={r.id}>{regionLabel(r)}</option>)}
                </select>
              )}
              {regions.filter((r) => r.id === 'latur-2026').map((r) => (
                <button key={r.id} data-region={r.id} aria-pressed={r.id === regionId && activeTab !== 'division'} className={`region-minor ${r.id === regionId && activeTab !== 'division' ? 'active' : ''}`} onClick={() => { if (activeTab === 'division') setActiveTab('ponds'); switchRegion(r.id); }}>Latur test box</button>
              ))}
              <span className="region-group-label">2024 replay</span>
              {['latur-district-2024', 'latur-2024'].map((id) => regions.find((r) => r.id === id)).filter(Boolean).map((r) => (
                <button key={r.id} data-region={r.id} aria-pressed={r.id === regionId && activeTab !== 'division'} className={`${r.id === 'latur-2024' ? 'region-minor ' : ''}${r.id === regionId && activeTab !== 'division' ? 'active' : ''}`} onClick={() => { if (activeTab === 'division') setActiveTab('ponds'); switchRegion(r.id); }}>{r.id === 'latur-2024' ? 'Latur test box' : 'Latur district'}</button>
              ))}
            </div>
          </div>

          {activeTab !== 'division' && <div className="app-context-meta">
            <div className="asof-block">
              <span className="eyebrow">
                AS OF {loading && <span className="loading-dot">· updating</span>}
              </span>
              <strong>{formatDate(asOf, { day: '2-digit', month: 'short', year: 'numeric' })}</strong>
              <small>Only data available by this date</small>
            </div>
            <div className="sun-share">
              <span className="eyebrow">☀ SUN'S SHARE</span>
              <strong>{data.sunShareMm ?? '—'} <small>mm</small></strong>
              <span className="since">
                evaporation since {formatDate(addDays(asOf, -45), { day: '2-digit', month: 'short' })}
              </span>
            </div>
          </div>}
        </div>
      </header>

      {!['division', 'accuracy', 'about'].includes(activeTab) && <div className={`mode-banner ${isLive ? 'live' : 'replay'}`}>
        {isLive
          ? <><b><span className="live-pulse" /> Live region</b> · Recomputed on AWS after new Sentinel-2 passes. Grey “Too early” ponds have fewer than three valid passes in the last 45 days, so Talaab will not guess a drying date.</>
          : <><b>2024 replay</b> · Each date shows only what Talaab could have known then. Ranges, not exact dates.</>}
      </div>}
      {error && <div className="error-strip" role="status">{error}</div>}

      {activeTab === 'division' && <DivisionOverview
        division={marathwadaDivision}
        onOpenDistrict={(targetRegion) => { setActiveTab('ponds'); switchRegion(targetRegion); }}
        onOpenPond={({ region: targetRegion, id }) => { setActiveTab('ponds'); switchRegion(targetRegion, id); }}
        onOpenPlan={(scope) => { setPlanScope(scope); setActiveTab('plan'); }}
      />}
      <Suspense fallback={<div className="tab-loading" role="status">Loading…</div>}>
        {activeTab === 'plan' && <PlanTab regionId={planScope?.regionId ?? regionId} asOf={planScope?.asOf ?? asOf} regionName={planScope?.regionName ?? data.region.name} />}
        {activeTab === 'accuracy' && <AccuracyTab />}
        {activeTab === 'about' && <AboutTab onExplore={() => setActiveTab('ponds')} />}
      </Suspense>
      {activeTab === 'ponds' && (
        <section className="workspace">
          <aside className={`sidebar ${mobileSheetExpanded ? 'sheet-expanded' : ''}`}>
            <div className="sidebar-head"
              onTouchStart={(event) => { sheetTouchStart.current = event.touches[0]?.clientY ?? null; }}
              onTouchEnd={(event) => {
                if (sheetTouchStart.current == null) return;
                const delta = sheetTouchStart.current - (event.changedTouches[0]?.clientY ?? sheetTouchStart.current);
                if (delta > 24) setMobileSheetExpanded(true);
                if (delta < -24) setMobileSheetExpanded(false);
                sheetTouchStart.current = null;
              }}>
              <div><h2>Act before it dries.</h2></div>
              <span className="count-total">{ponds.length}</span>
              <button className="sheet-handle" aria-label={mobileSheetExpanded ? 'Collapse pond list' : 'Expand pond list'} aria-expanded={mobileSheetExpanded} onClick={() => setMobileSheetExpanded((value) => !value)}><span /></button>
            </div>
            <div className="sidebar-stack">
            <div className="story-block">
              <span className="story-overline">{isLive ? 'THE DISTRICT TODAY' : 'THE 2024 SEASON · REPLAY'}</span>
              <h2>{headline}</h2>
              <p>{flaggedCount} pond{flaggedCount === 1 ? '' : 's'} shrinking faster than the local baseline. The flag suggests pumping; it is not proof.</p>
              <div className="sun-share-inline"><span>☀ SUN'S SHARE</span><strong>{data.sunShareMm ?? '—'} mm</strong><small>evaporation in the latest window</small></div>
            </div>
            {(regionId === 'latur-2024' || regionId === REPLAY_REGION) && !isLive && (
              <div className="timelapse-feature-card" role="region" aria-label="Satellite time-lapse feature">
                <div className="timelapse-feature-header">
                  <span className="timelapse-badge">SATELLITE TIME-LAPSE</span>
                  <span className="timelapse-dates">Jan – May 2024</span>
                </div>
                <div className="timelapse-feature-body">
                  <img src={P003_TIMELAPSE_SRC} alt="P003 time-lapse: Watch the sun drink the pond" className="timelapse-thumb-preview" loading="lazy" />
                  <div className="timelapse-feature-copy">
                    <h3 className="timelapse-feature-title">Watch the sun drink the pond</h3>
                    <p className="timelapse-feature-desc">24 authentic Copernicus Sentinel-2 passes tracking 33 ha reservoir P003 drying through the 2024 drought.</p>
                  </div>
                </div>
                <button type="button" className="timelapse-feature-btn" onClick={() => openPondFromList('P003')}>
                  ▶ Inspect P003 time-lapse
                </button>
              </div>
            )}
            <div className="status-summary">
              {STATUS_KEYS.filter((status) => counts[status]).map((status) => <span key={status}><i style={{ background: statusMeta(status).color }} />{counts[status]} {statusMeta(status).label.toLowerCase()}</span>)}
            </div>
            {isLive && <p className="too-early-note">“Too early” means there are not enough valid recent satellite passes to estimate a drying window.</p>}
            {talukas.length > 0 && (
              <div className="taluka-filter">
                <label htmlFor="taluka-filter">FILTER BY TALUKA</label>
                <select id="taluka-filter" value={talukaFilter} onChange={changeTaluka}>
                  <option value="">All talukas · {ponds.length} ponds</option>
                  {talukas.map((taluka) => (
                    <option key={taluka.name} value={taluka.name}>
                      {taluka.name}{taluka.nameMr ? ` · ${taluka.nameMr}` : ''} · {taluka.ponds} ponds
                    </option>
                  ))}
                </select>
                {talukaFilter && <button type="button" onClick={() => changeTaluka({ target: { value: '' } })}>Clear</button>}
              </div>
            )}
            </div>
            <AlertsFeed alerts={visibleAlerts} asOf={asOf} isReplay={!isLive} />
            <PondList ponds={filteredPonds} selectedId={selected?.id} onSelect={openPondFromList} isLive={isLive} regionId={regionId} />
            <details className="data-footer">
              <summary>About the data <span>{data.scenes?.length ?? 0} passes · {data.scenes?.filter((scene) => scene.status === 'suspect').length ?? 0} suspect</span></summary>
              <div className="data-footer-body">
                <p>Sentinel-2 L2A (Copernicus) via AWS Open Data · Open-Meteo (CC BY 4.0) · © OpenStreetMap contributors (ODbL) · Basemap © AWS, HERE</p>
                <p>{data.scenes?.length ?? 0} satellite passes; {data.scenes?.filter((scene) => scene.status === 'suspect').length ?? 0} suspect, not used for forecasts.</p>
                <ExcludedPonds excluded={data.excludedPonds} />
              </div>
            </details>
          </aside>

          <section className="map-panel">
            <div className="map-story-overlay">
              <span>{isLive ? 'LIVE MONITORING' : 'LONGLENS · 2024 REPLAY'}</span>
              <strong>{headline}</strong>
              <small>{flaggedCount} faster-than-sun inspection flag{flaggedCount === 1 ? '' : 's'}</small>
            </div>
            <div className="map-toolbar">
              <div className="legend" aria-label="Filter map by pond status">
                {STATUS_KEYS.map((status) => (
                  <button
                    type="button"
                    key={status}
                    className={`legend-status ${visibleStatuses.includes(status) ? 'is-on' : 'is-off'}`}
                    aria-pressed={visibleStatuses.includes(status)}
                    onClick={() => toggleMapStatus(status)}
                    title={`${visibleStatuses.includes(status) ? 'Hide' : 'Show'} ${statusMeta(status).label.toLowerCase()} ponds`}
                  >
                    <i style={{ background: statusMeta(status).color }} />{statusMeta(status).label}
                  </button>
                ))}
                {visibleStatuses.length !== STATUS_KEYS.length && (
                  <button type="button" className="legend-reset" onClick={() => setVisibleStatuses(STATUS_KEYS)}>All</button>
                )}
              </div>
              <button className={`sat-toggle ${satellite ? 'on' : ''}`} aria-pressed={satellite} onClick={() => setSatellite((value) => !value)}>Satellite {satellite ? 'on' : 'off'} <span aria-hidden="true">◉</span></button>
            </div>
            <MapView region={data.region} ponds={ponds} selectedId={selected?.id} onSelect={selectPondFromMap} satellite={satellite} outlines={outlines} visibleStatuses={visibleStatuses} focusRequest={focusRequest} />
            <div className="map-note">{outlines?.features?.length ? 'Pond outlines · click a shape to inspect it' : 'Pond locations · outlines appear when imagery files arrive'}</div>
          </section>

          <aside className={`detail-panel ${mobileDetailOpen ? 'mobile-open' : ''}`}>
            <button className="drawer-close" onClick={() => setMobileDetailOpen(false)} aria-label="Close pond details">✕ Close details</button>
            <PondDetailCard pond={selected} asOf={asOf} scenes={data.scenes} imageryIndex={imageryIndex} imageryRegion={imageryRegion} regionId={regionId} isLive={isLive} />
          </aside>
        </section>
      )}

      {activeTab === 'ponds' && (
        <SeasonTimeline dates={dates} dateIndex={dateIndex} onChange={(index) => { setPlaying(false); setDateIndex(index); }}
          playing={playing} onTogglePlay={toggleTimelinePlayback} disabled={reducedMotion || isLive} />
      )}
    </main>
  );
}

function AlertsFeed({ alerts, asOf, isReplay }) {
  return (
    <section className="alerts-feed" aria-label="Alerts through selected date" tabIndex={0}>
      <div className="feed-heading"><strong>ALERT TIMELINE</strong><span>THROUGH {formatDate(asOf, { day: '2-digit', month: 'short' })}</span></div>
      {alerts.length ? alerts.map((alert, index) => {
        const date = alertDate(alert);
        const kind = String(alert?.type ?? alert?.status ?? '').toLowerCase();
        const tone = /dry|critical|flag|urgent/.test(kind) ? 'alert-hot' : /watch|warn/.test(kind) ? 'alert-warm' : '';
        return <div className={`alert-item ${tone}`} key={alert?.id ?? `${date}-${alertPondId(alert)}-${index}`}>
          <span className="alert-date">{date ? formatDate(date, { day: '2-digit', month: 'short' }) : 'EVENT'}</span>
          <span className="alert-copy"><strong>{alertPondId(alert) || 'District alert'}</strong><small>{alertMessage(alert)}</small></span>
        </div>;
      }) : <p className="alerts-empty">{isReplay ? 'No alert recorded on or before this replay date.' : 'No alerts published for this region yet.'}</p>}
    </section>
  );
}

function SeasonTimeline({ dates, dateIndex, onChange, playing, onTogglePlay, disabled }) {
  const months = dates.map((date, index) => ({ date, index, month: date.slice(0, 7) }))
    .filter((item, index, list) => index === 0 || item.month !== list[index - 1].month);
  const currentDate = dates[dateIndex];
  const isAtEnd = dateIndex >= dates.length - 1;
  const monthLabel = (date) => formatDate(date, { month: 'short', year: '2-digit' });
  return (
    <section className="season-timeline" aria-label="Replay timeline">
      <button className={`play-button ${playing ? 'is-playing' : ''}`} onClick={onTogglePlay} disabled={disabled || dates.length < 2} aria-label={playing ? 'Pause season replay' : 'Play season replay'}>
        <span>{playing ? 'Ⅱ' : '▶'}</span><b>{playing ? 'PAUSE' : 'PLAY'}</b>
      </button>
      <div className="timeline-main">
        <div className="timeline-caption"><span>SEASON TIMELINE</span><strong>{currentDate ? formatDate(currentDate, { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}</strong><small>{isAtEnd ? 'Latest published pass' : 'Only observations available by this date'}</small></div>
        <input className="timeline-range" aria-label="Replay satellite pass date" type="range" min="0" max={Math.max(0, dates.length - 1)} value={dateIndex} disabled={dates.length < 2} onChange={(event) => onChange(Number(event.target.value))} />
        <div className="timeline-months">
          {months.map((item) => <span key={item.month} style={{ left: `${dates.length < 2 ? 0 : (item.index / (dates.length - 1)) * 100}%` }}>{monthLabel(item.date)}</span>)}
        </div>
      </div>
      <div className="timeline-note"><span className="timeline-led" />{disabled ? 'PLAY disabled for live data or reduced-motion settings' : `${dates.length} published satellite passes`}</div>
    </section>
  );
}

function ExcludedPonds({ excluded }) {
  if (!excluded?.length) return null;
  return <details className="excluded"><summary>{excluded.length} detections excluded by quality checks (why?)</summary><ul>{excluded.map((entry) => <li key={`${entry.lat},${entry.lon}`}><b>{entry.refAreaHa} ha</b> {placeLabel(entry)}: {entry.reason}</li>)}</ul></details>;
}

function daysLeftText(pond) {
  if (pond.status === 'dry') return 'Dry now';
  if (pond.status === 'unknown') return 'Too early';
  return pond.daysLeft ? `${pond.daysLeft.likely} d` : 'Stable';
}

function dryByText(pond) {
  if (pond.status === 'dry') return 'Already dry';
  if (pond.status === 'unknown') return 'Not enough clear passes yet (needs 3 over 15 days)';
  if (!pond.dryBy) return 'Stable: not shrinking beyond measurement noise';
  return formatRange(pond.dryBy);
}

function PondDetailCard({ pond, asOf, scenes, imageryIndex, imageryRegion, regionId, isLive }) {
  const [expandedPass, setExpandedPass] = useState(null);
  useEffect(() => setExpandedPass(null), [pond?.id, asOf]);
  // District thumbnails live in our S3 bucket: ONE API call returns a signed link for every pass of this pond
  // (one call per thumbnail would run ~24 Lambdas at once against the account's limit of 10). Box regions ship
  // their thumbnails with the site.
  const [links, setLinks] = useState(null);
  const fromApi = String(imageryRegion || '').includes('district');
  useEffect(() => {
    setLinks(null);
    if (!fromApi || !pond?.id || !imageryRegion) return undefined;
    const controller = new AbortController();
    fetch(`${imageryBase(imageryRegion)}/${encodeURIComponent(imageryRegion)}/${encodeURIComponent(pond.id)}/links.json`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null)).then((body) => setLinks(body?.links ?? {})).catch(() => {});
    return () => controller.abort();
  }, [fromApi, imageryRegion, pond?.id]);
  useEffect(() => {
    if (!expandedPass) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') setExpandedPass(null);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [expandedPass]);
  if (!pond) return <div className="detail-empty">Select a pond to inspect its history.</div>;
  const meta = statusMeta(pond.status);
  const shrinkPct = pond.maxAreaHa && pond.areaNowHa != null ? Math.max(0, Math.round((1 - pond.areaNowHa / pond.maxAreaHa) * 100)) : null;
  const pondImagery = imageryIndex?.ponds?.[pond.id];
  const passes = (pondImagery?.dates ?? []).filter((date) => !asOf || date <= asOf).sort();
  const districtImageryMissing = String(regionId || '').includes('district') && passes.length === 0;
  const historyByDate = new Map((pond.history ?? []).filter((point) => !asOf || point.date <= asOf).map((point) => [point.date, point]));
  const sceneByDate = new Map((scenes ?? []).filter((scene) => !asOf || scene.date <= asOf).map((scene) => [scene.date, scene]));
  return (
    <div className="detail-card">
      <div className="detail-kicker">SELECTED POND · {formatDate(asOf, { day: '2-digit', month: 'short', year: 'numeric' })}</div>
      <div className="detail-title-row"><div><h2>{pond.id}</h2><p>{placeLabel(pond)}</p>{(pond.taluka || pond.talukaMr) && <p className="detail-taluka">Taluka · {pond.taluka || '—'}{pond.talukaMr ? ` · ${pond.talukaMr}` : ''}</p>}</div><span className="status-pill large" style={{ '--status-color': meta.color, '--status-soft': meta.soft }}>{meta.label}</span></div>
      <div className="headline-metric"><strong>{pond.areaNowHa ?? '—'}</strong><span>ha water area now</span></div>
      <div className="metric-grid">
        <Stat label="Max area" value={`${pond.maxAreaHa ?? '—'} ha`} />
        <Stat label="Shrunk" value={shrinkPct == null ? '—' : `${shrinkPct}%`} />
        <Stat label="Likely dry in" value={daysLeftText(pond)} />
        {pond.confidence === 'low' && <p className="confidence-note"><strong>Low confidence</strong> · {pond.confidenceReason || 'few clear passes'}; confirm on the next satellite pass.</p>}
        <Stat label="Vs neighbours" value={pond.shrinkVsNeighbours ? `${pond.shrinkVsNeighbours}×` : '—'} tone={pond.shrinkVsNeighbours >= 2 ? 'danger' : ''} />
      </div>
      <AreaChart pond={pond} asOf={asOf} />
      {pond.flag === 'faster-than-sun' ? (
        <div className="inspection-callout"><div className="callout-icon">!</div><div><strong>Faster than the sun</strong><span>Shrinking {pond.shrinkVsNeighbours}× faster than nearby ponds under the same sun. Field inspection recommended; this suggests pumping but is not proof.</span></div></div>
      ) : <div className="safe-callout"><span>✓</span><div><strong>Within expected pattern</strong><span>No faster-than-sun flag on this pond.</span></div></div>}
      <div className="dry-by-box"><span className="eyebrow">DRY-BY WINDOW</span><strong>{dryByText(pond)}</strong><small>Range includes the year; it is not an exact day.</small></div>
      {pond.id === 'P003' && !isLive && (regionId === 'latur-2024' || regionId === REPLAY_REGION) && (
        <section className="pond-timelapse-section">
          <div className="timelapse-section-head">
            <div>
              <span className="eyebrow">SATELLITE TIME-LAPSE</span>
              <strong className="timelapse-tagline">“Watch the sun drink the pond”</strong>
            </div>
            <span className="timelapse-meta-pill">24 passes · 6.5s loop</span>
          </div>
          <div
            className="timelapse-preview-wrap"
            onClick={() => setExpandedPass({
              date: '2024-01-01 – 2024-05-30',
              src: P003_TIMELAPSE_SRC,
              isTimelapse: true
            })}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setExpandedPass({
                  date: '2024-01-01 – 2024-05-30',
                  src: P003_TIMELAPSE_SRC,
                  isTimelapse: true
                });
              }
            }}
            aria-label="Expand P003 Sentinel-2 time-lapse: Watch the sun drink the pond"
          >
            <img
              src={P003_TIMELAPSE_SRC}
              alt="P003 time-lapse: Watch the sun drink the pond"
              className="pond-timelapse-gif"
            />
            <div className="timelapse-overlay-badge">
              <span className="timelapse-play-pill">▶ Full resolution (512×512)</span>
            </div>
          </div>
          <p className="timelapse-caption">
            24 authentic Copernicus Sentinel-2 L2A true-colour passes (1 Jan 2024 – 30 May 2024) tracking 33 ha reservoir P003 drying through the 2024 drought.
          </p>
        </section>
      )}
      {passes.length > 0 && (
        <section className="imagery-strip-wrap">
          <div className="imagery-heading"><div><strong>Satellite passes</strong><span>Only passes up to {formatDate(asOf, { day: '2-digit', month: 'short', year: 'numeric' })}</span></div><span>{passes.length} views</span></div>
          <div className="imagery-strip">{passes.map((date) => {
            const history = historyByDate.get(date);
            const suspect = sceneByDate.get(date)?.status === 'suspect';
            const invalid = history?.valid === false || suspect;
            const src = fromApi ? links?.[date] : `${imageryBase(imageryRegion)}/${encodeURIComponent(imageryRegion)}/${encodeURIComponent(pond.id)}/${date}.jpg`;
            return <button key={date} className={`imagery-thumb ${invalid ? 'invalid-pass' : ''}`} disabled={!src} onClick={() => src && setExpandedPass({ date, src, invalid })} aria-label={`View satellite pass ${date}${invalid ? ', marked invalid or suspect' : ''}`}>
              {src ? <img src={src} loading="lazy" alt={`Sentinel-2 view of ${pond.id} on ${date}`} /> : <span className="imagery-thumb-loading" aria-hidden="true" />}
              <span>{formatDate(date, { day: '2-digit', month: 'short' })}</span><small>{invalid ? 'Not used' : 'Pass'}</small>
            </button>;
          })}</div>
          {imageryIndex?.credit && <p className="imagery-credit">{imageryIndex.credit}</p>}
        </section>
      )}
      {expandedPass && (
        <div className="image-lightbox" role="dialog" aria-modal="true" aria-label={expandedPass.isTimelapse ? 'Watch the sun drink the pond · Sentinel-2 time-lapse' : `Satellite image ${expandedPass.date}`} onClick={() => setExpandedPass(null)}>
          <button className="lightbox-close" onClick={() => setExpandedPass(null)} aria-label="Close image">✕</button>
          <img src={expandedPass.src} alt={expandedPass.isTimelapse ? 'Watch the sun drink the pond' : `Pond ${pond.id} on ${expandedPass.date}`} onClick={(event) => event.stopPropagation()} />
          <strong>{expandedPass.isTimelapse ? 'Watch the sun drink the pond' : `${pond.id} · ${formatDate(expandedPass.date, { day: 'numeric', month: 'short', year: 'numeric' })}`}</strong>
          {expandedPass.isTimelapse ? (
            <span>24 Copernicus Sentinel-2 L2A passes (1 Jan 2024 – 30 May 2024) · 270 ms/frame</span>
          ) : (
            expandedPass.invalid && <span>Invalid or suspect pass — shown for context, not used for forecasting.</span>
          )}
          <small>{expandedPass.isTimelapse ? 'Copernicus Sentinel-2 (AWS Open Data / Element84 Earth Search)' : imageryIndex?.credit}</small>
        </div>
      )}
      {districtImageryMissing && (
        <div className="imagery-empty" role="note">
          Satellite thumbnails available in the Latur 2024 view. District imagery is being prepared.
        </div>
      )}
    </div>
  );
}

function AreaChart({ pond, asOf }) {
  const data = (pond.history ?? []).filter((point) => !asOf || point.date <= asOf).map((point) => ({
    ...point,
    shortDate: formatDate(point.date, { day: '2-digit', month: 'short' }),
    validArea: point.valid ? point.areaHa : null,
    invalidArea: point.valid ? null : point.areaHa,
  }));
  return <div className="chart-wrap">
    <div className="chart-heading"><div><strong>Water area over time</strong><span>Grey marks show invalid or suspect passes</span></div><span>{data.length} passes</span></div>
    <div className="chart"><ResponsiveContainer width="100%" height="100%">
      <ReAreaChart data={data} margin={{ top: 12, right: 4, left: -18, bottom: 0 }}>
        <defs><linearGradient id="waterFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#14b8a6" stopOpacity={0.3} /><stop offset="100%" stopColor="#14b8a6" stopOpacity={0.02} /></linearGradient></defs>
        <CartesianGrid strokeDasharray="3 5" vertical={false} stroke="#2a3a35" />
        <XAxis dataKey="shortDate" tick={{ fontSize: 11, fill: '#6f7f77' }} tickLine={false} axisLine={false} minTickGap={18} />
        <YAxis tick={{ fontSize: 11, fill: '#6f7f77' }} tickLine={false} axisLine={false} width={34} />
        <Tooltip contentStyle={{ borderRadius: 10, border: '1px solid #30443b', background: '#101b18', color: '#edf5ef' }} formatter={(value, name, item) => [item.payload.areaHa != null ? `${item.payload.areaHa} ha` : '—', item.payload.valid ? 'Water area' : 'Not used (cloud / suspect)']} />
        {data.filter((point) => point.invalidArea != null).map((point) => <ReferenceLine key={point.date} x={point.shortDate} stroke="#7a8982" strokeDasharray="2 4" />)}
        <Area type="monotone" dataKey="validArea" stroke="#14b8a6" strokeWidth={2.5} fill="url(#waterFill)" dot={{ r: 2.5, fill: '#14b8a6', strokeWidth: 0 }} activeDot={{ r: 4 }} connectNulls />
        <Scatter dataKey="invalidArea" fill="#84928b" line={false} shape="circle" />
      </ReAreaChart>
    </ResponsiveContainer></div>
  </div>;
}
