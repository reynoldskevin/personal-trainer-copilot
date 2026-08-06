"""Ticket 016 — Observability: request traces (latency + tokens) + correlation ids.

Contract (module `app.observability.tracing`):
- Correlation ids: `new_correlation_id() -> str`, `get_correlation_id() -> str | None`,
  and a `correlation_scope(cid=None)` context manager that sets the id for its block and
  restores the previous one on exit.
- Tracers: a `Tracer` base exposing `.trace(name, **meta)` and `.span(name, **meta)` context
  managers, each yielding a `Span` with `.name`, `.metadata`, `.duration_ms`, `.correlation_id`,
  `.children`, and a `.set(**meta)` mutator. A root-level entry is *recorded*; a span opened while
  another is active nests under it as a child.
- `RecordingTracer` records roots into `.traces` and exposes `.all_spans()` / `.find(name)`.
- `get_tracer()/set_tracer()/reset_tracer()` manage the process-wide tracer; the default tracer
  is no-op-safe and needs NO `langfuse` import. `configure_from_settings(settings)` selects a
  LangFuse-backed tracer only when `langfuse` is importable + configured, else a structured-log
  tracer.
- Token helpers: `estimate_tokens(text)` and `token_usage(messages, completion)`.

Pure-data tests always run. Integration tests need the local Neo4j and skip if it is down.
"""
import json
import os

import pytest

from app.observability import tracing

# --------------------------------------------------------------------------- fakes

_VOCAB = [
    "shoulder", "overhead", "press", "pain", "rehab", "deadlift", "squat", "strong",
    "core", "back", "hip", "stability", "brace", "tight",
]


def _embed_text(text: str) -> list[float]:
    low = text.lower()
    return [float(low.count(word)) for word in _VOCAB] + [1.0]


class FakeProvider:
    """Minimal LLMProvider double: canned chat completion + deterministic embeddings."""

    def __init__(self, chat_text: str) -> None:
        self._chat_text = chat_text

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        return self._chat_text

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


@pytest.fixture(autouse=True)
def _fresh_tracer():
    """Each test starts from the default tracer and restores it afterward."""
    tracing.reset_tracer()
    yield
    tracing.reset_tracer()


# --------------------------------------------------------------------------- correlation ids

def test_new_correlation_id_is_unique_nonempty():
    a = tracing.new_correlation_id()
    b = tracing.new_correlation_id()
    assert isinstance(a, str) and a
    assert a != b


def test_correlation_scope_sets_and_restores():
    assert tracing.get_correlation_id() is None
    with tracing.correlation_scope("cid-outer") as cid:
        assert cid == "cid-outer"
        assert tracing.get_correlation_id() == "cid-outer"
        with tracing.correlation_scope("cid-inner"):
            assert tracing.get_correlation_id() == "cid-inner"
        # inner scope restored the outer id
        assert tracing.get_correlation_id() == "cid-outer"
    # outer scope restored the original (None)
    assert tracing.get_correlation_id() is None


def test_correlation_scope_generates_id_when_none_given():
    with tracing.correlation_scope() as cid:
        assert isinstance(cid, str) and cid
        assert tracing.get_correlation_id() == cid


# --------------------------------------------------------------------------- tracer core

def test_recording_tracer_records_trace_with_latency_and_metadata():
    tracer = tracing.RecordingTracer()
    with tracer.trace("generation.workout", prompt_version="workout-v1") as span:
        span.set(total_tokens=42)
    assert len(tracer.traces) == 1
    root = tracer.traces[0]
    assert root.name == "generation.workout"
    assert root.duration_ms is not None and root.duration_ms >= 0
    assert root.metadata["prompt_version"] == "workout-v1"
    assert root.metadata["total_tokens"] == 42


def test_spans_nest_under_the_active_trace():
    tracer = tracing.RecordingTracer()
    with tracer.trace("generation.workout") as root:
        with tracer.span("retrieval") as retrieval:
            with tracer.span("retrieval.vector_search"):
                pass
        assert root is not None
    # only the root is a top-level record
    assert len(tracer.traces) == 1
    root = tracer.traces[0]
    child_names = [c.name for c in root.children]
    assert "retrieval" in child_names
    retrieval = next(c for c in root.children if c.name == "retrieval")
    assert any(c.name == "retrieval.vector_search" for c in retrieval.children)
    # all_spans() flattens the whole tree
    all_names = [s.name for s in tracer.all_spans()]
    assert {"generation.workout", "retrieval", "retrieval.vector_search"} <= set(all_names)


def test_span_opened_without_a_parent_is_a_root_record():
    tracer = tracing.RecordingTracer()
    with tracer.span("retrieval"):
        pass
    assert [t.name for t in tracer.traces] == ["retrieval"]


def test_recorded_spans_capture_the_active_correlation_id():
    tracer = tracing.RecordingTracer()
    with tracing.correlation_scope("cid-xyz"):
        with tracer.trace("generation.workout"):
            with tracer.span("retrieval"):
                pass
    for span in tracer.all_spans():
        assert span.correlation_id == "cid-xyz", f"{span.name} lost the correlation id"


def test_find_returns_spans_by_name():
    tracer = tracing.RecordingTracer()
    with tracer.trace("generation.workout"):
        with tracer.span("retrieval"):
            pass
    assert [s.name for s in tracer.find("retrieval")] == ["retrieval"]
    assert tracer.find("nope") == []


# --------------------------------------------------------------------------- tracer registry

def test_default_tracer_is_noop_safe_without_langfuse():
    tracing.reset_tracer()
    tracer = tracing.get_tracer()
    assert isinstance(tracer, tracing.Tracer)
    assert type(tracer).__name__ != "LangfuseTracer"
    # Using the default tracer must never raise, even with metadata + nesting.
    with tracer.trace("x", a=1) as span:
        span.set(b=2)
        with tracer.span("y"):
            pass


def test_set_and_reset_tracer():
    recording = tracing.RecordingTracer()
    tracing.set_tracer(recording)
    assert tracing.get_tracer() is recording
    tracing.reset_tracer()
    assert tracing.get_tracer() is not recording


def test_configure_from_settings_returns_non_langfuse_when_unavailable():
    from app.config import get_settings

    tracer = tracing.configure_from_settings(get_settings())
    assert isinstance(tracer, tracing.Tracer)
    # langfuse is not a declared dependency, so CI/tests must not get a LangfuseTracer.
    assert type(tracer).__name__ != "LangfuseTracer"


# --------------------------------------------------------------------------- token helpers

def test_estimate_tokens_monotonic_and_zero_for_empty():
    assert tracing.estimate_tokens("") == 0
    assert tracing.estimate_tokens("a" * 8) >= tracing.estimate_tokens("a" * 4)


def test_token_usage_splits_prompt_and_completion():
    messages = [
        {"role": "system", "content": "x" * 40},
        {"role": "user", "content": "y" * 40},
    ]
    usage = tracing.token_usage(messages, "z" * 40)
    assert usage["prompt_tokens"] > 0
    assert usage["completion_tokens"] > 0
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


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
    embeddings.embed_and_index(c, FakeProvider(_plan_json([])))
    yield c
    c.close()


def test_generation_emits_trace_with_latency_tokens_and_prompt_version(client):
    from app.generation import workout

    recording = tracing.RecordingTracer()
    tracing.set_tracer(recording)
    with tracing.correlation_scope("req-1"):
        workout.generate_workout(client, FakeProvider(_plan_json(["push_up"])), "member_ava")

    gen_traces = recording.find("generation.workout")
    assert gen_traces, "generation must emit a 'generation.workout' trace"
    trace = gen_traces[0]
    # latency
    assert trace.duration_ms is not None and trace.duration_ms >= 0
    # token counts
    assert int(trace.metadata["total_tokens"]) > 0
    assert "prompt_tokens" in trace.metadata
    assert "completion_tokens" in trace.metadata
    # prompt version, pinned to the module's declared version
    assert trace.metadata["prompt_version"] == workout.PROMPT_VERSION
    # correlation id propagated onto the trace
    assert trace.correlation_id == "req-1"


def test_retrieval_steps_are_traced_as_spans(client):
    from app.retrieval import service

    recording = tracing.RecordingTracer()
    tracing.set_tracer(recording)
    service.retrieve(client, FakeProvider(_plan_json([])), "member_ava", "shoulder rehab")

    span_names = [s.name for s in recording.all_spans()]
    assert any(name == "retrieval" for name in span_names), "expected a top-level retrieval span"
    # at least one finer-grained retrieval sub-step is recorded as a span
    assert any(
        name.startswith("retrieval.") for name in span_names
    ), f"expected retrieval sub-step spans, got {span_names}"
