import type { InsightReport } from './types';

export default function InsightReportCard({ report }: { report: InsightReport }) {
  return (
    <div className="kg-card" data-component="InsightReportCard">
      <p className="kg-eyebrow">Insight report</p>
      <h2 className="kg-h1" style={{ marginTop: 6 }}>
        {report.summary}
      </h2>

      {report.personalization_notes.length > 0 && (
        <div className="kg-stack" style={{ gap: 'var(--space-sm)', marginTop: 'var(--space-lg)' }}>
          <p className="kg-eyebrow">Personalization notes</p>
          {report.personalization_notes.map((note) => (
            <div className="kg-inset" key={note}>
              <div className="kg-h3">{note}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
