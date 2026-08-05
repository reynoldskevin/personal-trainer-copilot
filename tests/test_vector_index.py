"""Ticket 006 — embeddings + Neo4j native vector index.

Contract (module `app.retrieval.embeddings`):
- `TEXT_SOURCES` — mapping of text-bearing node label -> the text property to embed
  (ChatMessage, Transcript, Goal, Exercise).
- `EMBEDDABLE_LABEL` / `VECTOR_INDEX_NAME` — the shared secondary label carrying the
  `embedding` vector and the name of the native vector index over it.
- `create_vector_index(client, dimensions, *, similarity="cosine")` — idempotent DDL.
- `embed_and_index(client, provider) -> dict` — embed every text-bearing node via
  `LLMProvider.embed`, tag it `EMBEDDABLE_LABEL`, store the vector, build/await the index.
  Idempotent: re-running does not duplicate nodes, vectors, or indexes.
- `embed_query(provider, text) -> list[float]` — embed a single query string.
- `similarity_search(client, query_vector, k=5) -> list[dict]` — top-k ranked nodes,
  each `{id, labels, score, text}`, ordered by score descending.

Pure-data tests always run. Integration tests need the local Neo4j (a 5.x that supports
native vector indexes) and skip cleanly if it is down.
"""
import os

import pytest

from app.graph import schema
from app.graph.client import Neo4jClient
from app.ingestion import members, ontology
from app.llm.provider import LLMProvider
from app.retrieval import embeddings

# --- deterministic, mockable embedding provider -------------------------------------
# A tiny bag-of-words embedder over a fixed vocabulary. Cosine similarity then tracks
# word overlap, so nearest-neighbour results are predictable without any live API. A
# trailing constant 1.0 dimension guarantees no vector is all-zero (cosine stays defined).
_VOCAB = [
    "shoulder", "overhead", "press", "pain", "rehab", "deadlift", "squat", "strong",
    "core", "back", "hip", "stability", "brace", "tight",
]


def _embed_text(text: str) -> list[float]:
    low = text.lower()
    return [float(low.count(word)) for word in _VOCAB] + [1.0]


class FakeEmbedProvider(LLMProvider):
    """Deterministic embedder: identical text always yields an identical vector."""

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:  # pragma: no cover
        return ""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_embed_text(t) for t in texts]


# ----------------------- pure-data (no Neo4j) -----------------------

def test_text_sources_cover_the_four_text_bearing_labels():
    assert set(embeddings.TEXT_SOURCES) == {"ChatMessage", "Transcript", "Goal", "Exercise"}
    # Each maps to the actual text-bearing property on that node.
    assert embeddings.TEXT_SOURCES["ChatMessage"] == "text"
    assert embeddings.TEXT_SOURCES["Transcript"] == "text"
    assert embeddings.TEXT_SOURCES["Goal"] == "description"
    assert embeddings.TEXT_SOURCES["Exercise"] == "description"


def test_index_and_label_names_are_stable_strings():
    assert isinstance(embeddings.VECTOR_INDEX_NAME, str) and embeddings.VECTOR_INDEX_NAME
    assert isinstance(embeddings.EMBEDDABLE_LABEL, str) and embeddings.EMBEDDABLE_LABEL


def test_embed_query_returns_single_vector():
    vec = embeddings.embed_query(FakeEmbedProvider(), "shoulder press")
    assert isinstance(vec, list)
    assert len(vec) == len(_VOCAB) + 1
    assert all(isinstance(x, float) for x in vec)


def test_fake_provider_is_deterministic():
    p = FakeEmbedProvider()
    assert p.embed(["shoulder press"]) == p.embed(["shoulder press"])


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
    yield c
    c.close()


def test_embed_and_index_tags_every_text_bearing_node(client):
    embeddings.embed_and_index(client, FakeEmbedProvider())
    # Every text-bearing node carries the shared label + a stored embedding vector.
    for label, prop in embeddings.TEXT_SOURCES.items():
        rows = client.execute_read(
            f"MATCH (n:{label}) WHERE n.{prop} IS NOT NULL "
            f"RETURN count(n) AS total, "
            f"count(CASE WHEN n:{embeddings.EMBEDDABLE_LABEL} AND n.embedding IS NOT NULL "
            f"THEN 1 END) AS embedded"
        )
        r = rows[0]
        assert r["total"] > 0, f"no {label} nodes to embed"
        assert r["embedded"] == r["total"], f"not all {label} nodes embedded"


def test_native_vector_index_exists(client):
    embeddings.embed_and_index(client, FakeEmbedProvider())
    rows = client.execute_read(
        "SHOW INDEXES YIELD name, type WHERE name = $name RETURN type",
        name=embeddings.VECTOR_INDEX_NAME,
    )
    assert rows, "expected the named vector index to exist"
    assert rows[0]["type"] == "VECTOR"


def test_similarity_search_returns_ranked_scored_nodes(client):
    embeddings.embed_and_index(client, FakeEmbedProvider())
    qvec = embeddings.embed_query(FakeEmbedProvider(), "rehab shoulder press pain")
    results = embeddings.similarity_search(client, qvec, k=5)
    assert 1 <= len(results) <= 5
    for hit in results:
        assert {"id", "labels", "score"} <= set(hit)
    scores = [h["score"] for h in results]
    assert scores == sorted(scores, reverse=True), "results must be ranked by score desc"


def test_semantic_query_returns_expected_shoulder_node(client):
    embeddings.embed_and_index(client, FakeEmbedProvider())
    # Ava's shoulder-rehab goal is the strongest match for this query's vocabulary.
    qvec = embeddings.embed_query(FakeEmbedProvider(), "rehab shoulder press pain")
    results = embeddings.similarity_search(client, qvec, k=5)
    assert results[0]["id"] == "goal_ava_shoulder"


def test_embed_and_index_is_idempotent(client):
    embeddings.embed_and_index(client, FakeEmbedProvider())
    n1 = client.execute_read(
        f"MATCH (n:{embeddings.EMBEDDABLE_LABEL}) RETURN count(n) AS c"
    )[0]["c"]
    before = client.execute_read(
        "MATCH (g:Goal {id: 'goal_ava_shoulder'}) RETURN g.embedding AS e"
    )[0]["e"]

    embeddings.embed_and_index(client, FakeEmbedProvider())
    n2 = client.execute_read(
        f"MATCH (n:{embeddings.EMBEDDABLE_LABEL}) RETURN count(n) AS c"
    )[0]["c"]
    after = client.execute_read(
        "MATCH (g:Goal {id: 'goal_ava_shoulder'}) RETURN g.embedding AS e"
    )[0]["e"]
    idx = client.execute_read(
        "SHOW INDEXES YIELD name WHERE name = $name RETURN count(*) AS c",
        name=embeddings.VECTOR_INDEX_NAME,
    )[0]["c"]

    assert n1 == n2, "re-embedding must not duplicate embeddable nodes"
    assert before == after, "re-embedding must be stable (same vector)"
    assert idx == 1, "exactly one named vector index"
