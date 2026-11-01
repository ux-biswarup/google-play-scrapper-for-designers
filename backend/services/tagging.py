"""Batched AI tagging of reviews: category, themes, journey stage and emotion."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from ..providers import LLMError, LLMProvider, Usage

CATEGORIES = ("bug", "feature_request", "ux_friction", "complaint", "praise", "question", "other")
JOURNEY_STAGES = (
    "install_onboarding",
    "account_login",
    "core_experience",
    "search_navigation",
    "payments_subscription",
    "notifications",
    "settings_privacy",
    "support_help",
    "app_updates",
    "other",
)
EMOTIONS = ("frustration", "anger", "confusion", "disappointment", "neutral", "satisfaction", "delight")

MAX_THEMES_PER_REVIEW = 3
MAX_REVIEW_CHARS = 1500

TAG_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                    "themes": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_THEMES_PER_REVIEW},
                    "journey_stage": {"type": "string", "enum": list(JOURNEY_STAGES)},
                    "emotion": {"type": "string", "enum": list(EMOTIONS)},
                },
                "required": ["id", "category", "themes", "journey_stage", "emotion"],
            },
        }
    },
    "required": ["results"],
}

_SYSTEM = """You are a senior UX researcher tagging mobile app store reviews for a product design team.
For every review return exactly one result with the same id:
- category: bug (something broken, crashes, errors), feature_request (asks for something new),
  ux_friction (confusing, hard to use, too many steps), complaint (unhappy with pricing, ads, policy,
  content or service, but nothing is broken), praise, question, or other.
- themes: 0-{max_themes} labels of 2-4 words in lowercase {language}. Each label names a concrete part of
  the product the reviewer talks about: a feature, flow, policy, content or quality attribute
  (e.g. "login after update", "ads frequency", "battery usage", "account bans", "map loading").
  Name the subject, not the feeling: never use sentiment words or catch-alls such as "bad experience",
  "negative review", "positive experience", "good app", "overall satisfaction" or "app quality".
  If the review only expresses a feeling without saying what about ("worst", "love it", "great game"),
  return []. Prefer the same wording for the same subject across reviews.
- journey_stage: where in the user journey the feedback belongs.
- emotion: the reviewer's dominant emotion."""


@dataclass(frozen=True)
class ReviewInput:
    key: int  # database review id
    rating: int
    text: str


@dataclass
class TagResult:
    category: str
    themes: list[str]
    journey_stage: str
    emotion: str


@dataclass
class TagOutcome:
    results: dict[int, TagResult] = field(default_factory=dict)
    usage: Usage = field(default_factory=Usage)
    failed: int = 0
    errors: list[str] = field(default_factory=list)


# (results of this batch, reviews done so far, total reviews, usage so far)
BatchDoneFn = Callable[[dict[int, TagResult], int, int, Usage], Awaitable[None] | None]


def normalize_theme(label: str) -> str:
    return " ".join(str(label).strip().strip(".").lower().split())[:60]


def _coerce(item: dict) -> TagResult:
    def pick(value, allowed, default):
        value = str(value or "").strip().lower()
        return value if value in allowed else default

    themes: list[str] = []
    for raw in item.get("themes") or []:
        label = normalize_theme(raw)
        if label and label not in themes:
            themes.append(label)
    return TagResult(
        category=pick(item.get("category"), CATEGORIES, "other"),
        themes=themes[:MAX_THEMES_PER_REVIEW],
        journey_stage=pick(item.get("journey_stage"), JOURNEY_STAGES, "other"),
        emotion=pick(item.get("emotion"), EMOTIONS, "neutral"),
    )


def build_prompt(batch: Sequence[ReviewInput], app_context: str = "") -> str:
    payload = [{"id": str(i), "rating": r.rating, "text": r.text[:MAX_REVIEW_CHARS]} for i, r in enumerate(batch)]
    about = f" of {app_context}" if app_context else ""
    return f"Tag these reviews{about}.\nREVIEWS:\n" + json.dumps(payload, ensure_ascii=False)


async def tag_batch(
    provider: LLMProvider, batch: Sequence[ReviewInput], *, output_language: str = "English", app_context: str = ""
) -> tuple[dict[int, TagResult], Usage]:
    system = _SYSTEM.format(max_themes=MAX_THEMES_PER_REVIEW, language=output_language)
    data, usage = await provider.complete_json(
        system=system, prompt=build_prompt(batch, app_context), schema=TAG_SCHEMA
    )
    results: dict[int, TagResult] = {}
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        try:
            index = int(str(item.get("id")).strip())
        except ValueError:
            continue
        if 0 <= index < len(batch):
            results[batch[index].key] = _coerce(item)
    return results, usage


async def tag_reviews(
    provider: LLMProvider,
    reviews: Sequence[ReviewInput],
    *,
    batch_size: int = 25,
    concurrency: int = 4,
    output_language: str = "English",
    app_context: str = "",
    on_batch_done: BatchDoneFn | None = None,
    cancel: asyncio.Event | None = None,
) -> TagOutcome:
    """Tag reviews in parallel batches. Raises LLMError immediately on fatal errors (bad key, unknown model)."""
    outcome = TagOutcome()
    empty = [r for r in reviews if not r.text.strip()]
    for r in empty:  # star-only reviews: nothing for the model to read
        outcome.results[r.key] = TagResult("other", [], "other", "neutral")
    todo = [r for r in reviews if r.text.strip()]
    batches = [todo[i : i + batch_size] for i in range(0, len(todo), batch_size)]
    total = len(reviews)
    done = len(empty)
    semaphore = asyncio.Semaphore(max(1, concurrency))
    fatal: list[LLMError] = []

    async def run(batch: list[ReviewInput]) -> None:
        nonlocal done
        async with semaphore:
            if fatal or (cancel and cancel.is_set()):
                return
            try:
                results, usage = await tag_batch(
                    provider, batch, output_language=output_language, app_context=app_context
                )
            except LLMError as exc:
                if exc.fatal:
                    fatal.append(exc)
                    return
                results, usage = {}, Usage()
                outcome.errors.append(str(exc))
        outcome.usage.add(usage)
        outcome.results.update(results)
        outcome.failed += len(batch) - len(results)
        done += len(batch)
        if on_batch_done:
            maybe = on_batch_done(results, done, total, outcome.usage)
            if asyncio.iscoroutine(maybe):
                await maybe

    await asyncio.gather(*(run(b) for b in batches))
    if fatal:
        raise fatal[0]
    return outcome
