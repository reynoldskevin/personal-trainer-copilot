---
id: 006
title: Embeddings + Neo4j native vector index
status: tests-authored
depends_on: [003, 005]
branch: ticket/006-embeddings-vector-index
base_branch: main
test_command: ".venv/bin/python -m pytest tests/test_vector_index.py -q"
full_suite_command: ".venv/bin/ruff check . && .venv/bin/mypy app && .venv/bin/python -m pytest -q"
attempts: 0
---

## Description
Compute embeddings (via `LLMProvider.embed`) for text-bearing nodes (ChatMessage, Transcript, Goal,
Exercise) and store them in a Neo4j **native vector index**; expose a similarity query.

## Acceptance criteria
- [ ] Embeddings generated + stored on text-bearing nodes during/after ingest
- [ ] Neo4j vector index created; top-k similarity query returns ranked nodes with scores
- [ ] Embedding provider mockable in tests (deterministic vectors)
- [ ] Re-embedding is idempotent (no duplicate vectors)

## Test plan (orchestrator authors these)
- unit: `tests/test_vector_index.py` — text-source map + query embedding as pure-data assertions;
  index existence, top-k ranked scoring, semantic nearest-neighbour, and idempotency as an
  integration check that skips cleanly if Neo4j unavailable
