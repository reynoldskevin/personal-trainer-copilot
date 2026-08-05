"""Ticket 012 — InsightReport + /generate/insight.

Contract:
- `app.generation.insight.RiskFlag(kind, severity, detail)` — Pydantic.
- `app.generation.insight.InsightReport(member_id, summary, risk_flags, personalization_notes,
  trends, excluded_contraindicated, safety_flags)` — Pydantic.
- `app.generation.insight.risk_flags_from_trends(trends) -> list[RiskFlag]` — DETERMINISTIC risk
  derivation from a `TrendSummary`, independent of the LLM (declining adherence -> an
  `kind="adherence"` flag).
- `app.generation.insight.generate_insight(client, provider, member_id, *, window=...,
  token_budget=..., k=...) -> InsightReport` — windowed retrieval (trends attached) + LLM insight,
  guardrailed so no contraindicated exercise is ever recommended.
- `app.api.schemas.GenerateInsightRequest(member_id, window_weeks=None)`.
- `POST /generate/insight` -> `InsightReport` (422 on missing member_id; typed + OpenAPI).

Pure-data tests always run. Integration tests need the local Neo4j and skip if it is down.
"""
import json
import os

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.generation import insight
from app.graph import schema
from app.graph.client import Neo4jClient
from app.ingestion import members, ontology
from app.llm.provider import LLMProvider
from app.main import app
from app.retrieval.temporal import TrendSummary

_VOCAB = [
    "shoulder", "overhead", "press", "pain", "rehab", "deadlift", "squat", "strong",
    "core", "back", "hip", "stability", "brace", "tight",
]


def _embed_text(text: str) -> list[float]:
    low = text.lower()
    return [float(low.count(word)) for word in _VOCAB] + [1.0]


class FakeProvider(LLMProvider):
    """Returns a canned JSON insight; `recommended_exercise_ids` is parametrizable."""

    def __init__(self, recommended: list[str] | None = None) -> None:
        self._recommended = recommended if recommended is not None else []
        self.last_messages: list[dict[str, str]] | None = None

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        self.last_messages = messages
        return json.dumps(
            {
                "summary": "Ava is progressing on her shoulder rehab with steady adherence.",
                "personalization_notes": ["Keep pressing volume light this block."],
                "recommended_exercise_ids": self._recommended,
            }
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_embed_text(t) for t in texts]


def _trends(adherence: float | None) -> TrendSummary:
    return TrendSummary(
        window_weeks=4,
        adherence_percentage=adherence,
        adherence_sessions="n of m planned sessions",
        biometrics=[],
        workout_count=2,
        summary_lines=[],
    )


# ----------------------- pure-data (no Neo4j) -----------------------

def test_models_are_pydantic():
    report = insight.InsightReport(
        member_id="m",
        summary="s",
        risk_flags=[insight.RiskFlag(kind="adherence", severity="high", detail="d")],
        personalization_notes=["note"],
        trends=None,
        excluded_contraindicated=[],
        safety_flags=[],
    )
    dumped = report.model_dump()
    assert dumped["member_id"] == "m"
    assert dumped["risk_flags"][0]["kind"] == "adherence"


def test_declining_adherence_raises_a_risk_flag():
    flags = insight.risk_flags_from_trends(_trends(50.0))
    assert any(f.kind == "adherence" for f in flags), "declining adherence should flag risk"


def test_healthy_adherence_raises_no_adherence_flag():
    flags = insight.risk_flags_from_trends(_trends(90.0))
    assert not any(f.kind == "adherence" for f in flags), "healthy adherence must not flag risk"


def test_risk_flags_handle_missing_adherence_gracefully():
    # No adherence data -> no crash, no spurious adherence flag.
    flags = insight.risk_flags_from_trends(_trends(None))
    assert all(isinstance(f, insight.RiskFlag) for f in flags)


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
    embeddings.embed_and_index(c, FakeProvider())
    yield c
    c.close()


def test_generate_insight_returns_schema_valid_report_with_trends(client):
    report = insight.generate_insight(client, FakeProvider(["push_up"]), "member_ava")
    assert isinstance(report, insight.InsightReport)
    assert report.member_id == "member_ava"
    assert report.summary, "expected a non-empty insight summary"
    assert report.trends is not None, "insight must be grounded in the member's trends"


def test_generate_insight_strips_contraindicated_recommendation(client):
    # The mocked LLM recommends an exercise unsafe for Ava's rotator cuff tear.
    provider = FakeProvider(["overhead_press", "push_up"])
    report = insight.generate_insight(client, provider, "member_ava")
    assert "overhead_press" in report.excluded_contraindicated, (
        "a contraindicated recommendation must be excluded from the insight"
    )
    assert any("overhead_press" in flag for flag in report.safety_flags), (
        "excluding a contraindicated recommendation must be disclosed in safety_flags"
    )


def test_generate_insight_endpoint_returns_report(client):
    app.dependency_overrides[deps.get_neo4j_client] = lambda: client
    app.dependency_overrides[deps.get_llm_provider] = lambda: FakeProvider(["push_up"])
    try:
        api = TestClient(app)
        r = api.post("/generate/insight", json={"member_id": "member_ava"})
        assert r.status_code == 200
        body = r.json()
        assert body["member_id"] == "member_ava"
        assert body["summary"]
        assert isinstance(body["risk_flags"], list)
        assert isinstance(body["excluded_contraindicated"], list)
    finally:
        app.dependency_overrides.clear()


def test_generate_insight_missing_member_id_returns_422(client):
    app.dependency_overrides[deps.get_neo4j_client] = lambda: client
    app.dependency_overrides[deps.get_llm_provider] = lambda: FakeProvider()
    try:
        api = TestClient(app)
        r = api.post("/generate/insight", json={})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_openapi_documents_generate_insight(client):
    app.dependency_overrides[deps.get_neo4j_client] = lambda: client
    app.dependency_overrides[deps.get_llm_provider] = lambda: FakeProvider()
    try:
        api = TestClient(app)
        paths = api.get("/openapi.json").json()["paths"]
        assert "/generate/insight" in paths
        assert "post" in paths["/generate/insight"]
    finally:
        app.dependency_overrides.clear()
