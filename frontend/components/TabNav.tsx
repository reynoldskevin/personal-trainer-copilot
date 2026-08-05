import type { TabId } from './types';

const TABS: TabId[] = ['Overview', 'Workout', 'Insights', 'Trends', 'Chat'];

interface TabNavProps {
  active: TabId;
  onChange: (tab: TabId) => void;
}

export default function TabNav({ active, onChange }: TabNavProps) {
  return (
    <div
      className="kg-tabs"
      data-component="TabNav"
      role="tablist"
      style={{ width: 'max-content' }}
    >
      {TABS.map((tab) => (
        <button
          key={tab}
          type="button"
          role="tab"
          className={`kg-tab${active === tab ? ' is-active' : ''}`}
          aria-selected={active === tab}
          onClick={() => onChange(tab)}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}
