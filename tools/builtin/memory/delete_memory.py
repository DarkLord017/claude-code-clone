from __future__ import annotations

from pydantic import BaseModel, Field

from config.types import Config
from memory.store import delete_entry
from tools.base import Tool
from tools.types import ToolInvocation, ToolKind, ToolResult


class DeleteMemoryParams(BaseModel):
    name: str = Field(..., description="The memory's slug to delete, exactly as shown in the memory index.")


class DeleteMemoryTool(Tool):
    name = "delete_memory"
    description = (
        "Permanently delete one saved memory by name, removing both its file and its entry "
        "in the memory index. Use this when a remembered fact is no longer true or relevant."
    )
    kind = ToolKind.MEMORY

    schema = DeleteMemoryParams

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = DeleteMemoryParams(**invocation.params)
        deleted = delete_entry(self._config.memory_dir, params.name)

        if not deleted:
            return ToolResult.error_result(f"No memory found named '{params.name}'.")

        return ToolResult.success_result(
            output=f"Deleted memory '{params.name}'.",
            metadata={"name": params.name},
        )
