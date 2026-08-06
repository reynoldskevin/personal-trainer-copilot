"""Ticket 017 — Token/context budgeting + prompt efficiency.

Shared utilities that keep the context handed to the model within a configurable token budget and
keep prompts/outputs lean:

- :func:`truncate_to_budget` — **strict rank-prefix** truncation. Given a list of candidate strings
  already ordered by importance, it keeps the highest-ranked prefix whose running token estimate
  stays within the budget and stops at the first item that would overflow, so the kept set is
  always a prefix of the input and never exceeds the budget.
- :func:`resolve_budget` — the explicit per-call budget when given, else the environment-configured
  :attr:`app.config.Settings.context_token_budget`.
- :func:`count_prompt_tokens` — the estimated prompt-token cost of an assembled chat ``messages``
  list, used by the prompt-assembly regression guards.
- :data:`RESPONSE_FORMAT` — the structured-output request (a strict JSON object) shared by the
  generators, which minimizes output tokens and keeps completions machine-parseable.

Token estimation delegates to :func:`app.observability.tracing.estimate_tokens` so every layer
(retrieval budgeting, trace token counts, prompt guards) uses one identical heuristic.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.observability.tracing import estimate_tokens

if TYPE_CHECKING:
    from app.config import Settings

__all__ = [
    "RESPONSE_FORMAT",
    "count_prompt_tokens",
    "estimate_tokens",
    "resolve_budget",
    "truncate_to_budget",
]

# The structured-output request shared by the JSON generators (workout, insight). Asking for a
# strict JSON object keeps completions compact and directly parseable, minimizing output tokens.
RESPONSE_FORMAT: dict[str, str] = {"type": "json_object"}


def truncate_to_budget(items: list[str], budget: int) -> tuple[list[str], int]:
    """Keep the highest-ranked prefix of ``items`` whose token estimate fits ``budget``.

    Candidates are assumed to be ordered by importance (most important first). Items are included
    in order while the running :func:`estimate_tokens` sum stays within ``budget``; truncation
    stops at the **first** item that would overflow, so the returned list is always a prefix of
    ``items`` (a lower-ranked item is never swapped in for a higher-ranked one that did not fit).
    Returns ``(kept, total_tokens)`` where ``total_tokens`` never exceeds ``budget``.
    """
    kept: list[str] = []
    total = 0
    for item in items:
        cost = estimate_tokens(item)
        if total + cost > budget:
            break
        kept.append(item)
        total += cost
    return kept, total


def resolve_budget(explicit: int | None, settings: Settings) -> int:
    """Return ``explicit`` when provided, else the configured ``settings.context_token_budget``."""
    if explicit is not None:
        return explicit
    return settings.context_token_budget


def count_prompt_tokens(messages: list[dict[str, str]]) -> int:
    """Return the estimated prompt-token cost across every message's ``content``."""
    return sum(estimate_tokens(message.get("content", "")) for message in messages)
