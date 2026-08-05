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
import InjuryBadge from './InjuryBadge';
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
    <div className="kg-app">
      <div data-region="app-header">
        <AppHeader />
      </div>
      <div className="kg-shell">
        <section className="kg-card kg-rail" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)', flexBasis: 340 }}>
          <div data-region="list-toolbar">
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
          <div data-region="members-list" className="kg-list">
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

        <section className="kg-main">
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
    <div className="kg-shell" style={{ flex: 1 }}>
      <div className="kg-rail" data-region="member-context-rail">
        <MemberContextRail detail={detail} />
      </div>
      <div className="kg-main">
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
  );
}

function OverviewTab({ detail }: { detail: MemberDetail }) {
  const totals = detail.adherence.reduce(
    (acc, a) => {
      acc.planned += a.planned;
      acc.completed += a.completed;
      return acc;
    },
    { planned: 0, completed: 0 }
  );
  const adherencePct =
    totals.planned > 0 ? Math.round((totals.completed / totals.planned) * 100) : 0;

  return (
    <div className="kg-stack">
      <div
        data-region="overview-metrics"
        className="kg-grid"
        style={{ gridTemplateColumns: '1.55fr 1fr' }}
      >
        <MetricStat
          label="4-week adherence"
          value={String(adherencePct)}
          unit="%"
          pct={adherencePct}
          sub={`${totals.completed}/${totals.planned}`}
        />
        <MetricStat
          label="Sessions logged"
          value={String(detail.recent_workouts.length)}
          tone="safe"
        />
      </div>

      <div className="kg-cols" style={{ alignItems: 'stretch' }}>
        <div data-region="overview-injuries" style={{ flex: '0 0 340px', order: 2 }}>
          <div className="kg-card" style={{ height: '100%' }}>
            <h2 className="kg-h1">Injuries</h2>
            <div
              className="kg-stack"
              style={{ gap: 'var(--space-sm)', marginTop: 'var(--space-lg)' }}
            >
              {detail.injuries.length === 0 ? (
                <span className="kg-chip kg-chip--safe kg-chip--sm">Cleared</span>
              ) : (
                detail.injuries.map((injury) => (
                  <div className="kg-inset" key={injury}>
                    <InjuryBadge injury={injury} />
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <div data-region="overview-goals" className="kg-grow" style={{ order: 1 }}>
          <div className="kg-card" style={{ height: '100%' }}>
            <h2 className="kg-h1">Goals</h2>
            <div
              className="kg-stack"
              style={{ gap: 'var(--space-lg)', marginTop: 'var(--space-lg)' }}
            >
              {detail.goals.map((goal) => (
                <div key={goal}>
                  <div className="kg-h3">{goal}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div data-region="overview-recent-activity">
        <div className="kg-card">
          <h2 className="kg-h1">Recent activity</h2>
          <div className="kg-stack" style={{ gap: 0, marginTop: 'var(--space-md)' }}>
            {detail.recent_workouts.length === 0 ? (
              <p className="kg-p">No recent workouts.</p>
            ) : (
              detail.recent_workouts.map((w) => (
                <div className="kg-source" key={w.timestamp}>
                  <span className="kg-source__tag">SESSION</span>
                  <div>
                    <div className="kg-h3">{w.exercises.join(', ')}</div>
                    <p className="kg-mono">{new Date(w.timestamp).toLocaleDateString()}</p>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
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
    <div className="kg-stack">
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
