# Build Plan — Knowledge Graph Coaching Platform

## Approach

MVP-first and **value-first**. The plan front-loads the single highest-value capability — a
**safe, personalized, graph-grounded workout generated end-to-end** — into Milestone 1 as a thin
vertical slice through every layer (schema → ingest → GraphRAG retrieval → injury-aware generation
→ typed API → minimal dashboard). This is the demo that proves the thesis, so it must exist before
anything is deepened.

Because time may run short, **every milestone is a coherent stop-point**: you can halt after any
one and still have a working, defensible system. Later milestones add value in descending order —
insights + temporal reasoning (the second differentiator), then evals/observability (what makes
quality *provable*), then CI/scale/docs (hardening and submission polish). Safety is never absent:
a basic pre-filter + post-validate guardrail ships in M1 and is formalized in M2.

Optional/beyond-brief work (Bedrock, full SNOMED, live AWS deploy, 100M-scale, streaming) sits in
the Backlog, each attached to an extension point from ARCHITECTURE.md so it can be added without
mainline rework.

**Stop-point value ladder:**
- After **M1** → live demo: pick a member with an injury → get a safe, personalized workout grounded in their context.
- After **M2** → full feature set: insights, temporal trends, formal guardrails, chat context.
- After **M3** → *provable* quality: eval scores + LangFuse traces + <5s latency + token efficiency.
- After **M4** → submission-ready: green CI, documented scaling, complete docs.

## Milestone 1 — MVP walking skeleton: safe personalized workout, end-to-end (highest value)
Goal: satisfy the brief's core Functional Requirements as one demoable vertical slice.
- **Scope:** Docker Compose (Neo4j + API + frontend skeleton); graph schema + connection layer;
  `LLMProvider` interface + OpenAI impl (chat + embeddings); curated SNOMED/exercise/contraindication
  seed; timestamped member seed ingestion; embeddings + Neo4j native vector index; hybrid GraphRAG
  retrieval (vector + subgraph + contraindication set); LangGraph workout generation with
  **pre-filter + basic post-validate guardrail**; typed FastAPI (`/members`, `/retrieve`,
  `/generate/workout`); minimal Next.js dashboard.
- **Exit criteria:** `docker-compose up` boots the stack; calling `/generate/workout` for a seeded
  member **with an injury** returns a schema-valid `WorkoutPlan` that contains **zero contraindicated
  exercises** and reflects the member's goals/context; the dashboard renders it with safety flags.
- **Dependencies:** none (greenfield).

## Milestone 2 — Insights, temporal reasoning & formal safety (second differentiator)
Goal: complete the differentiated feature set beyond the base demo.
- **Scope:** temporal trends (adherence %, biometric slope, progression) + last-N-weeks retrieval
  windowing; `InsightReport` + `/generate/insight`; formalized Guardrails module (input + output
  validators + repair loop); `/chat` (context-only); dashboard views for insights, trends, chat, and
  safety flags.
- **Exit criteria:** `/generate/insight` returns progress + adherence/risk flags derived from
  timestamped data; guardrails reject/repair any contraindicated output in a repeatable test; chat
  answers are grounded in member context; dashboard surfaces insights + trends.
- **Dependencies:** M1.

## Milestone 3 — Provable quality: evals, observability & efficiency (graded, defensible)
Goal: make retrieval quality, safety, latency, and token cost measurable — not asserted.
- **Scope:** LangFuse tracing on retrieval + LLM calls (latency, tokens, prompt version); token/context
  budgeting + prompt efficiency; labeled eval dataset (retrieval quality + safety); evals harness/runner
  + scoring + report; performance verification (<5s p95).
- **Exit criteria:** `evals` run produces retrieval-quality + safety scores; LangFuse shows per-call
  latency/token traces; p95 generation latency measured < 5s on the seed set.
- **Dependencies:** M1 (M2 recommended for full coverage).

## Milestone 4 — Hardening & submission polish: CI/CD, scale, docs
Goal: deliver the remaining graded/submission artifacts and prove the scale story.
- **Scope:** GitHub Actions CI (ruff + mypy + pytest + eval smoke); batched ingest + synthetic
  100K-node load + index validation + documented scaling extension points; README + setup/run guide +
  API docs + architecture pointers + commit conventions.
- **Exit criteria:** CI green on a clean checkout; 100K synthetic graph ingests and retrieval stays
  within latency budget; docs let a new reader run and understand the system end-to-end.
- **Dependencies:** M3 (CI gates on the eval smoke); M1 (scale work).

## Backlog (optional / beyond-brief — build only if time allows)
| Optional deliverable | Extension point it attaches to (from ARCHITECTURE.md) |
|---|---|
| AWS Bedrock AgentCore provider | `LLMProvider` interface — add `BedrockProvider`, config-select |
| Full SNOMED CT ingest | `SnomedLoader` behind existing `MAPS_TO`/`AFFECTS` schema (subset is a strict subset) |
| Live AWS deployment | Containers already built → Neo4j Aura + ECS/Amplify (documented, not built) |
| Hundreds-of-millions-node scale | Managed/clustered Neo4j, read replicas, partitioning — hot paths already member-scoped |
| Streaming responses / real-time biometric ingestion | Async generation + ingestion; add stream/event source, no schema change |
| Separate/managed vector store | Retrieval's vector call is abstracted → swap Neo4j index for pgvector/OpenSearch |

## Deliverables map (Submission / graded artifacts → milestone)
> The brief has no explicit "Submission Requirements" section; these are the graded Code Quality
> Expectations + Functional artifacts, mapped to the milestone that produces them.

| Deliverable | Produced by milestone |
|---|---|
| Dockerized local setup (`docker-compose`) | M1 |
| Knowledge graph + schema | M1 |
| Vector search / retrieval REST API | M1 |
| AI workout recommendations (typed API) | M1 |
| Injury-aware filtering (structural safety) | M1 (basic) → M2 (formal guardrails) |
| Frontend dashboard | M1 (minimal) → M2 (insights/trends/chat) |
| Coaching insights | M2 |
| Longitudinal/temporal reasoning + adherence | M2 |
| Guardrails | M1 (basic) → M2 (module) |
| Evals | M3 |
| Observability / logging (LangFuse) | M3 |
| Token/prompt efficiency + <5s perf | M3 |
| CI/CD | M4 |
| Scalability (100K→ documented 100M) | M4 |
| Clear documentation | M4 (continuous throughout) |
| Typed APIs (Pydantic) | M1 (all endpoints) |
| Meaningful git history | All (per-ticket branches via tdd-ticket-loop) |

## Wireframes & Structure Contract

> Added by wireframe-project. The named structure dev + design both build against.
> Full detail: `STRUCTURE_CONTRACT.md`. Design bundle: `design/` (push with `/design-sync`).
> Token source: **neutral placeholders** (no brand source detected). Form factor: desktop-first responsive web.

### Flow
```
members-list → member-overview ─┬─ workout-generator
                                ├─ insights (M2)
                                ├─ trends    (M2)
                                └─ chat      (M2)
```
Hub shares one shell (`app-header`, `member-context-rail`, `tab-nav`) across all per-member tabs.

### Screen inventory
| Screen id | Title | Milestone | Status | Wireframe | Ticket(s) |
|---|---|---|---|---|---|
| members-list | Members | 1 | scheduled | design/screens/members-list.html | 010 |
| member-overview | Member · Overview | 1 | scheduled | design/screens/member-overview.html | 010 |
| workout-generator | Member · Workout | 1 | scheduled | design/screens/workout-generator.html | 010 |
| insights | Member · Insights | 2 | scheduled | design/screens/insights.html | 015 |
| trends | Member · Trends | 2 | scheduled | design/screens/trends.html | 015 |
| chat | Member · Chat | 2 | scheduled | design/screens/chat.html | 015 |

No backlog/structure-only screens — this is the full UI surface.

### Shared components
AppHeader — top bar · SearchBar — client-side member filter · MemberListItem — member row ·
MemberContextRail — persistent member facts · TabNav — hub tabs · InjuryBadge — SNOMED injury chip ·
StatusChip — safety/risk flag · Button — generic action · GenerateControl — goal hint + generate ·
WorkoutPlanCard — rendered plan · ExerciseRow — exercise + safety flag · SupportingContextPanel —
GraphRAG context · InsightReportCard — progress + notes · TrendChart — time-series · MetricStat —
KPI tile · ChatThread / ChatMessage / ChatComposer — chat · StatusView — empty/loading/error.

### Clashes resolved at the gate
| # | Clash | Sources | Resolution (approved) |
|---|---|---|---|
| 1 | Hub shell + `TabNav` ship in M1 (010) but Insights/Trends/Chat tabs activate in M2 (015) | structure vs plan | 010 builds the shell + `TabNav` with Overview + Workout active; M2 tabs visible but render `StatusView` "coming in M2" until 015 activates them. No rework. |
| 2 | `trends` is a dedicated screen; plan named "trends visualization" | structure vs plan | Built under existing ticket 015 (its criteria already require trends visualized); no new ticket. |
| 3 | `SearchBar` implies member search; API (009) has no search endpoint | structure vs architecture | `SearchBar` = client-side filter over the loaded list. Server-side search would be a new ticket, not silently added. |
| 4 | `SupportingContextPanel` surfaces `/retrieve` inside screens | structure vs plan | Consistent with architecture (`WorkoutPlan.supporting-context` + `/retrieve`); no separate inspector screen. |
