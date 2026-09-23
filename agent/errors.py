from __future__ import annotations

UNKNOWN_STREAM_ERROR = "Unknown error"
TOOL_FAILED_FALLBACK = "Tool failed"


def invalid_tool_arguments(error: Exception) -> str:
    return f"Invalid JSON arguments: {error}"


def action_denied(description: str) -> str:
    return f"Action denied by user: {description}"


def tool_iteration_limit_reached(max_iterations: int) -> str:
    return f"Stopped after {max_iterations} tool iterations without a final answer."
