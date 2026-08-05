"""Ticket 006 — embeddings + Neo4j native vector index.

Text-bearing nodes (chat messages, coaching transcripts, member goals and exercise
descriptions) are embedded via :meth:`LLMProvider.embed` and stored on a shared secondary
label so a single Neo4j *native* vector index can serve semantic similarity search across
all of them.

The public surface is intentionally small:

- :data:`TEXT_SOURCES` maps each text-bearing node label to the property holding its text.
- :data:`EMBEDDABLE_LABEL` is the shared secondary label carrying the ``embedding`` vector;
  :data:`VECTOR_INDEX_NAME` names the native vector index defined over it.
- :func:`create_vector_index` issues idempotent DDL for that index.
- :func:`embed_and_index` embeds every text-bearing node, tags it, stores the vector and
  builds/awaits the index — safe to re-run without duplicating nodes, vectors or indexes.
- :func:`embed_query` embeds a single query string.
- :func:`similarity_search` returns the top-k ranked nodes for a query vector.

Fixed label/property/index names come from the constants below (never user input), so
interpolating them into Cypher is safe — matching the DDL pattern in
:mod:`app.graph.schema`. Query *data* (ids, vectors, k) is always parameterized.
"""
from __future__ import annotations

from typing import Any

from app.graph.client import Neo4jClient
from app.llm.provider import LLMProvider

# Text-bearing node label -> the property whose text is embedded.
TEXT_SOURCES: dict[str, str] = {
    "ChatMessage": "text",
    "Transcript": "text",
    "Goal": "description",
    "Exercise": "description",
}

# Shared secondary label carrying the `embedding` vector, and the native index over it.
EMBEDDABLE_LABEL: str = "Embeddable"
VECTOR_INDEX_NAME: str = "embeddable_embedding_index"

# Seconds to wait for the vector index to come ONLINE before returning.
_AWAIT_INDEX_SECONDS: int = 60


def create_vector_index(
    client: Neo4jClient, dimensions: int, *, similarity: str = "cosine"
) -> None:
    """Idempotently create the native vector index over ``EMBEDDABLE_LABEL.embedding``.

    Uses ``CREATE VECTOR INDEX ... IF NOT EXISTS`` so a second call is a no-op. The index
    name and label are fixed constants (interpolated safely); ``dimensions`` and
    ``similarity`` configure the vector space.
    """
    client.execute_write(
        f"CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS "
        f"FOR (n:{EMBEDDABLE_LABEL}) ON (n.embedding) "
        "OPTIONS {indexConfig: {"
        "`vector.dimensions`: $dimensions, "
        "`vector.similarity_function`: $similarity"
        "}}",
        dimensions=dimensions,
        similarity=similarity,
    )


def embed_and_index(client: Neo4jClient, provider: LLMProvider) -> dict[str, Any]:
    """Embed every text-bearing node, store the vectors and build the vector index.

    For each label in :data:`TEXT_SOURCES` the nodes' text is read, batch-embedded via
    ``provider.embed`` in a single call, the index is created, then each vector is written
    onto its node (tagging it :data:`EMBEDDABLE_LABEL`) so the write indexes transactionally.
    Finally the index is awaited ONLINE.

    Idempotent: nodes are matched by their unique ``id`` and vectors overwritten in place, so
    re-running duplicates no nodes, keeps each stored vector stable and leaves exactly one
    named index. Returns per-label embedded counts plus the vector ``dimensions``.
    """
    # 1. Read all text-bearing nodes, per label, ordered by id for determinism.
    collected: list[tuple[str, str, str]] = []  # (label, node id, text)
    for label, prop in TEXT_SOURCES.items():
        rows = client.execute_read(
            f"MATCH (n:{label}) WHERE n.{prop} IS NOT NULL "
            f"RETURN n.id AS id, n.{prop} AS text ORDER BY n.id"
        )
        for row in rows:
            collected.append((label, row["id"], row["text"]))

    result: dict[str, Any] = {"dimensions": 0, "embedded": len(collected)}
    if not collected:
        return result

    # 2. Batch-embed every text in one provider call; derive dimensionality.
    vectors = provider.embed([text for _, _, text in collected])
    dimensions = len(vectors[0])
    result["dimensions"] = dimensions

    # 3. Create the index BEFORE writing vectors so updates index transactionally.
    create_vector_index(client, dimensions)

    # 4. Write each vector onto its node, tagging it with the shared label. The write is
    #    label-scoped (`row.label IN labels(n)`) so an unrelated node that happens to share
    #    an id — `id` uniqueness is enforced only per-label — is never mis-tagged.
    write_rows = [
        {"label": label, "id": node_id, "vec": vec}
        for (label, node_id, _), vec in zip(collected, vectors, strict=True)
    ]
    client.execute_write(
        "UNWIND $rows AS row "
        "MATCH (n {id: row.id}) WHERE row.label IN labels(n) "
        f"SET n:{EMBEDDABLE_LABEL} "
        "SET n.embedding = row.vec",
        rows=write_rows,
    )

    # 5. Wait for the index to come ONLINE before returning.
    client.execute_read("CALL db.awaitIndexes($seconds)", seconds=_AWAIT_INDEX_SECONDS)

    return result


def embed_query(provider: LLMProvider, text: str) -> list[float]:
    """Embed a single query string, returning its embedding vector."""
    return provider.embed([text])[0]


def similarity_search(
    client: Neo4jClient, query_vector: list[float], k: int = 5
) -> list[dict[str, Any]]:
    """Return the top-``k`` nodes most similar to ``query_vector``, ranked by score desc.

    Queries the native vector index via ``db.index.vector.queryNodes``. Each hit is a dict
    ``{id, labels, score, text}`` where ``text`` falls back across the possible text-bearing
    properties. ``k`` and the query vector are parameters; the index name is a fixed constant.
    """
    return client.execute_read(
        "CALL db.index.vector.queryNodes($name, $k, $vec) YIELD node, score "
        "RETURN node.id AS id, labels(node) AS labels, score, "
        "coalesce(node.text, node.description, node.name) AS text "
        "ORDER BY score DESC",
        name=VECTOR_INDEX_NAME,
        k=k,
        vec=query_vector,
    )
