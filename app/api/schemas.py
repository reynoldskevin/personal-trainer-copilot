"""Ticket 009 — Pydantic request/response models for the FastAPI surface.

Defines the typed request bodies and member-facing response models used by
:mod:`app.api.routes`. Retrieval and generation responses reuse the domain models
:class:`app.retrieval.service.ContextBundle` and
:class:`app.generation.workout.WorkoutPlan` directly, so those endpoints are documented and
serialized straight from the service layer without a parallel schema.
"""
from __future__ import annotations

from pydantic import BaseModel


class RetrieveRequest(BaseModel):
    """Request body for ``POST /retrieve``.

    ``member_id`` and ``query`` are required (omitting either yields a 422). ``token_budget``
    and ``k`` are optional retrieval tuning knobs passed through to the service when provided.
    """

    member_id: str
    query: str
    token_budget: int | None = None
    k: int | None = None


class GenerateWorkoutRequest(BaseModel):
    """Request body for ``POST /generate/workout``.

    ``member_id`` is required (an empty body yields a 422). ``query`` optionally overrides the
    default retrieval query used to build the member's context.
    """

    member_id: str
    query: str | None = None


class MemberSummary(BaseModel):
    """A compact member listing entry returned by ``GET /members``."""

    id: str
    name: str
    injuries: list[str]
    goals: list[str]


class WorkoutSummary(BaseModel):
    """A single recent workout: its timestamp and the exercise names it included."""

    timestamp: str
    exercises: list[str]


class AdherenceSummary(BaseModel):
    """A single adherence record: planned vs. completed sessions at a timestamp."""

    timestamp: str
    planned: int
    completed: int


class MemberDetail(BaseModel):
    """Full member detail returned by ``GET /members/{member_id}``.

    ``injuries`` holds injury names, ``goals`` holds goal descriptions, and
    ``recent_workouts``/``adherence`` hold the member's most recent time-series rows.
    """

    id: str
    name: str
    injuries: list[str]
    goals: list[str]
    recent_workouts: list[WorkoutSummary]
    adherence: list[AdherenceSummary]
