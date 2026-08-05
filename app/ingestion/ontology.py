"""Ticket 004 — curated ontology + SNOMED subset + exercise/contraindication seed.

This module holds a small, **curated** reference knowledge graph used to reason about
fitness-coaching safety. It exposes in-repo data structures (lists of dicts) and an
idempotent loader that MERGEs them into Neo4j together with the relationships that connect
injuries, SNOMED concepts, body regions, muscle groups, equipment and exercises.

The SNOMED CT codes below are a **curated subset** chosen for common musculoskeletal
conditions relevant to strength coaching. They are NOT the full SNOMED CT release — see
``docs/ontology_mapping.md`` for the documented mapping and the extension point for loading
the complete terminology later.

All writes are parameterized (data passed as query params, never string-interpolated) and use
``MERGE`` so ``load_ontology`` is safe to run repeatedly without creating duplicates.
"""
from __future__ import annotations

from typing import TypedDict

from app.graph.client import Neo4jClient

# --------------------------------------------------------------------------- typed rows

class SnomedConcept(TypedDict):
    code: str
    label: str
    body_region: str


class BodyRegion(TypedDict):
    id: str
    name: str


class MuscleGroup(TypedDict):
    id: str
    name: str
    body_region: str


class Equipment(TypedDict):
    id: str
    name: str


class Exercise(TypedDict):
    id: str
    name: str
    description: str
    muscle_groups: list[str]
    equipment: list[str]


class Injury(TypedDict):
    id: str
    name: str
    snomed_code: str


class Contraindication(TypedDict):
    injury_id: str
    exercise_id: str
    reason: str


# --------------------------------------------------------------------------- curated data

# Curated SUBSET of SNOMED CT — common musculoskeletal conditions only. These are real,
# plausible SNOMED CT concept identifiers, not the full release. See docs/ontology_mapping.md.
SNOMED_CONCEPTS: list[SnomedConcept] = [
    {"code": "202856007", "label": "Rotator cuff syndrome", "body_region": "shoulder"},
    {"code": "202855006", "label": "Lateral epicondylitis", "body_region": "elbow"},
    {"code": "239720000", "label": "Rupture of anterior cruciate ligament", "body_region": "knee"},
    {"code": "209583007", "label": "Sprain of lumbar spine", "body_region": "lumbar_spine"},
    {"code": "202580003", "label": "Patellar tendinopathy", "body_region": "knee"},
]

BODY_REGIONS: list[BodyRegion] = [
    {"id": "shoulder", "name": "Shoulder"},
    {"id": "elbow", "name": "Elbow"},
    {"id": "knee", "name": "Knee"},
    {"id": "lumbar_spine", "name": "Lumbar spine"},
    {"id": "chest", "name": "Chest"},
    {"id": "hip", "name": "Hip"},
]

MUSCLE_GROUPS: list[MuscleGroup] = [
    {"id": "deltoids", "name": "Deltoids", "body_region": "shoulder"},
    {"id": "rotator_cuff", "name": "Rotator cuff", "body_region": "shoulder"},
    {"id": "pectorals", "name": "Pectorals", "body_region": "chest"},
    {"id": "biceps", "name": "Biceps brachii", "body_region": "elbow"},
    {"id": "triceps", "name": "Triceps brachii", "body_region": "elbow"},
    {"id": "forearm_extensors", "name": "Forearm extensors", "body_region": "elbow"},
    {"id": "quadriceps", "name": "Quadriceps", "body_region": "knee"},
    {"id": "hamstrings", "name": "Hamstrings", "body_region": "knee"},
    {"id": "glutes", "name": "Gluteals", "body_region": "hip"},
    {"id": "erector_spinae", "name": "Erector spinae", "body_region": "lumbar_spine"},
]

EQUIPMENT: list[Equipment] = [
    {"id": "barbell", "name": "Barbell"},
    {"id": "dumbbell", "name": "Dumbbell"},
    {"id": "bodyweight", "name": "Bodyweight"},
    {"id": "machine", "name": "Machine"},
    {"id": "kettlebell", "name": "Kettlebell"},
    {"id": "cable", "name": "Cable"},
]

EXERCISES: list[Exercise] = [
    {
        "id": "overhead_press",
        "name": "Barbell overhead press",
        "description": "Standing press of a barbell from shoulders to overhead.",
        "muscle_groups": ["deltoids", "triceps", "rotator_cuff"],
        "equipment": ["barbell"],
    },
    {
        "id": "bench_press",
        "name": "Barbell bench press",
        "description": "Horizontal press of a barbell while lying supine on a bench.",
        "muscle_groups": ["pectorals", "deltoids", "triceps"],
        "equipment": ["barbell"],
    },
    {
        "id": "barbell_back_squat",
        "name": "Barbell back squat",
        "description": "Squat with a barbell racked across the upper back.",
        "muscle_groups": ["quadriceps", "glutes", "erector_spinae"],
        "equipment": ["barbell"],
    },
    {
        "id": "conventional_deadlift",
        "name": "Conventional deadlift",
        "description": "Hip-hinge lift of a barbell from the floor to lockout.",
        "muscle_groups": ["hamstrings", "glutes", "erector_spinae"],
        "equipment": ["barbell"],
    },
    {
        "id": "barbell_curl",
        "name": "Barbell biceps curl",
        "description": "Elbow-flexion curl of a barbell with a supinated grip.",
        "muscle_groups": ["biceps", "forearm_extensors"],
        "equipment": ["barbell"],
    },
    {
        "id": "leg_extension",
        "name": "Machine leg extension",
        "description": "Seated open-chain knee extension against a machine pad.",
        "muscle_groups": ["quadriceps"],
        "equipment": ["machine"],
    },
    {
        "id": "push_up",
        "name": "Push-up",
        "description": "Bodyweight horizontal press from a prone plank position.",
        "muscle_groups": ["pectorals", "triceps", "deltoids"],
        "equipment": ["bodyweight"],
    },
]

INJURIES: list[Injury] = [
    {"id": "rotator_cuff_tear", "name": "Rotator cuff injury", "snomed_code": "202856007"},
    {"id": "tennis_elbow", "name": "Lateral epicondylitis", "snomed_code": "202855006"},
    {"id": "acl_tear", "name": "ACL rupture", "snomed_code": "239720000"},
    {"id": "lumbar_strain", "name": "Lumbar strain", "snomed_code": "209583007"},
    {"id": "patellar_tendinopathy", "name": "Patellar tendinopathy", "snomed_code": "202580003"},
]

CONTRAINDICATIONS: list[Contraindication] = [
    {
        "injury_id": "rotator_cuff_tear",
        "exercise_id": "overhead_press",
        "reason": "Overhead pressing loads the rotator cuff at end-range abduction, aggravating "
        "impingement and cuff tears.",
    },
    {
        "injury_id": "rotator_cuff_tear",
        "exercise_id": "bench_press",
        "reason": "Barbell bench pressing forces horizontal adduction under load that stresses an "
        "injured cuff and anterior shoulder.",
    },
    {
        "injury_id": "tennis_elbow",
        "exercise_id": "barbell_curl",
        "reason": "Loaded elbow flexion with a fixed bar strains the common extensor origin, "
        "worsening lateral epicondylitis.",
    },
    {
        "injury_id": "lumbar_strain",
        "exercise_id": "conventional_deadlift",
        "reason": "Heavy hip-hinge loading places high shear and compressive demand on an already "
        "strained lumbar spine.",
    },
    {
        "injury_id": "lumbar_strain",
        "exercise_id": "barbell_back_squat",
        "reason": "Axial spinal loading under a back-racked barbell aggravates an acute lumbar "
        "strain.",
    },
    {
        "injury_id": "acl_tear",
        "exercise_id": "leg_extension",
        "reason": "Open-chain knee extension produces high anterior tibial translation, stressing "
        "a deficient or healing ACL.",
    },
    {
        "injury_id": "patellar_tendinopathy",
        "exercise_id": "barbell_back_squat",
        "reason": "Deep loaded knee flexion increases patellar tendon load and provokes "
        "tendinopathy pain.",
    },
]


# --------------------------------------------------------------------------- loader

def load_ontology(client: Neo4jClient) -> dict[str, int]:
    """Idempotently MERGE the curated ontology into Neo4j and return per-entity counts.

    All node and relationship writes use ``MERGE`` keyed on stable ids (SnomedConcept keyed on
    its ``code``, also stored as ``id``), so running this repeatedly never duplicates data. Data
    is passed as query parameters via ``UNWIND $rows AS row``.
    """
    # --- nodes ---
    client.execute_write(
        "UNWIND $rows AS row "
        "MERGE (n:BodyRegion {id: row.id}) SET n.name = row.name",
        rows=[dict(r) for r in BODY_REGIONS],
    )
    client.execute_write(
        "UNWIND $rows AS row "
        "MERGE (n:SnomedConcept {id: row.code}) "
        "SET n.code = row.code, n.label = row.label, n.body_region = row.body_region",
        rows=[dict(r) for r in SNOMED_CONCEPTS],
    )
    client.execute_write(
        "UNWIND $rows AS row "
        "MERGE (n:MuscleGroup {id: row.id}) "
        "SET n.name = row.name, n.body_region = row.body_region",
        rows=[dict(r) for r in MUSCLE_GROUPS],
    )
    client.execute_write(
        "UNWIND $rows AS row "
        "MERGE (n:Equipment {id: row.id}) SET n.name = row.name",
        rows=[dict(r) for r in EQUIPMENT],
    )
    client.execute_write(
        "UNWIND $rows AS row "
        "MERGE (n:Exercise {id: row.id}) "
        "SET n.name = row.name, n.description = row.description",
        rows=[
            {"id": e["id"], "name": e["name"], "description": e["description"]}
            for e in EXERCISES
        ],
    )
    client.execute_write(
        "UNWIND $rows AS row "
        "MERGE (n:Injury {id: row.id}) "
        "SET n.name = row.name, n.snomed_code = row.snomed_code",
        rows=[dict(r) for r in INJURIES],
    )

    # --- relationships ---
    client.execute_write(
        "UNWIND $rows AS row "
        "MATCH (m:MuscleGroup {id: row.id}), (b:BodyRegion {id: row.body_region}) "
        "MERGE (m)-[:IN_REGION]->(b)",
        rows=[{"id": m["id"], "body_region": m["body_region"]} for m in MUSCLE_GROUPS],
    )
    client.execute_write(
        "UNWIND $rows AS row "
        "MATCH (s:SnomedConcept {id: row.code}), (b:BodyRegion {id: row.body_region}) "
        "MERGE (s)-[:AFFECTS]->(b)",
        rows=[{"code": s["code"], "body_region": s["body_region"]} for s in SNOMED_CONCEPTS],
    )
    client.execute_write(
        "UNWIND $rows AS row "
        "MATCH (i:Injury {id: row.id}), (s:SnomedConcept {id: row.snomed_code}) "
        "MERGE (i)-[:MAPS_TO]->(s)",
        rows=[{"id": i["id"], "snomed_code": i["snomed_code"]} for i in INJURIES],
    )
    client.execute_write(
        "UNWIND $rows AS row "
        "MATCH (e:Exercise {id: row.exercise_id}), (m:MuscleGroup {id: row.muscle_id}) "
        "MERGE (e)-[:TARGETS]->(m)",
        rows=[
            {"exercise_id": e["id"], "muscle_id": mg}
            for e in EXERCISES
            for mg in e["muscle_groups"]
        ],
    )
    client.execute_write(
        "UNWIND $rows AS row "
        "MATCH (e:Exercise {id: row.exercise_id}), (q:Equipment {id: row.equipment_id}) "
        "MERGE (e)-[:REQUIRES]->(q)",
        rows=[
            {"exercise_id": e["id"], "equipment_id": eq}
            for e in EXERCISES
            for eq in e["equipment"]
        ],
    )
    client.execute_write(
        "UNWIND $rows AS row "
        "MATCH (e:Exercise {id: row.exercise_id}), (i:Injury {id: row.injury_id}) "
        "MERGE (e)-[r:CONTRAINDICATED_FOR]->(i) SET r.reason = row.reason",
        rows=[dict(c) for c in CONTRAINDICATIONS],
    )

    return {
        "body_regions": len(BODY_REGIONS),
        "snomed_concepts": len(SNOMED_CONCEPTS),
        "muscle_groups": len(MUSCLE_GROUPS),
        "equipment": len(EQUIPMENT),
        "exercises": len(EXERCISES),
        "injuries": len(INJURIES),
        "contraindications": len(CONTRAINDICATIONS),
    }


def contraindicated_exercises(client: Neo4jClient, injury_id: str) -> list[str]:
    """Return the ids of exercises marked contraindicated for the given injury."""
    rows = client.execute_read(
        "MATCH (e:Exercise)-[:CONTRAINDICATED_FOR]->(:Injury {id: $injury_id}) "
        "RETURN e.id AS id ORDER BY e.id",
        injury_id=injury_id,
    )
    return [row["id"] for row in rows]
