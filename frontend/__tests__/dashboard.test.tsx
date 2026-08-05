/**
 * Ticket 010 — Minimal coach dashboard (Next.js) — component/smoke test.
 *
 * The dashboard is the M1 hub built to the structure contract. This test drives the
 * top-level `Dashboard` component with a mocked `fetch` and asserts:
 *  - the members-list screen renders its named regions/components from GET /members
 *  - SearchBar filters the loaded list client-side (no backend search)
 *  - selecting a member opens the hub (member-overview) with MemberContextRail, InjuryBadge,
 *    MetricStat, the goals region, and a TabNav whose M2 tabs (Insights/Trends/Chat) are
 *    visible but render a StatusView "coming in M2" placeholder
 *  - the Workout tab generates a plan via POST /generate/workout and renders a WorkoutPlanCard
 *    of ExerciseRows with the injury-safety flags surfaced (and NO contraindicated exercise row)
 *  - loading and error states are handled
 *
 * Only the DOM contract (data-region / data-component attributes + accessible roles/text) is
 * asserted, so the implementation is free to structure the React internals as it sees fit.
 */
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import Dashboard from '@/components/Dashboard';

const MEMBERS = [
  { id: 'member_ava', name: 'Ava Thompson', injuries: ['Rotator cuff injury'], goals: ['Rehab right shoulder'] },
  { id: 'member_ben', name: 'Ben Carter', injuries: [], goals: ['Deadlift 180kg'] },
  { id: 'member_chloe', name: 'Chloe Nguyen', injuries: ['Lumbar strain'], goals: ['Rebuild core'] },
];

const AVA_DETAIL = {
  id: 'member_ava',
  name: 'Ava Thompson',
  injuries: ['Rotator cuff injury'],
  goals: ['Rehab right shoulder and press pain-free', 'Return to a bodyweight squat for 5 reps'],
  recent_workouts: [{ timestamp: '2026-01-27T08:45:00+00:00', exercises: ['Barbell back squat'] }],
  adherence: [{ timestamp: '2026-01-27T20:00:00+00:00', planned: 4, completed: 4 }],
};

const AVA_PLAN = {
  member_id: 'member_ava',
  summary: 'Shoulder-safe upper/lower session.',
  exercises: [
    { exercise_id: 'push_up', name: 'Push-up', sets: 3, reps: 10, notes: null },
    { exercise_id: 'leg_extension', name: 'Machine leg extension', sets: 3, reps: 12, notes: null },
  ],
  safety_flags: ["Removed contraindicated exercise 'overhead_press' from the plan; unsafe for this member."],
  excluded_contraindicated: ['overhead_press', 'bench_press'],
};

const AVA_BUNDLE = {
  member_id: 'member_ava',
  query: 'workout',
  vector_hits: [{ id: 'goal_ava_shoulder', labels: ['Goal'], score: 0.9, text: 'Rehab right shoulder' }],
  subgraph_facts: ['Active injury: Rotator cuff injury.'],
  context_items: ['Active injury: Rotator cuff injury.'],
  contraindications: ['bench_press', 'overhead_press'],
  token_estimate: 12,
  token_budget: 2000,
};

const AVA_INSIGHT = {
  member_id: 'member_ava',
  summary: 'Ava is progressing on her shoulder rehab with steady adherence.',
  risk_flags: [{ kind: 'adherence', severity: 'medium', detail: 'Windowed adherence dipped to 60%.' }],
  personalization_notes: ['Keep pressing volume light this block.'],
  trends: {
    window_weeks: 12,
    adherence_percentage: 75,
    adherence_sessions: '12 of 16 planned sessions',
    biometrics: [],
    workout_count: 2,
    summary_lines: ['Adherence 75% over the last 12 weeks.'],
  },
  excluded_contraindicated: ['overhead_press'],
  safety_flags: ["Excluded contraindicated recommendation 'overhead_press' — unsafe for this member."],
};

const AVA_CHAT = {
  member_id: 'member_ava',
  message: 'How is she doing?',
  answer: 'Ava is rehabbing her shoulder and her adherence is steady.',
  context_used: ['Active injury: Rotator cuff injury.'],
};

function jsonResponse(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response);
}

/** A fetch router keyed on path suffix + method, so call order doesn't matter. */
function installFetch(overrides: Partial<Record<string, () => Promise<Response>>> = {}) {
  const fn = jest.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method || 'GET').toUpperCase();
    if (url.endsWith('/members') && method === 'GET') return (overrides.members ?? (() => jsonResponse(MEMBERS)))();
    if (/\/members\/[^/]+$/.test(url) && method === 'GET') return (overrides.detail ?? (() => jsonResponse(AVA_DETAIL)))();
    if (url.endsWith('/generate/insight')) return (overrides.insight ?? (() => jsonResponse(AVA_INSIGHT)))();
    if (url.endsWith('/generate/workout')) return (overrides.generate ?? (() => jsonResponse(AVA_PLAN)))();
    if (url.endsWith('/retrieve')) return (overrides.retrieve ?? (() => jsonResponse(AVA_BUNDLE)))();
    if (url.endsWith('/chat')) return (overrides.chat ?? (() => jsonResponse(AVA_CHAT)))();
    return Promise.reject(new Error(`unexpected fetch: ${method} ${url}`));
  });
  (global as unknown as { fetch: typeof fn }).fetch = fn;
  return fn;
}

afterEach(() => {
  jest.resetAllMocks();
});

async function selectAva() {
  const user = userEvent.setup();
  render(<Dashboard />);
  const row = await screen.findByRole('button', { name: /Ava Thompson/ });
  await user.click(row);
  await screen.findByText(/Rehab right shoulder and press pain-free/);
  return user;
}

test('members-list screen renders its contract regions and components', async () => {
  installFetch();
  render(<Dashboard />);
  await screen.findByText('Ava Thompson');

  expect(document.querySelector('[data-region="app-header"]')).toBeInTheDocument();
  expect(document.querySelector('[data-component="AppHeader"]')).toBeInTheDocument();
  expect(document.querySelector('[data-region="list-toolbar"]')).toBeInTheDocument();
  expect(document.querySelector('[data-component="SearchBar"]')).toBeInTheDocument();
  expect(document.querySelector('[data-region="members-list"]')).toBeInTheDocument();
  expect(document.querySelectorAll('[data-component="MemberListItem"]').length).toBeGreaterThanOrEqual(3);
  // All three seed members are listed.
  expect(screen.getByText('Ben Carter')).toBeInTheDocument();
  expect(screen.getByText('Chloe Nguyen')).toBeInTheDocument();
});

test('SearchBar filters the loaded member list client-side', async () => {
  installFetch();
  const user = userEvent.setup();
  render(<Dashboard />);
  await screen.findByText('Ava Thompson');

  await user.type(screen.getByRole('textbox'), 'Ava');
  expect(screen.getByText('Ava Thompson')).toBeInTheDocument();
  expect(screen.queryByText('Ben Carter')).not.toBeInTheDocument();
  expect(screen.queryByText('Chloe Nguyen')).not.toBeInTheDocument();
});

test('selecting a member opens the overview hub with rail, injury, metrics, goals and tabs', async () => {
  installFetch();
  await selectAva();

  const rail = document.querySelector('[data-region="member-context-rail"]');
  expect(rail).toBeInTheDocument();
  expect(within(rail as HTMLElement).getByText(/Ava Thompson/)).toBeInTheDocument();

  expect(document.querySelector('[data-component="MemberContextRail"]')).toBeInTheDocument();
  expect(document.querySelector('[data-component="InjuryBadge"]')).toBeInTheDocument();
  expect(document.querySelector('[data-region="tab-nav"]')).toBeInTheDocument();
  expect(document.querySelector('[data-component="TabNav"]')).toBeInTheDocument();
  expect(document.querySelector('[data-region="overview-metrics"]')).toBeInTheDocument();
  expect(document.querySelectorAll('[data-component="MetricStat"]').length).toBeGreaterThanOrEqual(1);
  expect(document.querySelector('[data-region="overview-injuries"]')).toBeInTheDocument();
  expect(document.querySelector('[data-region="overview-goals"]')).toBeInTheDocument();
  expect(document.querySelector('[data-region="overview-recent-activity"]')).toBeInTheDocument();

  // The five hub tabs exist; Overview is the active default.
  for (const label of ['Overview', 'Workout', 'Insights', 'Trends', 'Chat']) {
    expect(screen.getByRole('tab', { name: new RegExp(label) })).toBeInTheDocument();
  }
});

test('the Insights/Trends/Chat tabs are now active (no "coming in M2" placeholder)', async () => {
  installFetch();
  const user = await selectAva();

  await user.click(screen.getByRole('tab', { name: /Insights/ }));
  await waitFor(() =>
    expect(document.querySelector('[data-region="insight-summary"]')).toBeInTheDocument()
  );
  expect(document.querySelector('[data-component="InsightReportCard"]')).toBeInTheDocument();

  await user.click(screen.getByRole('tab', { name: /Trends/ }));
  expect(document.querySelector('[data-region="trends-metrics"]')).toBeInTheDocument();

  await user.click(screen.getByRole('tab', { name: /Chat/ }));
  expect(document.querySelector('[data-region="chat-composer"]')).toBeInTheDocument();

  expect(screen.queryByText(/coming in M2/i)).not.toBeInTheDocument();
});

test('the Workout tab generates a plan and renders it with safety flags', async () => {
  installFetch();
  const user = await selectAva();

  await user.click(screen.getByRole('tab', { name: /Workout/ }));
  expect(document.querySelector('[data-region="workout-controls"]')).toBeInTheDocument();
  expect(document.querySelector('[data-component="GenerateControl"]')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /Generate/i }));

  // Plan card renders after generation.
  await waitFor(() => expect(document.querySelector('[data-component="WorkoutPlanCard"]')).toBeInTheDocument());
  const planRegion = document.querySelector('[data-region="workout-plan"]') as HTMLElement;
  expect(planRegion).toBeInTheDocument();

  const rows = planRegion.querySelectorAll('[data-component="ExerciseRow"]');
  expect(rows.length).toBeGreaterThanOrEqual(2);
  // The safe exercises are shown...
  expect(within(planRegion).getByText(/Push-up/)).toBeInTheDocument();
  // ...and the contraindicated exercise is NOT rendered as a prescribed row.
  rows.forEach((row) => expect(row.textContent).not.toMatch(/overhead_press/));

  // The safety flag surfaces the removal (a StatusChip carries it).
  expect(document.querySelector('[data-component="StatusChip"]')).toBeInTheDocument();
  expect(screen.getByText(/overhead_press/)).toBeInTheDocument();
  expect(screen.getByText(/contraindicated/i)).toBeInTheDocument();
});

test('a failed members load shows an error state', async () => {
  installFetch({ members: () => Promise.reject(new Error('boom')) });
  render(<Dashboard />);
  await waitFor(() => expect(document.querySelector('[data-region="list-status"]')).toBeInTheDocument());
  expect(screen.getByText(/error|failed|something went wrong/i)).toBeInTheDocument();
});

test('the members list shows a loading state before data arrives', async () => {
  let resolve: (r: Response) => void = () => {};
  installFetch({ members: () => new Promise<Response>((r) => { resolve = r; }) });
  render(<Dashboard />);
  // Before the promise resolves, a loading affordance is present.
  expect(screen.getByText(/loading/i)).toBeInTheDocument();
  resolve(jsonResponse(MEMBERS) as unknown as Response);
  await screen.findByText('Ava Thompson');
});
