from __future__ import annotations

from typing import Any

from client.types import TokenUsage, ToolCall
from config.types import Config
from context.constants import context_window_for
from context.types import Message
from memory.store import read_index
from prompts.system import get_system_prompt
from tools.base import Tool
from utils.logging import get_logger
from utils.text import count_tokens

logger = get_logger(__name__)


class ContextManager:
    COMPACTION_THRESHOLD = 0.9  # trigger once real usage crosses 90% of the model's context window
    KEEP_LAST_MESSAGES = 10  # most recent messages always kept verbatim, before pair-safety adjustment

    def __init__(
        self,
        model_name: str = "gpt-4o",
        config: Config | None = None,
        tools: list[Tool] | None = None,
    ) -> None:
        self._config = config or Config()
        user_memory = read_index(self._config.memory_dir)
        self._system_prompt: str = get_system_prompt(self._config, user_memory=user_memory, tools=tools)
        self._model_name: str = model_name
        self._messages: list[Message] = []
        self._total_tokens: int = 0
        self._last_prompt_tokens: int | None = None  # real usage from the API's last response

    def add_user_message(self, content: Any) -> None:
        self._add_message({"role": "user", "content": content})

    def add_assistant_message(self, content: Any) -> None:
        self._add_message({"role": "assistant", "content": content})

    def add_tool_call_message(self, tool_calls: list[ToolCall]) -> None:
        """The assistant turn where the model asked to call one or more tools."""
        self._add_message({
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in tool_calls
            ],
        })

    def add_tool_result_message(self, tool_call_id: str, content: str) -> None:
        """The result of one tool call, matched back to the request via tool_call_id."""
        self._add_message({"role": "tool", "tool_call_id": tool_call_id, "content": content})

    def _add_message(self, message: Message) -> None:
        self._messages.append(message)
        content = message.get("content")
        if isinstance(content, str):
            self._total_tokens += count_tokens(content, self._model_name)

    def update_usage(self, usage: TokenUsage) -> None:
        """Record the real prompt token count the API reported for the last request."""
        self._last_prompt_tokens = usage.prompt_tokens

    def should_compact(self) -> bool:
        if self._last_prompt_tokens is None:
            return False
        window = context_window_for(self._model_name)
        return self._last_prompt_tokens > self.COMPACTION_THRESHOLD * window

    def compaction_range(self) -> tuple[int, int] | None:
        """(start, end) of the message range to summarize away, or None if there's nothing safe to compact."""
        total = len(self._messages)
        cut = self._safe_cut(max(0, total - self.KEEP_LAST_MESSAGES))
        if cut <= 0:
            return None
        return (0, cut)

    def _safe_cut(self, cut: int) -> int:
        """Never land on a tool result whose matching tool-call request would be compacted away."""
        while cut > 0 and self._messages[cut].get("role") == "tool":
            cut -= 1
        return cut

    def messages_slice(self, start: int, end: int) -> list[Message]:
        return self._messages[start:end]

    def apply_compaction(self, end: int, summary: str) -> None:
        """Replace messages[0:end] with a single system-role summary message."""
        logger.info("Compacted %d messages into a summary", end)
        summary_message: Message = {
            "role": "system",
            "content": f"[Compacted summary of {end} earlier message(s)]\n{summary}",
        }
        self._messages = [summary_message, *self._messages[end:]]
        self._last_prompt_tokens = None  # stale until the next real API response

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @property
    def messages(self) -> list[Message]:
        return [{"role": "system", "content": self._system_prompt}, *self._messages]

    @property
    def total_tokens(self) -> int:
        return self._total_tokens
