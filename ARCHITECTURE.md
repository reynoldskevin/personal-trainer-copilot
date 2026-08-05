# Architecture — Knowledge Graph Coaching Platform

## Summary

This platform is an **AI-native GraphRAG system** that gives fitness coaches safer, more
personalized workout recommendations and coaching insights in real time. Its foundation is a
**single Neo4j knowledge graph** that unifies heterogeneous member data — profiles, workouts,
injuries, goals, adherence, biometrics, chat history, and session transcripts — and grounds it
in a curated clinical ontology (a **SNOMED CT** subset for musculoskeletal injuries and body
regions). Neo4j serves double duty: it stores the graph *and* the embedding vectors via its
**native vector index**, so a single system answers both "who/what is related" (graph traversal)
and "what is semantically similar" (vector search). This deliberately avoids a second vector
datastore and the sync/infra overhead the brief warns against.

The core engineering bet is **hybrid GraphRAG**: retrieval fuses (1) vector search over
text-bearing nodes (chats, transcripts, goals, exercise descriptions) with (2) graph traversal
of the member's subgraph and the injury→contraindication paths. That fused, member-scoped
context is passed to a **LangGraph** generation pipeline that calls an LLM through a thin
**`LLMProvider`** interface (OpenAI for MVP; AWS Bedrock AgentCore is a drop-in behind the same
seam). **Injury safety is enforced structurally, not just by prompting**: contraindicated
exercises are computed from `CONTRAINDICATED_FOR` graph edges and filtered *before* generation,
and a **guardrails** stage re-validates the model's output against the same graph so no unsafe
exercise can reach a coach.

Cross-cutting requirements are first-class, not bolted on: a typed **FastAPI** layer (Pydantic
in/out), **LangFuse** tracing on every retrieval and LLM call (latency + token usage), an
**evals** harness with a small labeled dataset for retrieval quality and safety, **Docker
Compose** for one-command local setup, and **GitHub Actions** CI running lint/type/test. The
design targets the brief's performance envelope (<5s responses, 100K → hundreds-of-millions
nodes) through member-scoped subgraph queries, top-k budgeting, indexing, and batched ingestion,
with clear extension points (managed/clustered Neo4j, streaming) for the upper scale range. A
simple **Next.js** dashboard demonstrates the end-to-end flow: pick a member → generate a
safe, personalized workout or insight → see the supporting context and safety flags.

## Goals & non-goals

- **Goals** (traced to the brief):
  - Ingest heterogeneous member context into a knowledge graph (Functional Reqs).
  - Model KG relationships grounded in a SNOMED CT subset for injury/safety reasoning (Business Context, Other Reqs).
  - Vector / semantic retrieval + graph traversal = GraphRAG (Functional Reqs, AI/ML Frameworks).
  - AI-generated, injury-aware, chat-personalized workout recommendations and insights (Functional Reqs).
  - Typed REST API for retrieval + generation; simple frontend dashboard (Functional Reqs).
  - <5s responses, scalable architecture, clean retrieval, token efficiency (Performance Benchmarks).
  - Evals, guardrails, observability, Docker, typed APIs, docs, meaningful git history (Code Quality).
- **Non-goals** (explicitly out of scope for the mainline build):
  - Full 350K-concept SNOMED CT ingest (curated subset instead → extension point).
  - AWS Bedrock as the primary LLM (OpenAI first → extension point behind `LLMProvider`).
  - A production, publicly-live AWS deployment gate (Dockerized local is the deliverable; AWS path documented).
  - Microservices, multi-tenant auth, or elaborate infra — the brief explicitly warns against over-engineering.
  - A polished consumer UI — the frontend is a functional coach dashboard, not a product surface.
  - AI-drafted client-facing replies — chat history is used as *context* only for MVP.
  - Instrumenting business impact KPIs (churn, ROI, engagement) — business outcomes, not build targets.

## Requirements coverage

| Requirement (from brief) | Type | How the architecture satisfies it |
|---|---|---|
| Member profile ingestion | MVP | Ingestion Service loads members + related entities into Neo4j (M1). |
| Knowledge graph relationships | MVP | Graph schema: Member/Workout/Exercise/Injury/Goal/Biometric/Chat/Transcript/SnomedConcept + typed edges (M1). |
| Vector search / semantic retrieval | MVP | Neo4j **native vector index** over text-bearing nodes; embeddings via provider (M1). |
| AI-generated workout recommendations | MVP | LangGraph generation pipeline + `LLMProvider` (OpenAI) producing structured plans (M1). |
| Injury-aware exercise filtering | MVP | `CONTRAINDICATED_FOR` edges → pre-generation filter + post-generation guardrail (M1). |
| Chat/context-aware personalization | MVP | Chats/transcripts embedded + traversed into the GraphRAG context bundle; **chat is context only** (no AI-drafted client replies) (M1). |
| Longitudinal / temporal member data | MVP | **First-class time modeling**: timestamped records + derived trends (adherence %, biometric slope); retrieval can window "last N weeks" (M1). |
| Adherence | MVP | First-class `AdherenceRecord` entity (planned vs. completed over time) feeding trends + insights (M1). |
| Coaching insights (distinct from workouts) | MVP | Dedicated `/generate/insight` → `InsightReport` (progress summary, adherence/risk flags, personalization notes) (M1). |
| Simple frontend dashboard | MVP | Next.js coach dashboard: member view, generate workout, insights, chat context, safety flags (M1). |
| API endpoints for retrieval + generation | MVP | Typed FastAPI: `/members`, `/retrieve` (explicit vector+graph search), `/generate/workout`, `/generate/insight`, `/chat` (M1). |
| Impact metrics (coach time, personalization, churn, ROI) | Business KPI | Business outcomes, not directly buildable; only **latency** is instrumented (LangFuse). Eval harness proxies personalization/retrieval quality. Others are out-of-scope-to-measure for MVP. |
| AI response time < 5s | Platform/Eng | Member-scoped subgraph queries, top-k budgeting, async I/O, caching; measured in evals (M3). |
| Scalable 100K → hundreds of Ms nodes | Platform/Eng | Indexed lookups, batched ingest, scoped traversals; extension to managed/clustered Neo4j (M3 + ext point). |
| Clean retrieval quality | Platform/Eng | Hybrid rank + eval harness with labeled set measuring retrieval precision (M2). |
| Prompt/token efficiency | Platform/Eng | Context budgeting, structured prompts, token accounting via LangFuse (M2). |
| Strong project structure | Eng | Layered package layout (ingestion/graph/retrieval/generation/api/frontend/evals) (M1). |
| Clear documentation | Eng/Submission | README, ARCHITECTURE.md, per-module docs, API schema (all milestones). |
| Evals | Eng/Submission | `evals/` harness + dataset, run in CI (M2). |
| Guardrails | Eng/Submission | Guardrails module: input validation + output safety re-check against graph (M2). |
| Readable code / typed APIs | Eng | Pydantic models, mypy, ruff; typed FastAPI contracts (all). |
| Dockerized local setup | Eng/Submission | `docker-compose` (Neo4j + API + frontend) one-command up (M1). |
| Git commits with meaningful history | Eng/Submission | Conventional commits, per-ticket branches via tdd-ticket-loop (all). |
| Basic observability/logging | Eng | LangFuse traces + structured logging on every request/LLM call (M2). |
| CI/CD familiarity | Eng | GitHub Actions: ruff + mypy + pytest + eval smoke (M3). |
| Python; LangChain/LangGraph; embeddings; GraphRAG; LangFuse | Platform | Core stack of the generation/retrieval services. |
| Neo4j / graph database | Platform | The single source-of-truth datastore. |
| React/Next.js; Docker; Git; AWS | Platform | Frontend; Compose; VCS; AWS as documented deploy target. |
| OpenAI API **and** AWS Bedrock AgentCore | Platform | OpenAI concrete impl now; Bedrock behind `LLMProvider` (ext point). |
| Avoid over-engineering / microservices / magic | Platform (constraint) | Single datastore, modular monolith, explained abstractions only. |

## Hard problems — how this design addresses each

### HP1 — Modeling a heterogeneous KG grounded in a clinical ontology
The graph schema treats each data source as first-class node types with typed edges, so
member context is *navigable*, not just stored. Injuries link to a **curated SNOMED CT subset**
(`Injury -[:MAPS_TO]-> SnomedConcept`, `SnomedConcept -[:AFFECTS]-> BodyRegion`), giving the
system clinical grounding for safety reasoning without the cost of a full SNOMED ingest. The
mapping table is documented and versioned; a full-SNOMED loader is a clean extension point.

### HP1b — Longitudinal / temporal member data
"Longitudinal member data" is modeled as **first-class time**, not flat snapshots. Time-varying
records (`BiometricReading`, `Workout`/`PERFORMED`, `AdherenceRecord`, `ChatMessage`) carry
timestamps, and the ingestion/retrieval layers compute lightweight **derived trends** — adherence
% over a window, biometric slope, workout progression. Retrieval supports a **time window**
("last N weeks") so the GraphRAG context reflects the member's trajectory, and insights can flag
"adherence dropping" or "load progressing safely." This directly powers the brief's engagement/
churn value without a separate time-series store.

### HP2 — GraphRAG that fuses semantic + structural retrieval
Retrieval is a two-signal fusion inside one datastore: a **vector search** (Neo4j native index)
finds semantically relevant text (chats, transcripts, goals), and a **graph traversal** expands
from the anchor member across their subgraph and injury→contraindication paths. Results are
merged and ranked into a single bounded context bundle. Because both live in Neo4j, a hybrid
query needs no cross-store join — reducing latency and infra.

### HP3 — Injury-aware exercise filtering (safety is structural)
Safety is enforced in the graph, not left to the prompt. Candidate exercises are filtered by
traversing `CONTRAINDICATED_FOR` from the member's active injuries/conditions *before* the LLM
sees them, so unsafe options are never offered. After generation, the **guardrails** stage
re-validates every prescribed exercise against the same edges and rejects/repairs any violation.
Two independent checks (pre-filter + post-validate) make an unsafe recommendation a defect, not a
probability.

### HP4 — Scaling from 100K to hundreds of millions of nodes
All hot-path queries are **member-scoped**: retrieval anchors on one member and traverses a
bounded neighborhood, so query cost tracks subgraph size, not total graph size. Ingestion is
batched/idempotent; lookups use indexes and the vector index. This makes 100K trivial and keeps
per-request cost flat as the global graph grows. The upper range (100Ms) attaches at documented
extension points: managed/clustered Neo4j (Aura), read replicas, and partitioning — no mainline
rework.

### HP5 — <5s responses with token efficiency
Latency budget is controlled by bounding what reaches the LLM: top-k vector hits + depth-limited
traversal + a **context token budget**. Structured prompts and structured (JSON) outputs cut
tokens both ways; LangFuse records per-call token + latency so regressions are visible. Async
FastAPI + optional response caching for repeat member/context keeps p95 under the 5s target,
verified in the eval harness.

### HP6 — Evals + guardrails as graded, first-class concerns
A dedicated `evals/` harness runs a small labeled dataset for **retrieval quality** (did we fetch
the right context?) and **generation safety** (did we ever prescribe a contraindicated exercise?),
producing scores in CI. Guardrails are a separate module with explicit input and output
validators. Both are wired into GitHub Actions so quality/safety can't silently regress.

## Components

Names below match `ARCHITECTURE_DIAGRAM.md`.

- **Ingestion Service** (`ingestion/`) — Responsibility: load member data (profiles, workouts,
  injuries, goals, adherence, biometrics, chats, transcripts) + the curated SNOMED subset +
  exercise/ontology seed into Neo4j; compute and store embeddings on text-bearing nodes. Inputs:
  seed JSON/CSV fixtures. Outputs: populated graph + vector index. Trust: internal, batch.
- **Knowledge Graph — Neo4j** (`graph/`) — Responsibility: single source of truth for entities,
  relationships, and embedding vectors (native vector index). Inputs: Cypher writes/reads.
  Outputs: subgraphs, vector hits. Trust: internal datastore.
- **Retrieval Service (GraphRAG)** (`retrieval/`) — Responsibility: hybrid retrieval — vector
  search + graph traversal + **temporal windowing** (last-N-weeks) + derived trends (adherence %,
  biometric slope) + safety-aware candidate filtering — fused into a ranked, token-bounded context
  bundle. Inputs: member id + query/intent + optional time window. Outputs: context bundle +
  contraindication set + trend summary. Trust: internal.
- **Generation Service (LangGraph)** (`generation/`) — Responsibility: orchestrate retrieve →
  assemble prompt → LLM call → guardrail → structured result. Two output types: **`WorkoutPlan`**
  (`/generate/workout`) and **`InsightReport`** (`/generate/insight` — progress summary, adherence/
  risk flags, personalization notes). Inputs: context bundle + request. Outputs: validated structured
  response. Trust: internal; calls external LLM.
- **Guardrails** (`generation/guardrails/`) — Responsibility: validate inputs (schema, injury
  presence) and outputs (no contraindicated exercise, schema-valid, disclaimers). Inputs: request
  + model output + contraindication set. Outputs: pass / repaired / rejected. Trust: safety-critical.
- **LLMProvider interface** (`llm/`) — Responsibility: abstract chat + embedding calls; OpenAI
  concrete impl for MVP. Inputs: prompts/text. Outputs: completions/embeddings. Trust: external boundary.
  *Mandate note:* this is the seam that satisfies "OpenAI **and** Bedrock" — Bedrock AgentCore plugs
  in here without touching callers.
- **API layer — FastAPI** (`api/`) — Responsibility: typed REST surface for retrieval + generation
  + member/chat. Inputs: HTTP + Pydantic models. Outputs: typed JSON. Trust: external boundary (coach client).
- **Frontend — Next.js** (`frontend/`) — Responsibility: coach dashboard (member list/detail,
  generate workout, chat, safety flags, supporting context). Inputs: API. Outputs: UI. Trust: client.
- **Observability — LangFuse + logging** (`observability/`) — Responsibility: trace retrieval +
  LLM calls (latency, tokens, prompt/version), structured request logs. Inputs: instrumentation
  hooks. Outputs: traces/metrics. Trust: internal.
- **Evals harness** (`evals/`) — Responsibility: run labeled retrieval + safety evals, score, gate
  CI. Inputs: eval dataset + running services. Outputs: scores/reports. Trust: internal/CI.

## Interfaces & data flow

- **Primary request (generate workout):** Frontend → `POST /generate/workout {member_id, goalHint?}`
  → API validates (Pydantic) → Retrieval builds context bundle (vector hits + member subgraph +
  contraindication set) → Generation assembles prompt, pre-filters contraindicated exercises, calls
  `LLMProvider.chat` (OpenAI) via LangGraph → Guardrails re-validate output against contraindication
  set → API returns typed `WorkoutPlan` (with supporting-context + safety-flag fields) → dashboard renders.
- **Retrieval-only (vector search REST API):** `POST /retrieve {member_id, query, window?}` →
  context bundle (vector hits + subgraph + trend summary), for inspection and as the KG/vector search surface.
- **Insights:** `POST /generate/insight {member_id, window?}` → `InsightReport` (progress, adherence/risk
  flags, personalization notes) via the same retrieval + guardrail path.
- **Chat (context only):** `POST /chat {member_id, message}` → grounded answer using the member's
  GraphRAG context. Chat history is *retrieval context*; the platform does **not** draft client-facing replies in MVP.
- **Ingestion (offline):** CLI/script → Ingestion Service → Neo4j (idempotent, timestamped upserts + embeddings).
- **Contract shapes:** all request/response bodies are Pydantic models (typed APIs requirement);
  the context bundle and `WorkoutPlan` are versioned schemas shared between generation and API.
- **State:** all persistent state lives in Neo4j (graph + vectors). No separate vector DB, no
  app-side session store for MVP; LangFuse holds traces.

## Cross-cutting concerns

- **Security / safety:** structural injury filtering + guardrail re-validation (HP3); input schema
  validation; medical-context disclaimers on outputs; secrets via env/`.env` (never committed).
- **Cost / scale:** member-scoped queries, top-k + token budgeting, batched ingest, indexes;
  extension points for managed/clustered Neo4j. Token cost tracked per call (LangFuse).
- **Observability:** every retrieval + LLM call traced (latency, tokens, prompt version) via
  LangFuse; structured request logging with correlation ids.
- **Testing / regression:** pytest unit + integration (against a test Neo4j), plus the evals harness
  for retrieval quality + safety; all gated in CI (ruff, mypy, pytest, eval smoke).
- **Reproducibility:** `docker-compose up` brings Neo4j + API + frontend + seed data; deterministic
  seed fixtures.
- **Maintainability / clarity (What We Value):** modular monolith, explained abstractions only, typed
  contracts, conventional commits.

## Extension points (for optional / future deliverables)

The brief lists no explicit "Optional" section, so these are **beyond-mainline enhancements** the
architecture deliberately leaves reachable without rework:

- **AWS Bedrock AgentCore** → add a `BedrockProvider` implementing `LLMProvider`; config selects it. No caller changes.
- **Full SNOMED CT ingest** → a `SnomedLoader` variant behind the same `MAPS_TO`/`AFFECTS` schema; curated subset is a strict subset.
- **Live AWS deployment** → containers already built; swap Compose Neo4j for Neo4j Aura, deploy API/frontend to ECS/Amplify; documented, not built.
- **Hundreds-of-millions scale** → managed/clustered Neo4j, read replicas, partitioning — hot-path queries are already member-scoped.
- **Streaming responses / real-time biometric ingestion** → generation pipeline and ingestion are async-ready; add a stream/event source without changing the graph schema.
- **Separate/managed vector store** → retrieval abstracts the vector call; a pgvector/OpenSearch impl could replace the Neo4j index if scale demands.

## Key tradeoffs & alternatives considered

- **Neo4j native vector index vs. a dedicated vector DB.** Chose one datastore to cut infra,
  simplify hybrid GraphRAG (no cross-store join), and honor "no unnecessary microservices." Rejected
  Neo4j + pgvector/OpenSearch for MVP; kept it as an extension point if vector scale outgrows Neo4j.
- **Neo4j vs. AWS Neptune.** Neptune is more AWS-native but hard to run locally, conflicting with the
  Dockerized-local requirement and adding complexity. Chose Neo4j (trivial Docker) with Aura as the AWS path.
- **OpenAI-first vs. Bedrock-first.** The brief names both; OpenAI has the cleanest LangChain path for a
  fast MVP. Abstracted behind `LLMProvider` so leading with OpenAI costs nothing later.
- **Structural safety filtering vs. prompt-only.** Prompt-only is cheaper but unsafe. Chose graph-enforced
  pre-filter + post-validate; the extra query cost is justified because injury safety is the core value prop.
- **Modular monolith vs. microservices.** Chose a single deployable with clean module boundaries — matches
  team size (solo), the anti-over-engineering constraint, and still splits cleanly later if needed.
- **Curated SNOMED subset vs. full ingest.** Full ingest risks the MVP timeline and scale envelope; the
  curated subset delivers real clinical grounding now and upgrades via one documented loader.
