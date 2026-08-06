"""Ticket 020 — Performance verification harness.

Measures end-to-end ``/generate/workout`` latency across the seed members and asserts it stays
within budget. The LLM provider is **stubbed to ~zero latency** by the caller, so the harness
measures *our* overhead — Neo4j round-trips, member-scoped retrieval, candidate pre-filtering and
plan assembly — rather than the language model's response time (which in production dominates and
is outside our control).

`run_workout_benchmark` times each generation end-to-end and, separately, the retrieval step, so
the retrieval/assembly overhead is reported on its own. Latencies are summarized as p50/p95 (plus
mean/max) via a nearest-rank :func:`percentile`. See ``docs/performance.md`` for the method and the
measured numbers.
"""
from __future__ import annotations

import math
import time

from pydantic import BaseModel

from app.generation import workout
from app.graph.client import Neo4jClient
from app.llm.provider import LLMProvider
from app.retrieval import service

# The p95 budget (ms) the end-to-end generation must stay under, excluding provider latency.
DEFAULT_P95_BUDGET_MS: float = 5000.0


def percentile(samples: list[float], p: float) -> float:
    """Return the nearest-rank ``p``-th percentile of ``samples`` (0.0 for empty input).

    Nearest-rank: the value at rank ``ceil(p/100 * n)`` in the sorted samples (1-indexed). So
    ``percentile(range(1..100), 95) == 95`` and ``percentile([], p) == 0.0``.
    """
    if not samples:
        return 0.0
    ordered = sorted(samples)
    rank = max(1, math.ceil(p / 100.0 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


class LatencyStats(BaseModel):
    """Summary latency statistics (milliseconds) over a set of timed runs."""

    count: int
    p50_ms: float
    p95_ms: float
    mean_ms: float
    max_ms: float


def summarize(samples_ms: list[float]) -> LatencyStats:
    """Summarize a list of millisecond latencies into :class:`LatencyStats`."""
    if not samples_ms:
        return LatencyStats(count=0, p50_ms=0.0, p95_ms=0.0, mean_ms=0.0, max_ms=0.0)
    return LatencyStats(
        count=len(samples_ms),
        p50_ms=percentile(samples_ms, 50),
        p95_ms=percentile(samples_ms, 95),
        mean_ms=sum(samples_ms) / len(samples_ms),
        max_ms=max(samples_ms),
    )


class BenchmarkReport(BaseModel):
    """End-to-end and retrieval-only latency for a workout-generation benchmark."""

    iterations: int
    members: list[str]
    end_to_end: LatencyStats
    retrieval: LatencyStats

    def to_markdown(self) -> str:
        """Render a concise, human-readable markdown summary of the benchmark."""

        def _row(label: str, s: LatencyStats) -> str:
            return (
                f"| {label} | {s.count} | {s.p50_ms:.1f} | {s.p95_ms:.1f} | "
                f"{s.mean_ms:.1f} | {s.max_ms:.1f} |"
            )

        return "\n".join(
            [
                "# Performance benchmark — /generate/workout",
                "",
                f"- members: {', '.join(self.members)}",
                f"- iterations per member: {self.iterations}",
                "- provider latency: stubbed to ~0 (measuring our overhead only)",
                "",
                "| stage | n | p50 (ms) | p95 (ms) | mean (ms) | max (ms) |",
                "|---|---|---|---|---|---|",
                _row("end-to-end generate", self.end_to_end),
                _row("retrieval only", self.retrieval),
                "",
            ]
        )


def _time_ms(start: float) -> float:
    """Elapsed milliseconds since ``start`` (a :func:`time.perf_counter` reading)."""
    return (time.perf_counter() - start) * 1000.0


def run_workout_benchmark(
    client: Neo4jClient,
    provider: LLMProvider,
    member_ids: list[str],
    *,
    iterations: int = 5,
) -> BenchmarkReport:
    """Benchmark ``generate_workout`` over ``member_ids`` × ``iterations`` runs.

    For each run it times the full generation end-to-end and, separately, the retrieval step, so
    the retrieval/assembly overhead can be reported apart from the whole pipeline.
    """
    end_to_end: list[float] = []
    retrieval: list[float] = []
    for member_id in member_ids:
        for _ in range(iterations):
            start = time.perf_counter()
            service.retrieve(client, provider, member_id, workout.DEFAULT_QUERY)
            retrieval.append(_time_ms(start))

            start = time.perf_counter()
            workout.generate_workout(client, provider, member_id)
            end_to_end.append(_time_ms(start))

    return BenchmarkReport(
        iterations=iterations,
        members=list(member_ids),
        end_to_end=summarize(end_to_end),
        retrieval=summarize(retrieval),
    )
