from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import AsyncGenerator

from agent import errors
from agent.types import AgentEvent, AgentEventType, ConfirmCallback
from client import EventType, LLMClient
from client.types import ToolCall
from config.types import Config
from context.manager import ContextManager
from context.types import Message
from prompts.system import get_compression_prompt
from tools.builtin import create_default_registry
from tools.builtin.compact_context import CompactContextTool
from tools.builtin.subagent import OnSubagentEvent, SubagentTool
from tools.registry import ToolRegistry
from tools.types import ToolConfirmation, ToolInvocation, ToolResult
from utils.logging import get_logger

logger = get_logger(__name__)


class Agent:
    MAX_TOOL_ITERATIONS = 10

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        registry: ToolRegistry | None = None,
        cwd: Path | None = None,
        on_confirm: ConfirmCallback | None = None,
        config: Config | None = None,
        auto_fill_tools: bool = True,
        on_subagent_event: OnSubagentEvent | None = None,
        subagent_label: str | None = None,
    ) -> None:
        self._client = LLMClient()
        self._config = config or Config()
        self._model_name = model_name
        self._cwd = cwd or Path.cwd()
        self._on_confirm = on_confirm
        self._on_subagent_event = on_subagent_event
        # None for the main agent; a subagent's own task description otherwise — lets the
        # approval prompt say *who* is asking, since subagents share the same on_confirm.
        self._subagent_label = subagent_label

        self._registry = create_default_registry(
            config=self._config,
            get_context_manager=lambda: self._context_manager,
            summarize=self._summarize,
            registry=registry,
            auto_fill=auto_fill_tools,
            get_parent_registry=lambda: self._registry,
            build_subagent=self._build_subagent,
            on_subagent_event=self._on_subagent_event,
        )

        self._context_manager = ContextManager(
            model_name=model_name, config=self._config, tools=self._registry.list_tools()
        )

    def _build_subagent(self, task: str, scoped_registry: ToolRegistry) -> "Agent":
        """Always uses the main agent's own model — no LLM-controlled override. An LLM-supplied
        model string can't be trusted to be a real, valid model ID (this crashed a subagent
        once with 'text-davinci-003 is not a valid model ID' when the LLM guessed one)."""
        logger.info("Spawning subagent for task: %s", task[:80])
        return Agent(
            model_name=self._model_name,
            registry=scoped_registry,
            auto_fill_tools=False,
            cwd=self._cwd,
            config=self._config,
            on_confirm=self._on_confirm,
            on_subagent_event=self._on_subagent_event,
            subagent_label=task,
        )

    async def _request_approval(self, confirmation: ToolConfirmation) -> bool:
        """No callback configured means mutating actions are denied by default, not silently allowed."""
        if self._on_confirm is None:
            logger.info("No confirmation handler configured — denying '%s' by default", confirmation.tool_name)
            return False
        if self._subagent_label is not None:
            confirmation = replace(confirmation, source=self._subagent_label)
        return await self._on_confirm(confirmation)

    async def run(self, message: str):
        yield AgentEvent.agent_start(message=message)
        self._context_manager.add_user_message(message)

        final_response: str | None = None
        async for event in self._agentic_loop():
            yield event

            if event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content")

        yield AgentEvent.agent_end(final_response)

    async def _agentic_loop(self) -> AsyncGenerator[AgentEvent, None]:
        for _ in range(self.MAX_TOOL_ITERATIONS):
            async for subagent_event in self._check_subagents():
                yield subagent_event

            response_text = ""
            tool_calls: list[ToolCall] = []

            async for event in self._client.chat_completion(
                messages=self._context_manager.messages,
                model=self._model_name,
                tools=self._registry.to_schema_list() or None,
                stream=True,
            ):
                if event.type == EventType.TEXT_DELTA:
                    yield AgentEvent.text_delta(content=event.text_delta.content)
                    response_text += event.text_delta.content
                elif event.type == EventType.ERROR:
                    logger.error("LLM stream error: %s", event.error_message)
                    yield AgentEvent.agent_error(error=event.error_message or errors.UNKNOWN_STREAM_ERROR)
                    return
                elif event.type == EventType.MESSAGE_COMPLETE:
                    tool_calls = event.tool_calls or []
                    if event.usage:
                        self._context_manager.update_usage(event.usage)

            if self._context_manager.should_compact():
                async for compaction_event in self._compact():
                    yield compaction_event

            if not tool_calls:
                self._context_manager.add_assistant_message(response_text or None)
                if response_text:
                    yield AgentEvent.text_complete(content=response_text)
                return

            self._context_manager.add_tool_call_message(tool_calls)

            for call in tool_calls:
                logger.info("Calling tool '%s' (id=%s)", call.name, call.id)
                tool = self._registry.get(call.name)
                kind = tool.kind.value if tool else "unknown"

                yield AgentEvent.tool_call_start(
                    tool_name=call.name, tool_call_id=call.id, arguments=call.arguments, kind=kind
                )

                try:
                    params = json.loads(call.arguments) if call.arguments else {}
                except json.JSONDecodeError as e:
                    result = ToolResult.error_result(errors.invalid_tool_arguments(e))
                else:
                    invocation = ToolInvocation(params=params, cwd=self._cwd)
                    confirmation = await tool.get_confirmation(invocation) if tool else None

                    if confirmation is not None and not await self._request_approval(confirmation):
                        logger.info("Tool call denied: %s", confirmation.description)
                        result = ToolResult.error_result(errors.action_denied(confirmation.description))
                    else:
                        result = await self._registry.execute(call.name, invocation)

                yield AgentEvent.tool_call_end(
                    tool_name=call.name, tool_call_id=call.id, result=result, kind=kind
                )

                if call.name == CompactContextTool.name and result.success:
                    yield AgentEvent.context_compacted(
                        messages_removed=result.metadata["messages_removed"],
                        summary=result.metadata["summary"],
                    )

                self._context_manager.add_tool_result_message(
                    tool_call_id=call.id,
                    content=result.output if result.success else (result.error or errors.TOOL_FAILED_FALLBACK),
                )

        logger.warning("Stopped after %d tool iterations without a final answer", self.MAX_TOOL_ITERATIONS)
        yield AgentEvent.agent_error(error=errors.tool_iteration_limit_reached(self.MAX_TOOL_ITERATIONS))

    async def _check_subagents(self) -> AsyncGenerator[AgentEvent, None]:
        """Surface any background subagents that finished since the last check — injects a
        notification into the conversation so the next LLM call sees it, and yields an event
        so the UI shows it immediately, before whatever this loop does next."""
        subagent_tool = self._registry.get(SubagentTool.name)
        if subagent_tool is None:
            return

        for task_id, result in subagent_tool.pop_completed():
            status = "finished" if result.success else "failed"
            content = result.output if result.success else (result.error or "no result")
            logger.info("Subagent '%s' %s", task_id, status)
            self._context_manager.add_system_notice(f"[Subagent '{task_id}' {status}]\n{content}")
            yield AgentEvent.subagent_completed(task_id=task_id, success=result.success, output=content)

    async def _compact(self) -> AsyncGenerator[AgentEvent, None]:
        """Automatic safety-net trigger — runs the compact_context tool directly, bypassing
        the approval gate on purpose (it can't be silently skipped just because no on_confirm
        callback is configured, or the safety net does nothing)."""
        if self._context_manager.compaction_range() is None:
            logger.warning("Context is over budget but nothing is safe to compact")
            return

        result = await self._registry.execute("compact_context", ToolInvocation(params={}, cwd=self._cwd))
        if not result.success:
            logger.warning("Auto-compaction failed: %s", result.error)
            return

        yield AgentEvent.context_compacted(
            messages_removed=result.metadata["messages_removed"],
            summary=result.metadata["summary"],
        )

    async def _summarize(
        self, messages_to_summarize: list[Message], instruction: str | None = None
    ) -> str | None:
        compression_prompt = get_compression_prompt()
        if instruction:
            compression_prompt += f"\n\nAdditional instruction from the user: {instruction}"

        prompt_messages = [
            {"role": "system", "content": self._context_manager.system_prompt},
            *messages_to_summarize,
            {"role": "user", "content": compression_prompt},
        ]

        async for event in self._client.chat_completion(
            messages=prompt_messages,
            model=self._model_name,
            tools=None,
            stream=False,
        ):
            if event.type == EventType.MESSAGE_COMPLETE:
                return event.text_delta.content if event.text_delta else None
            if event.type == EventType.ERROR:
                logger.error("Compaction summary call failed: %s", event.error_message)
                return None
        return None

    async def __aenter__(self) -> "Agent":
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        await self._client.close_client()
