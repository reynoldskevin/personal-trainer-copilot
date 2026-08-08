"""Ticket 025 — Streaming chat responses (SSE).

Contract:
- `app.llm.provider.LLMProvider.chat_stream(messages, **kwargs) -> Iterator[str]` — a NON-abstract
  method with a safe default (yield the full `chat()` result as one chunk), so existing providers
  and test fakes keep working unchanged; real providers override to yield token deltas.
- `app.generation.chat.answer_question_stream(client, provider, member_id, message, *,
  token_budget=..., k=...) -> Iterator[ChatStreamEvent]` — emits a `context` event, then `token`
  events whose deltas concatenate to the full answer, then a `done` event with the full answer.
  It builds the SAME prompt as `answer_question` (contraindications surfaced, inference-permitting
  system prompt) so streamed answers have identical grounding/safety.
- `app.generation.chat.ChatContextEvent | ChatTokenEvent | ChatDoneEvent` — typed SSE events.
- `POST /chat/stream` -> `text/event-stream` of `data: <json>\n\n` events (422 on missing fields).

Pure tests always run. Integration tests need the local Neo4j and skip if it is down.
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


class _PlainProvider(LLMProvider):
    """Implements only the required abstract methods — inherits the default `chat_stream`."""

    def __init__(self, answer: str = "one chunk answer") -> None:
        self._answer = answer

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        return self._answer

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_embed_text(t) for t in texts]


class _StreamingProvider(LLMProvider):
    """Records the messages it was handed and streams a canned answer in several chunks."""

    def __init__(self, chunks: list[str] | None = None) -> None:
        self.chunks = chunks or ["Yes, ", "she ", "can squat."]
        self.last_messages: list[dict[str, str]] | None = None

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        self.last_messages = messages
        return "".join(self.chunks)

    def chat_stream(self, messages: list[dict[str, str]], **kwargs: object):
        self.last_messages = messages
        for chunk in self.chunks:
            yield chunk

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_embed_text(t) for t in texts]


# --------------------------------------------------------------------------- pure (no Neo4j)

def test_default_chat_stream_yields_full_completion_as_one_chunk():
    provider = _PlainProvider("the whole answer")
    chunks = list(provider.chat_stream([{"role": "user", "content": "hi"}]))
    assert chunks == ["the whole answer"], "default chat_stream must yield the full completion once"


def test_stream_event_types_are_typed_and_discriminated():
    ctx = chat.ChatContextEvent(member_id="m", message="q", context_used=["a fact"])
    tok = chat.ChatTokenEvent(delta="Yes")
    done = chat.ChatDoneEvent(answer="Yes, she can.")
    assert ctx.type == "context"
    assert tok.type == "token"
    assert done.type == "done"
    # Round-trips through JSON (as the SSE endpoint serializes them).
    assert json.loads(ctx.model_dump_json())["context_used"] == ["a fact"]


# --------------------------------------------------------------------------- integration (Neo4j)

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
    embeddings.embed_and_index(c, _StreamingProvider())
    yield c
    c.close()


def test_stream_emits_context_then_tokens_then_done(client):
    provider = _StreamingProvider(["Yes, ", "she ", "can squat."])
    events = list(
        chat.answer_question_stream(client, provider, "member_ava", "Can Ava squat?")
    )
    assert len(events) >= 3

    first, last = events[0], events[-1]
    assert isinstance(first, chat.ChatContextEvent)
    assert first.member_id == "member_ava"
    assert first.context_used, "context event must carry the retrieved context"

    tokens = [e for e in events if isinstance(e, chat.ChatTokenEvent)]
    assert tokens, "must emit token events"
    streamed = "".join(t.delta for t in tokens)
    assert streamed == "Yes, she can squat."

    assert isinstance(last, chat.ChatDoneEvent)
    assert last.answer == "Yes, she can squat.", "done event carries the full reconstructed answer"


def test_streamed_prompt_matches_nonstream_safety_and_grounding(client):
    # The streamed path must ground/guard identically to POST /chat: contraindications surfaced,
    # inference-permitting system prompt. Ava (rotator-cuff) => overhead/bench press contraindicated.
    provider = _StreamingProvider()
    list(chat.answer_question_stream(client, provider, "member_ava", "Can Ava do a bodyweight squat?"))
    assert provider.last_messages is not None
    blob = json.dumps(provider.last_messages).lower()
    assert "contraindicat" in blob
    assert "overhead press" in blob and "bench press" in blob
    system = " ".join(
        m["content"] for m in provider.last_messages if m.get("role") == "system"
    ).lower()
    assert "infer" in system or "reason" in system
    assert "draft" in system and ("client" in system or "member" in system)


def _sse_events(body: str) -> list[dict]:
    """Parse an SSE body into the list of JSON payloads carried on `data:` lines."""
    out: list[dict] = []
    for block in body.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                out.append(json.loads(line[len("data:"):].strip()))
    return out


def test_chat_stream_endpoint_streams_sse(client):
    app.dependency_overrides[deps.get_neo4j_client] = lambda: client
    app.dependency_overrides[deps.get_llm_provider] = lambda: _StreamingProvider(
        ["No, ", "avoid ", "overhead pressing."]
    )
    try:
        api = TestClient(app)
        r = api.post("/chat/stream", json={"member_id": "member_ava", "message": "Overhead ok?"})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(r.text)
        types = [e["type"] for e in events]
        assert types[0] == "context"
        assert "token" in types
        assert types[-1] == "done"
        # The done event reconstructs the streamed answer.
        answer = next(e["answer"] for e in events if e["type"] == "done")
        assert answer == "No, avoid overhead pressing."
    finally:
        app.dependency_overrides.clear()


def test_chat_stream_endpoint_missing_message_returns_422(client):
    app.dependency_overrides[deps.get_neo4j_client] = lambda: client
    app.dependency_overrides[deps.get_llm_provider] = lambda: _StreamingProvider()
    try:
        api = TestClient(app)
        r = api.post("/chat/stream", json={"member_id": "member_ava"})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()
