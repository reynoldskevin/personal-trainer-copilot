"""Ticket 014 — Chat endpoint (context-only).

Contract:
- `app.generation.chat.ChatAnswer` — Pydantic model with `member_id`, `message`, `answer`,
  `context_used: list[str]`.
- `app.generation.chat.answer_question(client, provider, member_id, message, *, token_budget=...,
  k=...) -> ChatAnswer` — retrieves the member's GraphRAG context and asks the model to answer the
  COACH about the member, grounded ONLY in that context, and explicitly must NOT draft a
  client-facing reply. Returns the grounded answer plus the context it used.
- `app.api.schemas.ChatRequest(member_id: str, message: str)`.
- `POST /chat` -> `ChatAnswer` (422 on missing fields; typed + OpenAPI).

Pure-data tests always run. Integration tests need the local Neo4j and skip if it is down.
"""
import json
import os

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.generation import chat
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
    """Records the messages it was handed and returns a canned grounded answer."""

    def __init__(
        self, answer: str = "Based on her context, Ava is rehabbing a shoulder injury."
    ) -> None:
        self._answer = answer
        self.last_messages: list[dict[str, str]] | None = None

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        self.last_messages = messages
        return self._answer

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_embed_text(t) for t in texts]


# ----------------------- pure-data (no Neo4j) -----------------------

def test_chat_answer_is_a_pydantic_model():
    ans = chat.ChatAnswer(
        member_id="m", message="how are they doing?", answer="fine", context_used=["a fact"]
    )
    dumped = ans.model_dump()
    assert dumped["member_id"] == "m"
    assert dumped["answer"] == "fine"
    assert dumped["context_used"] == ["a fact"]


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


def test_answer_question_grounds_in_member_context(client):
    provider = FakeProvider()
    ans = chat.answer_question(client, provider, "member_ava", "How is her shoulder tracking?")
    assert isinstance(ans, chat.ChatAnswer)
    assert ans.member_id == "member_ava"
    assert ans.answer, "expected a non-empty answer"
    # The retrieved member context is surfaced to the model and reported back.
    assert ans.context_used, "expected the answer to report the context it used"
    prompt_blob = json.dumps(provider.last_messages).lower()
    assert "rotator cuff" in prompt_blob, "member context must be grounded into the prompt"


def test_answer_question_prompt_is_context_only_not_client_drafting(client):
    provider = FakeProvider()
    chat.answer_question(client, provider, "member_ava", "Should we deload next week?")
    assert provider.last_messages is not None
    system = " ".join(
        m["content"] for m in provider.last_messages if m.get("role") == "system"
    ).lower()
    # The assistant answers the COACH about the member...
    assert "coach" in system
    # ...and is explicitly forbidden from drafting a client/member-facing message.
    assert "draft" in system
    assert ("do not" in system) or ("must not" in system) or ("never" in system)
    assert ("client" in system) or ("member" in system)


def test_chat_endpoint_returns_grounded_answer(client):
    app.dependency_overrides[deps.get_neo4j_client] = lambda: client
    app.dependency_overrides[deps.get_llm_provider] = lambda: FakeProvider()
    try:
        api = TestClient(app)
        r = api.post("/chat", json={"member_id": "member_ava", "message": "How is she doing?"})
        assert r.status_code == 200
        body = r.json()
        assert body["member_id"] == "member_ava"
        assert body["answer"]
        assert isinstance(body["context_used"], list) and body["context_used"]
    finally:
        app.dependency_overrides.clear()


def test_chat_endpoint_missing_message_returns_422(client):
    app.dependency_overrides[deps.get_neo4j_client] = lambda: client
    app.dependency_overrides[deps.get_llm_provider] = lambda: FakeProvider()
    try:
        api = TestClient(app)
        r = api.post("/chat", json={"member_id": "member_ava"})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_openapi_documents_chat(client):
    app.dependency_overrides[deps.get_neo4j_client] = lambda: client
    app.dependency_overrides[deps.get_llm_provider] = lambda: FakeProvider()
    try:
        api = TestClient(app)
        paths = api.get("/openapi.json").json()["paths"]
        assert "/chat" in paths
        assert "post" in paths["/chat"]
    finally:
        app.dependency_overrides.clear()
