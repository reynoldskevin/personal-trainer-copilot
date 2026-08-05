"""One-shot seed entrypoint for a fresh deployment.

Loads the graph schema, the curated ontology/SNOMED subset, the seed members, and computes
embeddings + the native vector index — everything the app needs to answer requests against an
otherwise-empty Neo4j. Every step is idempotent (``MERGE``/``IF NOT EXISTS``/overwrite-in-place),
so re-running is safe.

Run after a deploy, e.g. ``railway run --service api python -m app.ingestion.seed``.
"""
from __future__ import annotations

from app.config import get_settings
from app.graph import schema
from app.graph.client import get_client
from app.ingestion import members, ontology
from app.llm import get_provider
from app.retrieval import embeddings


def main() -> None:
    """Bootstrap schema + ontology + members + embeddings into the configured Neo4j."""
    settings = get_settings()
    client = get_client()
    try:
        schema.bootstrap_schema(client)
        ontology.load_ontology(client)
        members.ingest_members(client)
        result = embeddings.embed_and_index(client, get_provider(settings))
        print(  # noqa: T201 — deployment console output
            f"seed complete: embedded {result.get('embedded', 0)} nodes "
            f"at {result.get('dimensions', 0)} dimensions"
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
