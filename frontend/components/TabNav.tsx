import type { TabId } from './types';

const TABS: TabId[] = ['Overview', 'Workout', 'Insights', 'Trends', 'Chat'];

interface TabNavProps {
  active: TabId;
  onChange: (tab: TabId) => void;
}

export default function TabNav({ active, onChange }: TabNavProps) {
  return (
    <div className="tab-nav" data-component="TabNav" role="tablist">
      {TABS.map((tab) => (
        <button
          key={tab}
          type="button"
          role="tab"
          aria-selected={active === tab}
          onClick={() => onChange(tab)}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}
