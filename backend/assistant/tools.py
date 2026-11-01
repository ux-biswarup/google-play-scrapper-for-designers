"""Read-only tools over analysis results, shared by the in-app assistant and the MCP server.

Every tool answers from the metrics layer and stored reviews, so the assistant cites real numbers
and real quotes instead of guessing. Outputs are trimmed to keep model context small.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import Field, create_model
from sqlalchemy import or_, select

from ..analytics import insights, trends, views
from ..analytics.frame import FrameCache, load_run_frame
from ..analytics.metrics import MetricsQuery, auto_grain, catalog, run_query
from ..db import Database
from ..models import App, Run, RunStatus

QUOTE_CHARS = 300
REVIEW_CHARS = 500


@dataclass
class ToolContext:
    db: Database
    frames: FrameCache


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    fn: Callable[..., Any]
    parameters: dict  # JSON Schema of the arguments (without the context)

    def run(self, ctx: ToolContext, args: dict) -> Any:
        return self.fn(ctx, **args)


TOOLS: dict[str, Tool] = {}


def tool(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Register a tool. Its JSON Schema comes from the type hints; the first line of the docstring is the summary."""
    params = list(inspect.signature(fn).parameters.values())[1:]  # skip ctx
    hints = inspect.get_annotations(fn, eval_str=True)
    fields = {
        p.name: (hints[p.name], Field(... if p.default is inspect.Parameter.empty else p.default)) for p in params
    }
    schema = create_model(f"{fn.__name__}_args", **fields).model_json_schema()
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    TOOLS[fn.__name__] = Tool(fn.__name__, inspect.cleandoc(fn.__doc__ or ""), fn, schema)
    return fn


def _frame(ctx: ToolContext, run_id: str):
    df = load_run_frame(ctx.db, run_id, ctx.frames)
    if df is None:
        raise ValueError(f"No analysis with id '{run_id}'. Call list_analyses to see the available ones.")
    return df


def _trim(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _review(r: dict, limit: int = REVIEW_CHARS) -> dict:
    return {
        "review_id": r["review_id"],
        "rating": r["rating"],
        "date": (r["date"] or "")[:10],
        "app_version": r["app_version"],
        "helpful_votes": r["thumbs_up"],
        "text": _trim(r["content"], limit),
        "type": r["category"],
        "themes": r["themes"],
        "journey_stage": r["journey_stage"],
        "emotion": r["emotion"],
    }


# ---- tools ----------------------------------------------------------------------------------


@tool
def list_analyses(ctx: ToolContext, app: str | None = None, limit: int = 20) -> dict:
    """List finished review analyses (newest first), optionally filtered by app name or package ID.

    Use the returned run_id with the other tools."""
    with ctx.db.session() as s:
        query = select(Run).join(App).where(Run.status == RunStatus.COMPLETED).order_by(Run.created_at.desc())
        if app:
            like = f"%{app}%"
            query = query.where(or_(App.title.ilike(like), App.store_id.ilike(like)))
        runs = s.scalars(query.limit(min(max(limit, 1), 50))).all()
        return {
            "analyses": [
                {
                    "run_id": r.id,
                    "app": r.app.title or r.app.store_id,
                    "package": r.app.store_id,
                    "country": r.country,
                    "reviews": r.review_count,
                    "star_filter": r.ratings or "all",
                    "model": r.model,
                    "analyzed_at": r.created_at.strftime("%Y-%m-%d"),
                }
                for r in runs
            ]
        }


@tool
def get_overview(ctx: ToolContext, run_id: str) -> dict:
    """Headline numbers for one analysis: review count, average rating, negative/positive share,
    date range, and how reviews split by rating, feedback type, journey stage and emotion."""
    df = _frame(ctx, run_id)
    data = insights.overview(df)
    with ctx.db.session() as s:
        run = s.get(Run, run_id)
        app = {
            "name": run.app.title,
            "package": run.app.store_id,
            "store_rating": run.app.score,
            "genre": run.app.genre,
        }
    return {"app": app, "country": run.country, **data}


@tool
def get_problems(ctx: ToolContext, run_id: str, limit: int = 8, quotes_per_theme: int = 2) -> dict:
    """Problem themes ranked by impact (reach × negativity × momentum) and themes users love,
    each with mention counts, trend, typical feedback type, journey stage, emotion and example quotes."""
    board = insights.problem_board(_frame(ctx, run_id), limit=min(limit, 20), quotes=min(quotes_per_theme, 5))

    def compact(item: dict) -> dict:
        return {
            "theme": item["theme"],
            "mentions": item["mentions"],
            "share_of_reviews": item["reach"],
            "negative_share": item["negative_share"],
            "positive_share": item["positive_share"],
            "avg_rating": item["avg_rating"],
            "trend": item["trend"],
            "impact": item["impact"],
            "top_type": item["categories"][0]["value"] if item["categories"] else None,
            "top_journey_stage": item["journey_stages"][0]["value"] if item["journey_stages"] else None,
            "top_emotion": item["emotions"][0]["value"] if item["emotions"] else None,
            "quotes": [_review(q, QUOTE_CHARS) for q in item["quotes"]],
        }

    return {
        "total_reviews": board["total_reviews"],
        "impact_formula": board["formula"],
        "problems": [compact(p) for p in board["problems"]],
        "strengths": [compact(p) for p in board["strengths"][:limit]],
    }


@tool
def search_reviews(
    ctx: ToolContext,
    run_id: str,
    text: str | None = None,
    ratings: list[int] | None = None,
    theme: str | None = None,
    feedback_type: str | None = None,
    journey_stage: str | None = None,
    emotion: str | None = None,
    app_version: str | None = None,
    sort: str = "most_helpful",
    limit: int = 8,
) -> dict:
    """Find individual reviews to quote as evidence. Filter by words in the text, star ratings,
    theme, feedback type, journey stage, emotion or app version.
    sort: most_helpful, newest, oldest, rating_asc or rating_desc."""
    filters = {
        "rating": ratings,
        "theme": [theme] if theme else None,
        "category": [feedback_type] if feedback_type else None,
        "journey_stage": [journey_stage] if journey_stage else None,
        "emotion": [emotion] if emotion else None,
        "app_version": [app_version] if app_version else None,
    }
    page = insights.list_reviews(
        _frame(ctx, run_id),
        filters={k: v for k, v in filters.items() if v},
        query=text,
        sort=sort,
        page_size=min(max(limit, 1), 25),
    )
    return {"matching_reviews": page["total"], "reviews": [_review(r) for r in page["items"]]}


@tool
def query_metrics(
    ctx: ToolContext,
    run_id: str,
    measures: list[str],
    dimensions: list[str] | None = None,
    filters: dict[str, list[str]] | None = None,
    time_grain: str = "day",
    date_from: date | None = None,
    date_to: date | None = None,
    order_by: str | None = None,
    limit: int = 30,
) -> dict:
    """Compute numbers with the shared metric definitions (call describe_metrics for the list).
    Example: measures=["review_count","negative_share"], dimensions=["theme"], filters={"rating":["1","2"]}."""
    rows = run_query(
        _frame(ctx, run_id),
        MetricsQuery(
            measures=measures,
            dimensions=dimensions or [],
            filters=filters or {},
            time_grain=time_grain,
            date_from=date_from,
            date_to=date_to,
            order_by=order_by,
            limit=min(max(limit, 1), 200),
        ),
    )
    return {"rows": rows}


@tool
def describe_metrics(ctx: ToolContext) -> dict:
    """List the measures, dimensions and time grains query_metrics accepts, with their definitions."""
    return catalog()


@tool
def get_trends(ctx: ToolContext, run_id: str) -> dict:
    """How sentiment changed over time, unusual spikes in one-star reviews (with their themes),
    themes trending this week, and reviews per app version."""
    df = _frame(ctx, run_id)
    grain = auto_grain(df["date"])
    series = run_query(
        df,
        MetricsQuery(measures=["review_count", "avg_rating", "negative_share"], dimensions=["date"], time_grain=grain),
    )
    return {
        "time_grain": grain,
        "series": series[-60:],
        "one_star_spikes": trends.spikes(df, grain)["spikes"],
        "trending_themes": trends.trending_themes(df, limit=10),
        "versions": trends.versions(df)[-15:],
    }


@tool
def compare_periods(ctx: ToolContext, run_id: str, pivot: str, mode: str = "version") -> dict:
    """Compare reviews before and after a release (mode="version", pivot="2.3.0") or a date
    (mode="date", pivot="2026-03-01"): rating, negative share, new and rising themes."""
    return trends.compare(_frame(ctx, run_id), mode, pivot)


@tool
def get_feedback_types(ctx: ToolContext, run_id: str, limit: int = 6) -> dict:
    """Boards of bugs (what to fix), feature requests (what to build), UX friction (what to redesign) and
    complaints (what to reconsider), each ranked with mentions, severity, affected versions and quotes."""
    data = views.feedback_boards(_frame(ctx, run_id), limit=min(limit, 12))
    for board in data["boards"].values():
        for item in board["items"]:
            item["quotes"] = [_review(q, QUOTE_CHARS) for q in item["quotes"][:1]]
    return data


@tool
def get_journey_map(ctx: ToolContext, run_id: str) -> dict:
    """The user journey stage by stage (onboarding, login, core use, payments, support...): volume, rating,
    negative share, main emotions, top problems and a quote, plus the most painful stage."""
    data = views.journey_map(_frame(ctx, run_id))
    for stage in data["stages"]:
        stage["quote"] = _review(stage["quote"], QUOTE_CHARS) if stage["quote"] else None
        stage["emotions"] = stage["emotions"][:3]
    return data


@tool
def get_segments(ctx: ToolContext, run_id: str, by: str = "user_type") -> dict:
    """Compare reviewer groups. by: sentiment, user_type (new, long-time, paying), app_version, detail
    (short vs detailed reviews), upvotes (how many others agreed) or replied (developer replied or not)."""
    data = views.segments_view(_frame(ctx, run_id), by)
    for segment in data["segments"]:
        segment["quote"] = _review(segment["quote"], QUOTE_CHARS) if segment["quote"] else None
    return data


@tool
def get_risks(ctx: ToolContext, run_id: str) -> dict:
    """Early warnings: reviewers who left or may leave (with why), competitors they name, and payment problems."""
    data = views.risks_view(_frame(ctx, run_id))
    data["churn"]["quotes"] = [_review(q, QUOTE_CHARS) for q in data["churn"]["quotes"]]
    data["payments"]["quotes"] = [_review(q, QUOTE_CHARS) for q in data["payments"]["quotes"]]
    for c in data["competitors"]:
        c["quote"] = _review(c["quote"], QUOTE_CHARS) if c["quote"] else None
    return data


@tool
def compare_analyses(ctx: ToolContext, run_ids: list[str]) -> dict:
    """Compare 2-4 analyses side by side (your app vs competitors, markets or periods): rating, negative share,
    churn, feedback types, emotions, journey-stage negativity and top problems. Get run_ids from list_analyses."""
    from ..analytics.benchmark import run_summary

    if not 2 <= len(run_ids) <= 4:
        raise ValueError("Compare between 2 and 4 analyses.")
    out = []
    for run_id in run_ids:
        df = _frame(ctx, run_id)
        with ctx.db.session() as s:
            run = s.get(Run, run_id)
            name = run.app.title or run.app.store_id
        out.append({"run_id": run_id, "app": name, "country": run.country, **run_summary(df)})
    return {"analyses": out}


def run_tool(ctx: ToolContext, name: str, args: dict) -> Any:
    if name not in TOOLS:
        raise ValueError(f"Unknown tool '{name}'.")
    return TOOLS[name].run(ctx, args)
