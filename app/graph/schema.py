"""Graph schema management.

Declares the domain node labels the platform manages and provides an *idempotent*
`bootstrap_schema` that creates a uniqueness constraint on ``id`` for every label plus a
range index on ``timestamp`` for the time-varying labels. All DDL uses ``IF NOT EXISTS``
so it is safe to run on every startup.

Constraint/index statements are built from the fixed `NODE_LABELS` constant — never from
user input — so the label interpolation here is safe. Query *data* is always parameterized.
"""
from __future__ import annotations

from app.graph.client import Neo4jClient

# Domain node labels this schema manages.
NODE_LABELS: tuple[str, ...] = (
    "Member",
    "Injury",
    "Goal",
    "Workout",
    "Exercise",
    "BiometricReading",
    "AdherenceRecord",
    "ChatMessage",
    "Transcript",
    "SnomedConcept",
    "BodyRegion",
    "MuscleGroup",
    "Equipment",
)

# Labels whose nodes carry a `timestamp` worth a range index for time-ordered queries.
TIMESTAMPED_LABELS: tuple[str, ...] = (
    "Workout",
    "BiometricReading",
    "AdherenceRecord",
    "ChatMessage",
    "Transcript",
)


def bootstrap_schema(client: Neo4jClient) -> None:
    """Create uniqueness constraints and indexes idempotently.

    Safe to run repeatedly: every statement uses ``IF NOT EXISTS`` so a second run raises
    no duplicate-constraint/index error.
    """
    for label in NODE_LABELS:
        constraint_name = f"unique_{label.lower()}_id"
        client.execute_write(
            f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
        )

    for label in TIMESTAMPED_LABELS:
        index_name = f"index_{label.lower()}_timestamp"
        client.execute_write(
            f"CREATE INDEX {index_name} IF NOT EXISTS "
            f"FOR (n:{label}) ON (n.timestamp)"
        )
