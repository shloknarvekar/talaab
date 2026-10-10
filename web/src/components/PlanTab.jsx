import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { requestPlan } from '../api';
import { formatDate } from '../utils';

const PLAN_SOURCE = {
  bedrock: 'Written with Amazon Bedrock · numbers checked against the data',
  'local-ai': 'AI briefing by an open model in our AWS Lambda · every sentence checked against the data',
  template: 'Deterministic plan · built directly from the numbers, no AI',
};

export default function PlanTab({ regionId, asOf, regionName }) {
  const [language, setLanguage] = useState('en');
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const abort = useRef(null);

  const runPlan = async (controller) => {
    setBusy(true);
    setError('');
    try {
      await requestPlan({ region: regionId, asOf, language }, { onUpdate: setPlan, signal: controller.signal });
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  };

  // Opening the tab and changing date/language automatically load the matching plan.
  useEffect(() => {
    const controller = new AbortController();
    abort.current?.abort();
    abort.current = controller;
    setPlan(null);
    setError('');
    runPlan(controller);
    return () => controller.abort();
    // runPlan intentionally uses the stable props/state dependencies below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [regionId, asOf, language]);

  const regenerate = () => {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    runPlan(controller);
  };

  const planStateLabel = plan?.status === 'generating'
    ? 'DRAFT IN PROGRESS'
    : plan
      ? (plan.status === 'template' ? 'TEMPLATE READY' : 'BRIEFING READY')
      : busy
        ? 'LOADING SOURCE'
        : 'AWAITING BRIEF';

  return <section className="plan-screen plan-screen--field-brief">
    <div className="plan-page-shell">
      <header className="plan-hero plan-hero--brief">
        <div className="plan-hero-copy">
          <span className="eyebrow">{regionId === 'marathwada-2026' ? 'DIVISION ACTION PLAN' : 'DISTRICT ACTION PLAN'} · {regionName} · {asOf ? formatDate(asOf, { day: '2-digit', month: 'short', year: 'numeric' }) : 'LATEST PUBLISHED'}</span>
          <h2>Turn pond risk<br /><em>into a field plan.</em></h2>
          <p>Village-level actions, grouped by scarcity period, with the pond evidence behind each decision.</p>
          <div className="plan-hero-proofline"><span className="plan-proof-dot" /> Only published observations for the selected date <span className="plan-proof-divider">/</span> Ranges, not exact dates</div>
        </div>
        <aside className="plan-overview-card" aria-label="Plan snapshot details">
          <div className="plan-overview-card-top"><span>FIELD BRIEF <b>/{language === 'mr' ? ' MR' : ' EN'}</b></span><span className={`plan-state-tag ${planStateLabel === 'BRIEFING READY' ? 'is-ready' : planStateLabel === 'DRAFT IN PROGRESS' || planStateLabel === 'LOADING SOURCE' ? 'is-working' : ''}`}><i />{planStateLabel}</span></div>
          <div className="plan-overview-headline">A clear next step<br /><em>for every field team.</em></div>
          <div className="plan-overview-meta">
            <div><span>REGION</span><strong>{regionName}</strong></div>
            <div><span>SNAPSHOT</span><strong>{asOf ? formatDate(asOf, { day: '2-digit', month: 'short', year: 'numeric' }) : 'Latest published'}</strong></div>
          </div>
          <div className="plan-overview-foot"><span>01</span><span>Data-led priorities · human review</span></div>
        </aside>
      </header>

      <div className="plan-command-bar">
        <div className="plan-actions">
          <button className="primary-action" onClick={regenerate} disabled={busy}>{busy ? 'Drafting…' : 'Regenerate plan'} <span aria-hidden="true">↻</span></button>
          <button className="secondary-action" onClick={() => window.print()} disabled={!plan?.markdown}>Download / print plan <span aria-hidden="true">↗</span></button>
          <div className="language-toggle" aria-label="Plan language">
            <button className={language === 'en' ? 'active' : ''} onClick={() => setLanguage('en')}>English</button>
            <button className={language === 'mr' ? 'active' : ''} onClick={() => setLanguage('mr')}>मराठी</button>
          </div>
        </div>
        <div className="plan-status-stack" aria-live="polite">
          {plan?.status === 'generating' && <span className="plan-status working"><i /> Drafting; showing the deterministic plan meanwhile</span>}
          {plan && plan.status !== 'generating' && <span className="plan-status ready"><i /> {PLAN_SOURCE[plan.source] ?? plan.source}</span>}
          {plan?.aiNote && <span className="plan-ai-note" role="status">{plan.aiNote}</span>}
          {error && <span className="plan-error" role="status">{error}</span>}
        </div>
      </div>

      <div className="plan-document-heading">
        <div><span className="eyebrow">01 / THE FIELD DOCUMENT</span><h3>Recommended actions</h3></div>
        <span className="plan-document-stamp">{language === 'mr' ? 'मराठी संस्करण' : 'ENGLISH EDITION'} <i /> {plan?.source === 'local-ai' ? 'AI briefing attached' : plan?.source === 'bedrock' ? 'AI plan' : 'Evidence-led template'}</span>
      </div>
      <article className="markdown-card plan-document">
        {plan ? <div className="markdown-render"><ReactMarkdown remarkPlugins={[remarkGfm]}>{plan.markdown}</ReactMarkdown></div> : <div className="plan-empty"><div className="plan-icon">↯</div><h3>{busy ? 'Preparing the district plan' : 'Plan unavailable'}</h3><p>{busy ? 'The selected date and language are being loaded.' : 'Check the API connection and regenerate.'}</p></div>}
      </article>
      <div className="plan-data-note"><span className="plan-note-mark" aria-hidden="true">i</span><div><strong>Forecasting stays evidence-led.</strong> Forecasts and flags come from Talaab's backend. A faster-than-sun flag suggests pumping; it is not proof.</div></div>
    </div>
  </section>;
}
