---
id: 008
title: Generation — WorkoutPlan + injury-safe guardrail (basic)
status: ready-for-merge
depends_on: [003, 007]
branch: ticket/008-generation-guardrail
base_branch: ticket/007-hybrid-retrieval
test_command: ".venv/bin/python -m pytest tests/test_generation_workout.py -q"
full_suite_command: ".venv/bin/ruff check . && .venv/bin/mypy app && .venv/bin/python -m pytest -q"
attempts: 1
---

## Description
LangGraph pipeline: retrieve → **pre-filter contraindicated exercises** → assemble prompt →
`LLMProvider.chat` → **post-validate** output against the contraindication set → typed `WorkoutPlan`.

## Acceptance criteria
- [ ] Returns a schema-valid `WorkoutPlan` (Pydantic) personalized to member goals/context
- [ ] Contraindicated exercises are removed before the LLM sees candidates
- [ ] Post-validation rejects/repairs any contraindicated exercise in the output (0 unsafe in final)
- [ ] LLM is mocked in tests; a mocked "unsafe" completion is caught by post-validation

## Test plan (orchestrator authors these)
- unit: `tests/test_generation_workout.py` — Pydantic models + pure `filter_contraindicated`
  post-validation as pure-data assertions; schema-valid generation, pre-filter hiding
  contraindicated candidates from the LLM, post-validate stripping an injected unsafe pick, and
  the zero-contraindicated invariant as an integration check that skips cleanly if Neo4j down
