"""A dummy tool exercising every ToolResult shape — no real tool needed for this."""

from __future__ import annotations

from pydantic import BaseModel

from tools.base import Tool, ToolErrorCategory, ToolResult


class _DummyInput(BaseModel):
    mode: str


class _DummyTool(Tool[str]):
    name = "dummy"

    def run(self, input: _DummyInput) -> ToolResult[str]:  # type: ignore[override]
        if input.mode == "ok":
            return ToolResult.success("value")
        if input.mode == "transient":
            return ToolResult.failure(ToolErrorCategory.TRANSIENT, "try again later")
        if input.mode == "permanent":
            return ToolResult.failure(ToolErrorCategory.PERMANENT, "bad request")
        return ToolResult.failure(ToolErrorCategory.VALIDATION, "invalid output")


def test_success_carries_value_and_no_error() -> None:
    result = _DummyTool().run(_DummyInput(mode="ok"))
    assert result.ok is True
    assert result.value == "value"
    assert result.error_category is None
    assert result.error_message is None


def test_transient_failure_shape() -> None:
    result = _DummyTool().run(_DummyInput(mode="transient"))
    assert result.ok is False
    assert result.value is None
    assert result.error_category == ToolErrorCategory.TRANSIENT
    assert result.error_message == "try again later"


def test_permanent_failure_shape() -> None:
    result = _DummyTool().run(_DummyInput(mode="permanent"))
    assert result.ok is False
    assert result.error_category == ToolErrorCategory.PERMANENT


def test_validation_failure_shape() -> None:
    result = _DummyTool().run(_DummyInput(mode="anything-else"))
    assert result.ok is False
    assert result.error_category == ToolErrorCategory.VALIDATION
