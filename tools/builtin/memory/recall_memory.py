from __future__ import annotations

from pydantic import BaseModel, Field

from config.types import Config
from memory.store import read_entry
from tools.base import Tool
from tools.types import ToolInvocation, ToolKind, ToolResult


class RecallMemoryParams(BaseModel):
    name: str = Field(..., description="The memory's slug, exactly as shown in the memory index.")


class RecallMemoryTool(Tool):
    name = "recall_memory"
    description = (
        "Fetch the full content of one specific saved memory by name. The system prompt only "
        "shows a one-line index of what's remembered — call this to read the full details of "
        "a specific entry once it looks relevant to the current conversation."
    )
    kind = ToolKind.READ

    schema = RecallMemoryParams

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = RecallMemoryParams(**invocation.params)
        content = read_entry(self._config.memory_dir, params.name)

        if content is None:
            return ToolResult.error_result(f"No memory found named '{params.name}'.")

        return ToolResult.success_result(output=content, metadata={"name": params.name})
