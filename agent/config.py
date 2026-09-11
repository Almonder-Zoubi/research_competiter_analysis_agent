"""Runtime configuration, loaded from .env.

Import `get_settings()` rather than constructing Settings() directly — the
cache means the .env file (and its validation) is only read once per process.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str
    tavily_api_key: str

    model_fast: str = "claude-haiku-4-5"
    model_smart: str = "claude-sonnet-5"

    # Budget guards: the loop must be unable to run away. See CLAUDE.md.
    max_steps: int = Field(default=25, gt=0)
    max_sources: int = Field(default=15, gt=0)
    run_timeout_seconds: int = Field(default=300, gt=0)

    database_url: str = "sqlite:///data/research.db"
    reports_dir: str = "reports"  # where --deep-research PDFs land; gitignored

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"


@lru_cache
def get_settings() -> Settings:
    # anthropic_api_key/tavily_api_key have no defaults because they must come
    # from .env — mypy can't see that pydantic-settings supplies them at
    # runtime, so it flags this call as missing required args.
    return Settings()  # type: ignore[call-arg]
