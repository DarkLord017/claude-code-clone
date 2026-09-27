from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from tools.base import Tool
from tools.registry import ToolRegistry
from tools.types import ToolInvocation, ToolKind, ToolResult

if TYPE_CHECKING:
    from agent.agent import Agent
    from agent.types import AgentEvent

BuildSubagent = Callable[[str, ToolRegistry], "Agent"]
# (task, event) -> None — called for every event the subagent produces, for live progress
OnSubagentEvent = Callable[[str, "AgentEvent"], None]
GetParentRegistry = Callable[[], ToolRegistry]


class SubagentParams(BaseModel):
    task: str = Field(
        ...,
        description=(
            "Complete, self-contained instructions for the subagent. It starts with no "
            "knowledge of this conversation — include everything it needs to know."
        ),
    )
    allowed_tools: List[str] = Field(
        ...,
        description=(
            "Bare tool names to grant the subagent, exactly as registered — e.g. "
            "['read_file', 'search']. Do NOT prefix them with 'functions.' or anything else "
            "(not 'functions.read_file' — just 'read_file'). It gets nothing else."
        ),
    )


class SubagentTool(Tool):
    name = "subagent"
    description = (
        "Delegate a self-contained task to a fresh, isolated agent with only the tools you "
        "specify in allowed_tools, running IN THE BACKGROUND — this call returns immediately "
        "with a task_id, it does not wait for the subagent to finish. You can keep working "
        "(answer the user, make other tool calls) while it runs; you'll automatically be told "
        "when it completes and what it found, injected into the conversation before your next "
        "turn. Use this for focused sub-tasks (e.g. 'find every usage of X and summarize') so "
        "the main conversation doesn't fill up with the sub-task's own tool calls. The "
        "subagent has NO access to this conversation's history — the task must be "
        "self-contained. Its live progress streams to the user as it works."
    )
    kind = ToolKind.READ

    schema = SubagentParams

    def __init__(
        self,
        get_parent_registry: GetParentRegistry,
        build_subagent: BuildSubagent,
        on_event: Optional[OnSubagentEvent] = None,
        max_concurrent: int = 3,
    ) -> None:
        super().__init__()
        self._get_parent_registry = get_parent_registry
        self._build_subagent = build_subagent
        self._on_event = on_event
        self._tasks: Dict[str, "asyncio.Task"] = {}
        self._results: Dict[str, ToolResult] = {}

        # Bounds how many subagents actually run at once.
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = SubagentParams(**invocation.params)
        parent_registry = self._get_parent_registry()

        scoped = ToolRegistry()
        for raw_name in params.allowed_tools:
            tool_name = raw_name.rsplit(".", 1)[-1]
            tool = parent_registry.get(tool_name)
            if tool is None:
                return ToolResult.error_result(
                    f"Unknown tool for subagent: '{raw_name}'. It must be one of the "
                    f"parent agent's own registered tools (bare name, no prefix)."
                )
            scoped.register(tool)

        subagent = self._build_subagent(params.task, scoped)
        task_id = uuid.uuid4().hex[:8]

        self._tasks[task_id] = asyncio.create_task(self._run(task_id, subagent, params.task))

        return ToolResult.success_result(
            output=(
                f"Subagent '{task_id}' dispatched in the background on: {params.task}. "
                f"It is NOT done yet — continue with other work; you'll be notified with its "
                f"result when it finishes. It may briefly wait for a free slot if the "
                f"concurrency limit is already reached."
            ),
            metadata={"task_id": task_id, "status": "dispatched", "allowed_tools": params.allowed_tools},
        )

    async def _run(self, task_id: str, subagent: "Agent", task: str) -> None:
        """The actual background work. Never lets an exception escape — a failed subagent
        still needs to report *something* back, not vanish as an unretrieved task exception."""
        from agent.types import AgentEvent, AgentEventType  # local: see the TYPE_CHECKING note up top

        async with self._semaphore:
            if self._on_event:
                self._on_event(task, AgentEvent.subagent_started(task_id=task_id, task=task))

            final_text: Optional[str] = None
            tool_call_count = 0

            try:
                async for event in subagent.run(task):
                    if self._on_event:
                        self._on_event(task, event)
                    if event.type == AgentEventType.TEXT_COMPLETE:
                        final_text = event.data["content"]
                    elif event.type == AgentEventType.TOOL_CALL_END:
                        tool_call_count += 1

                if final_text is None:
                    self._results[task_id] = ToolResult.error_result(
                        "Subagent finished without a final answer."
                    )
                else:
                    self._results[task_id] = ToolResult.success_result(
                        output=final_text,
                        metadata={"tool_calls_made": tool_call_count},
                    )
            except Exception as e:  # noqa: BLE001 — deliberately broad, see docstring
                self._results[task_id] = ToolResult.error_result(f"Subagent crashed: {e}")

    def pop_completed(self) -> List[tuple]:
        """(task_id, ToolResult) for every background subagent that finished since the last
        call — each one is only ever returned once."""
        done = [task_id for task_id, task in self._tasks.items() if task.done()]
        completed = []
        for task_id in done:
            del self._tasks[task_id]
            result = self._results.pop(task_id, ToolResult.error_result("Subagent result missing."))
            completed.append((task_id, result))
        return completed
