"""Ticket 021 — CI pipeline config test.

The repository's remote is GitLab (``labs.gauntletai.com``), so CI runs as GitLab
CI (``.gitlab-ci.yml``), not GitHub Actions — a GitHub workflow would never execute
here and the ticket's "green CI run" criterion would be unmeetable. This test locks
the pipeline's shape: lint, type-check, the full pytest suite backed by a real Neo4j
service, and the frontend checks — with the LLM mocked and no live secrets in the repo.

It parses the YAML structurally (a malformed pipeline fails the test), rather than
grepping raw text.
"""
from __future__ import annotations

from pathlib import Path

import yaml

CI_FILE = Path(__file__).resolve().parents[1] / ".gitlab-ci.yml"


def _load() -> dict:
    assert CI_FILE.exists(), f"CI pipeline file missing: {CI_FILE}"
    data = yaml.safe_load(CI_FILE.read_text())
    assert isinstance(data, dict), ".gitlab-ci.yml must parse to a mapping of jobs/config"
    return data


def _jobs(config: dict) -> dict[str, dict]:
    """Job entries are the top-level mappings that carry a `script`."""
    return {
        name: body
        for name, body in config.items()
        if isinstance(body, dict) and "script" in body
    }


def _all_script_lines(config: dict) -> list[str]:
    lines: list[str] = []
    for body in _jobs(config).values():
        for key in ("before_script", "script", "after_script"):
            block = body.get(key, [])
            if isinstance(block, str):
                lines.append(block)
            elif isinstance(block, list):
                lines.extend(str(s) for s in block)
    return lines


def _flatten(value) -> str:
    return yaml.safe_dump(value)


def test_pipeline_parses_and_has_jobs():
    config = _load()
    assert _jobs(config), "pipeline defines no jobs with a `script`"


def test_runs_lint_typecheck_and_full_test_suite():
    scripts = "\n".join(_all_script_lines(_load()))
    assert "ruff check" in scripts, "pipeline must run `ruff check`"
    assert "mypy" in scripts, "pipeline must run `mypy`"
    # The bare pytest invocation runs the WHOLE suite, including the integration
    # tests that only run when Neo4j is reachable (the point of the service below).
    assert "pytest" in scripts, "pipeline must run the pytest suite"


def test_neo4j_service_available_to_integration_tests():
    config = _load()
    blob = _flatten(config)
    assert "neo4j" in blob.lower(), "no neo4j service/image referenced in the pipeline"
    # A `services:` entry (job-level or default) is what makes Neo4j reachable to the
    # integration tests; assert one exists and points at a neo4j image.
    services_blobs: list[str] = []
    for body in config.values():
        if isinstance(body, dict) and "services" in body:
            services_blobs.append(_flatten(body["services"]).lower())
    if "default" in config and isinstance(config["default"], dict):
        default_services = config["default"].get("services")
        if default_services is not None:
            services_blobs.append(_flatten(default_services).lower())
    assert any("neo4j" in s for s in services_blobs), (
        "expected a `services:` entry running a neo4j image so integration tests do not skip"
    )
    # The test suite reaches Neo4j via NEO4J_* env; the pipeline must provide them.
    assert "NEO4J_URI" in blob, "pipeline must set NEO4J_URI for the test suite"
    assert "NEO4J_PASSWORD" in blob, "pipeline must set NEO4J_PASSWORD for the test suite"


def test_frontend_checks_run():
    scripts = "\n".join(_all_script_lines(_load()))
    assert "npm" in scripts, "pipeline must run the frontend npm checks"
    assert "tsc" in scripts, "pipeline must type-check the frontend (tsc --noEmit)"


def test_llm_mocked_and_no_live_secret_in_repo():
    """Tests use a fake LLM; the pipeline must NOT embed a real OpenAI key.

    A dummy placeholder value is expected (the fakes never call OpenAI). Guard against
    a real ``sk-...proj/live`` key being committed into the pipeline file.
    """
    config = _load()
    blob = _flatten(config)
    assert "OPENAI_API_KEY" in blob, "pipeline must define a (dummy) OPENAI_API_KEY for tests"
    raw = CI_FILE.read_text()
    # Reject anything that looks like a real key literal; a test placeholder must be obvious.
    for token in ("sk-proj-", "sk-svcacct-"):
        assert token not in raw, f"a live-looking OpenAI key ({token}...) is committed in {CI_FILE.name}"
