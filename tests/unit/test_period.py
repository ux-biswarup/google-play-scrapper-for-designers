"""Analyzing a date range: scanning Google Play newest-first, counting, and picking reviews."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from conftest import RUN_BODY, wait_for_run

from backend.services import play_store
from backend.services.play_store import PlayStoreClient, StoreReview, pick_reviews


def _review(i: int, day: int) -> StoreReview:
    return StoreReview(f"r{i}", 3, "text", datetime(2026, 3, day, 12), None, 0, None)


def test_pick_reviews_newest_or_spread():
    reviews = [_review(i, 30 - i) for i in range(30)]  # newest first: Mar 30 ... Mar 1
    assert [r.review_id for r in pick_reviews(reviews, 3, "newest")] == ["r0", "r1", "r2"]
    spread = pick_reviews(reviews, 3, "spread")
    assert [r.reviewed_at.day for r in spread] == [30, 15, 1]  # last, middle and first day, newest first
    assert len(pick_reviews(reviews, 100, "spread")) == 30


def test_scan_window_skips_newer_and_stops_at_older(monkeypatch):
    class Token:
        def __init__(self, n):
            self.token = n

    newest = datetime(2026, 3, 20, 12)
    calls = []

    def fake_reviews(app_id, *, continuation_token=None, **_kwargs):
        """Endless pages of 4 reviews, 12 hours apart, each page older than the last."""
        page = 0 if continuation_token is None else continuation_token.token
        calls.append(page)
        items = [
            {"reviewId": f"p{page}-{i}", "score": 4, "at": newest - timedelta(hours=12 * (page * 4 + i))}
            for i in range(4)
        ]
        return items, Token(page + 1)

    monkeypatch.setattr(play_store, "gp_reviews", fake_reviews)
    window = PlayStoreClient().scan_window(
        "com.x.y", lang="en", country="us", date_from=date(2026, 3, 17), date_to=date(2026, 3, 18)
    )
    days = sorted({r.reviewed_at.day for r in window.reviews})
    assert days == [17, 18] and len(window.reviews) == 4
    assert window.complete and window.oldest_reached.day == 16
    assert calls == [0, 1, 2]  # stopped on the page where it reached older reviews

    calls.clear()
    capped = PlayStoreClient().scan_window(
        "com.x.y", lang="en", country="us", date_from=date(2020, 1, 1), date_to=None, max_scan=400
    )
    assert not capped.complete and capped.scanned == 400 and len(calls) == 100  # budget hit before the start


def test_count_then_analyze_a_period(client):
    store = client.app.state.ctx.store
    body = {"app": "com.example.app", "date_from": "2026-01-04", "date_to": "2026-01-06"}
    window = client.post("/api/apps/review-window", json=body).json()
    assert window["complete"] and window["first_review"] >= "2026-01-04" and window["last_review"] <= "2026-01-06"
    assert 0 < window["in_range"] < 60
    scans = store.scans

    run = client.post(
        "/api/runs",
        json=RUN_BODY | {"count": 10, "date_from": "2026-01-04", "date_to": "2026-01-06", "sampling": "spread"},
    ).json()
    done = wait_for_run(client, run["id"])
    assert done["status"] == "completed" and done["review_count"] == 10
    assert (done["date_from"], done["date_to"], done["sampling"]) == ("2026-01-04", "2026-01-06", "spread")
    assert store.scans == scans  # the count's scan was reused, not repeated
    dates = [
        r["date"][:10] for r in client.get(f"/api/runs/{run['id']}/reviews", params={"page_size": 100}).json()["items"]
    ]
    assert min(dates) >= "2026-01-04" and max(dates) <= "2026-01-06"
    assert min(dates) < "2026-01-05" and max(dates) > "2026-01-05"  # spread covers both ends of the period


def test_period_validation(client):
    bad = client.post("/api/runs", json=RUN_BODY | {"date_from": "2026-02-01", "date_to": "2026-01-01"})
    assert bad.status_code == 422
    assert client.post("/api/apps/review-window", json={"app": "com.example.app"}).status_code == 400
    empty = client.post("/api/runs", json=RUN_BODY | {"date_from": "2030-01-01", "date_to": "2030-01-02"}).json()
    failed = wait_for_run(client, empty["id"])
    assert failed["status"] == "failed" and "No reviews in this period" in failed["error"]
