from __future__ import annotations

from typing import Awaitable, Callable, Optional

from pydantic import BaseModel, Field

from context.manager import ContextManager
from context.types import Message
from tools.base import Tool
from tools.types import ToolInvocation, ToolKind, ToolResult

# (messages to summarize, optional user instruction) -> summary text, or None on failure
SummarizeFn = Callable[[list[Message], Optional[str]], Awaitable[Optional[str]]]
GetContextManager = Callable[[], ContextManager]


class CompactContextParams(BaseModel):
    instruction: Optional[str] = Field(
        None,
        description=(
            "Optional guidance on what the summary should focus on or preserve "
            "(e.g. 'keep details about the auth bug, drop the read_file exploration')."
        ),
    )


class CompactContextTool(Tool):
    name = "compact_context"
    description = (
        "Summarize and remove older conversation history to free up context space, keeping "
        "the most recent messages intact. Use this when the user asks to compact or summarize "
        "the conversation. Pass `instruction` to guide what the summary should emphasize or keep."
    )
    kind = ToolKind.MEMORY

    schema = CompactContextParams

    def __init__(self, get_context_manager: GetContextManager, summarize: SummarizeFn) -> None:
        super().__init__()
        self._get_context_manager = get_context_manager
        self._summarize = summarize

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = CompactContextParams(**invocation.params)
        context_manager = self._get_context_manager()

        range_ = context_manager.compaction_range()
        if range_ is None:
            return ToolResult.error_result("There's nothing safe to compact right now.")

        start, end = range_
        to_summarize = context_manager.messages_slice(start, end)

        summary = await self._summarize(to_summarize, params.instruction)
        if summary is None:
            return ToolResult.error_result("Compaction summary call failed.")

        context_manager.apply_compaction(end, summary)

        return ToolResult.success_result(
            output=f"Compacted {end - start} earlier message(s) into a summary.",
            metadata={"messages_removed": end - start, "summary": summary},
        )
