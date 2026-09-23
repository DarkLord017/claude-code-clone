from __future__ import annotations

import os
from asyncio import sleep
from typing import Any, AsyncGenerator

from openai import APIError, AsyncOpenAI, RateLimitError

from client import errors
from client.types import EventType, StreamEvent, TextDelta, ToolCall, TokenUsage
from utils.logging import get_logger

logger = get_logger(__name__)


class LLMClient:
    def __init__(self, max_retries: int = 3) -> None:
        self._client: AsyncOpenAI | None = None
        self._max_retries = max_retries

    def get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=os.environ.get("OPENAI_API_KEY"),
                base_url=os.environ.get("OPENAI_API_BASE_URL", "https://openrouter.ai/api/v1"),
            )
        return self._client

    async def close_client(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        stream: bool = True,
        model: str = "gpt-4o-mini",
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        client = self.get_client()

        kwargs: dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
        if tools:
            kwargs["tools"] = tools
        if stream:
            kwargs["stream_options"] = {"include_usage": True}

        for attempt in range(self._max_retries):
            try:
                if stream:
                    async for event in self._stream_response(client=client, kwargs=kwargs):
                        yield event
                else:
                    yield await self._non_stream_response(client=client, kwargs=kwargs)
                return
            except RateLimitError as e:
                if attempt < self._max_retries - 1:
                    logger.warning("Rate limited (attempt %d/%d), retrying: %s", attempt + 1, self._max_retries, e)
                    await sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error("Rate limit exceeded after %d attempts: %s", self._max_retries, e)
                    yield StreamEvent(
                        type=EventType.ERROR,
                        error_message=errors.rate_limit_exceeded(self._max_retries, e),
                    )
                    return
            except APIError as e:
                logger.error("API error during chat_completion: %s", e)
                yield StreamEvent(type=EventType.ERROR, error_message=errors.api_error(e))
                return
            except Exception as e:
                logger.exception("Unexpected error during chat_completion")
                yield StreamEvent(type=EventType.ERROR, error_message=errors.unexpected_error(e))
                return

    async def _stream_response(
        self, client: AsyncOpenAI, kwargs: dict[str, Any]
    ) -> AsyncGenerator[StreamEvent, None]:
        response = await client.chat.completions.create(**kwargs)

        tool_call_buffers: dict[int, dict[str, str]] = {}
        usage: TokenUsage | None = None

        async for chunk in response:
            if chunk.usage:
                usage = TokenUsage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                    cached_tokens=getattr(chunk.usage, "cached_tokens", 0) or 0,
                )

            if not chunk.choices:
                continue  # trailing usage-only chunk (stream_options include_usage)

            choice = chunk.choices[0]
            delta = choice.delta

            if delta:
                if delta.content:
                    yield StreamEvent(
                        type=EventType.TEXT_DELTA,
                        text_delta=TextDelta(content=delta.content),
                    )

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        buf = tool_call_buffers.setdefault(
                            tc_delta.index, {"id": "", "name": "", "arguments": ""}
                        )
                        if tc_delta.id:
                            buf["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                buf["name"] += tc_delta.function.name
                            if tc_delta.function.arguments:
                                buf["arguments"] += tc_delta.function.arguments

            if choice.finish_reason:
                tool_calls = (
                    [
                        ToolCall(id=buf["id"], name=buf["name"], arguments=buf["arguments"])
                        for buf in tool_call_buffers.values()
                    ]
                    if tool_call_buffers
                    else None
                )
                yield StreamEvent(
                    type=EventType.MESSAGE_COMPLETE,
                    finish_reason=choice.finish_reason,
                    tool_calls=tool_calls,
                    usage=usage,
                )

    async def _non_stream_response(self, client: AsyncOpenAI, kwargs: dict[str, Any]) -> StreamEvent:
        response = await client.chat.completions.create(**kwargs)

        if not response.choices:
            return StreamEvent(type=EventType.ERROR, error_message=errors.NO_CHOICES_RETURNED)

        message = response.choices[0].message
        text_delta = TextDelta(content=message.content) if message.content else None

        tool_calls = None
        if message.tool_calls:
            tool_calls = [
                ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
                for tc in message.tool_calls
            ]

        usage = None
        if response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                cached_tokens=getattr(response.usage, "cached_tokens", 0) or 0,
            )

        return StreamEvent(
            type=EventType.MESSAGE_COMPLETE,
            text_delta=text_delta,
            tool_calls=tool_calls,
            finish_reason=response.choices[0].finish_reason,
            usage=usage,
        )
