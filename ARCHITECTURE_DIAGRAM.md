# Architecture Diagram — Knowledge Graph Coaching Platform

## Component / interaction diagram

```mermaid
flowchart TD
  subgraph Client
    FE[Frontend - Next.js<br/>Coach Dashboard]
  end

  subgraph Backend[Modular Monolith - Python]
    API[API layer - FastAPI<br/>typed Pydantic contracts]
    RET[Retrieval Service<br/>GraphRAG hybrid]
    GEN[Generation Service<br/>LangGraph pipeline]
    GUARD[Guardrails<br/>input + output safety]
    LLM[LLMProvider interface<br/>OpenAI impl]
    ING[Ingestion Service<br/>batch loaders + embeddings]
    OBS[Observability<br/>LangFuse + logging]
    EVAL[Evals harness]
  end

  subgraph Data
    NEO[(Neo4j<br/>Knowledge Graph<br/>+ native vector index)]
  end

  subgraph External
    OAI[[OpenAI API<br/>chat + embeddings]]
    BR[[AWS Bedrock AgentCore<br/>extension point]]
  end

  FE -->|HTTP JSON| API
  API --> RET
  API --> GEN
  GEN --> RET
  GEN --> GUARD
  GEN --> LLM
  RET --> NEO
  GUARD --> NEO
  ING --> NEO
  ING --> LLM
  LLM --> OAI
  LLM -.->|swap-in| BR
  RET -.instrument.-> OBS
  GEN -.instrument.-> OBS
  EVAL --> API
  EVAL --> RET
```

## Data flow — generate a safe workout

```mermaid
flowchart LR
  A[Coach picks member<br/>+ goal hint] --> B[API validates<br/>Pydantic]
  B --> C[Retrieval:<br/>vector search + graph traversal]
  C --> D[Context bundle<br/>+ contraindication set]
  D --> E[Generation: pre-filter<br/>contraindicated exercises]
  E --> F[LLM via LLMProvider<br/>OpenAI]
  F --> G[Guardrails:<br/>re-validate vs graph]
  G -->|pass / repaired| H[Typed WorkoutPlan<br/>+ safety flags]
  G -.reject/repair.-> E
  H --> I[Dashboard renders<br/>plan + supporting context]
```

## Knowledge graph schema (core entities & relationships)

```mermaid
flowchart TD
  M((Member)) -->|HAS_INJURY| INJ((Injury))
  M -->|HAS_GOAL| GOAL((Goal))
  M -->|PERFORMED @ts| WO((Workout))
  M -->|MEASURED @ts| BIO((BiometricReading))
  M -->|HAS_ADHERENCE @ts| ADH((AdherenceRecord<br/>planned vs completed))
  M -->|SENT @ts| CHAT((ChatMessage))
  M -->|IN_SESSION @ts| TR((Transcript))
  WO -->|INCLUDES| EX((Exercise))
  EX -->|TARGETS| MG((MuscleGroup))
  EX -->|REQUIRES| EQ((Equipment))
  EX -->|CONTRAINDICATED_FOR| INJ
  INJ -->|MAPS_TO| SN((SnomedConcept))
  SN -->|AFFECTS| BR2((BodyRegion))
  MG -->|IN_REGION| BR2
  %% @ts = timestamped for longitudinal/temporal reasoning (trends, last-N-weeks windows)
  %% Vector index lives on text-bearing nodes: ChatMessage, Transcript, Goal, Exercise
```

## Safety enforcement (trust boundary)

```mermaid
flowchart TD
  subgraph Untrusted[LLM output - untrusted]
    OUT[Proposed exercises]
  end
  subgraph Trusted[Graph-enforced safety]
    PRE[Pre-filter:<br/>traverse CONTRAINDICATED_FOR<br/>before LLM sees candidates]
    POST[Post-validate:<br/>re-check every prescribed exercise]
  end
  PRE --> LLMCALL[LLM generation]
  LLMCALL --> OUT
  OUT --> POST
  POST -->|clean| SAFE[Delivered to coach]
  POST -->|violation| REPAIR[Reject / repair loop]
  REPAIR --> LLMCALL
```
