from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from tools.base import Tool
from tools.types import ToolInvocation, ToolKind, ToolResult


class TaskItem(BaseModel):
    content: str = Field(..., description="The task description.")
    done: bool = Field(False, description="Whether this task is complete.")


class TasksParams(BaseModel):
    tasks: Optional[list[TaskItem]] = Field(
        None,
        description=(
            "The complete current task list, replacing whatever was stored before. "
            "Omit this entirely to just view the current list without changing it."
        ),
    )


class TasksTool(Tool):
    name = "tasks"
    description = (
        "Track and communicate progress on multi-step tasks. Call this with the complete, "
        "updated task list any time task status changes — not just to add new items, but "
        "whenever a task starts, finishes, or the plan changes. Always resend the full list "
        "(mark items done by setting done: true); it replaces whatever was stored before. "
        "Omit `tasks` entirely to just check the current list without changing it. Keep this "
        "updated as you work so progress stays visible, similar in spirit to using any "
        "task-tracking tool available for multi-step work."
    )
    kind = ToolKind.PLAN

    schema = TasksParams

    def __init__(self) -> None:
        self._tasks: list[dict] = []

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = TasksParams(**invocation.params)

        if params.tasks is not None:
            self._tasks = [{"content": t.content, "done": t.done} for t in params.tasks]

        total = len(self._tasks)
        done = sum(1 for t in self._tasks if t["done"])

        if total == 0:
            body = "No tasks yet."
        else:
            lines = []
            for t in self._tasks:
                if t["done"]:
                    lines.append(f"- [x] ~~{t['content']}~~")
                else:
                    lines.append(f"- [ ] {t['content']}")
            body = "\n".join(lines)

        output = f"{done}/{total} tasks complete\n{body}"

        return ToolResult.success_result(
            output=output,
            metadata={
                "tasks": [dict(t) for t in self._tasks],
                "total": total,
                "done": done,
            },
        )
