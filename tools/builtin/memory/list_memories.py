from __future__ import annotations

from config.types import Config
from memory.store import read_index
from tools.base import Tool
from tools.types import ToolInvocation, ToolKind, ToolResult


class ListMemoriesTool(Tool):
    name = "list_memories"
    description = (
        "List every saved memory (name + one-line description each). Use this to see what's "
        "been remembered, including anything saved earlier in this same conversation — the "
        "system prompt's memory index is only a snapshot from when the session started."
    )
    kind = ToolKind.READ

    schema = {} 

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        index = read_index(self._config.memory_dir)
        if index is None:
            return ToolResult.success_result(output="No memories saved yet.")
        return ToolResult.success_result(output=index)
