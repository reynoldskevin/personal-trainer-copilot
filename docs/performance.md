# Performance verification (Ticket 020)

Target: **p95 latency < 5 s** for `/generate/workout`, excluding the language model's own response
time. This document records the method and the measured numbers.

## Method

- Harness: `app/observability/perf.py` (`run_workout_benchmark`), exercised by `tests/test_perf.py`.
- The LLM provider is **stubbed to ~zero latency** (a fake that returns a fixed JSON plan and
  deterministic embeddings). Provider latency in production is real but is outside our control and
  dominates the wall clock; stubbing it isolates **our** overhead — Neo4j round-trips, member-scoped
  retrieval, candidate pre-filtering, and plan assembly.
- Each run is timed twice: the full end-to-end `generate_workout`, and the retrieval step on its
  own, so retrieval/assembly overhead is reported separately from the whole pipeline.
- Latencies are summarized as p50/p95 (plus mean/max) using a nearest-rank percentile.
- The regression gate: `run_workout_benchmark(...).end_to_end.p95_ms < DEFAULT_P95_BUDGET_MS`
  (5000 ms).

## Measured numbers

Local run — 3 seed members × 10 iterations (30 samples), Neo4j 5.26 on the dev machine:

| stage | n | p50 (ms) | p95 (ms) | mean (ms) | max (ms) |
|---|---|---|---|---|---|
| end-to-end generate | 30 | 10.4 | 13.8 | 10.7 | 13.9 |
| retrieval only | 30 | 6.9 | 8.3 | 6.9 | 9.1 |

**p95 end-to-end overhead ≈ 14 ms — ~360× under the 5 s budget.** Retrieval is the largest single
component (~8 ms p95); the remaining ~6 ms is the candidate pre-filter query + parse + guardrail +
plan assembly. The 5 s budget is therefore comfortably met even after adding a real provider's
response time, and leaves ample headroom for the larger graphs measured in the scale work
(ticket 022).

Reproduce: the benchmark runs in CI via `tests/test_perf.py` (asserting the budget), or manually
against a running Neo4j with the snippet in `run_workout_benchmark`'s docstring.
