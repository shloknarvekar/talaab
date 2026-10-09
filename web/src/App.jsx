import { useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { AreaChart as ReAreaChart, Area, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Scatter, ReferenceLine } from 'recharts';
import MapView from './components/MapView';
import PondList from './components/PondList';
import { fetchBacktest, fetchPonds, fetchRegions, requestPlan } from './api';
import { STATUS_KEYS, addDays, formatDate, formatRange, pct, placeLabel, sortPonds, statusMeta } from './utils';

const REPO = 'https://github.com/shloknarvekar/talaab';
const REPLAY_REGION = 'latur-2024';

function Stat({ label, value, tone }) {
  return <div className={`stat ${tone || ''}`}><span>{label}</span><strong>{value}</strong></div>;
}

function regionLabel(region) {
  const district = region.id.includes('district');
  if (region.mode === 'live') return district ? 'Whole district today' : 'Latur today';
  return district ? 'Whole district 2024' : 'Latur 2024';
}

export default function App() {
  const [regions, setRegions] = useState([]);
  const [regionId, setRegionId] = useState(null);
  const [dateIndex, setDateIndex] = useState(0);
  const [data, setData] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [satellite, setSatellite] = useState(false);
  const [activeTab, setActiveTab] = useState('ponds');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const requestId = useRef(0);

  // 1. Regions: open on the live whole district (else any live region), latest snapshot.
  useEffect(() => {
    fetchRegions()
      .then((list) => {
        if (!list.length) throw new Error('No published regions yet.');
        setRegions(list);
        const live = list.filter((r) => r.mode === 'live');
        const first = live.find((r) => r.id.includes('district')) ?? live[0] ?? list[0];
        setRegionId(first.id);
        setDateIndex(first.dates.length - 1);
      })
      .catch((err) => { setError(`Could not reach the Talaab API: ${err.message}`); setLoading(false); });
  }, []);

  const region = regions.find((r) => r.id === regionId);
  const dates = region?.dates ?? [];
  const asOf = dates[dateIndex];

  // 2. Snapshot for the chosen region and date (ignore answers to superseded requests).
  useEffect(() => {
    if (!regionId || !asOf) return;
    const id = ++requestId.current;
    setLoading(true);
    fetchPonds(regionId, asOf)
      .then((payload) => {
        if (id !== requestId.current) return;
        setData(payload);
        setError('');
        setSelectedId((current) => (payload.ponds.some((p) => p.id === current) ? current : sortPonds(payload.ponds)[0]?.id));
      })
      .catch((err) => id === requestId.current && setError(err.message))
      .finally(() => id === requestId.current && setLoading(false));
  }, [regionId, asOf]);

  const switchRegion = (id) => {
    const next = regions.find((r) => r.id === id);
    if (!next || id === regionId) return;
    setRegionId(id);
    setDateIndex(next.dates.length - 1);
  };

  const ponds = useMemo(() => sortPonds(data?.ponds ?? []), [data]);
  const selected = ponds.find((pond) => pond.id === selectedId) ?? ponds[0];
  const counts = useMemo(() => ponds.reduce((acc, pond) => ({ ...acc, [pond.status]: (acc[pond.status] || 0) + 1 }), {}), [ponds]);
  const isLive = region?.mode === 'live';

  if (!data) {
    return <main className="loading-screen"><div className="loading-mark">तालाब</div><p>{error || 'Loading pond intelligence…'}</p></main>;
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">जल</div>
          <div><h1>Talaab</h1><p>The sun drinks first.</p></div>
        </div>
        <div className="region-block">
          <span className="eyebrow">REGION</span>
          <div className="region-switch" role="tablist" aria-label="Choose region">
            {regions.map((r) => (
              <button key={r.id} role="tab" aria-selected={r.id === regionId} className={r.id === regionId ? 'active' : ''} onClick={() => switchRegion(r.id)}>
                {regionLabel(r)} <em className={r.mode}>{r.mode === 'live' ? 'LIVE' : 'REPLAY'}</em>
              </button>
            ))}
          </div>
        </div>
        <div className="asof-block">
          <span className="eyebrow">AS OF {loading && <span className="loading-dot">· updating</span>}</span>
          <strong>{formatDate(asOf, { day: '2-digit', month: 'short', year: 'numeric' })}</strong>
          <input aria-label="Choose as-of date" type="range" min="0" max={Math.max(0, dates.length - 1)} value={dateIndex}
            disabled={dates.length < 2} onChange={(event) => setDateIndex(Number(event.target.value))} />
        </div>
        <div className="sun-share">
          <span className="eyebrow">☀ SUN'S SHARE</span>
          <strong>{data.sunShareMm ?? '—'} <small>mm</small></strong>
          <span className="since">evaporation since {formatDate(addDays(asOf, -45), { day: '2-digit', month: 'short' })}</span>
        </div>
        <nav className="tab-group" aria-label="Views">
          {[['ponds', 'Ponds'], ['plan', 'Plan'], ['accuracy', 'Accuracy']].map(([key, label]) => (
            <button key={key} className={`tab-button ${activeTab === key ? 'active' : ''}`} onClick={() => setActiveTab(key)}>{label}</button>
          ))}
        </nav>
      </header>

      <div className={`mode-banner ${isLive ? 'live' : 'replay'}`}>
        {isLive
          ? <><b>Live</b> · Latur this season. Recomputed on AWS after every Sentinel-2 pass (about every 5 days) with real heat forecasts. Early in the season many ponds are “too early” to forecast.</>
          : <><b>2024 replay</b> · Each date shows only what Talaab could have known that day, so the slider is an honest backtest. Ranges, not exact dates.</>}
      </div>
      {error && <div className="error-strip">{error}</div>}

      {activeTab === 'plan' && <PlanTab regionId={regionId} asOf={asOf} regionName={data.region.name} />}
      {activeTab === 'accuracy' && <AccuracyTab />}
      {activeTab === 'ponds' && (
        <section className="workspace">
          <aside className="sidebar">
            <div className="sidebar-head">
              <div><span className="eyebrow">POND RISK</span><h2>Act before it dries.</h2></div>
              <span className="count-total">{ponds.length}</span>
            </div>
            <div className="status-summary">
              {STATUS_KEYS.filter((s) => counts[s]).map((status) => <span key={status} style={{ color: statusMeta(status).color }}>{counts[status]} {statusMeta(status).label.toLowerCase()}</span>)}
            </div>
            <PondList ponds={ponds} selectedId={selected?.id} onSelect={setSelectedId} />
            <div className="data-footer">
              <strong>About the data</strong>
              <span>Sentinel-2 L2A (Copernicus) via AWS Open Data · Open-Meteo (CC BY 4.0) · village names © OpenStreetMap</span>
              <span>{data.scenes?.length ?? 0} satellite passes · {data.scenes?.filter((s) => s.status === 'suspect').length ?? 0} suspect, not used.</span>
              <ExcludedPonds excluded={data.excludedPonds} />
            </div>
          </aside>

          <section className="map-panel">
            <div className="map-toolbar">
              <div className="legend">
                {STATUS_KEYS.map((status) => <span key={status}><i style={{ background: statusMeta(status).color }}></i>{statusMeta(status).label}</span>)}
              </div>
              <button className={`sat-toggle ${satellite ? 'on' : ''}`} onClick={() => setSatellite((v) => !v)}>{satellite ? 'Satellite' : 'Street'} <span>◉</span></button>
            </div>
            <MapView region={data.region} ponds={ponds} selectedId={selected?.id} onSelect={setSelectedId} satellite={satellite} />
            <div className="map-note">One marker per pond · labels never rely on colour alone</div>
          </section>

          <aside className="detail-panel">
            <PondDetailCard pond={selected} asOf={asOf} />
          </aside>
        </section>
      )}
    </main>
  );
}

function ExcludedPonds({ excluded }) {
  if (!excluded?.length) return null;
  return (
    <details className="excluded">
      <summary>{excluded.length} detections excluded by quality checks (why?)</summary>
      <ul>{excluded.map((e) => <li key={`${e.lat},${e.lon}`}><b>{e.refAreaHa} ha</b> {placeLabel(e)}: {e.reason}</li>)}</ul>
    </details>
  );
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

function PondDetailCard({ pond, asOf }) {
  if (!pond) return <div className="detail-empty">Select a pond.</div>;
  const meta = statusMeta(pond.status);
  const shrinkPct = pond.maxAreaHa && pond.areaNowHa != null ? Math.max(0, Math.round((1 - pond.areaNowHa / pond.maxAreaHa) * 100)) : null;
  return (
    <div className="detail-card">
      <div className="detail-kicker">SELECTED POND · {formatDate(asOf, { day: '2-digit', month: 'short', year: 'numeric' })}</div>
      <div className="detail-title-row">
        <div><h2>{pond.id}</h2><p>{placeLabel(pond)}</p></div>
        <span className="status-pill large" style={{ '--status-color': meta.color, '--status-soft': meta.soft }}>{meta.label}</span>
      </div>
      <div className="headline-metric"><strong>{pond.areaNowHa ?? '—'}</strong><span>ha water area now</span></div>
      <div className="metric-grid">
        <Stat label="Max area" value={`${pond.maxAreaHa ?? '—'} ha`} />
        <Stat label="Shrunk" value={shrinkPct == null ? '—' : `${shrinkPct}%`} />
        <Stat label="Likely dry in" value={daysLeftText(pond)} />
        <Stat label="Vs neighbours" value={pond.shrinkVsNeighbours ? `${pond.shrinkVsNeighbours}×` : '—'} tone={pond.shrinkVsNeighbours >= 2 ? 'danger' : ''} />
      </div>
      <AreaChart pond={pond} />
      {pond.flag === 'faster-than-sun' ? (
        <div className="inspection-callout"><div className="callout-icon">!</div><div><strong>Faster than the sun</strong><span>Shrinking {pond.shrinkVsNeighbours}× faster than nearby ponds under the same sun. Field inspection recommended; this suggests pumping but is not proof.</span></div></div>
      ) : (
        <div className="safe-callout"><span>✓</span><div><strong>Within expected pattern</strong><span>No faster-than-sun flag on this pond.</span></div></div>
      )}
      <div className="dry-by-box"><span className="eyebrow">DRY-BY WINDOW</span><strong>{dryByText(pond)}</strong><small>Forecast is a range, not an exact day.</small></div>
    </div>
  );
}

function AreaChart({ pond }) {
  const data = pond.history.map((point) => ({ ...point, shortDate: formatDate(point.date, { day: '2-digit', month: 'short' }), validArea: point.valid ? point.areaHa : null, invalidArea: point.valid ? null : point.areaHa }));
  return (
    <div className="chart-wrap">
      <div className="chart-heading"><div><strong>Water area over time</strong><span>Dashed lines mark cloudy or suspect passes (not used)</span></div><span>{pond.history.length} passes</span></div>
      <div className="chart"><ResponsiveContainer width="100%" height="100%">
        <ReAreaChart data={data} margin={{ top: 12, right: 4, left: -18, bottom: 0 }}>
          <defs><linearGradient id="waterFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3d7c6d" stopOpacity={0.28} /><stop offset="100%" stopColor="#3d7c6d" stopOpacity={0.03} /></linearGradient></defs>
          <CartesianGrid strokeDasharray="3 5" vertical={false} stroke="#e3e9e4" />
          <XAxis dataKey="shortDate" tick={{ fontSize: 10, fill: '#64736a' }} tickLine={false} axisLine={false} minTickGap={18} />
          <YAxis tick={{ fontSize: 10, fill: '#64736a' }} tickLine={false} axisLine={false} width={34} />
          <Tooltip contentStyle={{ borderRadius: 10, border: '1px solid #dfe6e1', boxShadow: '0 8px 20px rgba(14,34,23,.08)' }} formatter={(value, name, item) => [item.payload.areaHa != null ? `${item.payload.areaHa} ha` : '—', item.payload.valid ? 'Water area' : 'Not used (cloud / suspect)']} labelFormatter={(label) => label} />
          {data.filter((point) => point.invalidArea != null).map((point) => <ReferenceLine key={point.date} x={point.shortDate} stroke="#c6cdc8" strokeDasharray="2 4" />)}
          <Area type="monotone" dataKey="validArea" stroke="#1f6354" strokeWidth={2.5} fill="url(#waterFill)" dot={{ r: 2.5, fill: '#1f6354', strokeWidth: 0 }} activeDot={{ r: 4 }} connectNulls />
          <Scatter dataKey="invalidArea" fill="#9aa6a0" line={false} shape="circle" />
        </ReAreaChart>
      </ResponsiveContainer></div>
    </div>
  );
}

const PLAN_SOURCE = {
  bedrock: 'Written by Claude on Amazon Bedrock · every number checked against the data',
  template: 'Deterministic plan · built directly from the numbers, no AI',
};

function PlanTab({ regionId, asOf, regionName }) {
  const [language, setLanguage] = useState('en');
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const abort = useRef(null);

  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => { setPlan(null); setError(''); }, [regionId, asOf, language]);

  const onGenerate = async () => {
    abort.current?.abort();
    abort.current = new AbortController();
    setBusy(true);
    setError('');
    try {
      await requestPlan({ region: regionId, asOf, language }, { onUpdate: setPlan, signal: abort.current.signal });
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="plan-screen">
      <div className="plan-hero">
        <div>
          <span className="eyebrow">DISTRICT ACTION PLAN · {regionName} · {formatDate(asOf, { day: '2-digit', month: 'short', year: 'numeric' })}</span>
          <h2>Turn pond risk into a field plan.</h2>
          <p>One section per scarcity period (Oct–Dec, Jan–Mar, Apr–Jun), by village, with an action for every pond.</p>
        </div>
        <div className="language-toggle">
          <button className={language === 'en' ? 'active' : ''} onClick={() => setLanguage('en')}>English</button>
          <button className={language === 'mr' ? 'active' : ''} onClick={() => setLanguage('mr')}>मराठी</button>
        </div>
      </div>
      <div className="plan-actions">
        <button className="primary-action" onClick={onGenerate} disabled={busy && plan?.status !== 'generating'}>{busy ? 'Drafting…' : plan ? 'Regenerate' : 'Generate plan'}</button>
        {plan?.status === 'generating' && <span className="plan-status working">● AI writer is drafting; showing the deterministic plan meanwhile</span>}
        {plan && plan.status !== 'generating' && <span className="plan-status ready">● {PLAN_SOURCE[plan.source] ?? plan.source}</span>}
        {error && <span className="plan-error">{error}</span>}
      </div>
      <article className="markdown-card">
        {plan ? <div className="markdown-render"><ReactMarkdown remarkPlugins={[remarkGfm]}>{plan.markdown}</ReactMarkdown></div> : (
          <div className="plan-empty"><div className="plan-icon">↯</div><h3>No draft yet</h3><p>Generate a plan for the date chosen on the slider.</p></div>
        )}
      </article>
      <div className="plan-data-note"><strong>Numbers only.</strong> Every figure comes from Talaab's measurements. When the AI writer is on, a number guard rejects any draft containing a number that isn't in the data.</div>
    </section>
  );
}

function AccuracyTab() {
  const [report, setReport] = useState(undefined);
  const [error, setError] = useState('');
  useEffect(() => { fetchBacktest(REPLAY_REGION).then(setReport).catch((err) => setError(err.message)); }, []);

  if (error) return <section className="plan-screen"><div className="error-strip">{error}</div></section>;
  if (report === undefined) return <section className="plan-screen"><p className="muted">Loading backtest…</p></section>;
  if (report === null) return <section className="plan-screen"><p className="muted">No backtest published yet.</p></section>;

  const s = report.summary;
  const noHeat = report.variants?.noHeatAdjustment;
  const before = report.comparisons?.[0];
  const ev = report.evaluated;
  const rows = [
    ['Ponds about to dry (≤ 30 days) that Talaab had marked critical', pct(s.criticalRecall), noHeat && pct(noHeat.criticalRecall), before && pct(before.summary.criticalRecall)],
    ['“Critical” calls that came true within 30 days', pct(s.criticalPrecision), noHeat && pct(noHeat.criticalPrecision), before && pct(before.summary.criticalPrecision)],
    ['Median warning before a pond dried', s.medianLeadDays != null ? `${s.medianLeadDays} days` : '—', noHeat?.medianLeadDays != null && `${noHeat.medianLeadDays} days`, before?.summary.medianLeadDays != null && `${before.summary.medianLeadDays} days`],
    ['Median error of the likely dry date', s.medianAbsErrorDays != null ? `${s.medianAbsErrorDays} days` : '—', noHeat?.medianAbsErrorDays != null && `${noHeat.medianAbsErrorDays} days`, before?.summary.medianAbsErrorDays != null && `${before.summary.medianAbsErrorDays} days`],
    ['Actual dry date inside the predicted range', pct(s.rangeHitRate), noHeat && pct(noHeat.rangeHitRate), before && pct(before.summary.rangeHitRate)],
    ['Predicted dry, but the pond survived the season', s.tooEarly, noHeat?.tooEarly, before?.summary.tooEarly],
  ];
  const dried = report.ponds.filter((p) => p.actualDry);

  return (
    <section className="plan-screen accuracy-screen">
      <div className="plan-hero"><div>
        <span className="eyebrow">HOW ACCURATE IS THIS? · {report.region.name}</span>
        <h2>We replayed 2024 and checked every forecast.</h2>
        <p>For each of {ev.snapshots} satellite passes ({formatDate(ev.from)} – {formatDate(ev.to, { day: 'numeric', month: 'short', year: 'numeric' })}) Talaab forecast every pond using only data available that day; then we compared with what really happened. {ev.pondsThatDried} of {ev.ponds} ponds dried up.</p>
      </div></div>

      <div className="accuracy-headline">
        <div><strong>{pct(s.criticalRecall)}</strong><span>of ponds about to dry were flagged critical in time</span></div>
        <div><strong>{s.medianLeadDays ?? '—'} days</strong><span>median warning before a pond dried</span></div>
        <div><strong>{pct(s.criticalPrecision)}</strong><span>of “critical” calls came true within 30 days</span></div>
      </div>

      <article className="markdown-card">
        <table className="accuracy-table">
          <thead><tr><th>Question</th><th>Talaab</th>{noHeat && <th>Without heat adjustment</th>}{before && <th>{before.label}</th>}</tr></thead>
          <tbody>{rows.map(([q, a, b, c]) => <tr key={q}><td>{q}</td><td><b>{a}</b></td>{noHeat && <td>{b ?? '—'}</td>}{before && <td>{c ?? '—'}</td>}</tr>)}</tbody>
        </table>

        <h3>Ponds that dried</h3>
        <table className="accuracy-table">
          <thead><tr><th>Pond</th><th>Actually dried between</th><th>First marked critical</th><th>Warning</th></tr></thead>
          <tbody>{dried.map((p) => (
            <tr key={p.id}><td><b>{p.id}</b></td><td>{formatDate(p.actualDry.from)} – {formatDate(p.actualDry.to)}</td>
              <td>{p.firstCritical ? formatDate(p.firstCritical) : 'never'}</td><td>{p.leadDays != null ? `${p.leadDays} days` : '—'}</td></tr>
          ))}</tbody>
        </table>
      </article>
      <div className="plan-data-note">
        <strong>Honest limits.</strong> Passes are ~5 days apart (with a 25-day cloud gap in May), so a dry date is known only to within a window; {ev.ponds} real ponds is a small sample; big tanks are often predicted to dry too early.
        {' '}What we found in the raw data and fixed: <a href={`${REPO}/blob/main/docs/data-quality.md`} target="_blank" rel="noreferrer">data-quality write-up</a>.
      </div>
    </section>
  );
}
