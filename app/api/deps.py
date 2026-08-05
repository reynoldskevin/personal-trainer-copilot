"""Ticket 009 — FastAPI dependency callables.

Exposes the two dependencies the API routes depend on: a :class:`~app.graph.client.Neo4jClient`
and an :class:`~app.llm.provider.LLMProvider`. Routes reference *these exact* callables in
``Depends(...)`` so tests can swap real infrastructure for fakes via
``app.dependency_overrides``.

:func:`get_neo4j_client` is a generator dependency that yields a live client and closes it in a
``finally`` block, giving each request a properly torn-down connection in production while
letting tests override the whole lifecycle.
"""
from __future__ import annotations

from collections.abc import Iterator

from app.config import get_settings
from app.graph.client import Neo4jClient, get_client
from app.llm import get_provider
from app.llm.provider import LLMProvider


def get_neo4j_client() -> Iterator[Neo4jClient]:
    """Yield a live :class:`Neo4jClient`, closing it when the request finishes."""
    client = get_client()
    try:
        yield client
    finally:
        client.close()


def get_llm_provider() -> LLMProvider:
    """Return the configured :class:`LLMProvider` selected from application settings."""
    return get_provider(get_settings())
