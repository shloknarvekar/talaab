import { Fragment, useEffect, useState } from 'react';
import { fetchBacktest } from '../api';
import { formatDate, pct } from '../utils';
import HoverRevealCards from './ui/HoverRevealCards';
const REPO = 'https://github.com/shloknarvekar/talaab';
// The whole-district replay (435 ponds) is the larger, more robust test; the README headlines the same numbers.
const REPLAY_REGION = 'latur-district-2024';

export default function AccuracyTab() {
  const [report, setReport] = useState(undefined);
  const [error, setError] = useState('');
  const [retryVersion, setRetryVersion] = useState(0);
  const [expandedMetric, setExpandedMetric] = useState(null);
  const [outcomeQuery, setOutcomeQuery] = useState('');
  const [outcomeFilter, setOutcomeFilter] = useState('all');
  const [outcomeSort, setOutcomeSort] = useState('warning-desc');
  const [selectedOutcome, setSelectedOutcome] = useState(null);
  useEffect(() => { let active = true; setError(''); setReport(undefined); fetchBacktest(REPLAY_REGION).then((value) => { if (active) setReport(value); }).catch((err) => { if (active) setError(err.message); }); return () => { active = false; }; }, [retryVersion]);
  if (error) return <section className="plan-screen"><div className="tab-error-state" role="alert"><p>Could not load the accuracy backtest: {error}</p><button type="button" className="retry-action" onClick={() => setRetryVersion((v) => v + 1)}>Retry connection</button></div></section>;
  if (report === undefined) return <section className="plan-screen"><p className="muted">Loading backtest…</p></section>;
  if (report === null) return <section className="plan-screen"><p className="muted">No backtest published yet.</p></section>;
  const summary = report.summary ?? {};
  const noHeat = report.variants?.noHeatAdjustment;
  const comparisons = report.comparisons ?? [];
  const evaluated = report.evaluated ?? {};
  const rows = [
    { label: 'Ponds about to dry (≤ 30 days) marked critical in time', key: 'criticalRecall', format: pct, explanation: 'Recall: among ponds that were about to dry, this is the share marked critical in time.' },
    { label: '“Critical” calls that came true within 30 days', key: 'criticalPrecision', format: pct, explanation: 'Precision: among the critical calls, this is the share followed by drying within 30 days.' },
    { label: 'Median warning before a pond dried', key: 'medianLeadDays', format: (v) => v == null ? '—' : `${v} days`, explanation: 'The median is the middle observed warning lead across ponds with a recorded drying outcome.' },
    { label: 'Median error of the likely dry date', key: 'medianAbsErrorDays', format: (v) => v == null ? '—' : `${v} days`, explanation: 'This is the median absolute difference between the predicted likely-dry date and the observed drying date.' },
    { label: 'Actual dry date inside predicted range', key: 'rangeHitRate', format: pct, explanation: 'Range hit rate: how often the observed dry date fell inside the predicted drying window.' },
    { label: 'Predicted dry, but pond survived the season', key: 'tooEarly', format: (v) => v ?? '—', explanation: 'These are the “too early” cases: a dry forecast was made, but the pond did not dry within the replayed season.' },
  ];
  const dried = (report.ponds ?? []).filter((pond) => pond.actualDry);
  const warnedCount = dried.filter((pond) => pond.leadDays != null).length;
  const normalizedQuery = outcomeQuery.trim().toLowerCase();
  const visibleDried = dried
    .filter((pond) => {
      const matchesQuery = !normalizedQuery || String(pond.id).toLowerCase().includes(normalizedQuery);
      const hasWarning = pond.leadDays != null;
      return matchesQuery && (outcomeFilter === 'all' || (outcomeFilter === 'warned' && hasWarning) || (outcomeFilter === 'unwarned' && !hasWarning));
    })
    .sort((a, b) => {
      if (outcomeSort === 'id') return String(a.id).localeCompare(String(b.id), undefined, { numeric: true });
      if (outcomeSort === 'dry-date') return String(a.actualDry?.from ?? '').localeCompare(String(b.actualDry?.from ?? ''));
      if (a.leadDays == null && b.leadDays == null) return 0;
      if (a.leadDays == null) return 1;
      if (b.leadDays == null) return -1;
      return outcomeSort === 'warning-asc' ? a.leadDays - b.leadDays : b.leadDays - a.leadDays;
    });
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

      <HoverRevealCards
        className="accuracy-quick-actions"
        density="compact"
        eyebrow="EXPLORE THE EVIDENCE"
        heading="Go from a headline to the numbers"
        ariaLabel="Accuracy report navigation"
        items={[
          { id: 'accuracy-coverage', title: 'Caught in time', subtitle: 'RECALL', description: 'See the forecast coverage and comparison methods.', detail: 'Recall measures the share of ponds that were about to dry and were marked critical in time. It is not a guarantee for an individual pond.', target: 'accuracy-comparison', actionLabel: 'Compare measures' },
          { id: 'accuracy-warning', title: 'Warning lead', subtitle: 'REAL OUTCOMES', description: 'See ponds that dried and how much warning Talaab gave.', detail: 'Observed outcomes are paired with each pond’s first recorded critical signal and the observed drying range.', target: 'accuracy-outcomes', actionLabel: 'Open outcomes' },
          { id: 'accuracy-false-alarms', title: 'Forecast limits', subtitle: 'UNCERTAINTY', description: 'Read the caveats behind every drying window.', detail: 'Satellite passes are intermittent; cloud gaps widen the observed interval. Dry-by estimates remain ranges rather than exact dates.', target: 'accuracy-limits', actionLabel: 'Read limits' },
          { id: 'accuracy-replay', title: 'Replay the season', subtitle: '2024 TEST', description: 'Return to the published backtest measures.', detail: 'This report replays only the information available on each historical pass, then compares forecasts with later observed outcomes.', target: 'accuracy-comparison', actionLabel: 'View replay' },
        ]}
      />

      <section className="accuracy-data-section accuracy-comparison-section" id="accuracy-comparison">
        <header className="accuracy-data-heading"><div><h3>How the forecasts held up.</h3><p>Each measure is shown alongside any published comparison variants.</p></div></header>
        <div className="accuracy-table-wrap" tabIndex={0} role="region" aria-label="Accuracy compared with simpler methods"><table className="accuracy-table accuracy-table--interactive"><thead><tr><th>Evaluation question <span className="accuracy-sort-hint">click a row to unpack</span></th><th>Talaab</th>{noHeat && <th>Without heat adjustment</th>}{comparisons.map((comparison, index) => <th key={comparison.label ?? index}>{comparison.label ?? `Comparison ${index + 1}`}</th>)}</tr></thead>
          <tbody>{rows.map((row, index) => <Fragment key={row.key}><tr className={expandedMetric === row.key ? 'is-expanded' : ''} style={{ '--row-index': index }}>
            <td><button type="button" className="accuracy-metric-expand" aria-expanded={expandedMetric === row.key} onClick={() => setExpandedMetric((current) => current === row.key ? null : row.key)} aria-controls={`accuracy-metric-detail-${row.key}`}><span className="accuracy-row-index">{String(index + 1).padStart(2, '0')}</span><span>{row.label}</span><span className="accuracy-row-toggle" aria-hidden="true">{expandedMetric === row.key ? '−' : '+'}</span></button></td>
            <td><b>{row.format(summary[row.key])}</b></td>
            {noHeat && <td>{row.format(noHeat[row.key])}</td>}
            {comparisons.map((comparison, comparisonIndex) => <td key={comparison.label ?? comparisonIndex}>{row.format(comparison.summary?.[row.key])}</td>)}
          </tr>{expandedMetric === row.key && <tr className="accuracy-explanation-row" id={`accuracy-metric-detail-${row.key}`}><td colSpan={2 + (noHeat ? 1 : 0) + comparisons.length}><div className="accuracy-explanation"><span className="accuracy-explanation-mark" aria-hidden="true">↳</span><p>{row.explanation}</p><span className="accuracy-explanation-current">Talaab: <b>{row.format(summary[row.key])}</b></span></div></td></tr>}</Fragment>)}</tbody>
        </table></div>
      </section>

      <section className="accuracy-data-section accuracy-outcomes-section" id="accuracy-outcomes">
        <header className="accuracy-data-heading"><div><h3>Ponds that dried.</h3><p>These rows connect a real outcome to the first critical signal recorded for that pond.</p></div><span className="accuracy-outcome-count">{dried.length} <small>observed</small></span></header>
        <div className="accuracy-table-tools" aria-label="Filter observed drying outcomes">
          <div className="accuracy-filter-chips" role="group" aria-label="Outcome warning filter">
            <button type="button" className={outcomeFilter === 'all' ? 'active' : ''} onClick={() => setOutcomeFilter('all')}>All <span>{dried.length}</span></button>
            <button type="button" className={outcomeFilter === 'warned' ? 'active' : ''} onClick={() => setOutcomeFilter('warned')}>Warning recorded <span>{warnedCount}</span></button>
            <button type="button" className={outcomeFilter === 'unwarned' ? 'active' : ''} onClick={() => setOutcomeFilter('unwarned')}>No warning <span>{dried.length - warnedCount}</span></button>
          </div>
          <label className="accuracy-search"><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5"/><path d="m13 13 4 4"/></svg><span className="sr-only">Search pond IDs</span><input type="search" value={outcomeQuery} onChange={(event) => setOutcomeQuery(event.target.value)} placeholder="Find a pond…" /></label>
          <label className="accuracy-sort-select"><span>Sort by</span><select value={outcomeSort} onChange={(event) => setOutcomeSort(event.target.value)}><option value="warning-desc">Most warning first</option><option value="warning-asc">Least warning first</option><option value="dry-date">Drying date</option><option value="id">Pond ID</option></select></label>
        </div>
        <div className="accuracy-table-meta"><span><b>{visibleDried.length}</b> of {dried.length} observed ponds</span><span>Choose a pond ID for its evidence trail</span></div>
        <div className="accuracy-table-wrap" tabIndex={0} role="region" aria-label="Ponds that dried and how much warning Talaab gave"><table className="accuracy-table accuracy-table--interactive"><thead><tr><th>Pond</th><th>Actually dried between</th><th>First marked critical</th><th>Warning</th></tr></thead>
          <tbody>{visibleDried.map((pond, index) => <Fragment key={pond.id}><tr className={selectedOutcome === pond.id ? 'is-expanded' : ''} style={{ '--row-index': index }}>
            <td><button type="button" className="accuracy-pond-id-button" aria-expanded={selectedOutcome === pond.id} aria-controls={`accuracy-pond-detail-${pond.id}`} onClick={() => setSelectedOutcome((current) => current === pond.id ? null : pond.id)}><span className="accuracy-pond-id">{pond.id}</span><span className="accuracy-pond-open" aria-hidden="true">{selectedOutcome === pond.id ? '−' : '+'}</span></button></td>
            <td>{formatDate(pond.actualDry.from, { day: 'numeric', month: 'short', year: 'numeric' })} – {formatDate(pond.actualDry.to, { day: 'numeric', month: 'short', year: 'numeric' })}</td>
            <td>{pond.firstCritical ? formatDate(pond.firstCritical, { day: 'numeric', month: 'short', year: 'numeric' }) : 'never'}</td>
            <td>{pond.leadDays != null ? <span className="accuracy-warning-pill">{pond.leadDays} days</span> : <span className="accuracy-no-warning">No recorded warning</span>}</td>
          </tr>{selectedOutcome === pond.id && <tr className="accuracy-explanation-row" id={`accuracy-pond-detail-${pond.id}`}><td colSpan={4}><div className="accuracy-pond-detail"><div className="accuracy-detail-icon" aria-hidden="true">◌</div><div><strong>{pond.id} · observed outcome</strong><p>The observed drying window runs from {formatDate(pond.actualDry.from, { day: 'numeric', month: 'short', year: 'numeric' })} to {formatDate(pond.actualDry.to, { day: 'numeric', month: 'short', year: 'numeric' })}. {pond.firstCritical ? `The first recorded critical signal was ${formatDate(pond.firstCritical, { day: 'numeric', month: 'short', year: 'numeric' })}.` : 'No first-critical date was recorded in this replay.'}</p></div><span className="accuracy-detail-lead">{pond.leadDays != null ? `${pond.leadDays} day${pond.leadDays === 1 ? '' : 's'} lead` : 'Lead time unavailable'}</span></div></td></tr>}</Fragment>)}
          {visibleDried.length === 0 && <tr><td className="accuracy-empty-row" colSpan={4}>No ponds match those filters. Try another search or choose “All”.</td></tr>}</tbody>
        </table></div>
      </section>

      <div className="plan-data-note accuracy-limits-note" id="accuracy-limits"><span className="plan-note-mark" aria-hidden="true">i</span><div><strong>Honest limits.</strong> Satellite passes are intermittent, cloud gaps widen the drying window, and a dry-by forecast remains a range. <a href={`${REPO}/blob/main/docs/data-quality.md`} target="_blank" rel="noreferrer">Read the data-quality write-up ↗</a>.</div></div>
    </div>
  </section>;
}
