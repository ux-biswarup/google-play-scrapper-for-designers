"""Decision-oriented views over one analysis: feedback boards, journey map, emotions, segments and risks."""

from __future__ import annotations

from collections import Counter

import pandas as pd

from ..services.tagging import EMOTIONS, JOURNEY_STAGES
from .insights import _momentum, review_dict
from .metrics import auto_grain, bucket_dates

BOARD_TYPES = ("bug", "feature_request", "ux_friction", "complaint")
SEVERITY_WEIGHT = {"high": 1.0, "medium": 0.5, "low": 0.2, "none": 0.0}
EMOTION_MEANING = {
    "confusion": "Clarity problem: unclear screens, wording or flows. Usually fixed by design.",
    "frustration": "Friction or bugs that stop people finishing what they came to do.",
    "anger": "Broken trust: money, bans, data loss or policy. Needs product or policy decisions.",
    "disappointment": "Unmet expectations: a change people dislike or something missing.",
    "neutral": "Factual feedback without strong feeling.",
    "satisfaction": "Things working as expected.",
    "delight": "What people love. Protect it when changing the product.",
}
SEGMENT_DIMENSIONS = {
    "sentiment": ("Sentiment", ["negative", "neutral", "positive"], False),
    "user_type": ("User type", ["new_user", "long_time_user", "paying_user", "unknown"], True),
    "app_version": ("App version", None, False),
    "detail": ("Review detail", ["short", "medium", "detailed"], False),
    "upvotes": ("Helpful votes", ["none", "some", "many"], False),
    "replied": ("Developer reply", ["replied", "not_replied"], False),
}


def _quotes(
    g: pd.DataFrame, n: int = 2, worst_first: bool = True, chars: int = 300, used: set[str] | None = None
) -> list[dict]:
    """Representative quotes; skips reviews already quoted elsewhere in the same view when `used` is given."""
    pool = g[g["content"].str.len() >= 20]
    if pool.empty:
        pool = g
    if used is not None:
        # Never repeat a quote within a view; a theme whose reviews were all quoted above shows none.
        pool = pool[~pool["review_id"].isin(used)]
    ranked = pool.sort_values(["thumbs_up", "rating"], ascending=[False, worst_first])
    quotes = [review_dict(r, max_chars=chars) for r in ranked.head(n).to_dict(orient="records")]
    if used is not None:
        used.update(q["review_id"] for q in quotes)
    return quotes


def _midpoint(df: pd.DataFrame):
    dated = df["date"].dropna()
    return dated.min() + (dated.max() - dated.min()) / 2 if len(dated) else None


def _trend(g: pd.DataFrame, df: pd.DataFrame, mid) -> str:
    if mid is None:
        return "steady"
    recent_total, prior_total = int((df["date"] >= mid).sum()), int((df["date"] < mid).sum())
    _, _, trend = _momentum(int((g["date"] >= mid).sum()), recent_total, int((g["date"] < mid).sum()), prior_total)
    return trend


def _shares(series: pd.Series, order: list[str] | None = None, top: int | None = None) -> list[dict]:
    counts = series.dropna().value_counts()
    total = int(counts.sum())
    if not total:
        return []
    keys = [k for k in order if k in counts] if order else list(counts.index)
    rows = [{"value": str(k), "count": int(counts[k]), "share": round(int(counts[k]) / total, 4)} for k in keys]
    return rows[:top] if top else rows


def _theme_rows(g: pd.DataFrame) -> pd.DataFrame:
    exploded = g.assign(theme=g["themes"]).explode("theme")
    return exploded[exploded["theme"].notna()]


def _has_v2(df: pd.DataFrame) -> bool:
    return bool(df["severity"].notna().any())


# ---- Bugs, feature requests, UX friction, complaints ----------------------------------------


def feedback_boards(df: pd.DataFrame, limit: int = 12) -> dict:
    """What to fix (bugs), what to build (requests), what to redesign (friction), what to reconsider (complaints)."""
    tagged = df[df["category"].notna()]
    total = len(tagged)
    mid = _midpoint(df)
    boards = {}
    for category in BOARD_TYPES:
        g = tagged[tagged["category"] == category]
        items = []
        used: set[str] = set()
        for theme, t in _theme_rows(g).groupby("theme"):
            mentions = len(t)
            high = float((t["severity"] == "high").mean()) if t["severity"].notna().any() else None
            votes = int(t["thumbs_up"].sum())
            if category == "bug":
                score = mentions * (1 + (high or 0))
            elif category == "feature_request":
                score = mentions + votes / 10
            else:
                score = mentions * (1 + float((t["rating"] <= 2).mean()))
            items.append(
                {
                    "theme": theme,
                    "mentions": mentions,
                    "helpful_votes": votes,
                    "avg_rating": round(float(t["rating"].mean()), 2),
                    "high_severity_share": None if high is None else round(high, 4),
                    "trend": _trend(t, df, mid),
                    "versions": _shares(t["app_version"][t["app_version"] != "unknown"], top=3),
                    "first_seen": None if t["date"].isna().all() else t["date"].min().isoformat(),
                    "_rows": t,
                    "_score": score,
                }
            )
        items.sort(key=lambda i: i["_score"], reverse=True)
        items = items[:limit]
        for item in items:  # pick quotes in rank order so higher-ranked themes get first choice
            item.pop("_score")
            item["quotes"] = _quotes(item.pop("_rows"), 2, worst_first=category != "feature_request", used=used)
        boards[category] = {
            "count": len(g),
            "share": round(len(g) / total, 4) if total else 0,
            "trend": _trend(g, df, mid),
            "severity": _shares(g["severity"], ["high", "medium", "low", "none"]),
            "items": items,
        }
    return {"total_tagged": total, "has_severity": _has_v2(df), "boards": boards}


# ---- Journey map -----------------------------------------------------------------------------


def journey_map(df: pd.DataFrame) -> dict:
    """Each step of the user journey with volume, sentiment, emotions, top problems and a quote."""
    tagged = df[df["journey_stage"].notna()]
    total = len(tagged)
    stages = []
    for stage in JOURNEY_STAGES:
        g = tagged[tagged["journey_stage"] == stage]
        if g.empty:
            continue
        themes = _theme_rows(g)
        problems, praise = [], []
        for theme, t in themes.groupby("theme"):
            neg, pos = float((t["rating"] <= 2).mean()), float((t["rating"] >= 4).mean())
            row = {"theme": theme, "mentions": len(t), "negative_share": round(neg, 4)}
            if neg >= 0.4:
                problems.append(row)
            elif pos >= 0.6:
                praise.append(row)
        negative = g[g["rating"] <= 2]
        negative_share = len(negative) / len(g)
        stages.append(
            {
                "stage": stage,
                "reviews": len(g),
                "share": round(len(g) / total, 4),
                "avg_rating": round(float(g["rating"].mean()), 2),
                "negative_share": round(negative_share, 4),
                "pain": round(100 * (len(g) / total) * negative_share, 2),
                "emotions": _shares(g["emotion"], list(EMOTIONS)),
                "problems": sorted(problems, key=lambda r: r["mentions"], reverse=True)[:3],
                "praise": sorted(praise, key=lambda r: r["mentions"], reverse=True)[:2],
                "quote": (_quotes(negative if len(negative) else g, 1) or [None])[0],
            }
        )
    worst = max(stages, key=lambda s: s["pain"])["stage"] if stages else None
    return {"total_tagged": total, "worst_stage": worst, "stages": stages}


# ---- Emotions --------------------------------------------------------------------------------


def emotions_view(df: pd.DataFrame, top_themes: int = 12) -> dict:
    """Which feelings dominate, which themes trigger them, and how that changed over time."""
    tagged = df[df["emotion"].notna()]
    themes = _theme_rows(tagged)
    top = themes["theme"].value_counts().head(top_themes).index.tolist()
    matrix = [
        {
            "theme": theme,
            "counts": {e: int(((themes["theme"] == theme) & (themes["emotion"] == e)).sum()) for e in EMOTIONS},
        }
        for theme in top
    ]
    dated = tagged[tagged["date"].notna()]
    grain = auto_grain(dated["date"]) if len(dated) else "day"
    series = []
    if len(dated):
        buckets = bucket_dates(dated["date"], grain)
        for bucket, g in dated.groupby(buckets):
            counts = g["emotion"].value_counts()
            series.append(
                {
                    "date": bucket.strftime("%Y-%m-%d"),
                    "total": len(g),
                    **{e: round(int(counts.get(e, 0)) / len(g), 4) for e in EMOTIONS},
                }
            )
    return {
        "distribution": _shares(tagged["emotion"], list(EMOTIONS)),
        "matrix": matrix,
        "grain": grain,
        "series": series,
        "meaning": EMOTION_MEANING,
        "quotes": {e: _quotes(tagged[tagged["emotion"] == e], 2) for e in EMOTIONS if (tagged["emotion"] == e).any()},
    }


# ---- Segments --------------------------------------------------------------------------------


def segments_view(df: pd.DataFrame, by: str = "sentiment") -> dict:
    """Compare groups of reviewers: what each group talks about, and what's distinctive for it."""
    if by not in SEGMENT_DIMENSIONS:
        raise ValueError(f"Segment by one of: {', '.join(SEGMENT_DIMENSIONS)}.")
    label, order, needs_v2 = SEGMENT_DIMENSIONS[by]
    available = [
        {"id": k, "label": v[0], "needs_reanalysis": v[2] and not _has_v2(df)} for k, v in SEGMENT_DIMENSIONS.items()
    ]
    data = df[df[by].notna()].copy()
    if by == "app_version":
        top = data[data["app_version"] != "unknown"]["app_version"].value_counts().head(6).index.tolist()
        data["app_version"] = data["app_version"].where(data["app_version"].isin(top), "other")
        order = top + ["other"]
    total = len(data)
    overall = Counter(t for themes in data["themes"] for t in themes)
    segments = []
    for value in order or sorted(data[by].unique()):
        g = data[data[by] == value]
        if g.empty:
            continue
        counts = Counter(t for themes in g["themes"] for t in themes)
        distinctive = []
        for theme, n in counts.items():
            if n < 2 or not overall[theme]:
                continue
            lift = (n / len(g)) / (overall[theme] / total)
            if lift >= 1.3:
                distinctive.append({"theme": theme, "mentions": n, "lift": round(lift, 2)})
        segments.append(
            {
                "value": value,
                "reviews": len(g),
                "share": round(len(g) / total, 4) if total else 0,
                "avg_rating": round(float(g["rating"].mean()), 2),
                "negative_share": round(float((g["rating"] <= 2).mean()), 4),
                "feedback_types": _shares(g["category"], top=4),
                "top_themes": [
                    {"theme": t, "mentions": n, "share": round(n / len(g), 4)} for t, n in counts.most_common(5)
                ],
                "distinctive_themes": sorted(distinctive, key=lambda d: d["lift"], reverse=True)[:3],
                "quote": (_quotes(g, 1) or [None])[0],
            }
        )
    return {
        "by": by,
        "label": label,
        "available": available,
        "needs_reanalysis": needs_v2 and not _has_v2(df),
        "segments": segments,
    }


# ---- Risks -----------------------------------------------------------------------------------


def risks_view(df: pd.DataFrame) -> dict:
    """Early warnings for a PM: people leaving, competitors named, and money problems."""
    tagged = df[df["tagged"]]
    total = len(tagged)
    mid = _midpoint(df)
    churn = tagged[tagged["churn_risk"].isin(["left", "considering"])]
    churn_themes = Counter(t for themes in churn["themes"] for t in themes)

    competitors = []
    named = tagged.assign(competitor=tagged["competitors"]).explode("competitor")
    named = named[named["competitor"].notna() & (named["competitor"] != "")]
    for name, g in named.groupby(named["competitor"].str.strip().str.title()):
        competitors.append(
            {
                "name": name,
                "mentions": len(g),
                "avg_rating": round(float(g["rating"].mean()), 2),
                "switching": int(g["churn_risk"].isin(["left", "considering"]).sum()),
                "quote": (_quotes(g, 1) or [None])[0],
            }
        )
    payments = tagged[(tagged["journey_stage"] == "payments_subscription") & (tagged["rating"] <= 2)]
    payment_themes = Counter(t for themes in payments["themes"] for t in themes)
    return {
        "available": _has_v2(df),
        "total_tagged": total,
        "churn": {
            "left": int((churn["churn_risk"] == "left").sum()),
            "considering": int((churn["churn_risk"] == "considering").sum()),
            "share": round(len(churn) / total, 4) if total else 0,
            "trend": _trend(churn, df, mid),
            "themes": [{"theme": t, "mentions": n} for t, n in churn_themes.most_common(6)],
            "by_user_type": _shares(churn["user_type"]),
            "quotes": _quotes(churn, 3),
        },
        "competitors": sorted(competitors, key=lambda c: c["mentions"], reverse=True)[:10],
        "payments": {
            "count": len(payments),
            "share": round(len(payments) / total, 4) if total else 0,
            "themes": [{"theme": t, "mentions": n} for t, n in payment_themes.most_common(5)],
            "quotes": _quotes(payments, 2),
        },
    }
