---
id: 005
title: Member seed ingestion (timestamped, idempotent)
status: tests-authored
depends_on: [002, 004]
branch: ticket/005-member-ingestion
base_branch: ticket/004-ontology-snomed-seed
test_command: ".venv/bin/python -m pytest tests/test_ingestion.py -q"
full_suite_command: ".venv/bin/ruff check . && .venv/bin/mypy app && .venv/bin/python -m pytest -q"
attempts: 1
---

## Description
Ingestion Service loading sample members with related entities — profiles, injuries, goals,
timestamped workouts, biometrics, AdherenceRecords, chat history, transcripts — from seed
fixtures via idempotent upserts.

## Acceptance criteria
- [ ] Seed fixtures for >=3 members incl. at least one with an active injury and multi-week history
- [ ] All related entities linked with correct edges + timestamps
- [ ] Re-running ingestion does not duplicate nodes/edges
- [ ] Adherence and biometric records span multiple dates (enables temporal work in M2)

## Test plan (orchestrator authors these)
- unit: `tests/test_ingestion.py` — fixture integrity (>=3 members, one injured, multi-week
  dated records) as pure-data assertions; node/edge counts + idempotency as an integration
  check that skips cleanly if Neo4j unavailable
