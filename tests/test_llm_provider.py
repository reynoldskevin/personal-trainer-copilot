"""Ticket 003 — LLMProvider interface + OpenAI implementation.

Contract:
- `app.llm.LLMProvider` is an abstract base with `chat(messages) -> str` and
  `embed(texts) -> list[list[float]]`.
- `app.llm.OpenAIProvider` implements it, driven by an injectable client so no live API is
  needed in tests. Supports `max_retries` + `retry_backoff` and retries transient errors
  (ConnectionError / TimeoutError). Has a `timeout`.
- `app.llm.get_provider(settings)` returns an `OpenAIProvider` when `llm_provider == "openai"`,
  and raises `ValueError` for an unsupported provider (Bedrock is a future extension point).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.llm import LLMProvider, OpenAIProvider, get_provider


def _mock_client(chat_content="hi", embed_vectors=None, chat_side_effect=None):
    client = MagicMock()
    if chat_side_effect is not None:
        client.chat.completions.create.side_effect = chat_side_effect
    else:
        msg = MagicMock()
        msg.content = chat_content
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        client.chat.completions.create.return_value = resp
    vectors = embed_vectors or [[0.1, 0.2, 0.3]]
    embresp = MagicMock()
    embresp.data = [MagicMock(embedding=v) for v in vectors]
    client.embeddings.create.return_value = embresp
    return client


def test_openai_provider_is_an_llmprovider():
    p = OpenAIProvider(api_key="sk-x", client=_mock_client())
    assert isinstance(p, LLMProvider)


def test_llmprovider_is_abstract():
    with pytest.raises(TypeError):
        LLMProvider()  # type: ignore[abstract]


def test_chat_returns_text():
    client = _mock_client(chat_content="hello world")
    p = OpenAIProvider(api_key="sk-x", client=client)
    out = p.chat([{"role": "user", "content": "hi"}])
    assert out == "hello world"
    client.chat.completions.create.assert_called_once()


def test_embed_returns_vectors():
    client = _mock_client(embed_vectors=[[0.1, 0.2], [0.3, 0.4]])
    p = OpenAIProvider(api_key="sk-x", client=client)
    vecs = p.embed(["a", "b"])
    assert vecs == [[0.1, 0.2], [0.3, 0.4]]


def test_chat_retries_transient_error_then_succeeds():
    msg = MagicMock()
    msg.content = "ok"
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.side_effect = [ConnectionError("transient"), resp]
    p = OpenAIProvider(api_key="sk-x", client=client, max_retries=3, retry_backoff=0)
    assert p.chat([{"role": "user", "content": "hi"}]) == "ok"
    assert client.chat.completions.create.call_count == 2


def test_chat_reraises_after_exhausting_retries():
    client = MagicMock()
    client.chat.completions.create.side_effect = ConnectionError("always down")
    p = OpenAIProvider(api_key="sk-x", client=client, max_retries=2, retry_backoff=0)
    with pytest.raises(ConnectionError):
        p.chat([{"role": "user", "content": "hi"}])


def test_provider_has_timeout():
    p = OpenAIProvider(api_key="sk-x", client=_mock_client(), timeout=7.5)
    assert p.timeout == 7.5


def test_get_provider_selects_openai():
    settings = SimpleNamespace(llm_provider="openai", openai_api_key="sk-x")
    assert isinstance(get_provider(settings), OpenAIProvider)


def test_get_provider_unknown_raises():
    settings = SimpleNamespace(llm_provider="bedrock", openai_api_key="sk-x")
    with pytest.raises(ValueError):
        get_provider(settings)
