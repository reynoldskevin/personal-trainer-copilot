---
id: 007
title: Retrieval Service — hybrid GraphRAG
status: tests-authored
depends_on: [004, 006]
branch: ticket/007-hybrid-retrieval
base_branch: ticket/006-embeddings-vector-index
test_command: ".venv/bin/python -m pytest tests/test_retrieval.py -q"
full_suite_command: ".venv/bin/ruff check . && .venv/bin/mypy app && .venv/bin/python -m pytest -q"
attempts: 0
---

## Description
Hybrid retrieval fusing vector search + member-scoped subgraph traversal into a ranked,
token-bounded context bundle, plus the member's **contraindication set** (from `CONTRAINDICATED_FOR`).

## Acceptance criteria
- [ ] `retrieve(member_id, query)` returns a context bundle (vector hits + subgraph facts) + contraindication set
- [ ] Traversal is member-scoped (cost tracks subgraph, not global graph)
- [ ] Context bundle is token-bounded (respects a configurable budget)
- [ ] Contraindication set correctly lists exercises unsafe for the member's active injuries

## Test plan (orchestrator authors these)
- unit: `tests/test_retrieval.py` — token-estimate + ContextBundle model as pure-data assertions;
  bundle shape, member-scoped traversal, token-budget enforcement, and contraindication-set
  correctness as an integration check that skips cleanly if Neo4j unavailable
