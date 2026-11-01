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
SEVERITIES = ("high", "medium", "low", "none")
USER_TYPES = ("new_user", "long_time_user", "paying_user", "unknown")
CHURN_RISKS = ("left", "considering", "none")
MAX_COMPETITORS = 3

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
                    "severity": {"type": "string", "enum": list(SEVERITIES)},
                    "user_type": {"type": "string", "enum": list(USER_TYPES)},
                    "churn_risk": {"type": "string", "enum": list(CHURN_RISKS)},
                    "churn_evidence": {"type": "string"},
                    "competitors": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_COMPETITORS},
                    "accessibility": {"type": "boolean"},
                },
                "required": [
                    "id",
                    "category",
                    "themes",
                    "journey_stage",
                    "emotion",
                    "severity",
                    "user_type",
                    "churn_risk",
                    "churn_evidence",
                    "competitors",
                    "accessibility",
                ],
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
- emotion: the reviewer's dominant emotion.
- severity: how much the issue hurts the user. high: blocks use, loses data or money, crashes; medium: clearly
  degrades the experience; low: minor annoyance; none: no problem reported (e.g. praise).
- user_type: new_user (just installed, first days), long_time_user (mentions using it for months or years),
  paying_user (mentions paying, subscriptions or purchases), otherwise unknown. Don't guess.
- churn_risk: left only if they say they uninstalled, quit, cancelled or stopped using it; considering only if
  they explicitly say they will stop, uninstall, cancel or switch. Anger or a low rating alone is none.
- churn_evidence: for left or considering, copy the exact words from the review that say so; otherwise "".
- competitors: specific named apps or products mentioned as alternatives or comparisons (e.g. "Monopoly Go"),
  never generic phrases like "other games" or "other apps"; else [].
- accessibility: true only if the feedback is about accessibility (vision, text size, contrast, colour
  blindness, screen readers, hearing, motor or cognitive difficulty)."""


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
    severity: str = "none"
    user_type: str = "unknown"
    churn_risk: str = "none"
    competitors: list[str] = field(default_factory=list)
    accessibility: bool = False


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


_GENERIC_WORDS = {"other", "others", "another", "similar", "any", "some", "games", "apps", "app", "game", "ones"}


def _is_named_product(name: str) -> bool:
    """Reject vague phrases ("other games", "similar apps") that models sometimes return as competitors."""
    words = name.lower().split()
    return bool(words) and not all(w in _GENERIC_WORDS for w in words) and words[0] not in {"other", "another"}


def _squash(text: str) -> str:
    return " ".join(str(text).lower().split())


def _verified_churn(item: dict, text: str) -> str:
    """Keep a churn tag only when the model quotes words that really are in the review."""
    risk = str(item.get("churn_risk") or "").strip().lower()
    if risk not in ("left", "considering"):
        return "none"
    if not text:
        return risk
    evidence = _squash(item.get("churn_evidence") or "")
    return risk if len(evidence) >= 4 and evidence in _squash(text) else "none"


def _coerce(item: dict, text: str = "") -> TagResult:
    def pick(value, allowed, default):
        value = str(value or "").strip().lower()
        return value if value in allowed else default

    themes: list[str] = []
    for raw in item.get("themes") or []:
        label = normalize_theme(raw)
        if label and label not in themes:
            themes.append(label)
    competitors: list[str] = []
    for raw in item.get("competitors") or []:
        name = " ".join(str(raw).strip().split())[:40]
        mentioned = not text or _squash(name) in _squash(text)  # must really appear in the review
        if _is_named_product(name) and mentioned and name.lower() not in {c.lower() for c in competitors}:
            competitors.append(name)
    return TagResult(
        category=pick(item.get("category"), CATEGORIES, "other"),
        themes=themes[:MAX_THEMES_PER_REVIEW],
        journey_stage=pick(item.get("journey_stage"), JOURNEY_STAGES, "other"),
        emotion=pick(item.get("emotion"), EMOTIONS, "neutral"),
        severity=pick(item.get("severity"), SEVERITIES, "none"),
        user_type=pick(item.get("user_type"), USER_TYPES, "unknown"),
        churn_risk=_verified_churn(item, text),
        competitors=competitors[:MAX_COMPETITORS],
        accessibility=item.get("accessibility") is True,
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
            results[batch[index].key] = _coerce(item, batch[index].text)
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
        outcome.results[r.key] = TagResult("other", [], "other", "neutral")  # defaults for the v2 fields
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
