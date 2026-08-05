import type { ChatTurn } from './types';

export default function ChatMessage({ role, text }: ChatTurn) {
  const isCoach = role === 'coach';
  return (
    <div
      className={`kg-msg ${isCoach ? 'kg-msg--coach' : 'kg-msg--ai'}`}
      data-component="ChatMessage"
    >
      <div>{text}</div>
      <div className="kg-msg__meta">{isCoach ? 'Coach' : 'Assistant'}</div>
    </div>
  );
}
