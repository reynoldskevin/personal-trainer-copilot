"""Abstract LLM provider interface.

`LLMProvider` defines the minimal contract every backend must satisfy: a chat
completion call and a batch embedding call. Concrete implementations (e.g.
`OpenAIProvider`) subclass this so the rest of the app depends only on the
interface, never on a specific vendor SDK.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Vendor-neutral interface for chat completion and embedding."""

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        """Return the assistant's reply text for the given chat `messages`."""
        raise NotImplementedError

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input string, in order."""
        raise NotImplementedError
