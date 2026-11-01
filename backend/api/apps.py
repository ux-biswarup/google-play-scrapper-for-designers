from __future__ import annotations

import asyncio
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from ..context import AppContext, get_ctx
from ..services.play_store import parse_store_id

router = APIRouter(prefix="/apps", tags=["apps"])


@router.get("/search")
async def search_apps(
    q: str = Query(min_length=2),
    country: str = "us",
    lang: str = "en",
    limit: int = Query(10, ge=1, le=30),
    ctx: AppContext = Depends(get_ctx),
) -> list[dict]:
    hits = await asyncio.to_thread(ctx.store.search, q, lang=lang, country=country, limit=limit)
    return [asdict(h) for h in hits]


@router.get("/lookup")
async def lookup_app(
    id: str = Query(min_length=3, description="App ID or Play Store link"),
    country: str = "us",
    lang: str = "en",
    ctx: AppContext = Depends(get_ctx),
) -> dict:
    details = await asyncio.to_thread(ctx.store.app_details, parse_store_id(id), lang=lang, country=country)
    return asdict(details)
