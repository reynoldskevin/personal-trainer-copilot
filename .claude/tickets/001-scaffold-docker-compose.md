---
id: 001
title: Repo scaffold + Docker Compose
status: ready-for-merge
depends_on: []
branch: ticket/001-scaffold-docker-compose
base_branch: main
test_command: ".venv/bin/python -m pytest tests/test_health.py tests/test_config.py -q"
full_suite_command: ".venv/bin/ruff check . && .venv/bin/mypy app && .venv/bin/python -m pytest -q"
attempts: 1
---

## Description
Stand up the modular-monolith layout and one-command local setup: Python package under
`app/` (ingestion, graph, retrieval, generation, llm, api, observability), plus `frontend/`,
`evals/`, `tests/`. Add env-based config, a FastAPI `/health` endpoint reporting Neo4j
connectivity, and a `docker-compose.yml` bringing up Neo4j + the API. This ticket bootstraps
the toolchain (pytest, ruff, mypy, fastapi, neo4j driver) into a `.venv`.

## Acceptance criteria
- [ ] `.venv` exists with pytest, ruff, mypy, fastapi, uvicorn, neo4j, pydantic-settings installed
- [ ] `GET /health` returns 200 with `{status, neo4j: <bool|status>}`
- [ ] Config loads Neo4j + OpenAI settings from env; missing required vars fail fast with a clear error
- [ ] `docker-compose.yml` defines Neo4j + api services (compose config validates)
- [ ] ruff + mypy pass on the scaffold

## Test plan (orchestrator authors these)
- unit: `tests/test_health.py` (health payload shape via FastAPI TestClient, Neo4j dep mockable),
  `tests/test_config.py` (env validation: required-var-missing raises, valid env parses)
