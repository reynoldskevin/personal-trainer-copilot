"""Ticket 022 — Scale: batched ingest + synthetic 100K load.

Contract (`app.ingestion.scale`):
- `synthetic_member(index) -> members.Member` — deterministic; reuses REAL ontology injury/
  exercise ids so its links resolve against the loaded ontology. Same index -> identical member;
  different indices -> distinct ids.
- `generate_members(count, *, start=0) -> list[Member]` — `count` unique members.
- `NODES_PER_MEMBER` — how many NEW graph nodes each synthetic member contributes (shared
  ontology Injury/Exercise nodes are not counted). `members_for_node_target(n) -> int` inverts it
  (ceil) so a caller can size a ~100K-node load.
- `batched(items, size) -> Iterator[list]` — contiguous chunks, last one may be short, nothing lost.
- `bulk_ingest(client, members, *, batch_size) -> dict` — idempotent, chunked bulk load; the
  returned dict reports `members` and `batches` and re-running never duplicates.
- `member_lookup_plan(client, member_id) -> dict` — the `EXPLAIN` plan root for the hot
  member-scoped lookup; `plan_operators(plan) -> list[str]` flattens it and `uses_index_seek(plan)`
  is True iff some operator is an index seek (not a label scan).
- `measure_retrieval_latency(client, provider, member_id, query, *, iterations) -> LatencyStats`
  and `SCALE_LATENCY_BUDGET_MS` — member-scoped retrieval must stay under budget at scale.

Pure tests always run. The scaled-load / plan / latency tests need Neo4j and skip if it is down.
"""
import json
import os

import pytest

from app.ingestion import ontology, scale
from app.observability import perf

# --------------------------------------------------------------------------- synthetic generator

def test_synthetic_member_is_deterministic():
    a = scale.synthetic_member(7)
    b = scale.synthetic_member(7)
    assert a == b
    assert scale.synthetic_member(8)["id"] != a["id"]


def test_synthetic_member_reuses_real_ontology_ids():
    known_injuries = {i["id"] for i in ontology.INJURIES}
    known_exercises = {e["id"] for e in ontology.EXERCISES}
    # Sample across indices so every rotation branch is covered.
    for i in range(0, 40):
        m = scale.synthetic_member(i)
        assert m["id"].startswith("syn_member_")
        assert m["name"], "member needs a name"
        for inj in m["injuries"]:
            assert inj in known_injuries, f"{m['id']} references unknown injury {inj}"
        for w in m["workouts"]:
            for ex in w["exercises"]:
                assert ex in known_exercises, f"{m['id']} references unknown exercise {ex}"


def test_generate_members_are_unique_and_counted():
    gen = scale.generate_members(50)
    assert len(gen) == 50
    ids = [m["id"] for m in gen]
    assert len(set(ids)) == 50, "member ids must be unique"
    # `start` offsets the id space so successive batches don't collide.
    more = scale.generate_members(50, start=50)
    assert not (set(ids) & {m["id"] for m in more})


def test_nodes_per_member_matches_a_generated_member():
    m = scale.synthetic_member(0)
    # Every new node this member contributes: the member + its owned entities (ontology
    # Injury/Exercise nodes are shared, not created here).
    actual = (
        1
        + len(m["goals"])
        + len(m["workouts"])
        + len(m["biometrics"])
        + len(m["adherence"])
        + len(m["chats"])
        + len(m["transcripts"])
    )
    assert scale.NODES_PER_MEMBER == actual


def test_members_for_node_target_sizes_a_100k_load():
    n = scale.members_for_node_target(100_000)
    # Enough members to reach ~100K nodes (ceil), and not absurdly more than needed.
    assert n * scale.NODES_PER_MEMBER >= 100_000
    assert (n - 1) * scale.NODES_PER_MEMBER < 100_000


# --------------------------------------------------------------------------- batching (pure)

def test_batched_splits_without_loss():
    items = list(range(23))
    chunks = list(scale.batched(items, 10))
    assert [len(c) for c in chunks] == [10, 10, 3]
    assert [x for c in chunks for x in c] == items


def test_batched_exact_multiple_and_empty():
    assert [len(c) for c in scale.batched(list(range(20)), 10)] == [10, 10]
    assert list(scale.batched([], 5)) == []


# --------------------------------------------------------------------------- plan inspection (pure)

_INDEX_PLAN = {
    "operatorType": "ProduceResults",
    "children": [
        {
            "operatorType": "Expand(All)",
            "children": [{"operatorType": "NodeUniqueIndexSeek", "children": []}],
        }
    ],
}
_SCAN_PLAN = {
    "operatorType": "ProduceResults",
    "children": [
        {
            "operatorType": "Filter",
            "children": [{"operatorType": "NodeByLabelScan", "children": []}],
        }
    ],
}


def test_plan_operators_flattens_the_tree():
    ops = scale.plan_operators(_INDEX_PLAN)
    assert "NodeUniqueIndexSeek" in ops
    assert "ProduceResults" in ops
    assert len(ops) == 3


def test_uses_index_seek_distinguishes_seek_from_scan():
    assert scale.uses_index_seek(_INDEX_PLAN) is True
    assert scale.uses_index_seek(_SCAN_PLAN) is False


def test_main_is_callable():
    assert callable(scale.main)


# --------------------------------------------------------------------------- integration (Neo4j)

_VOCAB = [
    "shoulder", "overhead", "press", "pain", "rehab", "deadlift", "squat", "strong",
    "core", "back", "hip", "stability", "brace", "tight",
]

# Kept modest so the suite stays fast; large enough that a label scan would be measurably
# worse than the index seek the retrieval path relies on.
_SUBSET_MEMBERS = 150


class _FakeProvider:
    """Deterministic 15-dim embeddings (14-word vocab + bias) matching the seed index."""

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        return json.dumps({"summary": "s", "exercises": []})

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(t.lower().count(w)) for w in _VOCAB] + [1.0] for t in texts]


@pytest.fixture
def client():
    from app.graph import schema
    from app.graph.client import Neo4jClient

    c = Neo4jClient(
        uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        user=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "testpassword"),
    )
    try:
        c.execute_read("RETURN 1 AS ok")
    except Exception:  # noqa: BLE001
        c.close()
        pytest.skip("Neo4j not available")
    schema.bootstrap_schema(c)
    ontology.load_ontology(c)  # synthetic members reference ontology injuries/exercises
    yield c
    c.close()


def _count(client, cypher: str) -> int:
    return client.execute_read(cypher)[0]["c"]


def _member_count(client) -> int:
    return _count(client, "MATCH (m:Member) RETURN count(m) AS c")


# Node + relationship counts a duplication bug would inflate — members, a child entity, and a
# member->child relationship — so idempotency is checked across the whole write, not just members.
_IDEMPOTENCY_COUNTS = {
    "members": "MATCH (m:Member) RETURN count(m) AS c",
    "workouts": "MATCH (w:Workout) RETURN count(w) AS c",
    "performed": "MATCH (:Member)-[r:PERFORMED]->(:Workout) RETURN count(r) AS c",
}


def test_bulk_ingest_is_batched_and_idempotent(client):
    gen = scale.generate_members(_SUBSET_MEMBERS)
    report = scale.bulk_ingest(client, gen, batch_size=40)
    assert report["members"] == _SUBSET_MEMBERS
    assert report["batches"] >= 2, "load must be chunked into multiple batches"

    after_first = {k: _count(client, q) for k, q in _IDEMPOTENCY_COUNTS.items()}
    assert after_first["members"] >= _SUBSET_MEMBERS
    assert after_first["workouts"] >= _SUBSET_MEMBERS * scale._WORKOUTS_PER_MEMBER
    assert after_first["performed"] >= _SUBSET_MEMBERS * scale._WORKOUTS_PER_MEMBER

    # Re-running the same load duplicates no nodes OR relationships (MERGE on stable ids).
    scale.bulk_ingest(client, gen, batch_size=40)
    after_second = {k: _count(client, q) for k, q in _IDEMPOTENCY_COUNTS.items()}
    assert after_second == after_first


def test_member_lookup_uses_an_index_seek(client):
    scale.bulk_ingest(client, scale.generate_members(_SUBSET_MEMBERS), batch_size=50)
    mid = scale.synthetic_member(0)["id"]
    plan = scale.member_lookup_plan(client, mid)
    assert scale.uses_index_seek(plan), (
        f"member lookup must be index-backed, plan was: {scale.plan_operators(plan)}"
    )


def test_member_scoped_retrieval_stays_within_budget_at_scale(client):
    from app.retrieval import embeddings

    scale.bulk_ingest(client, scale.generate_members(_SUBSET_MEMBERS), batch_size=50)
    embeddings.embed_and_index(client, _FakeProvider())

    mid = scale.synthetic_member(0)["id"]
    stats = scale.measure_retrieval_latency(
        client, _FakeProvider(), mid, "shoulder rehab", iterations=5
    )
    assert isinstance(stats, perf.LatencyStats)
    assert stats.count == 5
    assert stats.p95_ms >= stats.p50_ms >= 0.0
    assert stats.p95_ms < scale.SCALE_LATENCY_BUDGET_MS


def test_retrieval_at_scale_stays_member_scoped(client):
    from app.retrieval import service

    scale.bulk_ingest(client, scale.generate_members(_SUBSET_MEMBERS), batch_size=50)
    embeddings_mod = __import__("app.retrieval.embeddings", fromlist=["embed_and_index"])
    embeddings_mod.embed_and_index(client, _FakeProvider())

    mid = scale.synthetic_member(3)["id"]
    bundle = service.retrieve(client, _FakeProvider(), mid, "training")
    # Subgraph facts are rooted at this member — no other synthetic member's name leaks in.
    other_names = {scale.synthetic_member(i)["name"] for i in range(_SUBSET_MEMBERS)}
    other_names.discard(scale.synthetic_member(3)["name"])
    joined = " ".join(bundle.subgraph_facts)
    assert scale.synthetic_member(3)["name"] in joined
    leaked = [n for n in other_names if n in joined]
    assert not leaked, f"cross-member leakage at scale: {leaked[:3]}"
