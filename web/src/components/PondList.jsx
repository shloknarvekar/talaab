import { formatRange, statusMeta } from '../utils';

export default function PondList({ ponds, selectedId, onSelect }) {
  return (
    <div className="pond-list">
      {ponds.map((pond) => {
        const meta = statusMeta(pond.status);
        const dryText = pond.status === 'dry' ? 'Dry now' : formatRange(pond.dryBy);
        return (
          <button key={pond.id} className={`pond-card ${selectedId === pond.id ? 'selected' : ''}`} onClick={() => onSelect(pond.id)}>
            <div className="pond-card-top">
              <span className="pond-id">{pond.id}</span>
              <span className="status-pill" style={{ '--status-color': meta.color, '--status-soft': meta.soft }}>{meta.label}</span>
            </div>
            <div className="pond-place">{(pond.place || '').replace(' (mock)', '') || 'Unnamed location'}</div>
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
