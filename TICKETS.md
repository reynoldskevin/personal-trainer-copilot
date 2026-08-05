# Tickets — Knowledge Graph Coaching Platform

> Master index for the `tdd-ticket-loop` skill. Ordered by dependency; MVP milestone first,
> highest-value deliverables front-loaded. tdd-ticket-loop materializes each entry into
> `.claude/tickets/NNN-slug.md`.
>
> Toolchain: **pytest** (tests), **ruff** (lint), **mypy** (types). Python backend under `app/`,
> Next.js frontend under `frontend/`.
> Default `full_suite_command`: `ruff check . && mypy app && pytest`

---

## 001 — Repo scaffold + Docker Compose
- id: 001
- milestone: 1 (MVP)
- depends_on: []
- test_command: "pytest tests/test_health.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Stand up the modular-monolith layout (`app/{ingestion,graph,retrieval,generation,llm,api,observability}`,
`frontend/`, `evals/`, `tests/`), config/env loading (`.env`, no secrets committed), and a
`docker-compose.yml` bringing up Neo4j + the FastAPI app + a frontend skeleton. Add a `/health` endpoint.

**Acceptance criteria**
- [ ] `docker-compose up` starts Neo4j and the API without error
- [ ] `GET /health` returns 200 with service + Neo4j connectivity status
- [ ] Config reads Neo4j + OpenAI settings from env; missing required vars fail fast with a clear error
- [ ] ruff + mypy pass on the scaffold

**Test plan**
- unit: `tests/test_health.py` (health payload shape), `tests/test_config.py` (env validation)
- e2e: compose smoke — API reachable, Neo4j driver connects

## 002 — Graph schema + Neo4j connection layer
- id: 002
- milestone: 1 (MVP)
- depends_on: [001]
- test_command: "pytest tests/test_graph_schema.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Typed Neo4j access layer + schema bootstrap: node labels (Member, Injury, Goal, Workout, Exercise,
BiometricReading, AdherenceRecord, ChatMessage, Transcript, SnomedConcept, BodyRegion, MuscleGroup,
Equipment), constraints/uniqueness, and indexes. Time-varying records carry a `timestamp` property.

**Acceptance criteria**
- [ ] Schema bootstrap creates constraints + indexes idempotently
- [ ] Typed helpers for run/read/write with parameterized Cypher (no string interpolation)
- [ ] Time-varying node types persist and read back a `timestamp`
- [ ] Schema init is safe to run twice (no duplicate-constraint errors)

**Test plan**
- unit: `tests/test_graph_schema.py` (constraints/indexes present, idempotent re-run)
- integration: write+read a Member against a test Neo4j

## 003 — LLMProvider interface + OpenAI implementation
- id: 003
- milestone: 1 (MVP)
- depends_on: [001]
- test_command: "pytest tests/test_llm_provider.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Define the `LLMProvider` interface (`chat`, `embed`) and an `OpenAIProvider` concrete impl.
Provider is config-selected so Bedrock can slot in later. Include ret/timeout handling.

**Acceptance criteria**
- [ ] `LLMProvider` abstract interface with `chat()` and `embed()` signatures (typed)
- [ ] `OpenAIProvider` implements both; selected via config/env
- [ ] Calls are mockable in tests (no live API needed in CI)
- [ ] Timeout + basic retry on transient errors

**Test plan**
- unit: `tests/test_llm_provider.py` with a mocked OpenAI client (chat + embed shapes, retry path)

## 004 — Ontology + SNOMED subset + exercise/contraindication seed
- id: 004
- milestone: 1 (MVP)
- depends_on: [002]
- test_command: "pytest tests/test_ontology_seed.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Curate and load the SNOMED CT subset (MSK injuries, body regions), the exercise catalog (with
MuscleGroup/Equipment), and the `CONTRAINDICATED_FOR` edges + `MAPS_TO`/`AFFECTS`/`IN_REGION`
relationships. Ship a documented, versioned mapping table.

**Acceptance criteria**
- [ ] Curated SNOMED subset + exercise catalog load into Neo4j idempotently
- [ ] `CONTRAINDICATED_FOR`, `MAPS_TO`, `AFFECTS`, `IN_REGION`, `TARGETS`, `REQUIRES` edges created
- [ ] A documented mapping table (injury ↔ SNOMED concept ↔ contraindicated exercises) exists in-repo
- [ ] Given an injury, a Cypher query returns its contraindicated exercises

**Test plan**
- unit: `tests/test_ontology_seed.py` (edge counts, mapping-table integrity, idempotent reload)
- integration: contraindication query returns expected exercises for a known injury

## 005 — Member seed ingestion (timestamped, idempotent)
- id: 005
- milestone: 1 (MVP)
- depends_on: [002, 004]
- test_command: "pytest tests/test_ingestion.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Ingestion Service loading sample members with related entities — profiles, injuries, goals,
timestamped workouts, biometrics, `AdherenceRecord`s, chat history, transcripts — from seed
fixtures via idempotent upserts.

**Acceptance criteria**
- [ ] Seed fixtures for ≥3 members incl. at least one with an active injury and multi-week history
- [ ] All related entities linked with correct edges + timestamps
- [ ] Re-running ingestion does not duplicate nodes/edges
- [ ] Adherence and biometric records span multiple dates (enables temporal work in M2)

**Test plan**
- unit: `tests/test_ingestion.py` (node/edge counts, timestamps present, idempotency)
- integration: full seed load against test Neo4j

## 006 — Embeddings + Neo4j native vector index
- id: 006
- milestone: 1 (MVP)
- depends_on: [003, 005]
- test_command: "pytest tests/test_vector_index.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Compute embeddings (via `LLMProvider.embed`) for text-bearing nodes (ChatMessage, Transcript, Goal,
Exercise) and store them in a Neo4j **native vector index**; expose a similarity query.

**Acceptance criteria**
- [ ] Embeddings generated + stored on text-bearing nodes during/after ingest
- [ ] Neo4j vector index created; top-k similarity query returns ranked nodes with scores
- [ ] Embedding provider mockable in tests (deterministic vectors)
- [ ] Re-embedding is idempotent (no duplicate vectors)

**Test plan**
- unit: `tests/test_vector_index.py` (index exists, top-k ordering with mocked embeddings)
- integration: semantic query returns the expected chat/goal node

## 007 — Retrieval Service: hybrid GraphRAG
- id: 007
- milestone: 1 (MVP)
- depends_on: [004, 006]
- test_command: "pytest tests/test_retrieval.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Hybrid retrieval fusing vector search + member-scoped subgraph traversal into a ranked,
token-bounded context bundle, plus the member's **contraindication set** (from `CONTRAINDICATED_FOR`).

**Acceptance criteria**
- [ ] `retrieve(member_id, query)` returns a context bundle (vector hits + subgraph facts) + contraindication set
- [ ] Traversal is member-scoped (cost tracks subgraph, not global graph)
- [ ] Context bundle is token-bounded (respects a configurable budget)
- [ ] Contraindication set correctly lists exercises unsafe for the member's active injuries

**Test plan**
- unit: `tests/test_retrieval.py` (bundle shape, budget enforced, contraindication set correctness)
- integration: retrieval for the injured seed member excludes nothing yet but flags contraindications

## 008 — Generation: WorkoutPlan + injury-safe guardrail (basic)
- id: 008
- milestone: 1 (MVP)
- depends_on: [003, 007]
- test_command: "pytest tests/test_generation_workout.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
LangGraph pipeline: retrieve → **pre-filter contraindicated exercises** → assemble prompt →
`LLMProvider.chat` → **post-validate** output against the contraindication set → typed `WorkoutPlan`.

**Acceptance criteria**
- [ ] Returns a schema-valid `WorkoutPlan` (Pydantic) personalized to member goals/context
- [ ] Contraindicated exercises are removed before the LLM sees candidates
- [ ] Post-validation rejects/repairs any contraindicated exercise in the output (0 unsafe in final)
- [ ] LLM is mocked in tests; a mocked "unsafe" completion is caught by post-validation

**Test plan**
- unit: `tests/test_generation_workout.py` (schema valid, pre-filter applied, post-validate catches injected unsafe pick)
- integration: end-to-end generate for injured member → zero contraindicated exercises

## 009 — FastAPI endpoints: members, retrieve, generate/workout
- id: 009
- milestone: 1 (MVP)
- depends_on: [008]
- test_command: "pytest tests/test_api_core.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Typed FastAPI surface with Pydantic request/response models: `GET /members`, `GET /members/{id}`,
`POST /retrieve`, `POST /generate/workout`.

**Acceptance criteria**
- [ ] All endpoints have typed Pydantic request/response models + OpenAPI schema
- [ ] `POST /generate/workout` returns a `WorkoutPlan` with safety flags
- [ ] Validation errors return 422 with clear messages
- [ ] `/retrieve` exposes the vector+graph search results

**Test plan**
- unit: `tests/test_api_core.py` (TestClient: status codes, schema validation, 422 paths)
- e2e: generate-workout request end-to-end against seeded Neo4j (mocked LLM)

## 010 — Minimal coach dashboard (Next.js)
- id: 010
- milestone: 1 (MVP)
- depends_on: [009]
- test_command: "npm --prefix frontend test"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Minimal Next.js dashboard: member list → member detail → "Generate workout" → render the plan with
**safety flags** and the supporting context.

**Acceptance criteria**
- [ ] Member list + detail views call the API
- [ ] "Generate workout" renders the returned `WorkoutPlan` with visible safety flags
- [ ] Loading + error states handled
- [ ] Component/smoke test passes

**Test plan**
- unit: `frontend/__tests__/dashboard.test.tsx` (renders plan, shows safety flags, error state)
- e2e (manual/demo): pick injured member → generate → safe plan visible

**Wireframe & contract**
- screens: `members-list` (design/screens/members-list.html), `member-overview`
  (design/screens/member-overview.html), `workout-generator` (design/screens/workout-generator.html)
- must implement regions: `app-header`, `list-toolbar`, `members-list`, `list-status`,
  `member-context-rail`, `tab-nav`, `overview-metrics`, `overview-injuries`, `overview-goals`,
  `overview-recent-activity`, `workout-controls`, `workout-plan`, `workout-supporting-context`
- must place components: AppHeader, SearchBar, MemberListItem, MemberContextRail, TabNav, InjuryBadge,
  MetricStat, GenerateControl, WorkoutPlanCard, ExerciseRow, StatusChip, SupportingContextPanel, StatusView
- build the hub shell + `TabNav` now: Overview + Workout active; Insights/Trends/Chat tabs visible but
  render `StatusView` "coming in M2" (activated in ticket 015)
- `SearchBar` = client-side filter over the loaded list (no backend search endpoint)
- consume token slots only (no hardcoded colour/space/type): --color-*, --space-*, --radius-*, --font-*
- contract acceptance:
  - [ ] renders every named region for each screen in contract order
  - [ ] uses named components; no ad-hoc structural elements outside the contract
  - [ ] all visual values come from tokens (re-themes on token change; no hardcoded hues)
  - [ ] M2 tabs present but disabled with a `StatusView` placeholder

---

## 011 — Temporal trends + last-N-weeks windowing
- id: 011
- milestone: 2
- depends_on: [005, 007]
- test_command: "pytest tests/test_temporal.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Compute derived trends from timestamped data — adherence % over a window, biometric slope, workout
progression — and add a time-window parameter to retrieval so context can be scoped to "last N weeks."

**Acceptance criteria**
- [ ] Adherence % and biometric slope computed correctly over a window from seed data
- [ ] `retrieve(member_id, query, window)` scopes context to the window
- [ ] Trend summary included in the context bundle
- [ ] Deterministic results on the fixed seed set

**Test plan**
- unit: `tests/test_temporal.py` (trend math on known fixtures, window filtering)
- integration: windowed retrieval returns only in-window records + correct trend

## 012 — InsightReport + /generate/insight
- id: 012
- milestone: 2
- depends_on: [008, 011]
- test_command: "pytest tests/test_generation_insight.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
`InsightReport` schema + `/generate/insight` generation path: progress summary, adherence/risk flags,
personalization notes — grounded in trends + graph context, guardrailed like workouts.

**Acceptance criteria**
- [ ] `/generate/insight` returns a schema-valid `InsightReport` for a member
- [ ] Report reflects real trend signals (e.g. flags declining adherence on a declining fixture)
- [ ] Passes through the same guardrail path (no unsafe recommendations in insights)
- [ ] Typed endpoint + OpenAPI schema

**Test plan**
- unit: `tests/test_generation_insight.py` (schema, risk-flag logic on declining/improving fixtures, mocked LLM)
- e2e: insight request end-to-end

## 013 — Guardrails module (formal input + output validation)
- id: 013
- milestone: 2
- depends_on: [008]
- test_command: "pytest tests/test_guardrails.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Extract guardrails into a dedicated module: input validators (schema, member/injury presence) and
output validators (no contraindicated exercise, schema-valid, disclaimer present), with a
repair/reject loop shared by workout + insight generation.

**Acceptance criteria**
- [ ] Input validation rejects malformed/unsafe requests with clear errors
- [ ] Output validation catches contraindicated exercises and triggers repair or rejection
- [ ] Repair loop bounded (max N attempts, then safe failure)
- [ ] Reused by both workout and insight paths

**Test plan**
- unit: `tests/test_guardrails.py` (input reject cases, output-violation repair loop, bounded retries)

## 014 — Chat endpoint (context-only)
- id: 014
- milestone: 2
- depends_on: [008]
- test_command: "pytest tests/test_chat.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
`POST /chat {member_id, message}` answering with the member's GraphRAG context (history as context;
**no client-reply drafting**), guardrailed.

**Acceptance criteria**
- [ ] `/chat` returns a grounded answer citing/using member context
- [ ] Uses shared retrieval + guardrail path
- [ ] Typed request/response
- [ ] Does not produce client-facing drafted replies (context-only behavior verified)

**Test plan**
- unit: `tests/test_chat.py` (grounding uses retrieved context, guardrail applied, mocked LLM)

## 015 — Dashboard: insights, trends & chat
- id: 015
- milestone: 2
- depends_on: [010, 012, 014]
- test_command: "npm --prefix frontend test"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Extend the dashboard with an insights view (progress + risk flags), a trends visualization, and a
chat panel, all with safety flags surfaced.

**Acceptance criteria**
- [ ] Insights view renders `InsightReport` with risk flags
- [ ] Trends (adherence/biometric) visualized for a member
- [ ] Chat panel calls `/chat` and renders grounded answers
- [ ] Component/smoke tests pass

**Test plan**
- unit: `frontend/__tests__/insights.test.tsx`, `chat.test.tsx` (render + states)

**Wireframe & contract**
- screens: `insights` (design/screens/insights.html), `trends` (design/screens/trends.html),
  `chat` (design/screens/chat.html)
- must implement regions: `insight-summary`, `insight-flags`, `insight-supporting-context`,
  `trends-metrics`, `trends-charts`, `chat-thread`, `chat-composer`, `chat-supporting-context`
  (reusing the M1 hub shell: `app-header`, `member-context-rail`, `tab-nav`)
- must place components: InsightReportCard, StatusChip, SupportingContextPanel, MetricStat, TrendChart,
  ChatThread, ChatMessage, ChatComposer
- activate the Insights / Trends / Chat tabs in `TabNav` (replacing the M1 `StatusView` placeholders)
- `chat` is context-only: `ChatComposer` asks about the member; it does **not** draft client-facing replies
- consume token slots only (no hardcoded colour/space/type): --color-*, --space-*, --radius-*, --font-*
- contract acceptance:
  - [ ] renders every named region for insights/trends/chat in contract order
  - [ ] uses named components; no ad-hoc structural elements outside the contract
  - [ ] all visual values come from tokens (re-themes on token change; no hardcoded hues)
  - [ ] previously-disabled hub tabs are now active and routed

---

## 016 — LangFuse observability (traces: latency + tokens)
- id: 016
- milestone: 3
- depends_on: [007, 008]
- test_command: "pytest tests/test_observability.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Instrument retrieval + LLM calls with LangFuse traces (latency, token usage, prompt version) plus
structured request logging with correlation ids.

**Acceptance criteria**
- [ ] Each generation request emits a trace with latency + token counts + prompt version
- [ ] Retrieval steps traced as spans
- [ ] Structured logs carry a correlation id per request
- [ ] LangFuse client mockable/no-op in tests + CI

**Test plan**
- unit: `tests/test_observability.py` (trace emitted with expected fields via mock, correlation id propagation)

## 017 — Token/context budgeting + prompt efficiency
- id: 017
- milestone: 3
- depends_on: [007, 008]
- test_command: "pytest tests/test_token_budget.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Enforce a configurable context token budget in retrieval + generation; tighten prompt/output structure
to reduce tokens without losing grounding.

**Acceptance criteria**
- [ ] Context bundle never exceeds the configured token budget (truncates by rank)
- [ ] Prompt assembly measured for token count; regression guard in tests
- [ ] Structured (JSON) outputs used to minimize output tokens
- [ ] Token usage before/after documented

**Test plan**
- unit: `tests/test_token_budget.py` (budget enforced, truncation keeps highest-ranked, token count asserted)

## 018 — Evals dataset (retrieval quality + safety)
- id: 018
- milestone: 3
- depends_on: [005]
- test_command: "pytest tests/test_evals_dataset.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Author a small labeled eval dataset: retrieval-quality cases (query → expected context nodes) and
safety cases (member+injury → exercises that must never appear).

**Acceptance criteria**
- [ ] ≥10 retrieval-quality cases with expected-node labels
- [ ] ≥5 safety cases (injury → forbidden exercises)
- [ ] Dataset stored in-repo in a documented, versioned format
- [ ] Loader validates dataset integrity

**Test plan**
- unit: `tests/test_evals_dataset.py` (schema/integrity of dataset, loader)

## 019 — Evals harness + scoring
- id: 019
- milestone: 3
- depends_on: [007, 008, 018]
- test_command: "pytest tests/test_evals_runner.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Runner that executes retrieval + generation over the eval dataset and scores retrieval quality
(precision/recall vs expected nodes) and safety (0 forbidden exercises), emitting a report.

**Acceptance criteria**
- [ ] `python -m evals.run` produces retrieval-quality + safety scores + a report artifact
- [ ] Safety score fails if any forbidden exercise appears
- [ ] Scores are deterministic with mocked LLM/embeddings
- [ ] Report is human-readable (and machine-parseable for CI)

**Test plan**
- unit: `tests/test_evals_runner.py` (scoring math, safety-fail path, report shape)

## 020 — Performance verification (<5s p95)
- id: 020
- milestone: 3
- depends_on: [009, 017]
- test_command: "pytest tests/test_perf.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Measure end-to-end generation latency across the seed set and assert p95 < 5s (LLM stubbed to a fixed
latency so the harness measures our overhead, not the provider).

**Acceptance criteria**
- [ ] Latency harness reports p50/p95 for `/generate/workout`
- [ ] p95 (excluding provider latency) within budget
- [ ] Retrieval + assembly overhead reported separately
- [ ] Documented method + numbers

**Test plan**
- unit/integration: `tests/test_perf.py` (timed runs with stubbed LLM latency, p95 assertion)

---

## 021 — CI: ruff + mypy + pytest + eval smoke
- id: 021
- milestone: 4
- depends_on: [019]
- test_command: "pytest tests/test_ci_config.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
GitHub Actions workflow running lint, type-check, tests, and an eval smoke on push/PR, with a
service Neo4j for integration tests.

**Acceptance criteria**
- [ ] Workflow runs ruff + mypy + pytest + eval smoke on a clean checkout
- [ ] Neo4j service container available to integration tests
- [ ] Secrets injected via CI env (no live keys in repo); LLM mocked in CI
- [ ] Green on the current codebase

**Test plan**
- unit: `tests/test_ci_config.py` (workflow references expected steps) + observed green CI run

## 022 — Scale: batched ingest + 100K synthetic load
- id: 022
- milestone: 4
- depends_on: [005]
- test_command: "pytest tests/test_scale.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
Batched/idempotent bulk ingest + a synthetic generator to load ~100K nodes; validate indexes are
used and member-scoped retrieval stays within latency budget at that size. Document the 100M
extension path.

**Acceptance criteria**
- [ ] Synthetic generator loads ~100K nodes via batched ingest
- [ ] Retrieval latency for a member stays within budget at 100K (member-scoped, index-backed)
- [ ] `EXPLAIN`/query plan confirms index usage on hot paths
- [ ] Scaling-to-100M extension path documented

**Test plan**
- integration: `tests/test_scale.py` (scaled subset load, indexed lookup, latency check)

## 023 — Documentation & submission polish
- id: 023
- milestone: 4
- depends_on: [015, 019, 021, 022]
- test_command: "pytest tests/test_docs_links.py"
- full_suite_command: "ruff check . && mypy app && pytest"

**Description**
README (what/why, quickstart), setup/run guide (`docker-compose up` + seed), API docs pointer
(OpenAPI), architecture pointers (ARCHITECTURE.md/diagram), and commit-convention notes.

**Acceptance criteria**
- [ ] README lets a new reader boot + demo the system in <10 minutes
- [ ] Setup/run + seed instructions verified from a clean checkout
- [ ] API + architecture docs linked and consistent with the code
- [ ] Commit conventions documented

**Test plan**
- unit: `tests/test_docs_links.py` (referenced files/anchors exist) + manual clean-checkout run-through
