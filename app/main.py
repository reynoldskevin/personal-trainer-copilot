"""FastAPI application entrypoint for the Knowledge Graph Coaching Platform."""
from __future__ import annotations

from fastapi import FastAPI

from app.graph.health import check_neo4j

app = FastAPI(title="Knowledge Graph Coaching Platform")


@app.get("/health")
def health() -> dict[str, object]:
    """Liveness/readiness probe. Reports Neo4j connectivity without requiring it."""
    return {"status": "ok", "neo4j": check_neo4j()}
