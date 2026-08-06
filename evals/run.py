"""Ticket 019 — Evals CLI: ``python -m evals.run``.

Loads the versioned dataset, runs retrieval + safety evaluation against the configured Neo4j and
LLM provider, prints a human-readable markdown report and writes a machine-parseable JSON artifact
(for CI to parse). The process exit code is non-zero when the safety eval fails — any recommended
forbidden exercise is a hard failure — so CI can gate on it.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.config import get_settings
from app.graph.client import get_client
from app.llm import get_provider
from app.llm.provider import LLMProvider
from evals import runner, scoring
from evals.dataset import load_dataset
from evals.provider import DeterministicProvider

# Default location for the JSON report artifact.
DEFAULT_ARTIFACT_PATH: Path = Path(__file__).parent / "reports" / "report.json"


def render_report(report: scoring.EvalReport) -> str:
    """Return the human-readable markdown rendering of ``report``."""
    return report.to_markdown()


def write_artifact(report: scoring.EvalReport, path: Path) -> None:
    """Write ``report`` as a machine-parseable JSON artifact at ``path`` (creating parent dirs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")


def _resolve_provider(offline: bool) -> LLMProvider:
    """Return the deterministic offline provider when requested, else the configured provider.

    ``--offline`` (or ``EVALS_OFFLINE=1``) selects an in-repo deterministic provider so the eval
    runs with no OpenAI key and produces byte-stable scores — the path CI and demos use.
    """
    if offline or os.environ.get("EVALS_OFFLINE") == "1":
        return DeterministicProvider()
    return get_provider(get_settings())


def main(argv: list[str] | None = None) -> int:
    """Run the evals end-to-end; return 0 on a passing safety eval, 1 otherwise."""
    parser = argparse.ArgumentParser(prog="python -m evals.run", description="Run the eval suite.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use the deterministic in-repo provider (no OpenAI key needed).",
    )
    args = parser.parse_args(argv)

    client = get_client()
    try:
        provider = _resolve_provider(args.offline)
        report = runner.run_evals(client, provider, load_dataset())
    finally:
        client.close()

    print(render_report(report))
    write_artifact(report, DEFAULT_ARTIFACT_PATH)
    print(f"\nWrote JSON artifact to {DEFAULT_ARTIFACT_PATH}")
    return 0 if report.safety_passed() else 1


if __name__ == "__main__":
    raise SystemExit(main())
