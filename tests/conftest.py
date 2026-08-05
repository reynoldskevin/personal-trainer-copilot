"""Shared test config. Seeds env defaults BEFORE any `app` import so modules that
construct settings at import time can load. Individual tests may override via monkeypatch."""
import os

os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "testpassword")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault("LLM_PROVIDER", "openai")
