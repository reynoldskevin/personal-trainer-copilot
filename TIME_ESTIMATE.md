# Time Estimate — Knowledge Graph Coaching Platform

**Unit:** ideal engineering hours (single developer, focused). Estimates assume the stack in
ARCHITECTURE.md (Neo4j single-datastore, OpenAI via `LLMProvider`, FastAPI + LangGraph + Next.js)
and the ticket granularity in TICKETS.md. Percentages are of the **mainline** (Milestones 1–4 only);
backlog/optional items are listed separately and excluded from the %.

Tickets touching curated data (004) or the core GraphRAG/generation path (007, 008) carry the widest
uncertainty and are flagged. Milestones are ordered **highest-value-first**, so the effort is
deliberately front-loaded into M1 (the demo).

## Summary — effort by milestone
| Milestone | Effort (h) | % of build | |
|---|---:|---:|---|
| M1 — MVP walking skeleton (safe workout, end-to-end) | 56 | 47% | █████░░░░░ |
| M2 — Insights, temporal & formal safety | 26 | 22% | ██░░░░░░░░ |
| M3 — Evals, observability & efficiency | 23 | 19% | ██░░░░░░░░ |
| M4 — CI/CD, scale & docs | 15 | 13% | █░░░░░░░░░ |
| **Total (mainline)** | **120** | **100%** | |
| Contingency (15%) | 18 | — | applied to unknowns (data curation, GraphRAG tuning) |
| Backlog (optional) | 40 | — | not in the mainline % |
| **Total with contingency** | **138** | — | fits the 2–3 week (≈80–120h focused) budget with buffer |

> Note: mainline is 120h; realistic calendar with contingency ≈138h. If the schedule tightens,
> stop after M2 (82h) for the full feature set, or after M1 (56h) for the core demo — both are
> coherent, defensible stop-points (see BUILD_PLAN.md value ladder).

## Milestone 1 — MVP walking skeleton (safe personalized workout, end-to-end)
| Ticket | Title | Effort (h) | Notes / assumptions |
|---|---|---:|---|
| 001 | Repo scaffold + Docker Compose | 5 | Compose + config + health |
| 002 | Graph schema + Neo4j connection layer | 4 | |
| 003 | LLMProvider interface + OpenAI impl | 4 | Mockable; abstraction seam |
| 004 | Ontology + SNOMED subset + contraindication seed | 7 | **Wide (5–10):** curation is the main unknown |
| 005 | Member seed ingestion (timestamped) | 6 | Multi-week fixtures for M2 temporal work |
| 006 | Embeddings + Neo4j native vector index | 5 | |
| 007 | Retrieval Service: hybrid GraphRAG | 7 | **Wide (6–11):** fusion + ranking tuning |
| 008 | Generation: WorkoutPlan + injury-safe guardrail (basic) | 7 | **Wide (6–10):** pre-filter + post-validate |
| 009 | FastAPI endpoints (members/retrieve/generate) | 5 | Typed Pydantic contracts |
| 010 | Minimal coach dashboard (Next.js) | 6 | Functional, not polished |
| | **M1 subtotal** | **56** | 47% of build — the demo |

## Milestone 2 — Insights, temporal reasoning & formal safety
| Ticket | Title | Effort (h) | Notes / assumptions |
|---|---|---:|---|
| 011 | Temporal trends + last-N-weeks windowing | 6 | Trend math on seed fixtures |
| 012 | InsightReport + /generate/insight | 5 | |
| 013 | Guardrails module (formal) | 6 | Repair/reject loop, shared |
| 014 | Chat endpoint (context-only) | 3 | Reuses retrieval + guardrail |
| 015 | Dashboard: insights, trends & chat | 6 | |
| | **M2 subtotal** | **26** | 22% of build |

## Milestone 3 — Evals, observability & efficiency
| Ticket | Title | Effort (h) | Notes / assumptions |
|---|---|---:|---|
| 016 | LangFuse observability (traces) | 4 | Mock/no-op in CI |
| 017 | Token/context budgeting + prompt efficiency | 4 | |
| 018 | Evals dataset (retrieval + safety) | 5 | Labeling effort |
| 019 | Evals harness + scoring | 6 | Deterministic with mocks |
| 020 | Performance verification (<5s p95) | 4 | Stub provider latency |
| | **M3 subtotal** | **23** | 19% of build |

## Milestone 4 — CI/CD, scale & docs
| Ticket | Title | Effort (h) | Notes / assumptions |
|---|---|---:|---|
| 021 | CI: ruff + mypy + pytest + eval smoke | 4 | Neo4j service container |
| 022 | Scale: batched ingest + 100K synthetic load | 6 | Index validation; 100M documented |
| 023 | Documentation & submission polish | 5 | Continuous, finalized here |
| | **M4 subtotal** | **15** | 13% of build |

## Backlog (optional / beyond-brief — excluded from mainline %)
| Item | Effort (h) | Notes |
|---|---:|---|
| AWS Bedrock AgentCore provider | 4 | New impl behind `LLMProvider` |
| Full SNOMED CT ingest | 12 | Licensing + large loader + scale |
| Live AWS deployment (Aura + ECS/Amplify) | 10 | Containers already built |
| Streaming responses / real-time biometric ingestion | 6 | Async paths already in place |
| Separate/managed vector store (pgvector/OpenSearch) | 8 | Only if vector scale outgrows Neo4j |
| | **Backlog total** | **40** | build only if time allows |

## Basis & honesty notes
- Estimates assume the ARCHITECTURE.md stack decisions hold; a change (e.g. Neptune, Bedrock-first)
  would revise M1 materially.
- The three widest tickets (004 data curation, 007 retrieval fusion, 008 safe generation) drive most
  of the uncertainty — their ranges are shown inline; contingency (15% = 18h) is the explicit buffer.
- Ticket ids, titles, and milestone grouping match TICKETS.md and BUILD_PLAN.md exactly. Revising
  tickets later must revise this file too.
