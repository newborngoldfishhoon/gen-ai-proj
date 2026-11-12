"""Tools package for AgentForge Phase 2."""

from app.tools.base import BaseTool, ToolResult
from app.tools.calculator import CalculatorTool
from app.tools.web_search import WebSearchTool
from app.tools.extract_webpage import ExtractWebpageTool
from app.tools.registry import ToolRegistry, create_default_registry

__all__ = [
    "BaseTool",
    "ToolResult",
    "CalculatorTool",
    "WebSearchTool",
    "ExtractWebpageTool",
    "ToolRegistry",
    "create_default_registry",
]
