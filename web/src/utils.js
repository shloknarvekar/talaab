// Display helpers only. Countdowns, flags and status come from the backend (backend/logic/).
const STATUS_ORDER = { dry: 0, critical: 1, watch: 2, unknown: 3, ok: 4 };

export const STATUS_META = {
  dry: { label: 'DRY', color: '#8f1d2c', soft: '#f8dce1' },
  critical: { label: 'CRITICAL', color: '#c2412d', soft: '#ffe5df' },
  watch: { label: 'WATCH', color: '#b7791f', soft: '#fff0c8' },
  ok: { label: 'OK', color: '#2f855a', soft: '#dff5e8' },
  unknown: { label: 'TOO EARLY', color: '#64748b', soft: '#e2e8f0' },
};

export const STATUS_KEYS = ['dry', 'critical', 'watch', 'unknown', 'ok'];

export function formatDate(date, options = { day: 'numeric', month: 'short' }) {
  if (!date) return '—';
  return new Intl.DateTimeFormat('en-IN', { timeZone: 'UTC', ...options }).format(new Date(`${date}T00:00:00Z`));
}

const WITH_YEAR = { day: 'numeric', month: 'short', year: 'numeric' };

/** Always with the year: a forecast like "22 Feb" is ambiguous when it may fall next year. */
export function formatRange(dryBy) {
  if (!dryBy) return 'No dry-by forecast';
  return `${formatDate(dryBy.likely, WITH_YEAR)} (${formatDate(dryBy.earliest, WITH_YEAR)} – ${formatDate(dryBy.latest, WITH_YEAR)})`;
}

export function addDays(date, delta) {
  const value = new Date(`${date}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() + delta);
  return value.toISOString().slice(0, 10);
}

/** Most urgent first: by status, then by likely days left. */
export function sortPonds(ponds) {
  return [...ponds].sort(
    (a, b) =>
      (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9) ||
      (a.daysLeft?.likely ?? Infinity) - (b.daysLeft?.likely ?? Infinity) ||
      a.id.localeCompare(b.id),
  );
}

export function statusMeta(status) {
  return STATUS_META[status] || STATUS_META.unknown;
}

export function placeLabel(pond) {
  return (pond?.place || '').replace(' (mock)', '') || 'Unnamed location';
}

export function pct(value) {
  return value == null ? '—' : `${Math.round(value * 100)}%`;
}
