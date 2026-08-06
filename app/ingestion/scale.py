"""Ticket 022 — Scale: batched ingest + synthetic ~100K load.

A deterministic synthetic-member generator plus a batched, idempotent bulk-ingest that can load
~100K nodes into Neo4j, and small helpers to prove the load stays healthy at that size:

- :func:`synthetic_member` / :func:`generate_members` build members whose injuries and workout
  exercises reference the REAL ontology ids (:mod:`app.ingestion.ontology`), so every link MATCHes
  a shared ontology node rather than creating a competing one — exactly like the curated seed.
- :func:`bulk_ingest` chunks the load into batches and delegates each to
  :func:`app.ingestion.members.ingest_members`, whose ``MERGE``-on-stable-id writes make the whole
  thing idempotent: re-running duplicates nothing.
- :func:`member_lookup_plan` + :func:`uses_index_lookup` inspect the ``EXPLAIN`` query plan for the
  hot member-scoped lookup, confirming it is index-backed (not a full label scan) at scale.
- :func:`measure_retrieval_latency` times member-scoped retrieval so a caller can assert it stays
  under :data:`SCALE_LATENCY_BUDGET_MS`.

The 100M-node extension path is documented in ``docs/scale.md``.
"""
from __future__ import annotations

import argparse
from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from math import ceil
from time import perf_counter
from typing import Any

from app.graph.client import Neo4jClient, get_client
from app.ingestion import members as members_mod
from app.ingestion import ontology
from app.ingestion.members import (
    AdherenceRecord,
    BiometricReading,
    ChatMessage,
    Goal,
    Member,
    Transcript,
    Workout,
)
from app.llm.provider import LLMProvider
from app.observability import perf
from app.retrieval import service

# Ontology ids the synthetic members draw from, so their links resolve against loaded ontology.
_INJURY_IDS: list[str] = [i["id"] for i in ontology.INJURIES]
_EXERCISE_IDS: list[str] = [e["id"] for e in ontology.EXERCISES]

# Fixed structure per synthetic member (used to compute NODES_PER_MEMBER).
_GOALS_PER_MEMBER = 2
_WORKOUTS_PER_MEMBER = 3
_BIOMETRICS_PER_MEMBER = 3
_ADHERENCE_PER_MEMBER = 3
_CHATS_PER_MEMBER = 2
_TRANSCRIPTS_PER_MEMBER = 1

#: New graph nodes each synthetic member contributes (shared ontology nodes are NOT counted):
#: the Member plus its owned goals, workouts, biometrics, adherence, chats and transcripts.
NODES_PER_MEMBER: int = (
    1
    + _GOALS_PER_MEMBER
    + _WORKOUTS_PER_MEMBER
    + _BIOMETRICS_PER_MEMBER
    + _ADHERENCE_PER_MEMBER
    + _CHATS_PER_MEMBER
    + _TRANSCRIPTS_PER_MEMBER
)

#: Latency budget (ms) for a single member-scoped retrieval at scale. Member scoping is
#: index-backed, so retrieval is bound by the anchored seek — not the graph size — and stays an
#: order of magnitude below the end-to-end 5s generation budget.
SCALE_LATENCY_BUDGET_MS: float = 1500.0

_EPOCH = datetime(2025, 1, 1, tzinfo=UTC)

# Zero-padding width for ids/names — wide enough that no member's id/name is a substring of
# another's (e.g. "...00003" is not a prefix-substring of "...00030"), which keeps text-scan
# assertions (cross-member leakage checks) unambiguous.
_PAD = 5


def _ts(index: int, day_offset: int, hour: int = 9) -> str:
    """Deterministic ISO-8601 timestamp for member ``index``, spread across weeks."""
    dt = _EPOCH + timedelta(days=(index % 400) * 3 + day_offset, hours=hour)
    return dt.isoformat()


def synthetic_member(index: int) -> Member:
    """Build a deterministic synthetic member for ``index``.

    Same ``index`` always yields an identical member; distinct indices yield distinct ids. The
    member's single injury and every workout exercise reference REAL ontology ids so the ingest's
    ``MATCH`` links resolve against the loaded ontology.
    """
    mid = f"syn_member_{index:0{_PAD}d}"
    injury = _INJURY_IDS[index % len(_INJURY_IDS)]

    goals: list[Goal] = [
        {"id": f"goal_{mid}_{k}", "description": f"Synthetic goal {k} for member {index}"}
        for k in range(_GOALS_PER_MEMBER)
    ]
    workouts: list[Workout] = [
        {
            "id": f"workout_{mid}_{k}",
            "timestamp": _ts(index, day_offset=k * 7),
            "exercises": [
                _EXERCISE_IDS[(index + k) % len(_EXERCISE_IDS)],
                _EXERCISE_IDS[(index + k + 1) % len(_EXERCISE_IDS)],
            ],
        }
        for k in range(_WORKOUTS_PER_MEMBER)
    ]
    biometrics: list[BiometricReading] = [
        {
            "id": f"bio_{mid}_{k}",
            "timestamp": _ts(index, day_offset=k * 7, hour=7),
            "type": "resting_heart_rate" if k % 2 == 0 else "body_weight_kg",
            "value": 60.0 + (index % 10) + k,
        }
        for k in range(_BIOMETRICS_PER_MEMBER)
    ]
    adherence: list[AdherenceRecord] = [
        {
            "id": f"adh_{mid}_{k}",
            "timestamp": _ts(index, day_offset=k * 7, hour=20),
            "planned": 4,
            "completed": (index + k) % 5,
        }
        for k in range(_ADHERENCE_PER_MEMBER)
    ]
    chats: list[ChatMessage] = [
        {
            "id": f"chat_{mid}_{k}",
            "timestamp": _ts(index, day_offset=k, hour=10),
            "role": "member" if k % 2 == 0 else "coach",
            "text": (
                "How should I train around my shoulder this week?"
                if k % 2 == 0
                else "Keep loads light and prioritise pain-free ranges."
            ),
        }
        for k in range(_CHATS_PER_MEMBER)
    ]
    transcripts: list[Transcript] = [
        {
            "id": f"transcript_{mid}_{k}",
            "timestamp": _ts(index, day_offset=k, hour=12),
            "text": "Check-in call: reviewed rehab progress and adjusted training volume.",
        }
        for k in range(_TRANSCRIPTS_PER_MEMBER)
    ]

    return {
        "id": mid,
        "name": f"Synthetic Member {index:0{_PAD}d}",
        "injuries": [injury],
        "goals": goals,
        "workouts": workouts,
        "biometrics": biometrics,
        "adherence": adherence,
        "chats": chats,
        "transcripts": transcripts,
    }


def generate_members(count: int, *, start: int = 0) -> list[Member]:
    """Return ``count`` distinct synthetic members, indexed ``start .. start + count``."""
    return [synthetic_member(i) for i in range(start, start + count)]


def members_for_node_target(target_nodes: int) -> int:
    """Number of synthetic members needed to reach ~``target_nodes`` nodes (ceil)."""
    return ceil(target_nodes / NODES_PER_MEMBER)


def batched[T](items: Iterable[T], size: int) -> Iterator[list[T]]:
    """Yield contiguous chunks of ``items`` of length ``size`` (the last chunk may be shorter)."""
    if size < 1:
        raise ValueError("size must be >= 1")
    batch: list[T] = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def bulk_ingest(
    client: Neo4jClient, members: Sequence[Member], *, batch_size: int = 500
) -> dict[str, int]:
    """Idempotently bulk-load ``members`` into Neo4j in chunks of ``batch_size``.

    Each batch is delegated to :func:`app.ingestion.members.ingest_members`, whose parameterized
    ``MERGE`` writes key on stable ids — so re-running the same load duplicates nothing. The
    returned dict aggregates per-entity counts across batches plus ``members`` (total) and
    ``batches`` (chunk count).
    """
    totals: dict[str, int] = {"members": 0, "batches": 0}
    for batch in batched(members, batch_size):
        result = members_mod.ingest_members(client, list(batch))
        totals["batches"] += 1
        for key, value in result.items():
            totals[key] = totals.get(key, 0) + value
    return totals


# --------------------------------------------------------------------------- query-plan checks

# The hot member-scoped read: everything downstream starts from this anchored MATCH, so if THIS
# lookup is index-backed the retrieval path stays index-backed at any scale.
_MEMBER_LOOKUP_CYPHER = (
    "MATCH (m:Member {id: $member_id})-[:HAS_INJURY]->(i:Injury) RETURN i.id AS id"
)

# Plan operators that read EVERY node of a label (or the whole store) — the un-indexed hot-path
# regression the plan check must catch.
_FULL_SCAN_OPS = ("NodeByLabelScan", "AllNodesScan")


def member_lookup_plan(client: Neo4jClient, member_id: str) -> dict[str, Any]:
    """Return the ``EXPLAIN`` plan (root operator dict) for the hot member-scoped lookup.

    Waits for indexes to come ONLINE first so the plan reflects the intended index-backed access
    (a freshly created constraint index that is still populating can otherwise be planned as an
    index scan rather than the ideal unique-index seek).
    """
    client.execute_read("CALL db.awaitIndexes($seconds)", seconds=30)
    return client.explain(_MEMBER_LOOKUP_CYPHER, member_id=member_id)


def plan_operators(plan: dict[str, Any]) -> list[str]:
    """Flatten a Neo4j plan tree into a pre-order list of its ``operatorType`` names."""
    ops: list[str] = []
    op = plan.get("operatorType")
    if isinstance(op, str):
        ops.append(op)
    for child in plan.get("children", []):
        ops.extend(plan_operators(child))
    return ops


def uses_index_lookup(plan: dict[str, Any]) -> bool:
    """True iff the hot member lookup is index-backed rather than a full label/all-nodes scan.

    The anchored ``(m:Member {id: ...})`` lookup is index-backed on ``Member.id`` — ideally a
    ``NodeUniqueIndexSeek`` (O(1)), which is what production gets from the uniqueness constraint.
    Depending on index state/version the planner may instead pick a ``NodeIndexScan``; both hit the
    id index and satisfy "index usage on the hot path". The regression this guards against is the
    lookup degrading to a ``NodeByLabelScan`` — reading every Member — which this returns False for.
    """
    ops = plan_operators(plan)
    has_index = any("Index" in op for op in ops)
    has_full_scan = any(scan in op for op in ops for scan in _FULL_SCAN_OPS)
    return has_index and not has_full_scan


# --------------------------------------------------------------------------- latency at scale

def measure_retrieval_latency(
    client: Neo4jClient,
    provider: LLMProvider,
    member_id: str,
    query: str,
    *,
    iterations: int = 5,
) -> perf.LatencyStats:
    """Time ``iterations`` member-scoped retrievals and summarize their latency (ms)."""
    samples: list[float] = []
    for _ in range(iterations):
        start = perf_counter()
        service.retrieve(client, provider, member_id, query)
        samples.append((perf_counter() - start) * 1000.0)
    return perf.summarize(samples)


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    """Load synthetic members into the configured Neo4j via batched ingest.

    ``--members N`` loads exactly N; otherwise ``--nodes`` (default 100000) is converted to a
    member count via :func:`members_for_node_target`. ``--batch-size`` controls chunk size.
    """
    parser = argparse.ArgumentParser(description="Synthetic batched load for scale testing.")
    parser.add_argument("--members", type=int, default=None, help="exact member count to load")
    parser.add_argument("--nodes", type=int, default=100_000, help="approx node target")
    parser.add_argument("--batch-size", type=int, default=500, help="members per write batch")
    args = parser.parse_args(argv)

    count = args.members if args.members is not None else members_for_node_target(args.nodes)
    client = get_client()
    try:
        report = bulk_ingest(client, generate_members(count), batch_size=args.batch_size)
    finally:
        client.close()
    print(  # noqa: T201 — CLI console output
        f"loaded {report['members']} synthetic members "
        f"(~{report['members'] * NODES_PER_MEMBER} nodes) in {report['batches']} batches"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
