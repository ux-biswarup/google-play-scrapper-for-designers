"""OpenAI and every OpenAI-compatible API (Gemini, OpenRouter, Groq, Mistral, Ollama, custom)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import openai

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
    extract_json_object,
    parse_arguments,
    provider_message,
)

# Model ids containing these are not chat models (embeddings, audio, images, moderation...).
_NON_CHAT_MARKERS = (
    "embed",
    "tts",
    "whisper",
    "dall-e",
    "davinci",
    "babbage",
    "moderation",
    "transcribe",
    "realtime",
    "audio",
    "image",
    "sora",
    "aqa",
    "imagen",
    "veo",
)


def is_chat_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return not any(marker in lowered for marker in _NON_CHAT_MARKERS)


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, config: LLMConfig, *, label: str, base_url: str | None):
        self._model = config.model
        self._label = label
        self._json_mode = True
        self._client = openai.AsyncOpenAI(
            # Local servers such as Ollama ignore the key but the SDK requires a value.
            api_key=config.api_key or "not-needed",
            base_url=base_url,
            max_retries=3,
            timeout=120,
        )

    def _wrap(self, exc: openai.APIError) -> LLMError:
        if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
            return LLMError(f"{self._label} rejected the API key. Check the key and its permissions.", fatal=True)
        if isinstance(exc, openai.NotFoundError):
            return LLMError(f"{self._label} could not find that model. Pick another model.", fatal=True)
        if isinstance(exc, openai.RateLimitError):
            if getattr(exc, "code", None) == "insufficient_quota":
                return LLMError(f"{self._label}: {provider_message(exc)}", fatal=True)
            return LLMError(f"{self._label} rate limit reached. Try fewer reviews or wait a minute.")
        if isinstance(exc, openai.BadRequestError):
            return LLMError(f"{self._label}: {provider_message(exc)}", fatal=True)
        if isinstance(exc, openai.APIConnectionError):
            return LLMError(f"Could not connect to {self._label}. Is the service reachable?", fatal=True)
        return LLMError(f"{self._label} request failed: {provider_message(exc)}")

    async def list_models(self) -> list[ModelInfo]:
        try:
            ids = [m.id async for m in self._client.models.list()]
        except openai.APIError as exc:
            raise self._wrap(exc) from exc
        # Gemini's compatibility endpoint returns ids as "models/<id>".
        cleaned = sorted({i.removeprefix("models/") for i in ids if is_chat_model(i)})
        return [ModelInfo(i, i) for i in cleaned]

    async def complete_json(
        self, *, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 8000
    ) -> tuple[dict[str, Any], Usage]:
        instructions = f"{system}\n\nRespond with one JSON object that matches this JSON Schema:\n{json.dumps(schema)}"
        messages = [{"role": "system", "content": instructions}, {"role": "user", "content": prompt}]
        # Token limits and temperature are omitted on purpose: parameter names and support differ
        # across OpenAI-compatible servers and reasoning models, and the defaults work everywhere.
        try:
            resp = await self._create(messages)
        except openai.BadRequestError as exc:
            if not self._json_mode or "response_format" not in str(exc):
                raise self._wrap(exc) from exc
            self._json_mode = False  # This server doesn't support JSON mode; rely on the prompt instead.
            try:
                resp = await self._create(messages)
            except openai.APIError as retry_exc:
                raise self._wrap(retry_exc) from retry_exc
        except openai.APIError as exc:
            raise self._wrap(exc) from exc

        usage = Usage()
        if resp.usage:
            usage = Usage(resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0)
        content = resp.choices[0].message.content if resp.choices else None
        data = extract_json_object(content or "")
        if data is None:
            raise LLMError("The model did not return valid JSON.")
        return data, usage

    async def _create(self, messages: list[dict[str, str]]):
        kwargs: dict[str, Any] = {"response_format": {"type": "json_object"}} if self._json_mode else {}
        return await self._client.chat.completions.create(model=self._model, messages=messages, **kwargs)

    async def chat_stream(
        self, *, system: str, messages: list[ChatMessage], tools: list[ToolSpec], max_tokens: int = 4000
    ) -> AsyncIterator[ChatEvent]:
        payload = [{"role": "system", "content": system}, *_to_openai(messages)]
        specs = [
            {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in tools
        ]
        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=payload,
                tools=specs or openai.NOT_GIVEN,
                stream=True,
                # Usage in streams is opt-in on OpenAI; other compatible servers may reject the option.
                stream_options={"include_usage": True} if self._label == "OpenAI" else openai.NOT_GIVEN,
            )
            partial: dict[int, dict] = {}  # tool calls arrive in fragments, keyed by index
            usage = Usage()
            async for chunk in stream:
                if chunk.usage:
                    usage = Usage(chunk.usage.prompt_tokens or 0, chunk.usage.completion_tokens or 0)
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    yield TextDelta(delta.content)
                for fragment in delta.tool_calls or []:
                    call = partial.setdefault(fragment.index, {"id": "", "name": "", "arguments": ""})
                    call["id"] = fragment.id or call["id"]
                    if fragment.function:
                        call["name"] += fragment.function.name or ""
                        call["arguments"] += fragment.function.arguments or ""
        except openai.APIError as exc:
            raise self._wrap(exc) from exc
        calls = [
            ToolCall(c["id"] or f"call_{i}", c["name"], parse_arguments(c["arguments"]))
            for i, c in sorted(partial.items())
            if c["name"]
        ]
        yield TurnEnd(calls, usage)

    async def aclose(self) -> None:
        await self._client.close()


def _to_openai(messages: list[ChatMessage]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        elif m.role == "assistant":
            entry: dict = {"role": "assistant", "content": m.content or None}
            if m.tool_calls:
                entry["tool_calls"] = [
                    {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                    for c in m.tool_calls
                ]
            out.append(entry)
        else:
            out.append({"role": "user", "content": m.content})
    return out
