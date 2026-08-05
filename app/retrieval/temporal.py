"""Ticket 011 — Temporal trends + last-N-weeks windowing.

Pure, side-effect-free helpers for scoping a member's time-series rows to a trailing window
and summarising trends over that window:

- :class:`TimeWindow` — a value object describing a trailing ``weeks``-wide window, optionally
  anchored to an explicit ``as_of`` instant (otherwise the latest in-scope timestamp).
- :func:`filter_window` — keep only the rows whose timestamp falls inside the window.
- :func:`adherence_percentage` — completed / planned across adherence records.
- :func:`linear_slope` — ordinary least-squares slope, degenerate-safe.
- :func:`biometric_trends` — per-metric slope-per-week trends.
- :func:`compute_trends` — fuse the above into a :class:`TrendSummary` with human-readable lines.

Every function is deterministic and operates on plain mappings, so it is trivially testable
without a database.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel

# Seconds per day and days per week, used to convert elapsed time into weeks for slope
# calculations. Elapsed time is normalised to whole days so that readings taken at slightly
# different times of day still register as an exact number of days (and weeks) apart.
_SECONDS_PER_DAY: float = 86400.0
_DAYS_PER_WEEK: float = 7.0


@dataclass(frozen=True)
class TimeWindow:
    """A trailing ``weeks``-wide window, optionally anchored at ``as_of``.

    When ``as_of`` is ``None`` the window anchors to the latest timestamp among the rows being
    filtered, so the window always ends at the most recent in-scope activity.
    """

    weeks: int
    as_of: datetime | None = None


def parse_timestamp(s: str) -> datetime:
    """Parse an ISO 8601 timestamp string into a timezone-aware :class:`datetime`."""
    return datetime.fromisoformat(s)


def filter_window(
    rows: Sequence[Mapping[str, Any]], window: TimeWindow
) -> list[Mapping[str, Any]]:
    """Return the rows whose ``"timestamp"`` falls within ``window``, preserving input order.

    The anchor is ``window.as_of`` when set, otherwise the maximum parsed timestamp among
    ``rows``. A row is kept when ``anchor - weeks*7d <= t <= anchor``. Empty input yields ``[]``.
    """
    if not rows:
        return []

    parsed: list[tuple[Mapping[str, Any], datetime]] = [
        (row, parse_timestamp(str(row["timestamp"]))) for row in rows
    ]
    anchor = window.as_of if window.as_of is not None else max(t for _, t in parsed)
    start = anchor - timedelta(weeks=window.weeks)
    return [row for row, t in parsed if start <= t <= anchor]


def adherence_percentage(records: Sequence[Mapping[str, Any]]) -> float | None:
    """Return ``100 * sum(completed) / sum(planned)``, or ``None`` when it is undefined.

    ``None`` is returned when there are no records or the total planned sessions is zero.
    """
    if not records:
        return None
    total_planned = sum(int(r["planned"]) for r in records)
    if total_planned == 0:
        return None
    total_completed = sum(int(r["completed"]) for r in records)
    return 100.0 * total_completed / total_planned


def linear_slope(points: list[tuple[float, float]]) -> float:
    """Return the ordinary least-squares slope of ``y`` over ``x``.

    Returns ``0.0`` when there are fewer than two points or the ``x`` values have zero variance
    (the division guard prevents a ``ZeroDivisionError``).
    """
    n = len(points)
    if n < 2:
        return 0.0
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    denominator = sum((x - mean_x) ** 2 for x, _ in points)
    if denominator == 0.0:
        return 0.0
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in points)
    return numerator / denominator


def _direction(slope: float) -> str:
    """Classify a slope as ``"rising"``, ``"falling"`` or ``"flat"``."""
    if slope > 0:
        return "rising"
    if slope < 0:
        return "falling"
    return "flat"


class BiometricTrend(BaseModel):
    """A per-metric trend: slope per week plus the earliest and latest observed values."""

    type: str
    slope_per_week: float
    direction: str
    first_value: float
    last_value: float


def biometric_trends(readings: Sequence[Mapping[str, Any]]) -> list[BiometricTrend]:
    """Compute a per-``type`` :class:`BiometricTrend` from timestamped biometric ``readings``.

    Within each metric type, readings are sorted by timestamp; ``x`` is weeks elapsed from that
    type's earliest reading and ``y`` is the value. A single reading yields a flat, zero-slope
    trend. Returns one trend per type.
    """
    grouped: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for reading in readings:
        grouped[str(reading["type"])].append(
            (parse_timestamp(str(reading["timestamp"])), float(reading["value"]))
        )

    trends: list[BiometricTrend] = []
    for metric_type, series in grouped.items():
        series.sort(key=lambda item: item[0])
        t0 = series[0][0]
        points = [
            (round((t - t0).total_seconds() / _SECONDS_PER_DAY) / _DAYS_PER_WEEK, value)
            for t, value in series
        ]
        slope = linear_slope(points)
        trends.append(
            BiometricTrend(
                type=metric_type,
                slope_per_week=slope,
                direction=_direction(slope),
                first_value=series[0][1],
                last_value=series[-1][1],
            )
        )
    return trends


class TrendSummary(BaseModel):
    """A fused, human-readable summary of a member's in-window trends."""

    window_weeks: int | None
    adherence_percentage: float | None
    adherence_sessions: str | None
    biometrics: list[BiometricTrend]
    workout_count: int
    summary_lines: list[str]


def compute_trends(
    *,
    window: TimeWindow,
    adherence_rows: Sequence[Mapping[str, Any]],
    biometric_rows: Sequence[Mapping[str, Any]],
    workout_rows: Sequence[Mapping[str, Any]],
) -> TrendSummary:
    """Compute a :class:`TrendSummary` from a member's in-window time-series rows.

    Each row list is scoped to ``window`` via :func:`filter_window`, then adherence percentage,
    biometric trends and workout count are derived and rendered as ``summary_lines``.
    """
    windowed_adherence = filter_window(adherence_rows, window)
    windowed_biometrics = filter_window(biometric_rows, window)
    windowed_workouts = filter_window(workout_rows, window)

    pct = adherence_percentage(windowed_adherence)
    trends = biometric_trends(windowed_biometrics)
    workout_count = len(windowed_workouts)

    total_planned = sum(int(r["planned"]) for r in windowed_adherence)
    total_completed = sum(int(r["completed"]) for r in windowed_adherence)
    adherence_sessions: str | None = None
    if windowed_adherence:
        adherence_sessions = f"{total_completed} of {total_planned} planned sessions"

    summary_lines: list[str] = []
    if pct is not None and adherence_sessions is not None:
        summary_lines.append(
            f"Adherence over the last {window.weeks} weeks: {pct:.1f}% "
            f"({adherence_sessions})."
        )
    summary_lines.append(
        f"Completed {workout_count} workouts in the last {window.weeks} weeks."
    )
    for trend in trends:
        summary_lines.append(
            f"{trend.type} is {trend.direction} "
            f"({trend.slope_per_week:+.2f} per week, "
            f"{trend.first_value:g} -> {trend.last_value:g})."
        )

    return TrendSummary(
        window_weeks=window.weeks,
        adherence_percentage=pct,
        adherence_sessions=adherence_sessions,
        biometrics=trends,
        workout_count=workout_count,
        summary_lines=summary_lines,
    )
