from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

from client.types import TokenUsage
from tools.types import ToolConfirmation, ToolResult

ConfirmCallback = Callable[[ToolConfirmation], Awaitable[bool]]


class AgentEventType(str, Enum):
    # agent lifecycle events
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    AGENT_ERROR = "agent_error"

    # text streaming events
    TEXT_DELTA = "text_delta"
    TEXT_COMPLETE = "text_complete"

    # tool call events
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"

    # context management events
    CONTEXT_COMPACTED = "context_compacted"

    # background subagent events
    SUBAGENT_STARTED = "subagent_started"
    SUBAGENT_COMPLETED = "subagent_completed"


@dataclass
class AgentEvent:
    type: AgentEventType
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def agent_start(cls, message: str) -> AgentEvent:
        return cls(
            type=AgentEventType.AGENT_START,
            data={"message": message},
        )

    @classmethod
    def agent_end(
        cls,
        response: str | None = None,
        usage: TokenUsage | None = None,
    ) -> AgentEvent:
        return cls(
            type=AgentEventType.AGENT_END,
            data={
                "response": response,
                "usage": usage.__dict__ if usage else None,
            },
        )

    @classmethod
    def agent_error(cls, error: str, details: dict[str, Any] | None = None) -> AgentEvent:
        return cls(
            type=AgentEventType.AGENT_ERROR,
            data={"error_message": error, "details": details if details else {}},
        )

    @classmethod
    def text_delta(cls, content: str) -> AgentEvent:
        return cls(
            type=AgentEventType.TEXT_DELTA,
            data={"content": content},
        )

    @classmethod
    def text_complete(cls, content: str) -> AgentEvent:
        return cls(
            type=AgentEventType.TEXT_COMPLETE,
            data={"content": content},
        )

    @classmethod
    def tool_call_start(cls, tool_name: str, tool_call_id: str, arguments: str, kind: str) -> AgentEvent:
        return cls(
            type=AgentEventType.TOOL_CALL_START,
            data={
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "arguments": arguments,
                "kind": kind,
            },
        )

    @classmethod
    def tool_call_end(
        cls, tool_name: str, tool_call_id: str, result: ToolResult, kind: str
    ) -> AgentEvent:
        return cls(
            type=AgentEventType.TOOL_CALL_END,
            data={
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "metadata": result.metadata,
                "kind": kind,
            },
        )

    @classmethod
    def context_compacted(cls, messages_removed: int, summary: str) -> AgentEvent:
        return cls(
            type=AgentEventType.CONTEXT_COMPACTED,
            data={"messages_removed": messages_removed, "summary": summary},
        )

    @classmethod
    def subagent_started(cls, task_id: str, task: str) -> AgentEvent:
        return cls(
            type=AgentEventType.SUBAGENT_STARTED,
            data={"task_id": task_id, "task": task},
        )

    @classmethod
    def subagent_completed(cls, task_id: str, success: bool, output: str) -> AgentEvent:
        return cls(
            type=AgentEventType.SUBAGENT_COMPLETED,
            data={"task_id": task_id, "success": success, "output": output},
        )
