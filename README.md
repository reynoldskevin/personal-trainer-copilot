# Knowledge Graph Coaching Platform

Modular-monolith backend: FastAPI + Neo4j + OpenAI.

## Quickstart (Docker)

```bash
cp .env.example .env   # add your OPENAI_API_KEY
docker compose up
```

The API is served at http://localhost:8000 (health check: `GET /health`).
Neo4j Browser is at http://localhost:7474.

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

uvicorn app.main:app --reload
```

### Quality gates

```bash
pytest -q
ruff check .
mypy app
```

## Layout

```
app/
  config.py        # pydantic-settings Settings (env-driven, fail-fast)
  main.py          # FastAPI app + /health
  graph/           # Neo4j access (connectivity probe today)
  ingestion/       # document ingestion (future milestones)
  retrieval/       # graph retrieval
  generation/      # response generation
  llm/             # LLM provider adapters
  api/             # HTTP routers
  observability/   # logging / tracing / metrics
frontend/          # web client (future)
evals/             # evaluation harness (future)
```
