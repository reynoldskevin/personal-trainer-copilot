"""Ticket 007 — Retrieval Service: hybrid GraphRAG.

Fuses two complementary retrieval signals into a single, token-bounded context bundle for a
member:

- a **global** semantic vector search over all text-bearing nodes
  (:func:`app.retrieval.embeddings.similarity_search`), and
- a **member-scoped** subgraph traversal rooted at ``(m:Member {id:$member_id})`` that reads
  the member's injuries, goals, recent workouts, adherence and biometrics as human-readable
  facts — every fact query starts from the member node so no other member's private entities
  can leak in.

It also computes the member's **contraindication set**: the sorted, de-duplicated union of
exercises unsafe for the member's active injuries
(:func:`app.ingestion.ontology.contraindicated_exercises`). Contraindications are safety data
and are always returned in full, never dropped by the budget.

The fused narrative (:attr:`ContextBundle.context_items`) prioritises subgraph facts, then
vector-hit texts, greedily appended while the running :func:`estimate_tokens` sum stays within
``token_budget``.

All member subgraph reads are parameterized (the member id is passed as query data, never
string-interpolated), matching the injection-safe pattern of :mod:`app.graph.client`.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from app.generation import budget
from app.graph.client import Neo4jClient
from app.ingestion import ontology
from app.llm.provider import LLMProvider
from app.observability import tracing
from app.retrieval import embeddings
from app.retrieval.temporal import (
    TimeWindow,
    TrendSummary,
    compute_trends,
    filter_window,
)

# Default token budget for a fused context bundle and default vector-search fan-out.
DEFAULT_TOKEN_BUDGET: int = 2000
DEFAULT_K: int = 5

# Characters-per-token heuristic for the deterministic token estimate.
_CHARS_PER_TOKEN: int = 4

# How many recent time-series rows to surface per relationship.
_RECENT_LIMIT: int = 3


def estimate_tokens(text: str) -> int:
    """Return a deterministic, non-negative token estimate for ``text``.

    Uses a simple characters-per-token heuristic: ``len(text) // _CHARS_PER_TOKEN``. The empty
    string yields ``0`` and a longer string always estimates at least as many tokens as a
    shorter one, which is all the budgeting logic relies on.
    """
    return max(0, len(text) // _CHARS_PER_TOKEN)


class VectorHit(BaseModel):
    """One vector-search hit: a text-bearing node ranked by similarity to the query."""

    id: str
    labels: list[str]
    score: float
    text: str | None


class ContextBundle(BaseModel):
    """The fused, token-bounded retrieval result for a member and query.

    ``vector_hits`` and ``subgraph_facts`` are the raw retrieved signals; ``context_items`` is
    the token-bounded narrative actually destined for a prompt (facts first, then vector-hit
    texts). ``contraindications`` is the member's full safety set (never budget-dropped).
    ``token_estimate`` is :func:`estimate_tokens` summed over ``context_items`` and never
    exceeds ``token_budget``.
    """

    member_id: str
    query: str
    vector_hits: list[VectorHit]
    subgraph_facts: list[str]
    context_items: list[str]
    contraindications: list[str]
    token_estimate: int
    token_budget: int
    trends: TrendSummary | None = None


def _subgraph_facts(client: Neo4jClient, member_id: str) -> list[str]:
    """Assemble human-readable facts about ``member_id`` from member-scoped Cypher.

    Runs one small query per relationship, each rooted at ``(m:Member {id:$member_id})``, so no
    other member's entities can appear. Recent time-series rows are ordered by ``timestamp``
    descending and capped to keep the context small.
    """
    facts: list[str] = []

    name_rows = client.execute_read(
        "MATCH (m:Member {id: $member_id}) RETURN m.name AS name",
        member_id=member_id,
    )
    if name_rows and name_rows[0].get("name"):
        facts.append(f"Member: {name_rows[0]['name']}.")

    injury_rows = client.execute_read(
        "MATCH (m:Member {id: $member_id})-[:HAS_INJURY]->(i:Injury) "
        "RETURN i.name AS name ORDER BY i.name",
        member_id=member_id,
    )
    for row in injury_rows:
        facts.append(f"Active injury: {row['name']}.")

    goal_rows = client.execute_read(
        "MATCH (m:Member {id: $member_id})-[:HAS_GOAL]->(g:Goal) "
        "RETURN g.description AS description ORDER BY g.id",
        member_id=member_id,
    )
    for row in goal_rows:
        facts.append(f"Goal: {row['description']}.")

    workout_rows = client.execute_read(
        "MATCH (m:Member {id: $member_id})-[:PERFORMED]->(w:Workout) "
        "OPTIONAL MATCH (w)-[:INCLUDES]->(e:Exercise) "
        "WITH w, collect(e.name) AS exercises "
        "RETURN w.timestamp AS timestamp, exercises ORDER BY w.timestamp DESC LIMIT $limit",
        member_id=member_id,
        limit=_RECENT_LIMIT,
    )
    for row in workout_rows:
        exercises = ", ".join(row["exercises"]) if row["exercises"] else "no exercises recorded"
        facts.append(f"Workout on {row['timestamp']}: {exercises}.")

    adherence_rows = client.execute_read(
        "MATCH (m:Member {id: $member_id})-[:HAS_ADHERENCE]->(a:AdherenceRecord) "
        "RETURN a.timestamp AS timestamp, a.planned AS planned, a.completed AS completed "
        "ORDER BY a.timestamp DESC LIMIT $limit",
        member_id=member_id,
        limit=_RECENT_LIMIT,
    )
    for row in adherence_rows:
        facts.append(
            f"Adherence on {row['timestamp']}: completed {row['completed']} of "
            f"{row['planned']} planned sessions."
        )

    biometric_rows = client.execute_read(
        "MATCH (m:Member {id: $member_id})-[:MEASURED]->(b:BiometricReading) "
        "RETURN b.timestamp AS timestamp, b.type AS type, b.value AS value "
        "ORDER BY b.timestamp DESC LIMIT $limit",
        member_id=member_id,
        limit=_RECENT_LIMIT,
    )
    for row in biometric_rows:
        facts.append(f"Biometric on {row['timestamp']}: {row['type']} = {row['value']}.")

    return facts


def _member_header_facts(client: Neo4jClient, member_id: str) -> list[str]:
    """Assemble the member's static (non-time-series) facts: name, injuries and goals.

    Each query is rooted at ``(m:Member {id:$member_id})`` so no other member's entities appear.
    """
    facts: list[str] = []

    name_rows = client.execute_read(
        "MATCH (m:Member {id: $member_id}) RETURN m.name AS name",
        member_id=member_id,
    )
    if name_rows and name_rows[0].get("name"):
        facts.append(f"Member: {name_rows[0]['name']}.")

    injury_rows = client.execute_read(
        "MATCH (m:Member {id: $member_id})-[:HAS_INJURY]->(i:Injury) "
        "RETURN i.name AS name ORDER BY i.name",
        member_id=member_id,
    )
    for row in injury_rows:
        facts.append(f"Active injury: {row['name']}.")

    goal_rows = client.execute_read(
        "MATCH (m:Member {id: $member_id})-[:HAS_GOAL]->(g:Goal) "
        "RETURN g.description AS description ORDER BY g.id",
        member_id=member_id,
    )
    for row in goal_rows:
        facts.append(f"Goal: {row['description']}.")

    return facts


def _member_workout_rows(client: Neo4jClient, member_id: str) -> list[dict[str, Any]]:
    """Return the member's full workout history (timestamp + exercises), newest first."""
    return client.execute_read(
        "MATCH (m:Member {id: $member_id})-[:PERFORMED]->(w:Workout) "
        "OPTIONAL MATCH (w)-[:INCLUDES]->(e:Exercise) "
        "WITH w, collect(e.name) AS exercises "
        "RETURN w.timestamp AS timestamp, exercises ORDER BY w.timestamp DESC",
        member_id=member_id,
    )


def _member_adherence_rows(client: Neo4jClient, member_id: str) -> list[dict[str, Any]]:
    """Return the member's full adherence history, newest first."""
    return client.execute_read(
        "MATCH (m:Member {id: $member_id})-[:HAS_ADHERENCE]->(a:AdherenceRecord) "
        "RETURN a.timestamp AS timestamp, a.planned AS planned, a.completed AS completed "
        "ORDER BY a.timestamp DESC",
        member_id=member_id,
    )


def _member_biometric_rows(client: Neo4jClient, member_id: str) -> list[dict[str, Any]]:
    """Return the member's full biometric history, newest first."""
    return client.execute_read(
        "MATCH (m:Member {id: $member_id})-[:MEASURED]->(b:BiometricReading) "
        "RETURN b.timestamp AS timestamp, b.type AS type, b.value AS value "
        "ORDER BY b.timestamp DESC",
        member_id=member_id,
    )


def _render_workout(row: Mapping[str, Any]) -> str:
    exercises = ", ".join(row["exercises"]) if row["exercises"] else "no exercises recorded"
    return f"Workout on {row['timestamp']}: {exercises}."


def _render_adherence(row: Mapping[str, Any]) -> str:
    return (
        f"Adherence on {row['timestamp']}: completed {row['completed']} of "
        f"{row['planned']} planned sessions."
    )


def _render_biometric(row: Mapping[str, Any]) -> str:
    return f"Biometric on {row['timestamp']}: {row['type']} = {row['value']}."


def _windowed_subgraph_facts(
    client: Neo4jClient,
    member_id: str,
    window: TimeWindow,
    workout_rows: list[dict[str, Any]],
    adherence_rows: list[dict[str, Any]],
    biometric_rows: list[dict[str, Any]],
) -> list[str]:
    """Assemble member facts with time-series activity scoped to ``window``.

    Static facts (name, injuries, goals) are always included; workout, adherence and biometric
    rows are filtered to the window via :func:`filter_window` before rendering.
    """
    facts = _member_header_facts(client, member_id)
    facts.extend(_render_workout(row) for row in filter_window(workout_rows, window))
    facts.extend(_render_adherence(row) for row in filter_window(adherence_rows, window))
    facts.extend(_render_biometric(row) for row in filter_window(biometric_rows, window))
    return facts


def _contraindications(client: Neo4jClient, member_id: str) -> list[str]:
    """Return the sorted, de-duplicated union of exercises unsafe for the member's injuries."""
    injury_rows = client.execute_read(
        "MATCH (m:Member {id: $member_id})-[:HAS_INJURY]->(i:Injury) "
        "RETURN i.id AS id ORDER BY i.id",
        member_id=member_id,
    )
    unsafe: set[str] = set()
    for row in injury_rows:
        unsafe.update(ontology.contraindicated_exercises(client, row["id"]))
    return sorted(unsafe)


def _budgeted_items(candidates: list[str], token_budget: int) -> tuple[list[str], int]:
    """Truncate ``candidates`` to ``token_budget`` by rank (highest-ranked prefix kept).

    Delegates to :func:`app.generation.budget.truncate_to_budget` so retrieval, prompt guards and
    trace token counts all share one truncation rule: candidates are already ordered by importance
    (trend summaries, then subgraph facts, then vector-hit texts), and the kept set is the
    highest-ranked prefix whose summed :func:`estimate_tokens` never exceeds ``token_budget``.
    """
    return budget.truncate_to_budget(candidates, token_budget)


def retrieve(
    client: Neo4jClient,
    provider: LLMProvider,
    member_id: str,
    query: str,
    *,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    k: int = DEFAULT_K,
    window: TimeWindow | None = None,
) -> ContextBundle:
    """Retrieve a fused, token-bounded GraphRAG context bundle for a member and query.

    Fuses a global vector search (query embedded via ``provider``) with a member-scoped
    subgraph traversal and the member's contraindication set. The narrative
    (``context_items``) prioritises subgraph facts, then vector-hit texts, greedily appended
    within ``token_budget``; contraindications are always returned in full.

    When ``window`` is supplied, the member's time-series facts (workouts, adherence,
    biometrics) are scoped to that trailing window and a :class:`TrendSummary` computed from the
    in-window rows is attached as ``trends``; its ``summary_lines`` are prepended to
    ``context_items`` so the trends survive the token budget. When ``window`` is ``None`` the
    behaviour is unchanged and ``trends`` stays ``None``.
    """
    tracer = tracing.get_tracer()
    with tracer.span("retrieval", member_id=member_id) as rspan:
        with tracer.span("retrieval.vector_search"):
            qvec = embeddings.embed_query(provider, query)
            raw_hits = embeddings.similarity_search(client, qvec, k=k)
            vector_hits = [
                VectorHit(
                    id=hit["id"],
                    labels=hit["labels"],
                    score=hit["score"],
                    text=hit.get("text"),
                )
                for hit in raw_hits
            ]

        with tracer.span("retrieval.contraindications"):
            contraindications = _contraindications(client, member_id)

        with tracer.span("retrieval.subgraph"):
            trends: TrendSummary | None = None
            summary_lines: list[str] = []
            if window is None:
                subgraph_facts = _subgraph_facts(client, member_id)
            else:
                workout_rows = _member_workout_rows(client, member_id)
                adherence_rows = _member_adherence_rows(client, member_id)
                biometric_rows = _member_biometric_rows(client, member_id)
                subgraph_facts = _windowed_subgraph_facts(
                    client, member_id, window, workout_rows, adherence_rows, biometric_rows
                )
                trends = compute_trends(
                    window=window,
                    adherence_rows=adherence_rows,
                    biometric_rows=biometric_rows,
                    workout_rows=workout_rows,
                )
                summary_lines = trends.summary_lines

        candidates: list[str] = list(summary_lines)
        candidates.extend(subgraph_facts)
        candidates.extend(hit.text for hit in vector_hits if hit.text)
        context_items, token_estimate = _budgeted_items(candidates, token_budget)

        rspan.set(
            token_estimate=token_estimate,
            vector_hits=len(vector_hits),
            subgraph_facts=len(subgraph_facts),
            contraindications=len(contraindications),
        )

        return ContextBundle(
            member_id=member_id,
            query=query,
            vector_hits=vector_hits,
            subgraph_facts=subgraph_facts,
            context_items=context_items,
            contraindications=contraindications,
            token_estimate=token_estimate,
            token_budget=token_budget,
            trends=trends,
        )
