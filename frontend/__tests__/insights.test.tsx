/**
 * Ticket 015 — Dashboard M2: Insights & Trends views (component/smoke test).
 *
 * Drives the top-level `Dashboard` with a mocked `fetch` and asserts the Insights and Trends
 * tabs — activated in M2 — render their contract regions/components:
 *  - Insights: POST /generate/insight -> InsightReportCard in `insight-summary`, risk + safety
 *    flags in `insight-flags` (StatusChip), and a SupportingContextPanel in
 *    `insight-supporting-context`.
 *  - Trends: adherence/biometric MetricStat in `trends-metrics` and a TrendChart in
 *    `trends-charts`, derived from the loaded member detail.
 *
 * Only the DOM contract (data-region / data-component + roles/text) is asserted.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import Dashboard from '@/components/Dashboard';

const MEMBERS = [
  { id: 'member_ava', name: 'Ava Thompson', injuries: ['Rotator cuff injury'], goals: ['Rehab right shoulder'] },
];

const AVA_DETAIL = {
  id: 'member_ava',
  name: 'Ava Thompson',
  injuries: ['Rotator cuff injury'],
  goals: ['Rehab right shoulder and press pain-free'],
  recent_workouts: [
    { timestamp: '2026-01-13T09:15:00+00:00', exercises: ['Leg extension'] },
    { timestamp: '2026-01-27T08:45:00+00:00', exercises: ['Barbell back squat'] },
  ],
  adherence: [
    { timestamp: '2026-01-06T20:00:00+00:00', planned: 4, completed: 2 },
    { timestamp: '2026-01-13T20:00:00+00:00', planned: 4, completed: 3 },
    { timestamp: '2026-01-27T20:00:00+00:00', planned: 4, completed: 4 },
  ],
};

const AVA_BUNDLE = {
  member_id: 'member_ava',
  query: 'insight',
  vector_hits: [],
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
    biometrics: [
      { type: 'resting_heart_rate', slope_per_week: -1, direction: 'falling', first_value: 61, last_value: 58 },
    ],
    workout_count: 2,
    summary_lines: ['Adherence 75% over the last 12 weeks.'],
  },
  excluded_contraindicated: ['overhead_press'],
  safety_flags: ["Excluded contraindicated recommendation 'overhead_press' — unsafe for this member."],
};

function jsonResponse(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response);
}

function installFetch(overrides: Partial<Record<string, () => Promise<Response>>> = {}) {
  const fn = jest.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method || 'GET').toUpperCase();
    if (url.endsWith('/members') && method === 'GET') return (overrides.members ?? (() => jsonResponse(MEMBERS)))();
    if (/\/members\/[^/]+$/.test(url) && method === 'GET') return (overrides.detail ?? (() => jsonResponse(AVA_DETAIL)))();
    if (url.endsWith('/generate/insight')) return (overrides.insight ?? (() => jsonResponse(AVA_INSIGHT)))();
    if (url.endsWith('/retrieve')) return (overrides.retrieve ?? (() => jsonResponse(AVA_BUNDLE)))();
    return Promise.reject(new Error(`unexpected fetch: ${method} ${url}`));
  });
  (global as unknown as { fetch: typeof fn }).fetch = fn;
  return fn;
}

afterEach(() => {
  jest.resetAllMocks();
});

async function openHub() {
  const user = userEvent.setup();
  render(<Dashboard />);
  const row = await screen.findByRole('button', { name: /Ava Thompson/ });
  await user.click(row);
  await screen.findByText(/Rehab right shoulder and press pain-free/);
  return user;
}

test('the Insights tab renders the InsightReport with risk and safety flags', async () => {
  installFetch();
  const user = await openHub();

  await user.click(screen.getByRole('tab', { name: /Insights/ }));

  const summary = await waitFor(() => {
    const el = document.querySelector('[data-region="insight-summary"]');
    expect(el).toBeInTheDocument();
    return el as HTMLElement;
  });
  expect(document.querySelector('[data-component="InsightReportCard"]')).toBeInTheDocument();
  expect(within(summary).getByText(/progressing on her shoulder rehab/i)).toBeInTheDocument();

  const flags = document.querySelector('[data-region="insight-flags"]') as HTMLElement;
  expect(flags).toBeInTheDocument();
  expect(flags.querySelector('[data-component="StatusChip"]')).toBeInTheDocument();
  // The risk flag (an adherence/risk signal) is surfaced within the flags region...
  expect(within(flags).getAllByText(/adherence|risk/i).length).toBeGreaterThanOrEqual(1);
  // ...and the safety flag (contraindicated recommendation removed) is surfaced.
  expect(screen.getByText(/overhead_press/)).toBeInTheDocument();

  // Supporting context is shown for the insight.
  expect(document.querySelector('[data-region="insight-supporting-context"]')).toBeInTheDocument();
  expect(document.querySelector('[data-component="SupportingContextPanel"]')).toBeInTheDocument();
});

test('the Insights tab shows a loading affordance before the report arrives', async () => {
  let resolve: (r: Response) => void = () => {};
  installFetch({ insight: () => new Promise<Response>((r) => { resolve = r; }) });
  const user = await openHub();

  await user.click(screen.getByRole('tab', { name: /Insights/ }));
  expect(screen.getByText(/loading|generating/i)).toBeInTheDocument();
  resolve(jsonResponse(AVA_INSIGHT) as unknown as Response);
  await waitFor(() =>
    expect(document.querySelector('[data-component="InsightReportCard"]')).toBeInTheDocument()
  );
});

test('the Trends tab visualizes adherence AND biometric trends', async () => {
  installFetch();
  const user = await openHub();

  await user.click(screen.getByRole('tab', { name: /Trends/ }));

  expect(document.querySelector('[data-region="trends-metrics"]')).toBeInTheDocument();
  expect(document.querySelectorAll('[data-component="MetricStat"]').length).toBeGreaterThanOrEqual(1);
  expect(document.querySelector('[data-region="trends-charts"]')).toBeInTheDocument();
  // Adherence-over-time chart is derived from the loaded member detail (synchronous)...
  expect(document.querySelector('[data-component="TrendChart"]')).toBeInTheDocument();
  // ...and once the trend data loads, a biometric-progression chart is shown too (the fixture
  // carries a resting_heart_rate trend), so both halves of the contract are visualized.
  await waitFor(() =>
    expect(document.querySelectorAll('[data-component="TrendChart"]').length).toBeGreaterThanOrEqual(2)
  );
});
