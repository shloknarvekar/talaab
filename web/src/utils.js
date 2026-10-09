// Display helpers only. Countdown calculations, flags and status come from the backend.
const STATUS_ORDER = { dry: 0, critical: 1, watch: 2, unknown: 3, ok: 4 };

export const STATUS_META = {
  dry: { label: 'DRY NOW', color: '#7f1d1d', soft: '#3b1a20' },
  critical: { label: 'CRITICAL', color: '#ef4444', soft: '#3d2024' },
  watch: { label: 'WATCH', color: '#f59e0b', soft: '#3b2c16' },
  ok: { label: 'OK', color: '#14b8a6', soft: '#123b37' },
  unknown: { label: 'TOO EARLY', color: '#94a3b8', soft: '#26313e' },
};

export const STATUS_KEYS = ['dry', 'critical', 'watch', 'unknown', 'ok'];

export function formatDate(date, options = { day: 'numeric', month: 'short' }) {
  if (!date) return '—';
  const value = String(date).length >= 10 ? String(date).slice(0, 10) : String(date);
  return new Intl.DateTimeFormat('en-IN', { timeZone: 'UTC', ...options }).format(new Date(`${value}T00:00:00Z`));
}

const WITH_YEAR = { day: 'numeric', month: 'short', year: 'numeric' };
export function formatRange(dryBy) {
  if (!dryBy) return 'No dry-by forecast';
  return `${formatDate(dryBy.likely, WITH_YEAR)} (${formatDate(dryBy.earliest, WITH_YEAR)} – ${formatDate(dryBy.latest, WITH_YEAR)})`;
}

export function addDays(date, delta) {
  const value = new Date(`${String(date).slice(0, 10)}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() + delta);
  return value.toISOString().slice(0, 10);
}

export function sortPonds(ponds) {
  return [...ponds].sort((a, b) =>
    (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9) ||
    (a.daysLeft?.likely ?? Infinity) - (b.daysLeft?.likely ?? Infinity) ||
    a.id.localeCompare(b.id));
}

export function statusMeta(status) { return STATUS_META[status] || STATUS_META.unknown; }
export function placeLabel(pond) { return (pond?.place || '').replace(' (mock)', '') || 'Unnamed location'; }
export function pct(value) { return value == null ? '—' : `${Math.round(value * 100)}%`; }
