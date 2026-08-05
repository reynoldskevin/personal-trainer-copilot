interface GenerateControlProps {
  onGenerate: () => void;
  loading: boolean;
}

export default function GenerateControl({ onGenerate, loading }: GenerateControlProps) {
  return (
    <div className="kg-card kg-card--flat" data-component="GenerateControl">
      <div className="kg-field">
        <input
          className="kg-input"
          aria-label="Workout focus"
          defaultValue="shoulder-safe upper body"
          readOnly
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
      <div className="kg-row-f" style={{ marginTop: 'var(--space-md)' }}>
        <span className="kg-mono">quick hints</span>
        <span className="kg-chip kg-chip--ghost kg-chip--sm">Return to run</span>
        <span className="kg-chip kg-chip--ghost kg-chip--sm">Upper push</span>
        <span className="kg-chip kg-chip--ghost kg-chip--sm">Deload week</span>
      </div>
    </div>
  );
}
