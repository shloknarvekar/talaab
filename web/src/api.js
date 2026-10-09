// Talaab API client. Forecasting maths stays on the backend; the web only presents results.
const DEFAULT_API = 'https://kbvkerr0kc.execute-api.us-west-2.amazonaws.com';
export const API_BASE = (import.meta.env.VITE_TALAAB_API_URL || DEFAULT_API).replace(/\/$/, '');

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

/** Regions with published snapshots. Synthetic test data is intentionally hidden. */
export async function fetchRegions() {
  const { regions } = await getJson('/regions');
  return regions.filter((region) => !region.synthetic);
}

export function fetchPonds(regionId, asOf) {
  return getJson(`/ponds?region=${encodeURIComponent(regionId)}&asOf=${encodeURIComponent(asOf)}`);
}

/** Alert timeline. Regions without a published timeline may return 404; that is not fatal. */
export async function fetchAlerts(regionId) {
  try {
    const payload = await getJson(`/alerts?region=${encodeURIComponent(regionId)}`);
    if (Array.isArray(payload)) return payload;
    return payload.alerts ?? payload.timeline ?? payload.items ?? [];
  } catch (error) {
    if (error.status === 404) return [];
    throw error;
  }
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
