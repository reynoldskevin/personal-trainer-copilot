"""Ticket 011 — Temporal trends + last-N-weeks windowing.

Contract (module `app.retrieval.temporal`):
- `TimeWindow(weeks: int, as_of: datetime | None = None)` — window value object; `as_of=None`
  anchors to the latest in-scope timestamp among the rows (deterministic on the fixed seed).
- `parse_timestamp(s) -> datetime`.
- `filter_window(rows, window) -> rows` — rows are mappings with a `"timestamp"` ISO key; keeps
  rows with `anchor - weeks*7d <= ts <= anchor`, `anchor = window.as_of or max(ts)`.
- `adherence_percentage(records) -> float | None` — `100*sum(completed)/sum(planned)`; `None` when
  no records / total planned is 0.
- `linear_slope(points) -> float` — least-squares slope; `0.0` for <2 points or zero x-variance.
- `biometric_trends(readings) -> list[BiometricTrend]` — per metric `type`, slope per week.
- `BiometricTrend` / `TrendSummary` — Pydantic models.

Retrieval integration (module `app.retrieval.service`):
- `ContextBundle` gains `trends: TrendSummary | None`.
- `retrieve(..., window=TimeWindow(...))` scopes time-series facts to the window and attaches a
  computed `TrendSummary`.

Pure-math tests always run. Integration tests need the local Neo4j and skip if it is down.
"""
import os
from datetime import UTC, datetime

import pytest

from app.graph import schema
from app.graph.client import Neo4jClient
from app.ingestion import members, ontology
from app.llm.provider import LLMProvider
from app.retrieval import service, temporal

_VOCAB = [
    "shoulder", "overhead", "press", "pain", "rehab", "deadlift", "squat", "strong",
    "core", "back", "hip", "stability", "brace", "tight",
]


def _embed_text(text: str) -> list[float]:
    low = text.lower()
    return [float(low.count(word)) for word in _VOCAB] + [1.0]


class FakeEmbedProvider(LLMProvider):
    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:  # pragma: no cover
        return ""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_embed_text(t) for t in texts]


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


# ----------------------- pure math (no Neo4j) -----------------------

def test_parse_timestamp_roundtrips_iso():
    parsed = temporal.parse_timestamp("2026-01-06T09:00:00+00:00")
    assert parsed == datetime(2026, 1, 6, 9, 0, 0, tzinfo=UTC)


def test_adherence_percentage_over_full_seed_set():
    # Ava's four adherence records: planned 4+4+4+4=16, completed 2+3+3+4=12 -> 75.0%.
    records = [
        {"planned": 4, "completed": 2},
        {"planned": 4, "completed": 3},
        {"planned": 4, "completed": 3},
        {"planned": 4, "completed": 4},
    ]
    assert temporal.adherence_percentage(records) == pytest.approx(75.0)


def test_adherence_percentage_is_none_when_no_data_or_zero_planned():
    assert temporal.adherence_percentage([]) is None
    assert temporal.adherence_percentage([{"planned": 0, "completed": 0}]) is None


def test_linear_slope_on_known_points():
    assert temporal.linear_slope([(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)]) == pytest.approx(1.0)
    assert temporal.linear_slope([(0.0, 10.0), (1.0, 8.0)]) == pytest.approx(-2.0)


def test_linear_slope_degenerate_cases_are_zero():
    assert temporal.linear_slope([]) == 0.0
    assert temporal.linear_slope([(5.0, 5.0)]) == 0.0
    # zero variance in x -> slope 0, not a division error
    assert temporal.linear_slope([(3.0, 1.0), (3.0, 9.0)]) == 0.0


def test_biometric_trends_slope_per_week_from_seed():
    # Ava resting_heart_rate: 61.0 @ 2026-01-06, 58.0 @ 2026-01-27 (21 days = 3 weeks).
    # slope ~= (58 - 61) / 3 = -1.0 per week, falling (timestamps are ~3 weeks apart).
    readings = [
        {"timestamp": "2026-01-06T07:30:00+00:00", "type": "resting_heart_rate", "value": 61.0},
        {"timestamp": "2026-01-27T07:28:00+00:00", "type": "resting_heart_rate", "value": 58.0},
        {"timestamp": "2026-01-13T07:32:00+00:00", "type": "body_weight_kg", "value": 68.4},
    ]
    by_type = {t.type: t for t in temporal.biometric_trends(readings)}
    assert set(by_type) == {"resting_heart_rate", "body_weight_kg"}

    rhr = by_type["resting_heart_rate"]
    assert rhr.slope_per_week == pytest.approx(-1.0, abs=0.05)
    assert rhr.direction == "falling"
    assert rhr.first_value == pytest.approx(61.0)
    assert rhr.last_value == pytest.approx(58.0)

    # single reading -> flat, zero slope
    bw = by_type["body_weight_kg"]
    assert bw.slope_per_week == pytest.approx(0.0)
    assert bw.direction == "flat"


def test_filter_window_excludes_out_of_window_rows():
    rows = [
        {"timestamp": "2026-01-06T20:00:00+00:00", "completed": 2},
        {"timestamp": "2026-01-13T20:00:00+00:00", "completed": 3},
        {"timestamp": "2026-01-20T20:00:00+00:00", "completed": 3},
        {"timestamp": "2026-01-27T20:00:00+00:00", "completed": 4},
    ]
    window = temporal.TimeWindow(weeks=3, as_of=_dt("2026-01-28T00:00:00+00:00"))
    kept = temporal.filter_window(rows, window)
    kept_ts = [r["timestamp"] for r in kept]
    # 2026-01-07 <= ts <= 2026-01-28 keeps the last three, drops 2026-01-06.
    assert "2026-01-06T20:00:00+00:00" not in kept_ts
    assert len(kept) == 3


def test_filter_window_default_anchor_is_latest_timestamp():
    rows = [
        {"timestamp": "2026-01-06T20:00:00+00:00"},
        {"timestamp": "2026-01-27T20:00:00+00:00"},
    ]
    # weeks=1, as_of=None -> anchor 2026-01-27, window start 2026-01-20; the 2026-01-06 row drops.
    kept = temporal.filter_window(rows, temporal.TimeWindow(weeks=1))
    assert [r["timestamp"] for r in kept] == ["2026-01-27T20:00:00+00:00"]


# ----------------------- integration (needs Neo4j) -----------------------

@pytest.fixture
def client():
    c = Neo4jClient(
        uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        user=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "testpassword"),
    )
    try:
        c.execute_read("RETURN 1 AS ok")
    except Exception:  # noqa: BLE001
        c.close()
        pytest.skip("Neo4j not available")
    schema.bootstrap_schema(c)
    ontology.load_ontology(c)
    members.ingest_members(c)
    from app.retrieval import embeddings
    embeddings.embed_and_index(c, FakeEmbedProvider())
    yield c
    c.close()


def test_windowed_retrieve_attaches_trends(client):
    window = temporal.TimeWindow(weeks=3, as_of=_dt("2026-01-28T00:00:00+00:00"))
    bundle = service.retrieve(
        client, FakeEmbedProvider(), "member_ava", "progress review", window=window
    )
    assert bundle.trends is not None, "windowed retrieval must attach a TrendSummary"
    trends = bundle.trends
    assert trends.window_weeks == 3
    # Windowed adherence excludes the poor 2026-01-06 record (2/4): 10 of 12 -> ~83.33%,
    # higher than the full-history 75%.
    assert trends.adherence_percentage == pytest.approx(83.33, abs=0.5)
    assert trends.adherence_percentage > 75.0
    # Two workouts fall in the window (2026-01-13, 2026-01-27); 2026-01-06 is excluded.
    assert trends.workout_count == 2


def test_windowed_retrieve_scopes_facts_to_the_window(client):
    window = temporal.TimeWindow(weeks=3, as_of=_dt("2026-01-28T00:00:00+00:00"))
    bundle = service.retrieve(
        client, FakeEmbedProvider(), "member_ava", "progress review", window=window
    )
    blob = "\n".join(bundle.subgraph_facts)
    # Out-of-window time-series records must not appear...
    assert "2026-01-06" not in blob, "a pre-window record leaked into the scoped facts"
    # ...while in-window activity is present.
    assert "2026-01-27" in blob


def test_unwindowed_retrieve_leaves_trends_none(client):
    bundle = service.retrieve(client, FakeEmbedProvider(), "member_ava", "progress review")
    assert bundle.trends is None, "trends only computed when a window is supplied"


def test_trend_summary_lines_feed_the_context(client):
    window = temporal.TimeWindow(weeks=3, as_of=_dt("2026-01-28T00:00:00+00:00"))
    bundle = service.retrieve(
        client, FakeEmbedProvider(), "member_ava", "progress review", window=window
    )
    assert bundle.trends is not None
    assert bundle.trends.summary_lines, "expected human-readable trend summary lines"
    joined = "\n".join(bundle.context_items)
    included = any(line in joined for line in bundle.trends.summary_lines)
    assert included, "trend summary lines should be included in the fused context"
