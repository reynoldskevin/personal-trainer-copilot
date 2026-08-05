export default function StatusChip({ label }: { label: string }) {
  return (
    <span className="status-chip" data-component="StatusChip">
      {label}
    </span>
  );
}
