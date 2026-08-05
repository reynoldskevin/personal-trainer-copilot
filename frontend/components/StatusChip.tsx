export default function StatusChip({
  label,
  variant = 'warn',
}: {
  label: string;
  variant?: 'warn' | 'danger' | 'safe' | 'info';
}) {
  return (
    <span className={`kg-chip kg-chip--${variant}`} data-component="StatusChip">
      <span className="kg-chip__dot" />
      {label}
    </span>
  );
}
