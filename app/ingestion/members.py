"""Ticket 005 — member seed ingestion (timestamped, idempotent).

This module holds a small, curated set of seed **members** with realistic, time-stamped
histories (workouts, biometric readings, adherence records, chat messages and coaching
transcripts) plus injuries and goals. ``ingest_members`` idempotently MERGEs each member and
its related entities into Neo4j, reusing the existing ontology ``Injury``/``Exercise`` nodes
loaded by :mod:`app.ingestion.ontology`.

All writes are parameterized (data passed via ``UNWIND $rows AS row``, never
string-interpolated) and keyed on stable ids with ``MERGE`` so running the ingest repeatedly
never duplicates data.
"""
from __future__ import annotations

from typing import TypedDict

from app.graph.client import Neo4jClient

# --------------------------------------------------------------------------- typed rows

class Goal(TypedDict):
    id: str
    description: str


class Workout(TypedDict):
    id: str
    timestamp: str
    exercises: list[str]


class BiometricReading(TypedDict):
    id: str
    timestamp: str
    type: str
    value: float


class AdherenceRecord(TypedDict):
    id: str
    timestamp: str
    planned: int
    completed: int


class ChatMessage(TypedDict):
    id: str
    timestamp: str
    role: str
    text: str


class Transcript(TypedDict):
    id: str
    timestamp: str
    text: str


class Member(TypedDict):
    id: str
    name: str
    injuries: list[str]
    goals: list[Goal]
    workouts: list[Workout]
    biometrics: list[BiometricReading]
    adherence: list[AdherenceRecord]
    chats: list[ChatMessage]
    transcripts: list[Transcript]


# --------------------------------------------------------------------------- curated seed

MEMBER_SEED: list[Member] = [
    {
        "id": "member_ava",
        "name": "Ava Thompson",
        # Active injury — the "injured member" the tests key on.
        "injuries": ["rotator_cuff_tear"],
        "goals": [
            {"id": "goal_ava_shoulder", "description": "Rehab right shoulder and press pain-free"},
            {"id": "goal_ava_strength", "description": "Return to a bodyweight squat for 5 reps"},
        ],
        "workouts": [
            {
                "id": "workout_ava_1",
                "timestamp": "2026-01-06T09:00:00+00:00",
                "exercises": ["barbell_back_squat", "push_up"],
            },
            {
                "id": "workout_ava_2",
                "timestamp": "2026-01-13T09:15:00+00:00",
                "exercises": ["leg_extension", "barbell_curl"],
            },
            {
                "id": "workout_ava_3",
                "timestamp": "2026-01-27T08:45:00+00:00",
                "exercises": ["barbell_back_squat", "conventional_deadlift"],
            },
        ],
        "biometrics": [
            {
                "id": "bio_ava_1",
                "timestamp": "2026-01-06T07:30:00+00:00",
                "type": "resting_heart_rate",
                "value": 61.0,
            },
            {
                "id": "bio_ava_2",
                "timestamp": "2026-01-13T07:32:00+00:00",
                "type": "body_weight_kg",
                "value": 68.4,
            },
            {
                "id": "bio_ava_3",
                "timestamp": "2026-01-27T07:28:00+00:00",
                "type": "resting_heart_rate",
                "value": 58.0,
            },
        ],
        "adherence": [
            {
                "id": "adh_ava_1",
                "timestamp": "2026-01-06T20:00:00+00:00",
                "planned": 4,
                "completed": 2,
            },
            {
                "id": "adh_ava_2",
                "timestamp": "2026-01-13T20:00:00+00:00",
                "planned": 4,
                "completed": 3,
            },
            {
                "id": "adh_ava_3",
                "timestamp": "2026-01-20T20:00:00+00:00",
                "planned": 4,
                "completed": 3,
            },
            {
                "id": "adh_ava_4",
                "timestamp": "2026-01-27T20:00:00+00:00",
                "planned": 4,
                "completed": 4,
            },
        ],
        "chats": [
            {
                "id": "chat_ava_1",
                "timestamp": "2026-01-06T09:45:00+00:00",
                "role": "member",
                "text": "My shoulder aches when I press overhead — should I skip it this week?",
            },
            {
                "id": "chat_ava_2",
                "timestamp": "2026-01-06T09:47:00+00:00",
                "role": "coach",
                "text": "Yes, let's avoid overhead pressing for now and focus on pain-free ranges.",
            },
        ],
        "transcripts": [
            {
                "id": "transcript_ava_1",
                "timestamp": "2026-01-06T10:00:00+00:00",
                "text": "Check-in call: reviewed shoulder rehab and scaled back pressing volume.",
            },
        ],
    },
    {
        "id": "member_ben",
        "name": "Ben Carter",
        "injuries": [],
        "goals": [
            {"id": "goal_ben_deadlift", "description": "Deadlift 180kg for a single"},
            {"id": "goal_ben_consistency", "description": "Train four sessions every week"},
        ],
        "workouts": [
            {
                "id": "workout_ben_1",
                "timestamp": "2026-02-03T18:00:00+00:00",
                "exercises": ["conventional_deadlift", "barbell_back_squat"],
            },
            {
                "id": "workout_ben_2",
                "timestamp": "2026-02-10T18:05:00+00:00",
                "exercises": ["bench_press", "overhead_press"],
            },
        ],
        "biometrics": [
            {
                "id": "bio_ben_1",
                "timestamp": "2026-02-03T06:45:00+00:00",
                "type": "body_weight_kg",
                "value": 84.1,
            },
            {
                "id": "bio_ben_2",
                "timestamp": "2026-02-17T06:50:00+00:00",
                "type": "body_weight_kg",
                "value": 83.6,
            },
        ],
        "adherence": [
            {
                "id": "adh_ben_1",
                "timestamp": "2026-02-03T21:00:00+00:00",
                "planned": 4,
                "completed": 4,
            },
            {
                "id": "adh_ben_2",
                "timestamp": "2026-02-10T21:00:00+00:00",
                "planned": 4,
                "completed": 3,
            },
        ],
        "chats": [
            {
                "id": "chat_ben_1",
                "timestamp": "2026-02-03T19:00:00+00:00",
                "role": "member",
                "text": "Hit all my sets today, deadlifts felt strong!",
            },
        ],
        "transcripts": [
            {
                "id": "transcript_ben_1",
                "timestamp": "2026-02-04T12:00:00+00:00",
                "text": "Programming review: increased deadlift intensity for the next block.",
            },
        ],
    },
    {
        "id": "member_chloe",
        "name": "Chloe Nguyen",
        "injuries": ["lumbar_strain"],
        "goals": [
            {"id": "goal_chloe_core", "description": "Rebuild core stability after back strain"},
            {"id": "goal_chloe_mobility", "description": "Restore pain-free hip hinge mechanics"},
        ],
        "workouts": [
            {
                "id": "workout_chloe_1",
                "timestamp": "2026-03-02T12:30:00+00:00",
                "exercises": ["push_up", "leg_extension"],
            },
            {
                "id": "workout_chloe_2",
                "timestamp": "2026-03-16T12:35:00+00:00",
                "exercises": ["bench_press", "barbell_curl"],
            },
        ],
        "biometrics": [
            {
                "id": "bio_chloe_1",
                "timestamp": "2026-03-02T07:00:00+00:00",
                "type": "resting_heart_rate",
                "value": 64.0,
            },
            {
                "id": "bio_chloe_2",
                "timestamp": "2026-03-16T07:05:00+00:00",
                "type": "sleep_hours",
                "value": 7.5,
            },
        ],
        "adherence": [
            {
                "id": "adh_chloe_1",
                "timestamp": "2026-03-02T20:30:00+00:00",
                "planned": 3,
                "completed": 2,
            },
            {
                "id": "adh_chloe_2",
                "timestamp": "2026-03-16T20:30:00+00:00",
                "planned": 3,
                "completed": 3,
            },
        ],
        "chats": [
            {
                "id": "chat_chloe_1",
                "timestamp": "2026-03-02T13:00:00+00:00",
                "role": "member",
                "text": "Lower back felt tight during warm-up, took it easy on hinging.",
            },
            {
                "id": "chat_chloe_2",
                "timestamp": "2026-03-02T13:02:00+00:00",
                "role": "coach",
                "text": "Good call — keep loads light and prioritise bracing this week.",
            },
        ],
        "transcripts": [
            {
                "id": "transcript_chloe_1",
                "timestamp": "2026-03-03T15:00:00+00:00",
                "text": "Assessment call: screened lumbar strain and set a return-to-load plan.",
            },
        ],
    },
]


# --------------------------------------------------------------------------- ingest

def ingest_members(
    client: Neo4jClient, members: list[Member] | None = None
) -> dict[str, int]:
    """Idempotently MERGE members and their related entities into Neo4j.

    Every write is parameterized and keyed on stable ids with ``MERGE`` so running twice never
    duplicates. Injury and Exercise links MATCH the existing ontology nodes by id (loaded by
    :func:`app.ingestion.ontology.load_ontology`) rather than creating competing nodes.
    """
    if members is None:
        members = MEMBER_SEED

    # --- members ---
    client.execute_write(
        "UNWIND $rows AS row "
        "MERGE (m:Member {id: row.id}) SET m.name = row.name",
        rows=[{"id": m["id"], "name": m["name"]} for m in members],
    )

    # --- injuries (reuse existing ontology Injury nodes) ---
    injury_rows = [
        {"member_id": m["id"], "injury_id": inj}
        for m in members
        for inj in m["injuries"]
    ]
    client.execute_write(
        "UNWIND $rows AS row "
        "MATCH (m:Member {id: row.member_id}), (i:Injury {id: row.injury_id}) "
        "MERGE (m)-[:HAS_INJURY]->(i)",
        rows=injury_rows,
    )

    # --- goals ---
    goal_rows = [
        {"member_id": m["id"], "id": g["id"], "description": g["description"]}
        for m in members
        for g in m["goals"]
    ]
    client.execute_write(
        "UNWIND $rows AS row "
        "MATCH (m:Member {id: row.member_id}) "
        "MERGE (g:Goal {id: row.id}) SET g.description = row.description "
        "MERGE (m)-[:HAS_GOAL]->(g)",
        rows=goal_rows,
    )

    # --- workouts + INCLUDES exercise links (reuse ontology Exercise nodes) ---
    workout_rows = [
        {"member_id": m["id"], "id": w["id"], "timestamp": w["timestamp"]}
        for m in members
        for w in m["workouts"]
    ]
    client.execute_write(
        "UNWIND $rows AS row "
        "MATCH (m:Member {id: row.member_id}) "
        "MERGE (w:Workout {id: row.id}) SET w.timestamp = row.timestamp "
        "MERGE (m)-[:PERFORMED]->(w)",
        rows=workout_rows,
    )
    workout_exercise_rows = [
        {"workout_id": w["id"], "exercise_id": ex}
        for m in members
        for w in m["workouts"]
        for ex in w["exercises"]
    ]
    client.execute_write(
        "UNWIND $rows AS row "
        "MATCH (w:Workout {id: row.workout_id}), (e:Exercise {id: row.exercise_id}) "
        "MERGE (w)-[:INCLUDES]->(e)",
        rows=workout_exercise_rows,
    )

    # --- biometric readings ---
    biometric_rows = [
        {
            "member_id": m["id"],
            "id": b["id"],
            "timestamp": b["timestamp"],
            "type": b["type"],
            "value": b["value"],
        }
        for m in members
        for b in m["biometrics"]
    ]
    client.execute_write(
        "UNWIND $rows AS row "
        "MATCH (m:Member {id: row.member_id}) "
        "MERGE (b:BiometricReading {id: row.id}) "
        "SET b.timestamp = row.timestamp, b.type = row.type, b.value = row.value "
        "MERGE (m)-[:MEASURED]->(b)",
        rows=biometric_rows,
    )

    # --- adherence records ---
    adherence_rows = [
        {
            "member_id": m["id"],
            "id": a["id"],
            "timestamp": a["timestamp"],
            "planned": a["planned"],
            "completed": a["completed"],
        }
        for m in members
        for a in m["adherence"]
    ]
    client.execute_write(
        "UNWIND $rows AS row "
        "MATCH (m:Member {id: row.member_id}) "
        "MERGE (a:AdherenceRecord {id: row.id}) "
        "SET a.timestamp = row.timestamp, a.planned = row.planned, a.completed = row.completed "
        "MERGE (m)-[:HAS_ADHERENCE]->(a)",
        rows=adherence_rows,
    )

    # --- chat messages ---
    chat_rows = [
        {
            "member_id": m["id"],
            "id": c["id"],
            "timestamp": c["timestamp"],
            "role": c["role"],
            "text": c["text"],
        }
        for m in members
        for c in m["chats"]
    ]
    client.execute_write(
        "UNWIND $rows AS row "
        "MATCH (m:Member {id: row.member_id}) "
        "MERGE (c:ChatMessage {id: row.id}) "
        "SET c.timestamp = row.timestamp, c.role = row.role, c.text = row.text "
        "MERGE (m)-[:SENT]->(c)",
        rows=chat_rows,
    )

    # --- transcripts ---
    transcript_rows = [
        {"member_id": m["id"], "id": t["id"], "timestamp": t["timestamp"], "text": t["text"]}
        for m in members
        for t in m["transcripts"]
    ]
    client.execute_write(
        "UNWIND $rows AS row "
        "MATCH (m:Member {id: row.member_id}) "
        "MERGE (t:Transcript {id: row.id}) SET t.timestamp = row.timestamp, t.text = row.text "
        "MERGE (m)-[:IN_SESSION]->(t)",
        rows=transcript_rows,
    )

    return {
        "members": len(members),
        "injuries": len(injury_rows),
        "goals": len(goal_rows),
        "workouts": len(workout_rows),
        "workout_exercises": len(workout_exercise_rows),
        "biometrics": len(biometric_rows),
        "adherence": len(adherence_rows),
        "chats": len(chat_rows),
        "transcripts": len(transcript_rows),
    }
