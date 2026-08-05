"""Ticket 013 — Guardrails module (formal input + output validation).

Contract (module `app.generation.guardrails`):
- `GuardrailError(ValueError)` — raised by input validation with a clear message.
- `validate_member_request(member_id) -> None` — rejects empty/blank member ids.
- `check_exercises_safe(exercise_ids, contraindicated) -> list[str]` — returns the offending
  (contraindicated) ids present, in order of appearance; `[]` when clean.
- `require_disclaimer(text, *, disclaimer) -> str` — appends the disclaimer if absent; idempotent.
- `repair_loop(produce, validate, *, max_attempts=DEFAULT_MAX_ATTEMPTS) -> (result, violations)`
  — bounded produce/validate loop; re-produces on violations up to `max_attempts`, then returns
  the last result and its residual violations.
- `DEFAULT_MAX_ATTEMPTS: int`, `DEFAULT_DISCLAIMER: str`.

Reuse: `app.generation.workout` uses `guardrails.check_exercises_safe` on its post-validation path.

All tests here are pure (no Neo4j).
"""
import pytest

from app.generation import guardrails, workout


# ----------------------- input validation -----------------------

def test_validate_member_request_accepts_a_real_id():
    # Should not raise.
    guardrails.validate_member_request("member_ava")


@pytest.mark.parametrize("bad", ["", "   ", "\t\n"])
def test_validate_member_request_rejects_blank_ids(bad):
    with pytest.raises(guardrails.GuardrailError):
        guardrails.validate_member_request(bad)


def test_guardrail_error_is_a_value_error():
    assert issubclass(guardrails.GuardrailError, ValueError)


# ----------------------- output: contraindication check -----------------------

def test_check_exercises_safe_reports_offenders_in_order():
    offenders = guardrails.check_exercises_safe(
        ["push_up", "overhead_press", "bench_press", "squat"],
        ["overhead_press", "bench_press"],
    )
    assert offenders == ["overhead_press", "bench_press"]


def test_check_exercises_safe_returns_empty_when_clean():
    assert guardrails.check_exercises_safe(["push_up", "squat"], ["overhead_press"]) == []
    assert guardrails.check_exercises_safe([], ["overhead_press"]) == []


# ----------------------- output: disclaimer -----------------------

def test_require_disclaimer_appends_when_absent():
    out = guardrails.require_disclaimer("Do 3x10 squats.", disclaimer="Consult a professional.")
    assert "Consult a professional." in out
    assert out.startswith("Do 3x10 squats.")


def test_require_disclaimer_is_idempotent():
    once = guardrails.require_disclaimer("Advice.", disclaimer="Consult a professional.")
    twice = guardrails.require_disclaimer(once, disclaimer="Consult a professional.")
    assert once == twice
    assert twice.count("Consult a professional.") == 1


# ----------------------- output: bounded repair loop -----------------------

def test_repair_loop_stops_once_output_is_valid():
    calls = {"n": 0}

    def produce():
        calls["n"] += 1
        # bad on the first attempt, valid on the second
        return "bad" if calls["n"] < 2 else "good"

    def validate(result):
        return [] if result == "good" else ["not good yet"]

    result, violations = guardrails.repair_loop(produce, validate, max_attempts=5)
    assert result == "good"
    assert violations == []
    assert calls["n"] == 2, "should stop producing as soon as output validates"


def test_repair_loop_is_bounded_and_returns_residual_violations():
    calls = {"n": 0}

    def produce():
        calls["n"] += 1
        return "always-bad"

    def validate(result):
        return ["still broken"]

    result, violations = guardrails.repair_loop(produce, validate, max_attempts=3)
    assert result == "always-bad"
    assert violations == ["still broken"], "residual violations surfaced after the loop gives up"
    assert calls["n"] == 3, "producer must be called at most max_attempts times (no infinite loop)"


def test_repair_loop_defaults_to_module_max_attempts():
    calls = {"n": 0}

    def produce():
        calls["n"] += 1
        return "x"

    def validate(result):
        return ["nope"]

    guardrails.repair_loop(produce, validate)
    assert calls["n"] == guardrails.DEFAULT_MAX_ATTEMPTS


def test_default_max_attempts_is_bounded():
    assert isinstance(guardrails.DEFAULT_MAX_ATTEMPTS, int)
    assert 1 <= guardrails.DEFAULT_MAX_ATTEMPTS <= 10


# ----------------------- reuse by the workout path -----------------------

def test_workout_reuses_the_shared_guardrail():
    # The generation path must share the module, not fork its own contraindication check.
    assert workout.guardrails.check_exercises_safe is guardrails.check_exercises_safe
