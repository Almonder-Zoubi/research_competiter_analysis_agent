"""Web search tool, wrapping the Tavily client behind the uniform Tool contract."""

from __future__ import annotations

from typing import Any, Protocol

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


class _TavilyClientLike(Protocol):
    """The slice of TavilyClient this tool depends on — lets tests inject a fake."""

    def search(
        self, query: str, max_results: int | None = None, **kwargs: Any
    ) -> dict[str, Any]: ...


class SearchTool(Tool[list[Source]]):
    name = "search"

    def __init__(self, client: _TavilyClientLike) -> None:
        self._client = client

    def run(self, input: SearchInput) -> ToolResult[list[Source]]:  # type: ignore[override]
        try:
            response = self._client.search(
                query=input.query, max_results=input.max_results
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
