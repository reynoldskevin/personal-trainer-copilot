"""Ticket 014 — Chat endpoint (context-only).

Answers a *coach's* question about a member, grounded strictly in the member's retrieved
GraphRAG context. Retrieval reuses :func:`app.retrieval.service.retrieve` so all member reads
stay member-scoped and parameterized.

The assistant is framed as a professional-to-professional aide: it answers the coach about the
member and is explicitly forbidden from drafting a client- or member-facing reply. It never
invents facts beyond the provided context.
"""
from __future__ import annotations

from collections.abc import Iterator
from time import perf_counter
from typing import Literal

from pydantic import BaseModel

from app.graph.client import Neo4jClient
from app.ingestion import ontology
from app.llm.provider import LLMProvider
from app.observability import tracing
from app.retrieval import service
from app.retrieval.service import ContextBundle

# Exercise id -> display name, so contraindications render with the SAME names the workout history
# uses (the retrieval facts render `e.name`), not raw ids — the model then reasons over one
# consistent spelling of each exercise instead of two.
_EXERCISE_NAMES: dict[str, str] = {e["id"]: e["name"] for e in ontology.EXERCISES}

# Reuse the retrieval service's defaults so chat and retrieval stay in lockstep.
DEFAULT_TOKEN_BUDGET: int = service.DEFAULT_TOKEN_BUDGET
DEFAULT_K: int = service.DEFAULT_K

# Prompt version pinned onto every emitted chat generation trace.
PROMPT_VERSION: str = "chat-v1"


class ChatAnswer(BaseModel):
    """A grounded answer to a coach's question about a member.

    ``answer`` is the model's response, grounded only in ``context_used`` — the token-bounded
    member context surfaced to the model (:attr:`ContextBundle.context_items`).
    """

    member_id: str
    message: str
    answer: str
    context_used: list[str]


_SYSTEM_PROMPT: str = (
    "You are an assistant that helps a professional fitness coach understand one of their "
    "members. Answer the coach's question about the member using the member context provided "
    "below. You MAY draw well-supported inferences from that context — the member's injuries, "
    "their contraindicated exercises, and their workout history — rather than only restating "
    "explicit facts (for example, a movement that is NOT in the contraindication list and is "
    "lighter than something the member already performs can be judged safe). But never invent "
    "unsupported facts, and never contradict the member's contraindication list; if nothing in "
    "the context supports an answer, say so plainly. You are speaking to the coach, not to the "
    "member. Do NOT draft a client-facing or member-facing message, and never write a reply "
    "addressed to the client or member — respond directly to the coach as a colleague."
)


class ChatContextEvent(BaseModel):
    """First SSE event: the retrieved context that grounds the answer (before any tokens)."""

    type: Literal["context"] = "context"
    member_id: str
    message: str
    context_used: list[str]


class ChatTokenEvent(BaseModel):
    """An incremental chunk of the streamed answer."""

    type: Literal["token"] = "token"
    delta: str


class ChatDoneEvent(BaseModel):
    """Terminal SSE event: the full reconstructed answer."""

    type: Literal["done"] = "done"
    answer: str


ChatStreamEvent = ChatContextEvent | ChatTokenEvent | ChatDoneEvent


def _build_messages(bundle: ContextBundle, message: str) -> list[dict[str, str]]:
    """Assemble the system+user chat prompt from a retrieved context ``bundle``.

    Shared by :func:`answer_question` and :func:`answer_question_stream` so the streamed and
    non-streamed paths ground and guard IDENTICALLY: the member's contraindication set is surfaced
    (by display name, or stated as none) and the inference-permitting system prompt is applied.
    """
    context_lines = bundle.context_items or bundle.subgraph_facts
    # Surface the member's contraindication set explicitly so the model can reason about safety
    # (what is forbidden vs. merely absent) instead of hedging on every movement.
    if bundle.contraindications:
        contra_names = [_EXERCISE_NAMES.get(ex, ex) for ex in bundle.contraindications]
        contra_line = (
            "Exercises contraindicated for this member's injuries (never recommend these): "
            + ", ".join(contra_names)
        )
    else:
        contra_line = "Exercises contraindicated for this member's injuries: none on record."
    user = (
        "Member context:\n"
        + "\n".join(context_lines)
        + "\n\n"
        + contra_line
        + "\n\nThe coach asks: "
        + message
        + "\n\nAnswer the coach's question, grounded in the member context above. You may draw "
        "well-supported inferences from the member's history and contraindication list; only "
        "say information is unavailable when no fact in the context supports an answer."
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def answer_question(
    client: Neo4jClient,
    provider: LLMProvider,
    member_id: str,
    message: str,
    *,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    k: int = DEFAULT_K,
) -> ChatAnswer:
    """Answer a coach's ``message`` about ``member_id``, grounded in the member's context.

    Retrieves the member's GraphRAG context bundle, assembles a system/user chat prompt that
    frames the assistant as answering the coach (never drafting a client-facing reply), calls
    :meth:`LLMProvider.chat`, and returns the grounded answer plus the context it used.
    """
    with tracing.get_tracer().trace("generation.chat", prompt_version=PROMPT_VERSION) as span:
        bundle = service.retrieve(
            client, provider, member_id, message, token_budget=token_budget, k=k
        )
        messages = _build_messages(bundle, message)
        completion = provider.chat(messages)
        usage = tracing.token_usage(messages, completion)
        span.set(**usage)
        return ChatAnswer(
            member_id=member_id,
            message=message,
            answer=completion,
            context_used=bundle.context_items,
        )


def answer_question_stream(
    client: Neo4jClient,
    provider: LLMProvider,
    member_id: str,
    message: str,
    *,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    k: int = DEFAULT_K,
) -> Iterator[ChatStreamEvent]:
    """Stream a grounded answer to a coach's ``message`` as typed events.

    Yields a :class:`ChatContextEvent` (the retrieved context), then a :class:`ChatTokenEvent`
    per streamed chunk (their deltas concatenate to the full answer), then a :class:`ChatDoneEvent`
    with the full answer. The prompt is built by the SAME :func:`_build_messages` used by
    :func:`answer_question`, so streamed answers are grounded and guarded identically.
    """
    # NOTE: we do NOT hold a tracing span open across the yields below. A streamed generator is
    # pumped by StreamingResponse across threadpool contexts, and a contextvar-based span opened in
    # one `next()` cannot be reset in another. Retrieval traces itself synchronously (before the
    # first yield), and the generation trace is recorded in one synchronous block AFTER the stream
    # completes, so no span crosses a yield.
    bundle = service.retrieve(
        client, provider, member_id, message, token_budget=token_budget, k=k
    )
    messages = _build_messages(bundle, message)
    yield ChatContextEvent(
        member_id=member_id, message=message, context_used=bundle.context_items
    )
    parts: list[str] = []
    start = perf_counter()
    for delta in provider.chat_stream(messages):
        parts.append(delta)
        yield ChatTokenEvent(delta=delta)
    answer = "".join(parts)
    latency_ms = (perf_counter() - start) * 1000.0
    with tracing.get_tracer().trace(
        "generation.chat",
        prompt_version=PROMPT_VERSION,
        streamed=True,
        latency_ms=latency_ms,
        **tracing.token_usage(messages, answer),
    ):
        pass
    yield ChatDoneEvent(answer=answer)
