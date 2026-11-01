from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import anthropic

from .base import (
    ChatEvent,
    ChatMessage,
    LLMConfig,
    LLMError,
    LLMProvider,
    ModelInfo,
    TextDelta,
    ToolCall,
    ToolSpec,
    TurnEnd,
    Usage,
    provider_message,
)

_TOOL_NAME = "submit_result"


def _wrap(exc: anthropic.APIError) -> LLMError:
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return LLMError("Anthropic rejected the API key. Check the key and its permissions.", fatal=True)
    if isinstance(exc, anthropic.NotFoundError):
        return LLMError("Anthropic could not find that model. Pick another model.", fatal=True)
    if isinstance(exc, anthropic.BadRequestError):
        # e.g. "credit balance is too low": every other request would fail the same way.
        return LLMError(f"Anthropic: {provider_message(exc)}", fatal=True)
    if isinstance(exc, anthropic.RateLimitError):
        return LLMError("Anthropic rate limit reached. Try fewer reviews or wait a minute.")
    if isinstance(exc, anthropic.APIConnectionError):
        return LLMError("Could not connect to Anthropic. Check your internet connection.")
    return LLMError(f"Anthropic request failed: {provider_message(exc)}")


class AnthropicProvider(LLMProvider):
    def __init__(self, config: LLMConfig):
        self._model = config.model
        self._client = anthropic.AsyncAnthropic(
            api_key=config.api_key, base_url=config.base_url or None, max_retries=3, timeout=120
        )

    async def list_models(self) -> list[ModelInfo]:
        try:
            models = [ModelInfo(m.id, m.display_name or m.id) async for m in self._client.models.list(limit=100)]
        except anthropic.APIError as exc:
            raise _wrap(exc) from exc
        return models

    async def complete_json(
        self, *, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 8000
    ) -> tuple[dict[str, Any], Usage]:
        # Forcing a tool call is Anthropic's most reliable way to get schema-shaped JSON.
        tool = {"name": _TOOL_NAME, "description": "Submit the structured result.", "input_schema": schema}
        try:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                tools=[tool],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
            )
        except anthropic.APIError as exc:
            raise _wrap(exc) from exc
        usage = Usage(resp.usage.input_tokens or 0, resp.usage.output_tokens or 0)
        for block in resp.content:
            if block.type == "tool_use" and isinstance(block.input, dict):
                return dict(block.input), usage
        raise LLMError("The model did not return structured output.")

    async def chat_stream(
        self, *, system: str, messages: list[ChatMessage], tools: list[ToolSpec], max_tokens: int = 4000
    ) -> AsyncIterator[ChatEvent]:
        try:
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=_to_anthropic(messages),
                tools=[{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools],
            ) as stream:
                async for event in stream:
                    if event.type == "text":
                        yield TextDelta(event.text)
                final = await stream.get_final_message()
        except anthropic.APIError as exc:
            raise _wrap(exc) from exc
        calls = [
            ToolCall(block.id, block.name, dict(block.input or {}))
            for block in final.content
            if block.type == "tool_use"
        ]
        yield TurnEnd(calls, Usage(final.usage.input_tokens or 0, final.usage.output_tokens or 0))

    async def aclose(self) -> None:
        await self._client.close()


def _to_anthropic(messages: list[ChatMessage]) -> list[dict]:
    """Anthropic wants tool calls as content blocks, and tool results inside the next user message."""
    out: list[dict] = []
    for m in messages:
        if m.role == "tool":
            block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
        elif m.role == "assistant":
            blocks: list[dict] = [{"type": "text", "text": m.content}] if m.content else []
            blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in m.tool_calls]
            out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": "…"}]})
        else:
            out.append({"role": "user", "content": m.content})
    return out
