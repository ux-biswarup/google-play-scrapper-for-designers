"""Static chart images (PNG/SVG) rendered with matplotlib, for report exports and sharing.

Uses the object-oriented Figure API rather than pyplot: no global state, safe across server threads.
Interactive charts are drawn in the frontend with Plotly from the same JSON data.
"""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO

import matplotlib.dates as mdates
import pandas as pd
from matplotlib.figure import Figure

from .insights import problem_board
from .metrics import MetricsQuery, auto_grain, run_query

INK = "#1f2430"
MUTED = "#6b7280"
GRID = "#e5e7eb"
NEGATIVE = "#d64545"
NEUTRAL = "#9aa0a6"
POSITIVE = "#2f9e66"
ACCENT = "#4f46e5"
RATING_COLORS = [NEGATIVE, "#e8833a", NEUTRAL, "#7cb87f", POSITIVE]
FORMATS = {"png": "image/png", "svg": "image/svg+xml"}


def _figure(width: float = 8, height: float = 4.5) -> tuple[Figure, object]:
    fig = Figure(figsize=(width, height), dpi=144, layout="constrained")
    ax = fig.add_subplot()
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    return fig, ax


def _title(ax, title: str, subtitle: str | None = None) -> None:
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", color=INK, pad=18 if subtitle else 10)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=MUTED)


def _empty(ax, message: str = "No data for this chart yet") -> None:
    ax.set_axis_off()
    ax.text(0.5, 0.5, message, ha="center", va="center", color=MUTED, fontsize=11, transform=ax.transAxes)


def rating_distribution(df: pd.DataFrame, title: str) -> Figure:
    fig, ax = _figure()
    counts = df["rating"].value_counts().reindex(range(1, 6), fill_value=0)
    if not counts.sum():
        _empty(ax)
        return fig
    bars = ax.bar([f"{r}★" for r in counts.index], counts.values, color=RATING_COLORS, width=0.65)
    ax.bar_label(bars, labels=[f"{v:,}" for v in counts.values], padding=3, color=INK, fontsize=9)
    _title(ax, "Rating distribution", f"{title} · {int(counts.sum()):,} reviews")
    ax.set_ylabel("Reviews", color=MUTED)
    return fig


def sentiment_trend(df: pd.DataFrame, title: str, grain: str | None = None) -> Figure:
    fig, ax = _figure()
    grain = grain or auto_grain(df["date"])
    rows = run_query(df, MetricsQuery(measures=["negative_share", "positive_share"], dimensions=["date"], time_grain=grain))
    if len(rows) < 2:
        _empty(ax, "Not enough dated reviews for a trend")
        return fig
    dates = pd.to_datetime([r["date"] for r in rows])
    style = {"linewidth": 2, "marker": "o", "markersize": 4}
    ax.plot(dates, [100 * r["positive_share"] for r in rows], color=POSITIVE, label="Positive (4-5★)", **style)
    ax.plot(dates, [100 * r["negative_share"] for r in rows], color=NEGATIVE, label="Negative (1-2★)", **style)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% of reviews", color=MUTED)
    ax.legend(frameon=False, fontsize=9, loc="upper left", bbox_to_anchor=(0, 1.0), ncols=2)
    if len(dates) <= 31:
        ax.set_xticks(dates)  # one tick per bucket, never intra-day ticks
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(mdates.AutoDateLocator()))
    _title(ax, "Sentiment over time", f"{title} · per {grain}")
    return fig


def top_problems(df: pd.DataFrame, title: str, limit: int = 8) -> Figure:
    problems = problem_board(df, limit=limit, quotes=0)["problems"]
    fig, ax = _figure(height=max(3.0, 0.5 * len(problems) + 1.5))
    if not problems:
        _empty(ax, "No problem themes found")
        return fig
    problems = list(reversed(problems))
    bars = ax.barh([p["theme"] for p in problems], [p["impact"] for p in problems], color=NEGATIVE, height=0.6)
    ax.bar_label(bars, labels=[f"{p['mentions']} review{'s' if p['mentions'] != 1 else ''}" for p in problems], padding=4, color=MUTED, fontsize=8)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_xlabel("Impact score", color=MUTED)
    _title(ax, "Top problems by impact", title)
    return fig


def feedback_mix(df: pd.DataFrame, title: str) -> Figure:
    fig, ax = _figure()
    tagged = df[df["category"].notna()]
    if tagged.empty:
        _empty(ax, "Reviews have not been analyzed yet")
        return fig
    counts = tagged["category"].value_counts().sort_values()
    labels = [c.replace("_", " ") for c in counts.index]
    ax.barh(labels, counts.values, color=ACCENT, height=0.6)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_xlabel("Reviews", color=MUTED)
    _title(ax, "Type of feedback", title)
    return fig


CHARTS: dict[str, Callable[..., Figure]] = {
    "rating-distribution": rating_distribution,
    "sentiment-trend": sentiment_trend,
    "top-problems": top_problems,
    "feedback-mix": feedback_mix,
}


def render(name: str, df: pd.DataFrame, title: str, fmt: str = "png") -> bytes:
    if name not in CHARTS:
        raise ValueError(f"Unknown chart '{name}'. Available: {', '.join(CHARTS)}.")
    if fmt not in FORMATS:
        raise ValueError(f"Format must be one of {list(FORMATS)}.")
    fig = CHARTS[name](df, title)
    buffer = BytesIO()
    fig.savefig(buffer, format=fmt, facecolor="white")
    return buffer.getvalue()
