"""Ticket 019 — Evals harness + scoring.

Contract:
- `evals.scoring`:
  - `score_retrieval(case_id, expected: set[str], retrieved: set[str]) -> RetrievalScore`
    (precision/recall/f1 vs expected nodes).
  - `score_safety(case_id, recommended, forbidden: set[str]) -> SafetyScore`
    (passes iff no forbidden exercise appears; violations list the offenders).
  - `EvalReport` — pydantic model aggregating per-case scores, with `mean_recall()`,
    `mean_precision()`, `safety_passed()`, `total_safety_violations()`, and `to_markdown()`.
- `evals.run`:
  - `render_report(report) -> str` — human-readable markdown.
  - `write_artifact(report, path) -> None` — machine-parseable JSON artifact.
  - `main()` — CLI entry (`python -m evals.run`).
- `evals.runner.run_evals(client, provider, dataset) -> EvalReport` — executes retrieval +
  generation over the dataset and scores it (integration; needs Neo4j).

Scoring/report tests are pure + deterministic. The end-to-end run test needs Neo4j and skips
if it is down.
"""
import json
import os

import pytest

from evals import run, scoring

# --------------------------------------------------------------------------- retrieval scoring

def test_score_retrieval_perfect_match():
    s = scoring.score_retrieval("c1", {"a", "b"}, {"a", "b"})
    assert s.precision == 1.0
    assert s.recall == 1.0
    assert s.f1 == 1.0
    assert s.hits == 2


def test_score_retrieval_partial():
    # expected {a,b,c}; retrieved {a,b,x} -> hits=2, precision=2/3, recall=2/3
    s = scoring.score_retrieval("c2", {"a", "b", "c"}, {"a", "b", "x"})
    assert s.hits == 2
    assert round(s.precision, 3) == round(2 / 3, 3)
    assert round(s.recall, 3) == round(2 / 3, 3)
    assert 0.0 < s.f1 < 1.0


def test_score_retrieval_no_overlap_and_empty_retrieved():
    assert scoring.score_retrieval("c3", {"a"}, set()).recall == 0.0
    assert scoring.score_retrieval("c3", {"a"}, set()).precision == 0.0
    assert scoring.score_retrieval("c4", {"a"}, {"z"}).f1 == 0.0


# --------------------------------------------------------------------------- safety scoring

def test_score_safety_pass_when_no_forbidden():
    s = scoring.score_safety("s1", ["push_up", "row"], {"overhead_press", "bench_press"})
    assert s.passed is True
    assert s.violations == []


def test_score_safety_fail_lists_violations():
    s = scoring.score_safety("s2", ["push_up", "overhead_press"], {"overhead_press", "bench_press"})
    assert s.passed is False
    assert s.violations == ["overhead_press"]


# --------------------------------------------------------------------------- report aggregation

def _sample_report(safety_ok: bool = True) -> scoring.EvalReport:
    retrieval = [
        scoring.score_retrieval("r1", {"a", "b"}, {"a", "b"}),      # recall 1.0
        scoring.score_retrieval("r2", {"a", "b"}, {"a"}),            # recall 0.5
    ]
    recommended = ["push_up"] if safety_ok else ["push_up", "overhead_press"]
    safety = [
        scoring.score_safety("s1", recommended, {"overhead_press"}),
    ]
    return scoring.EvalReport(version="test-1", retrieval=retrieval, safety=safety)


def test_report_aggregates_and_safety_gate():
    ok = _sample_report(safety_ok=True)
    assert round(ok.mean_recall(), 3) == 0.75
    assert ok.safety_passed() is True
    assert ok.total_safety_violations() == 0

    bad = _sample_report(safety_ok=False)
    assert bad.safety_passed() is False
    assert bad.total_safety_violations() == 1


def test_report_is_human_readable_and_machine_parseable(tmp_path):
    report = _sample_report()
    md = report.to_markdown()
    assert "Retrieval" in md and "Safety" in md
    assert "recall" in md.lower()

    # Machine-parseable JSON artifact round-trips.
    artifact = tmp_path / "report.json"
    run.write_artifact(report, artifact)
    loaded = json.loads(artifact.read_text())
    assert loaded["version"] == "test-1"
    assert len(loaded["retrieval"]) == 2
    assert len(loaded["safety"]) == 1


def test_render_report_returns_markdown():
    assert isinstance(run.render_report(_sample_report()), str)


def test_run_module_exposes_main():
    assert callable(run.main)


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
    embeddings.embed_and_index(c, _AdversarialProvider())
    yield c
    c.close()


_VOCAB = [
    "shoulder", "overhead", "press", "pain", "rehab", "deadlift", "squat", "strong",
    "core", "back", "hip", "stability", "brace", "tight",
]


class _AdversarialProvider:
    """Deterministic embeddings + a chat completion that tries to prescribe EVERY exercise —
    including contraindicated ones — so a passing safety score proves the guardrail (not luck)."""

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        # Recommend two exercises contraindicated for the seed injuries, plus one safe exercise.
        return json.dumps(
            {
                "summary": "adversarial",
                "exercises": [
                    {"exercise_id": "overhead_press", "name": "OHP", "sets": 3, "reps": 5},
                    {"exercise_id": "conventional_deadlift", "name": "DL", "sets": 3, "reps": 5},
                    {"exercise_id": "push_up", "name": "Push-up", "sets": 3, "reps": 10},
                ],
            }
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(t.lower().count(w)) for w in _VOCAB] + [1.0] for t in texts]


def test_run_evals_scores_dataset_and_safety_holds(client):
    from evals import dataset, runner

    ds = dataset.load_dataset()
    report = runner.run_evals(client, _AdversarialProvider(), ds)

    assert isinstance(report, scoring.EvalReport)
    assert report.retrieval, "expected retrieval scores"
    assert report.safety, "expected safety scores"
    # Even though the provider adversarially proposes contraindicated exercises, the guardrail
    # must strip them — the safety eval passes with zero violations.
    assert report.safety_passed() is True
    assert report.total_safety_violations() == 0
    # Retrieval surfaces at least some expected member context.
    assert report.mean_recall() > 0.0
