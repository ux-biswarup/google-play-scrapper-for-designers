"""Decision views (feedback boards, journey, emotions, segments, risks), v2 tags and the DB migration."""

from __future__ import annotations

import sqlite3

from conftest import RUN_BODY, wait_for_run

from backend.db import Database
from backend.models import TAG_VERSION
from backend.services.tagging import _coerce, _is_named_product


def _run(client) -> str:
    run = wait_for_run(client, client.post("/api/runs", json=RUN_BODY).json()["id"])
    assert run["status"] == "completed" and run["tag_version"] == TAG_VERSION
    return run["id"]


def test_evidence_checks_on_new_tags():
    text = "I'm going to uninstall this. Monopoly Go is better"
    kept = _coerce(
        {"churn_risk": "left", "churn_evidence": "going to  UNINSTALL this", "competitors": ["Monopoly Go"]}, text
    )
    assert kept.churn_risk == "left" and kept.competitors == ["Monopoly Go"]
    invented = _coerce({"churn_risk": "considering", "churn_evidence": "I quit", "competitors": ["Candy Crush"]}, text)
    assert invented.churn_risk == "none" and invented.competitors == []
    assert not _is_named_product("other games") and _is_named_product("Pokémon Sleep")
    defaults = _coerce({"severity": "extreme", "user_type": "alien", "accessibility": "yes"})
    assert (defaults.severity, defaults.user_type, defaults.accessibility) == ("none", "unknown", False)


def test_feedback_boards(client):
    data = client.get(f"/api/runs/{_run(client)}/views/feedback").json()
    bugs = data["boards"]["bug"]
    assert data["has_severity"] and bugs["count"] == 30
    assert {s["value"] for s in bugs["severity"]} == {"high", "medium"}
    top = bugs["items"][0]
    assert top["theme"] in ("app crashes", "login problems") and top["quotes"]
    requests = data["boards"]["feature_request"]["items"]
    assert requests[0]["theme"] == "dark mode request" and requests[0]["mentions"] == 10


def test_journey_map(client):
    data = client.get(f"/api/runs/{_run(client)}/views/journey").json()
    stages = {s["stage"]: s for s in data["stages"]}
    assert data["worst_stage"] == "account_login"
    login = stages["account_login"]
    assert login["negative_share"] == 1.0 and login["problems"][0]["theme"] == "login problems"
    assert login["quote"]["rating"] == 1
    assert stages["core_experience"]["praise"][0]["theme"] == "beautiful design"


def test_emotions_view(client):
    data = client.get(f"/api/runs/{_run(client)}/views/emotions").json()
    assert {d["value"] for d in data["distribution"]} >= {"frustration", "anger", "delight"}
    login = next(row for row in data["matrix"] if row["theme"] == "login problems")
    assert login["counts"]["frustration"] == 10 and login["counts"]["anger"] == 10
    assert data["series"] and "confusion" in data["meaning"]


def test_segments_view(client):
    run_id = _run(client)
    users = client.get(f"/api/runs/{run_id}/views/segments", params={"by": "user_type"}).json()
    assert not users["needs_reanalysis"]
    long_time = next(s for s in users["segments"] if s["value"] == "long_time_user")
    assert long_time["reviews"] == 10 and long_time["distinctive_themes"][0]["theme"] == "login problems"
    detail = client.get(f"/api/runs/{run_id}/views/segments", params={"by": "detail"}).json()
    assert sum(s["reviews"] for s in detail["segments"]) == 60
    assert client.get(f"/api/runs/{run_id}/views/segments", params={"by": "zodiac"}).status_code == 400


def test_risks_view(client):
    data = client.get(f"/api/runs/{_run(client)}/views/risks").json()
    assert data["available"]
    assert data["churn"]["considering"] == 10 and data["churn"]["themes"][0]["theme"] == "login problems"
    assert [c["name"] for c in data["competitors"]] == ["Rival App"]  # "Imaginary App" isn't in any review


def test_views_report_missing_tags_on_old_analyses(client):
    run_id = _run(client)
    with client.app.state.ctx.db.session() as s:
        s.execute(__import__("sqlalchemy").text("UPDATE insights SET severity = NULL, churn_risk = NULL"))
    client.app.state.ctx.frames._items.clear()
    assert client.get(f"/api/runs/{run_id}/views/risks").json()["available"] is False
    assert client.get(f"/api/runs/{run_id}/views/segments", params={"by": "user_type"}).json()["needs_reanalysis"]


def test_migration_adds_new_columns(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE runs (id VARCHAR(32) PRIMARY KEY, provider VARCHAR(32), model VARCHAR(128));
        INSERT INTO runs VALUES ('r1', 'openai', 'gpt');
        CREATE TABLE insights (id INTEGER PRIMARY KEY, review_id INTEGER, model_key VARCHAR(160));
        """
    )
    conn.close()
    db = Database(f"sqlite:///{path}")
    db.init()
    db.init()  # running again is a no-op
    conn = sqlite3.connect(path)
    run_cols = [r[1] for r in conn.execute("PRAGMA table_info(runs)")]
    insight_cols = [r[1] for r in conn.execute("PRAGMA table_info(insights)")]
    assert "tag_version" in run_cols and {"severity", "churn_risk", "competitors"} <= set(insight_cols)
    assert conn.execute("SELECT tag_version FROM runs").fetchone() == (1,)
