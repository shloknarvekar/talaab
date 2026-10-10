import { formatRange, statusMeta } from '../utils';

export default function PondList({ ponds, selectedId, onSelect, isLive, regionId }) {
  return (
    <div className="pond-list">
      {ponds.map((pond, pondIndex) => {
        const meta = statusMeta(pond.status);
        const place = (pond.place || '').replace(' (mock)', '') || 'Unnamed location';
        const dryText = pond.status === 'dry' ? 'Dry now' : formatRange(pond.dryBy);
        const accessibleSummary = `${pond.id}, ${meta.label.toLowerCase()}, ${place}, ${pond.areaNowHa ?? 'unknown'} hectares now, ${pond.daysLeft?.likely ?? 'no'} days likely`;
        return (
          <button key={pond.id} aria-label={accessibleSummary} className={`pond-card ${selectedId === pond.id ? 'selected' : ''}`} style={{ '--pond-index': pondIndex }} onClick={() => onSelect(pond.id)}>
            <div className="pond-card-top">
              <span className="pond-id">{pond.id}</span>
              {pond.id === 'P003' && !isLive && (!regionId || regionId === 'latur-2024') && <span className="timelapse-pill"><svg className="inline-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M5 3.5 12.5 8 5 12.5z" fill="currentColor" stroke="currentColor" strokeLinejoin="round"/></svg> Time-lapse</span>}
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
      })}
    </div>
  );
}
