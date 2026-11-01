from __future__ import annotations

from conftest import RUN_BODY, wait_for_run
from sqlalchemy import text

from backend.providers import LLMError


def _start(client, **overrides) -> str:
    response = client.post("/api/runs", json=RUN_BODY | overrides)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_full_analysis_run(client, llm_calls):
    run = wait_for_run(client, _start(client))
    assert run["status"] == "completed", run
    assert run["review_count"] == 60
    assert run["tagged_count"] == 60 and run["failed_count"] == 0
    assert run["input_tokens"] > 0
    assert run["app"]["title"] == "Example App"
    assert llm_calls == {"tag": 6, "group": 1}  # 60 reviews / batches of 10, plus one theme-grouping call

    overview = client.get(f"/api/runs/{run['id']}/overview").json()
    assert overview["kpis"]["review_count"] == 60
    assert sum(r["review_count"] for r in overview["rating_distribution"]) == 60
    categories = {c["category"]: c["review_count"] for c in overview["category_distribution"]}
    assert categories["bug"] == 30  # "Bug " from the model was normalised
    assert {e["emotion"] for e in overview["emotion_distribution"]} <= {
        "frustration",
        "anger",
        "confusion",
        "disappointment",
        "neutral",
        "satisfaction",
        "delight",
    }

    board = client.get(f"/api/runs/{run['id']}/themes").json()
    problems = {p["theme"]: p for p in board["problems"]}
    assert "login problems" in problems  # "login fails" + "cannot log in" grouped into one theme
    assert problems["login problems"]["mentions"] == 20
    assert problems["login problems"]["quotes"][0]["rating"] == 1
    assert board["problems"][0]["theme"] == "login problems"  # highest impact first
    assert "beautiful design" in {s["theme"] for s in board["strengths"]}


def test_insight_endpoints(client):
    run_id = wait_for_run(client, _start(client))["id"]

    reviews = client.get(f"/api/runs/{run_id}/reviews", params={"theme": "login problems", "page_size": 5}).json()
    assert reviews["total"] == 20 and len(reviews["items"]) == 5
    assert all("login problems" in r["themes"] for r in reviews["items"])
    search = client.get(f"/api/runs/{run_id}/reviews", params={"q": "DARK MODE", "rating": [4]}).json()
    assert search["total"] == 10

    metrics = client.post(
        f"/api/runs/{run_id}/metrics",
        json={
            "measures": ["review_count", "avg_rating"],
            "dimensions": ["category"],
            "order_by": "review_count",
        },
    ).json()["rows"]
    assert metrics[0] == {"category": "bug", "review_count": 30, "avg_rating": 1.3333}
    bad = client.post(f"/api/runs/{run_id}/metrics", json={"measures": ["profit"]})
    assert bad.status_code == 400 and "Unknown measures" in bad.json()["detail"]

    trends = client.get(f"/api/runs/{run_id}/trends", params={"grain": "day"}).json()
    assert sum(p["review_count"] for p in trends["series"]) == 60
    assert [v["app_version"] for v in trends["versions"]] == ["1.0", "2.0"]

    compare = client.get(f"/api/runs/{run_id}/compare", params={"mode": "version", "pivot": "2.0"}).json()
    assert compare["before"]["review_count"] + compare["after"]["review_count"] == 60

    png = client.get(f"/api/runs/{run_id}/charts/top-problems.png")
    assert png.status_code == 200 and png.content.startswith(b"\x89PNG")
    svg = client.get(f"/api/runs/{run_id}/charts/rating-distribution.svg")
    assert svg.headers["content-type"].startswith("image/svg+xml")

    events = client.get(f"/api/runs/{run_id}/events").text
    assert "event: progress" in events and "event: end" in events


def test_rerun_reuses_cached_insights(client, llm_calls):
    wait_for_run(client, _start(client))
    tag_calls = llm_calls["tag"]
    second = wait_for_run(client, _start(client))
    assert second["status"] == "completed"
    assert llm_calls["tag"] == tag_calls  # nothing re-tagged with the same model
    assert client.get("/api/runs").json()[0]["id"] == second["id"]


def test_negative_only_filter(client):
    run = wait_for_run(client, _start(client, ratings=[2, 1, 1]))
    assert run["ratings"] == [1, 2]
    ratings = client.get(f"/api/runs/{run['id']}/overview").json()["rating_distribution"]
    assert all(r["review_count"] == 0 for r in ratings if r["rating"] > 2)


def test_rejected_key_fails_run_with_clear_message(client, provider_failure):
    provider_failure["error"] = LLMError("Anthropic rejected the API key.", fatal=True)
    run = wait_for_run(client, _start(client))
    assert run["status"] == "failed"
    assert "rejected the API key" in run["error"]


def test_api_key_is_never_stored_or_returned(client):
    run_id = wait_for_run(client, _start(client))["id"]
    secret = RUN_BODY["llm"]["api_key"]
    assert secret not in client.get(f"/api/runs/{run_id}").text
    assert secret not in client.get("/api/runs").text
    with client.app.state.ctx.db.engine.connect() as conn:
        for table in ("apps", "reviews", "runs", "run_reviews", "insights"):
            for row in conn.execute(text(f"SELECT * FROM {table}")):
                assert secret not in str(row)


def test_validation_errors(client):
    assert client.post("/api/runs", json=RUN_BODY | {"app": "not an app id"}).status_code == 400
    assert client.post("/api/runs", json=RUN_BODY | {"ratings": [6]}).status_code == 422
    assert client.post("/api/runs", json=RUN_BODY | {"count": 5}).status_code == 422
    unknown = client.post("/api/runs", json=RUN_BODY | {"llm": {"provider": "nope", "model": "x"}})
    assert unknown.status_code == 400 and "Unknown provider" in unknown.json()["detail"]
    missing = wait_for_run(client, _start(client, app="com.missing.app"))
    assert missing["status"] == "failed" and "No Play Store app" in missing["error"]
    assert client.get("/api/runs/nope/overview").status_code == 404


def test_cancel_and_delete(client):
    run_id = wait_for_run(client, _start(client))["id"]
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 409  # already finished
    assert client.delete(f"/api/runs/{run_id}").status_code == 204
    assert client.get(f"/api/runs/{run_id}").status_code == 404


def test_provider_endpoints(client):
    providers = {p["id"]: p for p in client.get("/api/providers").json()}
    assert {"anthropic", "openai", "gemini", "ollama", "custom"} <= set(providers)
    assert providers["custom"]["requires_base_url"] is True
    models = client.post("/api/providers/models", json={"provider": "anthropic", "api_key": "k"}).json()
    assert models["models"][0]["id"] == "fake-1"
    test = client.post("/api/providers/test", json={"provider": "anthropic", "model": "fake-1", "api_key": "k"}).json()
    assert test["ok"] is True
    assert client.post("/api/providers/test", json={"provider": "anthropic", "api_key": "k"}).status_code == 400


def test_estimate_and_app_search(client):
    estimate = client.post("/api/runs/estimate", json={"count": 500}).json()
    assert estimate["ai_requests"] == 51 and estimate["seconds"] > 0
    assert client.get("/api/apps/search", params={"q": "example"}).json()[0]["store_id"] == "com.example.app"
    assert client.get("/api/apps/lookup", params={"id": "com.example.app"}).json()["title"] == "Example App"


def test_serves_built_frontend(tmp_path):
    from fastapi.testclient import TestClient

    from backend.config import Settings
    from backend.main import create_app

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("nope")
    with TestClient(create_app(Settings(database_url="sqlite://", web_dist=tmp_path))) as client:
        assert client.get("/runs/abc").text == "<div id=root></div>"  # client-side route
        assert client.get("/assets/app.js").text == "console.log(1)"
        assert "nope" not in client.get("/../secret.txt").text
        assert client.get("/api/does-not-exist").status_code == 404
        assert client.get("/api/health").json()["status"] == "ok"
