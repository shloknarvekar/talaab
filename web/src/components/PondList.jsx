import { formatRange, placeLabel, statusMeta } from '../utils';

function dryLine(pond) {
  if (pond.status === 'dry') return <strong>Dry now</strong>;
  if (pond.status === 'unknown') return <>Too early to forecast</>;
  if (!pond.dryBy) return <>Stable: not shrinking beyond noise</>;
  return <>Dry by <strong>{formatRange(pond.dryBy)}</strong></>;
}

export default function PondList({ ponds, selectedId, onSelect }) {
  return (
    <div className="pond-list">
      {ponds.map((pond) => {
        const meta = statusMeta(pond.status);
        const dryText = dryLine(pond);
        return (
          <button key={pond.id} className={`pond-card ${selectedId === pond.id ? 'selected' : ''}`} onClick={() => onSelect(pond.id)}>
            <div className="pond-card-top">
              <span className="pond-id">{pond.id}</span>
              <span className="status-pill" style={{ '--status-color': meta.color, '--status-soft': meta.soft }}>{meta.label}</span>
            </div>
            <div className="pond-place">{placeLabel(pond)}</div>
            <div className="pond-metrics">
              <div><strong>{pond.areaNowHa ?? '—'}</strong><span>ha now</span></div>
              <div><strong>{pond.daysLeft?.likely ?? '—'}</strong><span>days likely</span></div>
            </div>
            <div className="dry-line">{dryText}</div>
            {pond.flag === 'faster-than-sun' && <span className="inspect-badge">Faster than the sun — inspect</span>}
          </button>
        );
      })}
    </div>
  );
}
