"""Catalog of supported AI providers and a factory that builds the right client."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass

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
)


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    name: str
    kind: str  # "anthropic", "openai" (OpenAI-compatible API) or "chatgpt" (ChatGPT plan sign-in)
    base_url: str | None
    requires_key: bool
    key_url: str | None = None
    requires_base_url: bool = False
    env_var: str | None = None  # optional fallback key from the environment / .env

    def env_key(self) -> str | None:
        return os.getenv(self.env_var) if self.env_var else None

    def env_model(self) -> str | None:
        """Optional preselected model, e.g. OPENAI_MODEL in .env."""
        return (os.getenv(f"{self.id.upper()}_MODEL") or "").strip() or None

    def to_dict(self) -> dict:
        return asdict(self) | {"has_env_key": bool(self.env_key()), "default_model": self.env_model()}


PROVIDERS: dict[str, ProviderSpec] = {
    spec.id: spec
    for spec in (
        ProviderSpec(
            "anthropic",
            "Anthropic (Claude)",
            "anthropic",
            None,
            True,
            "https://console.anthropic.com/settings/keys",
            env_var="ANTHROPIC_API_KEY",
        ),
        ProviderSpec(
            "openai", "OpenAI", "openai", None, True, "https://platform.openai.com/api-keys", env_var="OPENAI_API_KEY"
        ),
        ProviderSpec(
            "gemini",
            "Google Gemini",
            "openai",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            True,
            "https://aistudio.google.com/apikey",
            env_var="GEMINI_API_KEY",
        ),
        ProviderSpec(
            "openrouter",
            "OpenRouter",
            "openai",
            "https://openrouter.ai/api/v1",
            True,
            "https://openrouter.ai/keys",
            env_var="OPENROUTER_API_KEY",
        ),
        ProviderSpec(
            "groq",
            "Groq",
            "openai",
            "https://api.groq.com/openai/v1",
            True,
            "https://console.groq.com/keys",
            env_var="GROQ_API_KEY",
        ),
        ProviderSpec(
            "mistral",
            "Mistral",
            "openai",
            "https://api.mistral.ai/v1",
            True,
            "https://console.mistral.ai/api-keys",
            env_var="MISTRAL_API_KEY",
        ),
        ProviderSpec("chatgpt", "ChatGPT plan", "chatgpt", None, False, "https://chatgpt.com/#settings"),
        ProviderSpec("ollama", "Ollama (local)", "openai", "http://localhost:11434/v1", False),
        ProviderSpec("custom", "Custom (OpenAI-compatible)", "openai", None, False, requires_base_url=True),
    )
}


def resolve_config(config: LLMConfig) -> LLMConfig:
    """Fill in the key and model from the environment when the user didn't set them in the interface."""
    spec = PROVIDERS.get(config.provider)
    if spec is None:
        raise LLMError(f"Unknown provider '{config.provider}'.", fatal=True)
    return LLMConfig(
        config.provider,
        config.model or spec.env_model() or "",
        config.api_key or spec.env_key(),
        config.base_url,
    )


def create_provider(config: LLMConfig) -> LLMProvider:
    config = resolve_config(config)
    spec = PROVIDERS[config.provider]
    if spec.requires_key and not config.api_key:
        raise LLMError(f"{spec.name} needs an API key.", fatal=True)
    base_url = config.base_url or spec.base_url
    if spec.requires_base_url and not base_url:
        raise LLMError("Enter the base URL of your OpenAI-compatible server.", fatal=True)

    if spec.kind == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(config)
    if spec.kind == "chatgpt":
        from ..services.chatgpt_auth import get_auth
        from .chatgpt_provider import ChatGPTProvider

        return ChatGPTProvider(config, get_auth())
    from .openai_provider import OpenAICompatibleProvider

    return OpenAICompatibleProvider(config, label=spec.name, base_url=base_url)


__all__ = [
    "PROVIDERS",
    "ChatEvent",
    "ChatMessage",
    "TextDelta",
    "ToolCall",
    "ToolSpec",
    "TurnEnd",
    "LLMConfig",
    "LLMError",
    "LLMProvider",
    "ModelInfo",
    "ProviderSpec",
    "Usage",
    "create_provider",
    "resolve_config",
    "extract_json_object",
]
