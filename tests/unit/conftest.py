"""Offline fakes for the Play Store and LLM providers, plus an API client fixture."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.providers import LLMConfig, LLMError, LLMProvider, ModelInfo, TextDelta, ToolCall, TurnEnd, Usage
from backend.services.play_store import AppDetails, AppNotFound, AppSearchHit, StoreReview

# (rating, text) templates; the fake model tags reviews by keywords in the text.
TEMPLATES = [
    (1, "Login fails every time after the update"),
    (1, "I can't log in anymore, so annoying"),
    (2, "The app crashes when I open the map"),
    (5, "I love the design, it is beautiful"),
    (4, "Great app but please add dark mode like Rival App"),
    (3, "It's ok"),
]


class FakeStore:
    platform = "android"

    def __init__(self, days: int = 12):
        self.days = days

    def app_details(self, store_id: str, *, lang: str, country: str) -> AppDetails:
        if store_id == "com.missing.app":
            raise AppNotFound("No Play Store app found")
        return AppDetails(
            store_id,
            "Example App",
            "Example Inc",
            "https://img/icon.png",
            "Tools",
            4.1,
            12345,
            "1,000+",
            "3.0",
            f"https://play.google.com/store/apps/details?id={store_id}",
        )

    def search(self, query: str, *, lang: str, country: str, limit: int = 10) -> list[AppSearchHit]:
        return [AppSearchHit("com.example.app", "Example App", "Example Inc", None, 4.1)]

    def scan_window(
        self, store_id, *, lang, country, date_from, date_to, ratings=None, max_scan=10_000, on_progress=None
    ):
        """120 reviews spread over 12 days (Jan 1-12, 2026), filtered to the period like the real scan."""
        from backend.services.play_store import ReviewWindow

        self.scans = getattr(self, "scans", 0) + 1
        everything = []
        for i in range(120):  # every 2.4 hours from Jan 1, newest first
            rating, text = TEMPLATES[i % len(TEMPLATES)]
            when = datetime(2026, 1, 1, 12) + timedelta(hours=i * 2.4)
            everything.append(StoreReview(f"w{i}", rating, text, when, "1.0", i % 5, None))
        everything = [r for r in reversed(everything) if not ratings or r.rating in ratings]
        inside = [
            r
            for r in everything
            if (not date_from or r.reviewed_at.date() >= date_from) and (not date_to or r.reviewed_at.date() <= date_to)
        ]
        return ReviewWindow(
            reviews=inside, scanned=len(everything), complete=True, oldest_reached=everything[-1].reviewed_at
        )

    def fetch_reviews(self, store_id, *, lang, country, count, ratings=None, on_progress=None) -> list[StoreReview]:
        start = datetime(2026, 1, 1, 12)
        reviews = []
        for i in range(count * 2):
            rating, text = TEMPLATES[i % len(TEMPLATES)]
            reviews.append(
                StoreReview(
                    review_id=f"r{i}",
                    rating=rating,
                    content=text,
                    reviewed_at=start + timedelta(hours=i * 24 * self.days / (count * 2)),
                    app_version="2.0" if i >= count * 3 // 2 else "1.0",
                    thumbs_up=i % 7,
                    reply_content=None,
                )
            )
        if ratings:
            reviews = [r for r in reviews if r.rating in ratings]
        reviews = sorted(reviews, key=lambda r: r.reviewed_at, reverse=True)[:count]
        if on_progress:
            on_progress(len(reviews), count)
        return reviews


def _fake_tag(text: str) -> dict:
    """Keyword-based tags, including the v2+ fields (churn evidence must quote the review)."""
    tags = _fake_core_tag(text)
    lowered = text.lower()
    tags["severity"] = (
        "high" if "crash" in lowered else "medium" if tags["category"].strip().lower() == "bug" else "none"
    )
    tags["user_type"] = "long_time_user" if "update" in lowered else "unknown"
    tags["churn_risk"] = "considering" if "annoying" in lowered else "none"
    tags["churn_evidence"] = "so annoying" if "annoying" in lowered else ""
    tags["competitors"] = ["Rival App", "Imaginary App"] if "dark mode" in lowered else []
    tags["accessibility"] = "map" in lowered
    return tags


def _fake_core_tag(text: str) -> dict:
    lowered = text.lower()
    if "login" in lowered:
        return {
            "category": "Bug ",
            "themes": ["Login fails"],
            "journey_stage": "account_login",
            "emotion": "frustration",
        }
    if "log in" in lowered:
        return {"category": "bug", "themes": ["cannot log in"], "journey_stage": "account_login", "emotion": "anger"}
    if "crash" in lowered:
        return {
            "category": "bug",
            "themes": ["app crashes"],
            "journey_stage": "core_experience",
            "emotion": "frustration",
        }
    if "love" in lowered:
        return {
            "category": "praise",
            "themes": ["beautiful design"],
            "journey_stage": "core_experience",
            "emotion": "delight",
        }
    if "dark mode" in lowered:
        return {
            "category": "feature_request",
            "themes": ["dark mode request"],
            "journey_stage": "settings_privacy",
            "emotion": "satisfaction",
        }
    return {"category": "made-up", "themes": [], "journey_stage": "nowhere", "emotion": "meh"}


def _fake_artifact(props: dict, prompt: str) -> dict | None:
    """Scripted decision artifacts that cite one real review id and one invented id."""
    if "FACTS:" not in prompt:
        return None
    real = re.search(r'"id": "([^"]+)"', prompt.split("FACTS:", 1)[1]).group(1)
    ids = [real, "made-up-id"]
    if "decisions" in props:
        decision = {
            "title": "Make login reliable",
            "lens": "product",
            "action": "fix",
            "theme": "login problems",
            "problem": "People can't log in.",
            "evidence": "20 reviews, 100% negative",
            "review_ids": ids,
            "who": "Everyone",
            "root_causes": ["Session bug"],
            "how_might_we": ["How might we..."],
            "options": [{"idea": "Retry login", "effort": "low"}],
            "impact": "high",
            "confidence": "high",
            "effort": "medium",
            "metric": "negative share of login problems",
            "risk_of_inaction": "Churn",
        }
        protect = {
            **decision,
            "title": "Keep the design",
            "lens": "design",
            "action": "protect",
            "theme": "beautiful design",
            "impact": "low",
            "confidence": "medium",
            "effort": "high",
        }
        return {"decisions": [protect, decision]}
    if "key_findings" in props:
        return {
            "title": "Login is the problem",
            "summary": "Summary.",
            "key_findings": [
                {"heading": "Login fails", "detail": "Many login problems.", "review_ids": ids},
                {"heading": "Crashes on the map", "detail": "The app crashes on the map.", "review_ids": []},
            ],
            "user_needs": ["Users need to log in"],
            "opportunities": [],
            "recommendations": [{"heading": "Fix login", "detail": "Now.", "when": "soon"}],
            "open_questions": ["Which devices?"],
        }
    if "changes" in props:
        return {
            "headline": "Login got worse.",
            "next_step": "Fix login.",
            "changes": [{"kind": "worse", "theme": "login problems", "detail": "Up.", "review_ids": ids}],
        }
    if "personas" in props:
        return {
            "personas": [
                {
                    "name": "The veteran",
                    "who": "Long-time user",
                    "goals": ["Play"],
                    "frustrations": ["Login"],
                    "behaviours": ["Daily"],
                    "how_common": "10 reviews",
                    "design_implications": ["Easy login"],
                    "review_ids": ids,
                }
            ]
        }
    return None


class FakeProvider(LLMProvider):
    def __init__(self, calls: dict, fail: LLMError | None = None):
        self.calls = calls
        self.fail = fail

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo("fake-1", "Fake 1")]

    async def complete_json(self, *, system, prompt, schema, max_tokens=8000):
        if self.fail:
            raise self.fail
        props = schema.get("properties", {})
        artifact = _fake_artifact(props, prompt)
        if artifact is not None:
            self.calls["artifact"] = self.calls.get("artifact", 0) + 1
            return artifact, Usage(50, 40)
        if "results" in props:
            self.calls["tag"] = self.calls.get("tag", 0) + 1
            items = json.loads(prompt.split("REVIEWS:\n", 1)[1])
            return {"results": [{"id": it["id"], **_fake_tag(it["text"])} for it in items]}, Usage(100, 50)
        if "themes" in props:
            self.calls["group"] = self.calls.get("group", 0) + 1
            labels = dict(re.findall(r"^(\d+)\. (.+?) \(\d+\)$", prompt.split("\n", 1)[1], re.M))
            themes: dict[str, list[int]] = {}
            for index, label in labels.items():
                name = "login problems" if "log" in label else label
                themes.setdefault(name, []).append(int(index))
            return {"themes": [{"name": n, "members": m} for n, m in themes.items()]}, Usage(20, 10)
        return {"ok": True}, Usage(1, 1)

    async def chat_stream(self, *, system, messages, tools, max_tokens=4000):
        """Scripted assistant: first look something up, then answer citing a review from the tool result."""
        if self.fail:
            raise self.fail
        self.calls["chat"] = self.calls.get("chat", 0) + 1
        self.calls.setdefault("chat_history_sizes", []).append(len(messages))
        last = messages[-1]
        if last.role == "user":
            if "bad metric" in last.content:
                yield TurnEnd([ToolCall("c1", "query_metrics", {"measures": ["profit"]})], Usage(5, 1))
            else:
                yield TurnEnd([ToolCall("c1", "get_problems", {"limit": 3})], Usage(5, 1))
            return
        cited = re.search(r'"review_id": "([^"]+)"', last.content)
        if cited:
            for part in ("The biggest problem is login. ", f"[[r:{cited.group(1)}]]"):
                yield TextDelta(part)
        else:
            yield TextDelta(f"That lookup failed: {json.loads(last.content).get('error', '')}")
        yield TurnEnd([], Usage(10, 5))


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Ignore keys/models from the developer's real .env so tests behave the same everywhere."""
    from backend.providers import PROVIDERS

    for spec in PROVIDERS.values():
        if spec.env_var:
            monkeypatch.delenv(spec.env_var, raising=False)
        monkeypatch.delenv(f"{spec.id.upper()}_MODEL", raising=False)


@pytest.fixture
def llm_calls() -> dict:
    return {}


@pytest.fixture
def provider_failure() -> dict:
    """Set provider_failure["error"] = LLMError(...) to make every model call fail."""
    return {}


@pytest.fixture
def client(llm_calls, provider_failure, tmp_path):
    def factory(config: LLMConfig) -> LLMProvider:
        if config.provider not in ("anthropic", "openai", "ollama"):
            raise LLMError(f"Unknown provider '{config.provider}'.", fatal=True)
        return FakeProvider(llm_calls, provider_failure.get("error"))

    app = create_app(
        Settings(database_url="sqlite://", data_dir=tmp_path, batch_size=10, llm_concurrency=3),
        store=FakeStore(),
        provider_factory=factory,
    )
    with TestClient(app) as test_client:
        yield test_client


def wait_for_run(client: TestClient, run_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in ("completed", "failed", "cancelled"):
            return run
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish: {run}")


RUN_BODY = {
    "app": "https://play.google.com/store/apps/details?id=com.example.app&hl=en",
    "count": 60,
    "llm": {"provider": "anthropic", "model": "fake-model", "api_key": "sk-test-secret-123"},
}
