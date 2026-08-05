"""Ticket 001 — /health contract.

The FastAPI app exposes GET /health returning 200 with a body carrying `status` and a
boolean `neo4j` connectivity flag. The endpoint must NOT fail when Neo4j is unreachable —
it reports connectivity, it does not require it.
"""
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_200_with_status_and_neo4j():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "neo4j" in body
    assert isinstance(body["neo4j"], bool)


def test_health_ok_even_when_neo4j_unreachable(monkeypatch):
    # Point Neo4j at a dead address; endpoint must still return 200 with neo4j=false.
    monkeypatch.setenv("NEO4J_URI", "bolt://127.0.0.1:1")
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["neo4j"] is False
