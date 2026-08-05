import type { RetrievalBundle } from './types';

export default function SupportingContextPanel({ bundle }: { bundle: RetrievalBundle }) {
  return (
    <div className="panel supporting-context-panel" data-component="SupportingContextPanel">
      <h3>Supporting context</h3>
      {bundle.subgraph_facts.length > 0 && (
        <>
          <h4>Knowledge graph facts</h4>
          <ul>
            {bundle.subgraph_facts.map((fact) => (
              <li key={fact}>{fact}</li>
            ))}
          </ul>
        </>
      )}
      <p className="meta">
        Token budget: {bundle.token_estimate}/{bundle.token_budget}
      </p>
    </div>
  );
}
