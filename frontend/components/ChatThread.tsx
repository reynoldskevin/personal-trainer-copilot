import type { ChatTurn } from './types';
import ChatMessage from './ChatMessage';

export default function ChatThread({ turns }: { turns: ChatTurn[] }) {
  return (
    <div className="kg-thread" data-component="ChatThread">
      {turns.length === 0 ? (
        <p className="kg-p">Ask a grounded question about this member to get started.</p>
      ) : (
        turns.map((turn, i) => (
          <ChatMessage key={`${turn.role}-${i}`} role={turn.role} text={turn.text} />
        ))
      )}
    </div>
  );
}
