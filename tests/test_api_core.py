"""Ticket 009 — FastAPI endpoints: members, retrieve, generate/workout.

Contract:
- `app/api/deps.py` exposes `get_neo4j_client` and `get_llm_provider` FastAPI dependencies,
  overridable in tests via `app.dependency_overrides`.
- The app (`app.main.app`) serves, with typed Pydantic request/response models + OpenAPI:
  - `GET  /members`            -> list of member summaries
  - `GET  /members/{id}`       -> one member detail (404 if unknown)
  - `POST /retrieve`           -> a retrieval ContextBundle (vector + graph)
  - `POST /generate/workout`   -> a WorkoutPlan with safety flags
- Validation errors return 422.

These are integration tests (they drive the real service/generation stack against the live
Neo4j) and skip cleanly if Neo4j is unavailable.
"""
import json
import os

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.graph import schema
from app.graph.client import Neo4jClient
from app.ingestion import members, ontology
from app.llm.provider import LLMProvider
from app.main import app

_VOCAB = [
    "shoulder", "overhead", "press", "pain", "rehab", "deadlift", "squat", "strong",
    "core", "back", "hip", "stability", "brace", "tight",
]


def _embed_text(text: str) -> list[float]:
    low = text.lower()
    return [float(low.count(word)) for word in _VOCAB] + [1.0]


class FakeProvider(LLMProvider):
    """Deterministic embedder; chat returns a plan that includes an UNSAFE pick for Ava."""

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        return json.dumps(
            {
                "summary": "Session",
                "exercises": [
                    {"exercise_id": "push_up", "name": "Push-up", "sets": 3, "reps": 10},
                    {"exercise_id": "overhead_press", "name": "OHP", "sets": 3, "reps": 8},
                ],
            }
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_embed_text(t) for t in texts]


@pytest.fixture
def api_client():
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

    app.dependency_overrides[deps.get_neo4j_client] = lambda: c
    app.dependency_overrides[deps.get_llm_provider] = lambda: FakeProvider()
    yield TestClient(app)
    app.dependency_overrides.clear()
    c.close()


def test_list_members(api_client):
    r = api_client.get("/members")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list) and len(body) >= 3
    by_id = {m["id"]: m for m in body}
    assert "member_ava" in by_id
    assert "name" in by_id["member_ava"]
    assert isinstance(by_id["member_ava"]["injuries"], list)


def test_get_member_detail(api_client):
    r = api_client.get("/members/member_ava")
    assert r.status_code == 200
    detail = r.json()
    assert detail["id"] == "member_ava"
    assert detail["name"]
    assert any("rotator cuff" in inj.lower() for inj in detail["injuries"])
    assert isinstance(detail["goals"], list) and detail["goals"]
    assert isinstance(detail["recent_workouts"], list)


def test_get_unknown_member_returns_404(api_client):
    r = api_client.get("/members/does_not_exist")
    assert r.status_code == 404


def test_retrieve_exposes_vector_and_graph_results(api_client):
    r = api_client.post("/retrieve", json={"member_id": "member_ava", "query": "shoulder rehab"})
    assert r.status_code == 200
    bundle = r.json()
    assert bundle["member_id"] == "member_ava"
    assert bundle["contraindications"] == sorted(["bench_press", "overhead_press"])
    assert isinstance(bundle["vector_hits"], list) and bundle["vector_hits"]
    assert isinstance(bundle["subgraph_facts"], list) and bundle["subgraph_facts"]


def test_generate_workout_returns_safe_plan_with_flags(api_client):
    r = api_client.post("/generate/workout", json={"member_id": "member_ava"})
    assert r.status_code == 200
    plan = r.json()
    assert plan["member_id"] == "member_ava"
    ids = [e["exercise_id"] for e in plan["exercises"]]
    assert "overhead_press" not in ids, "API must not return a contraindicated exercise"
    assert "push_up" in ids
    assert plan["safety_flags"], "expected safety flags documenting the removal"
    assert "overhead_press" in plan["excluded_contraindicated"]


def test_generate_workout_missing_member_id_returns_422(api_client):
    r = api_client.post("/generate/workout", json={})
    assert r.status_code == 422


def test_retrieve_missing_query_returns_422(api_client):
    r = api_client.post("/retrieve", json={"member_id": "member_ava"})
    assert r.status_code == 422


def test_openapi_schema_documents_the_endpoints(api_client):
    schema_doc = api_client.get("/openapi.json").json()
    paths = schema_doc["paths"]
    assert "/members" in paths
    assert "/retrieve" in paths
    assert "/generate/workout" in paths
    assert "get" in paths["/members"]
    assert "post" in paths["/generate/workout"]
