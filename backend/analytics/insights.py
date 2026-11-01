"""Designer/PM views: overview, problem board (themes ranked by impact) and the review explorer."""

from __future__ import annotations

from datetime import date

import pandas as pd

from .metrics import MetricsQuery, apply_filters, run_query

IMPACT_FORMULA = (
    "impact = 100 × reach × negativity × momentum. Reach: share of all reviews mentioning the theme. "
    "Negativity: share of those reviews rated 1-2 stars. Momentum (0.5-2.0): how much the theme's share "
    "grew in the newer half of the period compared with the older half."
)
SORTS = {
    "newest": ("date", False),
    "oldest": ("date", True),
    "rating_asc": ("rating", True),
    "rating_desc": ("rating", False),
    "most_helpful": ("thumbs_up", False),
}


def _iso(value) -> str | None:
    return None if value is None or pd.isna(value) else pd.Timestamp(value).isoformat()


def review_dict(row: dict, max_chars: int | None = None) -> dict:
    content = row["content"] or ""
    return {
        "review_id": row["review_id"],
        "date": _iso(row["date"]),
        "rating": int(row["rating"]),
        "sentiment": row["sentiment"],
        "content": content[:max_chars] + "…" if max_chars and len(content) > max_chars else content,
        "app_version": row["app_version"],
        "thumbs_up": int(row["thumbs_up"]),
        "reply": row["reply"],
        "category": row["category"],
        "themes": list(row["themes"]),
        "journey_stage": row["journey_stage"],
        "emotion": row["emotion"],
    }


def _distribution(df: pd.DataFrame, dimension: str) -> list[dict]:
    return run_query(df, MetricsQuery(measures=["review_count"], dimensions=[dimension]))


def overview(df: pd.DataFrame) -> dict:
    n = len(df)
    dated = df["date"].dropna()
    ratings = {r["rating"]: r["review_count"] for r in _distribution(df, "rating")}
    tagged = df[df["tagged"]]
    return {
        "kpis": {
            "review_count": n,
            "avg_rating": round(float(df["rating"].mean()), 3) if n else None,
            "negative_share": round(float((df["rating"] <= 2).mean()), 4) if n else None,
            "positive_share": round(float((df["rating"] >= 4).mean()), 4) if n else None,
            "analyzed_share": round(len(tagged) / n, 4) if n else None,
            "date_from": _iso(dated.min()) if len(dated) else None,
            "date_to": _iso(dated.max()) if len(dated) else None,
        },
        "rating_distribution": [{"rating": r, "review_count": int(ratings.get(r, 0))} for r in range(1, 6)],
        "sentiment_distribution": _distribution(df, "sentiment"),
        "category_distribution": _distribution(tagged, "category") if len(tagged) else [],
        "journey_distribution": _distribution(tagged, "journey_stage") if len(tagged) else [],
        "emotion_distribution": _distribution(tagged, "emotion") if len(tagged) else [],
    }


def _momentum(recent: int, recent_total: int, prior: int, prior_total: int) -> tuple[float, float, str]:
    if not recent_total or not prior_total:
        return 1.0, 0.0, "steady"
    recent_rate, prior_rate = recent / recent_total, prior / prior_total
    growth = (recent_rate - prior_rate) / prior_rate if prior_rate else (1.0 if recent_rate else 0.0)
    trend = "rising" if growth > 0.25 else "falling" if growth < -0.25 else "steady"
    return 1.0 + min(max(growth, -0.5), 1.0), round(growth, 4), trend


def _quotes(g: pd.DataFrame, worst_first: bool, n: int) -> list[dict]:
    pool = g[g["content"].str.len() >= 20]
    if pool.empty:
        pool = g
    ranked = pool.sort_values(["rating", "thumbs_up"], ascending=[worst_first, False])
    return [review_dict(r, max_chars=500) for r in ranked.head(n).to_dict(orient="records")]


def _top(series: pd.Series, n: int = 3) -> list[dict]:
    counts = series.dropna().value_counts()
    total = int(counts.sum())
    return [{"value": str(k), "share": round(int(v) / total, 4)} for k, v in counts.head(n).items()] if total else []


def problem_board(df: pd.DataFrame, limit: int = 20, quotes: int = 3) -> dict:
    total = len(df)
    empty = {"total_reviews": total, "problems": [], "strengths": [], "formula": IMPACT_FORMULA}
    if not total:
        return empty
    exploded = df.assign(theme=df["themes"]).explode("theme")
    exploded = exploded[exploded["theme"].notna()]
    if exploded.empty:
        return empty

    dated = df["date"].dropna()
    midpoint = dated.min() + (dated.max() - dated.min()) / 2 if len(dated) else None
    recent_total = int((df["date"] >= midpoint).sum()) if midpoint is not None else 0
    prior_total = int((df["date"] < midpoint).sum()) if midpoint is not None else 0

    items = []
    for theme, g in exploded.groupby("theme"):
        mentions = len(g)
        reach = mentions / total
        negativity = float((g["rating"] <= 2).mean())
        positivity = float((g["rating"] >= 4).mean())
        recent = int((g["date"] >= midpoint).sum()) if midpoint is not None else 0
        prior = int((g["date"] < midpoint).sum()) if midpoint is not None else 0
        momentum, growth, trend = _momentum(recent, recent_total, prior, prior_total)
        items.append({
            "theme": theme,
            "mentions": mentions,
            "reach": round(reach, 4),
            "avg_rating": round(float(g["rating"].mean()), 3),
            "negative_share": round(negativity, 4),
            "positive_share": round(positivity, 4),
            "trend": trend,
            "growth": growth,
            "impact": round(100 * reach * negativity * momentum, 2),
            "categories": _top(g["category"]),
            "journey_stages": _top(g["journey_stage"]),
            "emotions": _top(g["emotion"]),
            "versions": _top(g["app_version"]),
            "first_seen": _iso(g["date"].min()),
            "last_seen": _iso(g["date"].max()),
            "_group": g,
        })

    problems = sorted((i for i in items if i["negative_share"] >= 0.4), key=lambda i: i["impact"], reverse=True)
    strengths = sorted(
        (i for i in items if i["positive_share"] >= 0.6), key=lambda i: i["reach"] * i["positive_share"], reverse=True
    )

    def finish(item: dict, worst_first: bool) -> dict:
        g = item.pop("_group")
        return {**item, "quotes": _quotes(g, worst_first, quotes)}

    return {
        "total_reviews": total,
        "problems": [finish(dict(i), True) for i in problems[:limit]],
        "strengths": [finish(dict(i), False) for i in strengths[:limit]],
        "formula": IMPACT_FORMULA,
    }


def list_reviews(
    df: pd.DataFrame,
    *,
    filters: dict[str, list] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    query: str | None = None,
    sort: str = "newest",
    page: int = 1,
    page_size: int = 25,
) -> dict:
    if sort not in SORTS:
        raise ValueError(f"sort must be one of {list(SORTS)}.")
    data = apply_filters(df, filters, date_from, date_to)
    if query:
        data = data[data["content"].str.contains(query, case=False, regex=False, na=False)]
    column, ascending = SORTS[sort]
    data = data.sort_values(column, ascending=ascending, kind="stable", na_position="last")
    page, page_size = max(page, 1), min(max(page_size, 1), 100)
    start = (page - 1) * page_size
    return {
        "total": len(data),
        "page": page,
        "page_size": page_size,
        "items": [review_dict(r) for r in data.iloc[start : start + page_size].to_dict(orient="records")],
    }
