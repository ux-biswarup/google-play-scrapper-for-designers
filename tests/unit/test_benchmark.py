"""Benchmarks: comparing analyses side by side, plus the AI topic alignment."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pandas as pd
from conftest import RUN_BODY, FakeProvider, wait_for_run

from backend.analytics.benchmark import run_summary, topic_stats
from backend.analytics.frame import sentiment_from_rating
from backend.assistant import benchmark_ai

LLM = {"llm": {"provider": "anthropic", "model": "fake-model", "api_key": "sk-test"}}


def _two_runs(client) -> list[str]:
    ids = []
    for count in (60, 30):
        ids.append(wait_for_run(client, client.post("/api/runs", json=RUN_BODY | {"count": count}).json()["id"])["id"])
    return ids


def test_benchmark_compares_runs(client):
    a, b = _two_runs(client)
    created = client.post("/api/benchmarks", json={"run_ids": [a, b]}).json()
    assert created["name"] == "Example App" and [x["run_id"] for x in created["apps"]] == [a, b]
    data = client.get(f"/api/benchmarks/{created['id']}").json()
    first, second = (c["summary"] for c in data["columns"])
    assert first["reviews"] == 60 and second["reviews"] == 30
    assert set(first["feedback_types"]) >= {"bug", "praise"} and "account_login" in first["journey"]
    assert first["top_problems"][0]["theme"] == "login problems"
    assert data["insights"] is None
    assert client.get("/api/benchmarks").json()[0]["id"] == created["id"]


def test_benchmark_ai_alignment_is_validated(client):
    a, b = _two_runs(client)
    bench = client.post("/api/benchmarks", json={"run_ids": [a, b], "name": "Us vs them"}).json()
    data = client.post(f"/api/benchmarks/{bench['id']}/insights", json=LLM).json()
    insights = data["insights"]
    assert [t["name"] for t in insights["topics"]] == ["login", "dark mode"]  # invented-only topic dropped
    login = insights["topics"][0]["apps"]
    assert login[0]["themes"] == ["login problems"]  # invented theme name removed
    assert login[0]["mentions"] == 20 and login[0]["negative_share"] == 1.0
    assert insights["topics"][1]["apps"][0] == {"themes": [], "mentions": 0, "share": 0.0, "negative_share": None}
    # Same app twice with the same mix: nothing to lead or lag on.
    assert insights["leads"] == insights["lags"] == []
    assert insights["headline"] == "Example App compares well."


def _frame(prefix: str, login_ratings: list[int], extra: list[tuple[int, list[str], str]] = ()) -> pd.DataFrame:
    rows = []
    for i, rating in enumerate(login_ratings):
        rows.append(_row(f"{prefix}{i}", rating, ["login problems"], "account_login"))
    for j, (rating, themes, stage) in enumerate(extra):
        rows.append(_row(f"{prefix}x{j}", rating, themes, stage))
    return pd.DataFrame(rows)


def _row(rid: str, rating: int, themes: list[str], stage: str) -> dict:
    return {
        "review_id": rid,
        "date": pd.Timestamp(2026, 3, 1),
        "rating": rating,
        "sentiment": sentiment_from_rating(rating),
        "content": f"review {rid} with enough words to quote",
        "app_version": "1.0",
        "thumbs_up": 1,
        "reply": None,
        "category": "bug" if rating <= 2 else "praise",
        "themes": themes,
        "journey_stage": stage,
        "emotion": "neutral",
        "churn_risk": None,
        "tagged": True,
    }


def test_gaps_are_computed_not_written():
    ours = _frame("a", [1] * 8 + [5] * 2, extra=[(2, ["slow maps"], "core_experience")] * 2)
    theirs = _frame("b", [1] * 2 + [5] * 8, extra=[(5, ["dark mode request"], "settings_privacy")] * 5)
    topics = [
        {"name": "login", "apps": [topic_stats(ours, ["login problems"]), topic_stats(theirs, ["login problems"])]},
        {"name": "dark mode", "apps": [topic_stats(ours, []), topic_stats(theirs, ["dark mode request"])]},
    ]
    topics[0]["apps"][0]["themes"] = topics[0]["apps"][1]["themes"] = ["login problems"]
    topics[1]["apps"][0]["themes"], topics[1]["apps"][1]["themes"] = [], ["dark mode request"]
    topics[1]["apps"][0]["negative_share"] = 0.0
    found = benchmark_ai.find_gaps(["Us", "Them"], [ours, theirs], topics, [run_summary(ours), run_summary(theirs)])
    kinds = {(f["kind"], f["subject"]) for f in found}
    assert ("lag", "login") in kinds
    assert ("lag", "account login") not in kinds  # same reviews as the "login" topic
    assert ("learn", "dark mode") in kinds
    few = [{"mentions": 0, "share": 0.0, "negative_share": 0.0}, {"mentions": 4, "share": 0.3, "negative_share": 0.0}]
    assert benchmark_ai._compare("dark mode", few, ["Us", "Them"]) == []  # 4 reviews is too thin to learn from
    assert not any(f["kind"] == "lead" for f in found)
    login = next(f for f in found if f["subject"] == "login")
    assert login["evidence"] == "80% negative for Us vs 20% for Them"
    # A lag quotes our unhappy users and their happy ones.
    assert {(q["app"], q["rating"] <= 2) for q in login["quotes"]} == {("Us", True), ("Them", False)}


def test_benchmark_points_cite_their_own_quotes():
    ours = _frame("a", [1] * 8 + [5] * 2, extra=[(1, ["slow maps"], "core_experience")] * 4)
    theirs = _frame("b", [1] * 2 + [5] * 8, extra=[(5, ["fast maps"], "core_experience")] * 4)
    runs = [
        SimpleNamespace(app=SimpleNamespace(title=t, store_id=t), output_language="English", country="us")
        for t in ("Us", "Them")
    ]
    content = asyncio.run(
        benchmark_ai.generate(FakeProvider({}), runs, [ours, theirs], [run_summary(ours), run_summary(theirs)])
    )
    lags = content["lags"]
    assert [p["subject"] for p in lags] == ["login", "core experience"]
    assert lags[0]["point"] == "Users say so." and "made-up-id" not in lags[0]["review_ids"]
    # The model left the second point empty and cited nothing real: computed text and a real quote instead.
    assert lags[1]["point"] == "Core experience: 100% negative for Us vs 0% for Them." and lags[1]["review_ids"]
    assert set(content["reviews"]) == {i for p in lags for i in p["review_ids"]}
    # Each point shows both sides, and no review is quoted twice.
    assert [content["reviews"][i]["app"] for i in lags[0]["review_ids"]] == ["Us", "Them"]
    all_ids = [i for p in lags for i in p["review_ids"]]
    assert len(all_ids) == len(set(all_ids))


def test_benchmark_validation(client):
    a, b = _two_runs(client)
    assert client.post("/api/benchmarks", json={"run_ids": [a]}).status_code == 422
    assert client.post("/api/benchmarks", json={"run_ids": [a, a]}).status_code == 400
    assert client.post("/api/benchmarks", json={"run_ids": [a, "missing"]}).status_code == 404
    bench = client.post("/api/benchmarks", json={"run_ids": [a, b]}).json()
    assert client.delete(f"/api/benchmarks/{bench['id']}").status_code == 204
    assert client.get(f"/api/benchmarks/{bench['id']}").status_code == 404


def test_compare_tool_for_mcp(client):
    from backend.assistant.agent import chat_tools
    from backend.assistant.tools import ToolContext, run_tool

    a, b = _two_runs(client)
    ctx = client.app.state.ctx
    result = run_tool(ToolContext(ctx.db, ctx.frames), "compare_analyses", {"run_ids": [a, b]})
    assert [x["reviews"] for x in result["analyses"]] == [60, 30]
    assert "compare_analyses" not in {t.name for t in chat_tools()}
