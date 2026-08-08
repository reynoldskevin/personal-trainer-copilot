'use client';

import { useEffect, useMemo, useState } from 'react';
import type {
  ChatTurn,
  InsightReport,
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
import StatusChip from './StatusChip';
import InsightReportCard from './InsightReportCard';
import TrendChart from './TrendChart';
import ChatThread from './ChatThread';
import ChatComposer from './ChatComposer';

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
  const [focus, setFocus] = useState('shoulder-safe upper body');

  const [insight, setInsight] = useState<InsightReport | null>(null);
  const [insightBundle, setInsightBundle] = useState<RetrievalBundle | null>(null);
  const [insightState, setInsightState] = useState<LoadState>('loading');

  const [chatTurns, setChatTurns] = useState<ChatTurn[]>([]);
  const [chatContext, setChatContext] = useState<string[] | null>(null);
  const [chatSending, setChatSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

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
    setInsight(null);
    setInsightBundle(null);
    setInsightState('loading');
    setChatTurns([]);
    setChatContext(null);
    setChatError(null);
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
          body: JSON.stringify({ member_id: selectedId, query: focus }),
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

  // Fetch the insight report (and its supporting bundle) the first time the
  // Insights or Trends tab is activated for the selected member — mirrors the
  // workout tab. The `!insight` guard means it fetches once and never loops.
  // (The Trends tab charts its own series from the member detail, so it needs no insight fetch.)
  useEffect(() => {
    if (activeTab !== 'Insights' || !selectedId || insight) return;
    let active = true;
    setInsightState('loading');
    const memberId = selectedId;
    Promise.all([
      getJson<InsightReport>(`${API_BASE}/generate/insight`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ member_id: memberId }),
      }),
      getJson<RetrievalBundle>(`${API_BASE}/retrieve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ member_id: memberId, query: 'insight' }),
      }),
    ])
      .then(([report, retrieved]) => {
        if (!active) return;
        setInsight(report);
        setInsightBundle(retrieved);
        setInsightState('ready');
      })
      .catch(() => {
        if (!active) return;
        setInsightState('error');
      });
    return () => {
      active = false;
    };
  }, [activeTab, selectedId, insight]);

  // Grow the trailing assistant turn as tokens stream in (it is always the last turn during a send).
  function setStreamingAssistantText(text: string) {
    setChatTurns((turns) => {
      const copy = turns.slice();
      const last = copy[copy.length - 1];
      if (last && last.role === 'assistant') {
        copy[copy.length - 1] = { ...last, text };
      }
      return copy;
    });
  }

  async function sendChat(message: string) {
    if (!selectedId) return;
    const memberId = selectedId;
    const optimistic: ChatTurn = { role: 'coach', text: message };
    setChatSending(true);
    setChatError(null);
    // Add the coach's turn plus an empty assistant turn we grow as SSE tokens arrive.
    setChatTurns((turns) => [...turns, optimistic, { role: 'assistant', text: '' }]);
    try {
      const res = await fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ member_id: memberId, message }),
      });
      if (!res.ok || !res.body) {
        throw new Error(`Request failed: /chat/stream (${res.status})`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let answer = '';
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // SSE events are separated by a blank line; process every complete one.
        let sep: number;
        while ((sep = buffer.indexOf('\n\n')) !== -1) {
          const chunk = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          for (const line of chunk.split('\n')) {
            if (!line.startsWith('data:')) continue;
            const event = JSON.parse(line.slice(5).trim());
            if (event.type === 'context') {
              setChatContext(event.context_used);
            } else if (event.type === 'token') {
              answer += event.delta;
              setStreamingAssistantText(answer);
            } else if (event.type === 'done') {
              answer = event.answer;
              setStreamingAssistantText(answer);
            }
          }
        }
      }
    } catch {
      // Roll back the streaming assistant placeholder and the optimistic coach turn, and surface
      // an error affordance — never swallow the failure silently.
      setChatTurns((turns) => {
        const copy = turns.slice();
        if (copy.length && copy[copy.length - 1].role === 'assistant') copy.pop();
        const idx = copy.lastIndexOf(optimistic);
        if (idx !== -1) copy.splice(idx, 1);
        return copy;
      });
      // Don't leave the supporting-context panel populated for the rolled-back exchange.
      setChatContext(null);
      setChatError('Failed to send message. Please try again.');
    } finally {
      setChatSending(false);
    }
  }

  // Screen-based navigation: the members list and the member hub are distinct
  // full screens (per the structure contract), never a persistent master-detail.
  // Search lives only on the list screen; the hub's rail is the member context.
  const onList = selectedId === null;

  return (
    <div className="kg-app">
      <div data-region="app-header">
        <AppHeader />
      </div>

      {onList ? (
        <section className="kg-stack">
          <div className="kg-between" style={{ padding: 'var(--space-md) var(--space-sm) 0' }}>
            <h1 className="kg-display">Members</h1>
          </div>
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
      ) : (
        <section className="kg-shell">
          {detailState === 'loading' && (
            <StatusView message="Loading member…" variant="loading" />
          )}
          {detailState === 'error' && (
            <StatusView message="Failed to load member details." variant="error" />
          )}
          {detailState === 'ready' && detail && (
            <MemberHub
              detail={detail}
              onBack={() => setSelectedId(null)}
              activeTab={activeTab}
              onTabChange={setActiveTab}
              plan={plan}
              bundle={bundle}
              generating={generating}
              generateError={generateError}
              onGenerate={generateWorkout}
              focus={focus}
              onFocusChange={setFocus}
              insight={insight}
              insightBundle={insightBundle}
              insightState={insightState}
              chatTurns={chatTurns}
              chatContext={chatContext}
              chatSending={chatSending}
              chatError={chatError}
              onSendChat={sendChat}
            />
          )}
        </section>
      )}
    </div>
  );
}

interface MemberHubProps {
  detail: MemberDetail;
  onBack: () => void;
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
  plan: WorkoutPlan | null;
  bundle: RetrievalBundle | null;
  generating: boolean;
  generateError: string | null;
  onGenerate: () => void;
  focus: string;
  onFocusChange: (focus: string) => void;
  insight: InsightReport | null;
  insightBundle: RetrievalBundle | null;
  insightState: LoadState;
  chatTurns: ChatTurn[];
  chatContext: string[] | null;
  chatSending: boolean;
  chatError: string | null;
  onSendChat: (message: string) => void;
}

function MemberHub({
  detail,
  onBack,
  activeTab,
  onTabChange,
  plan,
  bundle,
  generating,
  generateError,
  onGenerate,
  focus,
  onFocusChange,
  insight,
  insightBundle,
  insightState,
  chatTurns,
  chatContext,
  chatSending,
  chatError,
  onSendChat,
}: MemberHubProps) {
  return (
    <>
      <div className="kg-rail" data-region="member-context-rail">
        <MemberContextRail detail={detail} onBack={onBack} />
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
            focus={focus}
            onFocusChange={onFocusChange}
          />
        )}
        {activeTab === 'Insights' && (
          <InsightsTab insight={insight} bundle={insightBundle} state={insightState} />
        )}
        {activeTab === 'Trends' && <TrendsTab detail={detail} />}
        {activeTab === 'Chat' && (
          <ChatTab
            turns={chatTurns}
            context={chatContext}
            sending={chatSending}
            error={chatError}
            onSend={onSendChat}
          />
        )}
      </div>
    </>
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

interface InsightsTabProps {
  insight: InsightReport | null;
  bundle: RetrievalBundle | null;
  state: LoadState;
}

function InsightsTab({ insight, bundle, state }: InsightsTabProps) {
  if (state === 'loading' || !insight) {
    return <StatusView message="Generating insight report…" variant="loading" />;
  }
  if (state === 'error') {
    return <StatusView message="Failed to generate insight." variant="error" />;
  }

  return (
    <div className="kg-stack">
      <div data-region="insight-summary">
        <InsightReportCard report={insight} />
      </div>

      <div data-region="insight-flags" className="kg-stack" style={{ gap: 'var(--space-sm)' }}>
        {insight.risk_flags.map((flag) => (
          <div key={`${flag.kind}-${flag.detail}`}>
            <StatusChip
              label={`${flag.kind} · ${flag.severity}`}
              variant={flag.severity === 'high' ? 'danger' : 'warn'}
            />
            <p className="kg-p" style={{ marginTop: 'var(--space-xs)' }}>
              {flag.detail}
            </p>
          </div>
        ))}
        {insight.safety_flags.length > 0 && (
          <div className="kg-row-f">
            {insight.safety_flags.map((flag) => (
              <StatusChip key={flag} label={flag} variant="info" />
            ))}
          </div>
        )}
      </div>

      {bundle && (
        <div data-region="insight-supporting-context">
          <SupportingContextPanel bundle={bundle} />
        </div>
      )}
    </div>
  );
}

const BIOMETRIC_LABEL: Record<string, string> = {
  resting_heart_rate: 'Resting HR',
  body_weight_kg: 'Body weight',
  sleep_hours: 'Sleep',
};
const BIOMETRIC_UNIT: Record<string, string> = {
  resting_heart_rate: 'bpm',
  body_weight_kg: 'kg',
  sleep_hours: 'h',
};

function shortDate(ts: string): string {
  return new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function deltaOf(values: number[], decimals: number, unit: string) {
  const d = values[values.length - 1] - values[0];
  const dir: 'up' | 'down' | 'flat' = d > 0 ? 'up' : d < 0 ? 'down' : 'flat';
  const glyph = d > 0 ? '▲' : d < 0 ? '▼' : '–';
  return { text: `${glyph} ${Math.abs(d).toFixed(decimals)}${unit}`, dir };
}

function TrendsTab({ detail }: { detail: MemberDetail }) {
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

  // Adherence over time — sorted chronologically so the line reads left → right in time.
  const adherenceSeries = [...detail.adherence]
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
    .map((a) => ({
      label: shortDate(a.timestamp),
      value: a.planned > 0 ? Math.round((a.completed / a.planned) * 100) : 0,
    }));
  const adherenceDelta = deltaOf(
    adherenceSeries.map((p) => p.value),
    0,
    '%'
  );

  // One line chart per biometric type the member has readings for (resting HR, body weight, …).
  const byType = new Map<string, number[]>();
  const tsByType = new Map<string, string[]>();
  for (const b of detail.biometrics) {
    (byType.get(b.type) ?? byType.set(b.type, []).get(b.type)!).push(b.value);
    (tsByType.get(b.type) ?? tsByType.set(b.type, []).get(b.type)!).push(b.timestamp);
  }
  const biometricCharts = [...byType.entries()].map(([type, values], i) => {
    const decimals = values.some((v) => !Number.isInteger(v)) ? 1 : 0;
    const unit = BIOMETRIC_UNIT[type] ?? '';
    return {
      type,
      decimals,
      unit,
      label: BIOMETRIC_LABEL[type] ?? type.replace(/_/g, ' '),
      chartTone: (i % 2 === 0 ? 'info' : 'accent-2') as 'info' | 'accent-2',
      statTone: (i % 2 === 0 ? 'info' : 'teal') as 'info' | 'teal',
      points: (tsByType.get(type) ?? []).map((ts, j) => ({
        label: shortDate(ts),
        value: values[j],
      })),
      latest: values[values.length - 1],
      delta: deltaOf(values, decimals, unit),
    };
  });

  return (
    <div className="kg-stack">
      <div data-region="trends-metrics" className="kg-grid kg-g4">
        <MetricStat
          label="Adherence"
          value={String(adherencePct)}
          unit="%"
          tone="accent"
          tight
          delta={adherenceSeries.length > 1 ? adherenceDelta : undefined}
          sub={`${totals.completed}/${totals.planned}`}
        />
        <MetricStat
          label="Sessions logged"
          value={String(detail.recent_workouts.length)}
          tone="teal"
          tight
        />
        {biometricCharts.map((c) => (
          <MetricStat
            key={c.type}
            label={c.label}
            value={c.latest.toFixed(c.decimals)}
            unit={c.unit}
            tone={c.statTone}
            tight
            delta={c.points.length > 1 ? c.delta : undefined}
          />
        ))}
      </div>

      <div data-region="trends-charts" className="kg-stack">
        <TrendChart title="Adherence" points={adherenceSeries} unit="%" tone="accent" />
        {biometricCharts.length > 0 && (
          <div className="kg-grid kg-g2">
            {biometricCharts.map((c) => (
              <TrendChart
                key={c.type}
                title={c.label}
                points={c.points}
                unit={c.unit}
                tone={c.chartTone}
                decimals={c.decimals}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

interface ChatTabProps {
  turns: ChatTurn[];
  context: string[] | null;
  sending: boolean;
  error: string | null;
  onSend: (message: string) => void;
}

function ChatTab({ turns, context, sending, error, onSend }: ChatTabProps) {
  const contextBundle: RetrievalBundle | null = context
    ? {
        member_id: '',
        query: 'chat',
        vector_hits: [],
        subgraph_facts: [],
        context_items: context,
        contraindications: [],
        token_estimate: 0,
        token_budget: 0,
      }
    : null;

  return (
    <div className="kg-stack">
      <div data-region="chat-thread">
        <ChatThread turns={turns} />
      </div>
      <div data-region="chat-composer">
        <ChatComposer onSend={onSend} disabled={sending} />
      </div>
      {error && <StatusView message={error} variant="error" />}
      {contextBundle && (
        <div data-region="chat-supporting-context">
          <SupportingContextPanel bundle={contextBundle} />
        </div>
      )}
    </div>
  );
}

interface WorkoutTabProps {
  plan: WorkoutPlan | null;
  bundle: RetrievalBundle | null;
  generating: boolean;
  generateError: string | null;
  onGenerate: () => void;
  focus: string;
  onFocusChange: (focus: string) => void;
}

function WorkoutTab({
  plan,
  bundle,
  generating,
  generateError,
  onGenerate,
  focus,
  onFocusChange,
}: WorkoutTabProps) {
  return (
    <div className="kg-stack">
      <div data-region="workout-controls">
        <GenerateControl
          onGenerate={onGenerate}
          loading={generating}
          focus={focus}
          onFocusChange={onFocusChange}
        />
      </div>
      {generateError && <StatusView message={generateError} variant="error" />}
      {plan && (
        <div data-region="workout-plan">
          <WorkoutPlanCard plan={plan} />
        </div>
      )}
      {bundle && (
        <div data-region="workout-supporting-context">
          <SupportingContextPanel bundle={bundle} defaultOpen={false} />
        </div>
      )}
    </div>
  );
}
