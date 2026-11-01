"""Side-by-side comparison of several analyses, computed from each run's tags (no AI)."""

from __future__ import annotations

from collections import Counter

import pandas as pd

from ..services.tagging import CATEGORIES, EMOTIONS, JOURNEY_STAGES
from .insights import problem_board


def _shares(series: pd.Series, keys: tuple[str, ...]) -> dict[str, float]:
    counts = series.dropna().value_counts()
    total = int(counts.sum())
    return {k: round(int(counts.get(k, 0)) / total, 4) if total else 0.0 for k in keys}


def run_summary(df: pd.DataFrame) -> dict:
    """Comparable numbers for one analysis."""
    n = len(df)
    tagged = df[df["tagged"]]
    journey = {}
    for stage in JOURNEY_STAGES:
        g = tagged[tagged["journey_stage"] == stage]
        if len(g):
            journey[stage] = {
                "reviews": len(g),
                "share": round(len(g) / max(len(tagged), 1), 4),
                "negative_share": round(float((g["rating"] <= 2).mean()), 4),
            }
    board = problem_board(df, limit=8, quotes=0)
    churn = tagged["churn_risk"].isin(["left", "considering"]) if tagged["churn_risk"].notna().any() else None
    return {
        "reviews": n,
        "avg_rating": round(float(df["rating"].mean()), 2) if n else None,
        "negative_share": round(float((df["rating"] <= 2).mean()), 4) if n else None,
        "positive_share": round(float((df["rating"] >= 4).mean()), 4) if n else None,
        "churn_share": round(float(churn.mean()), 4) if churn is not None and len(tagged) else None,
        "ratings": {str(r): round(float((df["rating"] == r).mean()), 4) if n else 0 for r in range(1, 6)},
        "feedback_types": _shares(tagged["category"], CATEGORIES),
        "emotions": _shares(tagged["emotion"], EMOTIONS),
        "journey": journey,
        "top_problems": [
            {"theme": p["theme"], "reach": p["reach"], "negative_share": p["negative_share"]} for p in board["problems"]
        ],
        "top_strengths": [{"theme": s["theme"], "reach": s["reach"]} for s in board["strengths"][:5]],
    }


def topic_stats(df: pd.DataFrame, member_themes: list[str]) -> dict:
    """How much one shared topic (a set of this app's themes) is mentioned, and how negatively."""
    wanted = set(member_themes)
    hits = df[df["themes"].apply(lambda ts: bool(wanted.intersection(ts)))]
    n = len(df)
    return {
        "mentions": len(hits),
        "share": round(len(hits) / n, 4) if n else 0.0,
        "negative_share": round(float((hits["rating"] <= 2).mean()), 4) if len(hits) else None,
    }


def theme_inventory(df: pd.DataFrame, limit: int = 15) -> list[dict]:
    counts = Counter(t for themes in df["themes"] for t in themes)
    rows = []
    for theme, mentions in counts.most_common(limit):
        g = df[df["themes"].apply(lambda ts, theme=theme: theme in ts)]
        rows.append(
            {"theme": theme, "mentions": mentions, "negative_share": round(float((g["rating"] <= 2).mean()), 4)}
        )
    return rows
