---
id: 009
title: FastAPI endpoints — members, retrieve, generate/workout
status: tests-authored
depends_on: [008]
branch: ticket/009-fastapi-endpoints
base_branch: ticket/008-generation-guardrail
test_command: ".venv/bin/python -m pytest tests/test_api_core.py -q"
full_suite_command: ".venv/bin/ruff check . && .venv/bin/mypy app && .venv/bin/python -m pytest -q"
attempts: 0
---

## Description
Typed FastAPI surface with Pydantic request/response models: `GET /members`, `GET /members/{id}`,
`POST /retrieve`, `POST /generate/workout`.

## Acceptance criteria
- [ ] All endpoints have typed Pydantic request/response models + OpenAPI schema
- [ ] `POST /generate/workout` returns a `WorkoutPlan` with safety flags
- [ ] Validation errors return 422 with clear messages
- [ ] `/retrieve` exposes the vector+graph search results

## Test plan (orchestrator authors these)
- unit: `tests/test_api_core.py` — TestClient with dependency overrides for the Neo4j client and
  LLM provider: list/detail/404, retrieve bundle, generate-workout safe plan + flags, 422 paths,
  and OpenAPI documentation. Integration-style; skips cleanly if Neo4j unavailable
