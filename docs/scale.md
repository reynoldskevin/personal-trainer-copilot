# Scale — batched ingest & the path to 100M nodes

This platform is a modular monolith over Neo4j. Scale work has two parts: **loading** a large
graph efficiently and **keeping member-scoped retrieval fast** as the graph grows. Both are
exercised by `app/ingestion/scale.py` and `tests/test_scale.py`.

## Synthetic load

`app.ingestion.scale` generates deterministic synthetic members that reuse the real ontology
injury/exercise ids, so every relationship `MATCH`es a shared ontology node instead of creating a
competing one — the same invariant the curated seed relies on.

```bash
# Load ~100K nodes (default) via batched, idempotent ingest:
python -m app.ingestion.scale --nodes 100000 --batch-size 500

# Or an exact member count:
python -m app.ingestion.scale --members 10000
```

- **Deterministic** — `synthetic_member(i)` is a pure function of `i`; re-running produces the
  same graph. Each member contributes `NODES_PER_MEMBER` new nodes (the Member plus its owned
  goals, workouts, biometrics, adherence, chats and transcripts).
- **Batched** — `bulk_ingest` chunks the load into `batch_size` writes, each a single parameterized
  `UNWIND` per entity type (`app.ingestion.members.ingest_members`). Chunking bounds transaction
  size and memory rather than issuing one write per node.
- **Idempotent** — every write is `MERGE` on a stable id, so re-loading the same members
  duplicates nothing. This makes loads restartable and safe to re-run after a partial failure.

## Staying fast at scale

Retrieval is **member-scoped**: every subgraph read starts from `(m:Member {id: $member_id})`.
That anchor resolves through the uniqueness constraint on `Member.id` (a backing index), so the hot
path is an **index seek**, not a full label scan — its cost is independent of how many members
exist. `scale.member_lookup_plan` runs `EXPLAIN` on that lookup and `scale.uses_index_seek` asserts
the plan contains an index seek (e.g. `NodeUniqueIndexSeek`); the test proves this holds after a
scaled load. `scale.measure_retrieval_latency` then times member-scoped retrieval and the test
asserts p95 stays under `SCALE_LATENCY_BUDGET_MS`.

Indexes that keep the hot paths sub-linear (from `app.graph.schema`):

- Uniqueness constraint on `id` for every node label → index seek for anchored lookups.
- Range index on `timestamp` for the time-varying labels (Workout, BiometricReading,
  AdherenceRecord, ChatMessage, Transcript) → ordered "recent N" reads without a sort of the whole
  history.
- Native vector index over `Embeddable.embedding` → approximate-nearest-neighbour semantic search
  instead of a linear scan of all vectors.

## Extension path to ~100M nodes

The current design already keeps per-member reads index-bound; reaching ~100M nodes (roughly
1000× the demo scale) is an operational scaling exercise, not a rewrite:

1. **Load throughput.** Replace the driver-side batched `UNWIND` with server-side batching —
   `CALL apoc.periodic.iterate` (or `LOAD CSV` with `USING PERIODIC COMMIT` from an exported
   dataset) — to commit in large chunks without holding one giant transaction. The synthetic
   generator already streams members in index order, so it can feed a producer/consumer loader
   with bounded memory. Drop-and-recreate the vector index once after bulk load rather than
   maintaining it write-by-write.
2. **Memory & storage.** Size the Neo4j page cache to hold the hot store files; put the store on
   NVMe. At 100M nodes the working set is dominated by the property store and the vector index —
   provision heap/page-cache from `neo4j-admin memrec` against the real store size.
3. **Read scale-out.** Member-scoped reads are independent, so they fan out linearly across a
   **causal cluster** of read replicas behind the routing driver; the primary takes writes. No
   query needs a global join, so replicas need no cross-shard coordination.
4. **Sharding by member.** The natural partition key is the member: a member's subgraph is
   self-contained and never joined to another member's private entities. Beyond a single cluster,
   route members across shards (Neo4j Fabric or app-level routing on `member_id`) with the shared
   ontology replicated read-only to each shard. Retrieval already never crosses members, so
   sharding requires no query changes — only routing.
5. **Vector index growth.** For very large embedding sets, tune the native HNSW index parameters
   (or offload ANN to a dedicated vector store) and keep the graph as the source of truth,
   re-embedding incrementally as text nodes change.

The invariant that makes all of this safe is the same one the retrieval service enforces today:
**reads are anchored at a single member and never traverse into another member's private data**, so
scaling is about placement and throughput, not correctness.
