interface GenerateControlProps {
  focus: string;
  onFocusChange: (focus: string) => void;
  onGenerate: () => void;
  loading: boolean;
}

export default function GenerateControl({
  focus,
  onFocusChange,
  onGenerate,
  loading,
}: GenerateControlProps) {
  return (
    <div className="kg-card kg-card--flat" data-component="GenerateControl">
      <div className="kg-field">
        <input
          className="kg-input"
          aria-label="Workout focus"
          value={focus}
          onChange={(e) => onFocusChange(e.target.value)}
        />
        <button
          type="button"
          className={`kg-btn${loading ? ' is-loading' : ''}`}
          onClick={onGenerate}
          disabled={loading}
        >
          {loading ? 'Generating…' : 'Generate'}
        </button>
      </div>
    </div>
  );
}
