import type { Member } from './types';

interface MemberListItemProps {
  member: Member;
  selected: boolean;
  onSelect: (member: Member) => void;
}

export default function MemberListItem({ member, selected, onSelect }: MemberListItemProps) {
  return (
    <button
      type="button"
      className="member-list-item"
      data-component="MemberListItem"
      aria-pressed={selected}
      onClick={() => onSelect(member)}
    >
      <span className="name">{member.name}</span>
      {member.injuries.length > 0 && (
        <span className="meta">{member.injuries.length} injury note(s)</span>
      )}
    </button>
  );
}
