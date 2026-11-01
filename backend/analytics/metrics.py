"""Semantic layer: named measures and dimensions with one definition each.

Dashboards and the chat assistant both query through here, so a number like "negative share"
always means the same thing everywhere, and the AI never writes raw SQL.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime

import pandas as pd


@dataclass(frozen=True)
class Measure:
    name: str
    label: str
    description: str
    column: str
    agg: str
    format: str  # number | percent | rating


@dataclass(frozen=True)
class Dimension:
    name: str
    label: str
    description: str
    column: str
    multi: bool = False  # one review can have several values (themes)


MEASURES: dict[str, Measure] = {
    m.name: m
    for m in (
        Measure(
            "review_count",
            "Reviews",
            "Number of reviews. Grouped by theme, it counts reviews mentioning the theme.",
            "review_id",
            "count",
            "number",
        ),
        Measure("avg_rating", "Average rating", "Mean star rating (1-5).", "rating", "mean", "rating"),
        Measure(
            "negative_share", "Negative share", "Share of reviews rated 1-2 stars (0-1).", "_neg", "mean", "percent"
        ),
        Measure("neutral_share", "Neutral share", "Share of reviews rated 3 stars (0-1).", "_neu", "mean", "percent"),
        Measure(
            "positive_share", "Positive share", "Share of reviews rated 4-5 stars (0-1).", "_pos", "mean", "percent"
        ),
        Measure(
            "helpful_votes",
            "Helpful votes",
            "Total 'helpful' votes other users gave these reviews.",
            "thumbs_up",
            "sum",
            "number",
        ),
    )
}

DIMENSIONS: dict[str, Dimension] = {
    d.name: d
    for d in (
        Dimension("date", "Date", "Review date, bucketed by time_grain (day, week or month).", "date"),
        Dimension("rating", "Rating", "Star rating 1-5.", "rating"),
        Dimension("sentiment", "Sentiment", "negative (1-2 stars), neutral (3), positive (4-5).", "sentiment"),
        Dimension("app_version", "App version", "App version the reviewer was using.", "app_version"),
        Dimension(
            "category",
            "Feedback type",
            "bug, feature_request, ux_friction, complaint, praise, question, other.",
            "category",
        ),
        Dimension(
            "theme",
            "Theme",
            "Grouped topic of the feedback. A review can mention several themes.",
            "themes",
            multi=True,
        ),
        Dimension("journey_stage", "Journey stage", "Where in the user journey the feedback belongs.", "journey_stage"),
        Dimension("emotion", "Emotion", "The reviewer's dominant emotion.", "emotion"),
    )
}

TIME_GRAINS = ("day", "week", "month")
UNKNOWN = "unknown"


@dataclass
class MetricsQuery:
    measures: list[str]
    dimensions: list[str] = field(default_factory=list)
    filters: dict[str, list] = field(default_factory=dict)
    time_grain: str = "day"
    date_from: date | None = None
    date_to: date | None = None
    order_by: str | None = None
    descending: bool = True
    limit: int | None = None


def catalog() -> dict:
    return {
        "measures": [asdict(m) for m in MEASURES.values()],
        "dimensions": [asdict(d) for d in DIMENSIONS.values()],
        "time_grains": list(TIME_GRAINS),
    }


def auto_grain(dates: pd.Series) -> str:
    """Pick a time grain that gives a readable number of points for the date span."""
    dates = dates.dropna()
    if dates.empty:
        return "day"
    span_days = (dates.max() - dates.min()).days
    return "day" if span_days <= 31 else "week" if span_days <= 180 else "month"


def bucket_dates(dates: pd.Series, grain: str) -> pd.Series:
    if grain == "week":
        return dates.dt.to_period("W-SUN").dt.start_time  # weeks start on Monday
    if grain == "month":
        return dates.dt.to_period("M").dt.start_time
    return dates.dt.normalize()


def apply_filters(
    df: pd.DataFrame,
    filters: dict[str, list] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> pd.DataFrame:
    """Filter rows. Date bounds are inclusive whole days."""
    out = df
    if date_from is not None:
        out = out[out["date"] >= pd.Timestamp(date_from).normalize()]
    if date_to is not None:
        out = out[out["date"] < pd.Timestamp(date_to).normalize() + pd.Timedelta(days=1)]
    for name, values in (filters or {}).items():
        if not values:
            continue
        dim = DIMENSIONS.get(name)
        if dim is None or name == "date":
            raise ValueError(
                f"Cannot filter on '{name}'. Use one of: {', '.join(d for d in DIMENSIONS if d != 'date')}."
            )
        wanted = {str(v) for v in values}
        if dim.multi:
            out = out[out[dim.column].apply(lambda items, wanted=wanted: any(str(i) in wanted for i in items))]
        else:
            out = out[out[dim.column].fillna(UNKNOWN).astype(str).isin(wanted)]
    return out


def run_query(df: pd.DataFrame, q: MetricsQuery) -> list[dict]:
    unknown_measures = [m for m in q.measures if m not in MEASURES]
    if not q.measures or unknown_measures:
        raise ValueError(f"Unknown measures {unknown_measures}. Use: {', '.join(MEASURES)}.")
    unknown_dims = [d for d in q.dimensions if d not in DIMENSIONS]
    if unknown_dims:
        raise ValueError(f"Unknown dimensions {unknown_dims}. Use: {', '.join(DIMENSIONS)}.")
    if q.time_grain not in TIME_GRAINS:
        raise ValueError(f"time_grain must be one of {TIME_GRAINS}.")

    data = apply_filters(df, q.filters, q.date_from, q.date_to).copy()
    data["_neg"] = (data["rating"] <= 2).astype(float)
    data["_neu"] = (data["rating"] == 3).astype(float)
    data["_pos"] = (data["rating"] >= 4).astype(float)

    group_cols: list[str] = []
    for name in q.dimensions:
        dim = DIMENSIONS[name]
        if dim.multi:
            data = data.explode(dim.column)
            data = data[data[dim.column].notna()]
            data[name] = data[dim.column]
        elif name == "date":
            data = data[data["date"].notna()]
            data[name] = bucket_dates(data["date"], q.time_grain)
        elif name != dim.column:
            data[name] = data[dim.column]
        if name not in ("date", "rating"):
            data[name] = data[name].fillna(UNKNOWN).astype(str)
        group_cols.append(name)

    aggs = {m: (MEASURES[m].column, MEASURES[m].agg) for m in q.measures}
    if group_cols:
        result = data.groupby(group_cols, dropna=False).agg(**aggs).reset_index()
    else:
        result = pd.DataFrame([{m: data[col].agg(fn) if len(data) else 0 for m, (col, fn) in aggs.items()}])

    order = q.order_by or ("date" if "date" in group_cols else q.measures[0])
    if order not in result.columns:
        raise ValueError(f"order_by must be one of the requested measures or dimensions, got '{order}'.")
    ascending = (order == "date") if q.order_by is None else not q.descending
    result = result.sort_values(order, ascending=ascending, kind="stable")
    if q.limit:
        result = result.head(q.limit)
    return [_clean_row(row) for row in result.to_dict(orient="records")]


def _clean_row(row: dict) -> dict:
    out = {}
    for key, value in row.items():
        if isinstance(value, (pd.Timestamp, datetime)):
            value = value.strftime("%Y-%m-%d")
        elif isinstance(value, float):
            value = None if pd.isna(value) else round(value, 4)
        elif hasattr(value, "item"):  # numpy scalar
            value = value.item()
        out[key] = value
    return out
