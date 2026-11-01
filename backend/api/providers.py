from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from ..context import AppContext, get_ctx
from ..providers import PROVIDERS, LLMError, resolve_config
from ..schemas import LLMConfigIn, TestConnectionIn
from ..services.chatgpt_auth import get_auth

router = APIRouter(prefix="/providers", tags=["providers"])

_PING_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


@router.get("")
def list_providers() -> list[dict]:
    providers = [spec.to_dict() for spec in PROVIDERS.values()]
    for p in providers:
        # "connected": a provider usable without a key; for ChatGPT it means signed in with plan usage.
        p["connected"] = get_auth().status()["plan_usage"] if p["id"] == "chatgpt" else None
    return providers


@router.post("/models")
async def list_models(body: LLMConfigIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    """List models for a provider + key. Doubles as a key check."""
    provider = ctx.provider_factory(body.to_config())
    try:
        models = await provider.list_models()
    finally:
        await provider.aclose()
    return {"models": [{"id": m.id, "name": m.name} for m in models]}


@router.post("/test")
async def test_connection(body: TestConnectionIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Send a tiny structured request to confirm the key and model both work."""
    config = resolve_config(body.to_config())
    if not config.model:
        raise LLMError("Choose a model first.", fatal=True)
    provider = ctx.provider_factory(config)
    started = time.perf_counter()
    try:
        data, _usage = await provider.complete_json(
            system="You are a health check.", prompt='Reply with {"ok": true}.', schema=_PING_SCHEMA, max_tokens=50
        )
    finally:
        await provider.aclose()
    return {"ok": bool(data.get("ok", True)), "latency_ms": round((time.perf_counter() - started) * 1000)}
