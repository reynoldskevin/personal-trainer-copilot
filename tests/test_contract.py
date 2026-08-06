"""Frontend↔backend contract: the hand-maintained TypeScript response types
(`frontend/components/types.ts`) MUST agree with the API's OpenAPI schema.

Why this exists
---------------
The Next.js frontend reads JSON off the FastAPI endpoints through TypeScript
interfaces that are maintained *by hand*, in a separate file from the Pydantic
models that actually shape the wire. Nothing else in the suite ties the two
together, so a backend field rename (e.g. ``biometrics`` → ``biometric_points``)
would leave the frontend reading ``undefined`` at runtime with **no** failing
test and **no** type error — the exact silent-drift hole called out in the M1+M2
coverage review.

This test closes it. It emits ``app.openapi()`` (pure — no DB, no network) and
compares every frontend interface field against the mapped backend schema
component. A rename or added/removed field on *either* side breaks this test.

It is a pure test: it runs in a clean CI checkout with no Neo4j.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.main import app

TYPES_TS = Path(__file__).resolve().parents[1] / "frontend" / "components" / "types.ts"

# Frontend interface  ->  (backend OpenAPI component, mode).
#   "exact"  : the two field sets must be identical (models the frontend fully owns).
#   "subset" : every frontend field must exist on the backend, but the backend may
#              carry extra fields the frontend deliberately ignores.
# Frontend-only UI types (ChatTurn, TabId) have no backend counterpart and are omitted.
MAPPING: dict[str, tuple[str, str]] = {
    "Member": ("MemberSummary", "exact"),
    "RecentWorkout": ("WorkoutSummary", "exact"),
    "AdherenceEntry": ("AdherenceSummary", "exact"),
    "BiometricPoint": ("BiometricPoint", "exact"),
    "MemberDetail": ("MemberDetail", "exact"),
    "PlanExercise": ("PlannedExercise", "exact"),
    "WorkoutPlan": ("WorkoutPlan", "exact"),
    # RetrievalBundle intentionally omits the backend ContextBundle's `trends`
    # field (the frontend renders trends via the InsightReport instead).
    "RetrievalBundle": ("ContextBundle", "subset"),
    "RiskFlag": ("RiskFlag", "exact"),
    "BiometricTrend": ("BiometricTrend", "exact"),
    "TrendSummary": ("TrendSummary", "exact"),
    "InsightReport": ("InsightReport", "exact"),
    "ChatAnswer": ("ChatAnswer", "exact"),
}


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)  # block comments
    src = re.sub(r"//[^\n]*", "", src)  # line comments
    return src


def _parse_interfaces(src: str) -> dict[str, dict[str, object]]:
    """Return {interface_name: {"extends": str|None, "fields": set[str]}}.

    Handles ``export interface X extends Y { ... }`` with one field declaration
    per line (``name: T;`` or ``name?: T;``). Nested object-literal field types
    are not used in this file, so a brace-depth counter is unnecessary — but we
    still ignore anything that isn't a top-level ``ident[?]:`` declaration.
    """
    src = _strip_comments(src)
    interfaces: dict[str, dict[str, object]] = {}
    header = re.compile(r"export\s+interface\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{")
    field = re.compile(r"^\s*(\w+)\??\s*:")
    pos = 0
    while True:
        m = header.search(src, pos)
        if not m:
            break
        name, base = m.group(1), m.group(2)
        # Body runs to the matching closing brace (flat — no nested braces here).
        end = src.index("}", m.end())
        body = src[m.end() : end]
        fields = {fm.group(1) for line in body.splitlines() if (fm := field.match(line))}
        interfaces[name] = {"extends": base, "fields": fields}
        pos = end + 1
    return interfaces


def _resolve_fields(name: str, interfaces: dict[str, dict[str, object]]) -> set[str]:
    """Full field set including inherited fields from an ``extends`` base."""
    info = interfaces[name]
    fields: set[str] = set(info["fields"])  # type: ignore[arg-type]
    base = info["extends"]
    if base:
        assert base in interfaces, f"{name} extends unknown interface {base}"
        fields |= _resolve_fields(str(base), interfaces)
    return fields


@pytest.fixture(scope="module")
def ts_interfaces() -> dict[str, dict[str, object]]:
    assert TYPES_TS.exists(), f"frontend types file missing: {TYPES_TS}"
    return _parse_interfaces(TYPES_TS.read_text())


@pytest.fixture(scope="module")
def openapi_schemas() -> dict[str, dict]:
    return app.openapi()["components"]["schemas"]


def test_mapping_covers_every_shared_frontend_interface(ts_interfaces):
    """Guards the contract itself: any new response interface in types.ts must be
    mapped here (or explicitly excluded), so a future model can't slip the net."""
    # UI-only types with no wire counterpart.
    frontend_only = {"ChatTurn"}
    unmapped = set(ts_interfaces) - set(MAPPING) - frontend_only
    assert not unmapped, (
        f"types.ts interfaces are not covered by the contract mapping: {sorted(unmapped)}. "
        "Add them to MAPPING (or to frontend_only if they are UI-only)."
    )


@pytest.mark.parametrize("interface", sorted(MAPPING))
def test_interface_matches_backend_schema(interface, ts_interfaces, openapi_schemas):
    component, mode = MAPPING[interface]
    assert interface in ts_interfaces, f"interface {interface} vanished from types.ts"
    assert component in openapi_schemas, (
        f"backend schema component {component!r} is gone — the API renamed or removed the model "
        f"the frontend {interface} maps to."
    )

    ts_fields = _resolve_fields(interface, ts_interfaces)
    api_fields = set(openapi_schemas[component].get("properties", {}))

    missing_on_backend = ts_fields - api_fields
    assert not missing_on_backend, (
        f"{interface} → {component}: frontend expects field(s) {sorted(missing_on_backend)} the "
        f"API does not send. A backend rename/removal would break the frontend silently at runtime."
    )
    if mode == "exact":
        extra_on_backend = api_fields - ts_fields
        assert not extra_on_backend, (
            f"{interface} → {component}: API sends field(s) {sorted(extra_on_backend)} the frontend "
            f"type does not declare. Add them to types.ts, or mark the mapping 'subset' if the "
            f"frontend intentionally ignores them."
        )
