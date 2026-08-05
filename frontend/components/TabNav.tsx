import type { TabId } from './types';

const TABS: TabId[] = ['Overview', 'Workout', 'Insights', 'Trends', 'Chat'];
const M2_TABS: TabId[] = ['Insights', 'Trends', 'Chat'];

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
      {TABS.map((tab) => {
        const isM2 = M2_TABS.includes(tab);
        return (
          <button
            key={tab}
            type="button"
            role="tab"
            className={`kg-tab${active === tab ? ' is-active' : ''}`}
            aria-selected={active === tab}
            onClick={() => onChange(tab)}
          >
            {tab}
            {isM2 && <span className="kg-tab__m2">soon</span>}
          </button>
        );
      })}
    </div>
  );
}
