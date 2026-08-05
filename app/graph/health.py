"""Neo4j connectivity probe used by the /health endpoint.

The probe reads the target URI from the environment at call time so it reflects the
*current* configuration on every request. It opens a short-timeout driver, runs a trivial
query, and never raises — any failure (unreachable host, auth error, timeout) yields
``False``.
"""
from __future__ import annotations

import os

from neo4j import GraphDatabase

# Keep connection attempts short so an unreachable Neo4j fails fast.
_CONNECTION_TIMEOUT_SECONDS = 2.0


def check_neo4j() -> bool:
    """Return True if the configured Neo4j is reachable, False otherwise (never raises)."""
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "neo4j")

    try:
        driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
            connection_timeout=_CONNECTION_TIMEOUT_SECONDS,
            connection_acquisition_timeout=_CONNECTION_TIMEOUT_SECONDS,
        )
        try:
            with driver.session() as session:
                session.run("RETURN 1").single()
            return True
        finally:
            driver.close()
    except Exception:
        return False
