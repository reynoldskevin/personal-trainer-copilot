"""Ticket 004 — ontology + SNOMED subset + exercise/contraindication seed.

Contract (module `app.ingestion.ontology`):
- Curated in-repo data structures: SNOMED_CONCEPTS, BODY_REGIONS, MUSCLE_GROUPS, EQUIPMENT,
  EXERCISES, INJURIES, CONTRAINDICATIONS (lists of dicts).
- `load_ontology(client) -> dict` — idempotent MERGE of all nodes + edges into Neo4j.
- `contraindicated_exercises(client, injury_id) -> list[str]` — exercise ids unsafe for that injury.
- A documented mapping table file exists in-repo.

Pure-data tests always run. Integration tests require the local Neo4j and skip if it's down.
"""
import os
from pathlib import Path

import pytest

from app.graph import schema
from app.graph.client import Neo4jClient
from app.ingestion import ontology

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_RELS = ["CONTRAINDICATED_FOR", "MAPS_TO", "AFFECTS", "IN_REGION", "TARGETS", "REQUIRES"]


# ----------------------- pure-data (no Neo4j) -----------------------

def test_curated_data_is_nonempty():
    assert len(ontology.SNOMED_CONCEPTS) >= 5
    assert len(ontology.EXERCISES) >= 5
    assert len(ontology.INJURIES) >= 3
    assert len(ontology.CONTRAINDICATIONS) >= 3


def test_every_injury_maps_to_a_known_snomed_code():
    codes = {c["code"] for c in ontology.SNOMED_CONCEPTS}
    for inj in ontology.INJURIES:
        assert inj["snomed_code"] in codes, f"injury {inj['id']} has unknown SNOMED code"


def test_contraindications_reference_known_entities():
    injury_ids = {i["id"] for i in ontology.INJURIES}
    exercise_ids = {e["id"] for e in ontology.EXERCISES}
    for c in ontology.CONTRAINDICATIONS:
        assert c["injury_id"] in injury_ids, f"unknown injury_id {c['injury_id']}"
        assert c["exercise_id"] in exercise_ids, f"unknown exercise_id {c['exercise_id']}"


def test_exercises_reference_known_muscles_and_equipment():
    muscles = {m["id"] for m in ontology.MUSCLE_GROUPS}
    equipment = {e["id"] for e in ontology.EQUIPMENT}
    for ex in ontology.EXERCISES:
        for mg in ex["muscle_groups"]:
            assert mg in muscles, f"exercise {ex['id']} references unknown muscle {mg}"
        for eq in ex["equipment"]:
            assert eq in equipment, f"exercise {ex['id']} references unknown equipment {eq}"


def test_mapping_table_documented_in_repo():
    candidates = [
        REPO_ROOT / "docs" / "ontology_mapping.md",
        REPO_ROOT / "docs" / "ONTOLOGY_MAPPING.md",
    ]
    found = [p for p in candidates if p.exists()]
    assert found, "expected a documented ontology mapping table under docs/"
    text = found[0].read_text().lower()
    assert "snomed" in text and "contraindicat" in text


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
    yield c
    c.close()


def test_load_ontology_is_idempotent(client):
    ontology.load_ontology(client)
    n1 = client.execute_read("MATCH ()-[r:CONTRAINDICATED_FOR]->() RETURN count(r) AS c")[0]["c"]
    ontology.load_ontology(client)
    n2 = client.execute_read("MATCH ()-[r:CONTRAINDICATED_FOR]->() RETURN count(r) AS c")[0]["c"]
    assert n1 == n2
    assert n1 > 0


def test_all_required_edge_types_created(client):
    ontology.load_ontology(client)
    for rel in REQUIRED_RELS:
        rows = client.execute_read(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS c")
        assert rows[0]["c"] > 0, f"no {rel} edges created"


def test_contraindicated_exercises_query(client):
    ontology.load_ontology(client)
    c = ontology.CONTRAINDICATIONS[0]
    result = ontology.contraindicated_exercises(client, c["injury_id"])
    assert isinstance(result, list)
    assert c["exercise_id"] in result
