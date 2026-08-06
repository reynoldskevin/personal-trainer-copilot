"""Ticket 019 — Evals runner: execute retrieval + generation and score the dataset.

`run_evals` runs the real GraphRAG pipeline over the labeled dataset:

- **Retrieval quality** — for each retrieval case it calls :func:`app.retrieval.service.retrieve`
  and derives the set of the member's expected nodes that actually surfaced in the returned
  context (by matching each node's deterministic text signature against the retrieved facts), then
  scores precision/recall/F1 against the case's expected node ids.
- **Safety** — for each safety case it obtains the recommended exercises the system would give a
  member with that injury and confirms **none** are forbidden. Cases tied to a seed member run the
  full injury-safe :func:`app.generation.workout.generate_workout` pipeline (so an adversarial
  model that proposes contraindicated exercises is caught end-to-end); injury-only cases run the
  same post-validation guardrail (:func:`app.generation.workout.filter_contraindicated`) directly
  against the ontology's contraindication set.

Determinism comes from the injected ``provider`` (deterministic fake embeddings/completions in
tests) and from the scoring being pure — the only nondeterminism a real provider could add is in
the workout summary text, which does not affect the scored exercise ids.
"""
from __future__ import annotations

from app.generation import workout
from app.generation.workout import PlannedExercise
from app.graph.client import Neo4jClient
from app.ingestion import members, ontology
from app.llm.provider import LLMProvider
from app.retrieval import service
from evals import scoring
from evals.dataset import EvalDataset, SafetyCase, contraindications_for

# Injury id -> display name, so an expected injury node matches its "Active injury: <name>." fact.
_INJURY_NAMES: dict[str, str] = {i["id"]: i["name"] for i in ontology.INJURIES}


def _member_signatures(member_id: str) -> dict[str, str]:
    """Map each of the member's node ids to the text signature retrieval would surface for it.

    Injuries surface by name, goals by description, and time-series nodes (workouts, adherence,
    biometrics) by their unique timestamp — the same strings the subgraph facts embed — so a node
    counts as "retrieved" when its signature appears in the returned context.
    """
    signatures: dict[str, str] = {}
    for member in members.MEMBER_SEED:
        if member["id"] != member_id:
            continue
        for injury_id in member["injuries"]:
            if injury_id in _INJURY_NAMES:
                signatures[injury_id] = _INJURY_NAMES[injury_id]
        for goal in member["goals"]:
            signatures[goal["id"]] = goal["description"]
        for w in member["workouts"]:
            signatures[w["id"]] = w["timestamp"]
        for a in member["adherence"]:
            signatures[a["id"]] = a["timestamp"]
        for b in member["biometrics"]:
            signatures[b["id"]] = b["timestamp"]
    return signatures


def _surfaced_node_ids(member_id: str, context_text: str) -> set[str]:
    """Return the member node ids whose text signature appears in ``context_text``."""
    return {
        node_id
        for node_id, signature in _member_signatures(member_id).items()
        if signature and signature in context_text
    }


def _safety_recommendations(
    client: Neo4jClient, provider: LLMProvider, case: SafetyCase
) -> list[str]:
    """Return the exercise ids the system would recommend for ``case`` (post-guardrail).

    Member-tied cases run the full generation pipeline; injury-only cases run the same
    post-validation guardrail directly against the injury's ontology contraindications.
    """
    if case.member_id is not None:
        plan = workout.generate_workout(client, provider, case.member_id)
        return [exercise.exercise_id for exercise in plan.exercises]

    forbidden = contraindications_for(case.injury_id)
    proposed = [
        PlannedExercise(exercise_id=ex, name=ex, sets=1, reps=1) for ex in sorted(forbidden)
    ]
    kept, _removed = workout.filter_contraindicated(proposed, sorted(forbidden))
    return [exercise.exercise_id for exercise in kept]


def run_evals(
    client: Neo4jClient, provider: LLMProvider, dataset: EvalDataset
) -> scoring.EvalReport:
    """Run retrieval + safety evaluation over ``dataset`` and return an aggregated report."""
    retrieval_scores = []
    for rc in dataset.retrieval_cases:
        bundle = service.retrieve(client, provider, rc.member_id, rc.query)
        context_text = "\n".join([*bundle.subgraph_facts, *bundle.context_items])
        retrieved = _surfaced_node_ids(rc.member_id, context_text)
        retrieval_scores.append(
            scoring.score_retrieval(rc.id, set(rc.expected_node_ids), retrieved)
        )

    safety_scores = []
    for sc in dataset.safety_cases:
        recommended = _safety_recommendations(client, provider, sc)
        safety_scores.append(
            scoring.score_safety(sc.id, recommended, set(sc.forbidden_exercise_ids))
        )

    return scoring.EvalReport(
        version=dataset.version, retrieval=retrieval_scores, safety=safety_scores
    )
