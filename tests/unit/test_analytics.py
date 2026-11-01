"""Unit tests for the metrics layer, trends, problem board and matplotlib charts."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from backend.analytics import charts, insights, trends
from backend.analytics.frame import sentiment_from_rating
from backend.analytics.metrics import MetricsQuery, auto_grain, run_query


def _row(i: int, day: int, rating: int, themes: list[str], version: str = "1.0", hour: int = 12) -> dict:
    return {
        "review_id": f"r{i}", "date": pd.Timestamp(2026, 3, day, hour), "rating": rating,
        "sentiment": sentiment_from_rating(rating), "content": f"review number {i} with enough text",
        "app_version": version, "thumbs_up": i, "reply": None, "category": "bug" if rating <= 2 else "praise",
        "themes": themes, "journey_stage": "core_experience", "emotion": "neutral", "tagged": True,
    }


@pytest.fixture
def df() -> pd.DataFrame:
    rows = []
    i = 0
    for day in range(1, 11):  # quiet period: one 1-star "slow app" + one 5-star "nice ui" per day
        rows += [_row(i, day, 1, ["slow app"]), _row(i + 1, day, 5, ["nice ui"])]
        i += 2
    for _ in range(6):  # release 2.0 on day 11: burst of 1-star login problems
        rows.append(_row(i, 11, 1, ["login broken", "slow app"], version="2.0", hour=23))
        i += 1
    return pd.DataFrame(rows)


def test_metrics_by_theme_and_filters(df):
    rows = run_query(df, MetricsQuery(measures=["review_count", "negative_share"], dimensions=["theme"]))
    by_theme = {r["theme"]: r for r in rows}
    assert by_theme["slow app"] == {"theme": "slow app", "review_count": 16, "negative_share": 1.0}
    assert rows[0]["theme"] == "slow app"  # sorted by first measure, descending

    only_v2 = run_query(df, MetricsQuery(measures=["review_count"], filters={"app_version": ["2.0"]}))
    assert only_v2 == [{"review_count": 6}]


def test_date_to_includes_the_whole_last_day(df):
    # Regression: the old version cut the end date at midnight and dropped that day's reviews.
    rows = run_query(df, MetricsQuery(measures=["review_count"], date_from=date(2026, 3, 11), date_to=date(2026, 3, 11)))
    assert rows == [{"review_count": 6}]


def test_time_series_and_grains(df):
    daily = run_query(df, MetricsQuery(measures=["review_count"], dimensions=["date"]))
    assert [r["date"] for r in daily][:2] == ["2026-03-01", "2026-03-02"] and len(daily) == 11
    weekly = run_query(df, MetricsQuery(measures=["review_count"], dimensions=["date"], time_grain="week"))
    assert weekly[0]["date"] == "2026-02-23"  # weeks start on Monday
    assert sum(r["review_count"] for r in weekly) == len(df)
    assert auto_grain(df["date"]) == "day"


def test_invalid_queries_raise(df):
    for bad in (
        MetricsQuery(measures=["nope"]),
        MetricsQuery(measures=["review_count"], dimensions=["planet"]),
        MetricsQuery(measures=["review_count"], time_grain="hour"),
        MetricsQuery(measures=["review_count"], filters={"date": ["x"]}),
        MetricsQuery(measures=["review_count"], order_by="avg_rating"),
    ):
        with pytest.raises(ValueError):
            run_query(df, bad)


def test_spike_detection_needs_history(df):
    result = trends.spikes(df, "day")
    assert [s["date"] for s in result["spikes"]] == ["2026-03-11"]
    assert result["spikes"][0]["top_themes"][0] in ("login broken", "slow app")
    assert result["series"][0]["is_spike"] is False  # first bucket has no baseline


def test_compare_by_version(df):
    result = trends.compare(df, "version", "2.0")
    assert result["split_date"] == "2026-03-11"
    assert result["after"]["review_count"] == 6
    assert [t["theme"] for t in result["new_themes"]] == ["login broken"]
    assert result["delta_negative_share"] > 0
    with pytest.raises(ValueError):
        trends.compare(df, "version", "9.9")


def test_trending_themes(df):
    top = trends.trending_themes(df, window_days=3)
    assert top[0]["theme"] == "slow app" and top[0]["direction"] == "up"


def test_problem_board_ranks_by_impact(df):
    board = insights.problem_board(df)
    assert [p["theme"] for p in board["problems"]] == ["slow app", "login broken"]
    login = board["problems"][1]
    assert login["trend"] == "rising" and login["mentions"] == 6
    assert login["quotes"] and login["quotes"][0]["rating"] == 1
    assert [s["theme"] for s in board["strengths"]] == ["nice ui"]
    assert "impact" in board["formula"]


def test_list_reviews_paging_and_sorting(df):
    page = insights.list_reviews(df, filters={"rating": [5]}, sort="most_helpful", page=2, page_size=3)
    assert page["total"] == 10 and len(page["items"]) == 3
    helpful = [r["thumbs_up"] for r in page["items"]]
    assert helpful == sorted(helpful, reverse=True)
    with pytest.raises(ValueError):
        insights.list_reviews(df, sort="random")


@pytest.mark.parametrize("name", list(charts.CHARTS))
def test_charts_render(df, name):
    assert charts.render(name, df, "Example App").startswith(b"\x89PNG")
    assert b"<svg" in charts.render(name, df.iloc[0:0], "Empty", fmt="svg")  # empty data still renders


def test_chart_errors(df):
    with pytest.raises(ValueError):
        charts.render("pie-of-doom", df, "x")
    with pytest.raises(ValueError):
        charts.render("top-problems", df, "x", fmt="gif")
