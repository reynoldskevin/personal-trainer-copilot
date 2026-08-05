import type { MemberDetail } from './types';
import InjuryBadge from './InjuryBadge';

export default function MemberContextRail({ detail }: { detail: MemberDetail }) {
  return (
    <aside className="panel" data-component="MemberContextRail">
      <h2>{detail.name}</h2>
      <div className="rail-section">
        <h3>Injuries</h3>
        {detail.injuries.length === 0 ? (
          <span className="meta">None recorded</span>
        ) : (
          detail.injuries.map((injury) => <InjuryBadge key={injury} injury={injury} />)
        )}
      </div>
    </aside>
  );
}
