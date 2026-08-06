"""Ticket 017 — Token/context budgeting + prompt efficiency.

Contract:
- `app.generation.budget`:
  - `truncate_to_budget(items, budget) -> (kept, tokens)` — strict rank-prefix truncation: keeps
    the highest-ranked items in order while the running token estimate stays within `budget`, and
    STOPS at the first item that would overflow (so `kept` is always a prefix of `items`). Never
    exceeds the budget.
  - `resolve_budget(explicit, settings) -> int` — the explicit budget when given, else the
    environment-configured `settings.context_token_budget`.
  - `count_prompt_tokens(messages) -> int` — estimated prompt tokens across message contents.
  - `RESPONSE_FORMAT` — the shared structured-output request that minimizes output tokens.
- `app.config.Settings.context_token_budget: int` — env-configurable, default 2000.
- `app.generation.workout`: `build_workout_messages(context_lines, candidate_lines)` is pure and
  measurable; `WORKOUT_PROMPT_TOKEN_BUDGET` guards prompt-assembly bloat.

Pure-data tests always run. One integration test needs the local Neo4j and skips if it is down.
"""
import os
from types import SimpleNamespace

import pytest

from app.generation import budget, workout
from app.llm.provider import LLMProvider

# Deterministic 15-dim bag-of-words embedder — matches the dimensionality the other integration
# tests seed into the shared vector index (14 vocab words + a bias term).
_VOCAB = [
    "shoulder", "overhead", "press", "pain", "rehab", "deadlift", "squat", "strong",
    "core", "back", "hip", "stability", "brace", "tight",
]


class FakeEmbedProvider(LLMProvider):
    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        return ""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(t.lower().count(w)) for w in _VOCAB] + [1.0] for t in texts]


# --------------------------------------------------------------------------- truncate_to_budget

def test_truncate_keeps_highest_ranked_prefix_within_budget():
    items = ["aaaa", "bbbb", "cccc"]  # each 4 chars -> 1 token
    kept, tokens = budget.truncate_to_budget(items, 2)
    assert kept == ["aaaa", "bbbb"]  # highest-ranked prefix
    assert tokens <= 2


def test_truncate_stops_at_first_overflow_not_greedy():
    # A big second item must halt truncation even though a small third item would fit — the kept
    # set is a strict prefix by rank, never a greedy "skip the big one and grab the small one".
    items = ["short", "X" * 400, "tiny"]
    kept, tokens = budget.truncate_to_budget(items, 20)
    assert kept == ["short"], f"expected strict rank prefix, got {kept}"
    assert "tiny" not in kept
    assert tokens <= 20


def test_truncate_never_exceeds_budget_and_tokens_match_kept():
    items = ["a" * 40, "b" * 40, "c" * 40]  # 10 tokens each
    kept, tokens = budget.truncate_to_budget(items, 25)
    assert tokens <= 25
    assert tokens == sum(budget.estimate_tokens(i) for i in kept)


def test_truncate_empty_and_zero_budget():
    assert budget.truncate_to_budget([], 100) == ([], 0)
    assert budget.truncate_to_budget(["anything"], 0) == ([], 0)


# --------------------------------------------------------------------------- resolve_budget

def test_resolve_budget_prefers_explicit():
    settings = SimpleNamespace(context_token_budget=777)
    assert budget.resolve_budget(1234, settings) == 1234


def test_resolve_budget_falls_back_to_settings():
    settings = SimpleNamespace(context_token_budget=777)
    assert budget.resolve_budget(None, settings) == 777


def test_settings_exposes_configurable_context_budget():
    from app.config import get_settings

    settings = get_settings()
    assert isinstance(settings.context_token_budget, int)
    assert settings.context_token_budget == 2000  # documented default


# --------------------------------------------------------------------------- prompt efficiency

def test_response_format_requests_a_json_object():
    assert budget.RESPONSE_FORMAT == {"type": "json_object"}


def test_count_prompt_tokens_sums_message_contents():
    messages = [
        {"role": "system", "content": "x" * 40},
        {"role": "user", "content": "y" * 40},
    ]
    assert budget.count_prompt_tokens(messages) == sum(
        budget.estimate_tokens(m["content"]) for m in messages
    )


def test_build_workout_messages_is_pure_and_json_structured():
    messages = workout.build_workout_messages(
        ["Member: Ava.", "Active injury: rotator cuff."],
        ["- push_up: Push-up", "- barbell_curl: Barbell curl"],
    )
    assert [m["role"] for m in messages] == ["system", "user"]
    # The system prompt must request a JSON object so output tokens stay minimal + parseable.
    assert "json" in messages[0]["content"].lower()
    # The safe candidates and context both make it into the assembled user turn.
    assert "push_up" in messages[1]["content"]
    assert "Active injury" in messages[1]["content"]


def test_workout_prompt_assembly_stays_within_regression_budget():
    # Regression guard: a representative workout prompt must not balloon past the pinned budget.
    context_lines = [f"Fact number {i} about the member's training history." for i in range(12)]
    candidate_lines = [f"- exercise_{i}: Exercise {i}" for i in range(30)]
    messages = workout.build_workout_messages(context_lines, candidate_lines)
    assert budget.count_prompt_tokens(messages) <= workout.WORKOUT_PROMPT_TOKEN_BUDGET


# --------------------------------------------------------------------------- integration (Neo4j)

@pytest.fixture
def client():
    from app.graph import schema
    from app.graph.client import Neo4jClient
    from app.ingestion import members, ontology
    from app.retrieval import embeddings

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
    embeddings.embed_and_index(c, FakeEmbedProvider())
    yield c
    c.close()


def test_tight_budget_truncates_context_but_never_drops_contraindications(client):
    from app.retrieval import service

    tight = service.retrieve(client, FakeEmbedProvider(), "member_ava", "shoulder", token_budget=10)
    # Context obeys the tight budget...
    assert tight.token_estimate <= 10
    assert tight.token_budget == 10
    # ...but contraindications are safety data and are always returned in full.
    assert tight.contraindications == sorted(["bench_press", "overhead_press"])
