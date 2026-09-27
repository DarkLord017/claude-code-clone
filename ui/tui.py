from __future__ import annotations

import asyncio
from typing import Any, Optional

from collections import deque

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.theme import Theme

from agent.types import AgentEvent, AgentEventType
from tools.types import ToolConfirmation

CLAUDE_ORANGE = "#D97757"
CLAUDE_BLUE = "#6A9BCC"
CLAUDE_GREEN = "#788C5D"

AGENT_THEME = Theme(
    {
        # General
        "info": CLAUDE_BLUE,
        "warning": "yellow",
        "error": "bright_red bold",
        "success": CLAUDE_GREEN,
        "dim": "dim",
        "muted": "grey50",
        "border": "grey35",
        "highlight": f"bold {CLAUDE_ORANGE}",
        "accent": CLAUDE_ORANGE,
        # Roles
        "user": "bright_blue bold",
        "assistant": f"bold {CLAUDE_ORANGE}",
        # Tools, by ToolKind — matches tools/types.py's ToolKind values
        "tool": "bright_magenta bold",
        "tool.read": CLAUDE_BLUE,
        "tool.write": CLAUDE_ORANGE,
        "tool.shell": "magenta",
        "tool.network": CLAUDE_BLUE,
        "tool.memory": CLAUDE_GREEN,
        "tool.plan": "yellow",
        "tool.mcp": "bright_cyan",
        "tool.unknown": "grey50",
        # Code / blocks
        "code": "white",
    }
)

_console: Optional[Console] = None


def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(theme=AGENT_THEME, highlight=False)
    return _console


class TUI:
    MAX_TOOL_ARGS_PREVIEW = 120
    MAX_TOOL_OUTPUT_PREVIEW = 400

    def __init__(self, console: Optional[Console] = None) -> None:
        self.console = console or get_console()
        self._session: PromptSession = PromptSession()
        self._pending_confirmations: "deque[asyncio.Future[bool]]" = deque()

    async def read_line(self, prompt_text: str) -> str:
        """The only place that reads the main steering input, via prompt_toolkit's native
        async prompt (patch_stdout keeps concurrent rich.console.print calls — subagent
        progress, tool output — from corrupting its rendering while it's open)."""
        with patch_stdout(raw=True):
            return await self._session.prompt_async(prompt_text)

    def resolve_pending_confirmation(self, line: str) -> bool:
        """If any confirmations are queued, resolve the OLDEST one using `line` as its
        y/n answer. Returns True if it did — the caller must NOT also treat `line` as a
        new steering message in that case."""
        if not self._pending_confirmations:
            return False
        future = self._pending_confirmations.popleft()
        answer = line.strip().lower() in ("y", "yes")
        if not future.done():
            future.set_result(answer)
        remaining = len(self._pending_confirmations)
        note = f" ({remaining} more still pending)" if remaining else ""
        self.console.print(f"[muted]→ answered pending confirmation: {'yes' if answer else 'no'}{note}[/muted]")
        return True

    def cancel_pending_confirmations(self) -> None:
        """Deny (don't hang) any confirmations still queued when the reader loop exits."""
        while self._pending_confirmations:
            future = self._pending_confirmations.popleft()
            if not future.done():
                future.set_result(False)

    def print_user_message(self, message: str) -> None:
        self.console.print(f"[user]>[/user] {escape(message)}")

    def stream_assistant_delta(self, content: str) -> None:
        self.console.print(content, end="", markup=False)

    def print_text_complete(self) -> None:
        self.console.print()  # close out the streamed assistant line

    def print_tool_call_start(self, tool_name: str, kind: str, arguments: str) -> None:
        style = f"tool.{kind}" if f"tool.{kind}" in AGENT_THEME.styles else "tool"
        preview = self._truncate(arguments, self.MAX_TOOL_ARGS_PREVIEW)
        self.console.print(
            f"[{style}]⏺ {escape(tool_name)}[/{style}] [dim]{escape(preview)}[/dim]"
        )

    def print_tool_call_end(
        self,
        tool_name: str,
        kind: str,
        success: bool,
        output: str,
        error: Optional[str],
    ) -> None:
        status_style = "success" if success else "error"
        glyph = "✓" if success else "✗"
        text = output if success else (error or "failed")
        preview = self._truncate(text, self.MAX_TOOL_OUTPUT_PREVIEW)
        self.console.print(f"  [{status_style}]{glyph}[/{status_style}] [dim]{escape(preview)}[/dim]")

    def print_subagent_event(self, task: str, event: AgentEvent) -> None:
        """Live progress for a delegated subagent — indented and dimmed so it reads as
        nested under the tool call that spawned it, distinct from the main conversation."""
        if event.type == AgentEventType.SUBAGENT_STARTED:
            preview = self._truncate(event.data["task"], self.MAX_TOOL_ARGS_PREVIEW)
            self.console.print(
                f"    [muted]▶ subagent '{escape(event.data['task_id'])}' launched in background:[/muted] "
                f"{escape(preview)}"
            )
        elif event.type == AgentEventType.AGENT_START:
            preview = self._truncate(task, self.MAX_TOOL_ARGS_PREVIEW)
            self.console.print(f"    [muted]↳ subagent:[/muted] {escape(preview)}")
        elif event.type == AgentEventType.TOOL_CALL_START:
            style = f"tool.{event.data['kind']}" if f"tool.{event.data['kind']}" in AGENT_THEME.styles else "tool"
            preview = self._truncate(event.data["arguments"], self.MAX_TOOL_ARGS_PREVIEW)
            self.console.print(
                f"      [{style}]⏺ {escape(event.data['tool_name'])}[/{style}] [dim]{escape(preview)}[/dim]"
            )
        elif event.type == AgentEventType.TOOL_CALL_END:
            status_style = "success" if event.data["success"] else "error"
            glyph = "✓" if event.data["success"] else "✗"
            text = event.data["output"] if event.data["success"] else (event.data["error"] or "failed")
            preview = self._truncate(text, self.MAX_TOOL_OUTPUT_PREVIEW)
            self.console.print(f"        [{status_style}]{glyph}[/{status_style}] [dim]{escape(preview)}[/dim]")
        elif event.type == AgentEventType.TEXT_COMPLETE:
            preview = self._truncate(event.data["content"], self.MAX_TOOL_OUTPUT_PREVIEW)
            self.console.print(f"    [muted]↳ subagent done:[/muted] {escape(preview)}")
        elif event.type == AgentEventType.AGENT_ERROR:
            self.console.print(f"    [error]↳ subagent error:[/error] {escape(event.data.get('error_message', ''))}")

    def print_subagent_completed(self, task_id: str, success: bool, output: str) -> None:
        """The top-level 'a background subagent just reported back' notice — distinct from
        print_subagent_event's nested live-progress stream, since this can land at any point
        in a later turn, not necessarily right after the tool call that spawned it."""
        style = "success" if success else "error"
        glyph = "✓" if success else "✗"
        preview = self._truncate(output, self.MAX_TOOL_OUTPUT_PREVIEW)
        self.console.print(
            f"[{style}]\U0001f514 subagent '{escape(task_id)}' {glyph} finished:[/{style}] {escape(preview)}"
        )

    def print_context_compacted(self, messages_removed: int, summary: str) -> None:
        self.console.print(f"[muted]⋯ compacted {messages_removed} earlier message(s)[/muted]")

    def print_error(self, message: str) -> None:
        self.console.print(f"[error]Error:[/error] {escape(message)}")

    def print_agent_end(self, usage: Optional[dict[str, Any]]) -> None:
        if usage:
            self.console.print(f"[dim]tokens: {usage}[/dim]")

    async def confirm_tool(self, confirmation: ToolConfirmation) -> bool:
        """Interactive approval prompt — queued, not a modal that seizes the terminal.
        Prints immediately (so you can see everything pending, even while several
        subagents are running) and queues a Future; your next non-empty typed line
        answers the OLDEST pending one (see resolve_pending_confirmation in main.py's
        reader loop), in the order requests arrived."""
        self.console.print(self._build_confirmation_panel(confirmation))
        future: "asyncio.Future[bool]" = asyncio.get_running_loop().create_future()
        self._pending_confirmations.append(future)
        return await future

    def _build_confirmation_panel(self, confirmation: ToolConfirmation) -> Panel:
        who = "the main agent" if confirmation.source is None else "a background subagent"
        lines = [f"[bold]{escape(confirmation.tool_name)}[/bold] wants to run [muted]({who})[/muted]"]
        if confirmation.source is not None:
            preview = self._truncate(confirmation.source, self.MAX_TOOL_ARGS_PREVIEW)
            lines.append(f"[muted]subagent task:[/muted] {escape(preview)}")
        lines.append(f"[dim]{escape(confirmation.description)}[/dim]")
        for key, value in confirmation.params.items():
            preview = self._truncate(str(value), self.MAX_TOOL_OUTPUT_PREVIEW)
            lines.append(f"[muted]{escape(str(key))}:[/muted] {escape(preview)}")
        lines.append("")
        lines.append("[bold]Allow this action?[/bold] [dim]— your next message answers y/n[/dim]")
        return Panel("\n".join(lines), title="[warning]⚠ Confirmation needed[/warning]", border_style="warning", expand=False)

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        text = text.replace("\n", " ")
        return text if len(text) <= limit else text[:limit] + "..."
