import { makeMockBacktestSnapshot } from './utils';

const API_BASE = (import.meta.env.VITE_TALAAB_API_URL || '').replace(/\/$/, '');
const MOCK_URL = '/mock/ponds.json';
let mockCache = null;

async function getMock() {
  if (!mockCache) {
    const response = await fetch(MOCK_URL);
    if (!response.ok) throw new Error('Unable to read mock pond data.');
    mockCache = await response.json();
  }
  return mockCache;
}

export async function fetchPonds(asOf) {
  if (API_BASE) {
    const response = await fetch(`${API_BASE}/ponds?region=latur-2024&asOf=${encodeURIComponent(asOf)}`);
    if (!response.ok) throw new Error(`Pond API failed (${response.status}).`);
    return response.json();
  }
  const base = await getMock();
  return makeMockBacktestSnapshot(base, asOf);
}

export async function createPlan({ region, asOf, language }) {
  if (API_BASE) {
    const response = await fetch(`${API_BASE}/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ region, asOf, language }),
    });
    if (!response.ok) throw new Error(`Plan API failed (${response.status}).`);
    return response.json();
  }
  return null;
}
