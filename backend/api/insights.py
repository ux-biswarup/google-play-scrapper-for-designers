from __future__ import annotations

import re
from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ..analytics import charts, insights, trends
from ..analytics.frame import load_run_frame
from ..analytics.metrics import MetricsQuery, catalog, run_query
from ..context import AppContext, get_ctx
from ..models import Run
from ..schemas import AppOut, MetricsQueryIn, RunOut

router = APIRouter(tags=["insights"])


def _frame(ctx: AppContext, run_id: str) -> pd.DataFrame:
    df = load_run_frame(ctx.db, run_id, ctx.frames)
    if df is None:
        raise HTTPException(404, "Analysis not found.")
    return df


def _filters(
    rating: list[int] | None = Query(None),
    sentiment: list[str] | None = Query(None),
    category: list[str] | None = Query(None),
    theme: list[str] | None = Query(None),
    journey_stage: list[str] | None = Query(None),
    emotion: list[str] | None = Query(None),
    app_version: list[str] | None = Query(None),
) -> dict[str, list]:
    values = {
        "rating": rating, "sentiment": sentiment, "category": category, "theme": theme,
        "journey_stage": journey_stage, "emotion": emotion, "app_version": app_version,
    }
    return {k: v for k, v in values.items() if v}


@router.get("/metrics/catalog")
def metrics_catalog() -> dict:
    return catalog()


@router.post("/runs/{run_id}/metrics")
def query_metrics(run_id: str, body: MetricsQueryIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    rows = run_query(_frame(ctx, run_id), MetricsQuery(**body.model_dump()))
    return {"rows": rows}


@router.get("/runs/{run_id}/overview")
def overview(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    df = _frame(ctx, run_id)
    with ctx.db.session() as s:
        run = s.get(Run, run_id)
        meta = {"run": RunOut.model_validate(run).model_dump(mode="json"),
                "app": AppOut.model_validate(run.app).model_dump()}
    return meta | insights.overview(df)


@router.get("/runs/{run_id}/themes")
def themes(
    run_id: str, limit: int = Query(20, ge=1, le=100), quotes: int = Query(3, ge=0, le=10),
    ctx: AppContext = Depends(get_ctx),
) -> dict:
    return insights.problem_board(_frame(ctx, run_id), limit=limit, quotes=quotes)


@router.get("/runs/{run_id}/trends")
def run_trends(
    run_id: str,
    grain: str = "day",
    date_from: date | None = None,
    date_to: date | None = None,
    spike_threshold: float = Query(2.0, ge=0.5, le=5.0),
    ctx: AppContext = Depends(get_ctx),
) -> dict:
    df = _frame(ctx, run_id)
    series = run_query(df, MetricsQuery(
        measures=["review_count", "avg_rating", "negative_share", "neutral_share", "positive_share"],
        dimensions=["date"], time_grain=grain, date_from=date_from, date_to=date_to,
    ))
    return {
        "grain": grain,
        "series": series,
        "spikes": trends.spikes(df, grain, spike_threshold, date_from=date_from, date_to=date_to),
        "trending_themes": trends.trending_themes(df, date_to=date_to),
        "versions": trends.versions(df),
    }


@router.get("/runs/{run_id}/compare")
def compare(run_id: str, mode: str = "version", pivot: str = Query(min_length=1), ctx: AppContext = Depends(get_ctx)) -> dict:
    return trends.compare(_frame(ctx, run_id), mode, pivot)


@router.get("/runs/{run_id}/reviews")
def reviews(
    run_id: str,
    filters: dict = Depends(_filters),
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: str = "newest",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    ctx: AppContext = Depends(get_ctx),
) -> dict:
    return insights.list_reviews(
        _frame(ctx, run_id), filters=filters, date_from=date_from, date_to=date_to,
        query=q, sort=sort, page=page, page_size=page_size,
    )


@router.get("/runs/{run_id}/charts/{chart}.{fmt}")
def chart_image(run_id: str, chart: str, fmt: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    df = _frame(ctx, run_id)
    with ctx.db.session() as s:
        app = s.get(Run, run_id).app
        title = app.title or app.store_id
    image = charts.render(chart, df, title, fmt)
    filename = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{app.store_id}-{chart}.{fmt}")
    return Response(image, media_type=charts.FORMATS[fmt],
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})
