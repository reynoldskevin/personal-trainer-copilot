import { useState } from 'react';

interface ChatComposerProps {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export default function ChatComposer({ onSend, disabled }: ChatComposerProps) {
  const [text, setText] = useState('');

  function handleSend() {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText('');
  }

  return (
    <div className="kg-card kg-card--flat" data-component="ChatComposer">
      <label className="kg-eyebrow" htmlFor="chat-composer-input">
        Ask a question about this member (for the coach)
      </label>
      <div className="kg-field" style={{ marginTop: 'var(--space-sm)', alignItems: 'flex-end' }}>
        <textarea
          id="chat-composer-input"
          className="kg-input kg-input--md"
          aria-label="Ask about this member"
          placeholder="Ask about this member's progress, injuries, or adherence…"
          rows={2}
          value={text}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          style={{ resize: 'vertical' }}
        />
        <button
          type="button"
          className="kg-btn"
          onClick={handleSend}
          disabled={disabled}
        >
          Ask
        </button>
      </div>
    </div>
  );
}
