interface StatusViewProps {
  message: string;
  variant?: 'loading' | 'error' | 'empty' | 'info';
}

export default function StatusView({ message, variant = 'info' }: StatusViewProps) {
  const markClass =
    variant === 'loading'
      ? 'kg-status__mark kg-status__mark--load'
      : variant === 'error'
        ? 'kg-status__mark kg-status__mark--err'
        : 'kg-status__mark';

  return (
    <div className="kg-status" data-component="StatusView" role="status">
      <div className={markClass}>{variant === 'error' ? '!' : ''}</div>
      <p className="kg-p">{message}</p>
    </div>
  );
}
