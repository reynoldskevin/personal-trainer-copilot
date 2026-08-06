# Token / context budgeting + prompt efficiency (Ticket 017)

This platform bounds how many tokens of retrieved context reach the model, keeps prompt assembly
lean, and asks the JSON generators for compact structured output. This document records the rules,
the knobs, and before/after numbers.

## Configurable context budget

- **Knob:** `CONTEXT_TOKEN_BUDGET` (env) → `Settings.context_token_budget`, default **2000** tokens.
- **Resolution:** `app.generation.budget.resolve_budget(explicit, settings)` returns the per-call
  budget when a request supplies one, else the environment default. The `POST /retrieve` route
  resolves the budget this way, so the deployment can tune context size without a code change.
- Token estimation uses one shared heuristic everywhere (`len(text) // 4`), exposed as
  `app.observability.tracing.estimate_tokens` and re-exported by `app.generation.budget`, so
  retrieval budgeting, trace token counts, and the prompt-assembly guard all agree.

## Truncation is strict rank-prefix (before → after)

Retrieval fuses candidates already ordered by importance: trend summaries → member subgraph facts
→ vector-hit texts. `budget.truncate_to_budget(items, budget)` keeps the **highest-ranked prefix**
whose running token estimate stays within budget and stops at the first item that would overflow.

- **Before:** a greedy budgeter that *skipped* an over-budget item and kept scanning — it could
  drop a higher-ranked item yet still admit a lower-ranked smaller one, so the kept set was not a
  clean prefix of the ranking.
- **After:** strict prefix. Example — `truncate_to_budget(["short", "X"*400, "tiny"], budget=20)`
  returns `(["short"], 1)`: the oversized second item halts truncation and the small `"tiny"` is
  **not** smuggled in ahead of rank. The kept context is always an honest top-of-ranking slice.

Contraindications are **never** budget-dropped — they are safety data and are always returned in
full, independent of `context_token_budget`.

## Prompt-assembly efficiency + regression guard

- Workout prompt assembly is a pure function, `workout.build_workout_messages(context, candidates)`,
  so its size is measurable without a model call.
- **`workout.WORKOUT_PROMPT_TOKEN_BUDGET = 3000`** guards against prompt bloat; the test suite
  fails if a representative assembly exceeds it.

| Measurement | Tokens |
|---|---|
| Workout system prompt | 89 |
| Representative assembled workout prompt (12 context facts + 30 candidates) | 461 |
| Regression ceiling (`WORKOUT_PROMPT_TOKEN_BUDGET`) | 3000 |

## Structured JSON output minimizes output tokens

The workout and insight generators request a strict JSON object via the shared
`budget.RESPONSE_FORMAT = {"type": "json_object"}`. Compact, directly-parseable JSON avoids the
token overhead (and parsing fragility) of free-form prose while remaining machine-readable. The
coach-facing chat endpoint stays free-text by design — it is a conversational answer, not a record.

## Where it lives

- `app/generation/budget.py` — `truncate_to_budget`, `resolve_budget`, `count_prompt_tokens`,
  `RESPONSE_FORMAT`, `estimate_tokens`.
- `app/retrieval/service.py` — retrieval delegates truncation to `budget.truncate_to_budget`.
- `app/generation/workout.py` — `build_workout_messages`, `WORKOUT_PROMPT_TOKEN_BUDGET`.
- `app/config.py` — `context_token_budget`.
- Tests: `tests/test_token_budget.py`.
