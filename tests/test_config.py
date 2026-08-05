"""Ticket 001 — config contract.

Settings must load Neo4j + OpenAI config from the environment, and fail fast (raise a
pydantic ValidationError) when a required Neo4j var is missing.
"""
import pytest
from pydantic import ValidationError

from app.config import Settings

REQUIRED = ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"]


def test_valid_settings_parse(monkeypatch):
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "testpassword")
    s = Settings(_env_file=None)
    assert s.neo4j_uri == "bolt://localhost:7687"
    assert s.neo4j_user == "neo4j"
    assert s.neo4j_password == "testpassword"


def test_missing_required_var_fails_fast(monkeypatch):
    for var in REQUIRED:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_llm_provider_defaults_to_openai(monkeypatch):
    for var in REQUIRED:
        monkeypatch.setenv(var, "x")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    s = Settings(_env_file=None)
    assert s.llm_provider == "openai"
