"""OpenAI and every OpenAI-compatible API (Gemini, OpenRouter, Groq, Mistral, Ollama, custom)."""

from __future__ import annotations

import json
from typing import Any

import openai

from .base import LLMConfig, LLMError, LLMProvider, ModelInfo, Usage, extract_json_object, provider_message

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

    async def aclose(self) -> None:
        await self._client.close()
