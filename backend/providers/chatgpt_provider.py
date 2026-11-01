"""Models on the user's ChatGPT plan (Sign in with ChatGPT), via the public Responses API.

Per OpenAI's plan-usage docs every request streams with store=false, system text goes in `instructions`,
and parameters such as temperature or max_output_tokens are not accepted. Function tools on this route
must use a format the docs don't show, so the assistant uses a plain-text tool protocol instead:
the model writes <tool_call>{...}</tool_call>, the app runs the tool and sends back the result.
"""

from __future__ import annotations

import asyncio
import json
import re
import ssl
import uuid
from collections.abc import AsyncIterator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi
import openai

from ..services.chatgpt_auth import RESOURCE, ChatGPTAuth, ChatGPTAuthError
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

OPEN_TAG, CLOSE_TAG = "<tool_call>", "</tool_call>"
TOOL_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
MANAGE_USAGE = "Manage usage in ChatGPT settings."

ERRORS = {
    "subscription_sharing_usage_limit_exceeded": f"Usage limit reached on your ChatGPT plan. {MANAGE_USAGE}",
    "subscription_sharing_user_not_eligible": "ChatGPT plan usage isn't available for this account or workspace.",
    "subscription_sharing_usage_unavailable": "ChatGPT couldn't check your plan usage right now. Try again shortly.",
    "subscription_sharing_unsupported_capability": "ChatGPT plan usage doesn't support this request.",
    "subscription_sharing_invalid_user": "ChatGPT didn't accept this sign-in. Sign out and sign in again.",
}

TOOL_PROTOCOL = """
You can look things up with these tools:
{tools}

To use a tool, write exactly this on its own line and then stop:
<tool_call>{{"name": "TOOL_NAME", "arguments": {{...}}}}</tool_call>
You may write several tool_call lines at once. You will get the results back, then continue.
When you have what you need, answer normally without any tool_call tags."""


def _error(code: str | None, fallback: str) -> LLMError:
    message = ERRORS.get(code or "", fallback)
    # Retrying won't help for limits, eligibility or bad credentials; it might for "unavailable".
    return LLMError(message, fatal=code != "subscription_sharing_usage_unavailable")


def _tool_prompt(tools: list[ToolSpec]) -> str:
    lines = [
        f"- {t.name}: {' '.join(t.description.split())} Arguments (JSON Schema): {json.dumps(t.parameters)}"
        for t in tools
    ]
    return TOOL_PROTOCOL.format(tools="\n".join(lines))


def _to_input(messages: list[ChatMessage]) -> list[dict]:
    items: list[dict] = []
    for m in messages:
        if m.role == "tool":
            text = f'<tool_result name="{m.name}">{m.content}</tool_result>'
            if items and items[-1]["role"] == "user" and items[-1]["content"].startswith("<tool_result"):
                items[-1]["content"] += "\n" + text
            else:
                items.append({"role": "user", "content": text})
        elif m.role == "assistant":
            calls = "\n".join(
                f"{OPEN_TAG}{json.dumps({'name': c.name, 'arguments': c.arguments})}{CLOSE_TAG}" for c in m.tool_calls
            )
            content = "\n".join(part for part in (m.content, calls) if part)
            items.append({"role": "assistant", "content": content or "…"})
        else:
            items.append({"role": "user", "content": m.content})
    return items


def split_tool_calls(text: str) -> tuple[str, list[ToolCall]]:
    """Separate visible text from <tool_call> blocks written by the model."""
    calls = []
    for match in TOOL_CALL.finditer(text):
        data = parse_arguments(match.group(1))
        if data.get("name"):
            calls.append(
                ToolCall(f"call_{uuid.uuid4().hex[:12]}", str(data["name"]), parse_arguments(data.get("arguments")))
            )
    visible = text.split(OPEN_TAG, 1)[0].rstrip() if calls else text
    return visible, calls


def safe_prefix(buffer: str) -> int:
    """How much of the streamed buffer can be shown: never a <tool_call> tag or the start of one."""
    if OPEN_TAG in buffer:
        return buffer.index(OPEN_TAG)
    for size in range(min(len(OPEN_TAG) - 1, len(buffer)), 0, -1):
        if OPEN_TAG.startswith(buffer[-size:]):
            return len(buffer) - size
    return len(buffer)


class ChatGPTProvider(LLMProvider):
    def __init__(self, config: LLMConfig, auth: ChatGPTAuth):
        self._model = config.model
        self._auth = auth
        self.last_usage = Usage()

    async def _token(self) -> str:
        try:
            return await asyncio.to_thread(self._auth.access_token)
        except ChatGPTAuthError as exc:
            raise LLMError(str(exc), fatal=True) from exc

    async def list_models(self) -> list[ModelInfo]:
        token = await self._token()

        def fetch() -> dict:
            request = Request(f"{RESOURCE}/models", headers={"Authorization": f"Bearer {token}"})
            try:
                with urlopen(request, context=ssl.create_default_context(cafile=certifi.where()), timeout=30) as r:
                    return json.loads(r.read())
            except HTTPError as exc:
                raise LLMError(f"ChatGPT couldn't list models (HTTP {exc.code}).", fatal=True) from exc
            except URLError as exc:
                raise LLMError("Could not reach OpenAI.", fatal=True) from exc

        data = await asyncio.to_thread(fetch)
        return [
            ModelInfo(m["slug"], m.get("display_name") or m["slug"])
            for m in data.get("models", [])
            if m.get("visibility") == "list" and m.get("slug")
        ]

    async def _stream(self, instructions: str, items: list[dict]) -> AsyncIterator[str]:
        client = openai.AsyncOpenAI(api_key=await self._token(), base_url=RESOURCE, max_retries=0, timeout=180)
        completed = False
        try:
            stream = await client.responses.create(
                model=self._model, instructions=instructions, input=items, store=False, stream=True
            )
            async for event in stream:
                if event.type == "response.output_text.delta":
                    yield event.delta
                elif event.type == "response.completed":
                    completed = True
                    usage = event.response.usage
                    if usage:
                        self.last_usage = Usage(usage.input_tokens or 0, usage.output_tokens or 0)
                elif event.type == "response.failed":
                    error = event.response.error
                    raise _error(error.code if error else None, "ChatGPT couldn't complete the request.")
                elif event.type == "response.incomplete":
                    raise LLMError("ChatGPT stopped before finishing the answer.")
        except openai.APIStatusError as exc:
            body = exc.body if isinstance(exc.body, dict) else {}
            error = body.get("error", body) if isinstance(body.get("error", body), dict) else {}
            raise _error(error.get("code"), f"ChatGPT request failed: {provider_message(exc)}") from exc
        except openai.APIConnectionError as exc:
            raise LLMError("Could not reach OpenAI. Check your internet connection.") from exc
        finally:
            await client.close()
        if not completed:
            raise LLMError("The ChatGPT response ended unexpectedly. Try again.")

    async def complete_json(
        self, *, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 8000
    ) -> tuple[dict[str, Any], Usage]:
        instructions = (
            f"{system}\n\nRespond with only one JSON object that matches this JSON Schema:\n{json.dumps(schema)}"
        )
        text = "".join([part async for part in self._stream(instructions, [{"role": "user", "content": prompt}])])
        data = extract_json_object(text)
        if data is None:
            raise LLMError("ChatGPT did not return valid JSON.")
        return data, self.last_usage

    async def chat_stream(
        self, *, system: str, messages: list[ChatMessage], tools: list[ToolSpec], max_tokens: int = 4000
    ) -> AsyncIterator[ChatEvent]:
        buffer, shown = "", 0
        async for delta in self._stream(system + _tool_prompt(tools), _to_input(messages)):
            buffer += delta
            visible = safe_prefix(buffer)
            if visible > shown:
                yield TextDelta(buffer[shown:visible])
                shown = visible
        text, calls = split_tool_calls(buffer)
        if len(text) > shown:
            yield TextDelta(text[shown:])
        yield TurnEnd(calls, self.last_usage)
