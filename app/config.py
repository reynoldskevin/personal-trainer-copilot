"""Application configuration.

`Settings` reads all runtime configuration from environment variables (or an optional
`.env` file) via pydantic-settings. Required Neo4j connection details have no defaults, so
constructing `Settings` without them raises a `pydantic.ValidationError` — the app fails
fast rather than starting in a broken state.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Neo4j (required — fail fast if absent)
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str

    # LLM
    llm_provider: str = "openai"
    openai_api_key: str | None = None

    # Observability (optional — LangFuse tracing is opt-in and never a hard dependency)
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return a cached `Settings` instance.

    Cached for cheap reuse across the app. Code paths that must reflect live environment
    changes (e.g. the health probe) should read the environment directly rather than rely
    on this cache.
    """
    return Settings()
