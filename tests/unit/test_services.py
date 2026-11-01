"""Unit tests for providers, Play Store parsing, AI tagging, theme grouping and legacy import."""

from __future__ import annotations

import asyncio
import json
import ssl
from datetime import datetime

import pytest
from sqlalchemy import select

from backend.db import Database
from backend.models import Insight, Run
from backend.providers import LLMConfig, LLMError, Usage, create_provider, extract_json_object, resolve_config
from backend.providers.openai_provider import is_chat_model
from backend.services import play_store
from backend.services.legacy_import import import_legacy_reports
from backend.services.play_store import PlayStoreClient, parse_store_id
from backend.services.tagging import ReviewInput, tag_reviews
from backend.services.themes import build_theme_map
from conftest import FakeProvider

# ---- providers ------------------------------------------------------------


def test_extract_json_object_variants():
    assert extract_json_object('{"a": 1}') == {"a": 1}
    assert extract_json_object('Sure!\n```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}
    assert extract_json_object("prefix {\"a\": {\"b\": 2}} suffix") == {"a": {"b": 2}}
    assert extract_json_object("no json here") is None
    assert extract_json_object("[1, 2]") is None


def test_chat_model_filter():
    assert is_chat_model("gpt-4.1-mini")
    assert is_chat_model("models/gemini-2.5-flash")
    assert not is_chat_model("text-embedding-3-small")
    assert not is_chat_model("whisper-1")


def test_api_key_hidden_from_repr():
    assert "sk-secret" not in repr(LLMConfig("openai", "gpt", "sk-secret"))


def test_env_key_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    assert resolve_config(LLMConfig("openai", "gpt")).api_key == "from-env"
    assert resolve_config(LLMConfig("openai", "gpt", "pasted")).api_key == "pasted"


def test_create_provider_validation(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(LLMError, match="needs an API key"):
        create_provider(LLMConfig("groq", "llama"))
    with pytest.raises(LLMError, match="base URL"):
        create_provider(LLMConfig("custom", "my-model"))
    with pytest.raises(LLMError, match="Unknown provider"):
        create_provider(LLMConfig("nope", "x"))
    assert create_provider(LLMConfig("ollama", "llama3")) is not None


# ---- Play Store -----------------------------------------------------------


def test_parse_store_id():
    assert parse_store_id(" com.example.app ") == "com.example.app"
    assert parse_store_id("https://play.google.com/store/apps/details?id=com.foo.bar&hl=en_US") == "com.foo.bar"
    assert parse_store_id("play.google.com/store/apps/details?id=com.foo.bar") == "com.foo.bar"
    for bad in ("", "example", "https://example.com/?x=1", "com.example app"):
        with pytest.raises(ValueError):
            parse_store_id(bad)


def test_tls_verification_restored():
    context = ssl._create_default_https_context()
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname


def test_fetch_reviews_merges_rating_filters(monkeypatch):
    class Token:
        token = None

    pages = {
        1: [{"reviewId": "a", "score": 1, "content": "bad", "at": datetime(2026, 1, 3)},
            {"reviewId": "b", "score": 1, "content": "worse", "at": datetime(2026, 1, 1)}],
        2: [{"reviewId": "c", "score": 2, "content": "meh", "at": datetime(2026, 1, 2),
             "reviewCreatedVersion": ["weird"], "thumbsUpCount": 4}],
    }

    def fake_reviews(app_id, *, filter_score_with, count, **_kwargs):
        return pages[filter_score_with][:count], Token()

    monkeypatch.setattr(play_store, "gp_reviews", fake_reviews)
    progress = []
    result = PlayStoreClient().fetch_reviews(
        "com.x.y", lang="en", country="us", count=2, ratings=[2, 1], on_progress=lambda d, t: progress.append((d, t))
    )
    assert [r.review_id for r in result] == ["a", "c"]  # newest two across both ratings
    assert result[1].app_version is None and result[1].thumbs_up == 4
    assert progress[-1] == (3, 4)


# ---- tagging & themes -----------------------------------------------------


def _inputs(*texts: str) -> list[ReviewInput]:
    return [ReviewInput(key=i + 100, rating=1, text=t) for i, t in enumerate(texts)]


def test_tag_reviews_coerces_and_batches():
    calls: dict = {}
    reviews = _inputs("login fails", "the app crashes", "", "random words")
    progress = []
    outcome = asyncio.run(tag_reviews(
        FakeProvider(calls), reviews, batch_size=2, concurrency=2,
        on_batch_done=lambda res, done, total, usage: progress.append((done, total)),
    ))
    assert calls["tag"] == 2  # empty review is never sent to the model
    assert outcome.failed == 0 and len(outcome.results) == 4
    assert outcome.results[100].category == "bug" and outcome.results[100].themes == ["login fails"]
    unknown = outcome.results[103]
    assert (unknown.category, unknown.journey_stage, unknown.emotion) == ("other", "other", "neutral")
    assert outcome.results[102].themes == []
    assert outcome.usage.input_tokens == 200
    assert sorted(progress)[-1] == (4, 4)


def test_tag_reviews_counts_missing_and_failed_results():
    class Partial(FakeProvider):
        async def complete_json(self, *, system, prompt, schema, max_tokens=8000):
            if "boom" in prompt:
                raise LLMError("temporary outage")
            data, usage = await super().complete_json(system=system, prompt=prompt, schema=schema)
            return {"results": data["results"][:1]}, usage  # model "forgot" one review

    outcome = asyncio.run(tag_reviews(Partial({}), _inputs("a", "b", "boom", "boom2"), batch_size=2))
    assert outcome.failed == 3
    assert outcome.errors == ["temporary outage"]


def test_tag_reviews_raises_fatal_errors():
    failing = FakeProvider({}, fail=LLMError("bad key", fatal=True))
    with pytest.raises(LLMError, match="bad key"):
        asyncio.run(tag_reviews(failing, _inputs("a", "b", "c"), batch_size=1))


def test_build_theme_map_groups_and_falls_back():
    from collections import Counter

    counts = Counter({"login fails": 5, "cannot log in": 3, "app crashes": 2})
    mapping, usage, warning = asyncio.run(build_theme_map(FakeProvider({}), counts))
    assert mapping == {"login fails": "login problems", "cannot log in": "login problems", "app crashes": "app crashes"}
    assert warning is None and usage.input_tokens == 20

    flaky = FakeProvider({}, fail=LLMError("timeout"))
    mapping, usage, warning = asyncio.run(build_theme_map(flaky, counts))
    assert mapping["login fails"] == "login fails" and "skipped" in warning and usage == Usage()


# ---- legacy import --------------------------------------------------------


def test_legacy_import_is_idempotent(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "com.old.app_reviews.json").write_text(json.dumps([
        {"review_id": "x1", "date": "2026-02-01T10:00:00", "rating": 1, "content": "Crashes",
         "app_version": "1.2", "topics": ["App Crashes", "error", "app crashes"]},
        {"review_id": "x2", "date": "2026-02-02T10:00:00", "rating": 5, "content": "Nice", "app_version": "unknown",
         "topics": []},
    ]))
    (reports / "com.old.app_report.json").write_text(json.dumps({"app_info": {"title": "Old App", "score": 3.9}}))
    db = Database("sqlite://")
    db.init()

    assert len(import_legacy_reports(db, reports)) == 1
    assert import_legacy_reports(db, reports) == []
    with db.session() as s:
        run = s.scalar(select(Run))
        assert (run.app.title, run.review_count, run.status) == ("Old App", 2, "completed")
        themes = sorted(s.scalars(select(Insight.themes)).all(), key=len)
        assert themes == [[], ["app crashes"]]


def test_provider_message_extracts_reason():
    from backend.providers.base import provider_message

    class FakeAPIError(Exception):
        body = {"type": "error", "error": {"type": "invalid_request_error", "message": "Your credit balance is too low"}}

    assert provider_message(FakeAPIError("Error code: 400 - {...}")) == "Your credit balance is too low"
    assert provider_message(ValueError("plain   message")) == "plain message"
