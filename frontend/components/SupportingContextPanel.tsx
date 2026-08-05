import type { RetrievalBundle } from './types';

export default function SupportingContextPanel({ bundle }: { bundle: RetrievalBundle }) {
  const facts = bundle.subgraph_facts;
  const context = bundle.context_items;
  const sourceCount = facts.length + context.length;

  return (
    <div className="kg-panel" data-component="SupportingContextPanel">
      <div className="kg-panel__head" style={{ marginBottom: 'var(--space-md)' }}>
        <div className="kg-row-f">
          <span className="kg-chip kg-chip--info">
            <span className="kg-chip__dot" />
            {sourceCount} sources
          </span>
          <span className="kg-h3">Supporting context</span>
        </div>
      </div>

      {facts.map((fact) => (
        <div className="kg-source" key={`graph-${fact}`}>
          <span className="kg-source__tag">GRAPH</span>
          <div>
            <div className="kg-h3">{fact}</div>
          </div>
        </div>
      ))}
      {context.map((item) => (
        <div className="kg-source" key={`context-${item}`}>
          <span className="kg-source__tag">CONTEXT</span>
          <div>
            <div className="kg-h3">{item}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
