import type { MemberDetail } from './types';
import InjuryBadge from './InjuryBadge';
import { initials } from './util';

export default function MemberContextRail({
  detail,
  onBack,
}: {
  detail: MemberDetail;
  onBack?: () => void;
}) {
  const totals = detail.adherence.reduce(
    (acc, a) => {
      acc.planned += a.planned;
      acc.completed += a.completed;
      return acc;
    },
    { planned: 0, completed: 0 }
  );
  const adherencePct =
    totals.planned > 0 ? Math.round((totals.completed / totals.planned) * 100) : 0;
  const sessions = detail.recent_workouts.length;

  return (
    <div className="kg-card" data-component="MemberContextRail" style={{ height: '100%' }}>
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          className="kg-mono"
          style={{
            display: 'inline-block',
            marginBottom: 'var(--space-md)',
            background: 'none',
            border: 0,
            padding: 0,
            color: 'var(--color-accent-2)',
            cursor: 'pointer',
          }}
        >
          ‹ All members
        </button>
      )}
      <div className="kg-avatar kg-avatar--lg">{initials(detail.name)}</div>
      <h2 className="kg-h1" style={{ margin: 'var(--space-md) 0 4px' }}>
        {detail.name}
      </h2>
      <p className="kg-mono">{detail.id}</p>

      <div className="kg-stack" style={{ gap: 'var(--space-sm)', margin: 'var(--space-lg) 0' }}>
        <div className="kg-between">
          <span className="kg-mono">Adherence</span>
          <span className="kg-h3" style={{ color: 'var(--color-safe)' }}>
            {adherencePct}%
          </span>
        </div>
        <div className="kg-between">
          <span className="kg-mono">Sessions logged</span>
          <span className="kg-h3">{sessions}</span>
        </div>
      </div>

      <p className="kg-eyebrow" style={{ marginBottom: 'var(--space-sm)' }}>
        Active injuries
      </p>
      {detail.injuries.length === 0 ? (
        <div className="kg-row-f" data-component="InjuryBadge">
          <span className="kg-chip kg-chip--safe kg-chip--sm">Cleared</span>
        </div>
      ) : (
        <div className="kg-row-f">
          {detail.injuries.map((injury) => (
            <InjuryBadge key={injury} injury={injury} />
          ))}
        </div>
      )}
    </div>
  );
}
