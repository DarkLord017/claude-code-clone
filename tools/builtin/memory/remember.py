from __future__ import annotations

from pydantic import BaseModel, Field

from config.types import Config
from memory.store import write_entry
from tools.base import Tool
from tools.types import ToolInvocation, ToolKind, ToolResult


class RememberParams(BaseModel):
    name: str = Field(
        ...,
        description="Short kebab-case slug identifying this memory, e.g. 'user-prefers-dark-mode'.",
    )
    description: str = Field(
        ...,
        description=(
            "One-line summary shown in the memory index. Must be specific enough that a future "
            "conversation can judge relevance without opening the full file."
        ),
    )
    content: str = Field(..., description="The full memory content to save.")


class RememberTool(Tool):
    name = "remember"
    description = (
        "Save a fact, preference, or piece of context that should persist across future "
        "conversations. Only the one-line description is loaded automatically next time — "
        "use recall_memory to fetch the full content when it's relevant. Calling this again "
        "with the same name fully overwrites that memory's description and content — use it "
        "to replace a memory wholesale, or update_memory to change only one field."
    )
    kind = ToolKind.MEMORY

    schema = RememberParams

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = RememberParams(**invocation.params)
        path = write_entry(self._config.memory_dir, params.name, params.description, params.content)

        return ToolResult.success_result(
            output=f"Saved memory '{params.name}' to {path}.",
            metadata={"path": str(path), "name": params.name},
        )
