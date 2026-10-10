import { useEffect, useState } from 'react';
import { fetchBacktest } from '../api';
import { formatDate, pct } from '../utils';
const REPO = 'https://github.com/shloknarvekar/talaab';
// The whole-district replay (435 ponds) is the larger, more robust test; the README headlines the same numbers.
const REPLAY_REGION = 'latur-district-2024';

export default function AccuracyTab() {
  const [report, setReport] = useState(undefined);
  const [error, setError] = useState('');
  useEffect(() => { fetchBacktest(REPLAY_REGION).then(setReport).catch((err) => setError(err.message)); }, []);
  if (error) return <section className="plan-screen"><div className="error-strip">{error}</div></section>;
  if (report === undefined) return <section className="plan-screen"><p className="muted">Loading backtest…</p></section>;
  if (report === null) return <section className="plan-screen"><p className="muted">No backtest published yet.</p></section>;
  const summary = report.summary ?? {};
  const noHeat = report.variants?.noHeatAdjustment;
  const comparisons = report.comparisons ?? [];
  const evaluated = report.evaluated ?? {};
  const rows = [
    { label: 'Ponds about to dry (≤ 30 days) marked critical in time', key: 'criticalRecall', format: pct },
    { label: '“Critical” calls that came true within 30 days', key: 'criticalPrecision', format: pct },
    { label: 'Median warning before a pond dried', key: 'medianLeadDays', format: (v) => v == null ? '—' : `${v} days` },
    { label: 'Median error of the likely dry date', key: 'medianAbsErrorDays', format: (v) => v == null ? '—' : `${v} days` },
    { label: 'Actual dry date inside predicted range', key: 'rangeHitRate', format: pct },
    { label: 'Predicted dry, but pond survived the season', key: 'tooEarly', format: (v) => v ?? '—' },
  ];
  const dried = (report.ponds ?? []).filter((pond) => pond.actualDry);
  return <section className="plan-screen accuracy-screen">
    <div className="accuracy-page-shell">
      <header className="plan-hero accuracy-hero">
        <div className="accuracy-hero-copy">
          <h2>{pct(summary.criticalPrecision)} of critical calls <em>came true.</em></h2>
          <p>{report.region?.name ?? 'Latur 2024'} replay: on each of {evaluated.snapshots ?? '—'} satellite passes Talaab forecast {evaluated.ponds ?? 'every'} ponds with only the data available that day, then we checked what really happened.</p>
        </div>
      </header>

      <div className="accuracy-metrics-heading"><div><h3>Warning quality, at a glance.</h3></div><span className="accuracy-metrics-note">Values from the published backtest</span></div>
      <div className="accuracy-headline">
        <div className="accuracy-metric accuracy-metric-recall"><div className="accuracy-metric-label"><span>Caught in time</span></div><strong>{pct(summary.criticalRecall)}</strong><span>of ponds about to dry flagged critical in time</span></div>
        <div className="accuracy-metric accuracy-metric-lead"><div className="accuracy-metric-label"><span>Warning before drying</span></div><strong>{summary.medianLeadDays ?? '—'}<small> days</small></strong><span>median warning before a pond dried</span></div>
        <div className="accuracy-metric accuracy-metric-precision"><div className="accuracy-metric-label"><span>Critical calls that came true</span></div><strong>{pct(summary.criticalPrecision)}</strong><span>of critical calls that came true within 30 days</span></div>
      </div>

      <section className="accuracy-data-section accuracy-comparison-section">
        <header className="accuracy-data-heading"><div><h3>How the forecasts held up.</h3><p>Each measure is shown alongside any published comparison variants.</p></div></header>
        <div className="accuracy-table-wrap" tabIndex={0} role="region" aria-label="Accuracy compared with simpler methods"><table className="accuracy-table"><thead><tr><th>Evaluation question</th><th>Talaab</th>{noHeat && <th>Without heat adjustment</th>}{comparisons.map((comparison, index) => <th key={comparison.label ?? index}>{comparison.label ?? `Comparison ${index + 1}`}</th>)}</tr></thead>
          <tbody>{rows.map((row, index) => <tr key={row.key}><td><span className="accuracy-row-index">{String(index + 1).padStart(2, '0')}</span>{row.label}</td><td><b>{row.format(summary[row.key])}</b></td>
            {noHeat && <td>{row.format(noHeat[row.key])}</td>}
            {comparisons.map((comparison, index) => <td key={comparison.label ?? index}>{row.format(comparison.summary?.[row.key])}</td>)}
          </tr>)}</tbody>
        </table></div>
      </section>

      <section className="accuracy-data-section accuracy-outcomes-section">
        <header className="accuracy-data-heading"><div><h3>Ponds that dried.</h3><p>These rows connect a real outcome to the first critical signal recorded for that pond.</p></div><span className="accuracy-outcome-count">{dried.length} <small>observed</small></span></header>
        <div className="accuracy-table-wrap" tabIndex={0} role="region" aria-label="Ponds that dried and how much warning Talaab gave"><table className="accuracy-table"><thead><tr><th>Pond</th><th>Actually dried between</th><th>First marked critical</th><th>Warning</th></tr></thead>
          <tbody>{dried.map((pond) => <tr key={pond.id}><td><span className="accuracy-pond-id">{pond.id}</span></td><td>{formatDate(pond.actualDry.from, { day: 'numeric', month: 'short', year: 'numeric' })} – {formatDate(pond.actualDry.to, { day: 'numeric', month: 'short', year: 'numeric' })}</td><td>{pond.firstCritical ? formatDate(pond.firstCritical, { day: 'numeric', month: 'short', year: 'numeric' }) : 'never'}</td><td>{pond.leadDays != null ? <span className="accuracy-warning-pill">{pond.leadDays} days</span> : '—'}</td></tr>)}</tbody>
        </table></div>
      </section>

      <div className="plan-data-note accuracy-limits-note"><span className="plan-note-mark" aria-hidden="true">i</span><div><strong>Honest limits.</strong> Satellite passes are intermittent, cloud gaps widen the drying window, and a dry-by forecast remains a range. <a href={`${REPO}/blob/main/docs/data-quality.md`} target="_blank" rel="noreferrer">Read the data-quality write-up ↗</a>.</div></div>
    </div>
  </section>;
}
