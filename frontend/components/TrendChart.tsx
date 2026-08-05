interface TrendPoint {
  /** Stable React key; falls back to label when omitted. */
  key?: string;
  label: string;
  value: number;
}

interface TrendChartProps {
  points: TrendPoint[];
  unit?: string;
}

export default function TrendChart({ points, unit }: TrendChartProps) {
  const max = points.reduce((m, p) => Math.max(m, p.value), 0);

  return (
    <div className="kg-card kg-card--flat" data-component="TrendChart">
      <div
        className="kg-row-f"
        role="img"
        aria-label={`Trend chart with ${points.length} points`}
        style={{ gap: 'var(--space-sm)', alignItems: 'flex-end', height: 120 }}
      >
        {points.map((point) => {
          const pct = max > 0 ? Math.round((point.value / max) * 100) : 0;
          const readout = `${point.value}${unit ?? ''}`;
          return (
            <div
              key={point.key ?? point.label}
              className="kg-stack"
              style={{ gap: 'var(--space-xs)', alignItems: 'center', flex: 1 }}
            >
              <span className="kg-mono" aria-hidden="true">
                {readout}
              </span>
              <div
                className="kg-bar"
                aria-label={`${point.label}: ${readout}`}
                style={{ width: '100%', height: `${pct}%`, minHeight: 4 }}
              >
                <div className="kg-bar__fill" style={{ height: '100%' }} />
              </div>
              <span className="kg-eyebrow">{point.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
