"""OpenAI-backed implementation of `LLMProvider`.

The underlying client is injectable so tests can supply a mock and no live API
call is ever made. Transient failures (network / timeout / rate limit) are
retried with a fixed backoff; non-transient errors propagate immediately.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

import openai

from app.llm.provider import LLMProvider

T = TypeVar("T")

# Exceptions worth retrying: stdlib connection/timeout errors plus the OpenAI
# SDK's transient error types.
_TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
)


class OpenAIProvider(LLMProvider):
    """`LLMProvider` implementation backed by the OpenAI SDK."""

    def __init__(
        self,
        api_key: str,
        *,
        client: Any = None,
        chat_model: str = "gpt-4o-mini",
        embed_model: str = "text-embedding-3-small",
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_backoff: float = 0.5,
    ) -> None:
        self._client: Any = (
            client if client is not None else openai.OpenAI(api_key=api_key, timeout=timeout)
        )
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

    def _with_retries(self, call: Callable[[], T]) -> T:
        """Invoke `call`, retrying transient errors up to `max_retries` attempts."""
        last_exc: BaseException | None = None
        for attempt in range(self.max_retries):
            try:
                return call()
            except _TRANSIENT_ERRORS as exc:
                last_exc = exc
                if attempt + 1 < self.max_retries:
                    time.sleep(self.retry_backoff)
        assert last_exc is not None
        raise last_exc

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        def _call() -> str:
            resp = self._client.chat.completions.create(
                model=self.chat_model, messages=messages, **kwargs
            )
            content: str = resp.choices[0].message.content
            return content

        return self._with_retries(_call)

    def embed(self, texts: list[str]) -> list[list[float]]:
        def _call() -> list[list[float]]:
            resp = self._client.embeddings.create(model=self.embed_model, input=texts)
            return [d.embedding for d in resp.data]

        return self._with_retries(_call)
