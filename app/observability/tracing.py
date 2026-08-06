"""Ticket 016 — Observability: request traces (latency + tokens) + correlation ids.

A small, vendor-neutral tracing layer for retrieval and generation. It provides:

- **Correlation ids** carried per request via :mod:`contextvars`
  (:func:`new_correlation_id`, :func:`get_correlation_id`, :func:`correlation_scope`), so a
  single id threads through structured logs and every span emitted while it is active.
- **Spans** (:class:`Span`) and **tracers** (:class:`Tracer` and subclasses) exposing
  ``.trace(name, **meta)`` / ``.span(name, **meta)`` context managers that measure wall-clock
  latency and nest child spans under whatever span is currently open (async/context-safe via a
  :class:`contextvars.ContextVar` stack).
- A process-wide tracer **registry** (:func:`get_tracer`/:func:`set_tracer`/:func:`reset_tracer`)
  whose lazy default is a :class:`StructuredLogTracer` — it never imports ``langfuse``.
  :func:`configure_from_settings` upgrades to a :class:`LangfuseTracer` only when the optional
  ``langfuse`` package is importable *and* credentials are configured.
- **Token helpers** (:func:`estimate_tokens`, :func:`token_usage`) matching the repo's existing
  characters-per-token heuristic, used to record prompt/completion token counts on a trace.

``langfuse`` is not a declared dependency: it is never imported at module import time, and every
reference to it is guarded so tests and CI run on the no-op-safe structured-log default.
"""
from __future__ import annotations

import abc
import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from app.config import Settings

# Characters-per-token heuristic, matching :func:`app.retrieval.service.estimate_tokens`.
_CHARS_PER_TOKEN: int = 4

_LOGGER = logging.getLogger("app.observability")

# --------------------------------------------------------------------------- correlation ids

# The correlation id in scope for the current logical request (async/context-safe).
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    """Return a fresh, unique, non-empty correlation id."""
    return uuid4().hex


def get_correlation_id() -> str | None:
    """Return the correlation id in scope for the current context, or ``None``."""
    return _correlation_id.get()


@contextmanager
def correlation_scope(cid: str | None = None) -> Iterator[str]:
    """Bind a correlation id for the duration of the ``with`` block.

    Generates a fresh id via :func:`new_correlation_id` when ``cid`` is ``None``, yields the
    effective id, and restores the previously bound value on exit (nesting correctly via a
    :class:`contextvars.ContextVar` token).
    """
    effective = cid if cid is not None else new_correlation_id()
    token = _correlation_id.set(effective)
    try:
        yield effective
    finally:
        _correlation_id.reset(token)


# --------------------------------------------------------------------------- spans


@dataclass
class Span:
    """One traced unit of work: a name, free-form metadata and measured latency.

    ``duration_ms`` is populated when the span's context manager exits. ``correlation_id`` is
    captured at span creation. ``children`` holds spans opened while this one was active.
    """

    name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None
    correlation_id: str | None = None
    children: list[Span] = field(default_factory=list)

    def set(self, **meta: Any) -> None:
        """Merge ``meta`` into the span's metadata."""
        self.metadata.update(meta)


# --------------------------------------------------------------------------- tracers


class Tracer(abc.ABC):
    """Abstract tracer: opens latency-measured, correlation-tagged, nesting :class:`Span` objects.

    Subclasses implement only :meth:`_record_root` to decide what happens to a completed root
    span (record it, log it, or drop it). The enter/exit/latency/nesting logic lives once in
    :meth:`_open`; :meth:`trace` and :meth:`span` are structurally identical — ``trace`` is just
    the semantic name for a root request.
    """

    def __init__(self) -> None:
        # A per-tracer stack of currently-open spans, kept context-safe so nesting survives
        # async boundaries. Each tracer instance gets its own ContextVar.
        self._stack: ContextVar[tuple[Span, ...]] = ContextVar(
            f"tracer_stack_{id(self)}", default=()
        )

    @contextmanager
    def _open(self, name: str, meta: dict[str, Any]) -> Iterator[Span]:
        """Open a span named ``name``, measuring latency and nesting it under any active span."""
        span = Span(
            name=name,
            metadata=dict(meta),
            correlation_id=get_correlation_id(),
        )
        stack = self._stack.get()
        parent = stack[-1] if stack else None
        if parent is not None:
            parent.children.append(span)
        token = self._stack.set((*stack, span))
        start = time.perf_counter()
        try:
            yield span
        finally:
            span.duration_ms = (time.perf_counter() - start) * 1000.0
            self._stack.reset(token)
            if parent is None:
                self._record_root(span)

    @contextmanager
    def trace(self, name: str, **meta: Any) -> Iterator[Span]:
        """Open a root-level trace span (the entry point for a logical request)."""
        with self._open(name, meta) as span:
            yield span

    @contextmanager
    def span(self, name: str, **meta: Any) -> Iterator[Span]:
        """Open a span, nested under the active span if one is open, else a root."""
        with self._open(name, meta) as span:
            yield span

    @abc.abstractmethod
    def _record_root(self, span: Span) -> None:
        """Handle a completed root span (called once the outermost span closes)."""


class RecordingTracer(Tracer):
    """In-memory tracer that records every root span (with its children) into :attr:`traces`."""

    def __init__(self) -> None:
        super().__init__()
        self.traces: list[Span] = []

    def _record_root(self, span: Span) -> None:
        self.traces.append(span)

    def all_spans(self) -> list[Span]:
        """Return every recorded root and all descendants, flattened pre-order."""
        flat: list[Span] = []

        def _walk(span: Span) -> None:
            flat.append(span)
            for child in span.children:
                _walk(child)

        for root in self.traces:
            _walk(root)
        return flat

    def find(self, name: str) -> list[Span]:
        """Return every recorded span whose ``.name`` equals ``name``."""
        return [span for span in self.all_spans() if span.name == name]


class NoOpTracer(Tracer):
    """Tracer that measures spans but keeps no state and emits nothing."""

    def _record_root(self, span: Span) -> None:
        return None


class StructuredLogTracer(Tracer):
    """Default tracer: emits one structured JSON log line per completed root span.

    The line carries the span name, ``duration_ms``, ``correlation_id`` and ``metadata`` so that
    structured logs carry a correlation id per request. Keeps no in-memory state.
    """

    def _record_root(self, span: Span) -> None:
        payload = {
            "event": "trace",
            "name": span.name,
            "duration_ms": span.duration_ms,
            "correlation_id": span.correlation_id,
            "metadata": span.metadata,
        }
        _LOGGER.info(json.dumps(payload, default=str))


class LangfuseTracer(Tracer):
    """Optional LangFuse-backed tracer.

    The ``langfuse`` package is imported lazily inside :meth:`__init__` so this class is
    import-safe when the (undeclared) dependency is absent. Beyond forwarding completed root
    spans to LangFuse, it behaves exactly like the other tracers.
    """

    def __init__(
        self,
        public_key: str,
        secret_key: str,
        host: str | None = None,
    ) -> None:
        super().__init__()
        import langfuse  # noqa: PLC0415  (lazy, optional dependency)

        self._client = langfuse.Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )

    def _record_root(self, span: Span) -> None:
        self._client.trace(
            name=span.name,
            metadata=span.metadata,
            session_id=span.correlation_id,
        )


# --------------------------------------------------------------------------- registry

_tracer: Tracer | None = None


def get_tracer() -> Tracer:
    """Return the process-wide tracer, lazily defaulting to a :class:`StructuredLogTracer`."""
    global _tracer
    if _tracer is None:
        _tracer = StructuredLogTracer()
    return _tracer


def set_tracer(tracer: Tracer) -> None:
    """Install ``tracer`` as the process-wide tracer."""
    global _tracer
    _tracer = tracer


def reset_tracer() -> None:
    """Clear the process-wide tracer back to the lazy default."""
    global _tracer
    _tracer = None


def configure_from_settings(settings: Settings) -> Tracer:
    """Return a :class:`LangfuseTracer` only when ``langfuse`` is available and configured.

    "Configured" requires both a public and a secret key on ``settings``. When ``langfuse`` is
    not importable (it is not a declared dependency) or credentials are missing, falls back to a
    :class:`StructuredLogTracer`.
    """
    public_key = getattr(settings, "langfuse_public_key", None)
    secret_key = getattr(settings, "langfuse_secret_key", None)
    host = getattr(settings, "langfuse_host", None)
    if public_key and secret_key:
        try:
            import langfuse  # noqa: F401, PLC0415  (probe for the optional dependency)
        except ImportError:
            return StructuredLogTracer()
        return LangfuseTracer(public_key, secret_key, host)
    return StructuredLogTracer()


# --------------------------------------------------------------------------- token helpers


def estimate_tokens(text: str) -> int:
    """Return a deterministic, non-negative token estimate (``len(text) // 4``)."""
    return max(0, len(text) // _CHARS_PER_TOKEN)


def token_usage(messages: list[dict[str, str]], completion: str) -> dict[str, int]:
    """Return prompt/completion/total token estimates for a chat exchange.

    Prompt tokens sum :func:`estimate_tokens` over each message's ``"content"``; completion
    tokens estimate ``completion``; total is their sum.
    """
    prompt_tokens = sum(estimate_tokens(message.get("content", "")) for message in messages)
    completion_tokens = estimate_tokens(completion)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
