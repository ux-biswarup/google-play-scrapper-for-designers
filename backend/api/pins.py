"""Pinboard: quotes a designer or PM pins while exploring an analysis, to use as evidence in the report."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from ..analytics.frame import load_run_frame
from ..analytics.insights import review_dict
from ..context import AppContext, get_ctx
from ..models import Pin

router = APIRouter(prefix="/runs/{run_id}/pins", tags=["pins"])


class PinIn(BaseModel):
    note: str = Field("", max_length=1000)


def pinned_reviews(ctx: AppContext, run_id: str) -> list[dict]:
    """Pinned reviews in pin order, each with its note. Pins whose review left the analysis are skipped."""
    df = load_run_frame(ctx.db, run_id, ctx.frames)
    if df is None:
        raise HTTPException(404, "Analysis not found.")
    with ctx.db.session() as s:
        pins = s.scalars(select(Pin).where(Pin.run_id == run_id).order_by(Pin.created_at, Pin.id)).all()
    rows = {r["review_id"]: r for r in df[df["review_id"].isin([p.review_id for p in pins])].to_dict("records")}
    return [
        {**review_dict(rows[p.review_id]), "note": p.note, "pinned_at": p.created_at.isoformat() + "Z"}
        for p in pins
        if p.review_id in rows
    ]


@router.get("")
def list_pins(run_id: str, ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    return pinned_reviews(ctx, run_id)


@router.put("/{review_id}")
def pin(run_id: str, review_id: str, body: PinIn, ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    df = load_run_frame(ctx.db, run_id, ctx.frames)
    if df is None:
        raise HTTPException(404, "Analysis not found.")
    if not (df["review_id"] == review_id).any():
        raise HTTPException(404, "That review isn't part of this analysis.")
    with ctx.db.session() as s:
        found = s.scalar(select(Pin).where(Pin.run_id == run_id, Pin.review_id == review_id))
        if found is None:
            s.add(Pin(run_id=run_id, review_id=review_id, note=body.note.strip()))
        else:
            found.note = body.note.strip()
    return pinned_reviews(ctx, run_id)


@router.delete("/{review_id}", status_code=204)
def unpin(run_id: str, review_id: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    with ctx.db.session() as s:
        s.execute(delete(Pin).where(Pin.run_id == run_id, Pin.review_id == review_id))
    return Response(status_code=204)
