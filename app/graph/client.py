"""Typed Neo4j connection layer.

`Neo4jClient` wraps a neo4j driver with two thin helpers — `execute_read` and
`execute_write` — that run *parameterized* Cypher and return each record as a plain
``dict``. Query DATA is always passed as parameters (never string-interpolated), which
keeps the layer injection-safe.
"""
from __future__ import annotations

from typing import Any

from neo4j import GraphDatabase, ManagedTransaction, Record

from app.config import get_settings


def _records_to_dicts(records: list[Record]) -> list[dict[str, Any]]:
    """Convert neo4j records into plain dicts keyed by return name."""
    return [dict(record) for record in records]


class Neo4jClient:
    """Small wrapper around the neo4j driver with parameterized read/write helpers."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def execute_read(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        """Run a read query with parameters and return records as dicts."""
        def _run(tx: ManagedTransaction) -> list[dict[str, Any]]:
            result = tx.run(cypher, **params)
            return _records_to_dicts(list(result))

        with self._driver.session() as session:
            return session.execute_read(_run)

    def execute_write(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        """Run a write query with parameters and return records as dicts."""
        def _run(tx: ManagedTransaction) -> list[dict[str, Any]]:
            result = tx.run(cypher, **params)
            return _records_to_dicts(list(result))

        with self._driver.session() as session:
            return session.execute_write(_run)

    def close(self) -> None:
        """Close the underlying driver and release its connections."""
        self._driver.close()


def get_client() -> Neo4jClient:
    """Construct a `Neo4jClient` from application settings."""
    settings = get_settings()
    return Neo4jClient(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
