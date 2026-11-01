"""Accessibility view, developer replies (with AI reply drafts) and the pinboard."""

from __future__ import annotations

import pandas as pd
from conftest import RUN_BODY, wait_for_run

from backend.analytics.frame import sentiment_from_rating
from backend.analytics.views import PLAY_REPLY_LIMIT, accessibility_view

LLM = {"llm": {"provider": "anthropic", "model": "fake-model", "api_key": "sk-test"}}


def _run(client) -> str:
    return wait_for_run(client, client.post("/api/runs", json=RUN_BODY).json()["id"])["id"]


def _row(i: int, rating: int, text: str, a11y: str) -> dict:
    return {
        "review_id": f"r{i}",
        "date": pd.Timestamp(2026, 3, 1 + i),
        "rating": rating,
        "sentiment": sentiment_from_rating(rating),
        "content": text,
        "app_version": "1.0",
        "thumbs_up": i,
        "reply": None,
        "category": "ux_friction",
        "themes": ["readability"],
        "journey_stage": "core_experience",
        "emotion": "frustration",
        "accessibility": a11y,
        "tagged": True,
    }


def test_accessibility_needs_are_grouped_with_checks():
    df = pd.DataFrame(
        [
            _row(0, 1, "The text is too small to read and there is no zoom", "yes"),
            _row(1, 2, "TalkBack reads every button as unlabeled", "yes"),
            _row(2, 1, "I have arthritis and the tiny buttons are hard to tap", "yes"),
            _row(3, 4, "Works for me, nice", "yes"),
            _row(4, 1, "Crashes all the time", "no"),
        ]
    )
    data = accessibility_view(df)
    assert data["count"] == 4 and data["share"] == 0.8 and data["available"]
    areas = {a["area"]: a for a in data["areas"]}
    assert areas["Text size and zoom"]["count"] == 1 and "WCAG 1.4.4" in areas["Text size and zoom"]["check"]
    assert areas["Touch and dexterity"]["count"] == 2  # both mention buttons; one also arthritis
    assert "Screen readers" in areas
    assert data["unmatched"] == 1
    quoted = [q["review_id"] for a in data["areas"] for q in a["quotes"]] + [q["review_id"] for q in data["quotes"]]
    assert len(quoted) == len(set(quoted))  # no quote repeated in the view


def test_accessibility_api(client):
    data = client.get(f"/api/runs/{_run(client)}/views/accessibility").json()
    assert data["count"] == 10  # the fake model flags the "map" reviews
    assert data["areas"] == [] and data["unmatched"] == 10


def test_developer_replies(client):
    run_id = _run(client)
    data = client.get(f"/api/runs/{run_id}/views/replies").json()
    # 60 reviews: 20 one-star logins, 10 two-star crashes (all answered with one template), 30 others.
    assert data["replied"] == 10 and data["reply_rate"] == round(10 / 60, 4)
    assert data["negative_reply_rate"] == round(10 / 30, 4)
    assert data["avg_rating_replied"] == 2.0
    assert data["templated_share"] == 1.0 and data["templates"][0]["uses"] == 10
    top = data["unanswered_themes"][0]
    assert (top["theme"], top["reviews"]) == ("login problems", 20) and top["helpful_votes"] > 0
    assert all(r["rating"] == 1 and not r["reply"] for r in data["reply_first"])
    assert [b["rating"] for b in data["by_rating"]] == [1, 2, 3, 4, 5] and data["by_rating"][1]["reply_rate"] == 1.0


def test_reply_draft_fits_play_limit(client):
    run_id = _run(client)
    review_id = client.get(f"/api/runs/{run_id}/views/replies").json()["reply_first"][0]["review_id"]
    draft = client.post(f"/api/runs/{run_id}/views/replies/draft", json={"review_id": review_id, **LLM}).json()
    assert 150 < len(draft["reply"]) <= PLAY_REPLY_LIMIT and draft["reply"].endswith(".")
    missing = client.post(f"/api/runs/{run_id}/views/replies/draft", json={"review_id": "nope", **LLM})
    assert missing.status_code == 404


def test_pinboard_and_report_export(client):
    run_id = _run(client)
    reviews = client.get(f"/api/runs/{run_id}/reviews", params={"limit": 3}).json()["items"]
    first, second = reviews[0]["review_id"], reviews[1]["review_id"]
    assert client.put(f"/api/runs/{run_id}/pins/{first}", json={"note": "  Use in kickoff "}).status_code == 200
    pins = client.put(f"/api/runs/{run_id}/pins/{second}", json={}).json()
    assert [p["review_id"] for p in pins] == [first, second] and pins[0]["note"] == "Use in kickoff"
    pins = client.put(f"/api/runs/{run_id}/pins/{first}", json={"note": "Changed"}).json()  # update, not duplicate
    assert len(pins) == 2 and pins[0]["note"] == "Changed"
    assert client.put(f"/api/runs/{run_id}/pins/not-a-review", json={}).status_code == 404
    assert client.delete(f"/api/runs/{run_id}/pins/{second}").status_code == 204
    assert [p["review_id"] for p in client.get(f"/api/runs/{run_id}/pins").json()] == [first]

    client.post(f"/api/runs/{run_id}/artifacts/report", json=LLM)
    md = client.get(f"/api/runs/{run_id}/artifacts/report/markdown").text
    assert "## Pinned evidence" in md and "Note: Changed" in md and reviews[0]["content"] in md


def test_assistant_tools_for_new_views(client):
    from backend.assistant.tools import ToolContext, run_tool

    run_id = _run(client)
    ctx = client.app.state.ctx
    tools = ToolContext(ctx.db, ctx.frames)
    assert run_tool(tools, "get_accessibility", {"run_id": run_id})["count"] == 10
    replies = run_tool(tools, "get_developer_replies", {"run_id": run_id})
    assert replies["templated_share"] == 1.0 and "text" in replies["reply_first"][0]


def test_near_identical_replies_count_as_one_template():
    from backend.analytics.views import _reply_templates

    groups = _reply_templates(
        [
            'After downloading, select "New Player". Minors use Kids @ Scopely Email.',
            'After downloading, select "New Player". Minors use Kids @ Scopley Email.',
            "Clear the cache and reinstall the game, then log in again.",
        ]
    )
    assert sorted(len(g) for g in groups) == [1, 2]
