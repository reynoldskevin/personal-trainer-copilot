"""Ticket 014 — Chat endpoint (context-only).

Answers a *coach's* question about a member, grounded strictly in the member's retrieved
GraphRAG context. Retrieval reuses :func:`app.retrieval.service.retrieve` so all member reads
stay member-scoped and parameterized.

The assistant is framed as a professional-to-professional aide: it answers the coach about the
member and is explicitly forbidden from drafting a client- or member-facing reply. It never
invents facts beyond the provided context.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.graph.client import Neo4jClient
from app.llm.provider import LLMProvider
from app.retrieval import service

# Reuse the retrieval service's defaults so chat and retrieval stay in lockstep.
DEFAULT_TOKEN_BUDGET: int = service.DEFAULT_TOKEN_BUDGET
DEFAULT_K: int = service.DEFAULT_K


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
    "members. Answer the coach's question about the member using ONLY the member context "
    "provided below; if the context does not contain the answer, say so plainly and never "
    "invent facts. You are speaking to the coach, not to the member. Do NOT draft a "
    "client-facing or member-facing message, and never write a reply addressed to the client "
    "or member — respond directly to the coach as a colleague."
)


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
    bundle = service.retrieve(
        client,
        provider,
        member_id,
        message,
        token_budget=token_budget,
        k=k,
    )

    context_lines = bundle.context_items or bundle.subgraph_facts
    user = (
        "Member context:\n"
        + "\n".join(context_lines)
        + "\n\nThe coach asks: "
        + message
        + "\n\nAnswer the coach's question grounded only in the member context above."
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]

    completion = provider.chat(messages)
    return ChatAnswer(
        member_id=member_id,
        message=message,
        answer=completion,
        context_used=bundle.context_items,
    )
