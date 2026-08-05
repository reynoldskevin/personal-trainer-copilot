"""LLM provider package: vendor-neutral interface plus OpenAI implementation.

`get_provider` selects a concrete provider from application settings, keeping
provider choice a single configuration switch rather than a code dependency.
"""
from __future__ import annotations

from typing import Any

from app.llm.openai_provider import OpenAIProvider
from app.llm.provider import LLMProvider

__all__ = ["LLMProvider", "OpenAIProvider", "get_provider"]


def get_provider(settings: Any) -> LLMProvider:
    """Return an `LLMProvider` selected by `settings.llm_provider`.

    Only ``"openai"`` is supported today; other values (e.g. ``"bedrock"``) are
    reserved future extension points and raise `ValueError`.
    """
    provider = settings.llm_provider
    if provider == "openai":
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            chat_model=getattr(settings, "openai_chat_model", "gpt-4o-mini"),
            embed_model=getattr(settings, "openai_embed_model", "text-embedding-3-small"),
        )
    raise ValueError(f"Unsupported llm_provider: {provider!r}")
