"""Ticket 012 — InsightReport + injury-safe insight generation.

Produces a member-facing :class:`InsightReport` that fuses two layers:

1. **Deterministic risk derivation** (:func:`risk_flags_from_trends`) — reads a
   :class:`~app.retrieval.temporal.TrendSummary` and emits typed :class:`RiskFlag` objects from
   fixed rules (e.g. low windowed adherence), with no language model involved. These flags are
   reproducible and auditable.
2. **LLM narrative** (:func:`generate_insight`) — windowed GraphRAG retrieval (trends attached)
   plus a JSON insight from the model, guardrailed so no exercise contraindicated for the
   member's injuries is ever surfaced as a recommendation.

The JSON completion is parsed defensively (reusing workout's ``_extract_json_object``) so
malformed model output degrades to sensible defaults rather than raising, and the same
contraindication invariant the workout path enforces runs here so an unsafe pick is excluded and
disclosed regardless of what the model does.
"""
from __future__ import annotations

import json

from pydantic import BaseModel

from app.generation import budget
from app.generation.workout import _extract_json_object
from app.graph.client import Neo4jClient
from app.llm.provider import LLMProvider
from app.observability import tracing
from app.retrieval import service
from app.retrieval.temporal import TimeWindow, TrendSummary

# Prompt version pinned onto every emitted insight generation trace.
PROMPT_VERSION: str = "insight-v1"

# Default review query, retrieval window, token budget and vector fan-out for an insight report.
DEFAULT_QUERY: str = "Review this member's recent training trends, adherence and injury risks."
DEFAULT_WINDOW_WEEKS: int = 12
DEFAULT_TOKEN_BUDGET: int = service.DEFAULT_TOKEN_BUDGET
DEFAULT_K: int = service.DEFAULT_K

# Adherence thresholds (windowed percentage) below which a risk flag fires.
_ADHERENCE_RISK_THRESHOLD: float = 70.0
_ADHERENCE_HIGH_THRESHOLD: float = 50.0


class RiskFlag(BaseModel):
    """A single, typed risk signal derived deterministically from a member's trends."""

    kind: str
    severity: str
    detail: str


class InsightReport(BaseModel):
    """A member-facing insight report grounded in the member's windowed trends.

    ``risk_flags`` are deterministic signals derived from ``trends``; ``personalization_notes``
    are the model's (safe) coaching notes; ``excluded_contraindicated`` lists any recommendation
    the model proposed that was stripped as unsafe, and ``safety_flags`` holds the human-readable
    disclosure for each such removal.
    """

    member_id: str
    summary: str
    risk_flags: list[RiskFlag]
    personalization_notes: list[str]
    trends: TrendSummary | None
    excluded_contraindicated: list[str]
    safety_flags: list[str]


def risk_flags_from_trends(trends: TrendSummary) -> list[RiskFlag]:
    """Derive deterministic :class:`RiskFlag` objects from a :class:`TrendSummary`.

    Rules (no language model, reproducible):

    - **adherence** — when ``adherence_percentage`` is below :data:`_ADHERENCE_RISK_THRESHOLD`,
      emit an ``kind="adherence"`` flag (severity ``"high"`` below
      :data:`_ADHERENCE_HIGH_THRESHOLD`, else ``"medium"``). A ``None`` adherence yields no
      adherence flag and never raises.
    - **inactivity** — when ``workout_count`` is zero, emit a ``kind="inactivity"`` flag.

    Healthy inputs (adherence at or above threshold, at least one workout) produce no flags.
    """
    flags: list[RiskFlag] = []

    pct = trends.adherence_percentage
    if pct is not None and pct < _ADHERENCE_RISK_THRESHOLD:
        severity = "high" if pct < _ADHERENCE_HIGH_THRESHOLD else "medium"
        window = trends.window_weeks
        window_phrase = f" over the last {window} weeks" if window is not None else ""
        flags.append(
            RiskFlag(
                kind="adherence",
                severity=severity,
                detail=(
                    f"Windowed adherence is low at {pct:.1f}%{window_phrase}, below the "
                    f"{_ADHERENCE_RISK_THRESHOLD:.0f}% target — increased risk of stalled "
                    f"progress and disengagement."
                ),
            )
        )

    if trends.workout_count == 0:
        flags.append(
            RiskFlag(
                kind="inactivity",
                severity="medium",
                detail="No workouts recorded in the trend window — engagement has lapsed.",
            )
        )

    return flags


def _parse_insight(
    completion: str,
) -> tuple[str, list[str], list[str]]:
    """Parse a model completion into ``(summary, personalization_notes, recommended_ids)``.

    Defensive by design: prose, fenced JSON, truncated JSON or wrong-typed fields all degrade to
    sensible defaults rather than raising. Non-string list items are coerced/skipped so the
    downstream guardrail always receives clean data.
    """
    default_summary = "Personalized insight report."
    try:
        data = json.loads(_extract_json_object(completion))
    except (ValueError, TypeError):
        return default_summary, [], []
    if not isinstance(data, dict):
        return default_summary, [], []

    summary = str(data.get("summary") or default_summary)

    notes_raw = data.get("personalization_notes", [])
    notes: list[str] = (
        [str(note) for note in notes_raw if note is not None and str(note)]
        if isinstance(notes_raw, list)
        else []
    )

    recs_raw = data.get("recommended_exercise_ids", [])
    recommended: list[str] = (
        [str(rec) for rec in recs_raw if rec is not None and str(rec)]
        if isinstance(recs_raw, list)
        else []
    )

    return summary, notes, recommended


def _build_messages(bundle: service.ContextBundle) -> list[dict[str, str]]:
    """Assemble the chat messages instructing the model to return a JSON insight object."""
    context_lines = bundle.context_items or bundle.subgraph_facts
    system = (
        "You are a certified strength coach and analyst who writes concise, safe, personalized "
        "training insights grounded strictly in the member's provided context and trends. "
        "Return ONLY a JSON object of the form "
        '{"summary": str, "personalization_notes": [str], "recommended_exercise_ids": [str]}.'
    )
    user = (
        "Member context and trends:\n"
        + "\n".join(context_lines)
        + "\n\nWrite an insight report for this member as JSON."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def generate_insight(
    client: Neo4jClient,
    provider: LLMProvider,
    member_id: str,
    *,
    window: TimeWindow | None = None,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    k: int = DEFAULT_K,
) -> InsightReport:
    """Generate an injury-safe :class:`InsightReport` for ``member_id``.

    Retrieves the member's windowed GraphRAG context (with ``trends`` attached), derives
    deterministic risk flags from those trends, prompts ``provider`` for a JSON insight, then
    guardrails the model's recommendations against the member's contraindication set. Any
    contraindicated recommendation is excluded and disclosed in ``safety_flags``; it can never
    appear as a kept recommendation.
    """
    if not member_id or not member_id.strip():
        raise ValueError("member_id must be a non-empty string")

    with tracing.get_tracer().trace("generation.insight", prompt_version=PROMPT_VERSION) as span:
        window = window or TimeWindow(weeks=DEFAULT_WINDOW_WEEKS)
        bundle = service.retrieve(
            client,
            provider,
            member_id,
            DEFAULT_QUERY,
            token_budget=token_budget,
            k=k,
            window=window,
        )

        risk_flags = risk_flags_from_trends(bundle.trends) if bundle.trends else []

        messages = _build_messages(bundle)
        completion = provider.chat(messages, response_format=budget.RESPONSE_FORMAT)
        usage = tracing.token_usage(messages, completion)
        span.set(**usage)
        summary, notes, recommended = _parse_insight(completion)

        # Structural safety invariant (same guarantee the workout path enforces): strip any
        # recommendation contraindicated for the member's active injuries, preserving order.
        unsafe = set(bundle.contraindications)
        offenders = [rec for rec in recommended if rec in unsafe]
        excluded = set(offenders)
        safety_flags = [
            f"Excluded contraindicated recommendation '{offender}' — unsafe for this member's "
            f"active injuries."
            for offender in offenders
        ]

        # Fold only the safe recommendations into the personalization notes; offenders never
        # appear in a kept/recommended position.
        personalization_notes = list(notes)
        for rec in recommended:
            if rec not in excluded:
                personalization_notes.append(f"Recommended focus: {rec}.")

        return InsightReport(
            member_id=member_id,
            summary=summary,
            risk_flags=risk_flags,
            personalization_notes=personalization_notes,
            trends=bundle.trends,
            excluded_contraindicated=offenders,
            safety_flags=safety_flags,
        )
