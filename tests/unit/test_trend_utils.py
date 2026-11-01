"""Offline unit tests for trend_utils (no network, no API keys)."""

import pandas as pd

import trend_utils as tu


def _make_df() -> pd.DataFrame:
    rows = []
    # 10 quiet days with one 1-star review each, then a spike day with eight.
    for day in range(1, 11):
        rows.append({
            "review_id": f"q{day}",
            "date": f"2026-01-{day:02d}T10:00:00",
            "rating": 1 if day % 2 else 5,
            "content": "works fine",
            "sentiment": "negative" if day % 2 else "positive",
            "app_version": "1.0",
            "topics": ["performance"],
            "issues": [],
            "praises": [],
        })
    for i in range(8):
        rows.append({
            "review_id": f"s{i}",
            "date": "2026-01-12T15:00:00",
            "rating": 1,
            "content": "login crash after update",
            "sentiment": "negative",
            "app_version": "2.0",
            "topics": ["login"],
            "issues": ["login crash"],
            "praises": [],
        })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_rating_trend_daily_buckets():
    out = tu.rating_trend(_make_df(), "D")
    assert len(out) == 11
    spike_day = out[out["bucket"] == pd.Timestamp("2026-01-12")].iloc[0]
    assert spike_day["count"] == 8
    assert spike_day["avg_rating"] == 1


def test_sentiment_trend_percentages_sum_to_100():
    out = tu.sentiment_trend(_make_df(), "D")
    totals = out["pct_positive"] + out["pct_neutral"] + out["pct_negative"]
    assert all(abs(t - 100) < 1e-9 for t in totals)


def test_detect_spikes_flags_spike_day_with_keywords():
    _, rows = tu.detect_spikes(_make_df(), "D", threshold=2.0)
    assert [r["spike_date"] for r in rows] == ["2026-01-12"]
    assert "login" in rows[0]["top_keywords"]


def test_compare_before_after_by_version_finds_emerging_issue():
    cmp = tu.compare_before_after(_make_df(), "version", "2.0")
    assert cmp["after"]["avg_rating"] == 1
    assert cmp["delta_rating"] < 0
    assert cmp["emerging_issues"] == ["login crash"]


def test_compare_before_after_unknown_version_is_empty():
    cmp = tu.compare_before_after(_make_df(), "version", "9.9")
    assert cmp["delta_rating"] == 0
    assert cmp["emerging_issues"] == []


def test_trending_topics_rising_topic_first():
    out = tu.trending_topics(_make_df(), window_days=7)
    assert out.iloc[0]["topic"] == "login"
    assert out.iloc[0]["direction"] == "↑"
