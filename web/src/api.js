// Talaab API client. Forecasting maths stays on the backend; the web only presents results.
const DEFAULT_API = 'https://kbvkerr0kc.execute-api.us-west-2.amazonaws.com';
export const API_BASE = (import.meta.env.VITE_TALAAB_API_URL || DEFAULT_API).replace(/\/$/, '');

/** District imagery is served through the API; the small Latur box uses committed public assets. */
export function imageryBase(regionId) {
  return regionId?.includes('district') ? `${API_BASE}/imagery` : '/imagery';
}

const PLAN_POLL_MS = 5000;
const PLAN_POLL_LIMIT_MS = 120000;

async function getJson(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options);
  let body = null;
  try { body = await response.json(); } catch { body = null; }
  if (!response.ok) {
    const error = new Error(body?.error || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return body;
}

/** Published regions and division summaries advertised by GET /regions. */
export async function fetchRegions() {
  const payload = await getJson('/regions');
  return {
    regions: (payload?.regions ?? []).filter((region) => !region.synthetic),
    divisions: payload?.divisions ?? [],
  };
}

export function fetchPonds(regionId, asOf) {
  return getJson(`/ponds?region=${encodeURIComponent(regionId)}&asOf=${encodeURIComponent(asOf)}`);
}

const ALERT_TEXT = {
  dry: (a) => `Dried up: ${a.areaNowHa} ha left of ${a.maxAreaHa} ha`,
  critical: (a) => `Turned critical: likely dry ${a.dryBy?.likely ?? 'soon'}, ${a.areaNowHa} of ${a.maxAreaHa} ha left`,
  flag: (a) => `Shrinking ${a.ratio}× faster than nearby ponds (suggests pumping, not proof)`,
};

/**
 * GET /alerts returns email events; flatten them to an item per pond alert.
 * Replay timelines are simulated. Missing timelines are not fatal.
 */
export async function fetchAlerts(regionId) {
  try {
    const payload = await getJson(`/alerts?region=${encodeURIComponent(regionId)}`);
    return (payload?.events ?? []).flatMap((event) => (event.alerts ?? []).map((alert) => ({
      date: event.asOf,
      pondId: alert.id,
      type: alert.reason,
      place: alert.place,
      message: (ALERT_TEXT[alert.reason] ?? (() => 'Pond risk changed'))(alert),
    })));
  } catch (error) {
    if (error.status === 404) return [];
    throw error;
  }
}

/** Division-level summary and district boundaries come directly from the API. */
export function fetchDivision(divisionId = 'marathwada-2026', asOf) {
  const query = new URLSearchParams({ division: divisionId });
  if (asOf) query.set('asOf', asOf);
  return getJson(`/division?${query.toString()}`);
}

export function fetchDivisionOutlines(divisionId = 'marathwada-2026') {
  return getJson(`/division/outlines?division=${encodeURIComponent(divisionId)}`);
}

/** Backtest report for a region, or null when none has been published. */
export async function fetchBacktest(regionId) {
  try { return await getJson(`/backtest?region=${encodeURIComponent(regionId)}`); }
  catch (error) { if (error.status === 404) return null; throw error; }
}

/** Poll POST /plan while the plan is being generated. */
export async function requestPlan({ region, asOf, language }, { onUpdate, signal } = {}) {
  const body = JSON.stringify({ region, asOf, language });
  const post = () => getJson('/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, signal });
  const started = Date.now();
  let plan = await post();
  onUpdate?.(plan);
  while (plan.status === 'generating' && Date.now() - started < PLAN_POLL_LIMIT_MS) {
    await new Promise((resolve) => setTimeout(resolve, PLAN_POLL_MS));
    if (signal?.aborted) break;
    plan = await post();
    onUpdate?.(plan);
  }
  return plan;
}
