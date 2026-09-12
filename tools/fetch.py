"""Direct page-fetch tool: fills the gap when Tavily's `content` field is thin
or empty. Uses httpx for the request and trafilatura for HTML -> clean text.

Same Tool/ToolResult contract as tools/search.py — never raises. Robots.txt is
checked through the same injectable HTTP client (not urllib.robotparser's own
built-in fetch), so the check stays offline-testable like everything else in
this project (see CLAUDE.md: no live calls in the test suite).
"""

from __future__ import annotations

from typing import Protocol
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura
from pydantic import BaseModel

from agent.schemas import Source
from tools.base import Tool, ToolErrorCategory, ToolResult

_TIMEOUT_SECONDS = 5.0
_MAX_ATTEMPTS = 2  # one retry on a transient failure
_USER_AGENT = "research-competitor-analysis-agent/0.1"
_PERMANENT_STATUS_CODES = {401, 403, 404, 410}


class FetchInput(BaseModel):
    url: str


class _HttpClientLike(Protocol):
    """The slice of httpx.Client this tool depends on — lets tests inject a fake."""

    def get(self, url: str, **kwargs: object) -> httpx.Response: ...


class FetchTool(Tool[Source]):
    name = "fetch"

    def __init__(self, client: _HttpClientLike | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=_TIMEOUT_SECONDS,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        )

    def run(self, input: FetchInput) -> ToolResult[Source]:  # type: ignore[override]
        robots_failure = self._check_robots(input.url)
        if robots_failure is not None:
            return robots_failure

        html, fetch_failure = self._get_with_retry(input.url)
        if fetch_failure is not None:
            return fetch_failure
        assert html is not None

        text = trafilatura.extract(html)
        if not text:
            return ToolResult.failure(
                ToolErrorCategory.VALIDATION,
                f"no extractable text at {input.url}",
            )

        metadata = trafilatura.extract_metadata(html)
        title = metadata.title if metadata is not None and metadata.title else ""

        return ToolResult.success(Source(url=input.url, title=title, content=text))

    def _check_robots(self, url: str) -> ToolResult[Source] | None:
        parts = urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        try:
            response = self._client.get(robots_url)
        except Exception:  # noqa: BLE001 - can't determine policy, fail open
            return None
        if response.status_code >= 400:
            return None  # no robots.txt (or inaccessible) — treat as allowed

        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        if not parser.can_fetch(_USER_AGENT, url):
            return ToolResult.failure(
                ToolErrorCategory.PERMANENT, f"robots.txt disallows fetching {url}"
            )
        return None

    def _get_with_retry(self, url: str) -> tuple[str | None, ToolResult[Source] | None]:
        last_error = ""
        for _ in range(_MAX_ATTEMPTS):
            try:
                response = self._client.get(url)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_error = str(e)
                continue

            if response.status_code in _PERMANENT_STATUS_CODES:
                return None, ToolResult.failure(
                    ToolErrorCategory.PERMANENT,
                    f"{response.status_code} fetching {url}",
                )
            if response.status_code >= 400:
                last_error = f"{response.status_code} fetching {url}"
                continue
            return response.text, None

        return None, ToolResult.failure(ToolErrorCategory.TRANSIENT, last_error)
