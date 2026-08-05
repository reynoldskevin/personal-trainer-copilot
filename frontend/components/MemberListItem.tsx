import type { Member } from './types';
import { initials } from './util';

interface MemberListItemProps {
  member: Member;
  selected: boolean;
  onSelect: (member: Member) => void;
}

export default function MemberListItem({ member, selected, onSelect }: MemberListItemProps) {
  const primaryInjury = member.injuries[0];
  const primaryGoal = member.goals[0];
  return (
    <button
      type="button"
      className={`kg-list-item${selected ? ' is-hover' : ''}`}
      data-component="MemberListItem"
      aria-pressed={selected}
      onClick={() => onSelect(member)}
      style={{
        width: '100%',
        textAlign: 'left',
        color: 'inherit',
        font: 'inherit',
        appearance: 'none',
      }}
    >
      <div className="kg-avatar">{initials(member.name)}</div>
      <div className="kg-grow">
        <div className="kg-h3">{member.name}</div>
        {primaryGoal && <p className="kg-mono">{primaryGoal}</p>}
      </div>
      {primaryInjury ? (
        <span className="kg-chip kg-chip--warn">
          <span className="kg-chip__dot" />
          {primaryInjury}
        </span>
      ) : (
        <span className="kg-chip kg-chip--safe kg-chip--sm">Cleared</span>
      )}
      <span className="kg-mono" style={{ fontSize: 14 }}>
        &rsaquo;
      </span>
    </button>
  );
}
