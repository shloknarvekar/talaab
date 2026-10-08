const STATUS_ORDER = { dry: 0, critical: 1, watch: 2, ok: 3, unknown: 4 };

export const STATUS_META = {
  dry: { label: 'DRY', color: '#8f1d2c', soft: '#f8dce1' },
  critical: { label: 'CRITICAL', color: '#c2412d', soft: '#ffe5df' },
  watch: { label: 'WATCH', color: '#b7791f', soft: '#fff0c8' },
  ok: { label: 'OK', color: '#2f855a', soft: '#dff5e8' },
  unknown: { label: 'UNKNOWN', color: '#64748b', soft: '#e2e8f0' },
};

export function formatDate(date, options = { day: 'numeric', month: 'short' }) {
  if (!date) return '—';
  return new Intl.DateTimeFormat('en-IN', { timeZone: 'UTC', ...options }).format(new Date(`${date}T00:00:00Z`));
}

export function formatRange(dryBy) {
  if (!dryBy) return 'No dry-by forecast';
  const likely = formatDate(dryBy.likely);
  const earliest = formatDate(dryBy.earliest);
  const latest = formatDate(dryBy.latest);
  return `${likely} (${earliest} – ${latest})`;
}

export function sortPonds(ponds) {
  return [...ponds].sort((a, b) => (a.daysLeft?.likely ?? Infinity) - (b.daysLeft?.likely ?? Infinity));
}

export function statusMeta(status) {
  return STATUS_META[status] || STATUS_META.unknown;
}

function diffDays(a, b) {
  return Math.round((new Date(`${a}T00:00:00Z`) - new Date(`${b}T00:00:00Z`)) / 86400000);
}

function addDays(date, days) {
  const value = new Date(`${date}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() + Math.round(days));
  return value.toISOString().slice(0, 10);
}

function linearFit(points) {
  if (points.length < 2) return { slope: 0, se: 0 };
  const t0 = points[0].date;
  const x = points.map((point) => diffDays(point.date, t0));
  const y = points.map((point) => point.areaHa);
  const xMean = x.reduce((s, v) => s + v, 0) / x.length;
  const yMean = y.reduce((s, v) => s + v, 0) / y.length;
  const denom = x.reduce((s, v) => s + (v - xMean) ** 2, 0) || 1;
  const slope = x.reduce((s, v, i) => s + (v - xMean) * (y[i] - yMean), 0) / denom;
  const intercept = yMean - slope * xMean;
  const residuals = y.map((value, i) => value - (intercept + slope * x[i]));
  const se = x.length > 2
    ? Math.sqrt(residuals.reduce((s, r) => s + r ** 2, 0) / (x.length - 2)) / Math.sqrt(denom)
    : 0;
  return { slope, se };
}

/**
 * Local-only backtest fallback. The real API already returns these fields.
 * This uses only points <= selected asOf so the slider behaves honestly against the mock history.
 */
export function makeMockBacktestSnapshot(base, selectedAsOf) {
  if (selectedAsOf === base.asOf) return base;
  const ponds = base.ponds.map((pond) => {
    const history = pond.history.filter((p) => p.date <= selectedAsOf);
    const validHistory = history.filter((p) => p.valid);
    if (!validHistory.length) return { ...pond, history, areaNowHa: null, status: 'unknown', dryBy: null, daysLeft: null };
    const latest = validHistory.at(-1);
    const maxAreaHa = Math.max(...validHistory.map((p) => p.areaHa));
    if (latest.areaHa < maxAreaHa * 0.05) {
      return {
        ...pond,
        history,
        maxAreaHa,
        areaNowHa: latest.areaHa,
        dryBy: null,
        daysLeft: { min: 0, likely: 0, max: 0 },
        status: 'dry',
        flag: null,
        shrinkVsNeighbours: pond.shrinkVsNeighbours,
      };
    }
    if (validHistory.length < 3) {
      return { ...pond, history, maxAreaHa, areaNowHa: latest.areaHa, dryBy: null, daysLeft: null, status: 'unknown' };
    }
    const fit = linearFit(validHistory);
    if (fit.slope >= 0 || fit.slope + 2 * fit.se >= 0) {
      return { ...pond, history, maxAreaHa, areaNowHa: latest.areaHa, dryBy: null, daysLeft: null, status: 'ok', flag: null };
    }
    const threshold = 0.05 * maxAreaHa;
    const toTarget = Math.max(0, (latest.areaHa - threshold) / Math.abs(fit.slope));
    const spread = Math.max(toTarget * 0.2, fit.se ? fit.se / Math.abs(fit.slope) : toTarget * 0.2);
    const likelyDays = Math.min(365, Math.round(toTarget));
    const minDays = Math.max(0, Math.round(toTarget - spread));
    const maxDays = Math.min(365, Math.round(toTarget + spread));
    const dryBy = {
      earliest: addDays(selectedAsOf, minDays),
      likely: addDays(selectedAsOf, likelyDays),
      latest: addDays(selectedAsOf, maxDays),
    };
    const status = likelyDays < 30 ? 'critical' : likelyDays <= 90 ? 'watch' : 'ok';
    const flag = pond.flag === 'faster-than-sun' && selectedAsOf >= '2024-03-01' ? 'faster-than-sun' : null;
    return {
      ...pond,
      history,
      maxAreaHa,
      areaNowHa: latest.areaHa,
      dryBy,
      daysLeft: { min: minDays, likely: likelyDays, max: maxDays },
      status,
      flag,
    };
  });
  return { ...base, asOf: selectedAsOf, ponds };
}

export function sceneStatusFor(pond, date) {
  const entry = pond.history.find((item) => item.date === date);
  return entry?.valid === false ? 'invalid' : 'valid';
}

export function getLatestValidHistory(pond) {
  return pond.history.filter((point) => point.valid).at(-1);
}
