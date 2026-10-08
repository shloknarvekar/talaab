import { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { AreaChart as ReAreaChart, Area, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Scatter, ReferenceLine } from 'recharts';
import MapView from './components/MapView';
import PondList from './components/PondList';
import { createPlan, fetchPonds } from './api';
import { formatDate, formatRange, sortPonds, statusMeta } from './utils';

function Stat({ label, value, tone }) {
  return <div className={`stat ${tone || ''}`}><span>{label}</span><strong>{value}</strong></div>;
}

export default function App() {
  const [data, setData] = useState(null);
  const [selectedId, setSelectedId] = useState('P003');
  const [satellite, setSatellite] = useState(false);
  const [activeTab, setActiveTab] = useState('ponds');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [sceneIndex, setSceneIndex] = useState(14);

  useEffect(() => {
    fetch('/mock/ponds.json')
      .then((res) => res.json())
      .then((payload) => {
        setData(payload);
        setSceneIndex(Math.max(0, payload.scenes.length - 1));
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const scenes = data?.scenes ?? [];
  const asOf = scenes[sceneIndex]?.date ?? data?.asOf ?? '';

  useEffect(() => {
    if (!asOf || !data || asOf === data.asOf) return;
    setLoading(true);
    fetchPonds(asOf)
      .then((payload) => {
        setData(payload);
        if (!payload.ponds.some((pond) => pond.id === selectedId)) setSelectedId(payload.ponds[0]?.id);
        setError('');
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [asOf]);

  const ponds = useMemo(() => sortPonds(data?.ponds ?? []), [data]);
  const selected = ponds.find((pond) => pond.id === selectedId) ?? ponds[0];
  const counts = useMemo(() => ponds.reduce((acc, pond) => ({ ...acc, [pond.status]: (acc[pond.status] || 0) + 1 }), {}), [ponds]);

  if (!data || loading && !ponds.length) {
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
          <strong>{data.region.name}</strong>
        </div>
        <div className="asof-block">
          <span className="eyebrow">AS OF</span>
          <strong>{formatDate(asOf, { day: '2-digit', month: 'short', year: 'numeric' })}</strong>
          <input aria-label="Choose backtest date" type="range" min="0" max={Math.max(0, scenes.length - 1)} value={sceneIndex} onChange={(event) => setSceneIndex(Number(event.target.value))} />
        </div>
        <div className="sun-share">
          <span className="eyebrow">☀ SUN'S SHARE</span>
          <strong>{data.sunShareMm ?? '—'} <small>mm</small></strong>
          <span className="since">since {formatDate(addDaysLocal(asOf, -45), { day: '2-digit', month: 'short' })}</span>
        </div>
        <button className="tab-button" onClick={() => setActiveTab(activeTab === 'plan' ? 'ponds' : 'plan')}>{activeTab === 'plan' ? '← Ponds' : 'Plan →'}</button>
      </header>

      {error && <div className="error-strip">{error}</div>}

      {activeTab === 'plan' ? (
        <PlanTab data={data} />
      ) : (
        <section className="workspace">
          <aside className="sidebar">
            <div className="sidebar-head">
              <div><span className="eyebrow">POND RISK</span><h2>Act before it dries.</h2></div>
              <span className="count-total">{ponds.length}</span>
            </div>
            <div className="status-summary">
              {['dry', 'critical', 'watch', 'ok'].map((status) => <span key={status} style={{ color: statusMeta(status).color }}>{counts[status] || 0} {statusMeta(status).label.toLowerCase()}</span>)}
            </div>
            <PondList ponds={ponds} selectedId={selectedId} onSelect={setSelectedId} />
            <div className="data-footer">
              <strong>About the data</strong>
              <span>Sentinel-2 via AWS Open Data · Open-Meteo (CC BY 4.0) · OpenStreetMap</span>
              <span><b>2024 replay.</b> Ranges, not exact dates.</span>
            </div>
          </aside>

          <section className="map-panel">
            <div className="map-toolbar">
              <div className="legend">
                {['dry', 'critical', 'watch', 'ok'].map((status) => <span key={status}><i style={{ background: statusMeta(status).color }}></i>{statusMeta(status).label}</span>)}
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

function addDaysLocal(date, delta) {
  const value = new Date(`${date}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() + delta);
  return value.toISOString().slice(0, 10);
}

function PondDetailCard({ pond, asOf }) {
  if (!pond) return <div className="detail-empty">Select a pond.</div>;
  const meta = statusMeta(pond.status);
  const shrinkPct = pond.maxAreaHa ? Math.max(0, Math.round((1 - pond.areaNowHa / pond.maxAreaHa) * 100)) : 0;
  return (
    <div className="detail-card">
      <div className="detail-kicker">SELECTED POND · {asOf}</div>
      <div className="detail-title-row">
        <div><h2>{pond.id}</h2><p>{pond.place.replace(' (mock)', '')}</p></div>
        <span className="status-pill large" style={{ '--status-color': meta.color, '--status-soft': meta.soft }}>{meta.label}</span>
      </div>
      <div className="headline-metric"><strong>{pond.areaNowHa ?? '—'}</strong><span>ha water area now</span></div>
      <div className="metric-grid">
        <Stat label="Max area" value={`${pond.maxAreaHa ?? '—'} ha`} />
        <Stat label="Shrunk" value={`${shrinkPct}%`} />
        <Stat label="Likely dry in" value={pond.daysLeft ? `${pond.daysLeft.likely} d` : 'Stable'} />
        <Stat label="Vs neighbours" value={pond.shrinkVsNeighbours ? `${pond.shrinkVsNeighbours}×` : '—'} tone={pond.shrinkVsNeighbours >= 2 ? 'danger' : ''} />
      </div>
      <AreaChart pond={pond} />
      {pond.flag === 'faster-than-sun' ? (
        <div className="inspection-callout"><div className="callout-icon">!</div><div><strong>Faster than the sun</strong><span>Shrinking {pond.shrinkVsNeighbours}× the neighbour rate. Field inspection recommended.</span></div></div>
      ) : (
        <div className="safe-callout"><span>✓</span><div><strong>Within expected pattern</strong><span>No faster-than-sun flag on this pond.</span></div></div>
      )}
      <div className="dry-by-box"><span className="eyebrow">DRY-BY WINDOW</span><strong>{pond.status === 'dry' ? 'Already dry' : formatRange(pond.dryBy)}</strong><small>Forecast is a range, not an exact day.</small></div>
    </div>
  );
}

function AreaChart({ pond }) {
  const data = pond.history.map((point) => ({ ...point, shortDate: formatDate(point.date, { day: '2-digit', month: 'short' }), validArea: point.valid ? point.areaHa : null, invalidArea: point.valid ? null : point.areaHa }));
  return (
    <div className="chart-wrap">
      <div className="chart-heading"><div><strong>Water area over time</strong><span>Grey points are invalid / suspect passes</span></div><span>{pond.history.length} passes</span></div>
      <div className="chart"><ResponsiveContainer width="100%" height="100%">
        <ReAreaChart data={data} margin={{ top: 12, right: 4, left: -18, bottom: 0 }}>
          <defs><linearGradient id="waterFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3d7c6d" stopOpacity={0.28} /><stop offset="100%" stopColor="#3d7c6d" stopOpacity={0.03} /></linearGradient></defs>
          <CartesianGrid strokeDasharray="3 5" vertical={false} stroke="#e3e9e4" />
          <XAxis dataKey="shortDate" tick={{ fontSize: 10, fill: '#64736a' }} tickLine={false} axisLine={false} minTickGap={18} />
          <YAxis tick={{ fontSize: 10, fill: '#64736a' }} tickLine={false} axisLine={false} width={34} />
          <Tooltip contentStyle={{ borderRadius: 10, border: '1px solid #dfe6e1', boxShadow: '0 8px 20px rgba(14,34,23,.08)' }} formatter={(value, name, item) => [item.payload.areaHa ? `${item.payload.areaHa} ha` : '—', item.payload.valid ? 'Water area' : 'Invalid pass']} labelFormatter={(label) => label} />
          {data.filter((point) => point.invalidArea != null).map((point) => <ReferenceLine key={point.date} x={point.shortDate} stroke="#c6cdc8" strokeDasharray="2 4" />)}
          <Area type="monotone" dataKey="validArea" stroke="#1f6354" strokeWidth={2.5} fill="url(#waterFill)" dot={{ r: 2.5, fill: '#1f6354', strokeWidth: 0 }} activeDot={{ r: 4 }} connectNulls />
          <Scatter dataKey="invalidArea" fill="#9aa6a0" line={false} shape="circle" />
        </ReAreaChart>
      </ResponsiveContainer></div>
    </div>
  );
}

function PlanTab({ data }) {
  const [language, setLanguage] = useState('en');
  const [plan, setPlan] = useState('');
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState('');
  const onGenerate = async () => {
    setStatus('loading');
    try {
      await fetchPonds(data.asOf);
      const payload = await createPlan({ region: data.region.id, asOf: data.asOf, language });
      if (payload) {
        setPlan(payload.markdown || 'No plan returned.');
      } else {
        const { mockPlans } = await import('./data/mockPlan');
        setPlan(mockPlans[language]);
      }
      setStatus('ready');
      setError('');
    } catch (err) {
      setStatus('error');
      setError(err.message);
    }
  };
  return (
    <section className="plan-screen">
      <div className="plan-hero"><div><span className="eyebrow">DISTRICT ACTION PLAN</span><h2>Turn pond risk into a field plan.</h2><p>Mocked locally for the replay; switch on <code>VITE_TALAAB_API_URL</code> to call <code>POST /plan</code>.</p></div><div className="language-toggle"><button className={language === 'en' ? 'active' : ''} onClick={() => setLanguage('en')}>English</button><button className={language === 'mr' ? 'active' : ''} onClick={() => setLanguage('mr')}>मराठी</button></div></div>
      <div className="plan-actions"><button className="primary-action" onClick={onGenerate} disabled={status === 'loading'}>{status === 'loading' ? 'Drafting…' : 'Generate plan'}</button>{status === 'ready' && <span className="ready-dot">● Ready</span>}{error && <span className="plan-error">{error}</span>}</div>
      <article className="markdown-card">{plan ? <MarkdownView source={plan} /> : <div className="plan-empty"><div className="plan-icon">↯</div><h3>No draft yet</h3><p>The plan ranks urgency, inspection flags and actions by quarter.</p></div>}</article>
      <div className="plan-data-note"><strong>Numbers only.</strong> The plan is expected to cite pond IDs and the measurements shown in Talaab; it should not invent figures.</div>
    </section>
  );
}

function MarkdownView({ source }) {
  return (
    <div className="markdown-render">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{source}</ReactMarkdown>
    </div>
  );
}
