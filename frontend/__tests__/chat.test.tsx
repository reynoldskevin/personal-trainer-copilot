/**
 * Ticket 015 — Dashboard M2: Chat panel (component/smoke test).
 *
 * The Chat tab is CONTEXT-ONLY: the composer asks the coach's question ABOUT the member and the
 * thread renders a grounded answer from POST /chat. It must NOT draft a client/member-facing
 * reply. Drives the top-level `Dashboard` with a mocked `fetch` and asserts the contract regions
 * (`chat-thread`, `chat-composer`, `chat-supporting-context`) and components (ChatThread,
 * ChatComposer, SupportingContextPanel).
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
  recent_workouts: [{ timestamp: '2026-01-27T08:45:00+00:00', exercises: ['Barbell back squat'] }],
  adherence: [{ timestamp: '2026-01-27T20:00:00+00:00', planned: 4, completed: 4 }],
};

// The chat answer arrives as an SSE stream: a context event, several token deltas that
// concatenate to the full answer, then a done event.
const AVA_STREAM = [
  `data: ${JSON.stringify({
    type: 'context',
    member_id: 'member_ava',
    message: 'How is her shoulder tracking?',
    context_used: ['Active injury: Rotator cuff injury.', 'Goal: Rehab right shoulder.'],
  })}\n\n`,
  `data: ${JSON.stringify({ type: 'token', delta: 'Ava is ' })}\n\n`,
  `data: ${JSON.stringify({ type: 'token', delta: 'rehabbing her rotator cuff.' })}\n\n`,
  `data: ${JSON.stringify({ type: 'done', answer: 'Ava is rehabbing her rotator cuff.' })}\n\n`,
];

function jsonResponse(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response);
}

// A Response whose body streams the given string chunks (one per reader.read()), like SSE.
function sseResponse(chunks: string[]) {
  const encoder = new TextEncoder();
  let i = 0;
  const body = {
    getReader() {
      return {
        read() {
          if (i < chunks.length) {
            return Promise.resolve({ done: false, value: encoder.encode(chunks[i++]) });
          }
          return Promise.resolve({ done: true, value: undefined });
        },
      };
    },
  };
  return Promise.resolve({ ok: true, status: 200, body } as unknown as Response);
}

function installFetch(overrides: Partial<Record<string, () => Promise<Response>>> = {}) {
  const fn = jest.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method || 'GET').toUpperCase();
    if (url.endsWith('/members') && method === 'GET') return (overrides.members ?? (() => jsonResponse(MEMBERS)))();
    if (/\/members\/[^/]+$/.test(url) && method === 'GET') return (overrides.detail ?? (() => jsonResponse(AVA_DETAIL)))();
    if (url.endsWith('/chat/stream')) return (overrides.chatStream ?? (() => sseResponse(AVA_STREAM)))();
    return Promise.reject(new Error(`unexpected fetch: ${method} ${url}`));
  });
  (global as unknown as { fetch: typeof fn }).fetch = fn;
  return fn;
}

afterEach(() => {
  jest.resetAllMocks();
});

async function openChat() {
  const user = userEvent.setup();
  render(<Dashboard />);
  const row = await screen.findByRole('button', { name: /Ava Thompson/ });
  await user.click(row);
  await screen.findByText(/Rehab right shoulder and press pain-free/);
  await user.click(screen.getByRole('tab', { name: /Chat/ }));
  return user;
}

test('the Chat tab renders its composer and thread regions', async () => {
  installFetch();
  await openChat();

  expect(document.querySelector('[data-region="chat-composer"]')).toBeInTheDocument();
  expect(document.querySelector('[data-component="ChatComposer"]')).toBeInTheDocument();
  expect(document.querySelector('[data-region="chat-thread"]')).toBeInTheDocument();
  expect(document.querySelector('[data-component="ChatThread"]')).toBeInTheDocument();
});

test('the composer is context-only: it asks ABOUT the member, not a client-facing draft', async () => {
  installFetch();
  await openChat();

  const composer = document.querySelector('[data-region="chat-composer"]') as HTMLElement;
  // The composer's copy frames the question as being about the member (for the coach).
  const textbox = within(composer).getByRole('textbox') as HTMLTextAreaElement;
  const composerText = (
    composer.textContent + ' ' + (textbox.getAttribute('placeholder') ?? '')
  ).toLowerCase();
  expect(composerText).toMatch(/member|about|coach/);
  // ...and it does not offer to draft a client/member-facing reply.
  expect(composerText).not.toMatch(/draft (a )?(reply|message|response) (to|for) (the )?(client|member)/);
});

test('sending a question streams from /chat/stream and assembles the grounded answer', async () => {
  const fetchMock = installFetch();
  const user = await openChat();

  const composer = document.querySelector('[data-region="chat-composer"]') as HTMLElement;
  await user.type(within(composer).getByRole('textbox'), 'How is her shoulder tracking?');
  await user.click(within(composer).getByRole('button', { name: /send|ask/i }));

  // The answer, assembled from the streamed token deltas, appears in the thread. The matched
  // text spans TWO separate token events, so it only renders if the SSE stream was consumed and
  // accumulated correctly.
  await waitFor(() =>
    expect(screen.getByText(/Ava is rehabbing her rotator cuff\./i)).toBeInTheDocument()
  );
  const thread = document.querySelector('[data-region="chat-thread"]') as HTMLElement;
  expect(within(thread).getByText(/Ava is rehabbing her rotator cuff\./i)).toBeInTheDocument();
  expect(document.querySelectorAll('[data-component="ChatMessage"]').length).toBeGreaterThanOrEqual(1);

  // The call went to the STREAMING endpoint and carried the member id and the coach's message.
  const chatCall = fetchMock.mock.calls.find(([u]) => String(u).endsWith('/chat/stream'));
  expect(chatCall).toBeTruthy();
  const body = JSON.parse(String((chatCall?.[1] as RequestInit).body));
  expect(body.member_id).toBe('member_ava');
  expect(body.message).toMatch(/shoulder/i);

  // The context surfaced by the stream's context event is shown as supporting context.
  expect(document.querySelector('[data-region="chat-supporting-context"]')).toBeInTheDocument();
  expect(document.querySelector('[data-component="SupportingContextPanel"]')).toBeInTheDocument();
});
