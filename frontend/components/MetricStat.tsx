interface MetricStatProps {
  label: string;
  value: string;
  unit?: string;
  /** When provided, render an adherence ring gauge instead of a plain tile. */
  pct?: number;
  tone?: 'accent' | 'info' | 'safe' | 'teal' | 'warn';
  sub?: string;
}

export default function MetricStat({ label, value, unit, pct, tone = 'accent', sub }: MetricStatProps) {
  if (pct != null) {
    return (
      <div className="kg-stat kg-stat--accent kg-gauge" data-component="MetricStat">
        <div className="kg-ring kg-ring--lg" style={{ ['--pct' as string]: String(pct) }}>
          <div className="kg-ring__hole">
            <div>
              <p className="kg-value kg-value--sm" style={{ margin: 0 }}>
                {value}
                {unit && <span className="kg-unit">{unit}</span>}
              </p>
              {sub && (
                <p className="kg-eyebrow" style={{ marginTop: 4 }}>
                  {sub}
                </p>
              )}
            </div>
          </div>
        </div>
        <div>
          <p className="kg-stat__label" style={{ maxWidth: 'none' }}>
            {label}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={`kg-stat kg-stat--${tone}`} data-component="MetricStat">
      <div className="kg-stat__head">
        <p className="kg-stat__label">{label}</p>
      </div>
      <div className="kg-stat__foot">
        <p className="kg-value" style={{ margin: 0 }}>
          {value}
          {unit && <span className="kg-unit">{unit}</span>}
        </p>
        {sub && <span className="kg-mono">{sub}</span>}
      </div>
    </div>
  );
}
