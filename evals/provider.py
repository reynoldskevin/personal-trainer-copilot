"""Ticket 019 — Deterministic offline provider for the evals CLI.

A dependency-free :class:`~app.llm.provider.LLMProvider` used by ``python -m evals.run --offline``
so the eval harness runs with **no** OpenAI key and produces byte-stable scores (in CI and demos).
It is deliberately kept inside ``evals`` — never registered in the production provider selection —
so it can only be reached by explicitly opting into the offline eval run.

- ``embed`` reuses the same 15-dimension bag-of-words scheme the integration tests seed into the
  vector index, so query embeddings are comparable to the indexed vectors.
- ``chat`` returns a fixed, safe JSON workout (only exercises that are safe for every seed member),
  so a real run exercises the full parse + guardrail path deterministically.
"""
from __future__ import annotations

import json

from app.llm.provider import LLMProvider

# Same vocabulary the retrieval/eval integration tests use to build 15-dim embeddings.
_VOCAB = [
    "shoulder", "overhead", "press", "pain", "rehab", "deadlift", "squat", "strong",
    "core", "back", "hip", "stability", "brace", "tight",
]


class DeterministicProvider(LLMProvider):
    """Offline, deterministic embeddings + a fixed safe JSON workout completion."""

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        return json.dumps(
            {
                "summary": "Deterministic offline plan.",
                "exercises": [
                    {"exercise_id": "push_up", "name": "Push-up", "sets": 3, "reps": 10},
                    {"exercise_id": "barbell_curl", "name": "Barbell curl", "sets": 3, "reps": 12},
                ],
            }
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(t.lower().count(word)) for word in _VOCAB] + [1.0] for t in texts]
