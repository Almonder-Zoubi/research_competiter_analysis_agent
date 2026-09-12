"""Web search tool, wrapping the Tavily client behind the uniform Tool contract."""

from __future__ import annotations

from typing import Any, Protocol

from langfuse import observe
from pydantic import BaseModel, Field
from tavily.errors import (
    BadRequestError,
    ForbiddenError,
    InvalidAPIKeyError,
    MissingAPIKeyError,
    UsageLimitExceededError,
)

from agent.schemas import Source
from tools.base import Tool, ToolErrorCategory, ToolResult


class SearchInput(BaseModel):
    query: str
    max_results: int = Field(default=5, gt=0)


# Domains that are rarely useful as citable sources for factual research — video
# and social platforms return content that isn't extractable article text, and
# aren't authoritative. This is a first-pass filter, not a full source-quality
# system: deeper credibility weighting (official site > major outlet > blog) is
# verification's job once corroboration across sources exists (ROADMAP.md Days
# 6-7's "source-quality heuristic"). Kept as a blocklist rather than an
# allowlist because research subjects vary too widely (a company vs. an
# engineering field) for any fixed list of "good" domains to fit both.
EXCLUDED_DOMAINS = [
    "youtube.com",
    "tiktok.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "reddit.com",
    "pinterest.com",
    "quora.com",
]


class _TavilyClientLike(Protocol):
    """The slice of TavilyClient this tool depends on — lets tests inject a fake."""

    def search(
        self, query: str, max_results: int | None = None, **kwargs: Any
    ) -> dict[str, Any]: ...


class SearchTool(Tool[list[Source]]):
    name = "search"

    def __init__(self, client: _TavilyClientLike) -> None:
        self._client = client

    @observe(name="search", as_type="tool")
    def run(self, input: SearchInput) -> ToolResult[list[Source]]:  # type: ignore[override]
        try:
            response = self._client.search(
                query=input.query,
                max_results=input.max_results,
                exclude_domains=EXCLUDED_DOMAINS,
            )
        except (
            InvalidAPIKeyError,
            MissingAPIKeyError,
            ForbiddenError,
            BadRequestError,
        ) as e:
            return ToolResult.failure(ToolErrorCategory.PERMANENT, str(e))
        except UsageLimitExceededError as e:
            return ToolResult.failure(ToolErrorCategory.TRANSIENT, str(e))
        except Exception as e:  # noqa: BLE001 - tools never raise to the loop
            return ToolResult.failure(ToolErrorCategory.TRANSIENT, str(e))

        try:
            sources = [
                Source(
                    url=result["url"],
                    title=result.get("title", ""),
                    content=result.get("content", ""),
                )
                for result in response["results"]
            ]
        except (KeyError, TypeError) as e:
            return ToolResult.failure(
                ToolErrorCategory.VALIDATION, f"malformed Tavily response: {e}"
            )

        return ToolResult.success(sources)
