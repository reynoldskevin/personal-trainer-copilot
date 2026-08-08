"""Ticket 008 — Generation: WorkoutPlan + injury-safe guardrail.

Contract (module `app.generation.workout`):
- `PlannedExercise` / `WorkoutPlan` — Pydantic models. `WorkoutPlan` carries `member_id`,
  `summary`, `exercises: list[PlannedExercise]`, `safety_flags: list[str]`, and
  `excluded_contraindicated: list[str]`.
- `filter_contraindicated(exercises, contraindicated) -> (kept, removed_ids)` — pure
  post-validation: drops any planned exercise whose id is contraindicated.
- `generate_workout(client, provider, member_id, *, query=..., token_budget=..., k=...)
  -> WorkoutPlan` — a LangGraph pipeline: retrieve -> pre-filter contraindicated -> prompt ->
  `LLMProvider.chat` -> post-validate -> typed `WorkoutPlan`. The LLM is injected/mocked.

Pure-data tests always run. Integration tests need the local Neo4j and skip if it is down.
"""
import json
import os

import pytest

from app.generation import workout
from app.graph import schema
from app.graph.client import Neo4jClient
from app.ingestion import members, ontology
from app.llm.provider import LLMProvider

_VOCAB = [
    "shoulder", "overhead", "press", "pain", "rehab", "deadlift", "squat", "strong",
    "core", "back", "hip", "stability", "brace", "tight",
]


def _embed_text(text: str) -> list[float]:
    low = text.lower()
    return [float(low.count(word)) for word in _VOCAB] + [1.0]


class FakeProvider(LLMProvider):
    """Records the prompt it was handed and returns a canned JSON workout completion."""

    def __init__(self, chat_json: str) -> None:
        self._chat_json = chat_json
        self.last_messages: list[dict[str, str]] | None = None

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        self.last_messages = messages
        return self._chat_json

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_embed_text(t) for t in texts]


def _plan_json(exercise_ids: list[str]) -> str:
    return json.dumps(
        {
            "summary": "Personalized session",
            "exercises": [
                {"exercise_id": ex, "name": ex.replace("_", " "), "sets": 3, "reps": 10}
                for ex in exercise_ids
            ],
        }
    )


# ----------------------- pure-data (no Neo4j) -----------------------

def test_target_exercise_range_constants_are_sane():
    # Ticket 027: a fuller session than the model's compact default of ~3.
    lo, hi = workout.TARGET_EXERCISE_MIN, workout.TARGET_EXERCISE_MAX
    assert isinstance(lo, int) and isinstance(hi, int)
    assert lo < hi, "range must be non-empty (min strictly below max)"
    assert hi >= 5, "target session should reach at least ~5 exercises, not stay at 3"


def test_system_prompt_requests_the_target_range_and_pattern_coverage():
    # The prompt is the only lever on count (the model's output can't be unit-tested), so it must
    # carry both bounds of the target range and ask for balanced movement-pattern coverage.
    prompt = workout._SYSTEM_PROMPT
    assert str(workout.TARGET_EXERCISE_MIN) in prompt
    assert str(workout.TARGET_EXERCISE_MAX) in prompt
    low = prompt.lower()
    assert "pattern" in low, "prompt should ask for balanced movement-pattern coverage"
    # Only ever from the safe candidate list, and degrade gracefully when too few exist.
    assert "candidate" in low
    assert "fewer" in low or "as many" in low or "too few" in low, (
        "prompt must permit degrading to fewer exercises when safe candidates are scarce"
    )
    # Output contract is unchanged: still a JSON object.
    assert "json" in low


def test_build_workout_messages_carries_the_target_instruction():
    messages = workout.build_workout_messages(["Member: Ava."], ["- push_up: Push-up"])
    system = messages[0]["content"]
    assert messages[0]["role"] == "system"
    # The assembled system turn carries the target-range instruction, not just the bare schema.
    assert str(workout.TARGET_EXERCISE_MAX) in system
    assert "pattern" in system.lower()


def test_models_are_pydantic():
    plan = workout.WorkoutPlan(
        member_id="m",
        summary="s",
        exercises=[workout.PlannedExercise(exercise_id="push_up", name="Push-up", sets=3, reps=10)],
        safety_flags=[],
        excluded_contraindicated=[],
    )
    dumped = plan.model_dump()
    assert dumped["member_id"] == "m"
    assert dumped["exercises"][0]["exercise_id"] == "push_up"


def test_filter_contraindicated_removes_unsafe_exercises():
    exercises = [
        workout.PlannedExercise(exercise_id="push_up", name="Push-up", sets=3, reps=10),
        workout.PlannedExercise(exercise_id="overhead_press", name="OHP", sets=3, reps=8),
    ]
    kept, removed = workout.filter_contraindicated(exercises, ["overhead_press", "bench_press"])
    kept_ids = [e.exercise_id for e in kept]
    assert kept_ids == ["push_up"]
    assert removed == ["overhead_press"]


def test_filter_contraindicated_keeps_all_when_none_unsafe():
    exercises = [
        workout.PlannedExercise(exercise_id="push_up", name="Push-up", sets=3, reps=10),
    ]
    kept, removed = workout.filter_contraindicated(exercises, ["overhead_press"])
    assert [e.exercise_id for e in kept] == ["push_up"]
    assert removed == []


# ----------------------- integration (needs Neo4j) -----------------------

@pytest.fixture
def client():
    c = Neo4jClient(
        uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        user=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "testpassword"),
    )
    try:
        c.execute_read("RETURN 1 AS ok")
    except Exception:  # noqa: BLE001
        c.close()
        pytest.skip("Neo4j not available")
    schema.bootstrap_schema(c)
    ontology.load_ontology(c)
    members.ingest_members(c)
    from app.retrieval import embeddings
    embeddings.embed_and_index(c, FakeProvider(_plan_json([])))
    yield c
    c.close()


def test_generate_returns_schema_valid_plan(client):
    provider = FakeProvider(_plan_json(["push_up", "barbell_curl"]))
    plan = workout.generate_workout(client, provider, "member_ava")
    assert isinstance(plan, workout.WorkoutPlan)
    assert plan.member_id == "member_ava"
    assert plan.exercises
    for ex in plan.exercises:
        assert isinstance(ex, workout.PlannedExercise)


def test_prefilter_hides_contraindicated_from_the_llm(client):
    # Ava's rotator cuff tear contraindicates overhead_press + bench_press.
    provider = FakeProvider(_plan_json(["push_up"]))
    workout.generate_workout(client, provider, "member_ava")
    assert provider.last_messages is not None, "LLM should have been called"
    prompt = json.dumps(provider.last_messages).lower()
    assert "push_up" in prompt, "safe candidates should be offered to the LLM"
    assert "overhead_press" not in prompt, "contraindicated exercise leaked to the LLM"
    assert "bench_press" not in prompt, "contraindicated exercise leaked to the LLM"


def test_postvalidate_strips_injected_unsafe_pick(client):
    # The mocked LLM defies the guardrail and returns a contraindicated exercise.
    provider = FakeProvider(_plan_json(["push_up", "overhead_press"]))
    plan = workout.generate_workout(client, provider, "member_ava")
    final_ids = [e.exercise_id for e in plan.exercises]
    assert "overhead_press" not in final_ids, "post-validation must remove contraindicated picks"
    assert "push_up" in final_ids
    assert "overhead_press" in plan.excluded_contraindicated
    assert any("overhead_press" in flag for flag in plan.safety_flags)


def test_generated_plan_has_zero_contraindicated_for_injured_member(client):
    # End-to-end safety invariant: no matter what the LLM proposes, the final plan for an
    # injured member contains zero exercises unsafe for their injuries.
    provider = FakeProvider(_plan_json(["overhead_press", "bench_press", "push_up"]))
    plan = workout.generate_workout(client, provider, "member_ava")
    unsafe = set(ontology.contraindicated_exercises(client, "rotator_cuff_tear"))
    final_ids = {e.exercise_id for e in plan.exercises}
    assert final_ids.isdisjoint(unsafe), f"unsafe exercises in final plan: {final_ids & unsafe}"
