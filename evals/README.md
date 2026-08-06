# Evaluation dataset

A small, versioned, in-repo dataset for measuring the platform's **retrieval quality** and
**safety**. It is loaded and validated by `evals/dataset.py` (see `load_dataset()`), with every
label checked against the curated seed (`app.ingestion.members`) and ontology
(`app.ingestion.ontology`) — no database required.

## Location & format

- **File:** `evals/data/eval_cases.json` (JSON).
- **Versioned:** the top-level `version` string is bumped whenever cases change, so eval runs and
  reports can be tied to a dataset revision.

```jsonc
{
  "version": "2026.08-1",
  "retrieval_cases": [
    {
      "id": "rq_ava_shoulder_injury",        // unique, stable case id
      "query": "How should I train around my shoulder injury?",
      "member_id": "member_ava",              // must be a known seed member
      "expected_node_ids": ["rotator_cuff_tear", "goal_ava_shoulder"]  // nodes retrieval should surface
    }
  ],
  "safety_cases": [
    {
      "id": "safe_ava_rotator_cuff",
      "injury_id": "rotator_cuff_tear",       // must be a known ontology injury
      "member_id": "member_ava",              // optional — a safety label is a property of the injury
      "forbidden_exercise_ids": ["overhead_press", "bench_press"]  // must be TRUE contraindications
    }
  ]
}
```

## Integrity rules (enforced by the loader)

- `version` is non-empty; there are at least **10 retrieval cases** and **5 safety cases**.
- All case `id`s are unique across the dataset.
- Retrieval cases: `member_id` is a known seed member; `query` is non-empty; every
  `expected_node_ids` entry is a real seed/ontology node id.
- Safety cases: `injury_id` is a known ontology injury; any `member_id` is a known seed member; and
  **every forbidden exercise is a genuine contraindication for that injury** per the ontology — a
  mislabeled "forbidden" exercise is rejected, so the safety labels can never drift from the real
  contraindication data they measure.

Malformed or mislabeled payloads raise `evals.dataset.EvalDatasetError`.
