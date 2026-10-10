import { memo, useEffect, useRef, useState } from 'react';
import { formatRange, statusMeta } from '../utils';

// A district has ~400 ponds: draw the list in chunks as it scrolls, and memoise each card, so selecting a pond
// re-renders two cards instead of every card (that re-render was the freeze on each click).
const CHUNK = 60;

const PondCard = memo(function PondCard({ pond, pondIndex, selected, onSelectRef, showTimelapse }) {
  const meta = statusMeta(pond.status);
  const place = (pond.place || '').replace(' (mock)', '') || 'Unnamed location';
  const dryText = pond.status === 'dry' ? 'Dry now' : formatRange(pond.dryBy);
  const accessibleSummary = `${pond.id}, ${meta.label.toLowerCase()}, ${place}, ${pond.areaNowHa ?? 'unknown'} hectares now, ${pond.daysLeft?.likely ?? 'no'} days likely`;
  return (
    <button aria-label={accessibleSummary} className={`pond-card ${selected ? 'selected' : ''}`} style={{ '--pond-index': Math.min(pondIndex, 12) }} onClick={() => onSelectRef.current(pond.id)}>
      <div className="pond-card-top">
        <span className="pond-id">{pond.id}</span>
        {showTimelapse && <span className="timelapse-pill"><svg className="inline-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M5 3.5 12.5 8 5 12.5z" fill="currentColor" stroke="currentColor" strokeLinejoin="round"/></svg> Time-lapse</span>}
        <span className="status-pill" style={{ '--status-color': meta.color, '--status-soft': meta.soft }}>{meta.label}</span>
      </div>
      <div className="pond-place">{place}</div>
      {(pond.taluka || pond.talukaMr) && <div className="pond-taluka">{pond.taluka || 'Taluka'}{pond.talukaMr ? ` · ${pond.talukaMr}` : ''}</div>}
      <div className="pond-metrics">
        <div><strong>{pond.areaNowHa ?? '—'}</strong><span>ha now</span></div>
        <div><strong>{pond.daysLeft?.likely ?? '—'}</strong><span>days likely</span></div>
      </div>
      <div className="dry-line">Dry by <strong>{dryText}</strong></div>
      {pond.flag === 'faster-than-sun' && <span className="inspect-badge">Faster than the sun — inspect</span>}
      {pond.confidence === 'low' && <span className="confidence-badge">Low confidence · confirm next pass</span>}
    </button>
  );
});

export default function PondList({ ponds, selectedId, onSelect, isLive, regionId }) {
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const listRef = useRef(null);
  const sentinelRef = useRef(null);
  const [limit, setLimit] = useState(CHUNK);

  useEffect(() => { setLimit(CHUNK); }, [ponds]);
  const selectedIndex = selectedId ? ponds.findIndex((p) => p.id === selectedId) : -1;
  const shown = Math.min(ponds.length, Math.max(limit, selectedIndex + 1));

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || shown >= ponds.length) return undefined;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) setLimit((n) => n + CHUNK);
    }, { root: listRef.current, rootMargin: '600px' });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [shown, ponds.length]);

  const timelapseRegion = !isLive && (!regionId || regionId === 'latur-2024');
  return (
    <div className="pond-list" ref={listRef}>
      {ponds.slice(0, shown).map((pond, pondIndex) => (
        <PondCard key={pond.id} pond={pond} pondIndex={pondIndex} selected={selectedId === pond.id}
          onSelectRef={onSelectRef} showTimelapse={pond.id === 'P003' && timelapseRegion} />
      ))}
      {shown < ponds.length && <span ref={sentinelRef} className="pond-list-sentinel" aria-hidden="true" />}
    </div>
  );
}
