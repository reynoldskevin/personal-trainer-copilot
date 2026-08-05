---
id: 002
title: Graph schema + Neo4j connection layer
status: tests-authored
depends_on: [001]
branch: ticket/002-graph-schema-connection
base_branch: ticket/001-scaffold-docker-compose
attempts: 1
test_command: ".venv/bin/python -m pytest tests/test_graph_schema.py -q"
full_suite_command: ".venv/bin/ruff check . && .venv/bin/mypy app && .venv/bin/python -m pytest -q"
---

## Description
Typed Neo4j access layer + schema bootstrap: node labels (Member, Injury, Goal, Workout,
Exercise, BiometricReading, AdherenceRecord, ChatMessage, Transcript, SnomedConcept,
BodyRegion, MuscleGroup, Equipment), constraints/uniqueness, and indexes. Time-varying
records carry a `timestamp` property.

## Acceptance criteria
- [ ] Schema bootstrap creates constraints + indexes idempotently (safe to run twice)
- [ ] Typed helpers for run/read/write with parameterized Cypher (no string interpolation)
- [ ] Time-varying node types persist and read back a `timestamp`
- [ ] Schema init raises no duplicate-constraint errors on re-run

## Test plan (orchestrator authors these)
- unit: `tests/test_graph_schema.py` — constraints/indexes present after bootstrap, idempotent
  re-run, write+read a Member round-trips (integration against the compose Neo4j; skip cleanly
  if Neo4j unavailable)
