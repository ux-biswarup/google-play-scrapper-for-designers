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
from backend.providers import LLMConfig, LLMError, LLMProvider, ModelInfo, Usage
from backend.services.play_store import AppDetails, AppNotFound, AppSearchHit, StoreReview

# (rating, text) templates; the fake model tags reviews by keywords in the text.
TEMPLATES = [
    (1, "Login fails every time after the update"),
    (1, "I can't log in anymore, so annoying"),
    (2, "The app crashes when I open the map"),
    (5, "I love the design, it is beautiful"),
    (4, "Great app but please add dark mode"),
    (3, "It's ok"),
]


class FakeStore:
    platform = "android"

    def __init__(self, days: int = 12):
        self.days = days

    def app_details(self, store_id: str, *, lang: str, country: str) -> AppDetails:
        if store_id == "com.missing.app":
            raise AppNotFound("No Play Store app found")
        return AppDetails(store_id, "Example App", "Example Inc", "https://img/icon.png", "Tools", 4.1,
                          12345, "1,000+", "3.0", f"https://play.google.com/store/apps/details?id={store_id}")

    def search(self, query: str, *, lang: str, country: str, limit: int = 10) -> list[AppSearchHit]:
        return [AppSearchHit("com.example.app", "Example App", "Example Inc", None, 4.1)]

    def fetch_reviews(self, store_id, *, lang, country, count, ratings=None, on_progress=None) -> list[StoreReview]:
        start = datetime(2026, 1, 1, 12)
        reviews = []
        for i in range(count * 2):
            rating, text = TEMPLATES[i % len(TEMPLATES)]
            reviews.append(StoreReview(
                review_id=f"r{i}", rating=rating, content=text,
                reviewed_at=start + timedelta(hours=i * 24 * self.days / (count * 2)),
                app_version="2.0" if i >= count * 3 // 2 else "1.0", thumbs_up=i % 7, reply_content=None,
            ))
        if ratings:
            reviews = [r for r in reviews if r.rating in ratings]
        reviews = sorted(reviews, key=lambda r: r.reviewed_at, reverse=True)[:count]
        if on_progress:
            on_progress(len(reviews), count)
        return reviews


def _fake_tag(text: str) -> dict:
    lowered = text.lower()
    if "login" in lowered:
        return {"category": "Bug ", "themes": ["Login fails"], "journey_stage": "account_login", "emotion": "frustration"}
    if "log in" in lowered:
        return {"category": "bug", "themes": ["cannot log in"], "journey_stage": "account_login", "emotion": "anger"}
    if "crash" in lowered:
        return {"category": "bug", "themes": ["app crashes"], "journey_stage": "core_experience", "emotion": "frustration"}
    if "love" in lowered:
        return {"category": "praise", "themes": ["beautiful design"], "journey_stage": "core_experience", "emotion": "delight"}
    if "dark mode" in lowered:
        return {"category": "feature_request", "themes": ["dark mode request"], "journey_stage": "settings_privacy",
                "emotion": "satisfaction"}
    return {"category": "made-up", "themes": [], "journey_stage": "nowhere", "emotion": "meh"}


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
def client(llm_calls, provider_failure):
    def factory(config: LLMConfig) -> LLMProvider:
        if config.provider not in ("anthropic", "openai", "ollama"):
            raise LLMError(f"Unknown provider '{config.provider}'.", fatal=True)
        return FakeProvider(llm_calls, provider_failure.get("error"))

    app = create_app(
        Settings(database_url="sqlite://", batch_size=10, llm_concurrency=3),
        store=FakeStore(), provider_factory=factory,
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
