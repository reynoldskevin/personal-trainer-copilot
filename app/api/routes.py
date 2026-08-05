"""Ticket 009 — FastAPI routes: members, retrieve, generate/workout.

Wires the typed API surface onto an :class:`fastapi.APIRouter`:

- ``GET  /members``            — list member summaries (id, name, injuries, goals),
- ``GET  /members/{member_id}`` — one member's detail (404 if unknown),
- ``POST /retrieve``           — a hybrid GraphRAG :class:`~app.retrieval.service.ContextBundle`,
- ``POST /generate/workout``   — an injury-safe :class:`~app.generation.workout.WorkoutPlan`.

Every route depends on the shared callables in :mod:`app.api.deps` so tests can override the
Neo4j client and LLM provider. All member reads are parameterized (the member id is passed as
query data, never string-interpolated).
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app.api import schemas
from app.api.deps import get_llm_provider, get_neo4j_client
from app.generation import chat, workout
from app.generation.chat import ChatAnswer
from app.generation.workout import WorkoutPlan
from app.graph.client import Neo4jClient
from app.llm.provider import LLMProvider
from app.retrieval import service
from app.retrieval.service import ContextBundle

router = APIRouter()

# Injected dependencies, referencing the shared callables tests override.
ClientDep = Annotated[Neo4jClient, Depends(get_neo4j_client)]
ProviderDep = Annotated[LLMProvider, Depends(get_llm_provider)]

# How many recent time-series rows to surface per member relationship in the detail view.
_RECENT_LIMIT: int = 5


@router.get("/members", response_model=list[schemas.MemberSummary])
def list_members(
    client: ClientDep,
) -> list[schemas.MemberSummary]:
    """Return a summary of every member: id, name, injury names and goal descriptions."""
    rows = client.execute_read(
        "MATCH (m:Member) "
        "OPTIONAL MATCH (m)-[:HAS_INJURY]->(i:Injury) "
        "OPTIONAL MATCH (m)-[:HAS_GOAL]->(g:Goal) "
        "RETURN m.id AS id, m.name AS name, "
        "collect(DISTINCT i.name) AS injuries, collect(DISTINCT g.description) AS goals "
        "ORDER BY m.name"
    )
    return [
        schemas.MemberSummary(
            id=row["id"],
            name=row["name"],
            injuries=row["injuries"],
            goals=row["goals"],
        )
        for row in rows
    ]


@router.get("/members/{member_id}", response_model=schemas.MemberDetail)
def get_member(
    member_id: str,
    client: ClientDep,
) -> schemas.MemberDetail:
    """Return one member's detail, or raise 404 if no member has ``member_id``."""
    name_rows = client.execute_read(
        "MATCH (m:Member {id: $member_id}) RETURN m.name AS name",
        member_id=member_id,
    )
    if not name_rows:
        raise HTTPException(status_code=404, detail=f"Unknown member: {member_id}")

    injury_rows = client.execute_read(
        "MATCH (m:Member {id: $member_id})-[:HAS_INJURY]->(i:Injury) "
        "RETURN i.name AS name ORDER BY i.name",
        member_id=member_id,
    )
    goal_rows = client.execute_read(
        "MATCH (m:Member {id: $member_id})-[:HAS_GOAL]->(g:Goal) "
        "RETURN g.description AS description ORDER BY g.id",
        member_id=member_id,
    )
    workout_rows = client.execute_read(
        "MATCH (m:Member {id: $member_id})-[:PERFORMED]->(w:Workout) "
        "OPTIONAL MATCH (w)-[:INCLUDES]->(e:Exercise) "
        "WITH w, collect(e.name) AS exercises "
        "RETURN w.timestamp AS timestamp, exercises "
        "ORDER BY w.timestamp DESC LIMIT $limit",
        member_id=member_id,
        limit=_RECENT_LIMIT,
    )
    adherence_rows = client.execute_read(
        "MATCH (m:Member {id: $member_id})-[:HAS_ADHERENCE]->(a:AdherenceRecord) "
        "RETURN a.timestamp AS timestamp, a.planned AS planned, a.completed AS completed "
        "ORDER BY a.timestamp DESC LIMIT $limit",
        member_id=member_id,
        limit=_RECENT_LIMIT,
    )

    return schemas.MemberDetail(
        id=member_id,
        name=name_rows[0]["name"],
        injuries=[row["name"] for row in injury_rows],
        goals=[row["description"] for row in goal_rows],
        recent_workouts=[
            schemas.WorkoutSummary(timestamp=row["timestamp"], exercises=row["exercises"])
            for row in workout_rows
        ],
        adherence=[
            schemas.AdherenceSummary(
                timestamp=row["timestamp"],
                planned=row["planned"],
                completed=row["completed"],
            )
            for row in adherence_rows
        ],
    )


@router.post("/retrieve", response_model=ContextBundle)
def retrieve(
    req: schemas.RetrieveRequest,
    client: ClientDep,
    provider: ProviderDep,
) -> ContextBundle:
    """Return a fused GraphRAG context bundle for the request's member and query."""
    kwargs: dict[str, Any] = {}
    if req.token_budget is not None:
        kwargs["token_budget"] = req.token_budget
    if req.k is not None:
        kwargs["k"] = req.k
    return service.retrieve(client, provider, req.member_id, req.query, **kwargs)


@router.post("/generate/workout", response_model=WorkoutPlan)
def generate_workout(
    req: schemas.GenerateWorkoutRequest,
    client: ClientDep,
    provider: ProviderDep,
) -> WorkoutPlan:
    """Return an injury-safe workout plan for the request's member."""
    if req.query is not None:
        return workout.generate_workout(client, provider, req.member_id, query=req.query)
    return workout.generate_workout(client, provider, req.member_id)


@router.post("/chat", response_model=ChatAnswer)
def chat_answer(
    req: schemas.ChatRequest,
    client: ClientDep,
    provider: ProviderDep,
) -> ChatAnswer:
    """Answer the coach's question about the request's member, grounded in member context."""
    return chat.answer_question(client, provider, req.member_id, req.message)
