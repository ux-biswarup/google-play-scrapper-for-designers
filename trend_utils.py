"""
Trend + "What changed" helpers: time-based insights for Play Store reviews.
Expects DataFrame with: review_id, date, rating, content, sentiment, app_version, topics, issues, praises.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Literal

import pandas as pd

Granularity = Literal["D", "W"]


# Lightweight stopwords (english) for keyword extraction fallback
_STOP = frozenset(
    "a an the and or but in on at to for of with by from as is was are were been be have has had do does did will would could should may might must can need dare ought used".split()
)


def _ensure_datetime(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    return pd.to_datetime(series, errors="coerce")


def load_reviews_df(app_id: str, reports_dir: str = "reports") -> pd.DataFrame | None:
    """Load enriched reviews from reports/{app_id}_reviews.json. Returns DataFrame or None."""
    path = os.path.join(reports_dir, f"{app_id}_reviews.json")
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        rows = json.load(f)
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["date"] = _ensure_datetime(df["date"])
    df = df.dropna(subset=["date"])
    return df


def compute_time_buckets(df: pd.DataFrame, granularity: Granularity) -> pd.DataFrame:
    """Add `bucket` column (datetime) floored to day or week. Modifies copy."""
    df = df.copy()
    if "date" not in df.columns or df["date"].isna().all():
        df["bucket"] = pd.NaT
        return df
    d = _ensure_datetime(df["date"]).dt
    if granularity == "W":
        df["bucket"] = (d.normalize() - pd.to_timedelta(d.dayofweek, unit="d")).dt.normalize()
    else:
        df["bucket"] = d.normalize()
    return df


def rating_trend(
    df: pd.DataFrame,
    granularity: Granularity,
    date_min: pd.Timestamp | None = None,
    date_max: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Aggregate by bucket: avg rating, count. Optional date filter."""
    out = compute_time_buckets(df, granularity)
    if date_min is not None:
        out = out[out["date"] >= date_min]
    if date_max is not None:
        out = out[out["date"] <= date_max]
    g = out.groupby("bucket", as_index=False).agg(
        avg_rating=("rating", "mean"),
        count=("review_id", "count"),
    )
    return g.sort_values("bucket")


def sentiment_trend(
    df: pd.DataFrame,
    granularity: Granularity,
    date_min: pd.Timestamp | None = None,
    date_max: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """By bucket: total count, and % positive, % negative, % neutral."""
    out = compute_time_buckets(df, granularity)
    if date_min is not None:
        out = out[out["date"] >= date_min]
    if date_max is not None:
        out = out[out["date"] <= date_max]
    g = out.groupby("bucket")["sentiment"].value_counts().unstack(fill_value=0)
    for c in ("positive", "neutral", "negative"):
        if c not in g.columns:
            g[c] = 0
    g = g[["positive", "neutral", "negative"]]
    g["total"] = g["positive"] + g["neutral"] + g["negative"]
    g["pct_positive"] = (g["positive"] / g["total"].replace(0, 1)) * 100
    g["pct_negative"] = (g["negative"] / g["total"].replace(0, 1)) * 100
    g["pct_neutral"] = (g["neutral"] / g["total"].replace(0, 1)) * 100
    g = g.reset_index()
    return g.sort_values("bucket")


def _extract_keywords(texts: list[str], top_n: int = 10) -> list[str]:
    """Simple word-frequency keywords from list of strings. Ignores stopwords."""
    c: dict[str, int] = {}
    for s in texts:
        s = (s or "").lower()
        for w in re.findall(r"[a-z0-9]+", s):
            if len(w) > 1 and w not in _STOP:
                c[w] = c.get(w, 0) + 1
    pairs = sorted(c.items(), key=lambda x: -x[1])[:top_n]
    return [w for w, _ in pairs]


def detect_spikes(
    df: pd.DataFrame,
    granularity: Granularity,
    threshold: float = 2.0,
    window: int = 7,
    date_min: pd.Timestamp | None = None,
    date_max: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """
    1-star spike detection: rolling mean + threshold * rolling std.
    Returns (series DataFrame: bucket, count_1, baseline_avg, spike_score, is_spike),
    and list of spike rows for table: spike_date, count_1, baseline_avg, spike_score, top_keywords.
    """
    out = compute_time_buckets(df, granularity)
    out["date"] = _ensure_datetime(out["date"])
    out = out.dropna(subset=["date"])
    if date_min is not None:
        out = out[out["date"] >= date_min]
    if date_max is not None:
        out = out[out["date"] <= date_max]

    one_star = out[out["rating"] == 1].copy()
    daily = one_star.groupby("bucket", as_index=False).agg(
        count_1=("review_id", "count"),
        contents=("content", lambda x: list(x.dropna().astype(str))),
    )

    # Full bucket range for continuous x-axis
    start = out["bucket"].min()
    end = out["bucket"].max()
    if pd.isna(start) or pd.isna(end):
        daily["baseline_avg"] = 0.0
        daily["baseline_std"] = 0.0
        daily["spike_score"] = 0.0
        daily["is_spike"] = False
        return daily, []

    freq = "W-MON" if granularity == "W" else "D"
    full_range = pd.date_range(start=start, end=end, freq=freq)
    full = pd.DataFrame({"bucket": full_range})
    daily = full.merge(daily, on="bucket", how="left").fillna({"count_1": 0})
    daily["count_1"] = daily["count_1"].astype(int)
    daily = daily.sort_values("bucket").reset_index(drop=True)

    daily["baseline_avg"] = daily["count_1"].rolling(window, min_periods=1).mean()
    daily["baseline_std"] = daily["count_1"].rolling(window, min_periods=1).std().fillna(0)
    daily["spike_score"] = (daily["count_1"] - daily["baseline_avg"]) / (daily["baseline_std"].replace(0, 1))
    daily["is_spike"] = daily["count_1"] > (daily["baseline_avg"] + threshold * daily["baseline_std"])

    spike_rows = []
    for _, r in daily[daily["is_spike"]].iterrows():
        kw = _extract_keywords((r.get("contents") or []) or [], top_n=5)
        b = r["bucket"]
        spike_rows.append({
            "spike_date": b.strftime("%Y-%m-%d") if hasattr(b, "strftime") else str(b)[:10],
            "count_1": int(r["count_1"]),
            "baseline_avg": round(float(r["baseline_avg"]), 2),
            "spike_score": round(float(r["spike_score"]), 2),
            "top_keywords": ", ".join(kw) if kw else "—",
        })

    return daily, spike_rows


def compare_before_after(
    df: pd.DataFrame,
    mode: Literal["version", "date"],
    pivot: str,
    date_min: pd.Timestamp | None = None,
    date_max: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """
    mode 'version': pivot = version string. Before = reviews before first occurrence of that version; After = that version.
    mode 'date': pivot = YYYY-MM-DD. Before = date < pivot; After = date >= pivot.

    Returns: {
      before: { avg_rating, sentiment_dist, issues_count },
      after: { ... },
      delta_rating, delta_negative_pct,
      emerging_issues: [ issue strings that appear in after but not before ],
    }
    """
    out = df.copy()
    out["date"] = _ensure_datetime(out["date"])
    out = out.dropna(subset=["date"])
    if date_min is not None:
        out = out[out["date"] >= date_min]
    if date_max is not None:
        out = out[out["date"] <= date_max]

    def sentiment_dist(s: pd.Series) -> dict[str, float]:
        v = s.value_counts()
        total = max(v.sum(), 1)
        return {
            "positive": 100 * v.get("positive", 0) / total,
            "neutral": 100 * v.get("neutral", 0) / total,
            "negative": 100 * v.get("negative", 0) / total,
        }

    def issues_count(grp: pd.DataFrame) -> dict[str, int]:
        c: dict[str, int] = {}
        for _, row in grp.iterrows():
            lst = row.get("issues") if "issues" in grp.columns else []
            if not isinstance(lst, list):
                lst = []
            for i in lst:
                if i:
                    c[str(i)] = c.get(str(i), 0) + 1
        return c

    before_df = pd.DataFrame()
    after_df = pd.DataFrame()

    if mode == "date":
        pivot_d = pd.Timestamp(pivot)
        before_df = out[out["date"] < pivot_d]
        after_df = out[out["date"] >= pivot_d]
    else:
        vers = out["app_version"].astype(str)
        mask = vers == str(pivot).strip()
        if not mask.any():
            return {
                "before": {"avg_rating": 0, "sentiment_dist": {}, "issues_count": {}},
                "after": {"avg_rating": 0, "sentiment_dist": {}, "issues_count": {}},
                "delta_rating": 0,
                "delta_negative_pct": 0,
                "emerging_issues": [],
            }
        first_after = out.loc[mask, "date"].min()
        before_df = out[out["date"] < first_after]
        after_df = out[out["date"] >= first_after]

    def row(grp: pd.DataFrame) -> dict:
        return {
            "avg_rating": float(grp["rating"].mean()) if len(grp) else 0,
            "sentiment_dist": sentiment_dist(grp["sentiment"]) if "sentiment" in grp.columns else {},
            "issues_count": issues_count(grp),
        }

    b = row(before_df)
    a = row(after_df)
    before_issues = set(b["issues_count"].keys())
    emerging = [i for i in a["issues_count"].keys() if i not in before_issues]

    return {
        "before": b,
        "after": a,
        "delta_rating": round(a["avg_rating"] - b["avg_rating"], 2),
        "delta_negative_pct": round(a["sentiment_dist"].get("negative", 0) - b["sentiment_dist"].get("negative", 0), 2),
        "emerging_issues": emerging,
    }


def trending_topics(
    df: pd.DataFrame,
    window_days: int = 7,
    date_max: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Last `window_days` vs previous `window_days`. Uses per-review `topics` (and `issues` as fallback).
    Returns DataFrame: topic, count_this_week, count_last_week, change_pct, direction (↑/↓).
    """
    out = df.copy()
    out["date"] = _ensure_datetime(out["date"])
    out = out.dropna(subset=["date"])
    end = date_max or out["date"].max()
    if pd.isna(end):
        return pd.DataFrame(columns=["topic", "count_this_week", "count_last_week", "change_pct", "direction"])
    this_start = end - timedelta(days=window_days)
    last_end = this_start
    last_start = last_end - timedelta(days=window_days)

    def collect(grp: pd.DataFrame) -> dict[str, int]:
        c: dict[str, int] = {}
        for _, r in grp.iterrows():
            for t in (r.get("topics") or []) or (r.get("issues") or []):
                if t and str(t).lower() != "error":
                    k = str(t).strip()
                    if k:
                        c[k] = c.get(k, 0) + 1
        return c

    this_df = out[(out["date"] >= this_start) & (out["date"] <= end)]
    last_df = out[(out["date"] >= last_start) & (out["date"] < last_end)]
    this_counts = collect(this_df)
    last_counts = collect(last_df)

    all_topics = set(this_counts.keys()) | set(last_counts.keys())
    rows = []
    for t in all_topics:
        tc = this_counts.get(t, 0)
        lc = last_counts.get(t, 0)
        if lc == 0:
            change_pct = 100.0 if tc else 0.0
        else:
            change_pct = ((tc - lc) / lc) * 100
        direction = "↑" if change_pct > 0 else "↓" if change_pct < 0 else "→"
        rows.append({"topic": t, "count_this_week": tc, "count_last_week": lc, "change_pct": round(change_pct, 1), "direction": direction})

    cols = ["topic", "count_this_week", "count_last_week", "change_pct", "direction"]
    if not rows:
        return pd.DataFrame(columns=cols)
    rows.sort(key=lambda r: r["count_this_week"], reverse=True)
    return pd.DataFrame(rows, columns=cols)
