"""Ticket 023 — Documentation & submission polish.

Contract: the README is the front door — a new reader must be able to boot and demo the system
from it, and every doc/entrypoint it references must actually exist and be consistent with the
code. These tests pin that: all local links resolve, the required sections are present, the seed +
run + OpenAPI entrypoints named in the README are real, and commit conventions are documented.

Pure filesystem/text assertions — no Neo4j, no LLM.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

# Markdown inline links: [text](target)
_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _local_link_targets(text: str) -> list[str]:
    """Return the local (non-URL) file paths the README links to, anchors stripped."""
    targets: list[str] = []
    for raw in _LINK_RE.findall(text):
        target = raw.strip()
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        path_part = target.split("#", 1)[0]
        if not path_part:  # pure in-page anchor (e.g. "#quickstart")
            continue
        targets.append(path_part)
    return targets


# --------------------------------------------------------------------------- README exists & links

def test_readme_exists_and_is_substantial():
    assert README.is_file(), "README.md must exist at the repo root"
    assert len(_readme().strip()) > 400, "README should be a real guide, not a stub"


def test_all_local_links_resolve():
    missing = [rel for rel in _local_link_targets(_readme()) if not (ROOT / rel).exists()]
    assert not missing, f"README links to missing files: {missing}"


def test_readme_links_are_nonempty_docs():
    empty = [
        rel
        for rel in _local_link_targets(_readme())
        if (ROOT / rel).is_file() and (ROOT / rel).stat().st_size == 0
    ]
    assert not empty, f"README links to empty docs: {empty}"


# --------------------------------------------------------------------------- required sections

def test_required_sections_present():
    text = _readme().lower()
    for needle in ("quickstart", "seed", "architecture", "commit", "eval", "api"):
        assert needle in text, f"README is missing a section covering: {needle!r}"


def test_architecture_and_a_docs_page_are_linked():
    targets = _local_link_targets(_readme())
    assert "ARCHITECTURE.md" in targets, "README must link the architecture doc"
    assert any(t.startswith("docs/") for t in targets), "README must link at least one docs/ page"


# --------------------------------------------------------------------------- entrypoints are real

def test_seed_entrypoint_is_documented_and_exists():
    assert "python -m app.ingestion.seed" in _readme(), "README must document the seed command"
    assert (ROOT / "app" / "ingestion" / "seed.py").is_file(), "seed module must exist"


def test_run_and_api_pointers_documented():
    text = _readme()
    assert "docker compose up" in text, "README must document the docker compose run"
    assert "uvicorn app.main:app" in text, "README must document the local run command"
    assert "/docs" in text, "README must point at the OpenAPI docs (/docs)"
    assert "/health" in text, "README must document the health check"


def test_commit_conventions_documented():
    text = _readme()
    # Conventional-commit style scoped by ticket number — the convention this repo uses.
    assert "feat(" in text and "test(" in text, "README must document the commit convention"
