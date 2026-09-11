"""Offline tests for SearchTool — a fake client stands in for TavilyClient, so this
suite never touches the network (see CLAUDE.md: no live calls in the test suite).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tavily.errors import BadRequestError, InvalidAPIKeyError, UsageLimitExceededError

from tools.base import ToolErrorCategory
from tools.search import SearchInput, SearchTool

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tavily_stripe.json"


class _FakeTavilyClient:
    """Stands in for tavily.TavilyClient: returns a canned response or raises."""

    def __init__(
        self, response: dict[str, Any] | None = None, raises: Exception | None = None
    ) -> None:
        self._response = response
        self._raises = raises

    def search(
        self, query: str, max_results: int | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        if self._raises is not None:
            raise self._raises
        assert self._response is not None
        return self._response


def _load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text())


def test_parses_fixture_into_sources() -> None:
    tool = SearchTool(client=_FakeTavilyClient(response=_load_fixture()))

    result = tool.run(SearchInput(query="Stripe company overview"))

    assert result.ok is True
    assert result.value is not None
    assert len(result.value) == 3
    first = result.value[0]
    assert first.url == "https://stripe.com/about"
    assert first.title == "About Stripe"
    assert "financial infrastructure" in first.content


def test_auth_failure_maps_to_permanent() -> None:
    tool = SearchTool(client=_FakeTavilyClient(raises=InvalidAPIKeyError("bad key")))

    result = tool.run(SearchInput(query="Stripe"))

    assert result.ok is False
    assert result.error_category == ToolErrorCategory.PERMANENT


def test_bad_request_maps_to_permanent() -> None:
    tool = SearchTool(client=_FakeTavilyClient(raises=BadRequestError("bad request")))

    result = tool.run(SearchInput(query="Stripe"))

    assert result.ok is False
    assert result.error_category == ToolErrorCategory.PERMANENT


def test_usage_limit_maps_to_transient() -> None:
    tool = SearchTool(
        client=_FakeTavilyClient(raises=UsageLimitExceededError("limit hit"))
    )

    result = tool.run(SearchInput(query="Stripe"))

    assert result.ok is False
    assert result.error_category == ToolErrorCategory.TRANSIENT


def test_malformed_response_maps_to_validation() -> None:
    tool = SearchTool(
        client=_FakeTavilyClient(response={"results": [{"title": "no url field"}]})
    )

    result = tool.run(SearchInput(query="Stripe"))

    assert result.ok is False
    assert result.error_category == ToolErrorCategory.VALIDATION
