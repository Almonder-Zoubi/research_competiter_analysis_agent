"""Uniform tool contract.

Every tool (search, fetch, extract, ...) returns a ToolResult instead of raising —
the loop needs to distinguish "network hiccup, try again" from "bad input, skip it"
from "model output didn't parse, repair and re-ask", and a raised exception loses
that distinction. See CLAUDE.md: tools are plain functions wrapped in uniform error
handling.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ToolErrorCategory(str, Enum):
    TRANSIENT = "transient"  # network, timeout, rate-limit -> caller may retry
    PERMANENT = "permanent"  # bad request, 404, auth -> caller skips + logs
    VALIDATION = (
        "validation"  # output failed Pydantic parse -> caller may repair/re-ask
    )


class ToolResult(BaseModel, Generic[T]):
    """Either ok=True with a typed value, or ok=False with an error category."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ok: bool
    value: T | None = None
    error_category: ToolErrorCategory | None = None
    error_message: str | None = None

    @classmethod
    def success(cls, value: T) -> ToolResult[T]:
        return cls(ok=True, value=value)

    @classmethod
    def failure(cls, category: ToolErrorCategory, message: str) -> ToolResult[T]:
        return cls(ok=False, error_category=category, error_message=message)


class Tool(ABC, Generic[T]):
    """Minimal tool base: a name, and a run(input) -> ToolResult.

    Implementations must never let an exception escape run() — catch it and
    return ToolResult.failure(...) with the right category instead.
    """

    name: str

    @abstractmethod
    def run(self, input: BaseModel) -> ToolResult[T]: ...
