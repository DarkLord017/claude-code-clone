from __future__ import annotations

import asyncio
from typing import Optional

from pydantic import BaseModel, Field

from tools.base import Tool
from tools.types import ToolInvocation, ToolKind, ToolResult
from utils.paths import resolve_path


class ShellParams(BaseModel):

    command: str = Field(
        ...,
        min_length=1,
        description="The shell command to run.",
    )

    timeout: Optional[int] = Field(
        30,
        ge=1,
        description="Seconds to wait before killing the command. Defaults to 30.",
    )

    cwd: Optional[str] = Field(
        None,
        description=(
            "Optional subdirectory (relative to the working directory) to run the command in. "
            "Defaults to the current working directory."
        ),
    )


class ShellTool(Tool):
    name = "shell"
    description = (
        "Run an arbitrary shell command and capture its stdout, stderr, and exit code. "
        "The command is killed if it exceeds the timeout (default 30s). "
        "Before running anything destructive or hard to reverse (deleting files, force-pushing, "
        "dropping data, installing/uninstalling packages, changing permissions, etc.), explain "
        "what the command does and its impact before executing it. Prefer targeted, safe commands. "
        "Avoid destructive operations unless explicitly requested."
    )
    kind = ToolKind.SHELL

    schema = ShellParams

    MAX_OUTPUT_CHARS = 30000

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ShellParams(**invocation.params)

        if params.cwd:
            cwd = resolve_path(invocation.cwd, params.cwd)
            if not cwd.exists():
                return ToolResult.error_result(f"cwd does not exist: {cwd}")
            if not cwd.is_dir():
                return ToolResult.error_result(f"cwd is not a directory: {cwd}")
        else:
            cwd = invocation.cwd

        try:
            process = await asyncio.create_subprocess_shell(
                params.command,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as e:
            return ToolResult.error_result(f"Failed to start command: {e}")

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=params.timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return ToolResult.error_result(
                f"Command timed out after {params.timeout}s: {params.command}"
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        returncode = process.returncode

        truncated = False
        if len(stdout) + len(stderr) > self.MAX_OUTPUT_CHARS:
            truncated = True
            budget = self.MAX_OUTPUT_CHARS
            stdout_budget = min(len(stdout), budget)
            if stdout_budget < len(stdout):
                stdout = stdout[:stdout_budget] + "\n... [stdout truncated]"
            remaining = max(0, budget - stdout_budget)
            if len(stderr) > remaining:
                stderr = stderr[:remaining] + "\n... [stderr truncated]"

        output = f"$ {params.command}\n(exit code: {returncode})\n\n{stdout}"
        if stderr:
            output += f"\n--- stderr ---\n{stderr}"

        metadata = {
            "command": params.command,
            "returncode": returncode,
            "cwd": str(cwd),
        }

        if returncode != 0:
            return ToolResult(
                success=False,
                output=output,
                error=f"Command exited with code {returncode}",
                truncated=truncated,
                metadata=metadata,
            )

        return ToolResult.success_result(
            output=output,
            truncated=truncated,
            metadata=metadata,
        )
