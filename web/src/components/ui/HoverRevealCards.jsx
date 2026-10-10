import { useId, useState } from 'react';
import './HoverRevealCards.css';

const BASE_PATH = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');

function resolveImage(imageUrl) {
  if (!imageUrl) return '';
  if (/^(https?:)?\/\//i.test(imageUrl) || imageUrl.startsWith('data:')) return imageUrl;
  return `${BASE_PATH}${imageUrl.startsWith('/') ? imageUrl : `/${imageUrl}`}`;
}

/**
 * Image-led action cards that reveal detail on hover, keyboard focus, and tap.
 * This project uses React JSX and its own CSS tokens, so the component intentionally
 * avoids requiring Tailwind, shadcn, clsx, or a TypeScript migration.
 */
export default function HoverRevealCards({
  items = [],
  className = '',
  cardClassName = '',
  heading,
  eyebrow,
  ariaLabel = 'Explore interactive cards',
  density = 'regular',
  onActivate,
}) {
  const id = useId().replace(/:/g, '');
  const [selectedId, setSelectedId] = useState(null);
  const selectedItem = items.find((item) => String(item.id) === String(selectedId));
  const detailId = `${id}-details`;

  const activate = (item) => {
    setSelectedId((current) => String(current) === String(item.id) ? null : item.id);
    if (item.onActivate) {
      item.onActivate(item);
      return;
    }
    if (onActivate) {
      onActivate(item);
      return;
    }
    if (item.target && typeof document !== 'undefined') {
      const target = document.getElementById(item.target);
      const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      target?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    }
  };

  return (
    <section
      className={`hover-reveal-section hover-reveal-section--${density} ${className}`.trim()}
      aria-label={ariaLabel}
    >
      {(eyebrow || heading) && (
        <header className="hover-reveal-heading">
          {eyebrow && <span className="hover-reveal-eyebrow">{eyebrow}</span>}
          {heading && <h3>{heading}</h3>}
        </header>
      )}
      <ul className="hover-reveal-grid">
        {items.map((item, itemIndex) => {
          const active = String(selectedId) === String(item.id);
          return (
            <li className="hover-reveal-item" key={item.id} style={{ '--card-index': itemIndex }}>
              <button
                type="button"
                className={`hover-reveal-card ${active ? 'is-selected' : ''} ${cardClassName}`.trim()}
                onClick={() => activate(item)}
                disabled={Boolean(item.disabled)}
                aria-expanded={active}
                aria-controls={active ? detailId : undefined}
                aria-label={`${item.title}. ${item.subtitle}. ${item.actionLabel || 'Reveal details'}`}
              >
                {item.imageUrl && (
                  <img
                    className={`hover-reveal-card-image ${item.imageClassName || ''}`.trim()}
                    src={resolveImage(item.imageUrl)}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    onError={(event) => { event.currentTarget.style.display = 'none'; }}
                  />
                )}
                <span className="hover-reveal-card-shade" aria-hidden="true" />
                <span className="hover-reveal-card-topline" aria-hidden="true"><span className="hover-reveal-card-number">{String(itemIndex + 1).padStart(2, '0')}</span><span className="hover-reveal-card-orbit"><svg viewBox="0 0 28 28"><circle cx="14" cy="14" r="8"/><circle cx="14" cy="14" r="3"/><path d="M14 1.5v5M14 21.5v5M1.5 14h5M21.5 14h5"/></svg></span></span>
                <span className="hover-reveal-card-copy">
                  <span className="hover-reveal-card-subtitle">{item.subtitle}</span>
                  <strong>{item.title}</strong>
                  {item.description && <span className="hover-reveal-card-description">{item.description}</span>}
                  <span className="hover-reveal-card-action">
                    {active ? 'Close details' : (item.actionLabel || 'Explore')}
                    <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                      <path d="M3 8h9M8 3.5 12.5 8 8 12.5" />
                    </svg>
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {selectedItem && (
        <div className="hover-reveal-detail" id={detailId} role="status" aria-live="polite">
          <div>
            <span>{selectedItem.subtitle}</span>
            <strong>{selectedItem.title}</strong>
            <p>{selectedItem.detail || selectedItem.description}</p>
          </div>
          <button type="button" className="hover-reveal-close" onClick={() => setSelectedId(null)} aria-label="Close card details">×</button>
        </div>
      )}
    </section>
  );
}
