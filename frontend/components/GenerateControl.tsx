interface GenerateControlProps {
  onGenerate: () => void;
  loading: boolean;
}

export default function GenerateControl({ onGenerate, loading }: GenerateControlProps) {
  return (
    <div className="generate-control" data-component="GenerateControl">
      <button type="button" className="btn" onClick={onGenerate} disabled={loading}>
        {loading ? 'Generating…' : 'Generate workout'}
      </button>
    </div>
  );
}
