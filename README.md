# Knowledge Graph Coaching Platform

A GraphRAG coaching backend: it answers questions and generates **injury-safe** training plans for
a member by fusing a **Neo4j knowledge graph** (the member's injuries, goals, workout history,
adherence and biometrics, plus a clinical ontology of exercises and contraindications) with
**semantic vector retrieval** and an **LLM**. Every generated plan is passed through a
deterministic guardrail that strips exercises contraindicated for the member's active injuries, so
the graph — not the model — has the final say on safety.

Modular-monolith backend: **FastAPI + Neo4j + OpenAI**, with a Next.js coach dashboard in
`frontend/`.

## What's inside

- **Graph knowledge base** — members, injuries, goals, workouts, biometrics, adherence, and a
  SNOMED-anchored exercise/contraindication ontology (`app/ingestion/`, `app/graph/`).
- **Hybrid retrieval** — a global vector search fused with a member-scoped subgraph traversal,
  token-budgeted into one context bundle (`app/retrieval/`).
- **Guarded generation** — workout plans, insight reports and context-grounded chat, each
  filtered by an injury-safety guardrail (`app/generation/`).
- **Observability, evals & scale** — tracing/latency/token accounting, a labelled evals harness
  with retrieval + safety scoring, and a batched synthetic loader for scale testing
  (`app/observability/`, `evals/`, `app/ingestion/scale.py`).

## Quickstart (Docker)

Boot the graph + API and load the demo data — under 10 minutes from a clean checkout:

```bash
cp .env.example .env          # add your OPENAI_API_KEY
docker compose up -d          # starts Neo4j + the API
docker compose run --rm api python -m app.ingestion.seed   # seed schema + ontology + members + embeddings
```

- API: <http://localhost:8000> — health check `GET /health`.
- Interactive API docs (OpenAPI/Swagger): <http://localhost:8000/docs>.
- Neo4j Browser: <http://localhost:7474> (user `neo4j`, password `testpassword`).

### Demo it

```bash
curl http://localhost:8000/members                      # list seeded members
curl -X POST http://localhost:8000/generate/workout \
  -H 'content-type: application/json' \
  -d '{"member_id": "member_ava", "query": "shoulder rehab"}'   # injury-safe plan
```

`member_ava` has an active rotator-cuff injury — the returned plan will never include exercises
contraindicated for it, even though the raw model output might.

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

# With a local Neo4j reachable at bolt://localhost:7687:
python -m app.ingestion.seed        # seed the graph
uvicorn app.main:app --reload       # serve the API at http://localhost:8000
```

`.env.example` documents the required variables (Neo4j connection + `OPENAI_API_KEY`). The app
fails fast if a required variable is missing.

### Quality gates

```bash
pytest -q            # unit + integration tests (integration tests skip if Neo4j is down)
ruff check .         # lint (line-length 100; E/F/I/UP/B)
mypy app             # strict type-check
```

### Scale load

Load a large synthetic graph to validate batched ingest and index-backed member scoping:

```bash
python -m app.ingestion.scale --nodes 100000 --batch-size 500
```

See [docs/scale.md](docs/scale.md) for the method and the path to ~100M nodes.

## HTTP API

| Method & path | Purpose |
|---|---|
| `GET /health` | Liveness/health probe |
| `GET /members` | List seeded members |
| `GET /members/{member_id}` | One member's detail |
| `POST /retrieve` | Fused GraphRAG context bundle for a member + query |
| `POST /generate/workout` | Injury-safe workout plan |
| `POST /generate/insight` | Coaching insight report |
| `POST /chat` | Context-grounded chat answer |

Full request/response schemas are browsable at `/docs` (OpenAPI).

## Architecture & docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — components, trust boundaries, key tradeoffs.
- [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md) — component/interaction diagram.
- [docs/ontology_mapping.md](docs/ontology_mapping.md) — SNOMED subset + exercise/contraindication model.
- [docs/token_budget.md](docs/token_budget.md) — token/context budgeting.
- [docs/performance.md](docs/performance.md) — latency verification (<5s p95).
- [docs/scale.md](docs/scale.md) — batched ingest + the path to 100M nodes.
- [evals/README.md](evals/README.md) — evaluation dataset, harness and scoring.
- [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md) — deploying the api + frontend to Railway.

## Layout

```
app/
  config.py        # pydantic-settings Settings (env-driven, fail-fast)
  main.py          # FastAPI app + /health
  graph/           # Neo4j access + schema/constraints/indexes
  ingestion/       # ontology + member seed + synthetic scale loader
  retrieval/       # hybrid graph + vector retrieval
  generation/      # workout / insight / chat + injury-safety guardrail
  llm/             # LLM provider adapters
  api/             # HTTP routers
  observability/   # tracing / latency / token accounting
frontend/          # Next.js coach dashboard
evals/             # evaluation dataset + harness + scoring
docs/              # ontology, token budget, performance, scale notes
```

## Commit conventions

Conventional-commit style, scoped by **ticket number**, so history maps to the build plan
(`TICKETS.md`). Each ticket lands two commits: the locked tests first, then the implementation —
e.g. `test(22): …` then `feat(22): …` (`fix(NN): …` for fixes). Tests are authored before the
implementation and are the contract the code must satisfy.
