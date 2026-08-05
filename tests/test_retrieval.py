"""Ticket 007 — Retrieval Service: hybrid GraphRAG.

Contract (module `app.retrieval.service`):
- `estimate_tokens(text) -> int` — deterministic token estimate for budgeting.
- `VectorHit` / `ContextBundle` — Pydantic models. `ContextBundle` carries `member_id`,
  `query`, `vector_hits`, `subgraph_facts`, `context_items` (the token-bounded fused
  context actually used for a prompt), `contraindications`, `token_estimate`, `token_budget`.
- `retrieve(client, provider, member_id, query, *, token_budget=..., k=...) -> ContextBundle`
  fuses global vector search with a MEMBER-SCOPED subgraph traversal and the member's
  contraindication set (union of exercises unsafe for the member's active injuries), with the
  fused context bounded to `token_budget`.

Pure-data tests always run. Integration tests need the local Neo4j and skip if it is down.
"""
import os

import pytest

from app.graph import schema
from app.graph.client import Neo4jClient
from app.ingestion import members, ontology
from app.llm.provider import LLMProvider
from app.retrieval import service

# Deterministic bag-of-words embedder (same scheme as the vector-index tests) so retrieval
# runs with no live API and predictable vectors.
_VOCAB = [
    "shoulder", "overhead", "press", "pain", "rehab", "deadlift", "squat", "strong",
    "core", "back", "hip", "stability", "brace", "tight",
]


def _embed_text(text: str) -> list[float]:
    low = text.lower()
    return [float(low.count(word)) for word in _VOCAB] + [1.0]


class FakeEmbedProvider(LLMProvider):
    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:  # pragma: no cover
        return ""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_embed_text(t) for t in texts]


# ----------------------- pure-data (no Neo4j) -----------------------

def test_estimate_tokens_is_positive_and_grows_with_length():
    assert service.estimate_tokens("") >= 0
    short = service.estimate_tokens("a short sentence")
    long = service.estimate_tokens("a much longer sentence with a good deal more content in it")
    assert long > short


def test_context_bundle_is_a_pydantic_model():
    bundle = service.ContextBundle(
        member_id="m",
        query="q",
        vector_hits=[],
        subgraph_facts=[],
        context_items=[],
        contraindications=[],
        token_estimate=0,
        token_budget=100,
    )
    dumped = bundle.model_dump()
    assert dumped["member_id"] == "m"
    assert dumped["token_budget"] == 100


# ----------------------- integration (needs Neo4j) -----------------------

@pytest.fixture
def client():
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
    ontology.load_ontology(c)
    members.ingest_members(c)
    from app.retrieval import embeddings
    embeddings.embed_and_index(c, FakeEmbedProvider())
    yield c
    c.close()


def test_retrieve_returns_a_populated_bundle(client):
    bundle = client_retrieve(client, "member_ava", "shoulder rehab plan")
    assert isinstance(bundle, service.ContextBundle)
    assert bundle.member_id == "member_ava"
    assert bundle.subgraph_facts, "expected member subgraph facts"
    assert bundle.vector_hits, "expected vector hits"
    for hit in bundle.vector_hits:
        assert isinstance(hit, service.VectorHit)


def test_contraindication_set_matches_member_active_injuries(client):
    # Ava has a rotator cuff tear -> overhead_press + bench_press are unsafe.
    ava = client_retrieve(client, "member_ava", "upper body workout")
    assert ava.contraindications == sorted(["bench_press", "overhead_press"])
    # Ben has no active injury -> empty contraindication set.
    ben = client_retrieve(client, "member_ben", "upper body workout")
    assert ben.contraindications == []


def test_traversal_is_member_scoped(client):
    # Ava's facts must describe Ava, never another member's private entities.
    ava = client_retrieve(client, "member_ava", "progress review")
    blob = "\n".join(ava.subgraph_facts).lower()
    assert "rotator cuff" in blob, "expected Ava's own injury in her facts"
    # Ben's and Chloe's goals must not leak into Ava's member-scoped subgraph.
    assert "deadlift 180" not in blob, "Ben's goal leaked into Ava's facts"
    assert "hip hinge" not in blob, "Chloe's goal leaked into Ava's facts"


def test_context_is_token_bounded(client):
    small = client_retrieve(client, "member_ava", "shoulder rehab plan", token_budget=20)
    large = client_retrieve(client, "member_ava", "shoulder rehab plan", token_budget=5000)
    # The fused context never exceeds the budget...
    assert small.token_estimate <= small.token_budget
    assert large.token_estimate <= large.token_budget
    # ...and a tighter budget includes no more context than a generous one.
    assert len(small.context_items) <= len(large.context_items)
    assert len(small.context_items) < len(large.context_items) or len(large.context_items) == 0


def client_retrieve(client, member_id, query, **kwargs):
    return service.retrieve(client, FakeEmbedProvider(), member_id, query, **kwargs)
