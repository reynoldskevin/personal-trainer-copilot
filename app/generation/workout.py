"""Ticket 008 — Generation: WorkoutPlan + injury-safe guardrail.

Assembles a personalized :class:`WorkoutPlan` for a member through a LangGraph pipeline that
enforces a hard safety invariant: no matter what the language model proposes, the final plan
for an injured member contains **zero** exercises contraindicated for their injuries.

The pipeline is a :class:`langgraph.graph.StateGraph` with four nodes:

1. **retrieve** — fetch a token-bounded GraphRAG :class:`~app.retrieval.service.ContextBundle`
   (member context + contraindication set) via :func:`app.retrieval.service.retrieve`.
2. **pre-filter** — read the ontology's exercise catalog from Neo4j and subtract the member's
   contraindications, so unsafe exercises never appear in the prompt handed to the model.
3. **prompt + chat** — assemble the chat ``messages`` (member context + the *safe* candidate
   exercises + a JSON output instruction) and call :meth:`LLMProvider.chat`.
4. **parse + post-validate** — parse the JSON completion into :class:`PlannedExercise` objects
   and run :func:`filter_contraindicated` against the contraindication set. Any contraindicated
   pick is stripped regardless of what the model returned, and recorded transparently in
   ``excluded_contraindicated`` and ``safety_flags``.

Both defensive layers (pre-filter and post-validate) are deliberate: pre-filtering keeps unsafe
options out of the model's reach, while post-validation guarantees the invariant even if the
model hallucinates or defies the instruction.
"""
from __future__ import annotations

import json
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from app.generation import guardrails
from app.graph.client import Neo4jClient
from app.llm.provider import LLMProvider
from app.retrieval import service
from app.retrieval.service import ContextBundle

# Default retrieval query, token budget and vector fan-out for a generated workout.
DEFAULT_QUERY: str = "Design a safe, personalized strength workout for this member."
DEFAULT_TOKEN_BUDGET: int = service.DEFAULT_TOKEN_BUDGET
DEFAULT_K: int = service.DEFAULT_K


class PlannedExercise(BaseModel):
    """A single prescribed exercise within a workout plan."""

    exercise_id: str
    name: str
    sets: int
    reps: int
    notes: str | None = None


class WorkoutPlan(BaseModel):
    """A typed, injury-safe workout plan for a member.

    ``exercises`` is guaranteed to contain no exercise contraindicated for the member's
    injuries. ``excluded_contraindicated`` lists every contraindicated exercise id that was
    kept out of the plan — both those pre-filtered before the model saw them and any the model
    proposed that post-validation stripped. ``safety_flags`` holds the human-readable
    explanations for each post-validation removal.
    """

    member_id: str
    summary: str
    exercises: list[PlannedExercise]
    safety_flags: list[str]
    excluded_contraindicated: list[str]


def filter_contraindicated(
    exercises: list[PlannedExercise],
    contraindicated: list[str],
) -> tuple[list[PlannedExercise], list[str]]:
    """Split ``exercises`` into safe kept exercises and the ids removed as contraindicated.

    Pure post-validation with no side effects: returns ``(kept, removed_ids)`` where ``kept``
    preserves the input order of every exercise whose ``exercise_id`` is not in
    ``contraindicated``, and ``removed_ids`` lists the contraindicated ids in their order of
    appearance.
    """
    removed_ids = guardrails.check_exercises_safe(
        [exercise.exercise_id for exercise in exercises],
        contraindicated,
    )
    unsafe = set(removed_ids)
    kept = [exercise for exercise in exercises if exercise.exercise_id not in unsafe]
    return kept, removed_ids


class _SafeCandidate(TypedDict):
    """A safe candidate exercise offered to the model in the prompt."""

    id: str
    name: str
    description: str


class _WorkoutState(TypedDict, total=False):
    """Mutable state threaded through the LangGraph workout-generation pipeline."""

    client: Neo4jClient
    provider: LLMProvider
    member_id: str
    query: str
    token_budget: int
    k: int
    bundle: ContextBundle
    candidates: list[_SafeCandidate]
    messages: list[dict[str, str]]
    completion: str
    plan: WorkoutPlan


def _retrieve_node(state: _WorkoutState) -> _WorkoutState:
    """Retrieve the member's token-bounded GraphRAG context bundle."""
    bundle = service.retrieve(
        state["client"],
        state["provider"],
        state["member_id"],
        state["query"],
        token_budget=state["token_budget"],
        k=state["k"],
    )
    return {"bundle": bundle}


def _prefilter_node(state: _WorkoutState) -> _WorkoutState:
    """Compute the safe candidate catalog: all ontology exercises minus contraindications."""
    rows = state["client"].execute_read(
        "MATCH (e:Exercise) RETURN e.id AS id, e.name AS name, e.description AS description "
        "ORDER BY e.id"
    )
    unsafe = set(state["bundle"].contraindications)
    candidates: list[_SafeCandidate] = [
        {"id": row["id"], "name": row["name"], "description": row["description"] or ""}
        for row in rows
        if row["id"] not in unsafe
    ]
    return {"candidates": candidates}


def _prompt_node(state: _WorkoutState) -> _WorkoutState:
    """Assemble the chat messages and call the model, recording the completion."""
    candidates = state["candidates"]
    context_lines = state["bundle"].context_items or state["bundle"].subgraph_facts
    catalog_lines = [f"- {c['id']}: {c['name']}" for c in candidates]

    system = (
        "You are a certified strength coach who designs safe, personalized workouts. "
        "You may only prescribe exercises drawn from the provided safe candidate list; "
        "never invent exercises or use any not listed. Return ONLY a JSON object of the form "
        '{"summary": str, "exercises": [{"exercise_id": str, "name": str, "sets": int, '
        '"reps": int, "notes": str (optional)}]}.'
    )
    user = (
        "Member context:\n"
        + "\n".join(context_lines)
        + "\n\nSafe candidate exercises (choose only from these):\n"
        + "\n".join(catalog_lines)
        + "\n\nDesign a workout for this member as JSON."
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    # Ask providers that support it (e.g. OpenAI) for a strict JSON object; providers that
    # ignore unknown kwargs (or the test fake) are unaffected. The parser still tolerates
    # fenced/prose output as a fallback.
    completion = state["provider"].chat(messages, response_format={"type": "json_object"})
    return {"messages": messages, "completion": completion}


def _extract_json_object(completion: str) -> str:
    """Return the JSON object embedded in a model completion.

    Real chat models often wrap JSON in a ```json fenced block or surround it with prose. This
    strips a leading/trailing code fence and, failing that, falls back to the substring between
    the first ``{`` and the last ``}`` so a bare ``json.loads`` of the result succeeds.
    """
    text = completion.strip()
    if text.startswith("```"):
        # Drop the opening fence line (``` or ```json) and any trailing fence.
        text = text.split("\n", 1)[-1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -len("```")]
        text = text.strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    return text


def _parse_exercises(completion: str) -> tuple[str, list[PlannedExercise]]:
    """Parse a model completion into a summary and a list of planned exercises.

    Defensive by design: a live model may return prose, fenced JSON, truncated JSON or items
    missing an ``exercise_id``. Any parse failure degrades to an empty exercise list (the safety
    invariant is enforced downstream regardless), and malformed items are skipped rather than
    raising. Tolerates a missing ``notes`` field and a missing/blank ``summary``.
    """
    try:
        data = json.loads(_extract_json_object(completion))
    except (ValueError, TypeError):
        return "Personalized workout plan.", []
    if not isinstance(data, dict):
        return "Personalized workout plan.", []

    summary = str(data.get("summary") or "Personalized workout plan.")
    parsed: list[PlannedExercise] = []
    for item in data.get("exercises", []):
        if not isinstance(item, dict) or not item.get("exercise_id"):
            continue
        try:
            parsed.append(
                PlannedExercise(
                    exercise_id=str(item["exercise_id"]),
                    name=str(item.get("name") or item["exercise_id"]),
                    sets=int(item.get("sets", 0)),
                    reps=int(item.get("reps", 0)),
                    notes=item.get("notes"),
                )
            )
        except (ValueError, TypeError):
            continue
    return summary, parsed


def _postvalidate_node(state: _WorkoutState) -> _WorkoutState:
    """Parse the completion, strip contraindicated picks and build the final plan."""
    bundle = state["bundle"]
    summary, parsed = _parse_exercises(state["completion"])
    kept, removed_ids = filter_contraindicated(parsed, bundle.contraindications)

    safety_flags = [
        f"Removed contraindicated exercise '{removed}' from the plan; it is unsafe for this "
        f"member's active injuries."
        for removed in removed_ids
    ]

    # Drop any exercise the model invented that was not in the safe candidate catalog it was
    # offered — the plan may only prescribe real, vetted exercises.
    valid_ids = {candidate["id"] for candidate in state["candidates"]}
    vetted: list[PlannedExercise] = []
    for exercise in kept:
        if exercise.exercise_id in valid_ids:
            vetted.append(exercise)
        else:
            safety_flags.append(
                f"Dropped unrecognized exercise '{exercise.exercise_id}' that was not among the "
                f"vetted candidates offered to the model."
            )
    kept = vetted

    # Fold both the post-validation removals and the pre-filtered contraindications into a
    # single de-duplicated, order-preserving disclosure of everything excluded for safety.
    excluded: list[str] = []
    seen: set[str] = set()
    for ex_id in [*removed_ids, *bundle.contraindications]:
        if ex_id not in seen:
            seen.add(ex_id)
            excluded.append(ex_id)

    plan = WorkoutPlan(
        member_id=state["member_id"],
        summary=summary,
        exercises=kept,
        safety_flags=safety_flags,
        excluded_contraindicated=excluded,
    )
    return {"plan": plan}


def _build_graph() -> object:
    """Build and compile the LangGraph workout-generation pipeline."""
    graph = StateGraph(_WorkoutState)
    graph.add_node("retrieve", _retrieve_node)
    graph.add_node("prefilter", _prefilter_node)
    graph.add_node("prompt", _prompt_node)
    graph.add_node("postvalidate", _postvalidate_node)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "prefilter")
    graph.add_edge("prefilter", "prompt")
    graph.add_edge("prompt", "postvalidate")
    graph.add_edge("postvalidate", END)
    return graph.compile()


def generate_workout(
    client: Neo4jClient,
    provider: LLMProvider,
    member_id: str,
    *,
    query: str = DEFAULT_QUERY,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    k: int = DEFAULT_K,
) -> WorkoutPlan:
    """Generate an injury-safe :class:`WorkoutPlan` for ``member_id``.

    Runs the LangGraph pipeline: retrieve the member's GraphRAG context, pre-filter
    contraindicated exercises out of the candidate catalog, prompt ``provider`` for a workout,
    then post-validate the model's output against the contraindication set. The returned plan is
    guaranteed to contain no exercise unsafe for the member's injuries.
    """
    app = _build_graph()
    initial: _WorkoutState = {
        "client": client,
        "provider": provider,
        "member_id": member_id,
        "query": query,
        "token_budget": token_budget,
        "k": k,
    }
    final_state: _WorkoutState = app.invoke(initial)  # type: ignore[attr-defined]
    return final_state["plan"]
