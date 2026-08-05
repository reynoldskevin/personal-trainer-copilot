import { useId } from 'react';

export interface TrendPoint {
  label: string;
  value: number;
}

type Tone = 'accent' | 'accent-2' | 'info';

interface TrendChartProps {
  title: string;
  points: TrendPoint[];
  unit?: string;
  tone?: Tone;
  /** Decimals for the headline (latest) value. */
  decimals?: number;
}

const TONE_VAR: Record<Tone, string> = {
  accent: 'var(--color-accent)',
  'accent-2': 'var(--color-accent-2)',
  info: 'var(--color-info)',
};

// SVG geometry (matches the design's kg-spark viewBox).
const W = 640;
const H = 180;
const X0 = 10;
const X1 = 630;
const Y_TOP = 25;
const Y_BOT = 155;

function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
}

/**
 * A single metric's trend as a line chart: a filled-area spark line with gridlines, an
 * end-point marker and a value axis, in a card with a headline value + delta. Renders the
 * member's real series (adherence over time, or a biometric like resting heart rate / body
 * weight). Degenerate series (one reading, or a flat series) render a flat line, never a crash.
 */
export default function TrendChart({
  title,
  points,
  unit,
  tone = 'accent',
  decimals = 0,
}: TrendChartProps) {
  const color = TONE_VAR[tone];
  // Unique per instance so two charts on one screen never share a gradient id (which would
  // cross-wire their fills). Strip ':' from useId so the value is a valid SVG url(#…) reference.
  const gid = `spark-${slug(title)}-${useId().replace(/:/g, '')}`;

  if (points.length === 0) {
    return (
      <div className="kg-card" data-component="TrendChart">
        <p className="kg-eyebrow">{title}</p>
        <p className="kg-mono" style={{ marginTop: 'var(--space-md)' }}>
          No data yet
        </p>
      </div>
    );
  }

  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const n = points.length;

  const xAt = (i: number) => (n === 1 ? [X0, X1] : [X0 + ((X1 - X0) * i) / (n - 1)]);
  const yAt = (v: number) =>
    max === min ? (Y_TOP + Y_BOT) / 2 : Y_BOT - ((v - min) / (max - min)) * (Y_BOT - Y_TOP);

  // Build the coordinate list (a single reading spans the full width as a flat line).
  const coords: Array<[number, number]> =
    n === 1
      ? [
          [X0, yAt(values[0])],
          [X1, yAt(values[0])],
        ]
      : points.map((p, i) => [xAt(i)[0], yAt(p.value)]);

  const line = coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `${line} L${coords[coords.length - 1][0].toFixed(1)},${H} L${coords[0][0].toFixed(1)},${H} Z`;
  const [endX, endY] = coords[coords.length - 1];

  const latest = values[values.length - 1];
  const deltaN = latest - values[0];
  const deltaDir = deltaN > 0 ? 'up' : deltaN < 0 ? 'down' : 'flat';
  const deltaGlyph = deltaN > 0 ? '▲' : deltaN < 0 ? '▼' : '–';
  const deltaText = `${deltaGlyph} ${Math.abs(deltaN).toFixed(decimals)}${unit ?? ''}`;

  return (
    <div className="kg-card" data-component="TrendChart">
      <div className="kg-between" style={{ marginBottom: 'var(--space-lg)' }}>
        <div>
          <p className="kg-eyebrow">{title}</p>
          <p className="kg-value kg-value--sm" style={{ marginTop: 8 }}>
            {latest.toFixed(decimals)}
            {unit && <span className="kg-unit">{unit}</span>}
          </p>
        </div>
        {n > 1 && <span className={`kg-delta kg-delta--${deltaDir}`}>{deltaText}</span>}
      </div>

      <svg
        className="kg-spark"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`${title} trend: ${values.map((v) => v.toFixed(decimals)).join(', ')}${unit ?? ''}`}
      >
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={color} stopOpacity="0.34" />
            <stop offset="1" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <g stroke="var(--color-border)" strokeDasharray="3 5">
          <line x1="0" y1="45" x2={W} y2="45" />
          <line x1="0" y1="90" x2={W} y2="90" />
          <line x1="0" y1="135" x2={W} y2="135" />
        </g>
        <path d={area} fill={`url(#${gid})`} />
        <path d={line} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx={endX} cy={endY} r="10" fill={color} opacity="0.22" />
        <circle cx={endX} cy={endY} r="5.5" fill={color} />
      </svg>

      <div className="kg-axis">
        {points.map((p, i) => (
          <span key={`${p.label}-${i}`}>{p.label}</span>
        ))}
      </div>
    </div>
  );
}
