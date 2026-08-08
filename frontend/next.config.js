/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Dev convenience: proxy the API paths to the FastAPI backend on :8000 so the
  // browser makes same-origin requests (no CORS needed). Production would set
  // NEXT_PUBLIC_API_BASE instead.
  async rewrites() {
    const api = process.env.API_PROXY_TARGET || 'http://localhost:8000';
    return [
      { source: '/members', destination: `${api}/members` },
      { source: '/members/:id', destination: `${api}/members/:id` },
      { source: '/retrieve', destination: `${api}/retrieve` },
      { source: '/generate/:path*', destination: `${api}/generate/:path*` },
      // `/chat/stream` (SSE) must be listed BEFORE `/chat` — the dashboard streams the chat
      // answer from it, and without this rewrite it 404s at the frontend origin in production.
      { source: '/chat/stream', destination: `${api}/chat/stream` },
      { source: '/chat', destination: `${api}/chat` },
    ];
  },
};

module.exports = nextConfig;
