interface StatusViewProps {
  message: string;
  variant?: 'loading' | 'error' | 'empty' | 'info';
}

export default function StatusView({ message, variant = 'info' }: StatusViewProps) {
  return (
    <div className={`status-view ${variant}`} data-component="StatusView" role="status">
      {message}
    </div>
  );
}
