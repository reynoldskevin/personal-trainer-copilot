"""Ticket 002 — graph schema + typed Neo4j connection layer.

Contract:
- `app.graph.client.Neo4jClient` wraps the driver with parameterized read/write helpers
  (`execute_read`/`execute_write(cypher, **params)` returning list[dict]) and `close()`.
- `app.graph.schema.bootstrap_schema(client)` creates constraints + indexes IDEMPOTENTLY
  (safe to run twice, no duplicate-constraint error).
- Time-varying nodes persist and read back a `timestamp`.

Integration tests: require the local Neo4j from docker-compose. They SKIP cleanly if it is
unreachable, so the suite still runs in a DB-less environment.
"""
import os

import pytest

from app.graph import schema
from app.graph.client import Neo4jClient

CLEANUP_IDS = ["t002-m1", "t002-b1"]


@pytest.fixture
def client():
    c = Neo4jClient(
        uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        user=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "testpassword"),
    )
    try:
        c.execute_read("RETURN 1 AS ok")
    except Exception:  # noqa: BLE001 - any connectivity failure means skip
        c.close()
        pytest.skip("Neo4j not available")
    yield c
    # remove only this test's data, never constraints
    c.execute_write("MATCH (n) WHERE n.id IN $ids DETACH DELETE n", ids=CLEANUP_IDS)
    c.close()


def test_execute_read_is_parameterized_and_returns_dicts(client):
    rows = client.execute_read("RETURN $x AS doubled", x=21)
    assert rows == [{"doubled": 21}]


def test_bootstrap_schema_is_idempotent_and_creates_core_constraints(client):
    # Two runs must both succeed — no duplicate-constraint error on the second.
    schema.bootstrap_schema(client)
    schema.bootstrap_schema(client)
    rows = client.execute_read("SHOW CONSTRAINTS YIELD labelsOrTypes RETURN labelsOrTypes")
    labels = {lbl for row in rows for lbl in (row["labelsOrTypes"] or [])}
    # Core domain labels must have a uniqueness/existence constraint.
    for expected in ("Member", "Exercise", "Injury"):
        assert expected in labels, f"missing constraint for {expected}; got {labels}"


def test_timestamped_node_round_trips(client):
    schema.bootstrap_schema(client)
    ts = "2026-01-15T10:00:00+00:00"
    client.execute_write("MERGE (m:Member {id: $id}) SET m.name = $name", id="t002-m1", name="T")
    client.execute_write(
        "MATCH (m:Member {id: $mid}) "
        "MERGE (b:BiometricReading {id: $bid}) SET b.timestamp = $ts "
        "MERGE (m)-[:MEASURED]->(b)",
        mid="t002-m1",
        bid="t002-b1",
        ts=ts,
    )
    rows = client.execute_read(
        "MATCH (b:BiometricReading {id: $bid}) RETURN b.timestamp AS ts", bid="t002-b1"
    )
    assert rows[0]["ts"] == ts


def test_node_labels_constant_is_exposed():
    # The schema module documents the domain node labels it manages.
    assert {"Member", "Injury", "Goal", "Workout", "Exercise", "BiometricReading",
            "AdherenceRecord", "ChatMessage", "Transcript", "SnomedConcept",
            "BodyRegion", "MuscleGroup", "Equipment"} <= set(schema.NODE_LABELS)
