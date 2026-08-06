"""Ticket 018 — Evals dataset: schema, reference sets and validating loader.

A small, **versioned**, in-repo evaluation dataset with two kinds of labeled cases:

- **retrieval-quality** cases — a coach query about a specific seed member, labeled with the graph
  node ids that good retrieval should surface for that member (:class:`RetrievalCase`);
- **safety** cases — an injury labeled with the exercises that must **never** be recommended for a
  member with that injury (:class:`SafetyCase`).

The dataset lives at :data:`DATASET_PATH` (JSON). The loader validates every label against the
curated seed (:mod:`app.ingestion.members`) and ontology (:mod:`app.ingestion.ontology`) constants
— entirely in-repo, needing **no database** — so a fictional member id, an unknown expected node,
a duplicate case id, too few cases, or a "forbidden" exercise that is not actually contraindicated
for its injury are all rejected with :class:`EvalDatasetError`. This keeps the labels honest: the
safety set can never drift away from the real contraindication ontology it is meant to measure.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ingestion import members, ontology

# The shipped dataset and the minimum case counts the ticket requires.
DATASET_PATH: Path = Path(__file__).parent / "data" / "eval_cases.json"
MIN_RETRIEVAL_CASES: int = 10
MIN_SAFETY_CASES: int = 5


class EvalDatasetError(ValueError):
    """Raised when an eval dataset fails integrity validation."""


# --------------------------------------------------------------------------- reference sets

KNOWN_MEMBER_IDS: set[str] = {m["id"] for m in members.MEMBER_SEED}
KNOWN_INJURY_IDS: set[str] = {i["id"] for i in ontology.INJURIES}
KNOWN_EXERCISE_IDS: set[str] = {e["id"] for e in ontology.EXERCISES}


def _all_node_ids() -> set[str]:
    """Every stable node id present in the curated seed + ontology (for expected-node labels)."""
    ids: set[str] = set()
    ids |= KNOWN_INJURY_IDS
    ids |= KNOWN_EXERCISE_IDS
    for member in members.MEMBER_SEED:
        ids.add(member["id"])
        ids.update(g["id"] for g in member["goals"])
        ids.update(w["id"] for w in member["workouts"])
        ids.update(b["id"] for b in member["biometrics"])
        ids.update(a["id"] for a in member["adherence"])
        ids.update(c["id"] for c in member["chats"])
        ids.update(t["id"] for t in member["transcripts"])
    return ids


ALL_NODE_IDS: set[str] = _all_node_ids()


def _contraindication_map() -> dict[str, set[str]]:
    """Map each injury id to the set of exercises contraindicated for it, per the ontology."""
    mapping: dict[str, set[str]] = {}
    for row in ontology.CONTRAINDICATIONS:
        mapping.setdefault(row["injury_id"], set()).add(row["exercise_id"])
    return mapping


_CONTRA_MAP: dict[str, set[str]] = _contraindication_map()


def contraindications_for(injury_id: str) -> set[str]:
    """Return the set of exercises contraindicated for ``injury_id`` (empty if none/unknown)."""
    return set(_CONTRA_MAP.get(injury_id, set()))


# --------------------------------------------------------------------------- models


class RetrievalCase(BaseModel):
    """A retrieval-quality case: a member query labeled with the nodes retrieval should surface."""

    id: str
    query: str
    member_id: str
    expected_node_ids: list[str]


class SafetyCase(BaseModel):
    """A safety case: an injury labeled with exercises that must never be recommended for it.

    ``member_id`` is optional — a safety label is a property of the injury, not of one member, so
    a case may or may not be tied to a specific seed member.
    """

    id: str
    injury_id: str
    forbidden_exercise_ids: list[str]
    member_id: str | None = None


class EvalDataset(BaseModel):
    """The full, versioned evaluation dataset."""

    version: str
    retrieval_cases: list[RetrievalCase]
    safety_cases: list[SafetyCase]


# --------------------------------------------------------------------------- validation + loading


def _validate(ds: EvalDataset) -> None:
    """Enforce dataset integrity against the seed/ontology constants; raise on any violation."""
    if not ds.version.strip():
        raise EvalDatasetError("dataset version must be a non-empty string")
    if len(ds.retrieval_cases) < MIN_RETRIEVAL_CASES:
        raise EvalDatasetError(
            f"need >={MIN_RETRIEVAL_CASES} retrieval cases, got {len(ds.retrieval_cases)}"
        )
    if len(ds.safety_cases) < MIN_SAFETY_CASES:
        raise EvalDatasetError(
            f"need >={MIN_SAFETY_CASES} safety cases, got {len(ds.safety_cases)}"
        )

    ids = [c.id for c in ds.retrieval_cases] + [c.id for c in ds.safety_cases]
    if len(ids) != len(set(ids)):
        raise EvalDatasetError("case ids must be unique across the dataset")

    for rc in ds.retrieval_cases:
        if rc.member_id not in KNOWN_MEMBER_IDS:
            raise EvalDatasetError(f"{rc.id}: unknown member '{rc.member_id}'")
        if not rc.query.strip():
            raise EvalDatasetError(f"{rc.id}: query must be non-empty")
        if not rc.expected_node_ids:
            raise EvalDatasetError(f"{rc.id}: expected_node_ids must be labeled")
        for node_id in rc.expected_node_ids:
            if node_id not in ALL_NODE_IDS:
                raise EvalDatasetError(f"{rc.id}: unknown expected node '{node_id}'")

    for sc in ds.safety_cases:
        if sc.injury_id not in KNOWN_INJURY_IDS:
            raise EvalDatasetError(f"{sc.id}: unknown injury '{sc.injury_id}'")
        if sc.member_id is not None and sc.member_id not in KNOWN_MEMBER_IDS:
            raise EvalDatasetError(f"{sc.id}: unknown member '{sc.member_id}'")
        if not sc.forbidden_exercise_ids:
            raise EvalDatasetError(f"{sc.id}: forbidden_exercise_ids must be labeled")
        real = contraindications_for(sc.injury_id)
        for ex in sc.forbidden_exercise_ids:
            if ex not in real:
                raise EvalDatasetError(
                    f"{sc.id}: '{ex}' is not contraindicated for '{sc.injury_id}' — "
                    "safety labels must match the ontology's real contraindications"
                )


def parse_dataset(data: dict[str, Any]) -> EvalDataset:
    """Validate an in-memory dataset payload, returning a checked :class:`EvalDataset`.

    Raises :class:`EvalDatasetError` on either a schema/type error or an integrity violation.
    """
    try:
        ds = EvalDataset.model_validate(data)
    except ValidationError as exc:  # normalize pydantic errors to our dataset error type
        raise EvalDatasetError(str(exc)) from exc
    _validate(ds)
    return ds


def load_dataset(path: Path | None = None) -> EvalDataset:
    """Load and validate the versioned JSON eval dataset (default :data:`DATASET_PATH`)."""
    target = path if path is not None else DATASET_PATH
    with target.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return parse_dataset(data)
