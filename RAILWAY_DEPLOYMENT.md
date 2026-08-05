# Railway Deployment Plan — Knowledge Graph Coaching Platform

A step-by-step plan to deploy the platform (FastAPI backend + Next.js frontend + Neo4j) to
[Railway](https://railway.com). Grounded in the repo as it stands: `Dockerfile` (API),
`docker-compose.yml` (local topology), `frontend/` (Next.js 15), and `app/config.py`
(required env: `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD`, `LLM_PROVIDER`, `OPENAI_API_KEY`).

> Status: **deployed and live** — the platform runs on Railway at
> <https://frontend-production-10da.up.railway.app> (project `kg-coaching-platform`, `production`
> environment). The repo is Railway-ready: the changes in §2 are committed. If you are
> reproducing the deploy from scratch, do §2 first, and read **§11 — Deployment gotchas** before
> you start: four non-obvious traps (monorepo config-as-code, IPv6 private networking, the
> IPv6/healthcheck conflict, and the proxy allow-list) each cost a failed deploy the first time.

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

### 2a. API `railway.json` — `$PORT`, IPv6 bind, no healthcheck
`Dockerfile` ends with `CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]`.
Railway injects a dynamic `$PORT` **and** its private network is **IPv6-only**. The repo-root
`railway.json` overrides the Dockerfile CMD at run time (no Dockerfile edit needed) and is what
actually shipped:

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
  "deploy": {
    "startCommand": "sh -c 'uvicorn app.main:app --host :: --port ${PORT:-8000}'",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

Three things that are easy to get wrong here (all learned the hard way — see §11):
- **`--host ::`, not `0.0.0.0`.** The frontend reaches the API over the private network, which is
  **IPv6**. `0.0.0.0` listens on IPv4 only, so private traffic gets `ECONNREFUSED`. `::` is
  dual-stack.
- **Wrap the command in `sh -c '… ${PORT:-8000}'`.** Railway does not shell-expand `$PORT` in a
  bare `startCommand`, so `--port $PORT` fails with *"'$PORT' is not a valid integer"*. The
  `sh -c` wrapper expands it (and falls back to 8000).
- **No `healthcheckPath`.** Railway's healthchecker probes over **IPv4**, which can't reach an
  IPv6-only (`::`) listener, so a `/health` healthcheck makes every deploy fail after a 5-minute
  timeout. The API is private (the frontend is its only consumer), so we drop the healthcheck and
  let the deploy go live once uvicorn is up. (`/health` still exists for manual checks.)

> **Dockerfile note:** `COPY pyproject.toml ./` and `COPY app ./app` must come **before**
> `RUN pip install .` — the wheel build needs the `app` package present, or the image build fails
> with *"package directory 'app' does not exist"*.

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
      { source: '/chat', destination: `${api}/chat` },
    ];
  },
};
module.exports = nextConfig;
```

With this, the frontend keeps `NEXT_PUBLIC_API_BASE` empty (same-origin `/members`, …) and the
Next server forwards to `API_PROXY_TARGET` over the private network.

> **The rewrite list is an allow-list — keep it in sync with the API.** Only the paths listed
> here are proxied; any endpoint you add later (e.g. `/chat`, added in Milestone 2) must be added
> here too, or it 404s in production while working fine locally.

### 2d. Frontend build config — a *per-service* `railway.json` (the monorepo trap)
This repo is a monorepo: one Git repo, two deployable services (the Python API at the root, the
Next.js app in `frontend/`). Railway's **config-as-code takes precedence over dashboard/service
settings**, and it reads the config file from each service's *root directory*. The repo-root
`railway.json` (§2a) says `builder: DOCKERFILE` — and if the frontend service also deploys from
the repo root, that file is applied to it too, so **the frontend service builds the Python API**
(and then 500s with missing `NEO4J_*` vars). Setting the builder in the dashboard does *not* help
— config-as-code wins.

The fix is two coupled settings:

1. Commit a **`frontend/railway.json`** so the frontend gets its own config:

   ```json
   {
     "$schema": "https://railway.com/railway.schema.json",
     "build": { "builder": "NIXPACKS" },
     "deploy": {
       "startCommand": "npm run start",
       "healthcheckPath": "/",
       "restartPolicyType": "ON_FAILURE"
     }
   }
   ```

2. Pin the **frontend service's Root Directory to `frontend`** (see §6). This makes Railway read
   `frontend/railway.json` instead of the repo-root one, so the frontend builds as a Next.js app
   via nixpacks (`npm run build` / `npm run start`, binding `$PORT` automatically). Unlike the
   private API, the frontend *is* public and `next start` serves `/`, so a `/` healthcheck is fine.

> The Root Directory is a **service setting**, not something the repo can carry — it's the pointer
> that tells Railway where to find `frontend/railway.json` (chicken-and-egg). Set it once per
> service (§6); it persists across deploys.

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
- The repo changes in §2 committed (root `railway.json`, env-driven proxy incl. `/chat`, the seed
  entrypoint, and `frontend/railway.json`).

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
# Pin the API port so it matches the frontend's proxy target (:8000). The API is private-only,
# so a fixed port is fine; the startCommand's ${PORT:-8000} then always resolves to 8000.
railway variable set PORT=8000 --service api
```

> **Never set a secret with `railway add --variables "OPENAI_API_KEY=$KEY"`** — that form echoes
> the value to the console. Use `railway variable set` (and redirect output if scripting). If a
> key is ever printed, rotate it.

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

- **api** — builder: Dockerfile (via root `railway.json`); binds `::` (IPv6); **no** healthcheck
  (§2a); private only (don't add a public domain) unless you want `/docs` exposed. If you *do*
  expose it, add CORS (`fastapi.middleware.cors.CORSMiddleware`) and point the frontend at the
  public URL via `NEXT_PUBLIC_API_BASE` instead of the proxy. Leave Root Directory unset (it
  deploys from the repo root and uses the root `railway.json`).
- **frontend** — set **Root Directory** = `frontend` (this is what makes Railway read
  `frontend/railway.json` instead of the repo-root one — see §2d, and it's the difference between
  a Next.js build and accidentally building the Python API). Builder nixpacks; build `npm run
  build`; start `npm run start` (Next binds `$PORT` automatically); `/` healthcheck. Add a
  **public domain** (Railway-generated `*.up.railway.app`, or a custom domain). This is the only
  public surface.

  Set it from the CLI (or the dashboard → Settings → Source → Root Directory):
  ```bash
  FE=$(railway service list --json | jq -r '.[]|select(.name=="frontend").id')
  railway environment edit --json <<JSON
  {"services":{"'"$FE"'":{"source":{"rootDirectory":"/frontend"},"build":{"builder":"NIXPACKS"}}}}
  JSON
  ```
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
2. `api` deployment `SUCCESS` and a clean start in the logs
   (`railway logs --service api` → *"Uvicorn running …"*, no `Settings` validation error). The API
   has no healthcheck, so `SUCCESS` here just means the container started — real connectivity is
   proven by step 4.
3. Seed ran: `railway run --service api python -m app.ingestion.seed` printed no errors.
4. Through the **frontend public URL** (which proves the IPv6 proxy hop end-to-end):
   ```bash
   BASE=https://<your-frontend>.up.railway.app
   curl -s "$BASE/members"                                              # members list
   curl -s -X POST "$BASE/generate/workout" -d '{"member_id":"member_ava"}' -H 'Content-Type: application/json'
   curl -s -X POST "$BASE/generate/insight" -d '{"member_id":"member_ava"}' -H 'Content-Type: application/json'
   curl -s -X POST "$BASE/chat" -d '{"member_id":"member_ava","message":"How is her rehab?"}' -H 'Content-Type: application/json'
   ```
   Each returns JSON (a `500` with an empty content-type means the proxy couldn't reach the API —
   check `railway logs --service frontend` for `ECONNREFUSED`, which points at §11 #2). Then open
   the URL in a browser → members load → pick an injured member → the Overview/Workout/Insights/
   Trends/Chat tabs all work (real OpenAI end-to-end).

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

---

## 11. Deployment gotchas (learned in production)

These four bit the very first deploy of each service. None are hypothetical — each is baked into
the committed config above; this section explains *why*, so a future redeploy (or a fresh project)
doesn't rediscover them. Symptom → cause → fix:

1. **The frontend service built the Python API and 500'd with missing `NEO4J_*`.**
   *Cause:* monorepo + Railway **config-as-code precedence**. The repo-root `railway.json`
   (`builder: DOCKERFILE`) is applied to *any* service that deploys from the repo root — including
   the frontend — and it overrides dashboard/service build settings, so `railway up --service
   frontend` built the API's Dockerfile. *Fix:* commit **`frontend/railway.json`** (nixpacks) and
   pin the frontend service's **Root Directory = `frontend`** so Railway reads that file instead
   (§2d, §6). Tell-tale: the "frontend" logs show FastAPI/uvicorn tracebacks.

2. **Frontend proxy → API failed with `connect ECONNREFUSED fd12:…:8000` (IPv6 address).**
   *Cause:* Railway's private network is **IPv6-only**; the API bound `--host 0.0.0.0` (IPv4 only),
   so nothing listened on the IPv6 address the frontend resolved. *Fix:* bind `--host ::` (§2a).
   Tell-tale: `railway logs --service frontend` shows the `ECONNREFUSED` with an `fd12:…` address,
   and the API logs show *no* incoming request for the path.

3. **After switching the API to `::`, every deploy failed after ~5 min in `DEPLOYING`.**
   *Cause:* the `/health` **healthcheck probes over IPv4**, which can't reach an IPv6-only (`::`)
   listener, so it times out and marks the deploy `FAILED` even though the app started fine.
   *Fix:* remove `healthcheckPath` from the API's `railway.json` (§2a). The API is private, so the
   frontend's own requests are the real health signal.

4. **A new endpoint (`/chat`) worked locally but 404'd in production.**
   *Cause:* the Next.js `rewrites()` proxy is an **allow-list**; only listed paths are forwarded.
   *Fix:* add each new API path to `frontend/next.config.js` (§2b).

**Also worth remembering**
- Railway does not shell-expand `$PORT` in a bare `startCommand` — wrap it: `sh -c '… ${PORT:-8000}'`
  (§2a).
- The API Dockerfile must `COPY app ./app` **before** `pip install .` (§2a note).
- `railway up` builds the **working directory**, not a Git ref — so a local edit deploys without a
  commit. Commit anyway, or prod and `main` silently diverge.
- `railway deployment list` reports `QUEUED`/`BUILDING`/`DEPLOYING` before a terminal
  `SUCCESS`/`FAILED` — always poll to a terminal state; don't trust the first status.
