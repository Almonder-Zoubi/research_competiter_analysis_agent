"""Config tests are pure validation logic — no .env, no network, no cost.

`_env_file=None` stops Settings from reading the real .env, so these pass
the same way on a fresh clone as they do here.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from agent.config import Settings


def make_settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        anthropic_api_key="test-key",
        tavily_api_key="test-key",
        **overrides,
    )


def test_requires_api_keys() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_defaults() -> None:
    settings = make_settings()
    assert settings.model_fast == "claude-haiku-4-5"
    assert settings.model_smart == "claude-sonnet-5"
    assert settings.max_steps == 25
    assert settings.max_sources == 15
    assert settings.run_timeout_seconds == 300
    assert settings.database_url == "sqlite:///data/research.db"
    assert settings.langfuse_public_key is None


@pytest.mark.parametrize(
    "field_name,value",
    [("max_steps", 0), ("max_sources", -1), ("run_timeout_seconds", 0)],
)
def test_budget_guards_must_be_positive(field_name: str, value: int) -> None:
    with pytest.raises(ValidationError):
        make_settings(**{field_name: value})
