"""Offline tests for FetchTool — a fake httpx-like client stands in, so this
suite never touches the network (see CLAUDE.md: no live calls in the test
suite). The fixture page has nav/footer boilerplate around a real article to
prove trafilatura's cleanup actually runs, not just that *some* text comes back.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from tools.base import ToolErrorCategory
from tools.fetch import FetchInput, FetchTool

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "example_page.html"
PAGE_URL = "https://example-acme.test/about"
ROBOTS_ALLOW_ALL = "User-agent: *\nAllow: /\n"
ROBOTS_DISALLOW_ALL = "User-agent: *\nDisallow: /\n"


def _load_fixture_html() -> str:
    return FIXTURE_PATH.read_text()


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeHttpClient:
    """Queues one canned response (or exception) per call to .get(), in order —
    lets a test script a robots.txt fetch followed by the page fetch, including
    retries."""

    def __init__(self, responses: list[_FakeResponse | Exception]) -> None:
        self._responses = list(responses)
        self.urls_requested: list[str] = []

    def get(self, url: str, **kwargs: object) -> httpx.Response:
        self.urls_requested.append(url)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item  # type: ignore[return-value]


def test_extracts_clean_text_and_strips_boilerplate() -> None:
    client = _FakeHttpClient(
        [
            _FakeResponse(200, ROBOTS_ALLOW_ALL),
            _FakeResponse(200, _load_fixture_html()),
        ]
    )
    tool = FetchTool(client=client)

    result = tool.run(FetchInput(url=PAGE_URL))

    assert result.ok is True
    assert result.value is not None
    assert "Acme Robotics was founded in 2016" in result.value.content
    assert "Privacy Policy" not in result.value.content
    assert "Home" not in result.value.content
    assert result.value.title == "About Acme Robotics"
    assert result.value.url == PAGE_URL


def test_robots_disallow_maps_to_permanent_without_fetching_page() -> None:
    client = _FakeHttpClient([_FakeResponse(200, ROBOTS_DISALLOW_ALL)])
    tool = FetchTool(client=client)

    result = tool.run(FetchInput(url=PAGE_URL))

    assert result.ok is False
    assert result.error_category == ToolErrorCategory.PERMANENT
    assert len(client.urls_requested) == 1  # never fetched the page itself


def test_missing_robots_txt_treated_as_allowed() -> None:
    client = _FakeHttpClient(
        [_FakeResponse(404), _FakeResponse(200, _load_fixture_html())]
    )
    tool = FetchTool(client=client)

    result = tool.run(FetchInput(url=PAGE_URL))

    assert result.ok is True


def test_404_on_page_maps_to_permanent() -> None:
    client = _FakeHttpClient([_FakeResponse(200, ROBOTS_ALLOW_ALL), _FakeResponse(404)])
    tool = FetchTool(client=client)

    result = tool.run(FetchInput(url=PAGE_URL))

    assert result.ok is False
    assert result.error_category == ToolErrorCategory.PERMANENT


def test_403_on_page_maps_to_permanent() -> None:
    client = _FakeHttpClient([_FakeResponse(200, ROBOTS_ALLOW_ALL), _FakeResponse(403)])
    tool = FetchTool(client=client)

    result = tool.run(FetchInput(url=PAGE_URL))

    assert result.ok is False
    assert result.error_category == ToolErrorCategory.PERMANENT


def test_timeout_retries_then_maps_to_transient() -> None:
    client = _FakeHttpClient(
        [
            _FakeResponse(200, ROBOTS_ALLOW_ALL),
            httpx.TimeoutException("timed out"),
            httpx.TimeoutException("timed out"),
        ]
    )
    tool = FetchTool(client=client)

    result = tool.run(FetchInput(url=PAGE_URL))

    assert result.ok is False
    assert result.error_category == ToolErrorCategory.TRANSIENT
    # 1 robots fetch + 2 page attempts
    assert len(client.urls_requested) == 3


def test_succeeds_on_retry_after_one_transient_failure() -> None:
    client = _FakeHttpClient(
        [
            _FakeResponse(200, ROBOTS_ALLOW_ALL),
            httpx.TimeoutException("timed out"),
            _FakeResponse(200, _load_fixture_html()),
        ]
    )
    tool = FetchTool(client=client)

    result = tool.run(FetchInput(url=PAGE_URL))

    assert result.ok is True


def test_no_extractable_text_maps_to_validation() -> None:
    client = _FakeHttpClient(
        [
            _FakeResponse(200, ROBOTS_ALLOW_ALL),
            _FakeResponse(200, "<html><body></body></html>"),
        ]
    )
    tool = FetchTool(client=client)

    result = tool.run(FetchInput(url=PAGE_URL))

    assert result.ok is False
    assert result.error_category == ToolErrorCategory.VALIDATION


def test_robots_fetch_failure_fails_open() -> None:
    client = _FakeHttpClient(
        [ConnectionError("dns failure"), _FakeResponse(200, _load_fixture_html())]
    )
    tool = FetchTool(client=client)

    result = tool.run(FetchInput(url=PAGE_URL))

    assert result.ok is True
