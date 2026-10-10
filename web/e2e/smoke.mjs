// Browser smoke test for the web app: every tab, real data from the live API, in a real Chrome.
//   npm run test:e2e                      (against `vite preview --port 5173`, an origin the API's CORS allows)
//   E2E_URL=https://… npm run test:e2e    (against any deployed site)
// Exits non-zero if any check fails. Written after district satellite thumbnails silently 404ed for days.
import fs from 'node:fs';
import puppeteer from 'puppeteer-core';

const URL = process.env.E2E_URL || 'http://localhost:5173';
const CHROME = process.env.CHROME_PATH || [
  '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium-browser', '/usr/bin/chromium',
  'C:/Program Files/Google/Chrome/Application/chrome.exe', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].find((p) => fs.existsSync(p));
if (!CHROME) { console.error('No Chrome found; set CHROME_PATH'); process.exit(2); }

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failed = 0;
const check = (name, ok, detail = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`); if (!ok) failed += 1; };

const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] });
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900 });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => { if (m.type() === 'error' && !/favicon/.test(m.text())) errors.push(m.text()); });

const click = (text, byLabel = false) => page.evaluate((text, byLabel) => {
  const el = [...document.querySelectorAll('button,[role=tab],summary')]
    .find((e) => (byLabel ? (e.getAttribute('aria-label') || e.textContent.trim()) : e.textContent.trim()).startsWith(text) && e.getClientRects().length);
  el?.click(); return Boolean(el);
}, text, byLabel);
const region = (id) => page.evaluate((id) => { const el = document.querySelector(`[data-region="${id}"]`); el?.click(); return Boolean(el); }, id);
const waitFor = async (fn, ms = 20000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await page.evaluate(fn)) return true; await sleep(500); } return false; };
const thumbs = () => page.evaluate(() => { const im = [...document.querySelectorAll('.imagery-strip img')]; return { all: im.length, loaded: im.filter((i) => i.complete && i.naturalWidth > 0).length, broken: im.filter((i) => i.complete && i.naturalWidth === 0).length }; });

try {
  await page.goto(URL, { waitUntil: 'networkidle2', timeout: 90000 });
  check('landing page', await click('Explore'), 'Explore button');

  check('live map draws ponds', await waitFor(() => document.querySelectorAll('.pond-list > .pond-card').length > 50, 30000));

  // A district pond: its satellite passes come from S3 through one signed-links call.
  await page.evaluate(() => document.querySelector('.pond-list > .pond-card')?.click());
  await waitFor(() => document.querySelector('.detail-card'));
  await waitFor(() => [...document.querySelectorAll('.imagery-strip img')].some((i) => i.complete && i.naturalWidth > 0), 20000);
  let t = await thumbs();
  check('district pond thumbnails load', t.loaded > 0 && t.broken === 0, `${t.loaded}/${t.all} loaded, ${t.broken} broken`);

  // The 2024 replay box ships its thumbnails with the site.
  check('replay region button', await region('latur-2024'));
  await waitFor(() => document.querySelectorAll('.pond-list > .pond-card').length > 5 && document.querySelectorAll('.pond-list > .pond-card').length < 50);
  await click('P003', true);
  await waitFor(() => [...document.querySelectorAll('.imagery-strip img')].some((i) => i.complete && i.naturalWidth > 0), 20000);
  t = await thumbs();
  check('replay pond thumbnails load', t.loaded > 0 && t.broken === 0, `${t.loaded}/${t.all} loaded`);
  check('no card scrolls inside itself', await page.evaluate(() => [...document.querySelectorAll('.pond-list > .pond-card')].every((c) => c.scrollHeight <= c.clientHeight + 1)));

  await click('Plan');
  check('plan renders', await waitFor(() => document.querySelector('.markdown-render h1')?.textContent.length > 10, 40000));

  await click('Accuracy');
  check('accuracy shows the backtest', await waitFor(() => /\d+%/.test(document.querySelector('.accuracy-hero h2')?.textContent || ''), 20000));
  check('region bar hidden on accuracy', await page.evaluate(() => getComputedStyle(document.querySelector('.app-context-row')).display === 'none'));

  await click('About');
  check('about shows real satellite frames', await waitFor(() => { const f = [...document.querySelectorAll('.portfolio-card-frame')]; return f.length === 4 && f.every((i) => i.complete && i.naturalWidth > 0); }, 20000));

  await click('Pond map'); await sleep(1500);
  check('division button', await region('marathwada-2026'));
  check('division page: 8 districts', await waitFor(() => document.querySelectorAll('.division-district-row').length === 8, 30000));
  check('division map: 8 outlines', await waitFor(() => document.querySelectorAll('.division-map-canvas path').length === 8, 20000));

  check('no console errors', errors.length === 0, errors.slice(0, 3).join(' | '));
} catch (err) {
  check('test ran to the end', false, err.message);
} finally {
  await browser.close();
}
console.log(failed ? `\n${failed} check(s) failed` : '\nall checks passed');
process.exit(failed ? 1 : 0);
