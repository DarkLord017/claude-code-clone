from __future__ import annotations

import asyncio
from pathlib import Path

import click
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

from agent import Agent, AgentEventType
from config.loader import build_config
from config.types import Config
from ui.tui import TUI, get_console

class CLI:
    def __init__(self, model: str, config: Config) -> None:
        self.tui = TUI(get_console())
        self.model = model
        self.config = config

    def _build_agent(self) -> Agent:
        return Agent(
            model_name=self.model,
            cwd=self.config.cwd,
            config=self.config,
            on_confirm=self.tui.confirm_tool,
            on_subagent_event=self.tui.print_subagent_event,
        )

    async def run_single(self, prompt: str) -> None:
        async with self._build_agent() as agent:
            await self._process_message(agent, prompt)

    async def run_interactive(self) -> None:
        self.tui.console.print(
            "[accent]Claude Code (clone)[/accent] — type a message, or Ctrl+D to exit.\n"
        )
        queue: asyncio.Queue = asyncio.Queue()

        async def reader() -> None:
            while True:
                try:
                    message = await self.tui.read_line("> ")
                except (EOFError, KeyboardInterrupt):
                    self.tui.console.print()
                    self.tui.cancel_pending_confirmations()
                    await queue.put(None)  # sentinel: tells the runner to stop too
                    return
                if message.strip() and self.tui.resolve_pending_confirmation(message):
                    continue
                if message.strip():
                    await queue.put(message)

        async def runner(agent: Agent) -> None:
            while True:
                message = await queue.get()
                if message is None:
                    return
                await self._process_message(agent, message)
                self.tui.console.print()

        async with self._build_agent() as agent:
            await asyncio.gather(reader(), runner(agent))

    async def _process_message(self, agent: Agent, message: str) -> None:
        async for event in agent.run(message=message):
            if event.type == AgentEventType.TEXT_DELTA:
                self.tui.stream_assistant_delta(event.data["content"])
            elif event.type == AgentEventType.TEXT_COMPLETE:
                self.tui.print_text_complete()
            elif event.type == AgentEventType.TOOL_CALL_START:
                self.tui.print_tool_call_start(
                    tool_name=event.data["tool_name"],
                    kind=event.data["kind"],
                    arguments=event.data["arguments"],
                )
            elif event.type == AgentEventType.TOOL_CALL_END:
                self.tui.print_tool_call_end(
                    tool_name=event.data["tool_name"],
                    kind=event.data["kind"],
                    success=event.data["success"],
                    output=event.data["output"],
                    error=event.data["error"],
                )
            elif event.type == AgentEventType.SUBAGENT_COMPLETED:
                self.tui.print_subagent_completed(
                    task_id=event.data["task_id"],
                    success=event.data["success"],
                    output=event.data["output"],
                )
            elif event.type == AgentEventType.CONTEXT_COMPACTED:
                self.tui.print_context_compacted(
                    messages_removed=event.data["messages_removed"],
                    summary=event.data["summary"],
                )
            elif event.type == AgentEventType.AGENT_ERROR:
                self.tui.print_error(event.data.get("error_message", "Unknown error"))
            elif event.type == AgentEventType.AGENT_END:
                self.tui.print_agent_end(event.data.get("usage"))


@click.command()
@click.argument("prompt", required=False)
@click.option("--model", default="gpt-4o-mini", show_default=True, help="Model to use (via OpenRouter).")
@click.option(
    "--cwd",
    "cwd_str",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    help="Working directory for the agent (default: current directory). Also where AGENTS.md discovery starts.",
)
@click.option(
    "--instructions",
    default=None,
    help="Ad-hoc user instructions to add to the system prompt for this run.",
)
def main(prompt: str | None, model: str, cwd_str: str | None, instructions: str | None) -> None:
    config = build_config(
        cwd=Path(cwd_str) if cwd_str else None,
        user_instructions=instructions,
    )
    cli = CLI(model=model, config=config)

    if prompt:
        asyncio.run(cli.run_single(prompt))
    else:
        asyncio.run(cli.run_interactive())


if __name__ == "__main__":
    main()
