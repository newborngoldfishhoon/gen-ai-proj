"""Tool registry — central allowlist and dispatch engine for all agent tools."""

import asyncio
import logging
from typing import Any
from pydantic import ValidationError

from app.core.config import get_settings
from app.tools.base import BaseTool, ToolResult
from app.tools.calculator import CalculatorTool
from app.tools.web_search import WebSearchTool
from app.tools.extract_webpage import ExtractWebpageTool

logger = logging.getLogger("agentforge.tools.registry")


class ToolRegistry:
    """Manages registered tools, validates requests, and controls execution."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool in the allowlist."""
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def get(self, name: str) -> BaseTool | None:
        """Lookup a registered tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def get_declarations(self) -> list[dict]:
        """Return JSON schema declarations for all registered tools."""
        return [tool.get_declaration() for tool in self._tools.values()]

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """Validate and execute a tool call.

        Security enforcement:
        1. Name must be in the allowlist.
        2. Arguments must strictly match the Pydantic schema.
        3. Execution is bounded by timeout.
        """
        tool = self.get(tool_name)
        if not tool:
            allowed = ", ".join(self._tools.keys())
            return ToolResult(
                success=False,
                tool_name=tool_name,
                summary=f"Unknown tool '{tool_name}'. Allowed tools are: {allowed}",
                error=f"Tool '{tool_name}' is not in the allowed registry",
            )

        # Validate arguments against Pydantic schema
        try:
            validated = tool.args_schema.model_validate(arguments or {})
        except ValidationError as val_err:
            error_details = []
            for err in val_err.errors():
                loc = ".".join(str(p) for p in err["loc"])
                msg = err["msg"]
                error_details.append(f"Argument '{loc}': {msg}")
            combined = "; ".join(error_details)
            return ToolResult(
                success=False,
                tool_name=tool_name,
                summary=f"Invalid arguments for {tool_name}: {combined}",
                error=combined,
                metadata={"raw_arguments": arguments},
            )

        settings = get_settings()
        timeout = float(settings.tool_timeout_seconds)

        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                tool.execute(**validated.model_dump()),
                timeout=timeout,
            )
            return result
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                tool_name=tool_name,
                summary=f"Tool '{tool_name}' timed out after {timeout} seconds",
                error=f"Timeout of {timeout}s exceeded",
                metadata={"raw_arguments": arguments},
            )
        except Exception as e:
            logger.exception("Unexpected error executing tool '%s': %s", tool_name, str(e))
            return ToolResult(
                success=False,
                tool_name=tool_name,
                summary=f"Execution error in {tool_name}: {str(e)}",
                error=str(e),
                metadata={"raw_arguments": arguments},
            )


def create_default_registry() -> ToolRegistry:
    """Factory: build and return the default tool registry based on application settings."""
    settings = get_settings()
    registry = ToolRegistry()

    if settings.agent_enable_calculator:
        registry.register(CalculatorTool())

    if settings.agent_enable_web_search:
        registry.register(WebSearchTool())
        registry.register(ExtractWebpageTool())

    return registry
