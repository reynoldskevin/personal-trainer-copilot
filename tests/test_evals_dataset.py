"""Ticket 018 — Evals dataset (retrieval quality + safety).

Contract (`evals.dataset`):
- `RetrievalCase` / `SafetyCase` / `EvalDataset` — pydantic models for the labeled cases.
- `load_dataset(path=None) -> EvalDataset` — load + validate the shipped, versioned JSON dataset.
- `parse_dataset(data: dict) -> EvalDataset` — validate an in-memory payload (used to prove the
  loader rejects malformed/mislabeled data).
- Reference sets derived from the in-repo seed + ontology: `KNOWN_MEMBER_IDS`, `KNOWN_INJURY_IDS`,
  `KNOWN_EXERCISE_IDS`, `ALL_NODE_IDS`, and `contraindications_for(injury_id) -> set[str]`.

The loader enforces dataset integrity WITHOUT a database, validating every label against the
curated seed/ontology constants. All tests here are pure (no Neo4j, no LLM).
"""
import copy

import pytest

from evals import dataset

# --------------------------------------------------------------------------- shipped dataset

def test_shipped_dataset_loads_and_meets_minimums():
    ds = dataset.load_dataset()
    assert isinstance(ds, dataset.EvalDataset)
    assert ds.version, "dataset must declare a version"
    assert len(ds.retrieval_cases) >= 10, "need >=10 retrieval-quality cases"
    assert len(ds.safety_cases) >= 5, "need >=5 safety cases"


def test_all_case_ids_are_unique():
    ds = dataset.load_dataset()
    ids = [c.id for c in ds.retrieval_cases] + [c.id for c in ds.safety_cases]
    assert len(ids) == len(set(ids)), "case ids must be unique across the dataset"


def test_retrieval_cases_reference_known_ids_with_labels():
    ds = dataset.load_dataset()
    for case in ds.retrieval_cases:
        assert case.member_id in dataset.KNOWN_MEMBER_IDS, f"{case.id}: unknown member"
        assert case.query.strip(), f"{case.id}: empty query"
        assert case.expected_node_ids, f"{case.id}: expected nodes must be labeled"
        for node_id in case.expected_node_ids:
            assert node_id in dataset.ALL_NODE_IDS, f"{case.id}: unknown expected node {node_id}"


def test_safety_labels_are_genuine_contraindications():
    # Every forbidden exercise in a safety case must be a TRUE contraindication for that injury
    # per the ontology — otherwise the "safety" label is fiction and the eval is meaningless.
    ds = dataset.load_dataset()
    for case in ds.safety_cases:
        assert case.injury_id in dataset.KNOWN_INJURY_IDS, f"{case.id}: unknown injury"
        assert case.forbidden_exercise_ids, f"{case.id}: forbidden set must be labeled"
        real = dataset.contraindications_for(case.injury_id)
        for ex in case.forbidden_exercise_ids:
            assert ex in real, f"{case.id}: {ex} is not contraindicated for {case.injury_id}"


# --------------------------------------------------------------------------- loader is a real gate

def _valid_payload() -> dict:
    """A minimal valid payload (loader accepts it) to mutate in the rejection tests."""
    return copy.deepcopy(
        {
            "version": "test-1",
            "retrieval_cases": [
                {
                    "id": f"r{i}",
                    "query": "shoulder rehab",
                    "member_id": "member_ava",
                    "expected_node_ids": ["rotator_cuff_tear"],
                }
                for i in range(10)
            ],
            "safety_cases": [
                {
                    "id": f"s{i}",
                    "injury_id": "rotator_cuff_tear",
                    "forbidden_exercise_ids": ["overhead_press"],
                }
                for i in range(5)
            ],
        }
    )


def test_parse_accepts_a_valid_payload():
    ds = dataset.parse_dataset(_valid_payload())
    assert len(ds.retrieval_cases) == 10
    assert len(ds.safety_cases) == 5


def test_loader_rejects_too_few_cases():
    bad = _valid_payload()
    bad["retrieval_cases"] = bad["retrieval_cases"][:3]
    with pytest.raises(dataset.EvalDatasetError):
        dataset.parse_dataset(bad)


def test_loader_rejects_unknown_member():
    bad = _valid_payload()
    bad["retrieval_cases"][0]["member_id"] = "member_nobody"
    with pytest.raises(dataset.EvalDatasetError):
        dataset.parse_dataset(bad)


def test_loader_rejects_unknown_expected_node():
    bad = _valid_payload()
    bad["retrieval_cases"][0]["expected_node_ids"] = ["node_that_does_not_exist"]
    with pytest.raises(dataset.EvalDatasetError):
        dataset.parse_dataset(bad)


def test_loader_rejects_mislabeled_safety_case():
    # push_up is safe for a rotator cuff tear — labeling it forbidden is a false safety label.
    bad = _valid_payload()
    bad["safety_cases"][0]["forbidden_exercise_ids"] = ["push_up"]
    with pytest.raises(dataset.EvalDatasetError):
        dataset.parse_dataset(bad)


def test_loader_rejects_duplicate_case_ids():
    bad = _valid_payload()
    bad["retrieval_cases"][1]["id"] = bad["retrieval_cases"][0]["id"]
    with pytest.raises(dataset.EvalDatasetError):
        dataset.parse_dataset(bad)
