"""Ticket 020 — Performance verification (<5s p95).

Contract (`app.observability.perf`):
- `percentile(samples, p) -> float` — nearest-rank percentile (0.0 for empty input).
- `LatencyStats` / `BenchmarkReport` — pydantic models; `summarize(samples_ms) -> LatencyStats`.
- `run_workout_benchmark(client, provider, member_ids, *, iterations) -> BenchmarkReport` — times
  end-to-end `/generate/workout` and, separately, the retrieval step, reporting p50/p95 for each.
- `DEFAULT_P95_BUDGET_MS` — the p95 budget the end-to-end latency must stay under.

The LLM is stubbed to ~zero latency so the harness measures OUR overhead (retrieval + graph +
assembly), not the provider. Pure percentile/summary tests always run; the benchmark test needs
the local Neo4j and skips if it is down.
"""
import json
import os

import pytest

from app.observability import perf

# --------------------------------------------------------------------------- percentile (pure)

def test_percentile_nearest_rank():
    samples = [float(i) for i in range(1, 101)]  # 1..100
    assert perf.percentile(samples, 50) == 50.0
    assert perf.percentile(samples, 95) == 95.0
    assert perf.percentile(samples, 100) == 100.0


def test_percentile_small_and_empty():
    assert perf.percentile([], 95) == 0.0
    assert perf.percentile([42.0], 95) == 42.0
    assert perf.percentile([10.0, 20.0, 30.0], 50) == 20.0


def test_summarize_orders_p50_le_p95():
    stats = perf.summarize([float(i) for i in range(1, 101)])
    assert stats.count == 100
    assert stats.p50_ms <= stats.p95_ms <= stats.max_ms
    assert stats.p50_ms == 50.0
    assert stats.p95_ms == 95.0


def test_summarize_empty():
    stats = perf.summarize([])
    assert stats.count == 0
    assert stats.p50_ms == 0.0
    assert stats.p95_ms == 0.0


def test_report_is_markdown_and_json_serializable():
    report = perf.BenchmarkReport(
        iterations=3,
        members=["member_ava"],
        end_to_end=perf.summarize([10.0, 20.0, 30.0]),
        retrieval=perf.summarize([1.0, 2.0, 3.0]),
    )
    md = report.to_markdown()
    assert "p95" in md.lower()
    assert "retrieval" in md.lower()
    loaded = json.loads(json.dumps(report.model_dump()))
    assert loaded["end_to_end"]["p95_ms"] == 30.0


# --------------------------------------------------------------------------- integration (Neo4j)

_VOCAB = [
    "shoulder", "overhead", "press", "pain", "rehab", "deadlift", "squat", "strong",
    "core", "back", "hip", "stability", "brace", "tight",
]


class _FastProvider:
    """~Zero-latency stub so the benchmark measures our overhead, not the provider."""

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        return json.dumps(
            {
                "summary": "bench",
                "exercises": [{"exercise_id": "push_up", "name": "Push-up", "sets": 3, "reps": 10}],
            }
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(t.lower().count(w)) for w in _VOCAB] + [1.0] for t in texts]


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
    embeddings.embed_and_index(c, _FastProvider())
    yield c
    c.close()


def test_workout_benchmark_meets_p95_budget(client):
    report = perf.run_workout_benchmark(
        client,
        _FastProvider(),
        ["member_ava", "member_ben", "member_chloe"],
        iterations=5,
    )
    # p50/p95 reported for /generate/workout...
    assert report.end_to_end.count == 15
    assert report.end_to_end.p50_ms >= 0.0
    assert report.end_to_end.p95_ms >= report.end_to_end.p50_ms
    # ...and within the budget (excluding provider latency, which is stubbed to ~0).
    assert report.end_to_end.p95_ms < perf.DEFAULT_P95_BUDGET_MS
    # Retrieval overhead is reported separately and is a component of the end-to-end time.
    assert report.retrieval.count == 15
    assert report.retrieval.p95_ms <= report.end_to_end.p95_ms + 1.0
