"""Ticket 013 — Guardrails: formal input + output validation for generation.

A small, dependency-free toolkit that hardens the generation pipeline at both ends:

- **Input validation** — :func:`validate_member_request` rejects blank member ids before any
  expensive retrieval or model call, raising :class:`GuardrailError`.
- **Output validation** — :func:`check_exercises_safe` reports contraindicated exercise ids,
  and :func:`require_disclaimer` guarantees a professional safety disclaimer is present without
  ever duplicating it.
- **Bounded repair** — :func:`repair_loop` re-runs a producer against a validator a bounded
  number of times, returning the last result and its residual violations rather than looping
  forever.

The contraindication check is the single shared implementation reused by
:mod:`app.generation.workout` on its post-validation path, so the safety invariant is defined in
exactly one place.
"""
from __future__ import annotations

from collections.abc import Callable

#: Upper bound on how many times :func:`repair_loop` may call its producer.
DEFAULT_MAX_ATTEMPTS: int = 3

#: Professional safety disclaimer appended to generated fitness advice.
DEFAULT_DISCLAIMER: str = (
    "This plan is generated for general informational purposes only and is not medical advice. "
    "Consult a qualified healthcare or fitness professional before beginning any exercise "
    "program, especially if you have an injury or medical condition."
)


class GuardrailError(ValueError):
    """Raised when a request or output fails a guardrail check."""


def validate_member_request(member_id: str) -> None:
    """Validate an inbound member request, raising on a blank member id.

    Raises :class:`GuardrailError` when ``member_id`` is empty or whitespace-only; otherwise
    returns ``None``.
    """
    if not member_id or not member_id.strip():
        raise GuardrailError("member_id must be a non-empty, non-blank string.")


def check_exercises_safe(exercise_ids: list[str], contraindicated: list[str]) -> list[str]:
    """Return the contraindicated ids present in ``exercise_ids``, in order of appearance.

    Pure output validation with no side effects: returns ``[]`` when nothing is contraindicated
    or the inputs are empty.
    """
    unsafe = set(contraindicated)
    return [exercise_id for exercise_id in exercise_ids if exercise_id in unsafe]


def require_disclaimer(text: str, *, disclaimer: str) -> str:
    """Return ``text`` with ``disclaimer`` appended if it is not already present.

    Idempotent: applying it to already-disclaimed text is a no-op, so the disclaimer is never
    duplicated. When appended, it is separated from ``text`` by a newline.
    """
    if disclaimer in text:
        return text
    if not text:
        return disclaimer
    return f"{text}\n{disclaimer}"


def repair_loop[T](
    produce: Callable[[], T],
    validate: Callable[[T], list[str]],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> tuple[T, list[str]]:
    """Run a bounded produce/validate repair loop.

    Calls ``produce`` then ``validate``; while ``validate`` reports violations and ``produce``
    has been called fewer than ``max_attempts`` times, re-``produce`` and re-``validate``.
    Returns ``(last_result, last_violations)``. ``produce`` is called at least once and at most
    ``max_attempts`` times — as few as once when the first result validates.
    """
    result = produce()
    violations = validate(result)
    attempts = 1
    while violations and attempts < max_attempts:
        result = produce()
        violations = validate(result)
        attempts += 1
    return result, violations
