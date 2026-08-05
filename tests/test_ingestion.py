"""Ticket 005 — member seed ingestion (timestamped, idempotent).

Contract (module `app.ingestion.members`):
- `MEMBER_SEED` — list of >=3 member dicts. Each: id, name, injuries (ontology injury ids),
  goals, workouts (timestamped, exercises = ontology exercise ids), biometrics (timestamped,
  multi-date), adherence (timestamped, multi-date), chats, transcripts.
- `ingest_members(client, members=None) -> dict` — idempotent MERGE linking every entity with
  timestamps, reusing ontology Injury/Exercise nodes.

Pure-data tests always run; integration tests need Neo4j and skip if it is down.
"""
import os
from datetime import date

import pytest

from app.graph import schema
from app.graph.client import Neo4jClient
from app.ingestion import members, ontology


def _dates(records):
    return sorted({r["timestamp"][:10] for r in records})


def _injured_member():
    for m in members.MEMBER_SEED:
        if m["injuries"]:
            return m
    raise AssertionError("no injured member in seed")


# ----------------------- pure-data (no Neo4j) -----------------------

def test_seed_has_at_least_three_members():
    assert len(members.MEMBER_SEED) >= 3


def test_at_least_one_member_has_an_active_injury():
    assert any(m["injuries"] for m in members.MEMBER_SEED)


def test_member_injuries_reference_ontology():
    known = {i["id"] for i in ontology.INJURIES}
    for m in members.MEMBER_SEED:
        for inj in m["injuries"]:
            assert inj in known, f"member {m['id']} references unknown injury {inj}"


def test_workout_exercises_reference_ontology():
    known = {e["id"] for e in ontology.EXERCISES}
    for m in members.MEMBER_SEED:
        for w in m["workouts"]:
            for ex in w["exercises"]:
                assert ex in known, f"unknown exercise {ex} in workout {w['id']}"


def test_injured_member_has_multi_week_dated_history():
    m = _injured_member()
    adh_dates = _dates(m["adherence"])
    bio_dates = _dates(m["biometrics"])
    assert len(adh_dates) >= 3, "need multiple adherence dates"
    assert len(bio_dates) >= 3, "need multiple biometric dates"
    span = (date.fromisoformat(adh_dates[-1]) - date.fromisoformat(adh_dates[0])).days
    assert span >= 14, f"adherence history should span multiple weeks, got {span} days"


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
    ontology.load_ontology(c)  # members reference ontology injuries/exercises
    yield c
    c.close()


def test_ingest_is_idempotent(client):
    members.ingest_members(client)
    n1 = client.execute_read("MATCH (m:Member) RETURN count(m) AS c")[0]["c"]
    members.ingest_members(client)
    n2 = client.execute_read("MATCH (m:Member) RETURN count(m) AS c")[0]["c"]
    assert n1 == n2
    assert n1 >= 3


def test_member_entities_are_linked(client):
    members.ingest_members(client)
    mid = _injured_member()["id"]
    rows = client.execute_read(
        """
        MATCH (m:Member {id: $id})
        RETURN
          size([(m)-[:HAS_INJURY]->(:Injury) | 1]) AS injuries,
          size([(m)-[:PERFORMED]->(:Workout) | 1]) AS workouts,
          size([(m)-[:MEASURED]->(:BiometricReading) | 1]) AS biometrics,
          size([(m)-[:HAS_ADHERENCE]->(:AdherenceRecord) | 1]) AS adherence,
          size([(m)-[:HAS_GOAL]->(:Goal) | 1]) AS goals
        """,
        id=mid,
    )
    r = rows[0]
    assert r["injuries"] >= 1
    assert r["workouts"] >= 1
    assert r["biometrics"] >= 1
    assert r["adherence"] >= 1
    assert r["goals"] >= 1


def test_workout_links_to_ontology_exercise(client):
    members.ingest_members(client)
    rows = client.execute_read(
        "MATCH (:Member)-[:PERFORMED]->(:Workout)-[:INCLUDES]->(e:Exercise) RETURN count(e) AS c"
    )
    assert rows[0]["c"] >= 1


def test_adherence_records_are_timestamped_multidate(client):
    members.ingest_members(client)
    mid = _injured_member()["id"]
    rows = client.execute_read(
        """
        MATCH (:Member {id: $id})-[:HAS_ADHERENCE]->(a:AdherenceRecord)
        WHERE a.timestamp IS NOT NULL
        RETURN count(DISTINCT substring(a.timestamp, 0, 10)) AS distinct_dates
        """,
        id=mid,
    )
    assert rows[0]["distinct_dates"] >= 3
