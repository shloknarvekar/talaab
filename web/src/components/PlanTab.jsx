import { Children, cloneElement, isValidElement, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { requestPlan } from '../api';
import { formatDate } from '../utils';
import HoverRevealCards from './ui/HoverRevealCards';

const PLAN_SOURCE = {
  bedrock: 'Written with Amazon Bedrock · numbers checked against the data',
  'local-ai': 'AI briefing by an open model in our AWS Lambda · every sentence checked against the data',
  template: 'Built directly from the numbers, no AI',
};

// Plans already seen this visit, by region/date/language: switching back is instant instead of reloading.
const seen = new Map();
const keyOf = (regionId, asOf, language) => `${regionId}|${asOf ?? 'latest'}|${language}`;


// Keep the API-authored words intact, but make important evidence easier to scan.
const planTokens = /(P\d{2,})|\b(too early(?: to say)?|not visible|no warning|critical|dry(?:ing)?|watch|flagged|inspect(?:ion)?|urgent|pumping|priority|first|before|action)\b|\b(?!20\d{2}\b)(\d+(?:,\d{3})*(?:\.\d+)?%?)\b/gi;

function highlightPlanText(text) {
  const parts = [];
  let cursor = 0;
  for (const match of text.matchAll(planTokens)) {
    const token = match[0];
    const index = match.index ?? 0;
    if (index > cursor) parts.push(text.slice(cursor, index));
    let className = 'plan-highlight-number';
    if (match[1]) className = 'plan-highlight-pond';
    else if (match[2]) {
      const word = match[2].toLowerCase();
      className = /critical|dry|urgent|pumping|flagged/.test(word) ? 'plan-highlight-risk'
        : /watch/.test(word) ? 'plan-highlight-watch'
        : /too early|not visible|no warning/.test(word) ? 'plan-highlight-uncertain'
        : 'plan-highlight-action';
    }
    parts.push(<span className={className} key={`highlight-${index}`}>{token}</span>);
    cursor = index + token.length;
  }
  if (!parts.length) return text;
  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts;
}

function decoratePlanChildren(children) {
  return Children.map(children, (child) => {
    if (typeof child === 'string') return highlightPlanText(child);
    if (!isValidElement(child)) return child;
    // Leave code and custom Markdown components exact: they decorate their own text.
    if (child.type === 'code' || child.type === 'pre' || typeof child.type !== 'string') return child;
    return cloneElement(child, {
      ...child.props,
      children: decoratePlanChildren(child.props.children),
    });
  });
}

function nodeText(children) {
  return Children.toArray(children).map((child) => {
    if (typeof child === 'string' || typeof child === 'number') return String(child);
    if (isValidElement(child)) return nodeText(child.props.children);
    return '';
  }).join(' ');
}

const planMarkdownComponents = {
  h1: ({ node, children, ...props }) => <div className="plan-markdown-cover">
    <div className="plan-markdown-brand"><span className="plan-markdown-brand-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 2.8C9.4 6.3 5.8 10.3 5.8 14.1a6.2 6.2 0 0 0 12.4 0C18.2 10.3 14.6 6.3 12 2.8Z"/><path d="M9.1 14.7a3 3 0 0 0 2.9 3"/></svg></span><span>TALAAB <i> / </i> FIELD ACTION PLAN</span><span className="plan-document-live-dot" aria-hidden="true" /></div>
    <h1 {...props}>{decoratePlanChildren(children)}</h1>
    <div className="plan-cover-rule" aria-hidden="true"><span /></div>
  </div>,
  h2: ({ node, children, ...props }) => <h2 className="plan-markdown-section-title" {...props}>{decoratePlanChildren(children)}</h2>,
  h3: ({ node, children, ...props }) => <h3 className="plan-markdown-subtitle" {...props}>{decoratePlanChildren(children)}</h3>,
  p: ({ node, children, ...props }) => <p {...props}>{decoratePlanChildren(children)}</p>,
  ul: ({ node, children, ...props }) => <ul className="plan-markdown-action-list" {...props}>{children}</ul>,
  ol: ({ node, children, ...props }) => <ol className="plan-markdown-ordered-list" {...props}>{children}</ol>,
  li: ({ node, children, ...props }) => <li {...props}>{decoratePlanChildren(children)}</li>,
  strong: ({ node, children, ...props }) => <strong className="plan-markdown-strong" {...props}>{decoratePlanChildren(children)}</strong>,
  blockquote: ({ node, children, ...props }) => <blockquote className="plan-markdown-callout" {...props}>{decoratePlanChildren(children)}</blockquote>,
  table: ({ node, children, ...props }) => <div className="plan-markdown-table-wrap" role="region" aria-label="Plan data table" tabIndex={0}><table className="plan-markdown-table" {...props}>{children}</table></div>,
  tr: ({ node, children, ...props }) => {
    const text = nodeText(children).toLowerCase();
    const emphasis = /critical|dry now|urgent|inspect first|high priority/.test(text) ? ' is-priority-row'
      : /watch|soon|warning/.test(text) ? ' is-watch-row' : '';
    return <tr className={`plan-markdown-row${emphasis}`} {...props}>{children}</tr>;
  },
  th: ({ node, children, ...props }) => <th {...props}>{decoratePlanChildren(children)}</th>,
  td: ({ node, children, ...props }) => <td {...props}>{decoratePlanChildren(children)}</td>,
};

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

      <HoverRevealCards
        className="plan-quick-actions"
        density="compact"
        eyebrow="FIELD BRIEF TOOLS"
        heading="Make the plan work for you"
        ariaLabel="Plan tools"
        items={[
          { id: 'plan-english', title: 'English briefing', subtitle: 'LANGUAGE', imageUrl: '/imagery/latur-2024/P003/2024-01-16.jpg', description: 'Read the currently published plan in English.', detail: 'The English plan includes the briefing, evidence-backed priorities, and actions ordered by scarcity period.', actionLabel: 'Use English' },
          { id: 'plan-marathi', title: 'मराठी briefing', subtitle: 'LANGUAGE', imageUrl: '/imagery/latur-2024/P003/2024-03-06.jpg', description: 'Switch the plan to Marathi.', detail: 'The language control requests the Marathi version from the plan API; it does not translate forecast maths in the browser.', actionLabel: 'Use Marathi' },
          { id: 'plan-print', title: 'Print a field copy', subtitle: 'PDF / PAPER', imageUrl: '/imagery/latur-2024/P003/2024-04-15.jpg', description: 'Open the print dialog to save the action plan as a PDF.', detail: 'The print layout is designed to remove application controls and keep the plan title, date, and tables legible.', actionLabel: 'Print plan', disabled: !plan?.markdown },
          { id: 'plan-refresh', title: 'Refresh plan', subtitle: 'LATEST RUN', imageUrl: '/imagery/latur-2024/P003/2024-05-30.jpg', description: 'Request the briefing again for the selected place and date.', detail: 'The plan is built from published Talaab outputs. Forecast countdown calculations remain on the backend.', actionLabel: 'Refresh', disabled: busy },
        ]}
        onActivate={(item) => {
          if (item.id === 'plan-english') setLanguage('en');
          else if (item.id === 'plan-marathi') setLanguage('mr');
          else if (item.id === 'plan-print' && plan?.markdown) window.print();
          else if (item.id === 'plan-refresh' && !busy) regenerate();
        }}
      />

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
          {error && <div className="plan-error-wrap" role="alert"><span className="plan-error">{error}</span><button type="button" className="retry-action plan-retry" onClick={regenerate} disabled={busy}>Retry connection</button></div>}
        </div>
      </div>

      <article className={`markdown-card plan-document ${busy && plan ? 'is-refreshing' : ''}`} aria-busy={busy}>
        {plan
          ? <div className="markdown-render">{stale && <p className="plan-refreshing">Loading the plan for the selected place…</p>}<ReactMarkdown remarkPlugins={[remarkGfm]} components={planMarkdownComponents}>{plan.markdown}</ReactMarkdown></div>
          : <div className="plan-empty"><h3>{busy ? 'Loading the plan…' : 'Plan unavailable'}</h3><p>{busy ? 'Built from the latest published numbers for this place and date.' : 'Check the connection and press Refresh.'}</p></div>}
      </article>
      <p className="plan-data-note">Forecasts and flags come from Talaab's backend. A faster-than-sun flag suggests pumping; it is not proof.</p>
    </div>
  </section>;
}
