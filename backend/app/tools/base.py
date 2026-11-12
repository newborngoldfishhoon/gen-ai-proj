"""Base classes and schemas for the AgentForge tool system."""

from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Standardized result returned by every tool execution."""

    success: bool
    tool_name: str
    summary: str
    output: Any = None
    sources: list[dict] = Field(default_factory=list)
    error: str | None = None
    metadata: dict = Field(default_factory=dict)

    def to_llm_string(self) -> str:
        """Format the result as a clean text string for feeding back to an LLM."""
        if not self.success:
            return f"Error executing {self.tool_name}: {self.error or self.summary}"

        if isinstance(self.output, str):
            return self.output
        elif isinstance(self.output, (dict, list)):
            import json
            return json.dumps(self.output, indent=2)
        return str(self.output) if self.output is not None else self.summary


class BaseTool(ABC):
    """Abstract base class for all registered tools."""

    name: str
    description: str
    args_schema: type[BaseModel]

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with validated keyword arguments."""
        ...

    def get_declaration(self) -> dict:
        """Return the tool specification in JSON schema format for LLM function calling."""
        schema = self.args_schema.model_json_schema()
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # Clean schema for Gemini / OpenAI function declaration compatibility
        clean_properties = {}
        for key, prop in properties.items():
            clean_prop = {
                "type": prop.get("type", "string"),
                "description": prop.get("description", ""),
            }
            if "enum" in prop:
                clean_prop["enum"] = prop["enum"]
            clean_properties[key] = clean_prop

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": clean_properties,
                "required": required,
                "additionalProperties": False,
            },
        }
