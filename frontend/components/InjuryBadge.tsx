export default function InjuryBadge({
  injury,
  variant = 'warn',
}: {
  injury: string;
  variant?: 'warn' | 'danger';
}) {
  return (
    <span className={`kg-chip kg-chip--${variant}`} data-component="InjuryBadge">
      <span className="kg-chip__dot" />
      {injury}
    </span>
  );
}
