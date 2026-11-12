"""Unit tests for the ToolRegistry and BaseTool abstractions."""

import pytest
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.tools.registry import ToolRegistry, create_default_registry


class SampleInput(BaseModel):
    value: int = Field(..., ge=1, le=100)


class SampleTool(BaseTool):
    name = "sample_tool"
    description = "A sample test tool"
    args_schema = SampleInput

    async def execute(self, value: int, **kwargs) -> ToolResult:
        return ToolResult(
            success=True,
            tool_name=self.name,
            summary=f"Processed {value}",
            output={"result": value * 2},
        )


def test_tool_registration_and_discovery():
    registry = ToolRegistry()
    tool = SampleTool()
    registry.register(tool)

    assert registry.get("sample_tool") is tool
    assert registry.get("non_existent") is None
    assert tool in registry.list_tools()

    declarations = registry.get_declarations()
    assert len(declarations) == 1
    assert declarations[0]["name"] == "sample_tool"
    assert "value" in declarations[0]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_registry_execute_success():
    registry = ToolRegistry()
    registry.register(SampleTool())

    result = await registry.execute("sample_tool", {"value": 25})
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.tool_name == "sample_tool"
    assert result.output["result"] == 50


@pytest.mark.asyncio
async def test_registry_unknown_tool_rejected():
    registry = ToolRegistry()
    registry.register(SampleTool())

    result = await registry.execute("malicious_tool", {"arg": "val"})
    assert result.success is False
    assert "Unknown tool" in result.summary
    assert "malicious_tool" in result.error


@pytest.mark.asyncio
async def test_registry_invalid_arguments_rejected():
    registry = ToolRegistry()
    registry.register(SampleTool())

    # Value out of bounds (> 100)
    result = await registry.execute("sample_tool", {"value": 500})
    assert result.success is False
    assert "Invalid arguments" in result.summary

    # Missing required argument
    result = await registry.execute("sample_tool", {})
    assert result.success is False
    assert "Invalid arguments" in result.summary


def test_default_registry_creation():
    registry = create_default_registry()
    tool_names = {t.name for t in registry.list_tools()}

    assert "calculator" in tool_names
    assert "web_search" in tool_names
    assert "extract_webpage" in tool_names
