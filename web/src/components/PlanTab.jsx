import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { requestPlan } from '../api';
import { formatDate } from '../utils';

const PLAN_SOURCE = {
  bedrock: 'Written with Amazon Bedrock · numbers checked against the data',
  'local-ai': 'AI briefing by an open model in our AWS Lambda · every sentence checked against the data',
  template: 'Built directly from the numbers, no AI',
};

// Plans already seen this visit, by region/date/language: switching back is instant instead of reloading.
const seen = new Map();
const keyOf = (regionId, asOf, language) => `${regionId}|${asOf ?? 'latest'}|${language}`;

export default function PlanTab({ regionId, asOf, regionName }) {
  const [language, setLanguage] = useState('en');
  const [plan, setPlan] = useState(() => seen.get(keyOf(regionId, asOf, 'en')) ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const abort = useRef(null);
  const shownKey = useRef(seen.has(keyOf(regionId, asOf, 'en')) ? keyOf(regionId, asOf, 'en') : null);
  const isDivision = regionId === 'marathwada-2026';

  const runPlan = async (controller, key) => {
    setBusy(true);
    setError('');
    try {
      await requestPlan({ region: regionId, asOf, language }, {
        signal: controller.signal,
        onUpdate: (next) => { if (!controller.signal.aborted) { seen.set(key, next); shownKey.current = key; setPlan(next); } },
      });
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  };

  // Changing place, date or language shows the cached plan at once (or keeps the current one, dimmed) while the
  // matching plan loads, instead of blanking the page.
  useEffect(() => {
    const key = keyOf(regionId, asOf, language);
    const controller = new AbortController();
    abort.current?.abort();
    abort.current = controller;
    const cached = seen.get(key);
    if (cached) { shownKey.current = key; setPlan(cached); }
    setError('');
    if (!cached || cached.status === 'generating') runPlan(controller, key);
    else setBusy(false);
    return () => controller.abort();
    // runPlan intentionally uses the stable props/state dependencies below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [regionId, asOf, language]);

  const regenerate = () => {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    runPlan(controller, keyOf(regionId, asOf, language));
  };

  const stale = plan && busy && shownKey.current !== keyOf(regionId, asOf, language);
  return <section className="plan-screen plan-screen--field-brief">
    <div className="plan-page-shell">
      <header className="plan-head">
        <h2>{isDivision ? 'Division action plan' : 'District action plan'}</h2>
        <p>{regionName} · data as of {asOf ? formatDate(asOf, { day: 'numeric', month: 'short', year: 'numeric' }) : 'the latest pass'} · actions by scarcity period, dry-by dates as ranges</p>
      </header>

      <div className="plan-command-bar">
        <div className="plan-actions">
          <div className="language-toggle" aria-label="Plan language">
            <button className={language === 'en' ? 'active' : ''} onClick={() => setLanguage('en')}>English</button>
            <button className={language === 'mr' ? 'active' : ''} onClick={() => setLanguage('mr')}>मराठी</button>
          </div>
          <button className="secondary-action" onClick={() => window.print()} disabled={!plan?.markdown}>Print / save as PDF</button>
          <button className="secondary-action" onClick={regenerate} disabled={busy}>{busy ? 'Loading…' : 'Refresh'}</button>
        </div>
        <div className="plan-status-stack" aria-live="polite">
          {plan?.status === 'generating' && <span className="plan-status working"><i /> AI briefing on its way; showing the plan built from the numbers meanwhile</span>}
          {plan && plan.status !== 'generating' && <span className="plan-status ready"><i /> {PLAN_SOURCE[plan.source] ?? plan.source}</span>}
          {plan?.aiNote && <span className="plan-ai-note" role="status">{plan.aiNote}</span>}
          {error && <span className="plan-error" role="status">{error}</span>}
        </div>
      </div>

      <article className={`markdown-card plan-document ${busy && plan ? 'is-refreshing' : ''}`} aria-busy={busy}>
        {plan
          ? <div className="markdown-render">{stale && <p className="plan-refreshing">Loading the plan for the selected place…</p>}<ReactMarkdown remarkPlugins={[remarkGfm]}>{plan.markdown}</ReactMarkdown></div>
          : <div className="plan-empty"><h3>{busy ? 'Loading the plan…' : 'Plan unavailable'}</h3><p>{busy ? 'Built from the latest published numbers for this place and date.' : 'Check the connection and press Refresh.'}</p></div>}
      </article>
      <p className="plan-data-note">Forecasts and flags come from Talaab's backend. A faster-than-sun flag suggests pumping; it is not proof.</p>
    </div>
  </section>;
}
