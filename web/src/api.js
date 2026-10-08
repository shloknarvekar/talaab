// Talaab API client. All maths happens on the backend; the web app only displays it.
// Override the API with VITE_TALAAB_API_URL (e.g. a local backend); defaults to the live AWS API.
const DEFAULT_API = 'https://kbvkerr0kc.execute-api.us-west-2.amazonaws.com';
export const API_BASE = (import.meta.env.VITE_TALAAB_API_URL || DEFAULT_API).replace(/\/$/, '');

const PLAN_POLL_MS = 5000;
const PLAN_POLL_LIMIT_MS = 120000;

async function getJson(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options);
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const error = new Error(body?.error || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return body;
}

/** Regions with published snapshots. Synthetic test data is hidden from the website. */
export async function fetchRegions() {
  const { regions } = await getJson('/regions');
  return regions.filter((region) => !region.synthetic);
}

export function fetchPonds(regionId, asOf) {
  return getJson(`/ponds?region=${encodeURIComponent(regionId)}&asOf=${encodeURIComponent(asOf)}`);
}

/** Backtest report for a region, or null if none has been published yet. */
export async function fetchBacktest(regionId) {
  try {
    return await getJson(`/backtest?region=${encodeURIComponent(regionId)}`);
  } catch (error) {
    if (error.status === 404) return null;
    throw error;
  }
}

/**
 * POST /plan returns the deterministic plan instantly. When the AI writer is on, it answers
 * status "generating" and the Bedrock plan arrives on a later call; poll until it is "ready"
 * (or give up after two minutes and keep the deterministic plan). onUpdate gets every response.
 */
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
