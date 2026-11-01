from __future__ import annotations

import asyncio
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from ..context import AppContext, get_ctx
from ..schemas import ReviewWindowIn
from ..services.play_store import MAX_SCAN, parse_store_id

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


@router.post("/review-window")
async def review_window(body: ReviewWindowIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    """How many reviews were written in a period (no AI used). The scan is reused if an analysis starts soon."""
    if not body.date_from and not body.date_to:
        raise ValueError("Choose a period first.")
    window = await asyncio.to_thread(
        ctx.pipeline.window,
        parse_store_id(body.app),
        lang=body.lang,
        country=body.country.lower(),
        date_from=body.date_from,
        date_to=body.date_to,
        ratings=sorted(set(body.ratings)) if body.ratings else None,
    )
    dates = [r.reviewed_at for r in window.reviews if r.reviewed_at]
    return {
        "in_range": len(window.reviews),
        "complete": window.complete,
        "scanned": window.scanned,
        "max_scan": MAX_SCAN,
        "oldest_reached": window.oldest_reached.date().isoformat() if window.oldest_reached else None,
        "first_review": min(dates).date().isoformat() if dates else None,
        "last_review": max(dates).date().isoformat() if dates else None,
    }
