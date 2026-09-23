from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from config.types import Config
from memory.store import update_entry
from tools.base import Tool
from tools.types import ToolInvocation, ToolKind, ToolResult


class UpdateMemoryParams(BaseModel):
    name: str = Field(..., description="The existing memory's slug to update, exactly as shown in the memory index.")
    description: Optional[str] = Field(
        None, description="New one-line description. Leave unset to keep the existing description unchanged."
    )
    content: Optional[str] = Field(
        None, description="New full content. Leave unset to keep the existing content unchanged."
    )


class UpdateMemoryTool(Tool):
    name = "update_memory"
    description = (
        "Update an EXISTING memory, changing only the fields you provide — unlike remember, "
        "which replaces a memory entirely, this keeps whatever you don't pass unchanged (e.g. "
        "pass only `description` to fix the summary without touching the saved content). "
        "Fails if no memory with that name exists yet — use remember to create one first."
    )
    kind = ToolKind.MEMORY

    schema = UpdateMemoryParams

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = UpdateMemoryParams(**invocation.params)
        updated = update_entry(
            self._config.memory_dir, params.name, params.description, params.content
        )

        if not updated:
            return ToolResult.error_result(
                f"No memory found named '{params.name}'. Use remember to create it first."
            )

        return ToolResult.success_result(
            output=f"Updated memory '{params.name}'.",
            metadata={"name": params.name},
        )
