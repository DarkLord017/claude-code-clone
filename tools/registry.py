from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from tools import errors
from tools.base import Tool
from tools.types import ToolInvocation, ToolResult
from utils.logging import get_logger

logger = get_logger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(errors.already_registered(tool.name))
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        if name not in self._tools:
            raise KeyError(errors.not_registered(name))
        del self._tools[name]

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def to_schema_list(self) -> list[dict[str, Any]]:
        """Schemas for every registered tool, in OpenAI function-calling shape for the `tools` param."""
        return [{"type": "function", "function": tool.to_dict()} for tool in self._tools.values()]

    async def execute(self, name: str, invocation: ToolInvocation) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            logger.warning("Tool call for unknown tool '%s'", name)
            return ToolResult.error_result(errors.unknown_tool(name))

        if not tool.validate_params(invocation.params):
            logger.warning("Invalid parameters for tool '%s': %s", name, invocation.params)
            return ToolResult.error_result(errors.invalid_params(name, invocation.params))

        try:
            return await tool.execute(invocation)
        except Exception as e:
            logger.exception("Tool '%s' raised an unhandled error", name)
            return ToolResult.error_result(errors.unhandled_tool_error(name, e))

    async def invoke(self, name: str, params: dict[str, Any], cwd: Path) -> ToolResult:
        """Convenience wrapper around execute() for callers that don't already have a ToolInvocation."""
        return await self.execute(name, ToolInvocation(params=params, cwd=cwd))

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self) -> Iterator[Tool]:
        return iter(self._tools.values())
