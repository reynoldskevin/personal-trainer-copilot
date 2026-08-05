export default function MetricStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-stat" data-component="MetricStat">
      <div className="value">{value}</div>
      <div className="label">{label}</div>
    </div>
  );
}
