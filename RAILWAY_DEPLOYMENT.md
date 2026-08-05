# Railway Deployment Plan — Knowledge Graph Coaching Platform

A step-by-step plan to deploy the platform (FastAPI backend + Next.js frontend + Neo4j) to
[Railway](https://railway.com). Grounded in the repo as it stands: `Dockerfile` (API),
`docker-compose.yml` (local topology), `frontend/` (Next.js 15), and `app/config.py`
(required env: `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD`, `LLM_PROVIDER`, `OPENAI_API_KEY`).

> Status: **plan only** — nothing here has been applied to Railway yet. The repo is *not*
> Railway-ready out of the box; §2 lists the small, required code changes first.

---

## 1. Target topology

One Railway **project** (`kg-coaching-platform`), one **environment** (`production`), three
**services**:

```
                         ┌─────────────────────────────┐
  browser ──HTTPS──▶     │  frontend (Next.js)         │  public domain
                         │  next start on $PORT        │
                         └──────────────┬──────────────┘
                     same-origin /api…  │ (Next rewrite, server-side)
                                        ▼   private network (IPv6)
                         ┌─────────────────────────────┐
                         │  api (FastAPI)              │  private (optionally public /docs)
                         │  uvicorn on $PORT           │
                         └──────────────┬──────────────┘
                          bolt://…:7687 │ private network
                                        ▼
                         ┌─────────────────────────────┐
                         │  neo4j (5.26-community)     │  private only + Volume at /data
                         └─────────────────────────────┘
```

**Networking decision:** keep the **API private** and let the **Next.js server proxy** to it
(same pattern as the local dev proxy, promoted to production). The browser only ever talks to
the frontend's own origin, so there is **no CORS** and the API isn't publicly exposed. (Alt:
expose the API publicly and set `NEXT_PUBLIC_API_BASE` to its URL + add CORS middleware — see
§6.)

**Datastore decision:** Neo4j runs as a Railway service from the official image with a
persistent Volume. If you'd rather not operate the DB, swap it for **Neo4j Aura** (managed) and
point `NEO4J_URI` at the Aura `neo4j+s://` URL — the app needs no code change (this is the AWS/
Aura extension point the architecture already anticipates). Tradeoffs in §8.

---

## 2. Required repo changes (do these first)

The current build hardcodes assumptions that don't fit Railway's `$PORT` + private-network
model. Three small changes:

### 2a. API must bind Railway's `$PORT`
`Dockerfile` ends with `CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]`.
Railway injects a dynamic `$PORT`. Add a `railway.json` at repo root so the API service uses it
(this overrides the Dockerfile CMD at run time, no Dockerfile edit needed):

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
  "deploy": {
    "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

`/health` already returns `{"status":"ok","neo4j":<bool>}` (ticket 001), so it's a ready-made
healthcheck.

### 2b. Production-safe frontend proxy (replace the dev-only rewrite)
The local `frontend/next.config.js` rewrite is a dev convenience. Commit a version driven by an
env var so the **Next server** (not the browser) proxies API calls to the private API URL:

```js
// frontend/next.config.js
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const api = process.env.API_PROXY_TARGET; // e.g. http://api.railway.internal:8000
    if (!api) return [];
    return [
      { source: '/members', destination: `${api}/members` },
      { source: '/members/:id', destination: `${api}/members/:id` },
      { source: '/retrieve', destination: `${api}/retrieve` },
      { source: '/generate/:path*', destination: `${api}/generate/:path*` },
    ];
  },
};
module.exports = nextConfig;
```

With this, the frontend keeps `NEXT_PUBLIC_API_BASE` empty (same-origin `/members`, …) and the
Next server forwards to `API_PROXY_TARGET` over the private network.

### 2c. A one-shot seed entrypoint
A fresh Neo4j is empty; the app needs schema + ontology + members + embeddings loaded once.
Add `app/ingestion/seed.py` wrapping what the loaders already expose:

```python
"""One-shot seed: schema + ontology + members + embeddings. Idempotent."""
from app.graph.client import get_client
from app.graph import schema
from app.ingestion import ontology, members
from app.retrieval import embeddings
from app.config import get_settings
from app.llm import get_provider

def main() -> None:
    c = get_client()
    schema.bootstrap_schema(c)
    ontology.load_ontology(c)
    members.ingest_members(c)
    embeddings.embed_and_index(c, get_provider(get_settings()))  # real OpenAI embeddings (1536-d)
    c.close()

if __name__ == "__main__":
    main()
```

Run it once post-deploy via `railway run` / a one-off exec (§5). It's idempotent, so re-running
is safe.

---

## 3. Prerequisites

- Railway CLI installed and authenticated: `railway login` (opens your browser; creates the
  account on the fly if needed).
- An OpenAI API key for `OPENAI_API_KEY`.
- The three repo changes in §2 committed.

---

## 4. Create the project and services

```bash
# From the repo root — creates the project + first (API) service and deploys the Dockerfile
railway up --new --name kg-coaching-platform      # links + deploys the API from cwd

# Add Neo4j from the official image
railway add --service neo4j --image neo4j:5.26-community --json

# Add the frontend service (built from the ./frontend subdirectory — set root dir in §6)
railway add --service frontend --json
```

Attach a **Volume** to `neo4j` mounted at `/data` (persists the graph across deploys) — via the
dashboard (Service → Data → Add Volume) or CLI once available. Without it, the graph is wiped on
every redeploy.

---

## 5. Configure variables (per service)

**neo4j**
```bash
railway variable set NEO4J_AUTH=neo4j/<STRONG_PASSWORD> --service neo4j
# Railway private networking is IPv6 — make Neo4j listen on all interfaces:
railway variable set NEO4J_server_default__listen__address=0.0.0.0 --service neo4j
```

**api**
```bash
railway variable set NEO4J_URI=bolt://neo4j.railway.internal:7687 --service api
railway variable set NEO4J_USER=neo4j --service api
railway variable set NEO4J_PASSWORD=<STRONG_PASSWORD> --service api
railway variable set LLM_PROVIDER=openai --service api
railway variable set OPENAI_API_KEY=<your-key> --service api    # secret
```

**frontend**
```bash
railway variable set API_PROXY_TARGET=http://api.railway.internal:8000 --service frontend
# NEXT_PUBLIC_API_BASE left unset (empty) → same-origin, proxied by the Next server
```

> `*.railway.internal` is Railway's private DNS; those hostnames resolve only inside the
> project's private network. Match the password in `NEO4J_AUTH` and `NEO4J_PASSWORD`.

Then seed the graph once (idempotent):
```bash
railway run --service api python -m app.ingestion.seed
```

---

## 6. Build & networking settings

- **api** — builder: Dockerfile (via `railway.json`); healthcheck `/health`; private only
  (don't add a public domain) unless you want `/docs` exposed. If you *do* expose it, add CORS
  (`fastapi.middleware.cors.CORSMiddleware`) and point the frontend at the public URL via
  `NEXT_PUBLIC_API_BASE` instead of the proxy.
- **frontend** — set **Root Directory** = `frontend`; build `npm run build`; start `npm run
  start` (Next binds `$PORT` automatically). Add a **public domain** (Railway-generated
  `*.up.railway.app`, or a custom domain). This is the only public surface.
- **neo4j** — private only; Volume at `/data`. Do **not** add a public domain (bolt is TCP; if
  you ever need external bolt use a Railway TCP Proxy, but the API reaches it privately).

---

## 7. Deploy & verify

```bash
railway up --service api --detach -m "api"
railway up --service frontend --detach -m "frontend"
# neo4j deploys from its image automatically on create

# Poll to a terminal state (do not trust "queued"):
railway deployment list --json
```

Verify:
1. `neo4j` deployment `SUCCESS`, Volume mounted.
2. `api` healthcheck green — `GET https://<api-if-public>/health` → `{"neo4j": true}` (or check
   logs for a clean start; `neo4j:true` confirms private connectivity).
3. Seed ran: `railway run --service api python -m app.ingestion.seed` printed no errors.
4. Open the frontend public URL → members list loads → pick an injured member → **Generate
   workout** returns a safe plan with safety flags (real OpenAI end-to-end).

---

## 8. Neo4j on Railway vs. Neo4j Aura

| | Neo4j service on Railway | Neo4j Aura (managed) |
|---|---|---|
| Setup | Image + Volume, in-project private net | External; set `NEO4J_URI=neo4j+s://…` |
| Cost | Railway compute + volume | Aura free/paid tier |
| Ops | You own upgrades/backups | Managed backups, HA |
| Fit | Fine for MVP/demo | The documented production/scale path |

Switching to Aura is a **variables-only** change (`NEO4J_URI/USER/PASSWORD`) — no code edits —
because everything goes through `app/graph/client.py`.

---

## 9. Cost & scaling notes

- Three always-on services + one volume. Scale the API horizontally later (it's stateless; all
  state is in Neo4j) — replicas need no code change.
- The `<5s` latency target and token budgeting are already in the retrieval/generation layers;
  add LangFuse (M3) for per-call latency/token traces in production.
- Secrets (`OPENAI_API_KEY`, `NEO4J_PASSWORD`) live only in Railway variables — never commit
  them (`.env` is gitignored).

---

## 10. Command appendix (quick reference)

```bash
railway login                                              # auth (browser)
railway up --new --name kg-coaching-platform               # create project + deploy API from cwd
railway add --service neo4j --image neo4j:5.26-community --json
railway add --service frontend --json
railway variable set KEY=value --service <svc>             # set config/secrets
railway run --service api python -m app.ingestion.seed     # one-off seed
railway up --service <svc> --detach -m "<msg>"             # deploy a service
railway deployment list --json                             # poll to SUCCESS
railway logs --service <svc> --lines 200 --json            # troubleshoot
railway domain list --service frontend --json              # public URL / DNS
```
