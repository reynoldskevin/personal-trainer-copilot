export default function AppHeader() {
  return (
    <div className="kg-between" data-component="AppHeader">
      <div className="kg-row-f" style={{ gap: 'var(--space-md)' }}>
        <div
          className="kg-avatar"
          style={{
            borderRadius: 'var(--radius-md)',
            background: 'var(--color-accent)',
            color: 'var(--color-accent-fg)',
          }}
        />
        <div>
          <h2 className="kg-h2">AI Coaching Assistant</h2>
          <p className="kg-mono">members</p>
        </div>
      </div>
    </div>
  );
}
