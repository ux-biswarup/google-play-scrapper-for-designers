"""Provider-agnostic LLM interface used by the analysis pipeline (and later the chat assistant)."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMConfig:
    """Which model to call and how. The API key lives only in memory for the duration of a request/job."""

    provider: str
    model: str
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None

    @property
    def model_key(self) -> str:
        """Stable identifier used to cache per-review insights per model."""
        return f"{self.provider}:{self.model}"


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str


class LLMError(Exception):
    """An LLM call failed. `fatal` means retrying other requests won't help (bad key, unknown model)."""

    def __init__(self, message: str, *, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


class LLMProvider(ABC):
    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Models available to this key. Also serves as a connection/key check."""

    @abstractmethod
    async def complete_json(
        self, *, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 8000
    ) -> tuple[dict[str, Any], Usage]:
        """Return a JSON object matching `schema` (validated by the caller) plus token usage."""

    async def aclose(self) -> None:  # pragma: no cover - trivial default
        return None


def provider_message(exc: Exception) -> str:
    """The human-readable reason a provider gave for an error (e.g. "credit balance is too low")."""
    body = getattr(exc, "body", None)
    message = None
    if isinstance(body, dict):
        error = body.get("error", body)
        message = error.get("message") if isinstance(error, dict) else None
    message = message or getattr(exc, "message", None) or str(exc)
    return " ".join(str(message).split())[:300]


_CODE_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```")


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Parse the first JSON object in a model response, tolerating code fences and surrounding prose."""
    text = (text or "").strip()
    fenced = _CODE_FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None
