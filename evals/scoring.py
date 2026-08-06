"""Ticket 019 — Evals scoring + report models.

Pure, deterministic scoring for the two eval dimensions, plus the aggregate report:

- **Retrieval quality** — :func:`score_retrieval` compares the node ids retrieval surfaced against
  the case's expected nodes and reports precision, recall and F1.
- **Safety** — :func:`score_safety` checks that a generated plan's recommended exercises contain
  **none** of the injury's forbidden exercises; any that appear are recorded as violations and the
  case fails.

:class:`EvalReport` aggregates the per-case scores and renders both a human-readable markdown
summary (:meth:`EvalReport.to_markdown`) and, being a pydantic model, a machine-parseable JSON
artifact via ``model_dump``. Nothing here touches a database or a model — it operates on already
-computed id sets, so scoring is fully deterministic and unit-testable in isolation.
"""
from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel


class RetrievalScore(BaseModel):
    """Precision/recall/F1 for one retrieval case against its expected node set."""

    case_id: str
    expected: int
    retrieved: int
    hits: int
    precision: float
    recall: float
    f1: float


class SafetyScore(BaseModel):
    """Pass/fail for one safety case: fails if any forbidden exercise was recommended."""

    case_id: str
    passed: bool
    violations: list[str]


def score_retrieval(case_id: str, expected: set[str], retrieved: set[str]) -> RetrievalScore:
    """Score one retrieval case: precision/recall/F1 of ``retrieved`` against ``expected``.

    ``precision`` is 0 when nothing was retrieved, ``recall`` is 0 when nothing was expected, and
    ``f1`` is 0 whenever either is 0 — so an empty overlap always scores 0 rather than dividing by
    zero.
    """
    hit_set = expected & retrieved
    hits = len(hit_set)
    precision = hits / len(retrieved) if retrieved else 0.0
    recall = hits / len(expected) if expected else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return RetrievalScore(
        case_id=case_id,
        expected=len(expected),
        retrieved=len(retrieved),
        hits=hits,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def score_safety(case_id: str, recommended: Iterable[str], forbidden: set[str]) -> SafetyScore:
    """Score one safety case: pass iff none of ``forbidden`` appears in ``recommended``.

    ``violations`` lists the forbidden exercises that were recommended, in the order they appear in
    ``recommended`` (de-duplicated), so a failing case names exactly what leaked through.
    """
    seen: set[str] = set()
    violations: list[str] = []
    for exercise_id in recommended:
        if exercise_id in forbidden and exercise_id not in seen:
            seen.add(exercise_id)
            violations.append(exercise_id)
    return SafetyScore(case_id=case_id, passed=not violations, violations=violations)


class EvalReport(BaseModel):
    """Aggregated eval results across all retrieval + safety cases for a dataset version."""

    version: str
    retrieval: list[RetrievalScore]
    safety: list[SafetyScore]

    def mean_recall(self) -> float:
        """Mean retrieval recall across all retrieval cases (0.0 if there are none)."""
        if not self.retrieval:
            return 0.0
        return sum(s.recall for s in self.retrieval) / len(self.retrieval)

    def mean_precision(self) -> float:
        """Mean retrieval precision across all retrieval cases (0.0 if there are none)."""
        if not self.retrieval:
            return 0.0
        return sum(s.precision for s in self.retrieval) / len(self.retrieval)

    def mean_f1(self) -> float:
        """Mean retrieval F1 across all retrieval cases (0.0 if there are none)."""
        if not self.retrieval:
            return 0.0
        return sum(s.f1 for s in self.retrieval) / len(self.retrieval)

    def safety_passed(self) -> bool:
        """True iff every safety case passed (no forbidden exercise was ever recommended)."""
        return all(s.passed for s in self.safety)

    def total_safety_violations(self) -> int:
        """Total number of forbidden-exercise violations across all safety cases."""
        return sum(len(s.violations) for s in self.safety)

    def to_markdown(self) -> str:
        """Render a concise, human-readable markdown summary of the report."""
        lines = [
            f"# Eval report — dataset {self.version}",
            "",
            "## Retrieval quality",
            f"- cases: {len(self.retrieval)}",
            f"- mean precision: {self.mean_precision():.3f}",
            f"- mean recall: {self.mean_recall():.3f}",
            f"- mean F1: {self.mean_f1():.3f}",
            "",
            "| case | expected | retrieved | hits | precision | recall | f1 |",
            "|---|---|---|---|---|---|---|",
        ]
        for s in self.retrieval:
            lines.append(
                f"| {s.case_id} | {s.expected} | {s.retrieved} | {s.hits} | "
                f"{s.precision:.2f} | {s.recall:.2f} | {s.f1:.2f} |"
            )
        status = "PASS" if self.safety_passed() else "FAIL"
        lines += [
            "",
            "## Safety",
            f"- cases: {len(self.safety)}",
            f"- result: **{status}** ({self.total_safety_violations()} violations)",
            "",
            "| case | passed | violations |",
            "|---|---|---|",
        ]
        for sc in self.safety:
            viol = ", ".join(sc.violations) if sc.violations else "—"
            lines.append(f"| {sc.case_id} | {'yes' if sc.passed else 'NO'} | {viol} |")
        return "\n".join(lines) + "\n"
