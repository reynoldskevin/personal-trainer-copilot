export default function InjuryBadge({ injury }: { injury: string }) {
  return (
    <span className="badge injury-badge" data-component="InjuryBadge">
      {injury}
    </span>
  );
}
