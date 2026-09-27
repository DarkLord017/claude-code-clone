from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ToolKind(Enum):
    READ = "read"
    WRITE = "write"
    SHELL = "shell"
    NETWORK = "network"
    MEMORY = "memory"
    MCP = "mcp"
    PLAN = "plan"  # internal bookkeeping (e.g. a todo list) — no external side effect, no approval needed


@dataclass
class ToolInvocation:
    params: dict[str, Any]
    cwd: Path


@dataclass
class ToolConfirmation:
    tool_name: str
    params: dict[str, Any]
    description: str
    # None means the request comes from the main agent. Set to a subagent's task description
    # when it comes from a background subagent instead, so the UI can say who's asking.
    source: str | None = None


@dataclass
class ToolResult:
    success: bool
    output: str
    error: str | None = None
    truncated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success_result(
        cls,
        output: str,
        truncated: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResult":
        return cls(
            success=True,
            output=output,
            truncated=truncated,
            metadata=metadata or {},
        )

    @classmethod
    def error_result(
        cls,
        error: str,
        output: str = "",
    ) -> "ToolResult":
        return cls(
            success=False,
            output=output,
            error=error,
        )
