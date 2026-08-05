---
id: 004
title: Ontology + SNOMED subset + exercise/contraindication seed
status: tests-authored
depends_on: [002]
branch: ticket/004-ontology-snomed-seed
base_branch: ticket/002-graph-schema-connection
test_command: ".venv/bin/python -m pytest tests/test_ontology_seed.py -q"
full_suite_command: ".venv/bin/ruff check . && .venv/bin/mypy app && .venv/bin/python -m pytest -q"
attempts: 1
---

## Description
Curate and load the SNOMED CT subset (MSK injuries, body regions), the exercise catalog
(with MuscleGroup/Equipment), and the `CONTRAINDICATED_FOR` edges + `MAPS_TO`/`AFFECTS`/
`IN_REGION`/`TARGETS`/`REQUIRES` relationships. Ship a documented, versioned mapping table.

## Acceptance criteria
- [ ] Curated SNOMED subset + exercise catalog load into Neo4j idempotently
- [ ] `CONTRAINDICATED_FOR`, `MAPS_TO`, `AFFECTS`, `IN_REGION`, `TARGETS`, `REQUIRES` edges created
- [ ] A documented mapping table (injury <-> SNOMED concept <-> contraindicated exercises) exists in-repo
- [ ] Given an injury, a query returns its contraindicated exercises

## Test plan (orchestrator authors these)
- unit: `tests/test_ontology_seed.py` — mapping-table integrity + schema of the seed data
  (pure-data assertions, no Neo4j required); edge-creation + contraindication query as an
  integration check that skips cleanly if Neo4j unavailable
