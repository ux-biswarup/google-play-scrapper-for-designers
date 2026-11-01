"""Decision views for one analysis: feedback boards, journey map, emotions, segments and risks."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..analytics import views
from ..analytics.frame import load_run_frame
from ..context import AppContext, get_ctx

router = APIRouter(prefix="/runs/{run_id}/views", tags=["views"])


def _frame(ctx: AppContext, run_id: str):
    df = load_run_frame(ctx.db, run_id, ctx.frames)
    if df is None:
        raise HTTPException(404, "Analysis not found.")
    return df


@router.get("/feedback")
def feedback(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    return views.feedback_boards(_frame(ctx, run_id))


@router.get("/journey")
def journey(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    return views.journey_map(_frame(ctx, run_id))


@router.get("/emotions")
def emotions(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    return views.emotions_view(_frame(ctx, run_id))


@router.get("/segments")
def segments(run_id: str, by: str = "sentiment", ctx: AppContext = Depends(get_ctx)) -> dict:
    return views.segments_view(_frame(ctx, run_id), by)


@router.get("/risks")
def risks(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    return views.risks_view(_frame(ctx, run_id))
