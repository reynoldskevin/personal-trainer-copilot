'use client';

import { useEffect, useMemo, useState } from 'react';
import type {
  Member,
  MemberDetail,
  RetrievalBundle,
  TabId,
  WorkoutPlan,
} from './types';
import AppHeader from './AppHeader';
import SearchBar from './SearchBar';
import MemberListItem from './MemberListItem';
import MemberContextRail from './MemberContextRail';
import TabNav from './TabNav';
import MetricStat from './MetricStat';
import GenerateControl from './GenerateControl';
import WorkoutPlanCard from './WorkoutPlanCard';
import SupportingContextPanel from './SupportingContextPanel';
import StatusView from './StatusView';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? '';

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    throw new Error(`Request failed: ${url} (${res.status})`);
  }
  return (await res.json()) as T;
}

type LoadState = 'loading' | 'ready' | 'error';

export default function Dashboard() {
  const [members, setMembers] = useState<Member[]>([]);
  const [listState, setListState] = useState<LoadState>('loading');
  const [search, setSearch] = useState('');

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<MemberDetail | null>(null);
  const [detailState, setDetailState] = useState<LoadState>('loading');

  const [activeTab, setActiveTab] = useState<TabId>('Overview');

  const [plan, setPlan] = useState<WorkoutPlan | null>(null);
  const [bundle, setBundle] = useState<RetrievalBundle | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setListState('loading');
    getJson<Member[]>(`${API_BASE}/members`)
      .then((data) => {
        if (!active) return;
        setMembers(data);
        setListState('ready');
      })
      .catch(() => {
        if (!active) return;
        setListState('error');
      });
    return () => {
      active = false;
    };
  }, []);

  const filteredMembers = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return members;
    return members.filter((m) => m.name.toLowerCase().includes(q));
  }, [members, search]);

  async function selectMember(member: Member) {
    setSelectedId(member.id);
    setActiveTab('Overview');
    setDetail(null);
    setDetailState('loading');
    setPlan(null);
    setBundle(null);
    setGenerateError(null);
    try {
      const data = await getJson<MemberDetail>(`${API_BASE}/members/${member.id}`);
      setDetail(data);
      setDetailState('ready');
    } catch {
      setDetailState('error');
    }
  }

  async function generateWorkout() {
    if (!selectedId) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      const [planRes, bundleRes] = await Promise.all([
        getJson<WorkoutPlan>(`${API_BASE}/generate/workout`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ member_id: selectedId }),
        }),
        getJson<RetrievalBundle>(`${API_BASE}/retrieve`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ member_id: selectedId, query: 'workout' }),
        }),
      ]);
      setPlan(planRes);
      setBundle(bundleRes);
    } catch {
      setGenerateError('Failed to generate workout.');
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="app">
      <div data-region="app-header">
        <AppHeader />
      </div>
      <div className="layout">
        <section className="panel">
          <div data-region="list-toolbar" className="list-toolbar">
            <SearchBar value={search} onChange={setSearch} />
          </div>
          {(listState === 'error' || (listState === 'ready' && filteredMembers.length === 0)) && (
            <div data-region="list-status">
              {listState === 'error' && (
                <StatusView message="Something went wrong loading members." variant="error" />
              )}
              {listState === 'ready' && filteredMembers.length === 0 && (
                <StatusView message="No members match your search." variant="empty" />
              )}
            </div>
          )}
          <div data-region="members-list" className="members-list">
            {listState === 'loading' && (
              <StatusView message="Loading members…" variant="loading" />
            )}
            {filteredMembers.map((member) => (
              <MemberListItem
                key={member.id}
                member={member}
                selected={member.id === selectedId}
                onSelect={selectMember}
              />
            ))}
          </div>
        </section>

        <section>
          {!selectedId && <StatusView message="Select a member to view their hub." variant="empty" />}
          {selectedId && detailState === 'loading' && (
            <StatusView message="Loading member…" variant="loading" />
          )}
          {selectedId && detailState === 'error' && (
            <StatusView message="Failed to load member details." variant="error" />
          )}
          {selectedId && detailState === 'ready' && detail && (
            <MemberHub
              detail={detail}
              activeTab={activeTab}
              onTabChange={setActiveTab}
              plan={plan}
              bundle={bundle}
              generating={generating}
              generateError={generateError}
              onGenerate={generateWorkout}
            />
          )}
        </section>
      </div>
    </div>
  );
}

interface MemberHubProps {
  detail: MemberDetail;
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
  plan: WorkoutPlan | null;
  bundle: RetrievalBundle | null;
  generating: boolean;
  generateError: string | null;
  onGenerate: () => void;
}

function MemberHub({
  detail,
  activeTab,
  onTabChange,
  plan,
  bundle,
  generating,
  generateError,
  onGenerate,
}: MemberHubProps) {
  return (
    <div className="member-hub">
      <div className="layout" style={{ padding: 0, gridTemplateColumns: '280px 1fr' }}>
        <div data-region="member-context-rail">
          <MemberContextRail detail={detail} />
        </div>
        <div>
          <div data-region="tab-nav">
            <TabNav active={activeTab} onChange={onTabChange} />
          </div>
          {activeTab === 'Overview' && <OverviewTab detail={detail} />}
          {activeTab === 'Workout' && (
            <WorkoutTab
              plan={plan}
              bundle={bundle}
              generating={generating}
              generateError={generateError}
              onGenerate={onGenerate}
            />
          )}
          {(activeTab === 'Insights' || activeTab === 'Trends' || activeTab === 'Chat') && (
            <StatusView message={`${activeTab} — coming in M2`} variant="info" />
          )}
        </div>
      </div>
    </div>
  );
}

function OverviewTab({ detail }: { detail: MemberDetail }) {
  const latestAdherence = detail.adherence[detail.adherence.length - 1];
  const adherencePct =
    latestAdherence && latestAdherence.planned > 0
      ? Math.round((latestAdherence.completed / latestAdherence.planned) * 100)
      : 0;

  return (
    <div className="overview">
      <div data-region="overview-metrics" className="metrics-grid">
        <MetricStat label="Adherence" value={`${adherencePct}%`} />
        <MetricStat label="Recent workouts" value={String(detail.recent_workouts.length)} />
      </div>

      <div data-region="overview-injuries" className="overview-section">
        <h3>Injuries</h3>
        {detail.injuries.length === 0 ? (
          <p className="meta">No injuries recorded.</p>
        ) : (
          <ul>
            {detail.injuries.map((injury) => (
              <li key={injury}>{injury}</li>
            ))}
          </ul>
        )}
      </div>

      <div data-region="overview-goals" className="overview-section">
        <h3>Goals</h3>
        <ul>
          {detail.goals.map((goal) => (
            <li key={goal}>{goal}</li>
          ))}
        </ul>
      </div>

      <div data-region="overview-recent-activity" className="overview-section">
        <h3>Recent activity</h3>
        {detail.recent_workouts.length === 0 ? (
          <p className="meta">No recent workouts.</p>
        ) : (
          <ul>
            {detail.recent_workouts.map((w) => (
              <li key={w.timestamp}>
                {new Date(w.timestamp).toLocaleDateString()} — {w.exercises.join(', ')}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

interface WorkoutTabProps {
  plan: WorkoutPlan | null;
  bundle: RetrievalBundle | null;
  generating: boolean;
  generateError: string | null;
  onGenerate: () => void;
}

function WorkoutTab({ plan, bundle, generating, generateError, onGenerate }: WorkoutTabProps) {
  return (
    <div className="workout">
      <div data-region="workout-controls">
        <GenerateControl onGenerate={onGenerate} loading={generating} />
      </div>
      {generateError && <StatusView message={generateError} variant="error" />}
      {plan && (
        <div data-region="workout-plan">
          <WorkoutPlanCard plan={plan} />
        </div>
      )}
      {bundle && (
        <div data-region="workout-supporting-context">
          <SupportingContextPanel bundle={bundle} />
        </div>
      )}
    </div>
  );
}
