/**
 * Proxy rewrites contract.
 *
 * The dashboard calls the API on its own origin and relies on Next.js `rewrites()` to proxy to the
 * backend. Every backend path the app uses MUST have a rewrite — in particular the SSE streaming
 * chat endpoint `/chat/stream`, whose absence 404s only in production (the component tests mock
 * `fetch`, so they cannot catch a missing rewrite). This locks the proxy map.
 */
// eslint-disable-next-line @typescript-eslint/no-var-requires
const nextConfig = require('@/next.config.js');

async function sources(): Promise<string[]> {
  const rewrites = await nextConfig.rewrites();
  return rewrites.map((r: { source: string }) => r.source);
}

test('every API path the dashboard calls is proxied', async () => {
  const srcs = await sources();
  for (const path of ['/members', '/members/:id', '/retrieve', '/generate/:path*', '/chat']) {
    expect(srcs).toContain(path);
  }
});

test('the SSE streaming chat endpoint is proxied (and before /chat)', async () => {
  const srcs = await sources();
  expect(srcs).toContain('/chat/stream');
  // More specific route must precede the exact `/chat` so it is matched first.
  expect(srcs.indexOf('/chat/stream')).toBeLessThan(srcs.indexOf('/chat'));

  const rewrites = await nextConfig.rewrites();
  const stream = rewrites.find((r: { source: string }) => r.source === '/chat/stream');
  expect(stream.destination).toMatch(/\/chat\/stream$/);
});
