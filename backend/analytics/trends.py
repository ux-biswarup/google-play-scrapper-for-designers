"""Time-based insights: 1-star spikes, release before/after comparison, trending themes, versions."""

from __future__ import annotations

from collections import Counter
from datetime import date

import pandas as pd

from .metrics import apply_filters, bucket_dates

_FREQ = {"day": "D", "week": "W-MON", "month": "MS"}
MIN_SPIKE_COUNT = 3  # ignore "spikes" of one or two reviews
MIN_HISTORY = 3  # buckets of history needed before a bucket can be called a spike


def _theme_counts(df: pd.DataFrame) -> Counter:
    counts: Counter = Counter()
    for themes in df["themes"]:
        counts.update(themes)
    return counts


def spikes(
    df: pd.DataFrame,
    grain: str = "day",
    threshold: float = 2.0,
    window: int = 7,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """1-star volume per bucket vs. a trailing baseline of the previous `window` buckets."""
    if grain not in _FREQ:
        raise ValueError(f"grain must be one of {list(_FREQ)}.")
    data = apply_filters(df, None, date_from, date_to)
    data = data[data["date"].notna()].copy()
    if data.empty:
        return {"series": [], "spikes": []}
    data["bucket"] = bucket_dates(data["date"], grain)
    full = pd.date_range(data["bucket"].min(), data["bucket"].max(), freq=_FREQ[grain])
    ones = data[data["rating"] == 1]
    counts = ones.groupby("bucket").size().reindex(full, fill_value=0).astype(int)
    totals = data.groupby("bucket").size().reindex(full, fill_value=0).astype(int)
    history = counts.shift(1)  # baseline excludes the bucket being tested
    enough_history = history.rolling(window, min_periods=1).count() >= MIN_HISTORY
    baseline = history.rolling(window, min_periods=1).mean().fillna(0.0)
    spread = history.rolling(window, min_periods=2).std().fillna(0.0)
    is_spike = enough_history & (counts > baseline + threshold * spread) & (counts >= MIN_SPIKE_COUNT)

    series, found = [], []
    for bucket in full:
        count, base, std = int(counts[bucket]), float(baseline[bucket]), float(spread[bucket])
        series.append(
            {
                "date": bucket.strftime("%Y-%m-%d"),
                "one_star": count,
                "total": int(totals[bucket]),
                "baseline": round(base, 2),
                "is_spike": bool(is_spike[bucket]),
            }
        )
        if is_spike[bucket]:
            in_bucket = ones[ones["bucket"] == bucket]
            found.append(
                {
                    "date": bucket.strftime("%Y-%m-%d"),
                    "one_star": count,
                    "baseline": round(base, 2),
                    "score": round((count - base) / max(std, 1.0), 2),
                    "top_themes": [t for t, _ in _theme_counts(in_bucket).most_common(3)],
                    "versions": in_bucket["app_version"].value_counts().head(3).index.tolist(),
                }
            )
    return {"series": series, "spikes": found}


def _group_summary(g: pd.DataFrame, top: int = 8) -> dict:
    n = len(g)
    counts = _theme_counts(g)
    return {
        "review_count": n,
        "avg_rating": round(float(g["rating"].mean()), 3) if n else None,
        "negative_share": round(float((g["rating"] <= 2).mean()), 4) if n else None,
        "positive_share": round(float((g["rating"] >= 4).mean()), 4) if n else None,
        "top_themes": [{"theme": t, "count": c, "share": round(c / n, 4)} for t, c in counts.most_common(top)],
    }


def compare(df: pd.DataFrame, mode: str, pivot: str) -> dict:
    """Before vs. after a release (first day a version appears) or a date (after = on/after that day)."""
    data = df[df["date"].notna()]
    if mode == "version":
        mask = data["app_version"] == pivot
        if not mask.any():
            raise ValueError(f"No reviews from version {pivot}.")
        start = data.loc[mask, "date"].min()
    elif mode == "date":
        start = pd.Timestamp(pivot).normalize()
    else:
        raise ValueError("mode must be 'version' or 'date'.")
    before, after = data[data["date"] < start], data[data["date"] >= start]
    b, a = _group_summary(before), _group_summary(after)

    b_counts, a_counts = _theme_counts(before), _theme_counts(after)
    shifts = []
    for theme in set(b_counts) | set(a_counts):
        b_share = b_counts[theme] / len(before) if len(before) else 0.0
        a_share = a_counts[theme] / len(after) if len(after) else 0.0
        shifts.append(
            {
                "theme": theme,
                "before_count": b_counts[theme],
                "after_count": a_counts[theme],
                "before_share": round(b_share, 4),
                "after_share": round(a_share, 4),
                "delta": round(a_share - b_share, 4),
            }
        )
    shifts.sort(key=lambda s: s["delta"], reverse=True)

    def delta(key: str):
        return None if a[key] is None or b[key] is None else round(a[key] - b[key], 4)

    return {
        "mode": mode,
        "pivot": pivot,
        "split_date": start.strftime("%Y-%m-%d"),
        "before": b,
        "after": a,
        "delta_avg_rating": delta("avg_rating"),
        "delta_negative_share": delta("negative_share"),
        "new_themes": [s for s in shifts if s["before_count"] == 0 and s["after_count"] >= 2],
        "rising_themes": [s for s in shifts if s["delta"] > 0 and s["before_count"] > 0][:10],
        "falling_themes": [s for s in reversed(shifts) if s["delta"] < 0][:10],
    }


def trending_themes(df: pd.DataFrame, window_days: int = 7, date_to: date | None = None, limit: int = 15) -> list[dict]:
    """Theme mentions in the last `window_days` vs. the window before it."""
    data = df[df["date"].notna()]
    if data.empty:
        return []
    end = (pd.Timestamp(date_to).normalize() + pd.Timedelta(days=1)) if date_to else data["date"].max()
    this_start = end - pd.Timedelta(days=window_days)
    last_start = this_start - pd.Timedelta(days=window_days)
    now = _theme_counts(data[(data["date"] >= this_start) & (data["date"] <= end)])
    prev = _theme_counts(data[(data["date"] >= last_start) & (data["date"] < this_start)])
    rows = []
    for theme in set(now) | set(prev):
        current, previous = now[theme], prev[theme]
        change = ((current - previous) / previous) if previous else (1.0 if current else 0.0)
        rows.append(
            {
                "theme": theme,
                "current": current,
                "previous": previous,
                "change": round(change, 4),
                "direction": "up" if current > previous else "down" if current < previous else "flat",
            }
        )
    rows.sort(key=lambda r: (r["current"], r["change"]), reverse=True)
    return rows[:limit]


def versions(df: pd.DataFrame) -> list[dict]:
    data = df[df["date"].notna()]
    if data.empty:
        return []
    g = data.groupby("app_version")
    out = (
        pd.DataFrame(
            {
                "review_count": g.size(),
                "avg_rating": g["rating"].mean().round(3),
                "negative_share": g["rating"].apply(lambda r: (r <= 2).mean()).round(4),
                "first_seen": g["date"].min(),
                "last_seen": g["date"].max(),
            }
        )
        .reset_index()
        .sort_values("first_seen")
    )
    return [
        {
            **row,
            "first_seen": row["first_seen"].strftime("%Y-%m-%d"),
            "last_seen": row["last_seen"].strftime("%Y-%m-%d"),
            "review_count": int(row["review_count"]),
            "avg_rating": float(row["avg_rating"]),
            "negative_share": float(row["negative_share"]),
        }
        for row in out.to_dict(orient="records")
    ]
